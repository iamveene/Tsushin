"""Tenant-scoped default-agent settings."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.catalog import CHANNEL_CATALOG
from db import get_db
from models import (
    Agent,
    Contact,
    DiscordIntegration,
    EmailChannelInstance,
    SlackIntegration,
    TelegramBotInstance,
    UserChannelDefaultAgent,
    WebhookIntegration,
    WhatsAppMCPInstance,
)

router = APIRouter(
    prefix="/api/settings/default-agents",
    tags=["Default Agents"],
    redirect_slashes=False,
)


class AgentOption(BaseModel):
    id: int
    name: str
    is_default: bool


class InstanceDefaultRead(BaseModel):
    kind: str
    channel_type: str
    instance_id: int
    display_name: str
    default_agent_id: Optional[int] = None
    default_agent_name: Optional[str] = None
    status: Optional[str] = None
    health_status: Optional[str] = None


class UserChannelDefaultRead(BaseModel):
    id: int
    channel_type: str
    user_identifier: str
    agent_id: int
    agent_name: Optional[str] = None


class DefaultAgentsSettingsResponse(BaseModel):
    tenant_default_agent_id: Optional[int] = None
    tenant_default_agent_name: Optional[str] = None
    available_agents: list[AgentOption]
    channel_defaults: list[InstanceDefaultRead]
    trigger_defaults: list[InstanceDefaultRead]
    user_defaults: list[UserChannelDefaultRead]


class TenantDefaultUpdate(BaseModel):
    agent_id: Optional[int] = Field(default=None)


class InstanceDefaultUpdate(BaseModel):
    agent_id: Optional[int] = Field(default=None)


class UserChannelDefaultUpsert(BaseModel):
    channel_type: str = Field(..., min_length=1, max_length=32)
    user_identifier: str = Field(..., min_length=1, max_length=256)
    agent_id: int = Field(..., ge=1)

    @field_validator("channel_type")
    @classmethod
    def _normalize_channel_type(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("user_identifier")
    @classmethod
    def _normalize_user_identifier(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("user_identifier must not be empty")
        return normalized


INSTANCE_CONFIG: dict[str, dict[str, object]] = {
    "whatsapp": {
        "kind": "channel",
        "model": WhatsAppMCPInstance,
        "display_name": lambda row: row.display_name or row.phone_number or f"WhatsApp #{row.id}",
    },
    "telegram": {
        "kind": "channel",
        "model": TelegramBotInstance,
        "display_name": lambda row: row.bot_name or row.bot_username or f"Telegram #{row.id}",
    },
    "slack": {
        "kind": "channel",
        "model": SlackIntegration,
        "display_name": lambda row: row.workspace_name or row.workspace_id or f"Slack #{row.id}",
    },
    "discord": {
        "kind": "channel",
        "model": DiscordIntegration,
        "display_name": lambda row: row.bot_user_id or row.application_id or f"Discord #{row.id}",
    },
    "webhook": {
        "kind": "trigger",
        "model": WebhookIntegration,
        "display_name": lambda row: row.integration_name or row.slug or f"Webhook #{row.id}",
    },
    "email": {
        "kind": "trigger",
        "model": EmailChannelInstance,
        "display_name": lambda row: row.integration_name or f"Email Trigger #{row.id}",
    },
}

USER_DEFAULT_CHANNEL_TYPES = {entry.id for entry in CHANNEL_CATALOG if entry.id != "playground"}


def _load_active_agent(db: Session, tenant_id: str, agent_id: int) -> Agent:
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.is_active == True,  # noqa: E712
    ).first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _agent_name_map(db: Session, tenant_id: str) -> dict[int, str]:
    rows = db.query(
        Agent.id,
        Contact.friendly_name,
    ).join(
        Contact,
        Contact.id == Agent.contact_id,
    ).filter(
        Agent.tenant_id == tenant_id,
    ).all()
    return {row.id: row.friendly_name for row in rows}


def _available_agents(db: Session, tenant_id: str) -> list[AgentOption]:
    rows = db.query(
        Agent.id,
        Agent.is_default,
        Contact.friendly_name,
    ).join(
        Contact,
        Contact.id == Agent.contact_id,
    ).filter(
        Agent.tenant_id == tenant_id,
        Agent.is_active == True,  # noqa: E712
    ).order_by(
        Agent.is_default.desc(),
        Contact.friendly_name.asc(),
        Agent.id.asc(),
    ).all()
    return [
        AgentOption(id=row.id, name=row.friendly_name, is_default=bool(row.is_default))
        for row in rows
    ]


def _instance_summary(
    *,
    channel_type: str,
    row,
    agent_names: dict[int, str],
) -> InstanceDefaultRead:
    config = INSTANCE_CONFIG[channel_type]
    display_name_fn = config["display_name"]
    status = getattr(row, "status", None)
    if status is None and hasattr(row, "is_active"):
        status = "active" if getattr(row, "is_active") else "paused"
    return InstanceDefaultRead(
        kind=str(config["kind"]),
        channel_type=channel_type,
        instance_id=row.id,
        display_name=display_name_fn(row) if callable(display_name_fn) else str(row.id),
        default_agent_id=getattr(row, "default_agent_id", None),
        default_agent_name=agent_names.get(getattr(row, "default_agent_id", None)),
        status=status,
        health_status=getattr(row, "health_status", None),
    )


def _instance_defaults(
    db: Session,
    tenant_id: str,
    *,
    kind: str,
    agent_names: dict[int, str],
) -> list[InstanceDefaultRead]:
    items: list[InstanceDefaultRead] = []
    for channel_type, config in INSTANCE_CONFIG.items():
        if config["kind"] != kind:
            continue
        model = config["model"]
        rows = db.query(model).filter(model.tenant_id == tenant_id).order_by(model.id.asc()).all()
        items.extend(
            _instance_summary(channel_type=channel_type, row=row, agent_names=agent_names)
            for row in rows
        )
    return items


def _load_instance_or_404(db: Session, tenant_id: str, channel_type: str):
    config = INSTANCE_CONFIG.get(channel_type)
    if config is None:
        raise HTTPException(status_code=400, detail="Unsupported channel_type")
    model = config["model"]
    def _loader(instance_id: int):
        record = db.query(model).filter(
            model.id == instance_id,
            model.tenant_id == tenant_id,
        ).first()
        if record is None:
            raise HTTPException(status_code=404, detail="Instance not found")
        return record
    return config, _loader


@router.get("", response_model=DefaultAgentsSettingsResponse)
def get_default_agents_settings(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
) -> DefaultAgentsSettingsResponse:
    available_agents = _available_agents(db, ctx.tenant_id)
    agent_names = {agent.id: agent.name for agent in available_agents}

    # Include any inactive legacy/default rows in the lookup map so the UI can
    # still render existing persisted references instead of hiding them.
    agent_names.update(_agent_name_map(db, ctx.tenant_id))

    tenant_default = db.query(
        Agent.id,
        Contact.friendly_name,
    ).join(
        Contact,
        Contact.id == Agent.contact_id,
    ).filter(
        Agent.tenant_id == ctx.tenant_id,
        Agent.is_default == True,  # noqa: E712
    ).order_by(Agent.id.asc()).first()

    user_defaults = db.query(UserChannelDefaultAgent).filter(
        UserChannelDefaultAgent.tenant_id == ctx.tenant_id,
    ).order_by(
        UserChannelDefaultAgent.channel_type.asc(),
        UserChannelDefaultAgent.user_identifier.asc(),
        UserChannelDefaultAgent.id.asc(),
    ).all()

    return DefaultAgentsSettingsResponse(
        tenant_default_agent_id=tenant_default.id if tenant_default else None,
        tenant_default_agent_name=tenant_default.friendly_name if tenant_default else None,
        available_agents=available_agents,
        channel_defaults=_instance_defaults(db, ctx.tenant_id, kind="channel", agent_names=agent_names),
        trigger_defaults=_instance_defaults(db, ctx.tenant_id, kind="trigger", agent_names=agent_names),
        user_defaults=[
            UserChannelDefaultRead(
                id=row.id,
                channel_type=row.channel_type,
                user_identifier=row.user_identifier,
                agent_id=row.agent_id,
                agent_name=agent_names.get(row.agent_id),
            )
            for row in user_defaults
        ],
    )


@router.put("/tenant")
def update_tenant_default_agent(
    payload: TenantDefaultUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    if payload.agent_id is not None:
        _load_active_agent(db, ctx.tenant_id, payload.agent_id)

    db.query(Agent).filter(
        Agent.tenant_id == ctx.tenant_id,
    ).update({"is_default": False})

    if payload.agent_id is not None:
        db.query(Agent).filter(
            Agent.id == payload.agent_id,
            Agent.tenant_id == ctx.tenant_id,
        ).update({"is_default": True})

    db.commit()
    return {
        "tenant_default_agent_id": payload.agent_id,
    }


@router.put("/instances/{channel_type}/{instance_id}", response_model=InstanceDefaultRead)
def update_instance_default_agent(
    channel_type: str,
    instance_id: int,
    payload: InstanceDefaultUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
) -> InstanceDefaultRead:
    channel_type = channel_type.strip().lower()
    _config, loader = _load_instance_or_404(db, ctx.tenant_id, channel_type)
    instance = loader(instance_id)

    if payload.agent_id is not None:
        _load_active_agent(db, ctx.tenant_id, payload.agent_id)

    instance.default_agent_id = payload.agent_id
    db.commit()
    db.refresh(instance)

    agent_names = _agent_name_map(db, ctx.tenant_id)
    return _instance_summary(channel_type=channel_type, row=instance, agent_names=agent_names)


@router.post("/users", response_model=UserChannelDefaultRead, status_code=status.HTTP_201_CREATED)
def upsert_user_channel_default_agent(
    payload: UserChannelDefaultUpsert,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
) -> UserChannelDefaultRead:
    if payload.channel_type not in USER_DEFAULT_CHANNEL_TYPES:
        raise HTTPException(status_code=400, detail="User defaults only support conversational channels")

    _load_active_agent(db, ctx.tenant_id, payload.agent_id)

    existing = db.query(UserChannelDefaultAgent).filter(
        UserChannelDefaultAgent.tenant_id == ctx.tenant_id,
        UserChannelDefaultAgent.channel_type == payload.channel_type,
        UserChannelDefaultAgent.user_identifier == payload.user_identifier,
    ).first()

    if existing is None:
        existing = UserChannelDefaultAgent(
            tenant_id=ctx.tenant_id,
            channel_type=payload.channel_type,
            user_identifier=payload.user_identifier,
            agent_id=payload.agent_id,
        )
        db.add(existing)
    else:
        existing.agent_id = payload.agent_id

    db.commit()
    db.refresh(existing)

    agent_names = _agent_name_map(db, ctx.tenant_id)
    return UserChannelDefaultRead(
        id=existing.id,
        channel_type=existing.channel_type,
        user_identifier=existing.user_identifier,
        agent_id=existing.agent_id,
        agent_name=agent_names.get(existing.agent_id),
    )


@router.delete("/users/{user_default_id}")
def delete_user_channel_default_agent(
    user_default_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    existing = db.query(UserChannelDefaultAgent).filter(
        UserChannelDefaultAgent.id == user_default_id,
        UserChannelDefaultAgent.tenant_id == ctx.tenant_id,
    ).first()
    if existing is None:
        raise HTTPException(status_code=404, detail="User default not found")

    db.delete(existing)
    db.commit()
    return {"deleted": True, "id": user_default_id}
