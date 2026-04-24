"""Email trigger CRUD for persisted trigger rows."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from db import get_db
from models import Agent, Contact, EmailChannelInstance, GmailIntegration
from services.email_triage_service import ensure_email_triage_subscription

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/triggers/email",
    tags=["Email Triggers"],
    redirect_slashes=False,
)


class EmailTriggerCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    gmail_integration_id: int = Field(..., ge=1)
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    search_query: Optional[str] = Field(default=None, max_length=500)
    poll_interval_seconds: int = Field(default=60, ge=30, le=3600)
    is_active: bool = True

    @field_validator("integration_name")
    @classmethod
    def _normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("integration_name must not be empty")
        return normalized

    @field_validator("search_query")
    @classmethod
    def _normalize_query(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class EmailTriggerUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    gmail_integration_id: Optional[int] = Field(default=None, ge=1)
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    search_query: Optional[str] = Field(default=None, max_length=500)
    poll_interval_seconds: Optional[int] = Field(default=None, ge=30, le=3600)
    is_active: Optional[bool] = None

    @field_validator("integration_name")
    @classmethod
    def _normalize_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("integration_name must not be empty")
        return normalized

    @field_validator("search_query")
    @classmethod
    def _normalize_query(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class EmailTriggerRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    provider: str
    gmail_integration_id: Optional[int] = None
    gmail_account_email: Optional[str] = None
    gmail_integration_name: Optional[str] = None
    default_agent_id: Optional[int] = None
    default_agent_name: Optional[str] = None
    search_query: Optional[str] = None
    poll_interval_seconds: int
    is_active: bool
    status: str
    health_status: str
    health_status_reason: Optional[str] = None
    last_health_check: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class EmailTriageSubscriptionRead(BaseModel):
    email_trigger_id: int
    continuous_agent_id: int
    continuous_subscription_id: int
    agent_id: int
    created_agent: bool
    created_subscription: bool
    status: str = "active"


def _load_gmail_integration(db: Session, tenant_id: str, integration_id: int) -> GmailIntegration:
    integration = db.query(GmailIntegration).filter(
        GmailIntegration.id == integration_id,
        GmailIntegration.tenant_id == tenant_id,
        GmailIntegration.type == "gmail",
        GmailIntegration.health_status != "disconnected",
    ).first()
    if integration is None:
        raise HTTPException(status_code=404, detail="Gmail integration not found")
    return integration


def _load_email_trigger(db: Session, tenant_id: str, trigger_id: int) -> EmailChannelInstance:
    instance = db.query(EmailChannelInstance).filter(
        EmailChannelInstance.id == trigger_id,
        EmailChannelInstance.tenant_id == tenant_id,
    ).first()
    if instance is None:
        raise HTTPException(status_code=404, detail="Email trigger not found")
    return instance


def _load_active_agent(db: Session, tenant_id: str, agent_id: int) -> Agent:
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.is_active == True,  # noqa: E712
    ).first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _agent_name(db: Session, tenant_id: str, agent_id: Optional[int]) -> Optional[str]:
    if not agent_id:
        return None
    row = db.query(Contact.friendly_name).join(
        Agent,
        Agent.contact_id == Contact.id,
    ).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
    ).first()
    return row.friendly_name if row else None


def _to_read(db: Session, instance: EmailChannelInstance) -> EmailTriggerRead:
    gmail_integration = None
    if instance.gmail_integration_id:
        gmail_integration = db.query(GmailIntegration).filter(
            GmailIntegration.id == instance.gmail_integration_id,
        ).first()
    gmail_integration_name = None
    if gmail_integration is not None:
        gmail_integration_name = gmail_integration.display_name or gmail_integration.name
    return EmailTriggerRead(
        id=instance.id,
        tenant_id=instance.tenant_id,
        integration_name=instance.integration_name,
        provider=instance.provider,
        gmail_integration_id=instance.gmail_integration_id,
        gmail_account_email=getattr(gmail_integration, "email_address", None),
        gmail_integration_name=gmail_integration_name,
        default_agent_id=instance.default_agent_id,
        default_agent_name=_agent_name(db, instance.tenant_id, instance.default_agent_id),
        search_query=instance.search_query,
        poll_interval_seconds=instance.poll_interval_seconds,
        is_active=bool(instance.is_active),
        status=instance.status or "active",
        health_status=instance.health_status or "unknown",
        health_status_reason=instance.health_status_reason,
        last_health_check=instance.last_health_check,
        last_activity_at=instance.last_activity_at,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )


@router.get("", response_model=list[EmailTriggerRead])
def list_email_triggers(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[EmailTriggerRead]:
    rows = db.query(EmailChannelInstance).filter(
        EmailChannelInstance.tenant_id == ctx.tenant_id,
    ).order_by(
        EmailChannelInstance.created_at.desc(),
        EmailChannelInstance.id.desc(),
    ).all()
    return [_to_read(db, row) for row in rows]


@router.post("", response_model=EmailTriggerRead, status_code=status.HTTP_201_CREATED)
def create_email_trigger(
    payload: EmailTriggerCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> EmailTriggerRead:
    _load_gmail_integration(db, ctx.tenant_id, payload.gmail_integration_id)
    if payload.default_agent_id is not None:
        _load_active_agent(db, ctx.tenant_id, payload.default_agent_id)

    instance = EmailChannelInstance(
        tenant_id=ctx.tenant_id,
        integration_name=payload.integration_name,
        provider="gmail",
        gmail_integration_id=payload.gmail_integration_id,
        default_agent_id=payload.default_agent_id,
        search_query=payload.search_query,
        poll_interval_seconds=payload.poll_interval_seconds,
        is_active=payload.is_active,
        status="active" if payload.is_active else "paused",
        health_status="unknown",
        created_by=current_user.id,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)
    return _to_read(db, instance)


@router.get("/{trigger_id}", response_model=EmailTriggerRead)
def get_email_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> EmailTriggerRead:
    instance = _load_email_trigger(db, ctx.tenant_id, trigger_id)
    return _to_read(db, instance)


@router.patch("/{trigger_id}", response_model=EmailTriggerRead)
def update_email_trigger(
    trigger_id: int,
    payload: EmailTriggerUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> EmailTriggerRead:
    instance = _load_email_trigger(db, ctx.tenant_id, trigger_id)

    data = payload.model_dump(exclude_unset=True)
    if "gmail_integration_id" in data and data["gmail_integration_id"] is not None:
        _load_gmail_integration(db, ctx.tenant_id, data["gmail_integration_id"])
        instance.gmail_integration_id = data["gmail_integration_id"]
    if "default_agent_id" in data:
        if data["default_agent_id"] is not None:
            _load_active_agent(db, ctx.tenant_id, data["default_agent_id"])
        instance.default_agent_id = data["default_agent_id"]
    if "integration_name" in data:
        instance.integration_name = data["integration_name"]
    if "search_query" in data:
        instance.search_query = data["search_query"]
    if "poll_interval_seconds" in data and data["poll_interval_seconds"] is not None:
        instance.poll_interval_seconds = data["poll_interval_seconds"]
    if "is_active" in data and data["is_active"] is not None:
        instance.is_active = data["is_active"]
        instance.status = "active" if data["is_active"] else "paused"

    db.commit()
    db.refresh(instance)
    return _to_read(db, instance)


@router.delete("/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_email_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    instance = _load_email_trigger(db, ctx.tenant_id, trigger_id)
    db.delete(instance)
    db.commit()
    return None


@router.post("/{trigger_id}/triage-subscription", response_model=EmailTriageSubscriptionRead)
def create_email_triage_subscription(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> EmailTriageSubscriptionRead:
    try:
        result = ensure_email_triage_subscription(
            db,
            tenant_id=ctx.tenant_id,
            email_trigger_id=trigger_id,
        )
    except ValueError as exc:
        reason = str(exc)
        if reason == "email_trigger_not_found":
            raise HTTPException(status_code=404, detail="Email trigger not found") from exc
        if reason == "missing_default_agent":
            raise HTTPException(
                status_code=400,
                detail="Email trigger needs a default agent before triage can be enabled",
            ) from exc
        raise HTTPException(status_code=400, detail=reason) from exc

    return EmailTriageSubscriptionRead(
        email_trigger_id=result.email_trigger_id,
        continuous_agent_id=result.continuous_agent_id,
        continuous_subscription_id=result.continuous_subscription_id,
        agent_id=result.agent_id,
        created_agent=result.created_agent,
        created_subscription=result.created_subscription,
    )
