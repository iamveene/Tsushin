"""Reverse-lookup endpoint for Agent Team triggers.

The primary CRUD for ``agent_team_trigger`` rows lives on the team-side
routes at ``POST/PUT/DELETE /api/teams/{team_id}/triggers[/{id}]`` — those
write paths already enforce tenant scoping, permissions, and config
validation.

This module adds a single READ-ONLY route the trigger detail page
(``/hub/triggers/{kind}/{id}``) uses to enumerate every team subscribed
to a given trigger instance, mirroring the reverse-lookup that
``flow_trigger_binding`` already exposes via ``GET /api/flow-trigger-bindings``.

Mutations stay on the team-side routes; the response carries ``team_id``
so the frontend can address those endpoints.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload

from api.schemas.teams import TeamTriggerWithTeamRead
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from db import get_db
from models import AgentTeam, AgentTeamMember, AgentTeamTrigger
from models_rbac import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/team-triggers", tags=["agent-team-triggers"])


_SUPPORTED_KINDS = {"jira", "github", "webhook", "gmail"}


def _serialize(
    trigger: AgentTeamTrigger,
    team: AgentTeam,
    member_count: int,
) -> TeamTriggerWithTeamRead:
    config: dict[str, Any] = trigger.config_json if isinstance(trigger.config_json, dict) else {}
    return TeamTriggerWithTeamRead(
        id=trigger.id,
        trigger_kind=trigger.trigger_kind,
        trigger_instance_id=int(config.get("trigger_instance_id") or 0),
        event_types=list(config.get("event_types") or []),
        filters=dict(config.get("filters") or {}),
        config_json=config,
        is_enabled=bool(trigger.is_enabled),
        created_at=trigger.created_at,
        updated_at=trigger.updated_at,
        team_id=team.id,
        team_name=team.name,
        team_status=team.status,
        team_topology=team.topology,
        member_count=member_count,
    )


@router.get("", response_model=list[TeamTriggerWithTeamRead])
async def list_team_triggers_by_instance(
    trigger_kind: str = Query(...),
    trigger_instance_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context),
    _current_user: User = Depends(require_permission("agents.read")),
) -> list[TeamTriggerWithTeamRead]:
    """List every Agent Team trigger wired to one trigger instance.

    Both ``trigger_kind`` and ``trigger_instance_id`` are required and
    fail-closed — the trigger-detail page only ever queries with both.
    Tenant scoping is enforced through :class:`TenantContext`.
    """
    if trigger_kind not in _SUPPORTED_KINDS:
        raise HTTPException(
            status_code=422,
            detail=f"trigger_kind must be one of {sorted(_SUPPORTED_KINDS)}",
        )

    rows: list[AgentTeamTrigger] = (
        db.query(AgentTeamTrigger)
        .options(joinedload(AgentTeamTrigger.team))
        .filter(
            AgentTeamTrigger.tenant_id == ctx.tenant_id,
            AgentTeamTrigger.trigger_kind == trigger_kind,
        )
        .order_by(AgentTeamTrigger.id.asc())
        .all()
    )

    matched: list[AgentTeamTrigger] = []
    for row in rows:
        config = row.config_json if isinstance(row.config_json, dict) else {}
        configured_id = config.get("trigger_instance_id")
        try:
            if configured_id is None or int(configured_id) != int(trigger_instance_id):
                continue
        except (TypeError, ValueError):
            continue
        if row.team is None or row.team.tenant_id != ctx.tenant_id:
            continue
        matched.append(row)

    if not matched:
        return []

    team_ids = {row.team_id for row in matched}
    member_counts: dict[int, int] = {team_id: 0 for team_id in team_ids}
    if team_ids:
        member_rows = (
            db.query(AgentTeamMember.team_id)
            .filter(
                AgentTeamMember.tenant_id == ctx.tenant_id,
                AgentTeamMember.team_id.in_(team_ids),
            )
            .all()
        )
        for (team_id,) in member_rows:
            member_counts[team_id] = member_counts.get(team_id, 0) + 1

    return [
        _serialize(row, row.team, member_counts.get(row.team_id, 0))
        for row in matched
    ]
