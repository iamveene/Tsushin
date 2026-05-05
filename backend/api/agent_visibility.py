"""Shared guards for hiding internal coordinator agents from public APIs."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from models import Agent, AgentCommunicationPermission


def raise_if_internal_agent(agent: Agent | None, *, detail: str = "Agent not found") -> None:
    """Return 404 for hidden coordinator agents on public API surfaces."""
    if agent is not None and getattr(agent, "is_internal", False):
        raise HTTPException(status_code=404, detail=detail)


def get_public_tenant_agent_or_404(
    db: Session,
    agent_id: int,
    tenant_id: str,
    *,
    detail: str = "Agent not found",
) -> Agent:
    agent = (
        db.query(Agent)
        .filter(
            Agent.id == agent_id,
            Agent.tenant_id == tenant_id,
            Agent.is_internal == False,
        )
        .first()
    )
    if not agent:
        raise HTTPException(status_code=404, detail=detail)
    return agent


def communication_permission_has_internal_agent(
    db: Session,
    permission: AgentCommunicationPermission,
    tenant_id: str,
) -> bool:
    internal_count = (
        db.query(Agent.id)
        .filter(
            Agent.tenant_id == tenant_id,
            Agent.id.in_([permission.source_agent_id, permission.target_agent_id]),
            Agent.is_internal == True,
        )
        .count()
    )
    return internal_count > 0
