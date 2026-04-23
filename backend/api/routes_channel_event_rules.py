"""Channel routing-rule API for v0.7.0 Track A2."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from db import get_db
from models import (
    Agent,
    ChannelEventRule,
    DiscordIntegration,
    SlackIntegration,
    TelegramBotInstance,
    WhatsAppMCPInstance,
)


router = APIRouter(prefix="/api/channels", tags=["Channel Routing Rules"])


CHANNEL_INSTANCE_MODELS = {
    "whatsapp": WhatsAppMCPInstance,
    "telegram": TelegramBotInstance,
    "slack": SlackIntegration,
    "discord": DiscordIntegration,
}


class ChannelEventRuleCreate(BaseModel):
    event_type: Optional[str] = Field(default=None, max_length=64)
    criteria: dict[str, Any] = Field(default_factory=dict)
    priority: int = Field(default=100, ge=0, le=100000)
    agent_id: int = Field(..., ge=1)
    is_active: bool = True

    @field_validator("criteria")
    @classmethod
    def _validate_criteria(cls, value: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(value, dict):
            raise ValueError("criteria must be an object")
        return value


class ChannelEventRuleUpdate(BaseModel):
    event_type: Optional[str] = Field(default=None, max_length=64)
    criteria: Optional[dict[str, Any]] = None
    priority: Optional[int] = Field(default=None, ge=0, le=100000)
    agent_id: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None

    @field_validator("criteria")
    @classmethod
    def _validate_criteria(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is not None and not isinstance(value, dict):
            raise ValueError("criteria must be an object")
        return value


class ChannelEventRuleRead(BaseModel):
    id: int
    tenant_id: str
    channel_type: str
    channel_instance_id: int
    event_type: Optional[str] = None
    criteria: dict[str, Any]
    priority: int
    agent_id: int
    is_active: bool
    created_by: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class ChannelEventRulePage(BaseModel):
    items: list[ChannelEventRuleRead]
    total: int
    limit: int
    offset: int


def _normalize_channel_type(channel_type: str) -> str:
    normalized = channel_type.strip().lower()
    if normalized not in CHANNEL_INSTANCE_MODELS:
        raise HTTPException(status_code=404, detail="Channel type not found")
    return normalized


def _assert_instance_owned(db: Session, tenant_id: str, channel_type: str, instance_id: int) -> None:
    model = CHANNEL_INSTANCE_MODELS[channel_type]
    exists = db.query(model.id).filter(model.id == instance_id).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="Channel instance not found")
    owned = db.query(model.id).filter(
        model.id == instance_id,
        model.tenant_id == tenant_id,
    ).first()
    if owned is None:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")


def _assert_agent_owned(db: Session, tenant_id: str, agent_id: int) -> None:
    exists = db.query(Agent.id).filter(Agent.id == agent_id).first()
    if exists is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    owned = db.query(Agent.id).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.is_active == True,  # noqa: E712
    ).first()
    if owned is None:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")


def _load_rule_or_forbidden(
    db: Session,
    tenant_id: str,
    channel_type: str,
    instance_id: int,
    rule_id: int,
) -> ChannelEventRule:
    row = db.query(ChannelEventRule).filter(ChannelEventRule.id == rule_id).first()
    if row is None:
        raise HTTPException(status_code=404, detail="Routing rule not found")
    if row.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="Cross-tenant access denied")
    if row.channel_type != channel_type or row.channel_instance_id != instance_id:
        raise HTTPException(status_code=404, detail="Routing rule not found")
    return row


def _to_read(row: ChannelEventRule) -> ChannelEventRuleRead:
    return ChannelEventRuleRead(
        id=row.id,
        tenant_id=row.tenant_id,
        channel_type=row.channel_type,
        channel_instance_id=row.channel_instance_id,
        event_type=row.event_type,
        criteria=row.criteria or {},
        priority=row.priority,
        agent_id=row.agent_id,
        is_active=bool(row.is_active),
        created_by=row.created_by,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/{channel_type}/{instance_id}/routing-rules", response_model=ChannelEventRulePage)
def list_channel_event_rules(
    channel_type: str,
    instance_id: int,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> ChannelEventRulePage:
    channel_type = _normalize_channel_type(channel_type)
    _assert_instance_owned(db, ctx.tenant_id, channel_type, instance_id)
    query = db.query(ChannelEventRule).filter(
        ChannelEventRule.tenant_id == ctx.tenant_id,
        ChannelEventRule.channel_type == channel_type,
        ChannelEventRule.channel_instance_id == instance_id,
    ).order_by(ChannelEventRule.priority.asc(), ChannelEventRule.id.asc())
    total = query.count()
    rows = query.offset(offset).limit(limit).all()
    return ChannelEventRulePage(
        items=[_to_read(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/{channel_type}/{instance_id}/routing-rules",
    response_model=ChannelEventRuleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_channel_event_rule(
    channel_type: str,
    instance_id: int,
    payload: ChannelEventRuleCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> ChannelEventRuleRead:
    channel_type = _normalize_channel_type(channel_type)
    _assert_instance_owned(db, ctx.tenant_id, channel_type, instance_id)
    _assert_agent_owned(db, ctx.tenant_id, payload.agent_id)

    row = ChannelEventRule(
        tenant_id=ctx.tenant_id,
        channel_type=channel_type,
        channel_instance_id=instance_id,
        event_type=payload.event_type,
        criteria=payload.criteria,
        priority=payload.priority,
        agent_id=payload.agent_id,
        is_active=payload.is_active,
        created_by=getattr(current_user, "id", None),
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Routing rule priority already exists") from exc
    db.refresh(row)
    return _to_read(row)


@router.get("/{channel_type}/{instance_id}/routing-rules/{rule_id}", response_model=ChannelEventRuleRead)
def get_channel_event_rule(
    channel_type: str,
    instance_id: int,
    rule_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> ChannelEventRuleRead:
    channel_type = _normalize_channel_type(channel_type)
    _assert_instance_owned(db, ctx.tenant_id, channel_type, instance_id)
    return _to_read(_load_rule_or_forbidden(db, ctx.tenant_id, channel_type, instance_id, rule_id))


@router.patch("/{channel_type}/{instance_id}/routing-rules/{rule_id}", response_model=ChannelEventRuleRead)
def update_channel_event_rule(
    channel_type: str,
    instance_id: int,
    rule_id: int,
    payload: ChannelEventRuleUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> ChannelEventRuleRead:
    channel_type = _normalize_channel_type(channel_type)
    _assert_instance_owned(db, ctx.tenant_id, channel_type, instance_id)
    row = _load_rule_or_forbidden(db, ctx.tenant_id, channel_type, instance_id, rule_id)

    data = payload.model_dump(exclude_unset=True)
    if "agent_id" in data and data["agent_id"] is not None:
        _assert_agent_owned(db, ctx.tenant_id, data["agent_id"])
        row.agent_id = data["agent_id"]
    if "event_type" in data:
        row.event_type = data["event_type"]
    if "criteria" in data and data["criteria"] is not None:
        row.criteria = data["criteria"]
    if "priority" in data and data["priority"] is not None:
        row.priority = data["priority"]
    if "is_active" in data and data["is_active"] is not None:
        row.is_active = data["is_active"]

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Routing rule priority already exists") from exc
    db.refresh(row)
    return _to_read(row)


@router.delete("/{channel_type}/{instance_id}/routing-rules/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_channel_event_rule(
    channel_type: str,
    instance_id: int,
    rule_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    channel_type = _normalize_channel_type(channel_type)
    _assert_instance_owned(db, ctx.tenant_id, channel_type, instance_id)
    row = _load_rule_or_forbidden(db, ctx.tenant_id, channel_type, instance_id, rule_id)
    db.delete(row)
    db.commit()
    return None
