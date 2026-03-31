"""
API Authentication — Public API v1
Provides unified auth dependency that supports both UI JWT tokens and API client auth.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Set, List

from fastapi import Depends, HTTPException, Header, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from auth_utils import decode_access_token
from auth_service import AuthService
from db import get_db
from models import ApiClient
from models_rbac import User
from services.api_client_service import ApiClientService

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


@dataclass
class ApiCaller:
    """Unified identity for both human users and API clients."""
    tenant_id: str
    permissions: Set[str] = field(default_factory=set)
    is_api_client: bool = False
    client_id: Optional[str] = None
    api_client_internal_id: Optional[int] = None
    user_id: Optional[int] = None
    name: str = ""
    is_global_admin: bool = False
    rate_limit_rpm: int = 60

    def has_permission(self, permission: str) -> bool:
        if self.is_global_admin:
            return True
        return permission in self.permissions


def get_api_caller(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    db: Session = Depends(get_db),
) -> ApiCaller:
    """
    Resolve the caller identity from either:
    1. Bearer JWT (from OAuth2 token exchange OR regular UI login)
    2. X-API-Key header (direct API key mode)
    Returns an ApiCaller object for unified permission checking.
    Sets request.state.rate_limit_rpm for the rate limiter middleware.
    """
    caller: Optional[ApiCaller] = None

    # Priority 1: Bearer token
    if credentials:
        token = credentials.credentials
        payload = decode_access_token(token)
        if not payload:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        token_type = payload.get("type")

        # API client JWT (from OAuth2 token exchange)
        if token_type == "api_client":
            caller = _resolve_api_client_jwt(payload, db)
        else:
            # Regular user JWT (from UI login) — also works on /api/v1/ for convenience
            caller = _resolve_user_jwt(payload, db)

    # Priority 2: X-API-Key direct mode
    elif x_api_key:
        caller = _resolve_api_key(x_api_key, db)

    if caller is None:
        # No auth provided
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Provide Bearer token or X-API-Key header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Propagate per-client rate limit to middleware
    request.state.rate_limit_rpm = caller.rate_limit_rpm

    return caller


def _resolve_api_client_jwt(payload: dict, db: Session) -> ApiCaller:
    """Resolve an API client from a JWT with type=api_client."""
    client_id_str = payload.get("client_id")
    scopes = payload.get("scopes", [])
    tenant_id = payload.get("tenant_id")

    if not client_id_str or not tenant_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API client token: missing claims",
        )

    # Verify the client still exists and is active
    service = ApiClientService(db)
    client = service.get_client_by_id(client_id_str)

    if not client or not client.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API client has been revoked or does not exist",
        )

    if client.expires_at and client.expires_at < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="API client has expired",
        )

    # Reject JWTs issued before the last secret rotation
    token_secret_ts = payload.get("secret_rotated_at")
    if client.secret_rotated_at is not None:
        if token_secret_ts is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API client token predates secret rotation — please re-authenticate",
            )
        token_rotated_at = datetime.fromisoformat(token_secret_ts)
        if token_rotated_at < client.secret_rotated_at:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="API client token has been invalidated by secret rotation",
            )

    return ApiCaller(
        tenant_id=tenant_id,
        permissions=set(scopes),
        is_api_client=True,
        client_id=client_id_str,
        api_client_internal_id=client.id,
        name=client.name,
        rate_limit_rpm=client.rate_limit_rpm or 60,
    )


def _resolve_user_jwt(payload: dict, db: Session) -> ApiCaller:
    """Resolve a regular UI user from a standard JWT."""
    try:
        user_id = int(payload.get("sub"))
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
        )

    auth_service = AuthService(db)
    user = auth_service.get_user_by_id(user_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled",
        )

    # Get user permissions
    user_permissions = set(auth_service.get_user_permissions(user.id))

    return ApiCaller(
        tenant_id=user.tenant_id or "",
        permissions=user_permissions,
        is_api_client=False,
        user_id=user.id,
        name=user.full_name or user.email,
        is_global_admin=user.is_global_admin,
        rate_limit_rpm=120,  # UI users get higher rate limits
    )


def _resolve_api_key(api_key: str, db: Session) -> ApiCaller:
    """Resolve an API client from an X-API-Key header (direct auth mode)."""
    if not api_key.startswith("tsn_cs_"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key format. Expected tsn_cs_* prefix.",
        )

    service = ApiClientService(db)
    client = service.resolve_by_api_key(api_key)

    if not client:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
        )

    scopes = service.resolve_scopes(client)

    return ApiCaller(
        tenant_id=client.tenant_id,
        permissions=set(scopes),
        is_api_client=True,
        client_id=client.client_id,
        api_client_internal_id=client.id,
        name=client.name,
        rate_limit_rpm=client.rate_limit_rpm or 60,
    )


def require_api_permission(permission: str):
    """
    FastAPI dependency factory that checks if the API caller has a specific permission.
    Works with both API clients and regular UI users.

    Usage:
        @router.get("/api/v1/agents")
        async def list_agents(caller: ApiCaller = Depends(require_api_permission("agents.read"))):
            # caller.tenant_id, caller.permissions, etc.
    """
    def check(caller: ApiCaller = Depends(get_api_caller)) -> ApiCaller:
        if not caller.has_permission(permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required: {permission}",
            )
        return caller

    return check
