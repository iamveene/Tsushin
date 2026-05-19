"""GitLab repository trigger CRUD."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

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
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.gitlab.trigger import (
    build_dispatch_payload,
    encrypt_webhook_secret,
    generate_webhook_secret,
    normalize_gitlab_events,
    normalize_project_path,
    preview_secret,
)
from channels.github.trigger import normalize_path_filters
from channels.repository.criteria import evaluate_repository_criteria, validate_repository_criteria
from db import get_db
from models import Agent, Contact, GitLabChannelInstance, GitLabIntegration
from services.flow_binding_service import (
    delete_bindings_for_trigger,
    delete_system_owned_continuous_artifacts_for_trigger,
    sync_system_managed_flow_default_agent,
)


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/triggers/gitlab",
    tags=["GitLab Triggers"],
    redirect_slashes=False,
)


class GitLabTriggerCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    gitlab_integration_id: int = Field(..., ge=1)
    project_path: str = Field(..., min_length=3, max_length=500)
    webhook_secret: Optional[str] = Field(default=None, min_length=8, max_length=500)
    events: Optional[list[str]] = None
    branch_filter: Optional[str] = Field(default=None, max_length=255)
    path_filters: Optional[list[str]] = None
    author_filter: Optional[str] = Field(default=None, max_length=255)
    trigger_criteria: Optional[dict[str, Any]] = None
    default_agent_id: Optional[int] = Field(default=None, ge=1)
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

    @field_validator("project_path")
    @classmethod
    def _normalize_project_path(cls, value: str) -> str:
        return normalize_project_path(value)

    @field_validator("events")
    @classmethod
    def _normalize_events(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        return normalize_gitlab_events(value)

    @field_validator("path_filters")
    @classmethod
    def _normalize_paths(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        return normalize_path_filters(value)

    @field_validator("branch_filter", "author_filter")
    @classmethod
    def _normalize_optional_string(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_criteria(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        return validate_repository_criteria(value)


class GitLabTriggerUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    gitlab_integration_id: Optional[int] = Field(default=None, ge=1)
    project_path: Optional[str] = Field(default=None, min_length=3, max_length=500)
    webhook_secret: Optional[str] = Field(default=None, min_length=8, max_length=500)
    events: Optional[list[str]] = None
    branch_filter: Optional[str] = Field(default=None, max_length=255)
    path_filters: Optional[list[str]] = None
    author_filter: Optional[str] = Field(default=None, max_length=255)
    trigger_criteria: Optional[dict[str, Any]] = None
    default_agent_id: Optional[int] = Field(default=None, ge=1)
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

    @field_validator("project_path")
    @classmethod
    def _normalize_project_path(cls, value: Optional[str]) -> Optional[str]:
        return normalize_project_path(value) if value is not None else None

    @field_validator("events")
    @classmethod
    def _normalize_events(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        return normalize_gitlab_events(value)

    @field_validator("path_filters")
    @classmethod
    def _normalize_paths(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        return normalize_path_filters(value)

    @field_validator("branch_filter", "author_filter")
    @classmethod
    def _normalize_optional_string(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_criteria(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        return validate_repository_criteria(value)


class GitLabTriggerRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    gitlab_integration_id: int
    gitlab_integration_name: Optional[str] = None
    project_path: str
    webhook_secret_preview: Optional[str] = None
    events: list[str]
    branch_filter: Optional[str] = None
    path_filters: Optional[list[str]] = None
    author_filter: Optional[str] = None
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
    last_delivery_id: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    inbound_url: str
    auto_flow_id: Optional[int] = None


class GitLabCriteriaTestRequest(BaseModel):
    criteria: dict[str, Any]
    payload: dict[str, Any]
    provider_event: Optional[str] = None


class GitLabCriteriaPayloadRequest(BaseModel):
    payload: dict[str, Any]
    provider_event: Optional[str] = None


class GitLabCriteriaTestResponse(BaseModel):
    matched: bool
    reason: str


def _gitlab_provider_event_for_criteria(criteria: dict[str, Any]) -> str:
    event = str(criteria.get("event") or "").strip().lower()
    return {
        "pull_request": "merge_request",
        "merge_request": "merge_request",
        "comment": "note",
        "release": "tag_push",
    }.get(event, event or "merge_request")


def _gitlab_repository_payload_for_criteria(
    payload: dict[str, Any],
    criteria: dict[str, Any],
    provider_event: Optional[str] = None,
) -> dict[str, Any]:
    if payload.get("provider") == "gitlab":
        return payload
    event_type = provider_event or _gitlab_provider_event_for_criteria(criteria)
    return build_dispatch_payload(
        instance_id=0,
        delivery_id="criteria-test",
        event_type=event_type,
        payload=payload,
    )


def _can_access(ctx: TenantContext, tenant_id: Optional[str]) -> bool:
    if hasattr(ctx, "can_access_resource"):
        return ctx.can_access_resource(tenant_id)
    return tenant_id == getattr(ctx, "tenant_id", None)


def _tenant_query(ctx: TenantContext, db: Session):
    query = db.query(GitLabChannelInstance)
    if hasattr(ctx, "filter_by_tenant"):
        return ctx.filter_by_tenant(query, GitLabChannelInstance.tenant_id)
    return query.filter(GitLabChannelInstance.tenant_id == getattr(ctx, "tenant_id", None))


def _load_gitlab_trigger(db: Session, ctx: TenantContext, trigger_id: int) -> GitLabChannelInstance:
    instance = db.query(GitLabChannelInstance).filter(GitLabChannelInstance.id == trigger_id).first()
    if instance is None or not _can_access(ctx, instance.tenant_id):
        raise HTTPException(status_code=404, detail="GitLab trigger not found")
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


def _load_gitlab_integration(db: Session, tenant_id: str, integration_id: int) -> GitLabIntegration:
    integration = db.query(GitLabIntegration).filter(
        GitLabIntegration.id == integration_id,
        GitLabIntegration.tenant_id == tenant_id,
        GitLabIntegration.type == "gitlab",
    ).first()
    if integration is None:
        raise HTTPException(status_code=404, detail="GitLab integration not found for this tenant. Create one under Hub -> Repository Integrations first.")
    return integration


def _agent_name(db: Session, tenant_id: str, agent_id: Optional[int]) -> Optional[str]:
    if not agent_id:
        return None
    row = db.query(Contact.friendly_name).join(Agent, Agent.contact_id == Contact.id).filter(
        Agent.id == agent_id,
        Agent.tenant_id == tenant_id,
    ).first()
    return row.friendly_name if row else None


def _integration_name(db: Session, integration_id: Optional[int], tenant_id: str) -> Optional[str]:
    if not integration_id:
        return None
    row = db.query(GitLabIntegration.display_name, GitLabIntegration.name).filter(
        GitLabIntegration.id == integration_id,
        GitLabIntegration.tenant_id == tenant_id,
        GitLabIntegration.type == "gitlab",
    ).first()
    if not row:
        return None
    return row.display_name or row.name


def _inbound_url(instance: GitLabChannelInstance) -> str:
    return f"/api/triggers/gitlab/{instance.id}/inbound"


def _to_read(db: Session, instance: GitLabChannelInstance) -> GitLabTriggerRead:
    from services.flow_binding_service import find_system_managed_flow_for_trigger

    auto_flow = find_system_managed_flow_for_trigger(
        db,
        tenant_id=instance.tenant_id,
        trigger_kind="gitlab",
        trigger_instance_id=instance.id,
    )
    return GitLabTriggerRead(
        id=instance.id,
        tenant_id=instance.tenant_id,
        integration_name=instance.integration_name,
        gitlab_integration_id=instance.gitlab_integration_id,
        gitlab_integration_name=_integration_name(db, instance.gitlab_integration_id, instance.tenant_id),
        project_path=instance.project_path,
        webhook_secret_preview=instance.webhook_secret_preview,
        events=normalize_gitlab_events(instance.events),
        branch_filter=instance.branch_filter,
        path_filters=normalize_path_filters(instance.path_filters),
        author_filter=instance.author_filter,
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
        last_delivery_id=instance.last_delivery_id,
        created_at=instance.created_at,
        updated_at=instance.updated_at,
        inbound_url=_inbound_url(instance),
        auto_flow_id=auto_flow.id if auto_flow else None,
    )


@router.get("", response_model=list[GitLabTriggerRead])
def list_gitlab_triggers(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[GitLabTriggerRead]:
    rows = _tenant_query(ctx, db).order_by(
        GitLabChannelInstance.created_at.desc(),
        GitLabChannelInstance.id.desc(),
    ).all()
    return [_to_read(db, row) for row in rows]


@router.post("", response_model=GitLabTriggerRead, status_code=status.HTTP_201_CREATED)
def create_gitlab_trigger(
    payload: GitLabTriggerCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitLabTriggerRead:
    tenant_id = ctx.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    if payload.default_agent_id is not None:
        _load_active_agent(db, tenant_id, payload.default_agent_id)
    _load_gitlab_integration(db, tenant_id, payload.gitlab_integration_id)

    webhook_secret = payload.webhook_secret or generate_webhook_secret()
    instance = GitLabChannelInstance(
        tenant_id=tenant_id,
        integration_name=payload.integration_name,
        gitlab_integration_id=payload.gitlab_integration_id,
        project_path=payload.project_path,
        webhook_secret_encrypted=encrypt_webhook_secret(db, tenant_id, webhook_secret),
        webhook_secret_preview=preview_secret(webhook_secret),
        events=normalize_gitlab_events(payload.events),
        branch_filter=payload.branch_filter,
        path_filters=payload.path_filters,
        author_filter=payload.author_filter,
        trigger_criteria=payload.trigger_criteria,
        default_agent_id=payload.default_agent_id,
        is_active=payload.is_active,
        status="active" if payload.is_active else "paused",
        health_status="unknown",
        created_by=current_user.id,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    try:
        from config.feature_flags import flows_auto_generation_enabled
        from services.flow_binding_service import ensure_system_managed_flow_for_trigger

        if flows_auto_generation_enabled():
            ensure_system_managed_flow_for_trigger(
                db,
                tenant_id=tenant_id,
                trigger_kind="gitlab",
                trigger_instance_id=instance.id,
                default_agent_id=instance.default_agent_id,
                notification_recipient=payload.notification_recipient,
                notification_enabled=payload.notification_enabled,
            )
            db.commit()
    except Exception:
        logger.exception("Auto-flow generation failed for gitlab trigger %s; trigger persists", instance.id)
        db.rollback()

    return _to_read(db, instance)


@router.post("/test-criteria", response_model=GitLabCriteriaTestResponse)
def dry_run_gitlab_criteria_unsaved(
    payload: GitLabCriteriaTestRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitLabCriteriaTestResponse:
    del ctx, db
    try:
        criteria = validate_repository_criteria(payload.criteria)
        matched, reason = evaluate_repository_criteria(
            _gitlab_repository_payload_for_criteria(payload.payload, criteria, payload.provider_event),
            criteria,
            provider="gitlab",
            provider_event=payload.provider_event,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_repository_criteria: {exc}") from exc
    return GitLabCriteriaTestResponse(matched=matched, reason=reason)


@router.post("/{trigger_id}/test-criteria", response_model=GitLabCriteriaTestResponse)
def dry_run_gitlab_criteria_saved(
    trigger_id: int,
    payload: GitLabCriteriaPayloadRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitLabCriteriaTestResponse:
    instance = _load_gitlab_trigger(db, ctx, trigger_id)
    if not instance.trigger_criteria:
        raise HTTPException(status_code=409, detail="trigger_criteria not configured")
    try:
        criteria = validate_repository_criteria(instance.trigger_criteria)
        matched, reason = evaluate_repository_criteria(
            _gitlab_repository_payload_for_criteria(payload.payload, criteria, payload.provider_event),
            criteria,
            provider="gitlab",
            provider_event=payload.provider_event,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_repository_criteria: {exc}") from exc
    return GitLabCriteriaTestResponse(matched=matched, reason=reason)


@router.get("/{trigger_id}", response_model=GitLabTriggerRead)
def get_gitlab_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitLabTriggerRead:
    return _to_read(db, _load_gitlab_trigger(db, ctx, trigger_id))


@router.patch("/{trigger_id}", response_model=GitLabTriggerRead)
def update_gitlab_trigger(
    trigger_id: int,
    payload: GitLabTriggerUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitLabTriggerRead:
    instance = _load_gitlab_trigger(db, ctx, trigger_id)
    data = payload.model_dump(exclude_unset=True)
    if "default_agent_id" in data:
        if data["default_agent_id"] is not None:
            _load_active_agent(db, instance.tenant_id, data["default_agent_id"])
        instance.default_agent_id = data["default_agent_id"]
        sync_system_managed_flow_default_agent(
            db,
            tenant_id=instance.tenant_id,
            trigger_kind="gitlab",
            trigger_instance_id=instance.id,
            default_agent_id=instance.default_agent_id,
        )
    if "gitlab_integration_id" in data and data["gitlab_integration_id"] is not None:
        _load_gitlab_integration(db, instance.tenant_id, data["gitlab_integration_id"])
        instance.gitlab_integration_id = data["gitlab_integration_id"]
    for field_name in ("integration_name", "project_path"):
        if field_name in data and data[field_name] is not None:
            setattr(instance, field_name, data[field_name])
    if "webhook_secret" in data and data["webhook_secret"]:
        instance.webhook_secret_encrypted = encrypt_webhook_secret(db, instance.tenant_id, data["webhook_secret"])
        instance.webhook_secret_preview = preview_secret(data["webhook_secret"])
    if "events" in data and data["events"] is not None:
        instance.events = normalize_gitlab_events(data["events"])
    if "branch_filter" in data:
        instance.branch_filter = data["branch_filter"]
    if "path_filters" in data:
        instance.path_filters = data["path_filters"]
    if "author_filter" in data:
        instance.author_filter = data["author_filter"]
    if "trigger_criteria" in data:
        instance.trigger_criteria = data["trigger_criteria"]
    if "is_active" in data and data["is_active"] is not None:
        instance.is_active = data["is_active"]
        instance.status = "active" if data["is_active"] else "paused"
    instance.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(instance)
    return _to_read(db, instance)


@router.delete("/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_gitlab_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    instance = _load_gitlab_trigger(db, ctx, trigger_id)
    delete_bindings_for_trigger(db, tenant_id=ctx.tenant_id, trigger_kind="gitlab", trigger_instance_id=trigger_id)
    delete_system_owned_continuous_artifacts_for_trigger(db, tenant_id=ctx.tenant_id, trigger_kind="gitlab", trigger_instance_id=trigger_id)
    delete_recap_config_for_trigger_instance(db, tenant_id=ctx.tenant_id, trigger_kind="gitlab", trigger_instance_id=trigger_id)
    db.delete(instance)
    db.commit()
    return None


@router.get("/{trigger_id}/recap-config", response_model=TriggerRecapConfigRead)
def get_gitlab_trigger_recap_config(trigger_id: int, ctx: TenantContext = Depends(get_tenant_context), _user=Depends(require_permission("hub.read")), db: Session = Depends(get_db)) -> TriggerRecapConfigRead:
    _load_gitlab_trigger(db, ctx, trigger_id)
    return get_recap_config_for(db, tenant_id=ctx.tenant_id, trigger_kind="gitlab", trigger_instance_id=trigger_id)


@router.put("/{trigger_id}/recap-config", response_model=TriggerRecapConfigRead)
def put_gitlab_trigger_recap_config(trigger_id: int, payload: TriggerRecapConfigWrite, ctx: TenantContext = Depends(get_tenant_context), _user=Depends(require_permission("hub.write")), db: Session = Depends(get_db)) -> TriggerRecapConfigRead:
    _load_gitlab_trigger(db, ctx, trigger_id)
    return put_recap_config_for(db, tenant_id=ctx.tenant_id, trigger_kind="gitlab", trigger_instance_id=trigger_id, payload=payload)


@router.delete("/{trigger_id}/recap-config", status_code=status.HTTP_204_NO_CONTENT)
def delete_gitlab_trigger_recap_config(trigger_id: int, ctx: TenantContext = Depends(get_tenant_context), _user=Depends(require_permission("hub.write")), db: Session = Depends(get_db)) -> None:
    _load_gitlab_trigger(db, ctx, trigger_id)
    delete_recap_config_for(db, tenant_id=ctx.tenant_id, trigger_kind="gitlab", trigger_instance_id=trigger_id)
    db.commit()
    return None


@router.post("/{trigger_id}/test-recap", response_model=TriggerRecapTestResponse)
def test_gitlab_trigger_recap(trigger_id: int, payload: TriggerRecapTestRequest, ctx: TenantContext = Depends(get_tenant_context), _user=Depends(require_permission("hub.read")), db: Session = Depends(get_db)) -> TriggerRecapTestResponse:
    _load_gitlab_trigger(db, ctx, trigger_id)
    return run_test_recap_for(db, tenant_id=ctx.tenant_id, trigger_kind="gitlab", trigger_instance_id=trigger_id, body=payload)
