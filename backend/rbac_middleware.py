"""
RBAC Middleware & Decorators
Phase 7.6.4 - Permission Enforcement

Provides middleware and decorators for role-based access control.
"""

from functools import wraps
from typing import List, Optional, Callable
from fastapi import HTTPException, status, Depends
from sqlalchemy.orm import Session

from auth_routes import get_current_user
from models_rbac import User
from auth_service import AuthService


class PermissionDeniedError(HTTPException):
    """Custom exception for permission denied"""
    def __init__(self, detail: str = "Permission denied"):
        super().__init__(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=detail
        )


def check_permission(user: User, permission: str, db: Session) -> bool:
    """
    Check if user has a specific permission

    Args:
        user: Current user object
        permission: Permission string (e.g., 'agents.read')
        db: Database session

    Returns:
        True if user has permission, False otherwise
    """
    # Global admins have all permissions
    if user.is_global_admin:
        return True

    # Get user permissions
    auth_service = AuthService(db)
    user_permissions = auth_service.get_user_permissions(user.id)

    # Check exact match
    if permission in user_permissions:
        return True

    # Check wildcard match (e.g., 'agents.*' matches 'agents.read')
    parts = permission.split('.')
    for i in range(len(parts), 0, -1):
        wildcard_perm = '.'.join(parts[:i]) + '.*'
        if wildcard_perm in user_permissions:
            return True

    return False


def require_permission(permission: str):
    """
    Decorator to require a specific permission for an endpoint

    Usage:
        @router.get("/api/agents")
        @require_permission("agents.read")
        async def list_agents(
            current_user: User = Depends(get_current_user),
            db: Session = Depends(get_db)
        ):
            # Endpoint code here

    Args:
        permission: Required permission string

    Raises:
        PermissionDeniedError: If user doesn't have permission
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user and db from kwargs
            current_user = kwargs.get('current_user')
            db = kwargs.get('db')

            if not current_user or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Missing current_user or db dependency"
                )

            # Check permission
            if not check_permission(current_user, permission, db):
                raise PermissionDeniedError(
                    f"You don't have permission to perform this action. Required: {permission}"
                )

            # Call original function
            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_any_permission(permissions: List[str]):
    """
    Decorator to require ANY of the specified permissions

    Args:
        permissions: List of permission strings (user needs at least one)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            db = kwargs.get('db')

            if not current_user or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Missing current_user or db dependency"
                )

            # Check if user has any of the permissions
            has_any = any(check_permission(current_user, perm, db) for perm in permissions)

            if not has_any:
                raise PermissionDeniedError(
                    f"You don't have permission to perform this action. Required (any): {', '.join(permissions)}"
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_all_permissions(permissions: List[str]):
    """
    Decorator to require ALL of the specified permissions

    Args:
        permissions: List of permission strings (user needs all of them)
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')
            db = kwargs.get('db')

            if not current_user or not db:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Missing current_user or db dependency"
                )

            # Check if user has all permissions
            for perm in permissions:
                if not check_permission(current_user, perm, db):
                    raise PermissionDeniedError(
                        f"You don't have permission to perform this action. Required (all): {', '.join(permissions)}"
                    )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_global_admin():
    """
    Decorator to require global admin access

    Raises:
        PermissionDeniedError: If user is not a global admin
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail="Missing current_user dependency"
                )

            if not current_user.is_global_admin:
                raise PermissionDeniedError(
                    "This action requires global admin privileges"
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_owner_or_admin():
    """
    Decorator to require owner or admin role

    Raises:
        PermissionDeniedError: If user is not owner or admin
    """
    return require_any_permission(["users.manage", "org.settings.write"])


def get_user_tenant_filter(user: User) -> Optional[str]:
    """
    Get tenant filter for database queries

    Args:
        user: Current user object

    Returns:
        Tenant ID for filtering, or None for global admins (see all tenants)
    """
    if user.is_global_admin:
        return None  # Global admins see all tenants
    return user.tenant_id


def enforce_tenant_isolation(query, user: User, tenant_column):
    """
    Apply tenant isolation to a SQLAlchemy query

    Usage:
        query = db.query(Agent)
        query = enforce_tenant_isolation(query, current_user, Agent.tenant_id)

    Args:
        query: SQLAlchemy query object
        user: Current user object
        tenant_column: Column to filter by (e.g., Agent.tenant_id)

    Returns:
        Filtered query
    """
    if user.is_global_admin:
        return query  # Global admins see everything

    return query.filter(tenant_column == user.tenant_id)
