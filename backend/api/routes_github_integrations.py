"""GitHub Hub integration CRUD and connection-test endpoints.

Mirrors :mod:`api.routes_jira_integrations` exactly. The PAT is encrypted
with the API-key encryption key (see
:func:`services.github_integration_service.get_github_encryptor`); a
preview is stored for the UI but the plaintext is never logged.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from auth_dependencies import TenantContext, get_tenant_context, require_permission
from db import get_db
from hub.github.github_repository_service import (
    GitHubRepositoryError,
    GitHubRepositoryService,
)
from models import GitHubChannelInstance, GitHubIntegration
from services.github_integration_service import (
    decrypt_github_pat,
    encrypt_github_pat,
    load_github_integration,
    normalize_optional,
    pat_preview,
)


router = APIRouter(
    prefix="/api/hub/github-integrations",
    tags=["GitHub Integrations"],
    redirect_slashes=False,
)


_VALID_PROVIDER_MODES = {"programmatic", "agentic"}
_DEFAULT_PROVIDER_MODE = "programmatic"

# GitHub repo-owner / repo-name validator. Matches the trigger form input.
_GITHUB_NAME_RE = re.compile(r"^[A-Za-z0-9._-]+$")


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


def _validate_github_name(value: Optional[str], *, field_name: str) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if not _GITHUB_NAME_RE.match(normalized):
        raise ValueError(
            f"{field_name} must match [A-Za-z0-9._-]+"
        )
    return normalized


class GitHubIntegrationCreate(BaseModel):
    integration_name: str = Field(..., min_length=1, max_length=100)
    pat_token: str = Field(..., min_length=1, max_length=4096)
    default_owner: Optional[str] = Field(default=None, max_length=100)
    default_repo: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = True
    provider_mode: Optional[str] = Field(default=_DEFAULT_PROVIDER_MODE, max_length=16)

    @field_validator("integration_name", "pat_token")
    @classmethod
    def _strip_required(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("value must not be empty")
        return normalized

    @field_validator("default_owner")
    @classmethod
    def _validate_owner(cls, value: Optional[str]) -> Optional[str]:
        return _validate_github_name(value, field_name="default_owner")

    @field_validator("default_repo")
    @classmethod
    def _validate_repo(cls, value: Optional[str]) -> Optional[str]:
        return _validate_github_name(value, field_name="default_repo")


class GitHubIntegrationUpdate(BaseModel):
    integration_name: Optional[str] = Field(default=None, min_length=1, max_length=100)
    pat_token: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    default_owner: Optional[str] = Field(default=None, max_length=100)
    default_repo: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None
    provider_mode: Optional[str] = Field(default=None, max_length=16)

    @field_validator("integration_name", "pat_token")
    @classmethod
    def _strip_optional(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)

    @field_validator("default_owner")
    @classmethod
    def _validate_owner(cls, value: Optional[str]) -> Optional[str]:
        return _validate_github_name(value, field_name="default_owner")

    @field_validator("default_repo")
    @classmethod
    def _validate_repo(cls, value: Optional[str]) -> Optional[str]:
        return _validate_github_name(value, field_name="default_repo")


class GitHubIntegrationRead(BaseModel):
    id: int
    tenant_id: str
    integration_name: str
    name: str
    provider: str = "github"
    auth_method: str = "pat"
    pat_token_preview: Optional[str] = None
    default_owner: Optional[str] = None
    default_repo: Optional[str] = None
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


class GitHubTestConnectionRequest(BaseModel):
    github_integration_id: Optional[int] = Field(default=None, ge=1)
    pat_token: Optional[str] = Field(default=None, min_length=1, max_length=4096)
    owner: Optional[str] = Field(default=None, max_length=100)
    repo: Optional[str] = Field(default=None, max_length=100)

    @field_validator("pat_token")
    @classmethod
    def _normalize_optional_text(cls, value: Optional[str]) -> Optional[str]:
        return normalize_optional(value)

    @field_validator("owner")
    @classmethod
    def _validate_owner(cls, value: Optional[str]) -> Optional[str]:
        return _validate_github_name(value, field_name="owner")

    @field_validator("repo")
    @classmethod
    def _validate_repo(cls, value: Optional[str]) -> Optional[str]:
        return _validate_github_name(value, field_name="repo")


class GitHubTestConnectionResponse(BaseModel):
    success: bool
    status_code: Optional[int] = None
    message: str
    repo_full_name: Optional[str] = None
    error: Optional[str] = None


def _require_tenant(ctx: TenantContext) -> str:
    if not getattr(ctx, "tenant_id", None):
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return ctx.tenant_id


def _load_integration_or_404(
    db: Session, tenant_id: str, integration_id: int
) -> GitHubIntegration:
    integration = load_github_integration(
        db, tenant_id=tenant_id, integration_id=integration_id
    )
    if integration is None:
        raise HTTPException(status_code=404, detail="GitHub integration not found")
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


def _to_read(db: Session, integration: GitHubIntegration) -> GitHubIntegrationRead:
    trigger_count = (
        db.query(GitHubChannelInstance.id)
        .filter(
            GitHubChannelInstance.tenant_id == integration.tenant_id,
            GitHubChannelInstance.github_integration_id == integration.id,
        )
        .count()
    )
    display_name = integration.display_name or integration.name
    return GitHubIntegrationRead(
        id=integration.id,
        tenant_id=integration.tenant_id,
        integration_name=display_name,
        name=display_name,
        provider=integration.provider or "github",
        auth_method=integration.auth_method or "pat",
        pat_token_preview=integration.pat_token_preview,
        default_owner=integration.default_owner,
        default_repo=integration.default_repo,
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


def _stored_pat(db: Session, integration: GitHubIntegration) -> Optional[str]:
    try:
        return decrypt_github_pat(db, integration.tenant_id, integration.pat_token_encrypted)
    except ValueError as exc:
        raise HTTPException(status_code=500, detail="Could not decrypt GitHub PAT") from exc


async def _run_test_connection(
    *,
    db: Session,
    tenant_id: str,
    integration: Optional[GitHubIntegration],
    pat_token: Optional[str],
    owner: str,
    repo: str,
) -> GitHubTestConnectionResponse:
    """Perform a live GET /repos/{owner}/{repo}.

    If ``integration`` is provided, its stored PAT is used (and its health
    fields are updated based on the result). If only an ad-hoc ``pat_token``
    is provided, we encrypt+seed a temporary in-memory integration to reuse
    the same code path — but we never persist that.
    """
    # Build a service. Easiest path: if we have a stored integration row,
    # use the normal constructor. Otherwise, encrypt the ad-hoc token, save
    # NOTHING, and call the API directly with httpx.
    if integration is not None:
        try:
            service = GitHubRepositoryService(db, tenant_id, integration.id)
            data = await service.get_repository(owner, repo)
        except GitHubRepositoryError as exc:
            integration.last_health_check = datetime.utcnow()
            integration.health_status = "unavailable"
            integration.health_status_reason = _health_reason(str(exc))
            db.add(integration)
            db.commit()
            return GitHubTestConnectionResponse(
                success=False,
                status_code=exc.status_code,
                message=str(exc),
                error="github_api_error",
            )
        integration.last_health_check = datetime.utcnow()
        integration.health_status = "healthy"
        integration.health_status_reason = None
        db.add(integration)
        db.commit()
        return GitHubTestConnectionResponse(
            success=True,
            status_code=200,
            message="Connection successful.",
            repo_full_name=data.get("full_name"),
        )

    # Ad-hoc PAT path — never persist the token.
    if not pat_token:
        raise HTTPException(
            status_code=400,
            detail="pat_token is required when github_integration_id is not provided",
        )
    import httpx

    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"token {pat_token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    url = f"https://api.github.com/repos/{owner}/{repo}"
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(url, headers=headers)
    except httpx.RequestError as exc:
        return GitHubTestConnectionResponse(
            success=False,
            message=f"Network error talking to GitHub: {exc}",
            error="network_error",
        )
    if 200 <= response.status_code < 300:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        return GitHubTestConnectionResponse(
            success=True,
            status_code=response.status_code,
            message="Connection successful.",
            repo_full_name=payload.get("full_name") if isinstance(payload, dict) else None,
        )
    try:
        body = response.json()
        msg = body.get("message") if isinstance(body, dict) else None
    except ValueError:
        msg = None
    return GitHubTestConnectionResponse(
        success=False,
        status_code=response.status_code,
        message=msg or f"HTTP {response.status_code}",
        error="github_api_error",
    )


@router.get("", response_model=list[GitHubIntegrationRead])
def list_github_integrations(
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> list[GitHubIntegrationRead]:
    tenant_id = _require_tenant(ctx)
    rows = (
        db.query(GitHubIntegration)
        .filter(
            GitHubIntegration.tenant_id == tenant_id,
            GitHubIntegration.type == "github",
        )
        .order_by(GitHubIntegration.created_at.desc(), GitHubIntegration.id.desc())
        .all()
    )
    return [_to_read(db, row) for row in rows]


@router.get("/{integration_id}", response_model=GitHubIntegrationRead)
def get_github_integration(
    integration_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubIntegrationRead:
    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    return _to_read(db, integration)


@router.post("", response_model=GitHubIntegrationRead, status_code=status.HTTP_201_CREATED)
def create_github_integration(
    payload: GitHubIntegrationCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitHubIntegrationRead:
    tenant_id = _require_tenant(ctx)
    provider_mode = _validate_provider_mode(payload.provider_mode)
    integration = GitHubIntegration(
        type="github",
        name=payload.integration_name,
        display_name=payload.integration_name,
        tenant_id=tenant_id,
        is_active=payload.is_active,
        health_status="unknown",
        provider="github",
        auth_method="pat",
        pat_token_encrypted=encrypt_github_pat(db, tenant_id, payload.pat_token),
        pat_token_preview=pat_preview(payload.pat_token),
        default_owner=payload.default_owner,
        default_repo=payload.default_repo,
        provider_mode=provider_mode,
    )
    db.add(integration)
    db.commit()
    db.refresh(integration)
    return _to_read(db, integration)


@router.patch("/{integration_id}", response_model=GitHubIntegrationRead)
def update_github_integration(
    integration_id: int,
    payload: GitHubIntegrationUpdate,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> GitHubIntegrationRead:
    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    data = payload.model_dump(exclude_unset=True)
    if "integration_name" in data and data["integration_name"] is not None:
        integration.name = data["integration_name"]
        integration.display_name = data["integration_name"]
    if "default_owner" in data:
        integration.default_owner = data["default_owner"]
    if "default_repo" in data:
        integration.default_repo = data["default_repo"]
    if "pat_token" in data:
        if data["pat_token"] is None:
            integration.pat_token_encrypted = None
            integration.pat_token_preview = None
        else:
            integration.pat_token_encrypted = encrypt_github_pat(
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
def delete_github_integration(
    integration_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.write")),
    db: Session = Depends(get_db),
) -> None:
    from models import AgentSkillIntegration

    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    in_use_trigger = (
        db.query(GitHubChannelInstance.id)
        .filter(
            GitHubChannelInstance.tenant_id == tenant_id,
            GitHubChannelInstance.github_integration_id == integration.id,
        )
        .first()
    )
    if in_use_trigger is not None:
        raise HTTPException(
            status_code=409,
            detail=(
                "GitHub integration is referenced by one or more triggers. "
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
                "GitHub integration is linked to one or more agent skills. "
                "Detach it from agents first."
            ),
        )
    db.delete(integration)
    db.commit()
    return None


@router.post("/test-connection", response_model=GitHubTestConnectionResponse)
async def test_github_connection(
    payload: GitHubTestConnectionRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubTestConnectionResponse:
    tenant_id = _require_tenant(ctx)
    if payload.github_integration_id:
        integration = _load_integration_or_404(db, tenant_id, payload.github_integration_id)
        owner = payload.owner or integration.default_owner
        repo = payload.repo or integration.default_repo
        if not owner or not repo:
            raise HTTPException(
                status_code=400,
                detail="owner and repo are required (no default_owner/default_repo on integration)",
            )
        return await _run_test_connection(
            db=db,
            tenant_id=tenant_id,
            integration=integration,
            pat_token=None,
            owner=owner,
            repo=repo,
        )
    if not payload.owner or not payload.repo:
        raise HTTPException(status_code=400, detail="owner and repo are required")
    return await _run_test_connection(
        db=db,
        tenant_id=tenant_id,
        integration=None,
        pat_token=payload.pat_token,
        owner=payload.owner,
        repo=payload.repo,
    )


@router.post("/{integration_id}/test-connection", response_model=GitHubTestConnectionResponse)
async def test_saved_github_connection(
    integration_id: int,
    payload: GitHubTestConnectionRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    _user=Depends(require_permission("hub.read")),
    db: Session = Depends(get_db),
) -> GitHubTestConnectionResponse:
    tenant_id = _require_tenant(ctx)
    integration = _load_integration_or_404(db, tenant_id, integration_id)
    owner = payload.owner or integration.default_owner
    repo = payload.repo or integration.default_repo
    if not owner or not repo:
        raise HTTPException(
            status_code=400,
            detail="owner and repo are required (no default_owner/default_repo on integration)",
        )
    return await _run_test_connection(
        db=db,
        tenant_id=tenant_id,
        integration=integration,
        pat_token=None,
        owner=owner,
        repo=repo,
    )
