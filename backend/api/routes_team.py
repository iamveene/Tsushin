"""
Team Management API Routes
Phase 7.9: Multi-tenancy support

Provides REST API endpoints for team member and invitation management.

IMPORTANT: Route order matters in FastAPI! Specific routes (e.g., /invitations, /roles)
must be defined BEFORE parameterized routes (e.g., /{user_id}) to avoid conflicts.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import Optional, List
from datetime import datetime, timedelta

from db import get_db
from models_rbac import User, UserRole, Role, Tenant, UserInvitation
from auth_dependencies import (
    get_current_user_required,
    require_permission,
    TenantContext,
    get_tenant_context
)
from auth_utils import generate_invitation_token
from services.email_service import send_invitation

router = APIRouter(prefix="/api/team", tags=["team"])


# Request/Response Models
class TeamMemberResponse(BaseModel):
    id: int
    email: str
    full_name: Optional[str]
    role: str
    role_display_name: str
    is_active: bool
    email_verified: bool
    auth_provider: str = "local"
    avatar_url: Optional[str] = None
    created_at: Optional[str]
    last_login_at: Optional[str]

    class Config:
        from_attributes = True


class TeamListResponse(BaseModel):
    members: List[TeamMemberResponse]
    total: int
    page: int
    page_size: int


class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = "member"
    message: Optional[str] = None


class InvitationResponse(BaseModel):
    id: int
    email: str
    role: str
    role_display_name: str
    invited_by_name: str
    expires_at: str
    created_at: str
    invitation_link: Optional[str] = None

    class Config:
        from_attributes = True


class InvitationListResponse(BaseModel):
    invitations: List[InvitationResponse]
    total: int


class RoleChangeRequest(BaseModel):
    role: str


# Helper functions
def get_user_role_info(user: User, tenant_id: str, db: Session) -> tuple:
    """Get user's role name and display name for a tenant."""
    user_role = db.query(UserRole).join(Role).filter(
        UserRole.user_id == user.id,
        UserRole.tenant_id == tenant_id
    ).first()

    if user_role:
        role = db.query(Role).filter(Role.id == user_role.role_id).first()
        return (role.name, role.display_name) if role else ("member", "Member")

    return ("member", "Member")


def user_to_response(user: User, tenant_id: str, db: Session) -> TeamMemberResponse:
    """Convert User model to TeamMemberResponse."""
    role_name, role_display = get_user_role_info(user, tenant_id, db)

    return TeamMemberResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=role_name,
        role_display_name=role_display,
        is_active=user.is_active,
        email_verified=user.email_verified,
        auth_provider=user.auth_provider or 'local',
        avatar_url=user.avatar_url,
        created_at=user.created_at.isoformat() if user.created_at else None,
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
    )


def invitation_to_response(invitation: UserInvitation, db: Session, include_link: bool = False) -> InvitationResponse:
    """Convert UserInvitation model to InvitationResponse."""
    role = db.query(Role).filter(Role.id == invitation.role_id).first()
    inviter = db.query(User).filter(User.id == invitation.invited_by).first()

    response = InvitationResponse(
        id=invitation.id,
        email=invitation.email,
        role=role.name if role else "member",
        role_display_name=role.display_name if role else "Member",
        invited_by_name=inviter.full_name if inviter else "Unknown",
        expires_at=invitation.expires_at.isoformat(),
        created_at=invitation.created_at.isoformat() if invitation.created_at else datetime.utcnow().isoformat() + "Z",
    )

    if include_link:
        # In production, this would be the actual frontend URL
        response.invitation_link = f"/auth/invite/{invitation.invitation_token}"

    return response


# ==============================================================================
# Endpoints
# ==============================================================================
# IMPORTANT: Specific routes must come BEFORE parameterized routes!
# Order: /, /invitations, /roles, /invite, then /{user_id} routes
# ==============================================================================


@router.get("/", response_model=TeamListResponse)
async def list_team_members(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("users.read")),
):
    """
    List team members for current tenant.

    Requires: users.read permission
    """
    if not ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant context available"
        )

    query = ctx.db.query(User).filter(
        User.tenant_id == ctx.tenant_id,
        User.deleted_at.is_(None)
    )

    # Search by email or name
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                User.email.ilike(search_term),
                User.full_name.ilike(search_term)
            )
        )

    # Filter by active status
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    # Get total count
    total = query.count()

    # Pagination
    offset = (page - 1) * page_size
    users = query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()

    # Filter by role (after pagination to simplify query)
    members = []
    for user in users:
        role_name, role_display = get_user_role_info(user, ctx.tenant_id, ctx.db)
        if role is None or role_name == role:
            members.append(user_to_response(user, ctx.tenant_id, ctx.db))

    return TeamListResponse(
        members=members,
        total=total,
        page=page,
        page_size=page_size,
    )


# ------------------------------------------------------------------------------
# Specific routes (must come BEFORE /{user_id} to avoid route conflicts)
# ------------------------------------------------------------------------------

@router.get("/invitations", response_model=InvitationListResponse)
async def list_invitations(
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("users.invite")),
):
    """
    List pending invitations for current tenant.

    Requires: users.invite permission
    """
    invitations = ctx.db.query(UserInvitation).filter(
        UserInvitation.tenant_id == ctx.tenant_id,
        UserInvitation.accepted_at.is_(None),
        UserInvitation.expires_at > datetime.utcnow()
    ).order_by(UserInvitation.created_at.desc()).all()

    return InvitationListResponse(
        invitations=[invitation_to_response(inv, ctx.db) for inv in invitations],
        total=len(invitations),
    )


@router.get("/roles")
async def get_available_roles(
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("users.read")),
):
    """
    Get list of available roles.

    Returns roles that the current user can assign.
    """
    roles = ctx.db.query(Role).filter(Role.is_system_role == True).all()

    current_role_name, _ = get_user_role_info(ctx.user, ctx.tenant_id, ctx.db)

    # Filter based on current user's permissions
    available_roles = []
    for role in roles:
        can_assign = True

        # Only owners/global admins can assign owner/admin roles
        if role.name in ["owner", "admin"]:
            if current_role_name not in ["owner"] and not ctx.is_global_admin:
                can_assign = False

        available_roles.append({
            "name": role.name,
            "display_name": role.display_name,
            "description": role.description,
            "can_assign": can_assign,
        })

    return {"roles": available_roles}


@router.post("/invite", response_model=InvitationResponse, status_code=status.HTTP_201_CREATED)
async def invite_team_member(
    request: InvitationCreate,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("users.invite")),
):
    """
    Send invitation to join team.

    Requires: users.invite permission
    """
    if not ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No tenant context available"
        )

    # Check if email already exists as user
    existing_user = ctx.db.query(User).filter(User.email == request.email).first()
    if existing_user:
        if existing_user.tenant_id == ctx.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a team member"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email is already registered with another organization"
        )

    # Check if invitation already exists
    existing_invitation = ctx.db.query(UserInvitation).filter(
        UserInvitation.tenant_id == ctx.tenant_id,
        UserInvitation.email == request.email,
        UserInvitation.accepted_at.is_(None),
        UserInvitation.expires_at > datetime.utcnow()
    ).first()

    if existing_invitation:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invitation already sent to this email"
        )

    # Check tenant user limit
    tenant = ctx.db.query(Tenant).filter(Tenant.id == ctx.tenant_id).first()
    if tenant:
        current_users = ctx.db.query(User).filter(
            User.tenant_id == ctx.tenant_id,
            User.deleted_at.is_(None)
        ).count()
        pending_invites = ctx.db.query(UserInvitation).filter(
            UserInvitation.tenant_id == ctx.tenant_id,
            UserInvitation.accepted_at.is_(None),
            UserInvitation.expires_at > datetime.utcnow()
        ).count()

        if current_users + pending_invites >= tenant.max_users:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Team size limit reached ({tenant.max_users} users)"
            )

    # Get role
    role = ctx.db.query(Role).filter(Role.name == request.role).first()
    if not role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {request.role}"
        )

    # Check if current user can invite with this role
    current_role_name, _ = get_user_role_info(ctx.user, ctx.tenant_id, ctx.db)
    if request.role in ["owner", "admin"] and current_role_name not in ["owner"] and not ctx.is_global_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can invite admins or owners"
        )

    # Create invitation
    invitation = UserInvitation(
        tenant_id=ctx.tenant_id,
        email=request.email,
        role_id=role.id,
        invited_by=ctx.user.id,
        invitation_token=generate_invitation_token(),
        expires_at=datetime.utcnow() + timedelta(days=7),
    )
    ctx.db.add(invitation)
    ctx.db.commit()
    ctx.db.refresh(invitation)

    # Get tenant name for email
    tenant = ctx.db.query(Tenant).filter(Tenant.id == ctx.tenant_id).first()
    tenant_name = tenant.name if tenant else "the organization"

    # Send invitation email
    send_invitation(
        to_email=request.email,
        inviter_name=ctx.user.full_name or ctx.user.email,
        tenant_name=tenant_name,
        role_name=role.display_name,
        invitation_token=invitation.invitation_token,
        personal_message=request.message,
    )

    return invitation_to_response(invitation, ctx.db, include_link=True)


@router.delete("/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_invitation(
    invitation_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("users.invite")),
):
    """
    Cancel a pending invitation.

    Requires: users.invite permission
    """
    invitation = ctx.db.query(UserInvitation).filter(
        UserInvitation.id == invitation_id,
        UserInvitation.tenant_id == ctx.tenant_id,
        UserInvitation.accepted_at.is_(None)
    ).first()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    ctx.db.delete(invitation)
    ctx.db.commit()


@router.post("/invitations/{invitation_id}/resend", response_model=InvitationResponse)
async def resend_invitation(
    invitation_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("users.invite")),
):
    """
    Resend an invitation (extends expiry and regenerates token).

    Requires: users.invite permission
    """
    invitation = ctx.db.query(UserInvitation).filter(
        UserInvitation.id == invitation_id,
        UserInvitation.tenant_id == ctx.tenant_id,
        UserInvitation.accepted_at.is_(None)
    ).first()

    if not invitation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found"
        )

    # Regenerate token and extend expiry
    invitation.invitation_token = generate_invitation_token()
    invitation.expires_at = datetime.utcnow() + timedelta(days=7)

    ctx.db.commit()
    ctx.db.refresh(invitation)

    # Get role and tenant info for email
    role = ctx.db.query(Role).filter(Role.id == invitation.role_id).first()
    tenant = ctx.db.query(Tenant).filter(Tenant.id == ctx.tenant_id).first()

    # Send invitation email
    send_invitation(
        to_email=invitation.email,
        inviter_name=ctx.user.full_name or ctx.user.email,
        tenant_name=tenant.name if tenant else "the organization",
        role_name=role.display_name if role else "Member",
        invitation_token=invitation.invitation_token,
    )

    return invitation_to_response(invitation, ctx.db, include_link=True)


# ------------------------------------------------------------------------------
# Parameterized routes (must come AFTER specific routes like /invitations, /roles)
# ------------------------------------------------------------------------------

@router.get("/{user_id}", response_model=TeamMemberResponse)
async def get_team_member(
    user_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("users.read")),
):
    """
    Get team member details by ID.

    Requires: users.read permission
    """
    user = ctx.db.query(User).filter(
        User.id == user_id,
        User.tenant_id == ctx.tenant_id,
        User.deleted_at.is_(None)
    ).first()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found"
        )

    return user_to_response(user, ctx.tenant_id, ctx.db)


@router.put("/{user_id}/role", response_model=TeamMemberResponse)
async def change_member_role(
    user_id: int,
    request: RoleChangeRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("users.manage")),
):
    """
    Change a team member's role.

    Requires: users.manage permission

    Restrictions:
    - Cannot change own role
    - Cannot demote other owners
    - Only owners can promote to admin/owner
    """
    if user_id == ctx.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot change your own role"
        )

    # Get target user
    target_user = ctx.db.query(User).filter(
        User.id == user_id,
        User.tenant_id == ctx.tenant_id,
        User.deleted_at.is_(None)
    ).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found"
        )

    # Get target's current role
    target_role_name, _ = get_user_role_info(target_user, ctx.tenant_id, ctx.db)

    # Check if target is owner - only global admin can demote owners
    if target_role_name == "owner" and not ctx.is_global_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot change owner role"
        )

    # Get new role
    new_role = ctx.db.query(Role).filter(Role.name == request.role).first()
    if not new_role:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid role: {request.role}"
        )

    # Check if current user can assign this role
    current_role_name, _ = get_user_role_info(ctx.user, ctx.tenant_id, ctx.db)

    # Only owners can promote to owner/admin
    if request.role in ["owner", "admin"] and current_role_name not in ["owner"] and not ctx.is_global_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only owners can promote users to admin or owner"
        )

    # Update or create user role
    user_role = ctx.db.query(UserRole).filter(
        UserRole.user_id == user_id,
        UserRole.tenant_id == ctx.tenant_id
    ).first()

    if user_role:
        user_role.role_id = new_role.id
        user_role.assigned_by = ctx.user.id
        user_role.assigned_at = datetime.utcnow()
    else:
        user_role = UserRole(
            user_id=user_id,
            role_id=new_role.id,
            tenant_id=ctx.tenant_id,
            assigned_by=ctx.user.id,
        )
        ctx.db.add(user_role)

    ctx.db.commit()

    return user_to_response(target_user, ctx.tenant_id, ctx.db)


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(
    user_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    current_user: User = Depends(require_permission("users.remove")),
):
    """
    Remove a team member (soft delete).

    Requires: users.remove permission

    Restrictions:
    - Cannot remove yourself
    - Cannot remove owners (unless global admin)
    """
    if user_id == ctx.user.id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Cannot remove yourself"
        )

    target_user = ctx.db.query(User).filter(
        User.id == user_id,
        User.tenant_id == ctx.tenant_id,
        User.deleted_at.is_(None)
    ).first()

    if not target_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Team member not found"
        )

    # Check if target is owner
    target_role_name, _ = get_user_role_info(target_user, ctx.tenant_id, ctx.db)
    if target_role_name == "owner" and not ctx.is_global_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cannot remove owner"
        )

    # Soft delete
    target_user.deleted_at = datetime.utcnow()
    target_user.is_active = False

    # Remove role assignment
    ctx.db.query(UserRole).filter(
        UserRole.user_id == user_id,
        UserRole.tenant_id == ctx.tenant_id
    ).delete()

    ctx.db.commit()
