"""GitLab Hub integration CRUD and read-only connection-test endpoints."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from db import get_db
from hub.gitlab.gitlab_repository_service import (
    GitLabRepositoryError,
    GitLabRepositoryService,
)
from models import GitLabChannelInstance, GitLabIntegration
from services.gitlab_integration_service import (
    GITLAB_API_BASE_URL,
    encrypt_gitlab_pat,
    load_gitlab_integration,
    normalize_optional,
    normalize_project_path,
    pat_preview,
)


router = APIRouter(
    prefix="/api/hub/gitlab-integrations",
    tags=["GitLab Integrations"],
    redirect_slashes=False,
)


_VALID_PROVIDER_MODES = {"programmatic", "agentic"}
_DEFAULT_PROVIDER_MODE = "programmatic"

_GITLAB_SEGMENT_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_GITLAB_PROJECT_PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def _validate_provider_mode(value: Optional[str]) -> str:
    mode = (value or _DEFAULT_PROVIDER_MODE).strip().lower()
    if mode not in _VALID_PROVIDER_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid provider_mode '{mode}'. Allowed: {sorted(_VALID_PROVIDER_MODES)}.",
        )
    if mode == "agentic":
        raise HTTPException(status_code=400, detail="agentic_mode_not_yet_supported")
    return mode


def _validate_gitlab_segment(value: Optional[str], *, field_name: str) -> Optional[str]:
    normalized = normalize_optional(value)
    if normalized is None:
        return None
    if "/" in normalized or not _GITLAB_SEGMENT_RE.match(normalized):
        raise ValueError(f"{field_name} must match [A-Za-z0-9._-]+")
    return normalized


def _validate_gitlab_project_path(value: Optional[str], *, field_name: str) -> Optional[str]:
    normalized = normalize_project_path(value)
    if normalized is None:
        return None
    if not _GITLAB_PROJECT_PATH_RE.match(normalized):
        raise ValueError(f"{field_name} must match [A-Za-z0-9._/-]+")
    if any(not part or not _GITLAB_SEGMENT_RE.match(part) for part in normalized.split("/")):
        raise ValueError(f"{field_name} must contain slash-separated [A-Za-z0-9._-]+ segments")
    return normalized


def _project_path_from_parts(
    *,
    namespace: Optional[str],
    project: Optional[str],
    project_path: Optional[str],
) -> Optional[str]:
    normalized_path = _validate_gitlab_project_path(project_path, field_name="project_path")
    if normalized_path:
        return normalized_path
    namespace = _validate_gitlab_project_path(namespace, field_name="namespace")
    project = _validate_gitlab_segment(project, field_name="project")
    if namespace and project:
        return f"{namespace}/{project}"
    return None


class GitLabIntegrationCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    pat_token: str = Field(..., min_length=1, max_length=4096)
    default_namespace: Optional[str] = Field(default=None, max_length=255)
    default_project: Optional[str] = Field(default=None, max_length=255)
    default_project_path: Optional[str] = Field(default=None, max_length=500)
    is_active: bool = True
    provider_mode: Optional[str] = Field(default=_DEFAULT_PROVIDER_MODE, max_length=16)

    @field_validator("integration_name", "pat_token")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("default_namespace")
    @classmethod
    def _validate_namespace(cls, value: Optional[str]) -> Optional[str]:
        return _validate_gitlab_project_path(value, field_name="default_namespace")

    @field_validator("default_project")
    @classmethod
    def _validate_project(cls, value: Optional[str]) -> Optional[str]:
        return _validate_gitlab_segment(value, field_name="default_project")

    @field_validator("default_project_path")
    @classmethod
    def _validate_project_path(cls, value: Optional[str]) -> Optional[str]:
        return _validate_gitlab_project_path(value, field_name="default_project_path")


class GitLabIntegrationUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    pat_token: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    default_namespace: Optional[str] = Field(default=None, max_length=255)
    default_project: Optional[str] = Field(default=None, max_length=255)
    default_project_path: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = None
    provider_mode: Optional[str] = Field(default=None, max_length=16)

    @field_validator("integration_name", "pat_token")
    @classmethod
    def _strip_optional(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)

    @field_validator("default_namespace")
    @classmethod
    def _validate_namespace(cls, value: Optional[str]) -> Optional[str]:
        return _validate_gitlab_project_path(value, field_name="default_namespace")

    @field_validator("default_project")
    @classmethod
    def _validate_project(cls, value: Optional[str]) -> Optional[str]:
        return _validate_gitlab_segment(value, field_name="default_project")

    @field_validator("default_project_path")
    @classmethod
    def _validate_project_path(cls, value: Optional[str]) -> Optional[str]:
        return _validate_gitlab_project_path(value, field_name="default_project_path")


class GitLabIntegrationRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    name: str
    provider: str = "gitlab"
    auth_method: str = "pat"
    pat_token_preview: Optional[str] = None
    default_namespace: Optional[str] = None
    default_project: Optional[str] = None
    default_project_path: Optional[str] = None
    is_active: bool
    provider_mode: str = _DEFAULT_PROVIDER_MODE
    health_status: Optional[str] = None
    health_status_reason: Optional[str] = None
    last_health_check: Optional[datetime] = None
    last_test_status: Optional[str] = None
    last_tested_at: Optional[datetime] = None
    trigger_count: int = 0
    skill_attached_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


class GitLabTestConnectionRequest(BaseModel):
    gitlab_integration_id: Optional[int] = Field(default=None, ge=1)
    pat_token: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    namespace: Optional[str] = Field(default=None, max_length=255)
    project: Optional[str] = Field(default=None, max_length=255)
    project_path: Optional[str] = Field(default=None, max_length=500)

    @field_validator("pat_token")
    @classmethod
    def _normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)

    @field_validator("namespace")
    @classmethod
    def _validate_namespace(cls, value: Optional[str]) -> Optional[str]:
        return _validate_gitlab_project_path(value, field_name="namespace")

    @field_validator("project")
    @classmethod
    def _validate_project(cls, value: Optional[str]) -> Optional[str]:
        return _validate_gitlab_segment(value, field_name="project")

    @field_validator("project_path")
    @classmethod
    def _validate_project_path(cls, value: Optional[str]) -> Optional[str]:
        return _validate_gitlab_project_path(value, field_name="project_path")


class GitLabTestConnectionResponse(BaseModel):
    success: bool
    status_code: Optional[int] = None
    message: str
    project_path: Optional[str] = None
    project_web_url: Optional[str] = None
    error: Optional[str] = None


def _require_tenant(ctx: TenantContext) -> str:
    if not getattr(ctx, "tenant_id", None):
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return ctx.tenant_id


def _load_integration_or_404(
    db: Session, tenant_id: str, integration_id: int
) -> GitLabIntegration:
    integration = load_gitlab_integration(
        db, tenant_id=tenant_id, integration_id=integration_id
    )
    if integration is None:
        raise HTTPException(status_code=404, detail="GitLab integration not found")
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


def _to_read(db: Session, integration: GitLabIntegration) -> GitLabIntegrationRead:
    from models import AgentSkillIntegration

    trigger_count = (
        db.query(GitLabChannelInstance.id)
        .filter(
            GitLabChannelInstance.tenant_id == integration.tenant_id,
            GitLabChannelInstance.gitlab_integration_id == integration.id,
        )
        .count()
    )
    skill_attached_count = (
        db.query(AgentSkillIntegration.id)
        .filter(
            AgentSkillIntegration.integration_id == integration.id,
            AgentSkillIntegration.skill_type == "code_repository",
        )
        .count()
    )
    display_name = integration.display_name or integration.name
    return GitLabIntegrationRead(
        id=integration.id,
        tenant_id=integration.tenant_id,
        integration_name=display_name,
        name=display_name,
        provider=integration.provider or "gitlab",
        auth_method=integration.auth_method or "pat",
        pat_token_preview=integration.pat_token_preview,
        default_namespace=integration.default_namespace,
        default_project=integration.default_project,
        default_project_path=integration.default_project_path,
        is_active=bool(integration.is_active),
        provider_mode=getattr(integration, "provider_mode", None) or _DEFAULT_PROVIDER_MODE,
        health_status=integration.health_status or "unknown",
        health_status_reason=integration.health_status_reason,
        last_health_check=integration.last_health_check,
        last_test_status=integration.health_status,
        last_tested_at=integration.last_health_check,
        trigger_count=trigger_count,
        skill_attached_count=skill_attached_count,
        created_at=integration.created_at,
        updated_at=integration.updated_at,
    )


def _owner_repo_from_project_path(project_path: str) -> tuple[str, str]:
    normalized = _validate_gitlab_project_path(project_path, field_name="project_path")
    if not normalized or "/" not in normalized:
        raise HTTPException(status_code=400, detail="project_path must include namespace/project")
    namespace, project = normalized.rsplit("/", 1)
    return namespace, project


async def _run_test_connection(
    *,
    db: Session,
    tenant_id: str,
    integration: Optional[GitLabIntegration],
    pat_token: Optional[str],
    project_path: str,
) -> GitLabTestConnectionResponse:
    if integration is not None:
        owner, repo = _owner_repo_from_project_path(project_path)
        try:
            service = GitLabRepositoryService(db, tenant_id, integration.id)
            data = await service.get_repository(owner, repo)
        except GitLabRepositoryError as exc:
            integration.last_health_check = datetime.utcnow()
            integration.health_status = "unavailable"
            integration.health_status_reason = _health_reason(str(exc))
            db.add(integration)
            db.commit()
            return GitLabTestConnectionResponse(
                success=False,
                status_code=exc.status_code,
                message=str(exc),
                error="gitlab_api_error",
            )
        integration.last_health_check = datetime.utcnow()
        integration.health_status = "healthy"
        integration.health_status_reason = None
        db.add(integration)
        db.commit()
        return GitLabTestConnectionResponse(
            success=True,
            status_code=200,
            message="Connection successful.",
            project_path=data.get("path_with_namespace"),
            project_web_url=data.get("web_url"),
        )

    if not pat_token:
        raise HTTPException(
            status_code=400,
            detail="pat_token is required when gitlab_integration_id is not provided",
        )

    import httpx

    url = f"{GITLAB_API_BASE_URL.rstrip('/')}/projects/{quote(project_path, safe='')}"
    headers = {
        "Accept": "application/json",
        "PRIVATE-TOKEN": pat_token,
    }
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        return GitLabTestConnectionResponse(
            success=False,
            message=f"Network error talking to GitLab: {exc}",
            error="network_error",
        )
    if 200 <= response.status_code < 300:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return GitLabTestConnectionResponse(
            success=True,
            status_code=response.status_code,
            message="Connection successful.",
            project_path=payload.get("path_with_namespace") if isinstance(payload, dict) else None,
            project_web_url=payload.get("web_url") if isinstance(payload, dict) else None,
        )
    try:
        body = response.json()
        msg = body.get("message") if isinstance(body, dict) else None
    except ValueError:
        msg = None
    return GitLabTestConnectionResponse(
        success=False,
        status_code=response.status_code,
        message=msg or f"HTTP {response.status_code}",
        error="gitlab_api_error",
    )


@router.get("", response_model=list[GitLabIntegrationRead])
def list_gitlab_integrations(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[GitLabIntegrationRead]:
    tenant_id = _require_tenant(ctx)
    rows = (
        db.query(GitLabIntegration)
        .filter(
            GitLabIntegration.tenant_id == tenant_id,
            GitLabIntegration.type == "gitlab",
        )
        .order_by(GitLabIntegration.created_at.desc(), GitLabIntegration.id.desc())
        .all()
    )
    return [_to_read(db, row) for row in rows]


@router.get("/{integration_id}", response_model=GitLabIntegrationRead)
def get_gitlab_integration(
    integration_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitLabIntegrationRead:
    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    return _to_read(db, integration)


@router.post("", response_model=GitLabIntegrationRead, status_code=status.HTTP_201_CREATED)
def create_gitlab_integration(
    payload: GitLabIntegrationCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitLabIntegrationRead:
    tenant_id = _require_tenant(ctx)
    provider_mode = _validate_provider_mode(payload.provider_mode)
    project_path = _project_path_from_parts(
        namespace=payload.default_namespace,
        project=payload.default_project,
        project_path=payload.default_project_path,
    )
    integration = GitLabIntegration(
        type="gitlab",
        name=payload.integration_name,
        display_name=payload.integration_name,
        tenant_id=tenant_id,
        is_active=payload.is_active,
        health_status="unknown",
        provider="gitlab",
        auth_method="pat",
        pat_token_encrypted=encrypt_gitlab_pat(db, tenant_id, payload.pat_token),
        pat_token_preview=pat_preview(payload.pat_token),
        default_namespace=payload.default_namespace,
        default_project=payload.default_project,
        default_project_path=project_path,
        provider_mode=provider_mode,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return _to_read(db, integration)


@router.patch("/{integration_id}", response_model=GitLabIntegrationRead)
def update_gitlab_integration(
    integration_id: int,
    payload: GitLabIntegrationUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitLabIntegrationRead:
    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    data = payload.model_dump(exclude_unset=True)
    if "integration_name" in data and data["integration_name"] is not None:
        integration.name = data["integration_name"]
        integration.display_name = data["integration_name"]
    if "default_namespace" in data:
        integration.default_namespace = data["default_namespace"]
    if "default_project" in data:
        integration.default_project = data["default_project"]
    if any(key in data for key in ("default_namespace", "default_project", "default_project_path")):
        namespace = data.get("default_namespace", integration.default_namespace)
        project = data.get("default_project", integration.default_project)
        project_path = data["default_project_path"] if "default_project_path" in data else None
        integration.default_project_path = _project_path_from_parts(
            namespace=namespace,
            project=project,
            project_path=project_path,
        )
    if "pat_token" in data:
        if data["pat_token"] is None:
            integration.pat_token_encrypted = None
            integration.pat_token_preview = None
        else:
            integration.pat_token_encrypted = encrypt_gitlab_pat(
                db, tenant_id, data["pat_token"]
            )
            integration.pat_token_preview = pat_preview(data["pat_token"])
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
def delete_gitlab_integration(
    integration_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    from models import AgentSkillIntegration

    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    in_use_trigger = (
        db.query(GitLabChannelInstance.id)
        .filter(
            GitLabChannelInstance.tenant_id == tenant_id,
            GitLabChannelInstance.gitlab_integration_id == integration.id,
        )
        .first()
    )
    if in_use_trigger is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "GitLab integration is referenced by one or more triggers. "
                "Detach the triggers first."
            ),
        )
    in_use_skill = (
        db.query(AgentSkillIntegration.id)
        .filter(
            AgentSkillIntegration.integration_id == integration.id,
            AgentSkillIntegration.skill_type == "code_repository",
        )
        .first()
    )
    if in_use_skill is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "GitLab integration is linked to one or more agent skills. "
                "Detach it from agents first."
            ),
        )
    db.delete(integration)
    db.commit()
    return None


@router.post("/test-connection", response_model=GitLabTestConnectionResponse)
async def test_gitlab_connection(
    payload: GitLabTestConnectionRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitLabTestConnectionResponse:
    tenant_id = _require_tenant(ctx)
    integration: Optional[GitLabIntegration] = None
    if payload.gitlab_integration_id:
        integration = _load_integration_or_404(db, tenant_id, payload.gitlab_integration_id)
        project_path = _project_path_from_parts(
            namespace=payload.namespace or integration.default_namespace,
            project=payload.project or integration.default_project,
            project_path=payload.project_path or integration.default_project_path,
        )
    else:
        project_path = _project_path_from_parts(
            namespace=payload.namespace,
            project=payload.project,
            project_path=payload.project_path,
        )
    if not project_path:
        raise HTTPException(
            status_code=400,
            detail="project_path or namespace/project is required",
        )
    return await _run_test_connection(
        db=db,
        tenant_id=tenant_id,
        integration=integration,
        pat_token=None if integration is not None else payload.pat_token,
        project_path=project_path,
    )


@router.post("/{integration_id}/test-connection", response_model=GitLabTestConnectionResponse)
async def test_saved_gitlab_connection(
    integration_id: int,
    payload: GitLabTestConnectionRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitLabTestConnectionResponse:
    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    project_path = _project_path_from_parts(
        namespace=payload.namespace or integration.default_namespace,
        project=payload.project or integration.default_project,
        project_path=payload.project_path or integration.default_project_path,
    )
    if not project_path:
        raise HTTPException(
            status_code=400,
            detail="project_path or namespace/project is required",
        )
    return await _run_test_connection(
        db=db,
        tenant_id=tenant_id,
        integration=integration,
        pat_token=None,
        project_path=project_path,
    )
