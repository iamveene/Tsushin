"""GitHub trigger CRUD and connection checks."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.github.criteria import evaluate_pr_criteria, validate_pr_criteria
from channels.github.trigger import (
    decrypt_pat_token,
    encrypt_pat_token,
    encrypt_webhook_secret,
    generate_webhook_secret,
    normalize_github_events,
    normalize_path_filters,
    normalize_repo_part,
    preview_secret,
)
from channels.trigger_criteria import validate_criteria
from db import get_db
from models import Agent, Contact, GitHubChannelInstance


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/triggers/github",
    tags=["GitHub Triggers"],
    redirect_slashes=False,
)


class GitHubTriggerCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    auth_method: str = Field(default="pat", max_length=20)
    repo_owner: str = Field(..., min_length=1, max_length=100)
    repo_name: str = Field(..., min_length=1, max_length=100)
    installation_id: Optional[str] = Field(default=None, max_length=64)
    pat_token: Optional[str] = Field(default=None, min_length=1, max_length=500)
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

    @field_validator("auth_method")
    @classmethod
    def _normalize_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"pat", "app"}:
            raise ValueError("auth_method must be one of: pat, app")
        return normalized

    @field_validator("repo_owner")
    @classmethod
    def _normalize_owner(cls, value: str) -> str:
        return normalize_repo_part(value, "repo_owner")

    @field_validator("repo_name")
    @classmethod
    def _normalize_repo_name(cls, value: str) -> str:
        return normalize_repo_part(value, "repo_name")

    @field_validator("events")
    @classmethod
    def _normalize_events(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        try:
            return normalize_github_events(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("path_filters")
    @classmethod
    def _normalize_path_filters(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        return normalize_path_filters(value)

    @field_validator("branch_filter", "author_filter", "installation_id")
    @classmethod
    def _normalize_optional_string(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("trigger_criteria must be an object")
        # The GitHub trigger ships a dedicated PR-submitted envelope today.
        # When ``event`` is set, route through the GitHub-specific validator;
        # otherwise fall back to the shared envelope so JSONPath-style rules
        # continue to round-trip cleanly.
        if str(value.get("event") or "").strip().lower() == "pull_request":
            try:
                return validate_pr_criteria(value)
            except ValueError as exc:
                raise ValueError(f"invalid_pr_criteria: {exc}") from exc
        try:
            return validate_criteria(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class GitHubTriggerUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    auth_method: Optional[str] = Field(default=None, max_length=20)
    repo_owner: Optional[str] = Field(default=None, min_length=1, max_length=100)
    repo_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    installation_id: Optional[str] = Field(default=None, max_length=64)
    pat_token: Optional[str] = Field(default=None, min_length=1, max_length=500)
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

    @field_validator("auth_method")
    @classmethod
    def _normalize_auth_method(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip().lower()
        if normalized not in {"pat", "app"}:
            raise ValueError("auth_method must be one of: pat, app")
        return normalized

    @field_validator("repo_owner")
    @classmethod
    def _normalize_owner(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return normalize_repo_part(value, "repo_owner")

    @field_validator("repo_name")
    @classmethod
    def _normalize_repo_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return normalize_repo_part(value, "repo_name")

    @field_validator("events")
    @classmethod
    def _normalize_events(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        if value is None:
            return None
        try:
            return normalize_github_events(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    @field_validator("path_filters")
    @classmethod
    def _normalize_path_filters(cls, value: Optional[list[str]]) -> Optional[list[str]]:
        return normalize_path_filters(value)

    @field_validator("branch_filter", "author_filter", "installation_id")
    @classmethod
    def _normalize_optional_string(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("trigger_criteria")
    @classmethod
    def _validate_trigger_criteria(cls, value: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("trigger_criteria must be an object")
        # The GitHub trigger ships a dedicated PR-submitted envelope today.
        # When ``event`` is set, route through the GitHub-specific validator;
        # otherwise fall back to the shared envelope so JSONPath-style rules
        # continue to round-trip cleanly.
        if str(value.get("event") or "").strip().lower() == "pull_request":
            try:
                return validate_pr_criteria(value)
            except ValueError as exc:
                raise ValueError(f"invalid_pr_criteria: {exc}") from exc
        try:
            return validate_criteria(value)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc


class GitHubTriggerRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    auth_method: str
    repo_owner: str
    repo_name: str
    installation_id: Optional[str] = None
    has_pat_token: bool
    pat_token_preview: Optional[str] = None
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


class GitHubConnectionCheckResponse(BaseModel):
    success: bool
    ok: bool
    status: str
    status_code: Optional[int] = None
    detail: Optional[str] = None
    message: Optional[str] = None
    error: Optional[str] = None
    repository: Optional[str] = None
    checked_at: datetime


class GitHubCriteriaTestRequest(BaseModel):
    """Body for the unsaved-criteria dry-run endpoint."""

    criteria: dict[str, Any] = Field(..., description="Candidate trigger_criteria envelope")
    payload: dict[str, Any] = Field(..., description="Sample GitHub webhook payload")


class GitHubCriteriaPayloadRequest(BaseModel):
    """Body for the saved-trigger dry-run endpoint."""

    payload: dict[str, Any] = Field(..., description="Sample GitHub webhook payload")


class GitHubCriteriaTestResponse(BaseModel):
    matched: bool
    reason: str


class GitHubConnectionTestRequest(BaseModel):
    auth_method: str = Field(default="pat", max_length=20)
    repo_owner: str = Field(..., min_length=1, max_length=100)
    repo_name: str = Field(..., min_length=1, max_length=100)
    installation_id: Optional[str] = Field(default=None, max_length=64)
    pat_token: Optional[str] = Field(default=None, min_length=1, max_length=500)

    @field_validator("auth_method")
    @classmethod
    def _normalize_auth_method(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"pat", "app"}:
            raise ValueError("auth_method must be one of: pat, app")
        return normalized

    @field_validator("repo_owner")
    @classmethod
    def _normalize_owner(cls, value: str) -> str:
        return normalize_repo_part(value, "repo_owner")

    @field_validator("repo_name")
    @classmethod
    def _normalize_repo_name(cls, value: str) -> str:
        return normalize_repo_part(value, "repo_name")

    @field_validator("installation_id")
    @classmethod
    def _normalize_installation_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


def _can_access(ctx: TenantContext, tenant_id: Optional[str]) -> bool:
    if hasattr(ctx, "can_access_resource"):
        return ctx.can_access_resource(tenant_id)
    return tenant_id == getattr(ctx, "tenant_id", None)


def _tenant_query(ctx: TenantContext, db: Session):
    query = db.query(GitHubChannelInstance)
    if hasattr(ctx, "filter_by_tenant"):
        return ctx.filter_by_tenant(query, GitHubChannelInstance.tenant_id)
    return query.filter(GitHubChannelInstance.tenant_id == getattr(ctx, "tenant_id", None))


def _load_github_trigger(db: Session, ctx: TenantContext, trigger_id: int) -> GitHubChannelInstance:
    instance = db.query(GitHubChannelInstance).filter(GitHubChannelInstance.id == trigger_id).first()
    if instance is None or not _can_access(ctx, instance.tenant_id):
        raise HTTPException(status_code=404, detail="GitHub trigger not found")
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


def _inbound_url(instance: GitHubChannelInstance) -> str:
    return f"/api/triggers/github/{instance.id}/inbound"


def _to_read(db: Session, instance: GitHubChannelInstance) -> GitHubTriggerRead:
    # TODO(v0.7.0 perf): per-call query for auto_flow lookup is acceptable for
    # current trigger volumes; optimize via a JOIN on FlowTriggerBinding for
    # list endpoints when N+1 becomes measurable (architect §6.4).
    from services.flow_binding_service import find_system_managed_flow_for_trigger

    auto_flow = find_system_managed_flow_for_trigger(
        db,
        tenant_id=instance.tenant_id,
        trigger_kind="github",
        trigger_instance_id=instance.id,
    )
    return GitHubTriggerRead(
        id=instance.id,
        tenant_id=instance.tenant_id,
        integration_name=instance.integration_name,
        auth_method=instance.auth_method or "pat",
        repo_owner=instance.repo_owner,
        repo_name=instance.repo_name,
        installation_id=instance.installation_id,
        has_pat_token=bool(instance.pat_token_encrypted),
        pat_token_preview=instance.pat_token_preview,
        webhook_secret_preview=instance.webhook_secret_preview,
        events=normalize_github_events(instance.events),
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


async def _github_get_repo(pat_token: str, repo_owner: str, repo_name: str) -> tuple[int, str]:
    url = f"https://api.github.com/repos/{repo_owner}/{repo_name}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {pat_token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "tsushin-github-trigger",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url, headers=headers)
    return response.status_code, response.text


async def _check_repo_connection(
    *,
    pat_token: Optional[str],
    repo_owner: str,
    repo_name: str,
    checked_at: datetime,
) -> GitHubConnectionCheckResponse:
    repository = f"{repo_owner}/{repo_name}"
    if not pat_token:
        return GitHubConnectionCheckResponse(
            success=False,
            ok=False,
            status="skipped",
            detail="PAT token is not configured",
            error="PAT token is not configured",
            repository=repository,
            checked_at=checked_at,
        )

    try:
        status_code, response_text = await _github_get_repo(pat_token, repo_owner, repo_name)
    except Exception as exc:
        detail = f"GitHub connection check failed: {type(exc).__name__}"
        return GitHubConnectionCheckResponse(
            success=False,
            ok=False,
            status="error",
            detail=detail,
            error=detail,
            repository=repository,
            checked_at=checked_at,
        )

    if status_code == 200:
        return GitHubConnectionCheckResponse(
            success=True,
            ok=True,
            status="ok",
            status_code=status_code,
            message=f"Connected to {repository}.",
            repository=repository,
            checked_at=checked_at,
        )

    detail = response_text[:500] if response_text else f"GitHub returned HTTP {status_code}"
    return GitHubConnectionCheckResponse(
        success=False,
        ok=False,
        status="error",
        status_code=status_code,
        detail=detail,
        error=detail,
        repository=repository,
        checked_at=checked_at,
    )


@router.get("", response_model=list[GitHubTriggerRead])
def list_github_triggers(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[GitHubTriggerRead]:
    rows = _tenant_query(ctx, db).order_by(
        GitHubChannelInstance.created_at.desc(),
        GitHubChannelInstance.id.desc(),
    ).all()
    return [_to_read(db, row) for row in rows]


@router.post("", response_model=GitHubTriggerRead, status_code=status.HTTP_201_CREATED)
def create_github_trigger(
    payload: GitHubTriggerCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitHubTriggerRead:
    tenant_id = ctx.tenant_id
    if not tenant_id:
        raise HTTPException(status_code=403, detail="Tenant context required")
    if payload.default_agent_id is not None:
        _load_active_agent(db, tenant_id, payload.default_agent_id)

    webhook_secret = payload.webhook_secret or generate_webhook_secret()
    instance = GitHubChannelInstance(
        tenant_id=tenant_id,
        integration_name=payload.integration_name,
        auth_method=payload.auth_method,
        repo_owner=payload.repo_owner,
        repo_name=payload.repo_name,
        installation_id=payload.installation_id,
        pat_token_encrypted=encrypt_pat_token(db, tenant_id, payload.pat_token) if payload.pat_token else None,
        pat_token_preview=preview_secret(payload.pat_token) if payload.pat_token else None,
        webhook_secret_encrypted=encrypt_webhook_secret(db, tenant_id, webhook_secret),
        webhook_secret_preview=preview_secret(webhook_secret),
        events=normalize_github_events(payload.events),
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
    logger.info("Created GitHub trigger %s for tenant %s", instance.id, tenant_id)

    # v0.7.0 Wave 4 — auto-generate the system-managed Flow for this trigger.
    try:
        from config.feature_flags import flows_auto_generation_enabled
        from services.flow_binding_service import ensure_system_managed_flow_for_trigger

        if flows_auto_generation_enabled():
            ensure_system_managed_flow_for_trigger(
                db,
                tenant_id=tenant_id,
                trigger_kind="github",
                trigger_instance_id=instance.id,
                default_agent_id=instance.default_agent_id,
                notification_recipient=payload.notification_recipient,
                notification_enabled=payload.notification_enabled,
            )
            db.commit()
    except Exception:
        logger.exception("Auto-flow generation failed for github trigger %s; trigger persists", instance.id)
        db.rollback()

    return _to_read(db, instance)


@router.post("/test-connection", response_model=GitHubConnectionCheckResponse)
async def test_github_connection(
    payload: GitHubConnectionTestRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubConnectionCheckResponse:
    del ctx, db
    if payload.auth_method == "app":
        return GitHubConnectionCheckResponse(
            success=False,
            ok=False,
            status="skipped",
            detail="GitHub App checks require a saved installation",
            error="GitHub App checks require a saved installation",
            repository=f"{payload.repo_owner}/{payload.repo_name}",
            checked_at=datetime.utcnow(),
        )
    return await _check_repo_connection(
        pat_token=payload.pat_token,
        repo_owner=payload.repo_owner,
        repo_name=payload.repo_name,
        checked_at=datetime.utcnow(),
    )


@router.post("/test-criteria", response_model=GitHubCriteriaTestResponse)
def dry_run_github_pr_criteria_unsaved(
    payload: GitHubCriteriaTestRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubCriteriaTestResponse:
    """Dry-run a candidate criteria envelope against a sample webhook payload.

    Used by the trigger wizard before the row exists, so it doesn't persist
    anything. Validation errors return a 400 with ``invalid_pr_criteria``.
    """
    del ctx, db
    try:
        validated = validate_pr_criteria(payload.criteria)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_pr_criteria: {exc}") from exc
    matched, reason = evaluate_pr_criteria(payload.payload, validated)
    return GitHubCriteriaTestResponse(matched=matched, reason=reason)


@router.post("/{trigger_id}/test-criteria", response_model=GitHubCriteriaTestResponse)
def dry_run_github_pr_criteria_saved(
    trigger_id: int,
    payload: GitHubCriteriaPayloadRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubCriteriaTestResponse:
    """Dry-run the saved trigger's criteria envelope against a sample payload.

    Returns a 409 if the saved row has no ``trigger_criteria`` configured (so
    callers don't accidentally interpret a no-op envelope as "matches anything").
    """
    instance = _load_github_trigger(db, ctx, trigger_id)
    criteria = instance.trigger_criteria
    if not criteria:
        raise HTTPException(status_code=409, detail="trigger_criteria not configured")
    if not isinstance(criteria, dict):
        raise HTTPException(
            status_code=409,
            detail="trigger_criteria is not an object — cannot dry-run",
        )
    # The dry-run path is PR-specific. If the saved envelope is a different
    # shape (legacy JSONPath-style criteria, no `event` key, or an
    # unsupported event), reject with a clear 409 instead of silently
    # coercing to a PR envelope (which `validate_pr_criteria` would do by
    # defaulting `event` to `pull_request` and `actions` to `["opened"]`).
    envelope_event = str(criteria.get("event") or "").strip().lower()
    if not envelope_event:
        raise HTTPException(
            status_code=409,
            detail="trigger_criteria has no 'event' field — only PR-shaped envelopes can be dry-run.",
        )
    if envelope_event != "pull_request":
        raise HTTPException(
            status_code=409,
            detail=(
                f"trigger_criteria.event='{envelope_event}' is not yet supported by the dry-run endpoint "
                "(only 'pull_request' envelopes can be dry-run today)."
            ),
        )
    try:
        validated = validate_pr_criteria(criteria)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid_pr_criteria: {exc}") from exc
    matched, reason = evaluate_pr_criteria(payload.payload, validated)
    return GitHubCriteriaTestResponse(matched=matched, reason=reason)


@router.get("/{trigger_id}", response_model=GitHubTriggerRead)
def get_github_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubTriggerRead:
    return _to_read(db, _load_github_trigger(db, ctx, trigger_id))


@router.patch("/{trigger_id}", response_model=GitHubTriggerRead)
def update_github_trigger(
    trigger_id: int,
    payload: GitHubTriggerUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitHubTriggerRead:
    instance = _load_github_trigger(db, ctx, trigger_id)
    data = payload.model_dump(exclude_unset=True)

    if "default_agent_id" in data:
        if data["default_agent_id"] is not None:
            _load_active_agent(db, instance.tenant_id, data["default_agent_id"])
        instance.default_agent_id = data["default_agent_id"]
    for field_name in ("integration_name", "auth_method", "repo_owner", "repo_name"):
        if field_name in data and data[field_name] is not None:
            setattr(instance, field_name, data[field_name])
    if "installation_id" in data:
        instance.installation_id = data["installation_id"]
    if "pat_token" in data and data["pat_token"]:
        instance.pat_token_encrypted = encrypt_pat_token(db, instance.tenant_id, data["pat_token"])
        instance.pat_token_preview = preview_secret(data["pat_token"])
        instance.health_status = "unknown"
        instance.health_status_reason = None
    if "webhook_secret" in data and data["webhook_secret"]:
        instance.webhook_secret_encrypted = encrypt_webhook_secret(db, instance.tenant_id, data["webhook_secret"])
        instance.webhook_secret_preview = preview_secret(data["webhook_secret"])
    if "events" in data and data["events"] is not None:
        instance.events = normalize_github_events(data["events"])
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
def delete_github_trigger(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    instance = _load_github_trigger(db, ctx, trigger_id)
    db.delete(instance)
    db.commit()
    return None


@router.post("/{trigger_id}/check-connection", response_model=GitHubConnectionCheckResponse)
async def check_github_connection(
    trigger_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubConnectionCheckResponse:
    instance = _load_github_trigger(db, ctx, trigger_id)
    checked_at = datetime.utcnow()
    if not instance.pat_token_encrypted:
        instance.health_status = "unknown"
        instance.health_status_reason = "PAT token is not configured"
        instance.last_health_check = checked_at
        db.commit()
        return GitHubConnectionCheckResponse(
            success=False,
            ok=False,
            status="skipped",
            detail="PAT token is not configured",
            error="PAT token is not configured",
            repository=f"{instance.repo_owner}/{instance.repo_name}",
            checked_at=checked_at,
        )

    try:
        pat_token = decrypt_pat_token(db, instance.tenant_id, instance.pat_token_encrypted)
        status_code, response_text = await _github_get_repo(
            pat_token,
            instance.repo_owner,
            instance.repo_name,
        )
    except Exception as exc:
        instance.health_status = "unhealthy"
        instance.health_status_reason = f"GitHub connection check failed: {type(exc).__name__}"
        instance.last_health_check = checked_at
        db.commit()
        return GitHubConnectionCheckResponse(
            success=False,
            ok=False,
            status="error",
            detail=instance.health_status_reason,
            error=instance.health_status_reason,
            repository=f"{instance.repo_owner}/{instance.repo_name}",
            checked_at=checked_at,
        )

    if status_code == 200:
        instance.health_status = "healthy"
        instance.health_status_reason = None
        ok = True
        response_status = "ok"
        detail = None
    else:
        instance.health_status = "unhealthy"
        instance.health_status_reason = f"GitHub returned HTTP {status_code}"
        ok = False
        response_status = "error"
        detail = response_text[:500] if response_text else instance.health_status_reason

    instance.last_health_check = checked_at
    db.commit()
    return GitHubConnectionCheckResponse(
        success=ok,
        ok=ok,
        status=response_status,
        status_code=status_code,
        detail=detail,
        message=f"Connected to {instance.repo_owner}/{instance.repo_name}." if ok else None,
        error=None if ok else detail,
        repository=f"{instance.repo_owner}/{instance.repo_name}",
        checked_at=checked_at,
    )
