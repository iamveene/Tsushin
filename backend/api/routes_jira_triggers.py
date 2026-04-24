"""Jira trigger CRUD and JQL test-query endpoints."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.trigger_criteria import validate_criteria
from db import get_db
from hub.security import TokenEncryption
from models import Agent, Contact, JiraChannelInstance
from services.encryption_key_service import get_webhook_encryption_key


logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/triggers/jira",
    tags=["Jira Triggers"],
    redirect_slashes=False,
)

_JIRA_SEARCH_TIMEOUT_SECONDS = 10.0
_MAX_SAMPLE_SIZE = 10


class JiraTriggerCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    site_url: str = Field(..., min_length=1, max_length=500)
    project_key: Optional[str] = Field(default=None, max_length=64)
    jql: str = Field(..., min_length=1, max_length=4000)
    auth_email: Optional[str] = Field(default=None, max_length=255)
    api_token: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    trigger_criteria: Optional[dict[str, Any]] = None
    poll_interval_seconds: int = Field(default=300, ge=60, le=86400)
    default_agent_id: Optional[int] = Field(default=None, ge=1)
    is_active: bool = True

    @field_validator("integration_name", "jql")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("site_url")
    @classmethod
    def _normalize_site_url(cls, value: str) -> str:
        return _normalize_site_url(value)

    @field_validator("project_key")
    @classmethod
    def _normalize_project_key(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional(value, upper=True)

    @field_validator("auth_email")
    @classmethod
    def _normalize_auth_email(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional(value)

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
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    site_url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    project_key: Optional[str] = Field(default=None, max_length=64)
    jql: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    auth_email: Optional[str] = Field(default=None, max_length=255)
    api_token: Optional[str] = Field(default=None, min_length=1, max_length=4096)
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

    @field_validator("site_url")
    @classmethod
    def _normalize_site_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_site_url(value)

    @field_validator("project_key")
    @classmethod
    def _normalize_project_key(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional(value, upper=True)

    @field_validator("auth_email")
    @classmethod
    def _normalize_auth_email(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional(value)

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
    site_url: str
    project_key: Optional[str] = None
    jql: str
    auth_email: Optional[str] = None
    api_token_preview: Optional[str] = None
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


class JiraTestQueryRequest(BaseModel):
    site_url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    jql: Optional[str] = Field(default=None, min_length=1, max_length=4000)
    auth_email: Optional[str] = Field(default=None, max_length=255)
    api_token: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    max_results: int = Field(default=3, ge=1, le=_MAX_SAMPLE_SIZE)

    @field_validator("site_url")
    @classmethod
    def _normalize_site_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return _normalize_site_url(value)

    @field_validator("jql")
    @classmethod
    def _normalize_jql(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional(value)

    @field_validator("auth_email")
    @classmethod
    def _normalize_auth_email(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_optional(value)


class JiraIssueSample(BaseModel):
    id: Optional[str] = None
    key: Optional[str] = None
    summary: Optional[str] = None
    status: Optional[str] = None
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


def _normalize_optional(value: Optional[str], *, upper: bool = False) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    return normalized.upper() if upper else normalized


def _normalize_site_url(value: str) -> str:
    normalized = value.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("site_url must be an http(s) URL")
    return normalized


def _token_preview(token: str) -> str:
    if len(token) <= 8:
        return f"{token[:2]}..."
    return f"{token[:4]}...{token[-4:]}"


def _get_encryptor(db: Session) -> TokenEncryption:
    master_key = get_webhook_encryption_key(db)
    if not master_key:
        raise HTTPException(status_code=500, detail="Server configuration error")
    return TokenEncryption(master_key.encode())


def _encrypt_token(db: Session, tenant_id: str, plaintext: str) -> str:
    return _get_encryptor(db).encrypt(plaintext, tenant_id)


def _decrypt_token(db: Session, tenant_id: str, encrypted: str) -> str:
    try:
        return _get_encryptor(db).decrypt(encrypted, tenant_id)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Could not decrypt Jira API token") from exc


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
    return JiraTriggerRead(
        id=instance.id,
        tenant_id=instance.tenant_id,
        integration_name=instance.integration_name,
        site_url=instance.site_url,
        project_key=instance.project_key,
        jql=instance.jql,
        auth_email=instance.auth_email,
        api_token_preview=instance.api_token_preview,
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

    url = f"{site_url}/rest/api/3/search"
    payload = {
        "jql": jql,
        "startAt": 0,
        "maxResults": max_results,
        "fields": ["summary", "status", "updated"],
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


def _sample_response(data: dict[str, Any]) -> JiraTestQueryResponse:
    raw_issues = data.get("issues")
    issues = raw_issues if isinstance(raw_issues, list) else []
    samples: list[JiraIssueSample] = []
    for issue in issues[:_MAX_SAMPLE_SIZE]:
        if not isinstance(issue, dict):
            continue
        fields = issue.get("fields") if isinstance(issue.get("fields"), dict) else {}
        status_value = fields.get("status")
        status_name = status_value.get("name") if isinstance(status_value, dict) else None
        samples.append(
            JiraIssueSample(
                id=str(issue.get("id")) if issue.get("id") is not None else None,
                key=str(issue.get("key")) if issue.get("key") is not None else None,
                summary=fields.get("summary") if isinstance(fields.get("summary"), str) else None,
                status=status_name if isinstance(status_name, str) else None,
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
    return _sample_response(data)


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

    encrypted_token = None
    token_preview = None
    if payload.api_token:
        encrypted_token = _encrypt_token(db, ctx.tenant_id, payload.api_token)
        token_preview = _token_preview(payload.api_token)

    instance = JiraChannelInstance(
        tenant_id=ctx.tenant_id,
        integration_name=payload.integration_name,
        site_url=payload.site_url,
        project_key=payload.project_key,
        jql=payload.jql,
        auth_email=payload.auth_email,
        api_token_encrypted=encrypted_token,
        api_token_preview=token_preview,
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
    return _to_read(db, instance)


@router.post("/test-query", response_model=JiraTestQueryResponse)
async def run_jira_test_query(
    payload: JiraTestQueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> JiraTestQueryResponse:
    if not payload.site_url or not payload.jql:
        raise HTTPException(status_code=400, detail="site_url and jql are required")
    return await _run_test_query(
        site_url=payload.site_url,
        jql=payload.jql,
        auth_email=payload.auth_email,
        api_token=payload.api_token,
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
    site_url = payload.site_url or instance.site_url
    jql = payload.jql or instance.jql
    auth_email = payload.auth_email if payload.auth_email is not None else instance.auth_email
    api_token = payload.api_token
    if api_token is None and instance.api_token_encrypted:
        api_token = _decrypt_token(db, instance.tenant_id, instance.api_token_encrypted)

    return await _run_test_query(
        site_url=site_url,
        jql=jql,
        auth_email=auth_email,
        api_token=api_token,
        max_results=payload.max_results,
    )


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
    if "integration_name" in data:
        instance.integration_name = data["integration_name"]
    if "site_url" in data:
        instance.site_url = data["site_url"]
    if "project_key" in data:
        instance.project_key = data["project_key"]
    if "jql" in data:
        instance.jql = data["jql"]
    if "auth_email" in data:
        instance.auth_email = data["auth_email"]
    if "api_token" in data:
        if data["api_token"] is None:
            instance.api_token_encrypted = None
            instance.api_token_preview = None
        else:
            instance.api_token_encrypted = _encrypt_token(db, instance.tenant_id, data["api_token"])
            instance.api_token_preview = _token_preview(data["api_token"])
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
    db.delete(instance)
    db.commit()
    return None
