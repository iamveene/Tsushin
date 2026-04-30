"""Email trigger CRUD for persisted trigger rows."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.email.trigger import DEFAULT_MAX_RESULTS, EmailPollResult, EmailTrigger, normalize_gmail_message
from channels.trigger_criteria import validate_criteria
from db import get_db
from hub.google.gmail_service import GmailService
from models import Agent, Contact, EmailChannelInstance, GmailIntegration
from services.flow_binding_service import (
    delete_bindings_for_trigger,
    delete_system_owned_continuous_artifacts_for_trigger,
    sync_system_managed_flow_default_agent,
)
from services.email_triage_service import ensure_email_triage_subscription
from api.routes_trigger_recap import (
    TriggerRecapConfigRead,
    TriggerRecapConfigWrite,
    TriggerRecapTestRequest,
    TriggerRecapTestResponse,
    delete_recap_config_for,
    delete_recap_config_for_trigger_instance,
    get_recap_config_for,
    put_recap_config_for,
    run_test_recap_for,
)

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
    trigger_criteria: Optional[dict[str, Any]] = None
    poll_interval_seconds: int = Field(default=60, ge=30, le=3600)
    is_active: bool = True
    notification_recipient: Optional[str] = Field(default=None, max_length=50)
    notification_enabled: bool = False

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

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, value):
        if value is None:
            return value
        try:
            return validate_criteria(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class EmailTriggerUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    gmail_integration_id: Optional[int] = Field(default=None, ge=1)
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    search_query: Optional[str] = Field(default=None, max_length=500)
    trigger_criteria: Optional[dict[str, Any]] = None
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

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, value):
        if value is None:
            return value
        try:
            return validate_criteria(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


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
    trigger_criteria: Optional[dict[str, Any]] = None
    poll_interval_seconds: int
    is_active: bool
    status: str
    health_status: str
    health_status_reason: Optional[str] = None
    last_health_check: Optional[datetime] = None
    last_activity_at: Optional[datetime] = None
    last_cursor: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    auto_flow_id: Optional[int] = None
    # Notification config now lives on the auto-flow's Notification node and
    # is discovered via auto_flow_id.


class EmailTriageSubscriptionRead(BaseModel):
    email_trigger_id: int
    continuous_agent_id: int
    continuous_subscription_id: int
    agent_id: int
    created_agent: bool
    created_subscription: bool
    status: str = "active"


class EmailTestQueryRequest(BaseModel):
    gmail_integration_id: Optional[int] = Field(default=None, ge=1)
    search_query: Optional[str] = Field(default=None, max_length=500)
    trigger_criteria: Optional[dict[str, Any]] = None
    max_results: int = Field(default=3, ge=1, le=10)

    @field_validator("search_query")
    @classmethod
    def _normalize_query(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, value):
        if value is None:
            return value
        try:
            return validate_criteria(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class EmailMessageSample(BaseModel):
    id: str
    thread_id: Optional[str] = None
    subject: str
    from_address: Optional[str] = None
    date: Optional[str] = None
    snippet: Optional[str] = None
    description_preview: Optional[str] = None
    link: Optional[str] = None


class EmailTestQueryResponse(BaseModel):
    success: bool = True
    total: int
    sample_count: int
    messages: list[EmailMessageSample]
    message_count: int
    sample_messages: list[EmailMessageSample]
    message: Optional[str] = None
    error: Optional[str] = None


class EmailPollNowResponse(BaseModel):
    success: bool
    instance_id: int
    tenant_id: str
    status: str
    message: Optional[str] = None
    error: Optional[str] = None
    fetched_count: int
    message_count: int
    emitted_count: int
    wake_event_count: int
    dispatched_count: int
    duplicate_count: int
    skipped_count: int
    processed_count: int
    failed_count: int
    cursor: Optional[str] = None
    reason: Optional[str] = None
    dispatch_statuses: list[str]
    started_at: datetime
    completed_at: datetime


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


def _criteria_email_search_query(criteria: Optional[dict[str, Any]]) -> Optional[str]:
    if not isinstance(criteria, dict):
        return None
    filters = criteria.get("filters")
    if not isinstance(filters, dict):
        return None
    email_filters = filters.get("email")
    if not isinstance(email_filters, dict):
        return None
    value = email_filters.get("search_query")
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def _to_read(db: Session, instance: EmailChannelInstance) -> EmailTriggerRead:
    # TODO(v0.7.0 perf): per-call query for auto_flow lookup is acceptable for
    # current trigger volumes; optimize via a JOIN on FlowTriggerBinding for
    # list endpoints when N+1 becomes measurable (architect §6.4).
    from services.flow_binding_service import find_system_managed_flow_for_trigger

    auto_flow = find_system_managed_flow_for_trigger(
        db,
        tenant_id=instance.tenant_id,
        trigger_kind="email",
        trigger_instance_id=instance.id,
    )
    gmail_integration = None
    if instance.gmail_integration_id:
        gmail_integration = db.query(GmailIntegration).filter(
            GmailIntegration.id == instance.gmail_integration_id,
            GmailIntegration.tenant_id == instance.tenant_id,
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
        trigger_criteria=instance.trigger_criteria,
        poll_interval_seconds=instance.poll_interval_seconds,
        is_active=bool(instance.is_active),
        status=instance.status or "active",
        health_status=instance.health_status or "unknown",
        health_status_reason=instance.health_status_reason,
        last_health_check=instance.last_health_check,
        last_activity_at=instance.last_activity_at,
        last_cursor=instance.last_cursor,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        auto_flow_id=auto_flow.id if auto_flow else None,
    )


async def _execute_email_query(
    *,
    db: Session,
    instance: EmailChannelInstance,
    integration: GmailIntegration,
    search_query: Optional[str],
    trigger_criteria: Optional[dict[str, Any]] = None,
    max_results: int,
) -> EmailTestQueryResponse:
    gmail = GmailService(db, integration.id)
    if search_query:
        message_refs = await gmail.search_messages(search_query, max_results=max_results)
    else:
        message_refs = await gmail.list_messages(max_results=max_results)

    samples: list[EmailMessageSample] = []
    seen_ids: set[str] = set()
    matched_count = 0
    for message_ref in message_refs:
        message_id = str((message_ref or {}).get("id") or "").strip()
        if not message_id or message_id in seen_ids:
            continue
        seen_ids.add(message_id)
        message = await gmail.get_message(message_id, format="full")
        normalized = normalize_gmail_message(instance=instance, integration=integration, message=message)
        effective_criteria = trigger_criteria if trigger_criteria is not None else instance.trigger_criteria
        if effective_criteria:
            from channels.trigger_criteria import evaluate_payload_criteria

            matched, _reason = evaluate_payload_criteria(normalized.payload, effective_criteria)
            if not matched:
                continue
        matched_count += 1
        body = normalized.payload.get("message") if isinstance(normalized.payload.get("message"), dict) else {}
        description = str(body.get("body_text") or body.get("snippet") or "").strip()
        description = " ".join(description.split())
        if len(description) > 180:
            description = description[:180] + "..."
        samples.append(
            EmailMessageSample(
                id=normalized.message_id,
                thread_id=body.get("threadId") if isinstance(body.get("threadId"), str) else None,
                subject=str(body.get("subject") or "(No Subject)"),
                from_address=str(body.get("from") or "") or None,
                date=str(body.get("date") or "") or None,
                snippet=str(body.get("snippet") or "") or None,
                description_preview=description or None,
                link=f"https://mail.google.com/mail/u/0/#inbox/{normalized.message_id}",
            )
        )

    return EmailTestQueryResponse(
        success=True,
        total=matched_count,
        sample_count=len(samples),
        messages=samples,
        message_count=matched_count,
        sample_messages=samples,
        message=f"Query returned {matched_count} message(s).",
    )


def _poll_response(result: EmailPollResult) -> EmailPollNowResponse:
    completed_at = datetime.utcnow()
    success = result.status == "ok"
    message = (
        f"Processed {result.fetched_count} message(s), emitted {result.dispatched_count} wake event(s)."
        if success
        else result.reason or "Email poll did not complete."
    )
    return EmailPollNowResponse(
        success=success,
        instance_id=result.instance_id,
        tenant_id=result.tenant_id or "",
        status=result.status,
        message=message,
        error=None if success else result.reason,
        fetched_count=result.fetched_count,
        message_count=result.fetched_count,
        emitted_count=result.dispatched_count,
        wake_event_count=result.dispatched_count,
        dispatched_count=result.dispatched_count,
        duplicate_count=result.duplicate_count,
        skipped_count=result.skipped_count,
        processed_count=result.processed_count,
        failed_count=result.failed_count,
        cursor=result.cursor,
        reason=result.reason,
        dispatch_statuses=result.dispatch_statuses,
        started_at=getattr(result, "started_at", None) or completed_at,
        completed_at=getattr(result, "completed_at", None) or completed_at,
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
        search_query=payload.search_query or _criteria_email_search_query(payload.trigger_criteria),
        trigger_criteria=payload.trigger_criteria,
        poll_interval_seconds=payload.poll_interval_seconds,
        is_active=payload.is_active,
        status="active" if payload.is_active else "paused",
        health_status="unknown",
        created_by=current_user.id,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    # v0.7.0 Wave 4 — auto-generate the system-managed Flow for this trigger.
    try:
        from config.feature_flags import flows_auto_generation_enabled
        from services.flow_binding_service import ensure_system_managed_flow_for_trigger

        if flows_auto_generation_enabled():
            ensure_system_managed_flow_for_trigger(
                db,
                tenant_id=ctx.tenant_id,
                trigger_kind="email",
                trigger_instance_id=instance.id,
                default_agent_id=instance.default_agent_id,
                notification_recipient=payload.notification_recipient,
                notification_enabled=payload.notification_enabled,
            )
            db.commit()
    except Exception:
        logger.exception("Auto-flow generation failed for email trigger %s; trigger persists", instance.id)
        db.rollback()

    return _to_read(db, instance)


@router.post("/test-query", response_model=EmailTestQueryResponse)
async def run_email_test_query(
    payload: EmailTestQueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> EmailTestQueryResponse:
    if payload.gmail_integration_id is None:
        raise HTTPException(status_code=400, detail="gmail_integration_id is required")
    integration = _load_gmail_integration(db, ctx.tenant_id, payload.gmail_integration_id)
    preview_instance = EmailChannelInstance(
        id=0,
        tenant_id=ctx.tenant_id,
        integration_name="Email query preview",
        provider="gmail",
        gmail_integration_id=integration.id,
        search_query=payload.search_query or _criteria_email_search_query(payload.trigger_criteria),
        trigger_criteria=payload.trigger_criteria,
        created_by=getattr(_user, "id", 0) or 0,
    )
    try:
        return await _execute_email_query(
            db=db,
            instance=preview_instance,
            integration=integration,
            search_query=preview_instance.search_query,
            trigger_criteria=payload.trigger_criteria,
            max_results=payload.max_results,
        )
    except Exception as exc:
        logger.warning("Email test query failed for Gmail integration %s: %s", integration.id, type(exc).__name__)
        raise HTTPException(status_code=502, detail=f"Email query failed: {type(exc).__name__}") from exc


@router.post("/{trigger_id}/test-query", response_model=EmailTestQueryResponse)
async def run_saved_email_test_query(
    trigger_id: int,
    payload: EmailTestQueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> EmailTestQueryResponse:
    instance = _load_email_trigger(db, ctx.tenant_id, trigger_id)
    if not instance.gmail_integration_id and payload.gmail_integration_id is None:
        raise HTTPException(status_code=400, detail="Email trigger is missing Gmail integration")
    integration = _load_gmail_integration(db, ctx.tenant_id, payload.gmail_integration_id or instance.gmail_integration_id)
    effective_criteria = payload.trigger_criteria if payload.trigger_criteria is not None else instance.trigger_criteria
    search_query = (
        payload.search_query
        if payload.search_query is not None
        else instance.search_query or _criteria_email_search_query(effective_criteria)
    )
    try:
        return await _execute_email_query(
            db=db,
            instance=instance,
            integration=integration,
            search_query=search_query,
            trigger_criteria=effective_criteria,
            max_results=payload.max_results,
        )
    except Exception as exc:
        logger.warning("Saved email test query failed for trigger %s: %s", trigger_id, type(exc).__name__)
        raise HTTPException(status_code=502, detail=f"Email query failed: {type(exc).__name__}") from exc


@router.post("/{trigger_id}/poll-now", response_model=EmailPollNowResponse)
async def poll_email_trigger_now(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> EmailPollNowResponse:
    instance = _load_email_trigger(db, ctx.tenant_id, trigger_id)
    result = await EmailTrigger.poll_instance(
        db,
        instance,
        max_results=DEFAULT_MAX_RESULTS,
        force=True,
    )
    return _poll_response(result)


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
        sync_system_managed_flow_default_agent(
            db,
            tenant_id=ctx.tenant_id,
            trigger_kind="email",
            trigger_instance_id=instance.id,
            default_agent_id=instance.default_agent_id,
        )
    if "integration_name" in data:
        instance.integration_name = data["integration_name"]
    if "search_query" in data:
        instance.search_query = data["search_query"]
    if "trigger_criteria" in data:
        instance.trigger_criteria = data["trigger_criteria"]
        if "search_query" not in data and not instance.search_query:
            instance.search_query = _criteria_email_search_query(data["trigger_criteria"])
    if "poll_interval_seconds" in data and data["poll_interval_seconds"] is not None:
        instance.poll_interval_seconds = data["poll_interval_seconds"]
    if "is_active" in data and data["is_active"] is not None:
        instance.is_active = data["is_active"]
        instance.status = "active" if data["is_active"] else "paused"

    instance.updated_at = datetime.utcnow()
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
    delete_bindings_for_trigger(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="email",
        trigger_instance_id=trigger_id,
    )
    delete_system_owned_continuous_artifacts_for_trigger(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="email",
        trigger_instance_id=trigger_id,
    )
    delete_recap_config_for_trigger_instance(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="email",
        trigger_instance_id=trigger_id,
    )
    db.delete(instance)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# v0.7.x Wave 2-C — per-trigger Memory Recap CRUD + test-recap.
# ---------------------------------------------------------------------------


@router.get("/{trigger_id}/recap-config", response_model=TriggerRecapConfigRead)
def get_email_trigger_recap_config(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> TriggerRecapConfigRead:
    _load_email_trigger(db, ctx.tenant_id, trigger_id)
    return get_recap_config_for(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="email",
        trigger_instance_id=trigger_id,
    )


@router.put("/{trigger_id}/recap-config", response_model=TriggerRecapConfigRead)
def put_email_trigger_recap_config(
    trigger_id: int,
    payload: TriggerRecapConfigWrite,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> TriggerRecapConfigRead:
    _load_email_trigger(db, ctx.tenant_id, trigger_id)
    return put_recap_config_for(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="email",
        trigger_instance_id=trigger_id,
        payload=payload,
    )


@router.delete("/{trigger_id}/recap-config", status_code=status.HTTP_204_NO_CONTENT)
def delete_email_trigger_recap_config(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    _load_email_trigger(db, ctx.tenant_id, trigger_id)
    delete_recap_config_for(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="email",
        trigger_instance_id=trigger_id,
    )
    return None


@router.post("/{trigger_id}/test-recap", response_model=TriggerRecapTestResponse)
def post_email_trigger_test_recap(
    trigger_id: int,
    payload: TriggerRecapTestRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> TriggerRecapTestResponse:
    _load_email_trigger(db, ctx.tenant_id, trigger_id)
    return run_test_recap_for(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="email",
        trigger_instance_id=trigger_id,
        body=payload,
    )


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
        if reason in {
            "unsupported_email_provider",
            "missing_gmail_integration",
            "gmail_integration_not_found",
            "gmail_integration_tenant_mismatch",
            "gmail_integration_type_mismatch",
            "gmail_integration_inactive",
            "gmail_integration_missing_token",
            "gmail_integration_missing_draft_scope",
        }:
            raise HTTPException(
                status_code=400,
                detail="Email triage requires an active tenant-owned Gmail integration reauthorized with gmail.compose.",
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
