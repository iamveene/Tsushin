"""Hidden coordinator support for Agent Team mesh orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session

from models import (
    Agent,
    AgentCustomSkill,
    AgentKnowledge,
    AgentSandboxedTool,
    AgentSkill,
    AgentSkillIntegration,
    AgentTeam,
    AgentTeamMember,
    Contact,
    TeamMemberRole,
)
from services.system_ai_config import get_system_ai_config


PROMPT_PATH = Path(__file__).resolve().parents[1] / "agent" / "prompts" / "team_coordinator.md"


@dataclass(frozen=True)
class CoordinatorCommand:
    command: str
    raw: dict[str, Any]
    dispatches: tuple[dict[str, Any], ...] = ()
    summary: str = ""
    reason: str = ""


class TeamCoordinatorCommandError(ValueError):
    """Raised when coordinator output cannot be used as a mesh command."""


def load_team_coordinator_prompt() -> str:
    return PROMPT_PATH.read_text(encoding="utf-8").strip()


def ensure_hidden_team_coordinator(db: Session, tenant_id: str, team: AgentTeam) -> tuple[AgentTeamMember, Agent]:
    """Create or reuse a hidden coordinator agent/member for one team."""
    coordinator_prompt = load_team_coordinator_prompt()
    coordinator_agent: Optional[Agent] = None
    if team.coordinator_agent_id:
        coordinator_agent = (
            db.query(Agent)
            .filter(Agent.id == team.coordinator_agent_id, Agent.tenant_id == tenant_id)
            .first()
        )

    if coordinator_agent is None:
        model_provider, model_name, provider_instance_id = get_system_ai_config(db)
        contact = Contact(
            friendly_name=f"{team.name} Coordinator",
            role="agent",
            tenant_id=tenant_id,
            is_active=True,
        )
        db.add(contact)
        db.flush()
        coordinator_agent = Agent(
            contact_id=contact.id,
            tenant_id=tenant_id,
            system_prompt=coordinator_prompt,
            model_provider=model_provider,
            model_name=model_name,
            provider_instance_id=provider_instance_id,
            is_active=True,
            is_internal=True,
            is_team_member=True,
            current_team_id=team.id,
        )
        db.add(coordinator_agent)
        db.flush()
        team.coordinator_agent_id = coordinator_agent.id
    else:
        coordinator_agent.is_active = True
        coordinator_agent.is_internal = True
        coordinator_agent.is_team_member = True
        coordinator_agent.current_team_id = team.id
        coordinator_agent.system_prompt = coordinator_prompt

    coordinator_member = (
        db.query(AgentTeamMember)
        .filter(
            AgentTeamMember.team_id == team.id,
            AgentTeamMember.tenant_id == tenant_id,
            AgentTeamMember.agent_id == coordinator_agent.id,
        )
        .first()
    )
    if coordinator_member is None:
        coordinator_member = AgentTeamMember(
            tenant_id=tenant_id,
            team_id=team.id,
            agent_id=coordinator_agent.id,
            role=TeamMemberRole.COORDINATOR.value,
            execution_order=0,
            is_required=True,
        )
        db.add(coordinator_member)
    else:
        coordinator_member.role = TeamMemberRole.COORDINATOR.value
        coordinator_member.execution_order = 0

    _clear_coordinator_attachments(db, coordinator_agent.id)
    db.commit()
    db.refresh(team)
    db.refresh(coordinator_agent)
    db.refresh(coordinator_member)
    return coordinator_member, coordinator_agent


def _clear_coordinator_attachments(db: Session, agent_id: int) -> None:
    """Keep the hidden coordinator free of operator-assigned skills, tools, and KBs."""
    for model in (
        AgentSkill,
        AgentSkillIntegration,
        AgentCustomSkill,
        AgentSandboxedTool,
        AgentKnowledge,
    ):
        db.query(model).filter(model.agent_id == agent_id).delete(synchronize_session=False)


def parse_coordinator_command(parsed: Optional[dict[str, Any]]) -> CoordinatorCommand:
    if not isinstance(parsed, dict):
        raise TeamCoordinatorCommandError("missing_final_json_command")
    command = str(parsed.get("command") or "").strip().lower()

    if command == "dispatch":
        dispatches = parsed.get("dispatches")
        if not isinstance(dispatches, list) or not dispatches:
            raise TeamCoordinatorCommandError("dispatch_requires_dispatches")
        normalized: list[dict[str, Any]] = []
        for item in dispatches:
            if not isinstance(item, dict):
                raise TeamCoordinatorCommandError("dispatch_item_must_be_object")
            member_id = item.get("member_id")
            message = item.get("message")
            try:
                member_id = int(member_id)
            except (TypeError, ValueError) as exc:
                raise TeamCoordinatorCommandError("dispatch_member_id_invalid") from exc
            if not isinstance(message, str) or not message.strip():
                raise TeamCoordinatorCommandError("dispatch_message_required")
            normalized.append({"member_id": member_id, "message": message.strip()})
        return CoordinatorCommand(
            command="dispatch",
            raw=parsed,
            dispatches=tuple(normalized),
            reason=str(parsed.get("reason") or "").strip(),
        )

    if command == "finish":
        summary = str(parsed.get("summary") or "").strip()
        if not summary:
            raise TeamCoordinatorCommandError("finish_summary_required")
        return CoordinatorCommand(command="finish", raw=parsed, summary=summary)

    if command == "escalate":
        reason = str(parsed.get("reason") or "").strip()
        summary = str(parsed.get("summary") or "").strip()
        if not reason:
            raise TeamCoordinatorCommandError("escalate_reason_required")
        return CoordinatorCommand(command="escalate", raw=parsed, reason=reason, summary=summary)

    raise TeamCoordinatorCommandError("unknown_coordinator_command")
