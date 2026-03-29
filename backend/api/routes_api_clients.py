"""
API Client Management Routes — Internal/UI-facing
Provides CRUD operations for managing API clients from the Settings UI.
Uses regular JWT auth (require_permission), NOT API client auth.
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models_rbac import User
from auth_dependencies import require_permission
from services.api_client_service import ApiClientService, VALID_ROLES
from services.audit_service import log_tenant_event, TenantAuditActions

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class ApiClientCreateRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    role: str = Field(default="api_agent_only")
    rate_limit_rpm: int = Field(default=60, ge=1, le=600)
    expires_at: Optional[datetime] = None
    custom_scopes: Optional[List[str]] = None


class ApiClientUpdateRequest(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    role: Optional[str] = None
    rate_limit_rpm: Optional[int] = Field(None, ge=1, le=600)
    expires_at: Optional[datetime] = None
    custom_scopes: Optional[List[str]] = None


class ApiClientResponse(BaseModel):
    id: int
    tenant_id: str
    name: str
    description: Optional[str]
    client_id: str
    client_secret_prefix: str
    role: str
    custom_scopes: Optional[List[str]]
    is_active: bool
    rate_limit_rpm: int
    expires_at: Optional[str]
    last_used_at: Optional[str]
    created_at: str
    updated_at: str


class ApiClientCreateResponse(ApiClientResponse):
    client_secret: str  # Only shown once at creation
    warning: str = "Save this secret now. It will not be shown again."
    scopes: List[str]


class RotateSecretResponse(BaseModel):
    client_id: str
    client_secret: str  # Only shown once
    warning: str = "Save this secret now. It will not be shown again."


class ApiClientUsageResponse(BaseModel):
    total_requests: int
    error_requests: int
    error_rate: float
    avg_response_time_ms: Optional[float]
    last_request_at: Optional[str]


# ============================================================================
# Helpers
# ============================================================================

def _client_to_response(client) -> dict:
    return {
        "id": client.id,
        "tenant_id": client.tenant_id,
        "name": client.name,
        "description": client.description,
        "client_id": client.client_id,
        "client_secret_prefix": client.client_secret_prefix,
        "role": client.role,
        "custom_scopes": client.custom_scopes,
        "is_active": client.is_active,
        "rate_limit_rpm": client.rate_limit_rpm,
        "expires_at": client.expires_at.isoformat() if client.expires_at else None,
        "last_used_at": client.last_used_at.isoformat() if client.last_used_at else None,
        "created_at": client.created_at.isoformat() if client.created_at else None,
        "updated_at": client.updated_at.isoformat() if client.updated_at else None,
    }


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/api/clients", response_model=List[ApiClientResponse])
async def list_api_clients(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("api_clients.read")),
):
    """List all API clients for the current tenant."""
    service = ApiClientService(db)
    clients = service.list_clients(current_user.tenant_id)
    return [_client_to_response(c) for c in clients]


@router.post("/api/clients", response_model=ApiClientCreateResponse, status_code=201)
async def create_api_client(
    request: ApiClientCreateRequest,
    http_request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("api_clients.write")),
):
    """Create a new API client. Returns the client secret (shown only once)."""
    service = ApiClientService(db)

    # BUG-070 FIX: Pass creator permissions for escalation check
    creator_perms = None
    if not current_user.is_global_admin:
        from auth_service import AuthService
        auth_svc = AuthService(db)
        creator_perms = auth_svc.get_user_permissions(current_user.id)

    try:
        client, raw_secret = service.create_client(
            tenant_id=current_user.tenant_id,
            name=request.name,
            description=request.description,
            role=request.role,
            rate_limit_rpm=request.rate_limit_rpm,
            created_by=current_user.id,
            expires_at=request.expires_at,
            custom_scopes=request.custom_scopes,
            creator_permissions=creator_perms,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    log_tenant_event(db, current_user.tenant_id, current_user.id, TenantAuditActions.API_CLIENT_CREATE, "api_client", client.client_id, {"name": client.name}, http_request)

    scopes = service.resolve_scopes(client)
    response = _client_to_response(client)
    response["client_secret"] = raw_secret
    response["scopes"] = scopes
    response["warning"] = "Save this secret now. It will not be shown again."
    return response


@router.get("/api/clients/{client_id}", response_model=ApiClientResponse)
async def get_api_client(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("api_clients.read")),
):
    """Get details of a specific API client."""
    service = ApiClientService(db)
    client = service.get_client_by_id(client_id, tenant_id=current_user.tenant_id)
    if not client:
        raise HTTPException(status_code=404, detail="API client not found")
    return _client_to_response(client)


@router.put("/api/clients/{client_id}", response_model=ApiClientResponse)
async def update_api_client(
    client_id: str,
    request: ApiClientUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("api_clients.write")),
):
    """Update an API client's configuration."""
    service = ApiClientService(db)
    client = service.get_client_by_id(client_id, tenant_id=current_user.tenant_id)
    if not client:
        raise HTTPException(status_code=404, detail="API client not found")

    try:
        updated = service.update_client(
            client,
            name=request.name,
            description=request.description,
            role=request.role,
            rate_limit_rpm=request.rate_limit_rpm,
            expires_at=request.expires_at,
            custom_scopes=request.custom_scopes,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    return _client_to_response(updated)


@router.post("/api/clients/{client_id}/rotate-secret", response_model=RotateSecretResponse)
async def rotate_api_client_secret(
    client_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("api_clients.write")),
):
    """Rotate the secret for an API client. Old secret becomes invalid immediately."""
    service = ApiClientService(db)
    client = service.get_client_by_id(client_id, tenant_id=current_user.tenant_id)
    if not client:
        raise HTTPException(status_code=404, detail="API client not found")

    raw_secret = service.rotate_secret(client)

    log_tenant_event(db, current_user.tenant_id, current_user.id, TenantAuditActions.API_CLIENT_ROTATE, "api_client", client_id, {"name": client.name}, request)

    return {
        "client_id": client.client_id,
        "client_secret": raw_secret,
        "warning": "Save this secret now. It will not be shown again.",
    }


@router.delete("/api/clients/{client_id}", status_code=204)
async def revoke_api_client(
    client_id: str,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("api_clients.delete")),
):
    """Revoke an API client. All issued tokens will fail on next use."""
    service = ApiClientService(db)
    client = service.get_client_by_id(client_id, tenant_id=current_user.tenant_id)
    if not client:
        raise HTTPException(status_code=404, detail="API client not found")

    client_name = client.name
    service.revoke_client(client)

    log_tenant_event(db, current_user.tenant_id, current_user.id, TenantAuditActions.API_CLIENT_REVOKE, "api_client", client_id, {"name": client_name}, request)


@router.get("/api/clients/{client_id}/usage", response_model=ApiClientUsageResponse)
async def get_api_client_usage(
    client_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("api_clients.read")),
):
    """Get usage statistics for an API client."""
    service = ApiClientService(db)
    client = service.get_client_by_id(client_id, tenant_id=current_user.tenant_id)
    if not client:
        raise HTTPException(status_code=404, detail="API client not found")

    return service.get_usage_stats(client.id)
