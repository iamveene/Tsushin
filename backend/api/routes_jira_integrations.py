"""Jira Tool API integration CRUD and connection-test endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from api.routes_jira_triggers import JiraTestQueryResponse, _run_test_query
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from channels.jira.utils import normalize_jira_site_url
from db import get_db
from models import JiraChannelInstance, JiraIntegration
from services.jira_integration_service import (
    decrypt_jira_token,
    encrypt_jira_token,
    load_jira_integration,
    normalize_optional,
    token_preview,
)


router = APIRouter(
    prefix="/api/hub/jira-integrations",
    tags=["Jira Tool API Integrations"],
    redirect_slashes=False,
)

_MAX_SAMPLE_SIZE = 10

# Provider modes for Jira integrations.
# 'programmatic' = REST API + token (shipped). 'agentic' = Atlassian Remote
# MCP (OAuth 2.1) — UI exposes the option as "coming soon"; API rejects it.
_VALID_PROVIDER_MODES = {"programmatic", "agentic"}
_DEFAULT_PROVIDER_MODE = "programmatic"


def _validate_provider_mode(value: Optional[str]) -> str:
    """Normalize and validate provider_mode. Reject 'agentic' until shipped."""
    mode = (value or _DEFAULT_PROVIDER_MODE).strip().lower()
    if mode not in _VALID_PROVIDER_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider_mode '{mode}'. Allowed: {sorted(_VALID_PROVIDER_MODES)}.",
        )
    if mode == "agentic":
        raise HTTPException(
            status_code=400,
            detail="agentic_mode_not_yet_supported",
        )
    return mode


class JiraIntegrationCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    site_url: str = Field(..., min_length=1, max_length=500)
    project_key: Optional[str] = Field(default=None, max_length=64)
    auth_email: str = Field(..., min_length=1, max_length=255)
    api_token: str = Field(..., min_length=1, max_length=4096)
    is_active: bool = True
    provider_mode: Optional[str] = Field(default=_DEFAULT_PROVIDER_MODE, max_length=16)

    @field_validator("integration_name", "auth_email", "api_token")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("site_url")
    @classmethod
    def _normalize_site_url(cls, value: str) -> str:
        return normalize_jira_site_url(value)

    @field_validator("project_key")
    @classmethod
    def _normalize_project_key(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value, upper=True)


class JiraIntegrationUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    site_url: Optional[str] = Field(default=None, min_length=1, max_length=500)
    project_key: Optional[str] = Field(default=None, max_length=64)
    auth_email: Optional[str] = Field(default=None, max_length=255)
    api_token: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    is_active: Optional[bool] = None
    provider_mode: Optional[str] = Field(default=None, max_length=16)

    @field_validator("integration_name", "auth_email", "api_token")
    @classmethod
    def _strip_optional(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)

    @field_validator("site_url")
    @classmethod
    def _normalize_site_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        return normalize_jira_site_url(value)

    @field_validator("project_key")
    @classmethod
    def _normalize_project_key(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value, upper=True)


class JiraIntegrationRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    name: str
    site_url: str
    project_key: Optional[str] = None
    auth_email: Optional[str] = None
    api_token_preview: Optional[str] = None
    is_active: bool
    provider_mode: str = _DEFAULT_PROVIDER_MODE
    health_status: Optional[str] = None
    health_status_reason: Optional[str] = None
    last_health_check: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_tested_at: Optional[datetime] = None
    trigger_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


class JiraIntegrationTestQueryRequest(BaseModel):
    jira_integration_id: Optional[int] = Field(default=None, ge=1)
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
        return normalize_jira_site_url(value)

    @field_validator("jql", "auth_email", "api_token")
    @classmethod
    def _normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)


def _require_tenant(ctx: TenantContext) -> str:
    if not getattr(ctx, "tenant_id", None):
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return ctx.tenant_id


def _load_integration_or_404(db: Session, tenant_id: str, integration_id: int) -> JiraIntegration:
    integration = load_jira_integration(db, tenant_id=tenant_id, integration_id=integration_id)
    if integration is None:
        raise HTTPException(status_code=404, detail="Jira integration not found")
    return integration


def _health_reason(detail: Any) -> str:
    if isinstance(detail, str):
        return detail[:500]
    if isinstance(detail, dict):
        message = detail.get("message")
        status_code = detail.get("status_code")
        if message and status_code:
            return f"{message} ({status_code})"[:500]
        if message:
            return str(message)[:500]
    return str(detail)[:500]


def _to_read(db: Session, integration: JiraIntegration) -> JiraIntegrationRead:
    trigger_count = db.query(JiraChannelInstance.id).filter(
        JiraChannelInstance.tenant_id == integration.tenant_id,
        JiraChannelInstance.jira_integration_id == integration.id,
    ).count()
    display_name = integration.display_name or integration.name
    return JiraIntegrationRead(
        id=integration.id,
        tenant_id=integration.tenant_id,
        integration_name=display_name,
        name=display_name,
        site_url=integration.site_url,
        project_key=integration.project_key,
        auth_email=integration.auth_email,
        api_token_preview=integration.api_token_preview,
        is_active=bool(integration.is_active),
        provider_mode=getattr(integration, "provider_mode", None) or _DEFAULT_PROVIDER_MODE,
        health_status=integration.health_status or "unknown",
        health_status_reason=integration.health_status_reason,
        last_health_check=integration.last_health_check,
        last_test_status=integration.health_status,
        last_tested_at=integration.last_health_check,
        trigger_count=trigger_count,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


def _stored_api_token(db: Session, integration: JiraIntegration) -> Optional[str]:
    try:
        return decrypt_jira_token(db, integration.tenant_id, integration.api_token_encrypted)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Could not decrypt Jira API token") from exc


async def _run_stored_test_query(
    db: Session,
    integration: JiraIntegration,
    payload: JiraIntegrationTestQueryRequest,
) -> JiraTestQueryResponse:
    if not payload.jql:
        raise HTTPException(status_code=400, detail="jql is required")
    try:
        response = await _run_test_query(
            site_url=payload.site_url or integration.site_url,
            jql=payload.jql,
            auth_email=payload.auth_email if payload.auth_email is not None else integration.auth_email,
            api_token=payload.api_token if payload.api_token is not None else _stored_api_token(db, integration),
            max_results=payload.max_results,
        )
    except HTTPException as exc:
        integration.last_health_check = datetime.utcnow()
        integration.health_status = "unavailable"
        integration.health_status_reason = _health_reason(exc.detail)
        db.add(integration)
        db.commit()
        raise

    integration.last_health_check = datetime.utcnow()
    integration.health_status = "healthy"
    integration.health_status_reason = None
    db.add(integration)
    db.commit()
    return response


@router.get("", response_model=list[JiraIntegrationRead])
def list_jira_integrations(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[JiraIntegrationRead]:
    tenant_id = _require_tenant(ctx)
    rows = db.query(JiraIntegration).filter(
        JiraIntegration.tenant_id == tenant_id,
        JiraIntegration.type == "jira",
    ).order_by(JiraIntegration.created_at.desc(), JiraIntegration.id.desc()).all()
    return [_to_read(db, row) for row in rows]


@router.post("", response_model=JiraIntegrationRead, status_code=status.HTTP_201_CREATED)
def create_jira_integration(
    payload: JiraIntegrationCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> JiraIntegrationRead:
    tenant_id = _require_tenant(ctx)
    provider_mode = _validate_provider_mode(payload.provider_mode)
    integration = JiraIntegration(
        type="jira",
        name=payload.integration_name,
        display_name=payload.integration_name,
        tenant_id=tenant_id,
        is_active=payload.is_active,
        health_status="unknown",
        site_url=payload.site_url,
        project_key=payload.project_key,
        auth_email=payload.auth_email,
        api_token_encrypted=encrypt_jira_token(db, tenant_id, payload.api_token),
        api_token_preview=token_preview(payload.api_token),
        provider_mode=provider_mode,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return _to_read(db, integration)


@router.patch("/{integration_id}", response_model=JiraIntegrationRead)
def update_jira_integration(
    integration_id: int,
    payload: JiraIntegrationUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> JiraIntegrationRead:
    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    data = payload.model_dump(exclude_unset=True)
    if "integration_name" in data and data["integration_name"] is not None:
        integration.name = data["integration_name"]
        integration.display_name = data["integration_name"]
    if "site_url" in data and data["site_url"] is not None:
        integration.site_url = data["site_url"]
    if "project_key" in data:
        integration.project_key = data["project_key"]
    if "auth_email" in data:
        integration.auth_email = data["auth_email"]
    if "api_token" in data:
        if data["api_token"] is None:
            integration.api_token_encrypted = None
            integration.api_token_preview = None
        else:
            integration.api_token_encrypted = encrypt_jira_token(db, tenant_id, data["api_token"])
            integration.api_token_preview = token_preview(data["api_token"])
            integration.health_status = "unknown"
            integration.health_status_reason = None
    if "is_active" in data and data["is_active"] is not None:
        integration.is_active = data["is_active"]
    if "provider_mode" in data and data["provider_mode"] is not None:
        integration.provider_mode = _validate_provider_mode(data["provider_mode"])
    integration.updated_at = datetime.utcnow()
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return _to_read(db, integration)


@router.delete("/{integration_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_jira_integration(
    integration_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    from models import AgentSkillIntegration

    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    in_use_trigger = db.query(JiraChannelInstance.id).filter(
        JiraChannelInstance.tenant_id == tenant_id,
        JiraChannelInstance.jira_integration_id == integration.id,
    ).first()
    if in_use_trigger is not None:
        raise HTTPException(status_code=409, detail="Jira integration is used by one or more triggers")
    in_use_skill = db.query(AgentSkillIntegration.id).filter(
        AgentSkillIntegration.integration_id == integration.id,
        AgentSkillIntegration.skill_type == "ticket_management",
    ).first()
    if in_use_skill is not None:
        raise HTTPException(
            status_code=409,
            detail="Jira integration is linked to one or more agent skills. Detach it from agents first.",
        )
    db.delete(integration)
    db.commit()
    return None


@router.post("/test-query", response_model=JiraTestQueryResponse)
async def test_jira_integration_query(
    payload: JiraIntegrationTestQueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> JiraTestQueryResponse:
    tenant_id = _require_tenant(ctx)
    if payload.jira_integration_id:
        integration = _load_integration_or_404(db, tenant_id, payload.jira_integration_id)
        return await _run_stored_test_query(db, integration, payload)
    if not payload.site_url or not payload.jql:
        raise HTTPException(status_code=400, detail="site_url and jql are required")
    return await _run_test_query(
        site_url=payload.site_url,
        jql=payload.jql,
        auth_email=payload.auth_email,
        api_token=payload.api_token,
        max_results=payload.max_results,
    )


@router.post("/{integration_id}/test-query", response_model=JiraTestQueryResponse)
async def test_saved_jira_integration_query(
    integration_id: int,
    payload: JiraIntegrationTestQueryRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> JiraTestQueryResponse:
    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    return await _run_stored_test_query(db, integration, payload)
