"""Jira trigger CRUD and JQL test-query endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.jira.trigger import JiraPollResult, JiraTrigger
from channels.jira.utils import jira_description_to_text, jira_issue_link, normalize_jira_site_url
from channels.trigger_criteria import validate_criteria
from db import get_db
from models import Agent, Contact, JiraChannelInstance, JiraIntegration
from services.jira_integration_service import (
    decrypt_jira_token,
    encrypt_jira_token,
    load_jira_integration,
    normalize_optional,
    resolve_jira_config,
    token_preview,
)
from services.flow_binding_service import (
    delete_bindings_for_trigger,
    delete_system_owned_continuous_artifacts_for_trigger,
    sync_system_managed_flow_default_agent,
)
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
    prefix="/api/triggers/jira",
    tags=["Jira Triggers"],
    redirect_slashes=False,
)

_JIRA_SEARCH_TIMEOUT_SECONDS = 10.0
_MAX_SAMPLE_SIZE = 10


class JiraTriggerCreate(BaseModel):
    """v0.7.0-fix Phase 4: jira_integration_id is required; auth_email/
    api_token/site_url are read from the linked Hub integration."""

    integration_name: str = Field(..., min_length=1, max_length=100)
    jira_integration_id: int = Field(..., ge=1)
    project_key: Optional[str] = Field(default=None, max_length=64)
    jql: str = Field(..., min_length=1, max_length=4000)
    trigger_criteria: Optional[dict[str, Any]] = None
    poll_interval_seconds: int = Field(default=300, ge=60, le=86400)
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    is_active: bool = True
    notification_recipient: Optional[str] = Field(default=None, max_length=50)
    notification_enabled: bool = False

    @field_validator("integration_name", "jql")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("project_key")
    @classmethod
    def _normalize_project_key(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional(value, upper=True)

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, value):
        if value is None:
            return value
        try:
            return validate_criteria(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class JiraTriggerUpdate(BaseModel):
    """v0.7.0-fix Phase 4: cannot accept auth_email/api_token/site_url —
    those fields are owned by the linked Hub Jira integration."""

    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    jira_integration_id: Optional[int] = Field(default=None, ge=1)
    project_key: Optional[str] = Field(default=None, max_length=64)
    jql: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    trigger_criteria: Optional[dict[str, Any]] = None
    poll_interval_seconds: Optional[int] = Field(default=None, ge=60, le=86400)
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    is_active: Optional[bool] = None

    @field_validator("integration_name", "jql")
    @classmethod
    def _strip_required(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("project_key")
    @classmethod
    def _normalize_project_key(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional(value, upper=True)

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, value):
        if value is None:
            return value
        try:
            return validate_criteria(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc




class JiraTriggerRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    jira_integration_id: Optional[int] = None
    jira_integration_name: Optional[str] = None
    jira_integration_health_status: Optional[str] = None
    jira_integration_health_status_reason: Optional[str] = None
    site_url: str
    project_key: Optional[str] = None
    jql: str
    trigger_criteria: Optional[dict[str, Any]] = None
    poll_interval_seconds: int
    default_agent_id: Optional[int] = None
    default_agent_name: Optional[str] = None
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
    # Notification config lives on the auto-generated Flow's Notification node
    # and is discovered via auto_flow_id + FlowDefinition.nodes.


class JiraTestQueryRequest(BaseModel):
    """v0.7.0-fix Phase 4: dry-runs require a Hub jira_integration_id;
    auth_email/api_token/site_url are no longer accepted on the wire."""

    jira_integration_id: Optional[int] = Field(default=None, ge=1)
    jql: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    max_results: int = Field(default=3, ge=1, le=_MAX_SAMPLE_SIZE)

    @field_validator("jql")
    @classmethod
    def _normalize_jql(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional(value)


class JiraIssueSample(BaseModel):
    id: Optional[str] = None
    key: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None
    issue_type: Optional[str] = None
    link: Optional[str] = None
    description_preview: Optional[str] = None
    updated: Optional[str] = None


class JiraTestQueryResponse(BaseModel):
    success: bool = True
    total: int
    sample_count: int
    issues: list[JiraIssueSample]
    issue_count: int
    sample_issues: list[JiraIssueSample]
    message: Optional[str] = None
    error: Optional[str] = None


class JiraPollNowResponse(BaseModel):
    success: bool
    instance_id: int
    tenant_id: str
    status: str
    message: Optional[str] = None
    error: Optional[str] = None
    fetched_count: int
    issue_count: int
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


def _normalize_optional(value: Optional[str], *, upper: bool = False) -> Optional[str]:
    return normalize_optional(value, upper=upper)


def _normalize_site_url(value: str) -> str:
    return normalize_jira_site_url(value)


def _token_preview(token: str) -> str:
    return token_preview(token)


def _encrypt_token(db: Session, tenant_id: str, plaintext: str) -> str:
    try:
        return encrypt_jira_token(db, tenant_id, plaintext)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Server configuration error") from exc


def _decrypt_token(db: Session, tenant_id: str, encrypted: str) -> str:
    try:
        token = decrypt_jira_token(db, tenant_id, encrypted)
        return token or ""
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Could not decrypt Jira API token") from exc


def _load_jira_integration(db: Session, tenant_id: str, integration_id: int) -> JiraIntegration:
    integration = load_jira_integration(db, tenant_id=tenant_id, integration_id=integration_id)
    if integration is None:
        raise HTTPException(status_code=404, detail="Jira integration not found")
    return integration


def _load_active_agent(db: Session, tenant_id: str, agent_id: int) -> Agent:
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
        Agent.is_active == True,  # noqa: E712
    ).first()
    if agent is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return agent


def _load_jira_trigger(db: Session, tenant_id: str, trigger_id: int) -> JiraChannelInstance:
    instance = db.query(JiraChannelInstance).filter(
        JiraChannelInstance.id == trigger_id,
        JiraChannelInstance.tenant_id == tenant_id,
    ).first()
    if instance is None:
        raise HTTPException(status_code=404, detail="Jira trigger not found")
    return instance


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


def _to_read(db: Session, instance: JiraChannelInstance) -> JiraTriggerRead:
    # TODO(v0.7.0 perf): per-call query for auto_flow lookup is acceptable for
    # current trigger volumes; optimize via a JOIN on FlowTriggerBinding for
    # list endpoints when N+1 becomes measurable (architect §6.4).
    from services.flow_binding_service import find_system_managed_flow_for_trigger

    try:
        config = resolve_jira_config(db, instance)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Jira integration not found") from exc
    auto_flow = find_system_managed_flow_for_trigger(
        db,
        tenant_id=instance.tenant_id,
        trigger_kind="jira",
        trigger_instance_id=instance.id,
    )
    jira_integration_name = None
    jira_integration_health_status = None
    jira_integration_health_status_reason = None
    if config.jira_integration_id:
        integration = db.query(JiraIntegration).filter(
            JiraIntegration.id == config.jira_integration_id,
            JiraIntegration.tenant_id == instance.tenant_id,
        ).first()
        if integration is not None:
            jira_integration_name = integration.display_name or integration.name
            jira_integration_health_status = integration.health_status
            jira_integration_health_status_reason = integration.health_status_reason
    return JiraTriggerRead(
        id=instance.id,
        tenant_id=instance.tenant_id,
        integration_name=instance.integration_name,
        jira_integration_id=config.jira_integration_id,
        jira_integration_name=jira_integration_name,
        jira_integration_health_status=jira_integration_health_status,
        jira_integration_health_status_reason=jira_integration_health_status_reason,
        site_url=config.site_url,
        project_key=instance.project_key or config.project_key,
        jql=instance.jql,
        trigger_criteria=instance.trigger_criteria,
        poll_interval_seconds=instance.poll_interval_seconds,
        default_agent_id=instance.default_agent_id,
        default_agent_name=_agent_name(db, instance.tenant_id, instance.default_agent_id),
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


async def _execute_jira_search(
    *,
    site_url: str,
    jql: str,
    auth_email: Optional[str],
    api_token: Optional[str],
    max_results: int,
) -> dict[str, Any]:
    auth = None
    if auth_email or api_token:
        if not auth_email or not api_token:
            raise HTTPException(
                status_code=400,
                detail="auth_email and api_token are both required for authenticated Jira queries",
            )
        auth = (auth_email, api_token)

    url = f"{normalize_jira_site_url(site_url)}/rest/api/3/search/jql"
    payload = {
        "jql": jql,
        "maxResults": max_results,
        "fields": [
            "summary",
            "description",
            "status",
            "issuetype",
            "project",
            "priority",
            "reporter",
            "assignee",
            "created",
            "updated",
            "labels",
        ],
    }
    try:
        async with httpx.AsyncClient(timeout=_JIRA_SEARCH_TIMEOUT_SECONDS) as client:
            response = await client.post(url, json=payload, auth=auth)
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="Jira query timed out") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"Jira query failed: {type(exc).__name__}") from exc

    if response.status_code >= 400:
        detail: Any
        try:
            detail = response.json()
        except ValueError:
            detail = response.text[:500]
        raise HTTPException(
            status_code=502,
            detail={"message": "Jira query failed", "status_code": response.status_code, "jira": detail},
        )

    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(status_code=502, detail="Jira returned invalid JSON") from exc


def _sample_response(data: dict[str, Any], *, site_url: str) -> JiraTestQueryResponse:
    raw_issues = data.get("issues")
    issues = raw_issues if isinstance(raw_issues, list) else []
    samples: list[JiraIssueSample] = []
    for issue in issues[:_MAX_SAMPLE_SIZE]:
        if not isinstance(issue, dict):
            continue
        fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
        status_value = fields.get("status")
        status_name = status_value.get("name") if isinstance(status_value, dict) else None
        issue_type = fields.get("issuetype")
        issue_type_name = issue_type.get("name") if isinstance(issue_type, dict) else None
        key = str(issue.get("key")) if issue.get("key") is not None else None
        samples.append(
            JiraIssueSample(
                id=str(issue.get("id")) if issue.get("id") is not None else None,
                key=key,
                summary=fields.get("summary") if isinstance(fields.get("summary"), str) else None,
                status=status_name if isinstance(status_name, str) else None,
                issue_type=issue_type_name if isinstance(issue_type_name, str) else None,
                link=jira_issue_link(site_url, key),
                description_preview=jira_description_to_text(fields.get("description"), max_chars=180),
                updated=fields.get("updated") if isinstance(fields.get("updated"), str) else None,
            )
        )
    total = data.get("total")
    count = total if isinstance(total, int) else len(issues)
    return JiraTestQueryResponse(
        success=True,
        total=count,
        sample_count=len(samples),
        issues=samples,
        issue_count=count,
        sample_issues=samples,
        message=f"Query returned {count} issue(s).",
    )


async def _run_test_query(
    *,
    site_url: str,
    jql: str,
    auth_email: Optional[str],
    api_token: Optional[str],
    max_results: int,
) -> JiraTestQueryResponse:
    data = await _execute_jira_search(
        site_url=site_url,
        jql=jql,
        auth_email=auth_email,
        api_token=api_token,
        max_results=max_results,
    )
    return _sample_response(data, site_url=site_url)


def _poll_response(result: JiraPollResult) -> JiraPollNowResponse:
    completed_at = datetime.utcnow()
    success = result.status == "ok"
    message = (
        f"Processed {result.fetched_count} issue(s), emitted {result.dispatched_count} wake event(s)."
        if success
        else result.reason or "Jira poll did not complete."
    )
    return JiraPollNowResponse(
        success=success,
        instance_id=result.instance_id,
        tenant_id=result.tenant_id,
        status=result.status,
        message=message,
        error=None if success else result.reason,
        fetched_count=result.fetched_count,
        issue_count=result.fetched_count,
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


@router.get("", response_model=list[JiraTriggerRead])
def list_jira_triggers(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[JiraTriggerRead]:
    rows = db.query(JiraChannelInstance).filter(
        JiraChannelInstance.tenant_id == ctx.tenant_id,
    ).order_by(
        JiraChannelInstance.created_at.desc(),
        JiraChannelInstance.id.desc(),
    ).all()
    return [_to_read(db, row) for row in rows]


@router.post("", response_model=JiraTriggerRead, status_code=status.HTTP_201_CREATED)
def create_jira_trigger(
    payload: JiraTriggerCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> JiraTriggerRead:
    if payload.default_agent_id is not None:
        _load_active_agent(db, ctx.tenant_id, payload.default_agent_id)

    jira_integration = _load_jira_integration(db, ctx.tenant_id, payload.jira_integration_id)
    site_url = jira_integration.site_url
    project_key = payload.project_key if payload.project_key is not None else getattr(jira_integration, "project_key", None)
    instance = JiraChannelInstance(
        tenant_id=ctx.tenant_id,
        integration_name=payload.integration_name,
        jira_integration_id=payload.jira_integration_id,
        site_url=site_url,
        project_key=project_key,
        jql=payload.jql,
        # Legacy auth columns (auth_email/api_token_encrypted/api_token_preview)
        # are kept on the model for runtime compatibility but never written to
        # from the API path. The runtime channel reads via resolve_jira_config
        # which prefers the linked integration. v0.7.0-fix Phase 4b will drop
        # these columns once the runtime is fully decoupled.
        trigger_criteria=payload.trigger_criteria,
        poll_interval_seconds=payload.poll_interval_seconds,
        default_agent_id=payload.default_agent_id,
        is_active=payload.is_active,
        status="active" if payload.is_active else "paused",
        health_status="unknown",
        created_by=current_user.id,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    # v0.7.0 Wave 4 — auto-generate the system-managed Flow for this trigger.
    # Gated by TSN_FLOWS_AUTO_GENERATION_ENABLED. Failure here NEVER aborts
    # trigger creation — the trigger row is the source of truth and a
    # reconciliation script can sweep for orphan triggers later.
    try:
        from config.feature_flags import flows_auto_generation_enabled
        from services.flow_binding_service import ensure_system_managed_flow_for_trigger

        if flows_auto_generation_enabled():
            ensure_system_managed_flow_for_trigger(
                db,
                tenant_id=ctx.tenant_id,
                trigger_kind="jira",
                trigger_instance_id=instance.id,
                default_agent_id=instance.default_agent_id,
                notification_recipient=payload.notification_recipient,
                notification_enabled=payload.notification_enabled,
            )
            db.commit()
    except Exception:
        logger.exception("Auto-flow generation failed for jira trigger %s; trigger persists", instance.id)
        db.rollback()

    return _to_read(db, instance)


@router.post("/test-query", response_model=JiraTestQueryResponse)
async def run_jira_test_query(
    payload: JiraTestQueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> JiraTestQueryResponse:
    if not payload.jql:
        raise HTTPException(status_code=400, detail="jql is required")
    if payload.jira_integration_id is None:
        raise HTTPException(status_code=400, detail="jira_integration_id is required")
    jira_integration = _load_jira_integration(db, ctx.tenant_id, payload.jira_integration_id)
    api_token = (
        _decrypt_token(db, ctx.tenant_id, jira_integration.api_token_encrypted)
        if jira_integration.api_token_encrypted
        else None
    )
    return await _run_test_query(
        site_url=jira_integration.site_url,
        jql=payload.jql,
        auth_email=jira_integration.auth_email,
        api_token=api_token,
        max_results=payload.max_results,
    )


@router.post("/{trigger_id}/test-query", response_model=JiraTestQueryResponse)
async def run_saved_jira_test_query(
    trigger_id: int,
    payload: JiraTestQueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> JiraTestQueryResponse:
    instance = _load_jira_trigger(db, ctx.tenant_id, trigger_id)
    try:
        config = resolve_jira_config(db, instance)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="Jira integration not found") from exc
    api_token = (
        _decrypt_token(db, instance.tenant_id, config.api_token_encrypted)
        if config.api_token_encrypted
        else None
    )
    return await _run_test_query(
        site_url=config.site_url,
        jql=payload.jql or instance.jql,
        auth_email=config.auth_email,
        api_token=api_token,
        max_results=payload.max_results,
    )


@router.post("/{trigger_id}/poll-now", response_model=JiraPollNowResponse)
async def poll_jira_trigger_now(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> JiraPollNowResponse:
    instance = _load_jira_trigger(db, ctx.tenant_id, trigger_id)
    result = await JiraTrigger.poll_instance(db, instance, force=True)
    return _poll_response(result)


@router.get("/{trigger_id}", response_model=JiraTriggerRead)
def get_jira_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> JiraTriggerRead:
    instance = _load_jira_trigger(db, ctx.tenant_id, trigger_id)
    return _to_read(db, instance)


@router.patch("/{trigger_id}", response_model=JiraTriggerRead)
def update_jira_trigger(
    trigger_id: int,
    payload: JiraTriggerUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> JiraTriggerRead:
    instance = _load_jira_trigger(db, ctx.tenant_id, trigger_id)
    data = payload.model_dump(exclude_unset=True)

    if "default_agent_id" in data:
        if data["default_agent_id"] is not None:
            _load_active_agent(db, ctx.tenant_id, data["default_agent_id"])
        instance.default_agent_id = data["default_agent_id"]
        sync_system_managed_flow_default_agent(
            db,
            tenant_id=ctx.tenant_id,
            trigger_kind="jira",
            trigger_instance_id=instance.id,
            default_agent_id=instance.default_agent_id,
        )
    if "integration_name" in data:
        instance.integration_name = data["integration_name"]
    if "jira_integration_id" in data and data["jira_integration_id"] is not None:
        integration = _load_jira_integration(db, ctx.tenant_id, data["jira_integration_id"])
        instance.jira_integration_id = integration.id
        instance.site_url = integration.site_url
        if instance.project_key is None:
            instance.project_key = integration.project_key
    if "project_key" in data:
        instance.project_key = data["project_key"]
    if "jql" in data:
        instance.jql = data["jql"]
    if "trigger_criteria" in data:
        instance.trigger_criteria = data["trigger_criteria"]
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
def delete_jira_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    instance = _load_jira_trigger(db, ctx.tenant_id, trigger_id)
    delete_bindings_for_trigger(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="jira",
        trigger_instance_id=trigger_id,
    )
    delete_system_owned_continuous_artifacts_for_trigger(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="jira",
        trigger_instance_id=trigger_id,
    )
    delete_recap_config_for_trigger_instance(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="jira",
        trigger_instance_id=trigger_id,
    )
    db.delete(instance)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# v0.7.x Wave 2-C — per-trigger Memory Recap CRUD + test-recap.
# ---------------------------------------------------------------------------


@router.get("/{trigger_id}/recap-config", response_model=TriggerRecapConfigRead)
def get_jira_trigger_recap_config(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> TriggerRecapConfigRead:
    _load_jira_trigger(db, ctx.tenant_id, trigger_id)
    return get_recap_config_for(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="jira",
        trigger_instance_id=trigger_id,
    )


@router.put("/{trigger_id}/recap-config", response_model=TriggerRecapConfigRead)
def put_jira_trigger_recap_config(
    trigger_id: int,
    payload: TriggerRecapConfigWrite,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> TriggerRecapConfigRead:
    _load_jira_trigger(db, ctx.tenant_id, trigger_id)
    return put_recap_config_for(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="jira",
        trigger_instance_id=trigger_id,
        payload=payload,
    )


@router.delete("/{trigger_id}/recap-config", status_code=status.HTTP_204_NO_CONTENT)
def delete_jira_trigger_recap_config(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    _load_jira_trigger(db, ctx.tenant_id, trigger_id)
    delete_recap_config_for(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="jira",
        trigger_instance_id=trigger_id,
    )
    return None


@router.post("/{trigger_id}/test-recap", response_model=TriggerRecapTestResponse)
def post_jira_trigger_test_recap(
    trigger_id: int,
    payload: TriggerRecapTestRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> TriggerRecapTestResponse:
    _load_jira_trigger(db, ctx.tenant_id, trigger_id)
    return run_test_recap_for(
        db,
        tenant_id=ctx.tenant_id,
        trigger_kind="jira",
        trigger_instance_id=trigger_id,
        body=payload,
    )
