"""
Authentication Dependencies
Phase 7.6.4 - Reusable FastAPI Dependencies

Provides common dependencies for authentication and authorization.

SEC-005: Supports httpOnly cookie auth (tsushin_session) with Bearer token fallback
for API clients and WebSocket connections that cannot use cookies.
"""

from datetime import datetime
from typing import Optional
from fastapi import Depends, HTTPException, Request, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from db import get_db
from models_rbac import User
from auth_service import AuthService

security = HTTPBearer(auto_error=False)  # Optional auth — kept for OpenAPI docs


def _extract_token(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> Optional[str]:
    """
    SEC-005: Extract JWT from httpOnly cookie (preferred) or Authorization Bearer (fallback).

    Priority:
    1. tsushin_session httpOnly cookie — set by backend on login/signup
    2. Authorization: Bearer <token> — for API clients, WebSocket auth, curl

    Returns the raw token string or None if no auth is present.
    """
    # Priority 1: httpOnly cookie (browser sessions)
    token = request.cookies.get("tsushin_session")
    if token:
        return token

    # Priority 2: Bearer token (API clients, WebSocket, mobile)
    if credentials:
        return credentials.credentials

    # Fallback for routes that call the strict helper directly without going
    # through the HTTPBearer dependency.
    auth_header = request.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        token = auth_header[7:].strip()
        if token:
            return token

    return None


def _resolve_current_user_strict_from_token(token: str, db: Session) -> User:
    """
    Resolve a JWT into an active user while enforcing the same checks used by
    required auth: valid signature/expiry, active user, and password-change
    invalidation via the token ``iat`` claim.
    """
    auth_service = AuthService(db)

    payload = auth_service.verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        user_id = int(payload.get("sub"))
        user = auth_service.get_user_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found"
            )

        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Account is disabled"
            )

        # BUG-134 FIX: Reject tokens issued before the last password change.
        # V060-API-004 HARDENING: Missing `iat` claim is a fatal 401 instead of
        # a silent skip — closes a JWT-stripping bypass.
        if user.password_changed_at:
            token_iat = payload.get("iat")
            if not token_iat:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token missing issued-at (iat) claim",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            try:
                token_issued = datetime.utcfromtimestamp(token_iat)
            except (TypeError, ValueError, OSError):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token issued-at claim",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            if token_issued < user.password_changed_at:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token invalidated by password change. Please log in again.",
                    headers={"WWW-Authenticate": "Bearer"},
                )

        return user

    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )


def _get_current_user_strict(
    request: Request,
    db: Session,
    credentials: Optional[HTTPAuthorizationCredentials] = None,
    required: bool = False,
) -> Optional[User]:
    """Shared strict auth path for optional/required session resolution."""
    token = _extract_token(request, credentials)
    if not token:
        if required:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return None

    return _resolve_current_user_strict_from_token(token, db)


def get_current_user_optional(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get current user from JWT token (optional - returns None if not authenticated)

    SEC-005: Checks httpOnly cookie first, then Authorization Bearer header.

    Args:
        request: FastAPI request (for cookie access)
        credentials: HTTP authorization credentials (optional)
        db: Database session

    Returns:
        User object if authenticated, None otherwise
    """
    token = _extract_token(request, credentials)
    if not token:
        return None

    auth_service = AuthService(db)

    # Verify token
    payload = auth_service.verify_token(token)
    if not payload:
        return None

    # Get user
    try:
        user_id = int(payload.get("sub"))
        user = auth_service.get_user_by_id(user_id)
        return user
    except (ValueError, TypeError):
        return None


def get_current_user_optional_strict(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get the current user when present, but enforce the same validation rules as
    required auth for any supplied token.

    Returns:
        User object if authenticated, ``None`` when no auth is present.

    Raises:
        HTTPException: 401/403 when an invalid or disabled-token path is supplied.
    """
    return _get_current_user_strict(request, db, credentials=credentials, required=False)


def get_current_user_optional_strict_from_request(
    request: Request,
    db: Session,
) -> Optional[User]:
    """
    Non-dependency variant of strict optional auth, used by routes that need to
    choose between multiple auth mechanisms before enforcing session auth.
    """
    return _get_current_user_strict(request, db, required=False)


def get_current_user_required(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user from JWT token (required - raises 401 if not authenticated)

    SEC-005: Checks httpOnly cookie first, then Authorization Bearer header.

    Args:
        request: FastAPI request (for cookie access)
        credentials: HTTP authorization credentials
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: 401 if not authenticated or token invalid
    """
    return _get_current_user_strict(request, db, credentials=credentials, required=True)


def ensure_permission(current_user: User, permission: str, db: Session) -> User:
    """
    Enforce a permission for a resolved user outside the dependency system.
    Reuses the same audit + error behavior as ``require_permission``.
    """
    from rbac_middleware import check_permission

    if not check_permission(current_user, permission, db):
        try:
            from services.audit_service import log_tenant_event, TenantAuditActions
            tenant_id = getattr(current_user, 'tenant_id', None)
            if tenant_id:
                log_tenant_event(
                    db,
                    tenant_id,
                    current_user.id,
                    TenantAuditActions.SECURITY_PERMISSION_DENIED,
                    "permission",
                    None,
                    {"required_permission": permission, "user_email": current_user.email},
                    severity="warning",
                )
        except Exception:
            pass
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied. Required: {permission}"
        )

    return current_user


def require_permission(permission: str):
    """
    Dependency to check if current user has a specific permission

    Usage:
        @router.get("/api/agents")
        async def list_agents(
            current_user: User = Depends(require_permission("agents.read")),
            db: Session = Depends(get_db)
        ):
            # Endpoint code here - current_user is returned

    Args:
        permission: Required permission string

    Returns:
        Dependency function that returns the user if authorized, raises 403 otherwise
    """
    def check(
        current_user: User = Depends(get_current_user_required),
        db: Session = Depends(get_db)
    ) -> User:
        return ensure_permission(current_user, permission, db)

    return check


def require_global_admin():
    """
    Dependency to check if current user is a global admin

    Raises:
        HTTPException: 403 if not global admin
    """
    def check(current_user: User = Depends(get_current_user_required)):
        if not current_user.is_global_admin:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Global admin privileges required"
            )
        return current_user

    return check


class TenantContext:
    """Context object containing current user and tenant information"""

    def __init__(self, user: User, db: Session):
        self.user = user
        self.db = db
        self.tenant_id = user.tenant_id
        self.is_global_admin = user.is_global_admin

    def filter_by_tenant(self, query, tenant_column, include_shared: bool = False):
        """
        Apply tenant isolation to a query

        Args:
            query: SQLAlchemy query
            tenant_column: Column to filter (e.g., Agent.tenant_id)
            include_shared: If True, also include resources with NULL tenant_id (use sparingly)

        Returns:
            Filtered query (or unfiltered for global admins)

        Security Note:
            By default, only returns resources matching the user's tenant.
            NULL tenant_id resources are NOT accessible unless explicitly requested
            with include_shared=True (should only be used for truly shared system resources).
        """
        if self.is_global_admin:
            return query

        if include_shared:
            # Only include NULL tenant resources when explicitly requested
            from sqlalchemy import or_
            return query.filter(or_(tenant_column == self.tenant_id, tenant_column.is_(None)))

        # Strict tenant isolation - only user's tenant, no NULL access
        return query.filter(tenant_column == self.tenant_id)

    def can_access_resource(self, resource_tenant_id: Optional[str], allow_shared: bool = False) -> bool:
        """
        Check if user can access a resource from another tenant

        Args:
            resource_tenant_id: Tenant ID of the resource
            allow_shared: If True, allow access to NULL tenant resources (use sparingly)

        Returns:
            True if user can access, False otherwise

        Security Note:
            By default, NULL tenant_id resources are NOT accessible to regular users.
            Only global admins or explicit allow_shared=True can access them.
        """
        if self.is_global_admin:
            return True

        # NULL tenant resources require explicit permission
        if resource_tenant_id is None:
            return allow_shared

        return resource_tenant_id == self.tenant_id


def get_tenant_context(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db)
) -> TenantContext:
    """
    Get tenant context for the current request

    Usage:
        @router.get("/api/agents")
        async def list_agents(ctx: TenantContext = Depends(get_tenant_context)):
            query = db.query(Agent)
            query = ctx.filter_by_tenant(query, Agent.tenant_id)
            return query.all()

    Args:
        current_user: Current authenticated user
        db: Database session

    Returns:
        TenantContext object
    """
    return TenantContext(current_user, db)
