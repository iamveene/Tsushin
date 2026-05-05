"""Watcher read APIs for Agent Team runs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from api.schemas.teams import WatcherTeamRunDetail, WatcherTeamRunListResponse
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from models import (
    Agent,
    AgentTeam,
    AgentTeamMember,
    AgentTeamMemberRun,
    AgentTeamRun,
    Contact,
    TeamMemberRole,
)
from models_rbac import User

router = APIRouter(prefix="/api/watcher", tags=["watcher-team-runs"])


def _apply_tenant_scope(query, ctx: TenantContext, requested_tenant_id: Optional[str]):
    if ctx.is_global_admin:
        if requested_tenant_id:
            return query.filter(AgentTeamRun.tenant_id == requested_tenant_id)
        return query
    return query.filter(AgentTeamRun.tenant_id == ctx.tenant_id)


def _agent_name_map(db: Session, agent_ids: list[int]) -> dict[int, str]:
    if not agent_ids:
        return {}
    rows = (
        db.query(Agent.id, Contact.friendly_name)
        .outerjoin(Contact, Agent.contact_id == Contact.id)
        .filter(Agent.id.in_(list(set(agent_ids))))
        .all()
    )
    return {row.id: row.friendly_name for row in rows if row.friendly_name}


def _visible_member_count(db: Session, team: AgentTeam) -> int:
    return (
        db.query(AgentTeamMember.id)
        .join(Agent, Agent.id == AgentTeamMember.agent_id)
        .filter(
            AgentTeamMember.tenant_id == team.tenant_id,
            AgentTeamMember.team_id == team.id,
            AgentTeamMember.role != TeamMemberRole.COORDINATOR.value,
            Agent.tenant_id == team.tenant_id,
            Agent.is_internal.is_(False),
        )
        .count()
    )


def _member_runs_for(db: Session, run: AgentTeamRun) -> list[AgentTeamMemberRun]:
    return (
        db.query(AgentTeamMemberRun)
        .filter(
            AgentTeamMemberRun.tenant_id == run.tenant_id,
            AgentTeamMemberRun.team_run_id == run.id,
        )
        .order_by(AgentTeamMemberRun.step_index, AgentTeamMemberRun.id)
        .all()
    )


def _coordinator_commands(
    member_runs: list[AgentTeamMemberRun],
    agent_names: dict[int, str],
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = []
    for row in member_runs:
        context = row.input_context_json or {}
        parsed = context.get("parsed_summary") if isinstance(context, dict) else None
        command = parsed.get("coordinator_command") if isinstance(parsed, dict) else None
        if not isinstance(command, dict):
            continue
        commands.append(
            {
                "member_run_id": row.id,
                "step_index": row.step_index,
                "agent_id": row.agent_id,
                "agent_name": agent_names.get(row.agent_id) if row.agent_id else None,
                "command": command,
                "created_at": row.created_at,
            }
        )
    return commands


def _serialize_run(db: Session, run: AgentTeamRun, *, detail: bool) -> dict[str, Any]:
    team = run.team
    if team is None:
        team = (
            db.query(AgentTeam)
            .filter(AgentTeam.tenant_id == run.tenant_id, AgentTeam.id == run.team_id)
            .first()
        )
    if team is None:
        raise HTTPException(status_code=404, detail="Team run not found")

    member_runs = _member_runs_for(db, run) if detail or run.topology_snapshot == "mesh" else []
    agent_names = _agent_name_map(db, [row.agent_id for row in member_runs if row.agent_id])
    data = {
        "id": run.id,
        "tenant_id": run.tenant_id,
        "team_id": run.team_id,
        "team_name": team.name,
        "team_status": team.status,
        "member_count": _visible_member_count(db, team),
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
        "coordinator_commands": _coordinator_commands(member_runs, agent_names),
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }
    if detail:
        data["member_runs"] = [
            {
                "id": row.id,
                "agent_team_member_id": row.agent_team_member_id,
                "agent_id": row.agent_id,
                "agent_name": agent_names.get(row.agent_id) if row.agent_id else None,
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


@router.get("/team-runs", response_model=WatcherTeamRunListResponse)
def list_watcher_team_runs(
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    team_id: Optional[int] = Query(default=None, ge=1),
    status_filter: Optional[str] = Query(default=None, alias="status"),
    created_after: Optional[datetime] = Query(default=None),
    created_before: Optional[datetime] = Query(default=None),
    tenant_id: Optional[str] = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("watcher.read")),
):
    query = ctx.db.query(AgentTeamRun).join(
        AgentTeam,
        (AgentTeamRun.tenant_id == AgentTeam.tenant_id) & (AgentTeamRun.team_id == AgentTeam.id),
    )
    query = _apply_tenant_scope(query, ctx, tenant_id)
    if team_id is not None:
        query = query.filter(AgentTeamRun.team_id == team_id)
    if status_filter:
        query = query.filter(AgentTeamRun.status == status_filter)
    if created_after is not None:
        query = query.filter(AgentTeamRun.created_at >= created_after)
    if created_before is not None:
        query = query.filter(AgentTeamRun.created_at <= created_before)

    total = query.count()
    runs = (
        query.order_by(AgentTeamRun.created_at.desc(), AgentTeamRun.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return {
        "items": [_serialize_run(ctx.db, run, detail=False) for run in runs],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.get("/team-runs/{run_id}", response_model=WatcherTeamRunDetail)
def get_watcher_team_run(
    run_id: int,
    tenant_id: Optional[str] = Query(default=None),
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("watcher.read")),
):
    query = ctx.db.query(AgentTeamRun).filter(AgentTeamRun.id == run_id)
    query = _apply_tenant_scope(query, ctx, tenant_id)
    run = query.first()
    if not run:
        raise HTTPException(status_code=404, detail="Team run not found")
    return _serialize_run(ctx.db, run, detail=True)
