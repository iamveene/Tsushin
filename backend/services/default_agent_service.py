"""Default-agent resolution for channels and triggers."""

from __future__ import annotations

import os
from typing import Optional

from sqlalchemy.orm import Session

from channels.catalog import CHANNEL_CATALOG, TRIGGER_CATALOG
from models import (
    Agent,
    ContactAgentMapping,
    DiscordIntegration,
    EmailChannelInstance,
    GitHubChannelInstance,
    JiraChannelInstance,
    SlackIntegration,
    TelegramBotInstance,
    UserChannelDefaultAgent,
    WebhookIntegration,
    WhatsAppMCPInstance,
)


CHANNEL_TYPES = {entry.id for entry in CHANNEL_CATALOG}
TRIGGER_TYPES = {entry.id for entry in TRIGGER_CATALOG}


def is_default_agent_v2_enabled() -> bool:
    raw_value = (os.getenv("TSN_DEFAULT_AGENT_V2_ENABLED") or "true").strip().lower()
    return raw_value not in {"0", "false", "no", "off"}


def get_default_agent(
    db: Session,
    tenant_id: str,
    channel_type: str,
    instance_id: Optional[int] = None,
    user_identifier: Optional[str] = None,
    contact_id: Optional[int] = None,
    explicit_agent_id: Optional[int] = None,
) -> Optional[int]:
    """Resolve the best default agent for a channel or trigger."""
    if not tenant_id:
        return None

    if not is_default_agent_v2_enabled():
        return _resolve_tenant_default_agent(db, tenant_id)

    if channel_type in TRIGGER_TYPES:
        return _resolve_trigger(
            db=db,
            tenant_id=tenant_id,
            channel_type=channel_type,
            instance_id=instance_id,
            explicit_agent_id=explicit_agent_id,
        )

    return _resolve_channel(
        db=db,
        tenant_id=tenant_id,
        channel_type=channel_type,
        instance_id=instance_id,
        user_identifier=user_identifier,
        contact_id=contact_id,
        explicit_agent_id=explicit_agent_id,
    )


def _resolve_trigger(
    db: Session,
    tenant_id: str,
    channel_type: str,
    instance_id: Optional[int],
    explicit_agent_id: Optional[int],
) -> Optional[int]:
    candidates = (
        explicit_agent_id,
        _resolve_instance_default_agent(db, tenant_id, channel_type, instance_id),
        _resolve_legacy_bound_agent(db, tenant_id, channel_type, instance_id),
        _resolve_tenant_default_agent(db, tenant_id),
    )
    return _first_active_agent(db, tenant_id, *candidates)


def _resolve_channel(
    db: Session,
    tenant_id: str,
    channel_type: str,
    instance_id: Optional[int],
    user_identifier: Optional[str],
    contact_id: Optional[int],
    explicit_agent_id: Optional[int],
) -> Optional[int]:
    candidates = (
        explicit_agent_id,
        _resolve_contact_mapping(db, tenant_id, contact_id),
        _resolve_user_channel_default_agent(db, tenant_id, channel_type, user_identifier),
        _resolve_instance_default_agent(db, tenant_id, channel_type, instance_id),
        _resolve_legacy_bound_agent(db, tenant_id, channel_type, instance_id),
        _resolve_tenant_default_agent(db, tenant_id),
    )
    return _first_active_agent(db, tenant_id, *candidates)


def _first_active_agent(db: Session, tenant_id: str, *agent_ids: Optional[int]) -> Optional[int]:
    for agent_id in agent_ids:
        if not agent_id:
            continue
        if _is_active_agent(db, tenant_id, agent_id):
            return agent_id
    return None


def _is_active_agent(db: Session, tenant_id: str, agent_id: int) -> bool:
    agent = db.query(Agent.id).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.is_active == True,  # noqa: E712
    ).first()
    return agent is not None


def _resolve_contact_mapping(db: Session, tenant_id: str, contact_id: Optional[int]) -> Optional[int]:
    if not contact_id:
        return None

    mapping = db.query(ContactAgentMapping).filter(
        ContactAgentMapping.contact_id == contact_id,
        ContactAgentMapping.tenant_id == tenant_id,
    ).first()
    return mapping.agent_id if mapping else None


def _resolve_user_channel_default_agent(
    db: Session,
    tenant_id: str,
    channel_type: str,
    user_identifier: Optional[str],
) -> Optional[int]:
    if not user_identifier:
        return None

    record = db.query(UserChannelDefaultAgent).filter(
        UserChannelDefaultAgent.tenant_id == tenant_id,
        UserChannelDefaultAgent.channel_type == channel_type,
        UserChannelDefaultAgent.user_identifier == user_identifier,
    ).first()
    return record.agent_id if record else None


def _resolve_instance_default_agent(
    db: Session,
    tenant_id: str,
    channel_type: str,
    instance_id: Optional[int],
) -> Optional[int]:
    if not instance_id:
        return None

    model = {
        "whatsapp": WhatsAppMCPInstance,
        "telegram": TelegramBotInstance,
        "slack": SlackIntegration,
        "discord": DiscordIntegration,
        "webhook": WebhookIntegration,
        "email": EmailChannelInstance,
        "jira": JiraChannelInstance,
        "github": GitHubChannelInstance,
    }.get(channel_type)
    if model is None or not hasattr(model, "default_agent_id"):
        return None

    query = db.query(model).filter(model.id == instance_id)
    if hasattr(model, "tenant_id"):
        query = query.filter(model.tenant_id == tenant_id)
    record = query.first()
    return getattr(record, "default_agent_id", None) if record else None


def _resolve_legacy_bound_agent(
    db: Session,
    tenant_id: str,
    channel_type: str,
    instance_id: Optional[int],
) -> Optional[int]:
    if not instance_id:
        return None

    field_name = {
        "whatsapp": "whatsapp_integration_id",
        "telegram": "telegram_integration_id",
        "slack": "slack_integration_id",
        "discord": "discord_integration_id",
        "webhook": "webhook_integration_id",
    }.get(channel_type)
    if field_name is None:
        return None

    field = getattr(Agent, field_name)
    agent = db.query(Agent.id).filter(
        Agent.tenant_id == tenant_id,
        Agent.is_active == True,  # noqa: E712
        field == instance_id,
    ).order_by(Agent.id.asc()).first()
    return agent.id if agent else None


def _resolve_tenant_default_agent(db: Session, tenant_id: str) -> Optional[int]:
    agent = db.query(Agent.id).filter(
        Agent.tenant_id == tenant_id,
        Agent.is_default == True,  # noqa: E712
        Agent.is_active == True,  # noqa: E712
    ).order_by(Agent.id.asc()).first()
    return agent.id if agent else None
