"""
Authentication Dependencies
Phase 7.6.4 - Reusable FastAPI Dependencies

Provides common dependencies for authentication and authorization.
"""

from typing import Optional
from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from db import get_db
from models_rbac import User
from auth_service import AuthService

security = HTTPBearer(auto_error=False)  # Optional auth


def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> Optional[User]:
    """
    Get current user from JWT token (optional - returns None if not authenticated)

    Args:
        credentials: HTTP authorization credentials (optional)
        db: Database session

    Returns:
        User object if authenticated, None otherwise
    """
    if not credentials:
        return None

    token = credentials.credentials
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


def get_current_user_required(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
    db: Session = Depends(get_db)
) -> User:
    """
    Get current user from JWT token (required - raises 401 if not authenticated)

    Args:
        credentials: HTTP authorization credentials
        db: Database session

    Returns:
        User object

    Raises:
        HTTPException: 401 if not authenticated or token invalid
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    auth_service = AuthService(db)

    # Verify token
    payload = auth_service.verify_token(token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Get user
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

        return user

    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )


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
        from rbac_middleware import check_permission

        if not check_permission(current_user, permission, db):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied. Required: {permission}"
            )

        return current_user

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
