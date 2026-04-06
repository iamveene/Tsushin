"""
WhatsApp agent binding helpers.

Keeps CRUD routes, Studio saves, graph preview, and startup backfills aligned
around the same tenant-scoped binding policy.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Iterable, List, Optional

from sqlalchemy.orm import Session

from models import Agent, WhatsAppMCPInstance


DEFAULT_ENABLED_CHANNELS = ["playground", "whatsapp"]
ACTIVE_WHATSAPP_STATUSES = {"running", "starting"}


@dataclass
class WhatsAppBindingResolution:
    enabled: bool
    status: str
    source: str
    explicit_instance_id: Optional[int]
    resolved_instance_id: Optional[int]
    candidate_instance_ids: List[int]


def parse_enabled_channels(value: Any) -> List[str]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        try:
            parsed = json.loads(value)
            if isinstance(parsed, list):
                return parsed
        except (TypeError, ValueError):
            pass
    return DEFAULT_ENABLED_CHANNELS.copy() if value is None else []


def get_whatsapp_agent_instances(
    db: Session,
    tenant_id: Optional[str],
    *,
    active_only: bool = False,
) -> List[WhatsAppMCPInstance]:
    if not tenant_id:
        return []

    query = db.query(WhatsAppMCPInstance).filter(
        WhatsAppMCPInstance.tenant_id == tenant_id,
        WhatsAppMCPInstance.instance_type == "agent",
    )
    if active_only:
        query = query.filter(WhatsAppMCPInstance.status.in_(ACTIVE_WHATSAPP_STATUSES))

    return query.order_by(WhatsAppMCPInstance.created_at.asc(), WhatsAppMCPInstance.id.asc()).all()


def get_whatsapp_agent_instance(
    db: Session,
    tenant_id: Optional[str],
    instance_id: Optional[int],
) -> Optional[WhatsAppMCPInstance]:
    if not tenant_id or not instance_id:
        return None

    return (
        db.query(WhatsAppMCPInstance)
        .filter(
            WhatsAppMCPInstance.id == instance_id,
            WhatsAppMCPInstance.tenant_id == tenant_id,
            WhatsAppMCPInstance.instance_type == "agent",
        )
        .first()
    )


def resolve_agent_whatsapp_binding(
    db: Session,
    agent: Agent,
    *,
    enabled_channels: Optional[Iterable[str]] = None,
    active_only: bool = False,
) -> WhatsAppBindingResolution:
    normalized_channels = list(enabled_channels) if enabled_channels is not None else parse_enabled_channels(agent.enabled_channels)
    if "whatsapp" not in normalized_channels:
        return WhatsAppBindingResolution(
            enabled=False,
            status="disabled",
            source="disabled",
            explicit_instance_id=agent.whatsapp_integration_id,
            resolved_instance_id=None,
            candidate_instance_ids=[],
        )

    explicit = get_whatsapp_agent_instance(db, agent.tenant_id, agent.whatsapp_integration_id)
    if explicit and (not active_only or explicit.status in ACTIVE_WHATSAPP_STATUSES):
        return WhatsAppBindingResolution(
            enabled=True,
            status="explicit",
            source="explicit",
            explicit_instance_id=explicit.id,
            resolved_instance_id=explicit.id,
            candidate_instance_ids=[explicit.id],
        )

    candidates = get_whatsapp_agent_instances(db, agent.tenant_id, active_only=active_only)
    candidate_ids = [candidate.id for candidate in candidates]

    if len(candidates) == 1:
        return WhatsAppBindingResolution(
            enabled=True,
            status="resolved",
            source="resolved_default",
            explicit_instance_id=agent.whatsapp_integration_id,
            resolved_instance_id=candidates[0].id,
            candidate_instance_ids=candidate_ids,
        )
    if len(candidates) > 1:
        return WhatsAppBindingResolution(
            enabled=True,
            status="ambiguous",
            source="none",
            explicit_instance_id=agent.whatsapp_integration_id,
            resolved_instance_id=None,
            candidate_instance_ids=candidate_ids,
        )

    return WhatsAppBindingResolution(
        enabled=True,
        status="unassigned",
        source="none",
        explicit_instance_id=agent.whatsapp_integration_id,
        resolved_instance_id=None,
        candidate_instance_ids=[],
    )


def validate_requested_whatsapp_instance(
    db: Session,
    tenant_id: Optional[str],
    instance_id: Optional[int],
) -> Optional[WhatsAppMCPInstance]:
    if instance_id is None:
        return None

    instance = get_whatsapp_agent_instance(db, tenant_id, instance_id)
    if not instance:
        raise ValueError("WhatsApp integration not found")
    return instance


def apply_agent_whatsapp_binding_policy(
    db: Session,
    agent: Agent,
    *,
    requested_instance_id: Optional[int] = None,
    explicit_request: bool = False,
) -> Optional[int]:
    enabled_channels = parse_enabled_channels(agent.enabled_channels)
    if "whatsapp" not in enabled_channels:
        agent.whatsapp_integration_id = None
        return None

    if explicit_request:
        if requested_instance_id is None:
            agent.whatsapp_integration_id = None
        else:
            instance = validate_requested_whatsapp_instance(db, agent.tenant_id, requested_instance_id)
            agent.whatsapp_integration_id = instance.id if instance else None

    explicit = get_whatsapp_agent_instance(db, agent.tenant_id, agent.whatsapp_integration_id)
    if explicit:
        agent.whatsapp_integration_id = explicit.id
        return explicit.id

    agent.whatsapp_integration_id = None
    active_candidates = get_whatsapp_agent_instances(db, agent.tenant_id, active_only=True)
    if len(active_candidates) == 1:
        agent.whatsapp_integration_id = active_candidates[0].id

    return agent.whatsapp_integration_id


def apply_whatsapp_binding_policy(
    db: Session,
    agent: Agent,
    *,
    enabled_channels: Optional[Iterable[str]] = None,
    requested_instance_id: Any = ...,
) -> WhatsAppBindingResolution:
    normalized_channels = list(enabled_channels) if enabled_channels is not None else parse_enabled_channels(agent.enabled_channels)
    agent.enabled_channels = normalized_channels

    explicit_request = requested_instance_id is not ...
    requested_value = requested_instance_id if explicit_request else agent.whatsapp_integration_id

    apply_agent_whatsapp_binding_policy(
        db,
        agent,
        requested_instance_id=requested_value,
        explicit_request=explicit_request,
    )

    return resolve_agent_whatsapp_binding(db, agent, enabled_channels=normalized_channels, active_only=False)


def backfill_unambiguous_whatsapp_bindings(
    db: Session,
    tenant_id: Optional[str] = None,
) -> int:
    query = db.query(Agent)
    if tenant_id:
        query = query.filter(Agent.tenant_id == tenant_id)

    updated = 0
    for agent in query.all():
        original = agent.whatsapp_integration_id
        resolved = apply_agent_whatsapp_binding_policy(db, agent)
        if original != resolved:
            updated += 1

    return updated


def backfill_tenant_whatsapp_bindings(db: Session, tenant_id: str) -> int:
    return backfill_unambiguous_whatsapp_bindings(db, tenant_id)
