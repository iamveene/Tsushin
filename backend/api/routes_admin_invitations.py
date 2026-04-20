"""
Global Admin Invitation Management API Routes

Provides REST API endpoints for global admins to create and manage
invitations across the entire platform. Unlike the tenant-scoped
``/api/team/invite`` endpoint, this router supports:

- Tenant-scoped invites to any tenant (admin picks the target tenant).
- Global-admin invites (``is_global_admin=True``, tenant_id/role null).
- Per-invite ``auth_provider`` ('local' or 'google') so Google-SSO users
  can be bootstrapped without a local password.

Endpoints:
    POST   /api/admin/invitations       — create invitation
    GET    /api/admin/invitations       — list pending invitations (filters)
    DELETE /api/admin/invitations/{id}  — cancel invitation

All endpoints require global admin privileges.
"""

from datetime import datetime, timedelta
from typing import List, Optional
import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy import and_, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db import get_db
from models_rbac import Role, Tenant, User, UserInvitation
from auth_dependencies import get_current_user_required, require_global_admin
from auth_utils import generate_invitation_token, hash_token
from services.audit_service import AuditActions, log_admin_action
from services.email_service import send_invitation
from services.public_ingress_resolver import resolve_invitation_base_url

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/invitations", tags=["admin-invitations"])


# ---------------------------------------------------------------------------
# Request/Response Models
# ---------------------------------------------------------------------------

class AdminInvitationCreate(BaseModel):
    """Create a new invitation (global admin).

    Two shapes are accepted:
      - Global-admin invite: ``is_global_admin=True``, ``tenant_id`` and
        ``role`` must be null.
      - Tenant-scoped invite: ``is_global_admin=False`` (default),
        ``tenant_id`` and ``role`` must both be set.
    """
    email: EmailStr
    tenant_id: Optional[str] = None
    role: Optional[str] = None
    is_global_admin: bool = False
    auth_provider: str = "local"
    message: Optional[str] = None

    @field_validator("auth_provider")
    @classmethod
    def _validate_auth_provider(cls, v: str) -> str:
        if v not in ("local", "google"):
            raise ValueError("auth_provider must be 'local' or 'google'")
        return v


class AdminInvitationResponse(BaseModel):
    id: int
    email: str
    tenant_id: Optional[str] = None
    tenant_name: Optional[str] = None
    role: Optional[str] = None
    role_display_name: Optional[str] = None
    is_global_admin: bool
    auth_provider: str
    invited_by_name: str
    expires_at: str
    created_at: str
    invitation_link: Optional[str] = None


class AdminInvitationListResponse(BaseModel):
    invitations: List[AdminInvitationResponse]
    total: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _invitation_to_response(
    inv: UserInvitation,
    db: Session,
    raw_token: Optional[str] = None,
    request: Optional[Request] = None,
) -> AdminInvitationResponse:
    tenant = None
    tenant_name = None
    if inv.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == inv.tenant_id).first()
        tenant_name = tenant.name if tenant else None

    role_name = None
    role_display = None
    if inv.role_id:
        role = db.query(Role).filter(Role.id == inv.role_id).first()
        if role:
            role_name = role.name
            role_display = role.display_name

    inviter = db.query(User).filter(User.id == inv.invited_by).first()

    resp = AdminInvitationResponse(
        id=inv.id,
        email=inv.email,
        tenant_id=inv.tenant_id,
        tenant_name=tenant_name,
        role=role_name,
        role_display_name=role_display,
        is_global_admin=bool(inv.is_global_admin),
        auth_provider=inv.auth_provider or "local",
        invited_by_name=(inviter.full_name or inviter.email) if inviter else "Unknown",
        expires_at=inv.expires_at.isoformat(),
        created_at=inv.created_at.isoformat() if inv.created_at else datetime.utcnow().isoformat(),
    )
    if raw_token:
        base_url = resolve_invitation_base_url(request, tenant) if request is not None else None
        resp.invitation_link = (
            f"{base_url}/auth/invite/{raw_token}" if base_url else f"/auth/invite/{raw_token}"
        )
    return resp


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", response_model=AdminInvitationResponse, status_code=status.HTTP_201_CREATED, include_in_schema=False)
@router.post("/", response_model=AdminInvitationResponse, status_code=status.HTTP_201_CREATED)
async def create_admin_invitation(
    payload: AdminInvitationCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_global_admin()),
):
    """Create a tenant-scoped or global-admin invitation."""
    # ------------------- shape validation -------------------
    # NOTE: use truthy checks (not `is not None`) so empty strings from the
    # frontend are rejected too. An empty `tenant_id=""` on a global-admin
    # invite would otherwise be written verbatim to UserInvitation.tenant_id,
    # breaking the `tenant_id IS NULL` invariant and the partial-unique
    # dedup index.
    if payload.is_global_admin:
        if payload.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Global admin invitations must not include tenant_id. Global admins are platform-wide and not scoped to a tenant.",
            )
        if payload.role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Global admin invitations must not include role.",
            )
        tenant_id: Optional[str] = None
        role_id: Optional[int] = None
    else:
        if not payload.tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="tenant_id is required for tenant-scoped invitations. Pick the organization this user should belong to.",
            )
        if not payload.role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="role is required for tenant-scoped invitations.",
            )
        tenant = db.query(Tenant).filter(Tenant.id == payload.tenant_id).first()
        if not tenant:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Tenant not found: {payload.tenant_id}",
            )
        role = db.query(Role).filter(Role.name == payload.role).first()
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid role: {payload.role}",
            )
        tenant_id = tenant.id
        role_id = role.id

    # ------------------- reject if already a user -------------------
    existing_user = db.query(User).filter(
        User.email == payload.email,
        User.deleted_at.is_(None),
    ).first()
    if existing_user:
        if payload.is_global_admin and existing_user.is_global_admin:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a global admin",
            )
        if (not payload.is_global_admin) and existing_user.tenant_id == tenant_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User is already a member of this tenant",
            )

    # ------------------- reject if pending invite already exists -------------------
    # Matches the partial-unique index behavior (accepted_at IS NULL). We do
    # this check pre-emptively for a nice error message, and also catch
    # IntegrityError below as a race safety net.
    pending_q = db.query(UserInvitation).filter(
        UserInvitation.email == payload.email,
        UserInvitation.accepted_at.is_(None),
    )
    if tenant_id is None:
        pending_q = pending_q.filter(UserInvitation.tenant_id.is_(None))
    else:
        pending_q = pending_q.filter(UserInvitation.tenant_id == tenant_id)
    existing_pending = pending_q.first()
    if existing_pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending invitation already exists for this email",
        )

    # ------------------- create invitation -------------------
    raw_token = generate_invitation_token()
    inv = UserInvitation(
        tenant_id=tenant_id,
        email=payload.email,
        role_id=role_id,
        invited_by=current_user.id,
        invitation_token=hash_token(raw_token),
        expires_at=datetime.utcnow() + timedelta(days=7),
        is_global_admin=payload.is_global_admin,
        auth_provider=payload.auth_provider,
    )
    db.add(inv)
    try:
        db.commit()
    except IntegrityError as e:
        db.rollback()
        logger.warning("Admin invite IntegrityError (likely partial-unique race): %s", e)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A pending invitation already exists for this email",
        )
    db.refresh(inv)

    # ------------------- send email -------------------
    tenant_name = "Tsushin Platform"
    role_display = "Global Admin"
    if tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        tenant_name = tenant.name if tenant else tenant_name
    if role_id:
        role = db.query(Role).filter(Role.id == role_id).first()
        role_display = role.display_name if role else role_display

    invite_base_url = resolve_invitation_base_url(request, tenant if tenant_id else None)

    try:
        send_invitation(
            to_email=payload.email,
            inviter_name=current_user.full_name or current_user.email,
            tenant_name=tenant_name,
            role_name=role_display,
            invitation_token=raw_token,
            personal_message=payload.message,
            base_url=invite_base_url,
        )
    except Exception as e:
        # Email delivery failure should not roll back the invite; log and
        # surface via the response (caller still has the link).
        logger.warning("Failed to send invitation email to %s: %s", payload.email, e)

    # ------------------- audit -------------------
    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.USER_CREATE,
        target_tenant_id=tenant_id,
        resource_type="user_invitation",
        resource_id=str(inv.id),
        details={
            "email": payload.email,
            "is_global_admin": payload.is_global_admin,
            "auth_provider": payload.auth_provider,
            "role": payload.role,
        },
        request=request,
    )

    return _invitation_to_response(inv, db, raw_token=raw_token, request=request)


@router.get("", response_model=AdminInvitationListResponse, include_in_schema=False)
@router.get("/", response_model=AdminInvitationListResponse)
async def list_admin_invitations(
    is_global_admin: Optional[bool] = Query(None),
    tenant_id: Optional[str] = Query(None),
    email_contains: Optional[str] = Query(None),
    include_expired: bool = Query(False, description="Include expired pending invites"),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_global_admin()),
):
    """List pending invitations visible to global admins."""
    q = db.query(UserInvitation).filter(UserInvitation.accepted_at.is_(None))

    if not include_expired:
        q = q.filter(UserInvitation.expires_at > datetime.utcnow())

    if is_global_admin is not None:
        q = q.filter(UserInvitation.is_global_admin == is_global_admin)

    if tenant_id is not None:
        if tenant_id == "":
            q = q.filter(UserInvitation.tenant_id.is_(None))
        else:
            q = q.filter(UserInvitation.tenant_id == tenant_id)

    if email_contains:
        q = q.filter(UserInvitation.email.ilike(f"%{email_contains}%"))

    total = q.count()
    offset = (page - 1) * page_size
    rows = (
        q.order_by(UserInvitation.created_at.desc())
         .offset(offset)
         .limit(page_size)
         .all()
    )

    return AdminInvitationListResponse(
        invitations=[_invitation_to_response(inv, db) for inv in rows],
        total=total,
    )


@router.delete("/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_admin_invitation(
    invitation_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_global_admin()),
):
    """Cancel (hard-delete) a pending invitation."""
    inv = db.query(UserInvitation).filter(
        UserInvitation.id == invitation_id,
        UserInvitation.accepted_at.is_(None),
    ).first()
    if not inv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Invitation not found",
        )

    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.USER_DELETE,
        target_tenant_id=inv.tenant_id,
        resource_type="user_invitation",
        resource_id=str(inv.id),
        details={
            "email": inv.email,
            "is_global_admin": bool(inv.is_global_admin),
        },
        request=request,
    )

    db.delete(inv)
    db.commit()
