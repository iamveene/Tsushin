"""Schedule trigger CRUD for persisted cron trigger rows."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.schedule.trigger import (
    CronUnavailableError,
    calculate_next_fire_times,
    validate_cron_expression,
)
from channels.trigger_criteria import validate_criteria
from db import get_db
from models import Agent, Contact, ScheduleChannelInstance

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/triggers/schedule",
    tags=["Schedule Triggers"],
    redirect_slashes=False,
)


class ScheduleTriggerCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    cron_expression: str = Field(..., min_length=1, max_length=120)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    payload_template: Optional[dict[str, Any]] = None
    trigger_criteria: Optional[dict[str, Any]] = None
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    is_active: bool = True

    @field_validator("integration_name", "cron_expression", "timezone")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, value):
        if value is None:
            return value
        try:
            return validate_criteria(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class ScheduleTriggerUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    cron_expression: Optional[str] = Field(default=None, min_length=1, max_length=120)
    timezone: Optional[str] = Field(default=None, min_length=1, max_length=64)
    payload_template: Optional[dict[str, Any]] = None
    trigger_criteria: Optional[dict[str, Any]] = None
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None

    @field_validator("integration_name", "cron_expression", "timezone")
    @classmethod
    def _strip_non_empty(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, value):
        if value is None:
            return value
        try:
            return validate_criteria(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class ScheduleTriggerPreviewRequest(BaseModel):
    cron_expression: str = Field(..., min_length=1, max_length=120)
    timezone: str = Field(default="UTC", min_length=1, max_length=64)
    base_time: Optional[datetime] = None

    @field_validator("cron_expression", "timezone")
    @classmethod
    def _strip_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized


class ScheduleTriggerPreviewResponse(BaseModel):
    cron_expression: str
    timezone: str
    next_fire_preview: list[datetime]
    next_fire_times: list[datetime]


class ScheduleTriggerRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    cron_expression: str
    timezone: str
    payload_template: Optional[dict[str, Any]] = None
    trigger_criteria: Optional[dict[str, Any]] = None
    default_agent_id: Optional[int] = None
    default_agent_name: Optional[str] = None
    is_active: bool
    status: str
    health_status: str
    health_status_reason: Optional[str] = None
    last_health_check: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    last_cursor: Optional[str] = None
    next_fire_at: Optional[datetime] = None
    last_fire_at: Optional[datetime] = None
    next_fire_preview: list[datetime] = Field(default_factory=list)
    created_at: datetime
    updated_at: Optional[datetime] = None


def _load_schedule_trigger(db: Session, tenant_id: str, trigger_id: int) -> ScheduleChannelInstance:
    instance = db.query(ScheduleChannelInstance).filter(
        ScheduleChannelInstance.id == trigger_id,
        ScheduleChannelInstance.tenant_id == tenant_id,
    ).first()
    if instance is None:
        raise HTTPException(status_code=404, detail="Schedule trigger not found")
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


def _preview_or_400(
    cron_expression: str,
    timezone_name: str,
    *,
    base_time: Optional[datetime] = None,
) -> list[datetime]:
    try:
        return calculate_next_fire_times(
            cron_expression,
            timezone_name,
            base=base_time,
            count=5,
        )
    except CronUnavailableError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _safe_preview(instance: ScheduleChannelInstance) -> list[datetime]:
    try:
        return calculate_next_fire_times(
            instance.cron_expression,
            instance.timezone,
            base=datetime.now(timezone.utc).replace(tzinfo=None),
            count=5,
        )
    except Exception as exc:
        logger.warning(
            "schedule trigger preview failed for trigger %s: %s",
            instance.id,
            exc,
        )
        return []


def _to_read(db: Session, instance: ScheduleChannelInstance) -> ScheduleTriggerRead:
    return ScheduleTriggerRead(
        id=instance.id,
        tenant_id=instance.tenant_id,
        integration_name=instance.integration_name,
        cron_expression=instance.cron_expression,
        timezone=instance.timezone,
        payload_template=instance.payload_template,
        trigger_criteria=instance.trigger_criteria,
        default_agent_id=instance.default_agent_id,
        default_agent_name=_agent_name(db, instance.tenant_id, instance.default_agent_id),
        is_active=bool(instance.is_active),
        status=instance.status or "active",
        health_status=instance.health_status or "unknown",
        health_status_reason=instance.health_status_reason,
        last_health_check=instance.last_health_check,
        last_activity_at=instance.last_activity_at,
        last_cursor=instance.last_cursor,
        next_fire_at=instance.next_fire_at,
        last_fire_at=instance.last_fire_at,
        next_fire_preview=_safe_preview(instance),
        created_at=instance.created_at,
        updated_at=instance.updated_at,
    )


@router.post("/preview", response_model=ScheduleTriggerPreviewResponse)
def preview_schedule_trigger(
    payload: ScheduleTriggerPreviewRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> ScheduleTriggerPreviewResponse:
    del ctx, db
    preview = _preview_or_400(
        payload.cron_expression,
        payload.timezone,
        base_time=payload.base_time,
    )
    return ScheduleTriggerPreviewResponse(
        cron_expression=validate_cron_expression(payload.cron_expression),
        timezone=payload.timezone,
        next_fire_preview=preview,
        next_fire_times=preview,
    )


@router.get("", response_model=list[ScheduleTriggerRead])
def list_schedule_triggers(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[ScheduleTriggerRead]:
    rows = db.query(ScheduleChannelInstance).filter(
        ScheduleChannelInstance.tenant_id == ctx.tenant_id,
    ).order_by(
        ScheduleChannelInstance.created_at.desc(),
        ScheduleChannelInstance.id.desc(),
    ).all()
    return [_to_read(db, row) for row in rows]


@router.post("", response_model=ScheduleTriggerRead, status_code=status.HTTP_201_CREATED)
def create_schedule_trigger(
    payload: ScheduleTriggerCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> ScheduleTriggerRead:
    preview = _preview_or_400(payload.cron_expression, payload.timezone)
    if payload.default_agent_id is not None:
        _load_active_agent(db, ctx.tenant_id, payload.default_agent_id)

    instance = ScheduleChannelInstance(
        tenant_id=ctx.tenant_id,
        integration_name=payload.integration_name,
        cron_expression=validate_cron_expression(payload.cron_expression),
        timezone=payload.timezone,
        payload_template=payload.payload_template,
        trigger_criteria=payload.trigger_criteria,
        default_agent_id=payload.default_agent_id,
        is_active=payload.is_active,
        status="active" if payload.is_active else "paused",
        health_status="unknown",
        next_fire_at=preview[0] if preview else None,
        created_by=current_user.id,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    # v0.7.0 Wave 4 — auto-generate the system-managed Flow for this trigger.
    try:
        import logging
        from config.feature_flags import flows_auto_generation_enabled
        from services.flow_binding_service import ensure_system_managed_flow_for_trigger

        if flows_auto_generation_enabled():
            ensure_system_managed_flow_for_trigger(
                db,
                tenant_id=ctx.tenant_id,
                trigger_kind="schedule",
                trigger_instance_id=instance.id,
                default_agent_id=instance.default_agent_id,
            )
            db.commit()
    except Exception:
        import logging
        logging.getLogger(__name__).exception(
            "Auto-flow generation failed for schedule trigger %s; trigger persists", instance.id
        )
        db.rollback()

    return _to_read(db, instance)


@router.get("/{trigger_id}", response_model=ScheduleTriggerRead)
def get_schedule_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> ScheduleTriggerRead:
    instance = _load_schedule_trigger(db, ctx.tenant_id, trigger_id)
    return _to_read(db, instance)


@router.patch("/{trigger_id}", response_model=ScheduleTriggerRead)
def update_schedule_trigger(
    trigger_id: int,
    payload: ScheduleTriggerUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> ScheduleTriggerRead:
    instance = _load_schedule_trigger(db, ctx.tenant_id, trigger_id)
    data = payload.model_dump(exclude_unset=True)

    next_cron = data.get("cron_expression", instance.cron_expression)
    next_timezone = data.get("timezone", instance.timezone)
    should_recalculate = "cron_expression" in data or "timezone" in data or "is_active" in data
    preview = _preview_or_400(next_cron, next_timezone) if should_recalculate else None

    if "default_agent_id" in data:
        if data["default_agent_id"] is not None:
            _load_active_agent(db, ctx.tenant_id, data["default_agent_id"])
        instance.default_agent_id = data["default_agent_id"]
    if "integration_name" in data:
        instance.integration_name = data["integration_name"]
    if "cron_expression" in data:
        instance.cron_expression = validate_cron_expression(data["cron_expression"])
    if "timezone" in data:
        instance.timezone = data["timezone"]
    if "payload_template" in data:
        instance.payload_template = data["payload_template"]
    if "trigger_criteria" in data:
        instance.trigger_criteria = data["trigger_criteria"]
    if "is_active" in data and data["is_active"] is not None:
        instance.is_active = data["is_active"]
        instance.status = "active" if data["is_active"] else "paused"
    if preview:
        instance.next_fire_at = preview[0]

    db.commit()
    db.refresh(instance)
    return _to_read(db, instance)


@router.delete("/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    instance = _load_schedule_trigger(db, ctx.tenant_id, trigger_id)
    db.delete(instance)
    db.commit()
    return None
