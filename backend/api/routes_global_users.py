"""
Global User Management API Routes
Phase: User Management & SSO

Provides REST API endpoints for global admin user management.
Allows viewing and managing users across all tenants.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import Optional, List
from datetime import datetime
import logging

from db import get_db
from models_rbac import User, Tenant, UserRole, Role
from auth_dependencies import (
    get_current_user_required,
    require_global_admin,
)
from auth_utils import hash_password
from services.audit_service import log_admin_action, AuditActions

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/users", tags=["admin-users"])


# Request/Response Models
class GlobalUserResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str] = None
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None
    is_global_admin: bool
    is_active: bool
    email_verified: bool
    auth_provider: str
    has_google_linked: bool
    avatar_url: Optional[str] = None
    role: Optional[str] = None
    role_display_name: Optional[str] = None
    created_at: Optional[str] = None
    last_login_at: Optional[str] = None

    class Config:
        from_attributes = True


class GlobalUserListResponse(BaseModel):
    users: List[GlobalUserResponse]
    total: int
    page: int
    page_size: int
    filters: dict


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    full_name: str
    tenant_id: str
    role_name: str = "member"
    is_active: bool = True


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    is_active: Optional[bool] = None
    email_verified: Optional[bool] = None
    tenant_id: Optional[str] = None  # Transfer to different tenant
    role_name: Optional[str] = None


class UserStatsResponse(BaseModel):
    total_users: int
    active_users: int
    global_admins: int
    google_sso_users: int
    local_users: int
    users_per_tenant: dict
    users_per_role: dict


# Helper functions
def user_to_response(user: User, db: Session) -> GlobalUserResponse:
    """Convert User model to response format."""
    # Get tenant name
    tenant_name = None
    if user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
        if tenant:
            tenant_name = tenant.name

    # Get role
    role_name = None
    role_display_name = None
    user_role = db.query(UserRole).filter(UserRole.user_id == user.id).first()
    if user_role:
        role = db.query(Role).filter(Role.id == user_role.role_id).first()
        if role:
            role_name = role.name
            role_display_name = role.display_name

    return GlobalUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        tenant_id=user.tenant_id,
        tenant_name=tenant_name,
        is_global_admin=user.is_global_admin,
        is_active=user.is_active,
        email_verified=user.email_verified,
        auth_provider=user.auth_provider or 'local',
        has_google_linked=bool(user.google_id),
        avatar_url=user.avatar_url,
        role=role_name,
        role_display_name=role_display_name,
        created_at=user.created_at.isoformat() if user.created_at else None,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


@router.get("/", response_model=GlobalUserListResponse)
async def list_users(
    search: Optional[str] = Query(None, description="Search by email or name"),
    tenant_id: Optional[str] = Query(None, description="Filter by tenant ID"),
    role: Optional[str] = Query(None, description="Filter by role name"),
    status: Optional[str] = Query(None, description="Filter by status: active, inactive, all"),
    auth_provider: Optional[str] = Query(None, description="Filter by auth provider: local, google"),
    is_global_admin: Optional[bool] = Query(None, description="Filter global admins"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    List all users across tenants (global admin only).

    Supports filtering, searching, and pagination.
    """
    query = db.query(User).filter(User.deleted_at.is_(None))

    # Apply filters
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                User.email.ilike(search_pattern),
                User.full_name.ilike(search_pattern),
            )
        )

    if tenant_id:
        query = query.filter(User.tenant_id == tenant_id)

    if role:
        # Join with user_role and role tables
        query = query.join(UserRole, UserRole.user_id == User.id)
        query = query.join(Role, Role.id == UserRole.role_id)
        query = query.filter(Role.name == role)

    if status == "active":
        query = query.filter(User.is_active == True)
    elif status == "inactive":
        query = query.filter(User.is_active == False)

    if auth_provider:
        query = query.filter(User.auth_provider == auth_provider)

    if is_global_admin is not None:
        query = query.filter(User.is_global_admin == is_global_admin)

    # Count total before pagination
    total = query.count()

    # Apply pagination
    offset = (page - 1) * page_size
    users = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()

    return GlobalUserListResponse(
        users=[user_to_response(u, db) for u in users],
        total=total,
        page=page,
        page_size=page_size,
        filters={
            "search": search,
            "tenant_id": tenant_id,
            "role": role,
            "status": status,
            "auth_provider": auth_provider,
            "is_global_admin": is_global_admin,
        },
    )


@router.get("/stats", response_model=UserStatsResponse)
async def get_user_stats(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Get user statistics across all tenants (global admin only).
    """
    total_users = db.query(User).filter(User.deleted_at.is_(None)).count()
    active_users = db.query(User).filter(
        User.deleted_at.is_(None),
        User.is_active == True
    ).count()
    global_admins = db.query(User).filter(
        User.deleted_at.is_(None),
        User.is_global_admin == True
    ).count()
    google_sso_users = db.query(User).filter(
        User.deleted_at.is_(None),
        User.auth_provider == 'google'
    ).count()
    local_users = db.query(User).filter(
        User.deleted_at.is_(None),
        or_(User.auth_provider == 'local', User.auth_provider.is_(None))
    ).count()

    # Users per tenant
    tenants = db.query(Tenant).filter(Tenant.deleted_at.is_(None)).all()
    users_per_tenant = {}
    for tenant in tenants:
        count = db.query(User).filter(
            User.tenant_id == tenant.id,
            User.deleted_at.is_(None)
        ).count()
        users_per_tenant[tenant.name] = count

    # Users per role
    roles = db.query(Role).all()
    users_per_role = {}
    for role in roles:
        count = db.query(UserRole).filter(UserRole.role_id == role.id).count()
        users_per_role[role.display_name] = count

    return UserStatsResponse(
        total_users=total_users,
        active_users=active_users,
        global_admins=global_admins,
        google_sso_users=google_sso_users,
        local_users=local_users,
        users_per_tenant=users_per_tenant,
        users_per_role=users_per_role,
    )


@router.get("/{user_id}", response_model=GlobalUserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Get a specific user by ID (global admin only).
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.deleted_at.is_(None)
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user_to_response(user, db)


@router.post("/", response_model=GlobalUserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(
    request: UserCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Create a new user in any tenant (global admin only).
    """
    # Check if email exists
    existing = db.query(User).filter(User.email == request.email).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered"
        )

    # Validate tenant
    tenant = db.query(Tenant).filter(
        Tenant.id == request.tenant_id,
        Tenant.deleted_at.is_(None)
    ).first()
    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid tenant ID"
        )

    # Validate role
    role = db.query(Role).filter(Role.name == request.role_name).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid role name"
        )

    # Check tenant limits
    current_users = db.query(User).filter(
        User.tenant_id == request.tenant_id,
        User.deleted_at.is_(None)
    ).count()

    if tenant.max_users > 0 and current_users >= tenant.max_users:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Tenant has reached maximum user limit ({tenant.max_users})"
        )

    # Create user
    user = User(
        email=request.email,
        password_hash=hash_password(request.password),
        full_name=request.full_name,
        tenant_id=request.tenant_id,
        is_global_admin=False,
        is_active=request.is_active,
        email_verified=True,  # Created by admin
        auth_provider='local',
    )
    db.add(user)
    db.flush()

    # Assign role
    user_role = UserRole(
        user_id=user.id,
        role_id=role.id,
        tenant_id=request.tenant_id,
        assigned_by=current_user.id,
    )
    db.add(user_role)

    db.commit()
    db.refresh(user)

    # Log action
    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.USER_CREATE,
        resource_type="user",
        resource_id=str(user.id),
        target_tenant_id=request.tenant_id,
        details={"email": user.email, "role": request.role_name},
    )

    logger.info(f"Global admin created user: {user.email} in tenant: {request.tenant_id}")

    return user_to_response(user, db)


@router.put("/{user_id}", response_model=GlobalUserResponse)
async def update_user(
    user_id: int,
    request: UserUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Update a user (global admin only).

    Can update profile, status, tenant assignment, and role.
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.deleted_at.is_(None)
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent modifying self
    if user.id == current_user.id and request.is_active == False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot deactivate your own account"
        )

    updates = {}

    if request.full_name is not None:
        user.full_name = request.full_name
        updates["full_name"] = request.full_name

    if request.is_active is not None:
        user.is_active = request.is_active
        updates["is_active"] = request.is_active

    if request.email_verified is not None:
        user.email_verified = request.email_verified
        updates["email_verified"] = request.email_verified

    # Handle tenant transfer
    if request.tenant_id is not None and request.tenant_id != user.tenant_id:
        # Validate new tenant
        new_tenant = db.query(Tenant).filter(
            Tenant.id == request.tenant_id,
            Tenant.deleted_at.is_(None)
        ).first()
        if not new_tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid tenant ID"
            )

        # Check new tenant limits
        current_users = db.query(User).filter(
            User.tenant_id == request.tenant_id,
            User.deleted_at.is_(None)
        ).count()

        if new_tenant.max_users > 0 and current_users >= new_tenant.max_users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Target tenant has reached maximum user limit ({new_tenant.max_users})"
            )

        old_tenant_id = user.tenant_id
        user.tenant_id = request.tenant_id
        updates["tenant_id"] = {"from": old_tenant_id, "to": request.tenant_id}

        # Update user role tenant_id
        user_role = db.query(UserRole).filter(UserRole.user_id == user.id).first()
        if user_role:
            user_role.tenant_id = request.tenant_id

    # Handle role change
    if request.role_name is not None:
        role = db.query(Role).filter(Role.name == request.role_name).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid role name"
            )

        # Update or create user role
        user_role = db.query(UserRole).filter(UserRole.user_id == user.id).first()
        if user_role:
            old_role = db.query(Role).filter(Role.id == user_role.role_id).first()
            user_role.role_id = role.id
            user_role.assigned_by = current_user.id
            user_role.assigned_at = datetime.utcnow()
            updates["role"] = {"from": old_role.name if old_role else None, "to": request.role_name}
        else:
            new_role = UserRole(
                user_id=user.id,
                role_id=role.id,
                tenant_id=user.tenant_id,
                assigned_by=current_user.id,
            )
            db.add(new_role)
            updates["role"] = {"from": None, "to": request.role_name}

    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)

    # Log action
    if updates:
        log_admin_action(
            db=db,
            admin=current_user,
            action=AuditActions.USER_UPDATE,
            resource_type="user",
            resource_id=str(user.id),
            target_tenant_id=user.tenant_id,
            details={"updates": updates},
        )

    return user_to_response(user, db)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(
    user_id: int,
    hard_delete: bool = Query(False, description="Permanently delete (cannot be undone)"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Delete (soft or hard) a user (global admin only).

    By default, performs a soft delete (marks as deleted).
    Use hard_delete=true to permanently remove.
    """
    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent deleting self
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete your own account"
        )

    # Prevent deleting other global admins
    if user.is_global_admin:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot delete a global admin account"
        )

    if hard_delete:
        # Delete user roles first
        db.query(UserRole).filter(UserRole.user_id == user.id).delete()
        # Hard delete
        db.delete(user)
    else:
        # Soft delete
        user.deleted_at = datetime.utcnow()
        user.is_active = False

    db.commit()

    # Log action
    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.USER_DELETE,
        resource_type="user",
        resource_id=str(user_id),
        target_tenant_id=user.tenant_id,
        details={"hard_delete": hard_delete, "email": user.email},
    )

    logger.info(f"Global admin deleted user: {user.email} (hard={hard_delete})")


@router.post("/{user_id}/reset-password")
async def admin_reset_password(
    user_id: int,
    new_password: str = Query(..., min_length=8),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Reset a user's password (global admin only).
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.deleted_at.is_(None)
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Update password
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.utcnow()
    db.commit()

    # Log action
    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.USER_UPDATE,
        resource_type="user",
        resource_id=str(user.id),
        target_tenant_id=user.tenant_id,
        details={"action": "password_reset"},
    )

    return {"message": "Password reset successfully"}


@router.post("/{user_id}/toggle-admin")
async def toggle_global_admin(
    user_id: int,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Toggle global admin status for a user (global admin only).
    """
    user = db.query(User).filter(
        User.id == user_id,
        User.deleted_at.is_(None)
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    # Prevent toggling self
    if user.id == current_user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot modify your own admin status"
        )

    # Toggle
    user.is_global_admin = not user.is_global_admin
    user.updated_at = datetime.utcnow()
    db.commit()

    # Log action
    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.USER_UPDATE,
        resource_type="user",
        resource_id=str(user.id),
        target_tenant_id=user.tenant_id,
        details={"is_global_admin": user.is_global_admin},
    )

    status_text = "granted" if user.is_global_admin else "revoked"
    return {"message": f"Global admin status {status_text}", "is_global_admin": user.is_global_admin}
