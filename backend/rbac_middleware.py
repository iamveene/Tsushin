"""
RBAC Middleware
Permission checking utilities for role-based access control.
"""

from sqlalchemy.orm import Session

from models_rbac import User
from auth_service import AuthService


def check_permission(user: User, permission: str, db: Session) -> bool:
    """
    Check if user has a specific permission.

    Args:
        user: Current user object
        permission: Permission string (e.g., 'agents.read')
        db: Database session

    Returns:
        True if user has permission, False otherwise
    """
    if user.is_global_admin:
        return True

    auth_service = AuthService(db)
    user_permissions = auth_service.get_user_permissions(user.id)

    if permission in user_permissions:
        return True

    parts = permission.split('.')
    for i in range(len(parts), 0, -1):
        wildcard_perm = '.'.join(parts[:i]) + '.*'
        if wildcard_perm in user_permissions:
            return True

    return False
