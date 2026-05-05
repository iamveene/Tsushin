"""Shared service layer for Agent Teams HTTP APIs."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import get_session_factory
from models import (
    Agent,
    AgentTeam,
    AgentTeamMember,
    AgentTeamMemberRun,
    AgentTeamRun,
    Contact,
    SandboxedTool,
    TeamMemberRole,
    TeamRunStatus,
    TeamStatus,
    TeamTopology,
)
from services.team_membership_service import TeamMembershipError, TeamMembershipService
from services.team_orchestrator_service import TeamRunOrchestrator, TeamValidationError

logger = logging.getLogger(__name__)

ACTIVE_RUN_STATUSES = {TeamRunStatus.PENDING.value, TeamRunStatus.RUNNING.value}
CANCELLED_STATUS = "cancelled"


class AgentTeamApiError(ValueError):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


def _membership_service(db: Session, tenant_id: str) -> TeamMembershipService:
    try:
        return TeamMembershipService(db, tenant_id, auto_commit=False)
    except TypeError:
        return TeamMembershipService(db, tenant_id)


def _commit_membership_service(service: TeamMembershipService, db: Session) -> None:
    if hasattr(service, "commit"):
        service.commit()
    elif db.in_transaction():
        db.commit()


def _rollback_membership_service(service: TeamMembershipService, db: Session) -> None:
    if hasattr(service, "rollback"):
        service.rollback()
    elif db.in_transaction():
        db.rollback()


def _team_tools_payload(tool_ids: list[int]) -> dict[str, list[int]]:
    return {"sandboxed_tool_ids": list(dict.fromkeys(int(tool_id) for tool_id in tool_ids))}


def _extract_tool_ids(tools: Any) -> list[int]:
    if tools is None:
        return []
    if hasattr(tools, "sandboxed_tool_ids"):
        return list(getattr(tools, "sandboxed_tool_ids") or [])
    if isinstance(tools, dict):
        return list(tools.get("sandboxed_tool_ids") or [])
    return []


def _agent_name_map(db: Session, agent_ids: list[int]) -> dict[int, str]:
    if not agent_ids:
        return {}
    rows = (
        db.query(Agent.id, Contact.friendly_name)
        .join(Contact, Contact.id == Agent.contact_id)
        .filter(Agent.id.in_(agent_ids))
        .all()
    )
    return {agent_id: friendly_name for agent_id, friendly_name in rows}


class AgentTeamApiService:
    def __init__(self, db: Session, tenant_id: str, *, user_id: Optional[int] = None):
        if not tenant_id:
            raise AgentTeamApiError(400, "Tenant context is required")
        self.db = db
        self.tenant_id = tenant_id
        self.user_id = user_id

    def list_teams(
        self,
        *,
        page: int,
        page_size: int,
        status: Optional[str] = None,
        include_archived: bool = False,
    ) -> dict[str, Any]:
        query = self.db.query(AgentTeam).filter(AgentTeam.tenant_id == self.tenant_id)
        if status:
            query = query.filter(AgentTeam.status == status)
        elif not include_archived:
            query = query.filter(AgentTeam.status != TeamStatus.ARCHIVED.value)
        total = query.count()
        teams = query.order_by(AgentTeam.updated_at.desc(), AgentTeam.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {
            "items": [self.serialize_team(team, detail=False) for team in teams],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def create_team(self, payload: Any) -> dict[str, Any]:
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        members = list(data.pop("members", []) or [])
        tools = data.pop("tools", None)
        topology = data.get("topology") or TeamTopology.LINE.value
        status = data.get("status") or TeamStatus.DRAFT.value
        self._reject_direct_archive_status(status)
        self._validate_active_ready(status=status, goal_text=data.get("goal_text"), member_count=len(members))
        tool_ids = self._validate_tool_ids(_extract_tool_ids(tools))
        self._ensure_unique_name(data["name"])
        self._validate_member_payloads(members)

        service = _membership_service(self.db, self.tenant_id)
        try:
            team = AgentTeam(
                tenant_id=self.tenant_id,
                name=data["name"],
                description=data.get("description"),
                goal_text=data.get("goal_text"),
                topology=topology,
                status=status,
                max_steps=data.get("max_steps") or 10,
                max_total_tokens=data.get("max_total_tokens"),
                max_concurrent_runs=data.get("max_concurrent_runs") or 1,
                tools_json=_team_tools_payload(tool_ids),
                created_by_user_id=self.user_id,
            )
            self.db.add(team)
            self.db.flush()

            for member in members:
                service.add_agent_to_team(team_id=team.id, agent_id=member["agent_id"])
                membership = self._get_member(team.id, member["agent_id"])
                self._apply_member_options(membership, member)

            self.db.flush()
            self._validate_active_ready(status=team.status, goal_text=team.goal_text, member_count=len(members))
            _commit_membership_service(service, self.db)
            self.db.refresh(team)
            return self.serialize_team(team, detail=True)
        except AgentTeamApiError:
            _rollback_membership_service(service, self.db)
            raise
        except TeamMembershipError as exc:
            _rollback_membership_service(service, self.db)
            raise self._membership_http_error(str(exc)) from exc
        except IntegrityError as exc:
            _rollback_membership_service(service, self.db)
            raise AgentTeamApiError(409, "Team name or membership conflicts with an existing record") from exc
        except Exception:
            _rollback_membership_service(service, self.db)
            raise

    def get_team(self, team_id: int) -> dict[str, Any]:
        return self.serialize_team(self._get_team_or_404(team_id), detail=True)

    def update_team(self, team_id: int, payload: Any) -> dict[str, Any]:
        team = self._get_team_or_404(team_id)
        data = payload.model_dump(exclude_unset=True) if hasattr(payload, "model_dump") else dict(payload)
        if not data:
            return self.serialize_team(team, detail=True)
        if "name" in data and data["name"] != team.name:
            self._ensure_unique_name(data["name"], exclude_team_id=team.id)
            team.name = data["name"]
        for field in ("description", "goal_text", "topology", "status", "max_steps", "max_total_tokens", "max_concurrent_runs"):
            if field in data:
                if field == "status":
                    self._reject_direct_archive_status(data[field])
                setattr(team, field, data[field])
        if "tools" in data and data["tools"] is not None:
            tool_ids = self._validate_tool_ids(_extract_tool_ids(data["tools"]))
            team.tools_json = _team_tools_payload(tool_ids)
        self._validate_active_ready(
            status=team.status,
            goal_text=team.goal_text,
            member_count=self._member_count(team.id),
        )
        self.db.commit()
        self.db.refresh(team)
        return self.serialize_team(team, detail=True)

    def archive_team(self, team_id: int) -> None:
        team = self._get_team_or_404(team_id)
        active_run = (
            self.db.query(AgentTeamRun.id)
            .filter(
                AgentTeamRun.tenant_id == self.tenant_id,
                AgentTeamRun.team_id == team_id,
                AgentTeamRun.status.in_(ACTIVE_RUN_STATUSES),
            )
            .first()
        )
        if active_run:
            raise AgentTeamApiError(409, "Cannot archive a team with an active run")

        service = _membership_service(self.db, self.tenant_id)
        try:
            for member in list(self._visible_members(team_id)):
                service.remove_agent_from_team(team_id=team_id, agent_id=member.agent_id)
            team.status = TeamStatus.ARCHIVED.value
            team.updated_at = datetime.utcnow()
            self.db.flush()
            _commit_membership_service(service, self.db)
        except TeamMembershipError as exc:
            _rollback_membership_service(service, self.db)
            raise self._membership_http_error(str(exc)) from exc
        except Exception:
            _rollback_membership_service(service, self.db)
            raise

    def add_member(self, team_id: int, payload: Any) -> dict[str, Any]:
        team = self._get_team_or_404(team_id)
        if team.status == TeamStatus.ARCHIVED.value:
            raise AgentTeamApiError(409, "Cannot add members to an archived team")
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        self._validate_member_payloads([data])
        service = _membership_service(self.db, self.tenant_id)
        try:
            service.add_agent_to_team(team_id=team_id, agent_id=data["agent_id"])
            membership = self._get_member(team_id, data["agent_id"])
            self._apply_member_options(membership, data)
            self.db.flush()
            _commit_membership_service(service, self.db)
            return self.serialize_member(membership)
        except TeamMembershipError as exc:
            _rollback_membership_service(service, self.db)
            raise self._membership_http_error(str(exc)) from exc
        except IntegrityError as exc:
            _rollback_membership_service(service, self.db)
            raise AgentTeamApiError(409, "Agent is already a member of a team") from exc
        except Exception:
            _rollback_membership_service(service, self.db)
            raise

    def remove_member(self, team_id: int, agent_id: int) -> None:
        self._get_team_or_404(team_id)
        service = _membership_service(self.db, self.tenant_id)
        try:
            service.remove_agent_from_team(team_id=team_id, agent_id=agent_id)
            _commit_membership_service(service, self.db)
        except TeamMembershipError as exc:
            _rollback_membership_service(service, self.db)
            raise self._membership_http_error(str(exc)) from exc
        except Exception:
            _rollback_membership_service(service, self.db)
            raise

    def reorder_members(self, team_id: int, payload: Any) -> dict[str, Any]:
        team = self._get_team_or_404(team_id)
        if team.topology != TeamTopology.LINE.value:
            raise AgentTeamApiError(409, "Member ordering is only editable for line topology teams")
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        requested = {item["agent_id"]: item["execution_order"] for item in data["members"]}
        members = self._visible_members(team_id)
        current_agent_ids = {member.agent_id for member in members}
        if set(requested) != current_agent_ids:
            raise AgentTeamApiError(422, "Order payload must include exactly the team's visible members")
        for member in members:
            member.execution_order = requested[member.agent_id]
        self.db.commit()
        self.db.refresh(team)
        return self.serialize_team(team, detail=True)

    def precreate_manual_run(self, team_id: int) -> AgentTeamRun:
        team = self._get_team_or_404(team_id)
        if team.status != TeamStatus.ACTIVE.value:
            raise AgentTeamApiError(409, "Team must be active before it can run")
        self._validate_active_ready(
            status=team.status,
            goal_text=team.goal_text,
            member_count=self._member_count(team.id),
        )
        active_run = (
            self.db.query(AgentTeamRun.id)
            .filter(
                AgentTeamRun.tenant_id == self.tenant_id,
                AgentTeamRun.team_id == team_id,
                AgentTeamRun.status.in_(ACTIVE_RUN_STATUSES),
            )
            .first()
        )
        if active_run and (team.max_concurrent_runs or 1) <= 1:
            raise AgentTeamApiError(409, "Team already has an active run")
        run = AgentTeamRun(
            tenant_id=self.tenant_id,
            team_id=team.id,
            status=TeamRunStatus.PENDING.value,
            goal_text_snapshot=team.goal_text,
            topology_snapshot=team.topology,
            total_steps=0,
            completed_steps=0,
            failed_steps=0,
        )
        self.db.add(run)
        self.db.commit()
        self.db.refresh(run)
        return run

    def list_runs(self, team_id: int, *, page: int, page_size: int) -> dict[str, Any]:
        self._get_team_or_404(team_id)
        query = self.db.query(AgentTeamRun).filter(
            AgentTeamRun.tenant_id == self.tenant_id,
            AgentTeamRun.team_id == team_id,
        )
        total = query.count()
        runs = query.order_by(AgentTeamRun.created_at.desc(), AgentTeamRun.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
        return {
            "items": [self.serialize_run(run, detail=False) for run in runs],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    def get_run(self, team_id: int, run_id: int) -> dict[str, Any]:
        self._get_team_or_404(team_id)
        return self.serialize_run(self._get_run_or_404(team_id, run_id), detail=True)

    def cancel_run(self, team_id: int, run_id: int) -> dict[str, Any]:
        run = self._get_run_or_404(team_id, run_id)
        if run.status not in ACTIVE_RUN_STATUSES:
            raise AgentTeamApiError(409, "Only pending or running team runs can be cancelled")
        run.status = CANCELLED_STATUS
        run.completed_at = datetime.utcnow()
        run.error_json = {"reason": "cancelled_by_user"}
        self.db.commit()
        self.db.refresh(run)
        return self.serialize_run(run, detail=True)

    def serialize_team(self, team: AgentTeam, *, detail: bool) -> dict[str, Any]:
        member_count = self._member_count(team.id)
        last_run = self._last_run(team.id)
        data = {
            "id": team.id,
            "name": team.name,
            "description": team.description,
            "goal_text": team.goal_text,
            "topology": team.topology,
            "status": team.status,
            "coordinator_agent_id": team.coordinator_agent_id,
            "member_count": member_count,
            "last_run_status": last_run.status if last_run else None,
            "max_steps": team.max_steps,
            "max_total_tokens": team.max_total_tokens,
            "max_concurrent_runs": team.max_concurrent_runs,
            "tools": _team_tools_payload(_extract_tool_ids(team.tools_json)),
            "created_at": team.created_at,
            "updated_at": team.updated_at,
        }
        if detail:
            data["members"] = [self.serialize_member(member) for member in self._visible_members(team.id)]
            data["triggers"] = [
                {
                    "id": trigger.id,
                    "trigger_kind": trigger.trigger_kind,
                    "config_json": trigger.config_json,
                    "is_enabled": trigger.is_enabled,
                    "created_at": trigger.created_at,
                    "updated_at": trigger.updated_at,
                }
                for trigger in sorted(team.triggers, key=lambda item: item.id)
            ]
            data["last_run"] = self.serialize_run(last_run, detail=False) if last_run else None
        return data

    def serialize_member(self, member: AgentTeamMember) -> dict[str, Any]:
        name_map = _agent_name_map(self.db, [member.agent_id])
        return {
            "id": member.id,
            "team_id": member.team_id,
            "agent_id": member.agent_id,
            "agent_name": name_map.get(member.agent_id),
            "role": member.role,
            "execution_order": member.execution_order,
            "is_required": member.is_required,
            "position_x": member.position_x,
            "position_y": member.position_y,
            "created_at": member.created_at,
            "updated_at": member.updated_at,
        }

    def serialize_run(self, run: Optional[AgentTeamRun], *, detail: bool) -> Optional[dict[str, Any]]:
        if run is None:
            return None
        data = {
            "id": run.id,
            "team_id": run.team_id,
            "status": run.status,
            "trigger_event_id": run.trigger_event_id,
            "goal_text_snapshot": run.goal_text_snapshot,
            "topology_snapshot": run.topology_snapshot,
            "total_steps": run.total_steps,
            "completed_steps": run.completed_steps,
            "failed_steps": run.failed_steps,
            "final_output_summary": run.final_output_summary,
            "error_json": run.error_json,
            "total_input_tokens": run.total_input_tokens,
            "total_output_tokens": run.total_output_tokens,
            "total_cost_cents": run.total_cost_cents,
            "started_at": run.started_at,
            "completed_at": run.completed_at,
            "created_at": run.created_at,
            "updated_at": run.updated_at,
        }
        if detail:
            member_runs = (
                self.db.query(AgentTeamMemberRun)
                .filter(
                    AgentTeamMemberRun.tenant_id == self.tenant_id,
                    AgentTeamMemberRun.team_run_id == run.id,
                )
                .order_by(AgentTeamMemberRun.step_index, AgentTeamMemberRun.id)
                .all()
            )
            name_map = _agent_name_map(self.db, [row.agent_id for row in member_runs if row.agent_id])
            data["member_runs"] = [
                {
                    "id": row.id,
                    "agent_team_member_id": row.agent_team_member_id,
                    "agent_id": row.agent_id,
                    "agent_name": name_map.get(row.agent_id) if row.agent_id else None,
                    "step_index": row.step_index,
                    "status": row.status,
                    "output_summary": row.output_summary,
                    "output_text": row.output_text,
                    "sentinel_decision_json": row.sentinel_decision_json,
                    "error_json": row.error_json,
                    "input_tokens": row.input_tokens,
                    "output_tokens": row.output_tokens,
                    "duration_ms": row.duration_ms,
                    "started_at": row.started_at,
                    "completed_at": row.completed_at,
                    "created_at": row.created_at,
                }
                for row in member_runs
            ]
        return data

    def _get_team_or_404(self, team_id: int) -> AgentTeam:
        team = (
            self.db.query(AgentTeam)
            .filter(AgentTeam.id == team_id, AgentTeam.tenant_id == self.tenant_id)
            .first()
        )
        if not team:
            raise AgentTeamApiError(404, "Team not found")
        return team

    def _get_run_or_404(self, team_id: int, run_id: int) -> AgentTeamRun:
        run = (
            self.db.query(AgentTeamRun)
            .filter(
                AgentTeamRun.id == run_id,
                AgentTeamRun.team_id == team_id,
                AgentTeamRun.tenant_id == self.tenant_id,
            )
            .first()
        )
        if not run:
            raise AgentTeamApiError(404, "Team run not found")
        return run

    def _get_member(self, team_id: int, agent_id: int) -> AgentTeamMember:
        member = (
            self.db.query(AgentTeamMember)
            .filter(
                AgentTeamMember.tenant_id == self.tenant_id,
                AgentTeamMember.team_id == team_id,
                AgentTeamMember.agent_id == agent_id,
            )
            .first()
        )
        if not member:
            raise AgentTeamApiError(404, "Team member not found")
        return member

    def _visible_members(self, team_id: int) -> list[AgentTeamMember]:
        return (
            self.db.query(AgentTeamMember)
            .join(Agent, Agent.id == AgentTeamMember.agent_id)
            .filter(
                AgentTeamMember.tenant_id == self.tenant_id,
                AgentTeamMember.team_id == team_id,
                AgentTeamMember.role != TeamMemberRole.COORDINATOR.value,
                Agent.tenant_id == self.tenant_id,
                Agent.is_internal.is_(False),
            )
            .order_by(AgentTeamMember.execution_order, AgentTeamMember.id)
            .all()
        )

    def _member_count(self, team_id: int) -> int:
        return len(self._visible_members(team_id))

    def _last_run(self, team_id: int) -> Optional[AgentTeamRun]:
        return (
            self.db.query(AgentTeamRun)
            .filter(AgentTeamRun.tenant_id == self.tenant_id, AgentTeamRun.team_id == team_id)
            .order_by(AgentTeamRun.created_at.desc(), AgentTeamRun.id.desc())
            .first()
        )

    def _validate_member_payloads(self, members: list[dict[str, Any]]) -> None:
        if len({member["agent_id"] for member in members}) != len(members):
            raise AgentTeamApiError(422, "Duplicate member agent IDs are not allowed")
        if not members:
            return
        agent_ids = [member["agent_id"] for member in members]
        found = {
            agent_id
            for (agent_id,) in self.db.query(Agent.id)
            .filter(
                Agent.id.in_(agent_ids),
                Agent.tenant_id == self.tenant_id,
                Agent.is_active.is_(True),
                Agent.is_internal.is_(False),
            )
            .all()
        }
        missing = sorted(set(agent_ids) - found)
        if missing:
            raise AgentTeamApiError(404, f"Agent not found or not eligible for team membership: {missing[0]}")

    def _validate_tool_ids(self, tool_ids: list[int]) -> list[int]:
        unique_ids = list(dict.fromkeys(tool_ids))
        if not unique_ids:
            return []
        found = {
            tool_id
            for (tool_id,) in self.db.query(SandboxedTool.id)
            .filter(
                SandboxedTool.id.in_(unique_ids),
                SandboxedTool.is_enabled.is_(True),
                or_(SandboxedTool.tenant_id == self.tenant_id, SandboxedTool.tenant_id.is_(None)),
            )
            .all()
        }
        missing = sorted(set(unique_ids) - found)
        if missing:
            raise AgentTeamApiError(404, f"Sandboxed tool not found or disabled: {missing[0]}")
        return unique_ids

    def _validate_active_ready(self, *, status: str, goal_text: Optional[str], member_count: int) -> None:
        if status == TeamStatus.ACTIVE.value:
            if not (goal_text or "").strip():
                raise AgentTeamApiError(422, "Active teams require goal_text")
            if member_count <= 0:
                raise AgentTeamApiError(422, "Active teams require at least one visible member")

    @staticmethod
    def _reject_direct_archive_status(status: Optional[str]) -> None:
        if status == TeamStatus.ARCHIVED.value:
            raise AgentTeamApiError(422, "Use the archive endpoint to archive Agent Teams")

    def _ensure_unique_name(self, name: str, *, exclude_team_id: Optional[int] = None) -> None:
        query = self.db.query(AgentTeam.id).filter(
            AgentTeam.tenant_id == self.tenant_id,
            func.lower(AgentTeam.name) == name.lower(),
        )
        if exclude_team_id is not None:
            query = query.filter(AgentTeam.id != exclude_team_id)
        if query.first():
            raise AgentTeamApiError(409, "A team with this name already exists")

    @staticmethod
    def _apply_member_options(member: AgentTeamMember, data: dict[str, Any]) -> None:
        if data.get("execution_order") is not None:
            member.execution_order = data["execution_order"]
        if "is_required" in data:
            member.is_required = bool(data["is_required"])
        if "position_x" in data:
            member.position_x = data["position_x"]
        if "position_y" in data:
            member.position_y = data["position_y"]

    @staticmethod
    def _membership_http_error(error_code: str) -> AgentTeamApiError:
        if error_code == "agent_already_member_of_another_team":
            return AgentTeamApiError(409, "Agent is already a member of another team")
        if error_code in {"team_not_found_for_tenant", "agent_not_found_for_tenant", "agent_not_member_of_team"}:
            return AgentTeamApiError(404, error_code)
        if "internal_coordinator" in error_code:
            return AgentTeamApiError(404, "Agent not found")
        return AgentTeamApiError(422, error_code)


def run_team_background(*, tenant_id: str, team_id: int, run_id: int) -> None:
    """Execute a pre-created manual run outside the request session."""
    SessionLocal = get_session_factory()
    db = SessionLocal()
    try:
        try:
            orchestrator = TeamRunOrchestrator(db, tenant_id=tenant_id, team_id=team_id, existing_run_id=run_id)
        except TypeError:
            orchestrator = TeamRunOrchestrator(db, tenant_id=tenant_id, team_id=team_id)
            setattr(orchestrator, "existing_run_id", run_id)
        asyncio.run(orchestrator.run())
    except Exception as exc:
        logger.exception("Agent Teams manual run failed: tenant=%s team=%s run=%s", tenant_id, team_id, run_id)
        run = (
            db.query(AgentTeamRun)
            .filter(
                AgentTeamRun.id == run_id,
                AgentTeamRun.team_id == team_id,
                AgentTeamRun.tenant_id == tenant_id,
            )
            .first()
        )
        if run and run.status in ACTIVE_RUN_STATUSES:
            run.status = TeamRunStatus.FAILED.value
            run.error_json = {"reason": "background_run_exception", "message": str(exc)[:500]}
            run.completed_at = datetime.utcnow()
            db.commit()
    finally:
        db.close()
