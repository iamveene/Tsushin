"""
Tenant Management API Routes
Phase 7.9: Multi-tenancy support

Provides REST API endpoints for tenant (organization) management.
Global admin only for most operations.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import Optional, List
from datetime import datetime
import re

from db import get_db
from models_rbac import Tenant, User, UserRole, Role
from auth_dependencies import (
    get_current_user_required,
    require_global_admin,
    TenantContext,
    get_tenant_context
)
from auth_service import AuthService
from auth_utils import hash_password
from services.audit_service import log_admin_action, AuditActions

router = APIRouter(prefix="/api/tenants", tags=["tenants"])


# Request/Response Models
class TenantCreate(BaseModel):
    name: str
    owner_email: EmailStr
    owner_password: str
    owner_name: str
    plan: str = "free"
    max_users: int = 5
    max_agents: int = 5
    max_monthly_requests: int = 10000


class TenantUpdate(BaseModel):
    name: Optional[str] = None
    plan: Optional[str] = None
    max_users: Optional[int] = None
    max_agents: Optional[int] = None
    max_monthly_requests: Optional[int] = None
    status: Optional[str] = None  # active, suspended, trial


class TenantResponse(BaseModel):
    id: str
    name: str
    slug: str
    plan: str
    max_users: int
    max_agents: int
    max_monthly_requests: int
    is_active: bool
    status: str
    user_count: int = 0
    agent_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class TenantListResponse(BaseModel):
    tenants: List[TenantResponse]
    total: int
    page: int
    page_size: int


# Helper functions
def generate_tenant_id() -> str:
    """Generate unique tenant ID."""
    return f"tenant_{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}"


def generate_slug(name: str, db: Session) -> str:
    """Generate unique slug from tenant name."""
    base_slug = re.sub(r'[^a-z0-9-]', '', name.lower().replace(' ', '-'))[:50]
    slug = base_slug

    # Check uniqueness
    counter = 1
    while db.query(Tenant).filter(Tenant.slug == slug).first():
        slug = f"{base_slug}-{counter}"
        counter += 1

    return slug


def tenant_to_response(tenant: Tenant, db: Session) -> TenantResponse:
    """Convert Tenant model to response with counts."""
    from models import Agent

    user_count = db.query(User).filter(
        User.tenant_id == tenant.id,
        User.deleted_at.is_(None)
    ).count()

    agent_count = db.query(Agent).filter(
        Agent.tenant_id == tenant.id,
        Agent.is_active == True
    ).count()

    return TenantResponse(
        id=tenant.id,
        name=tenant.name,
        slug=tenant.slug,
        plan=tenant.plan,
        max_users=tenant.max_users,
        max_agents=tenant.max_agents,
        max_monthly_requests=tenant.max_monthly_requests,
        is_active=tenant.is_active,
        status=tenant.status,
        user_count=user_count,
        agent_count=agent_count,
        created_at=tenant.created_at.isoformat() if tenant.created_at else None,
        updated_at=tenant.updated_at.isoformat() if tenant.updated_at else None,
    )


# Endpoints

@router.get("/", response_model=TenantListResponse)
async def list_tenants(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: Optional[str] = None,
    status: Optional[str] = None,
    plan: Optional[str] = None,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    List all tenants (global admin only).

    Supports pagination, search, and filtering.
    """
    query = db.query(Tenant).filter(Tenant.deleted_at.is_(None))

    # Search by name or slug
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            or_(
                Tenant.name.ilike(search_term),
                Tenant.slug.ilike(search_term)
            )
        )

    # Filter by status
    if status:
        query = query.filter(Tenant.status == status)

    # Filter by plan
    if plan:
        query = query.filter(Tenant.plan == plan)

    # Get total count
    total = query.count()

    # Pagination
    offset = (page - 1) * page_size
    tenants = query.order_by(Tenant.created_at.desc()).offset(offset).limit(page_size).all()

    return TenantListResponse(
        tenants=[tenant_to_response(t, db) for t in tenants],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    request: TenantCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Create a new tenant with owner (global admin only).

    Creates:
    - Tenant record
    - Owner user account
    - User role assignment
    """
    # Check if owner email already exists
    existing_user = db.query(User).filter(User.email == request.owner_email).first()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Generate tenant ID and slug
    tenant_id = generate_tenant_id()
    slug = generate_slug(request.name, db)

    # Create tenant
    tenant = Tenant(
        id=tenant_id,
        name=request.name,
        slug=slug,
        plan=request.plan,
        max_users=request.max_users,
        max_agents=request.max_agents,
        max_monthly_requests=request.max_monthly_requests,
        is_active=True,
        status="active",
        created_by_global_admin=current_user.id,
    )
    db.add(tenant)
    db.flush()

    # Create owner user
    owner = User(
        tenant_id=tenant_id,
        email=request.owner_email,
        password_hash=hash_password(request.owner_password),
        full_name=request.owner_name,
        is_global_admin=False,
        is_active=True,
        email_verified=True,  # Admin-created accounts are pre-verified
    )
    db.add(owner)
    db.flush()

    # Assign owner role
    owner_role = db.query(Role).filter(Role.name == "owner").first()
    if owner_role:
        user_role = UserRole(
            user_id=owner.id,
            role_id=owner_role.id,
            tenant_id=tenant_id,
            assigned_by=current_user.id,
        )
        db.add(user_role)

    db.commit()
    db.refresh(tenant)

    # Log the action
    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.TENANT_CREATE,
        target_tenant_id=tenant_id,
        resource_type="tenant",
        resource_id=tenant_id,
        details={
            "tenant_name": request.name,
            "owner_email": request.owner_email,
            "plan": request.plan,
        }
    )

    return tenant_to_response(tenant, db)


@router.get("/current", response_model=TenantResponse)
async def get_current_tenant(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Get current user's tenant details.

    Returns the tenant the current user belongs to.
    """
    if ctx.is_global_admin and not ctx.tenant_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Global admins must specify a tenant"
        )

    tenant = ctx.db.query(Tenant).filter(Tenant.id == ctx.tenant_id).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    return tenant_to_response(tenant, ctx.db)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    Get tenant details by ID.

    - Global admins can view any tenant
    - Regular users can only view their own tenant
    """
    tenant = db.query(Tenant).filter(
        Tenant.id == tenant_id,
        Tenant.deleted_at.is_(None)
    ).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    # Check access
    if not current_user.is_global_admin and current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this tenant"
        )

    return tenant_to_response(tenant, db)


@router.put("/{tenant_id}", response_model=TenantResponse)
async def update_tenant(
    tenant_id: str,
    request: TenantUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    Update tenant details.

    - Global admins can update any tenant
    - Tenant owners can update their own tenant (limited fields)
    """
    tenant = db.query(Tenant).filter(
        Tenant.id == tenant_id,
        Tenant.deleted_at.is_(None)
    ).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    # Check access
    is_owner = False
    if not current_user.is_global_admin:
        if current_user.tenant_id != tenant_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have access to this tenant"
            )

        # Check if user is owner
        user_role = db.query(UserRole).join(Role).filter(
            UserRole.user_id == current_user.id,
            UserRole.tenant_id == tenant_id,
            Role.name == "owner"
        ).first()

        if not user_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only tenant owners can update tenant settings"
            )
        is_owner = True

    # Apply updates
    if request.name is not None:
        tenant.name = request.name

    # Only global admins can change these
    if current_user.is_global_admin:
        if request.plan is not None:
            tenant.plan = request.plan
        if request.max_users is not None:
            tenant.max_users = request.max_users
        if request.max_agents is not None:
            tenant.max_agents = request.max_agents
        if request.max_monthly_requests is not None:
            tenant.max_monthly_requests = request.max_monthly_requests
        if request.status is not None:
            tenant.status = request.status
            tenant.is_active = request.status == "active"

    tenant.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(tenant)

    return tenant_to_response(tenant, db)


@router.delete("/{tenant_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_tenant(
    tenant_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Soft delete a tenant (global admin only).

    This marks the tenant as deleted but preserves data.
    """
    tenant = db.query(Tenant).filter(
        Tenant.id == tenant_id,
        Tenant.deleted_at.is_(None)
    ).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    # Soft delete
    tenant.deleted_at = datetime.utcnow()
    tenant.is_active = False
    tenant.status = "deleted"

    # Also deactivate all users
    db.query(User).filter(User.tenant_id == tenant_id).update({
        "is_active": False,
        "deleted_at": datetime.utcnow()
    })

    db.commit()


@router.get("/{tenant_id}/stats")
async def get_tenant_stats(
    tenant_id: str,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
):
    """
    Get tenant usage statistics.

    - Global admins can view any tenant stats
    - Regular users can only view their own tenant stats
    """
    from models import Agent, AgentRun

    # Check access
    if not current_user.is_global_admin and current_user.tenant_id != tenant_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have access to this tenant"
        )

    tenant = db.query(Tenant).filter(
        Tenant.id == tenant_id,
        Tenant.deleted_at.is_(None)
    ).first()

    if not tenant:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Tenant not found"
        )

    # Calculate stats
    user_count = db.query(User).filter(
        User.tenant_id == tenant_id,
        User.deleted_at.is_(None)
    ).count()

    agent_count = db.query(Agent).filter(
        Agent.tenant_id == tenant_id,
        Agent.is_active == True
    ).count()

    # Get request count for current month
    from datetime import datetime
    now = datetime.utcnow()
    month_start = datetime(now.year, now.month, 1)

    monthly_requests = db.query(AgentRun).join(
        Agent, Agent.id == AgentRun.agent_id
    ).filter(
        Agent.tenant_id == tenant_id,
        AgentRun.created_at >= month_start
    ).count()

    return {
        "tenant_id": tenant_id,
        "users": {
            "current": user_count,
            "limit": tenant.max_users,
            "percentage": round((user_count / tenant.max_users) * 100, 1) if tenant.max_users > 0 else 0,
        },
        "agents": {
            "current": agent_count,
            "limit": tenant.max_agents,
            "percentage": round((agent_count / tenant.max_agents) * 100, 1) if tenant.max_agents > 0 else 0,
        },
        "monthly_requests": {
            "current": monthly_requests,
            "limit": tenant.max_monthly_requests,
            "percentage": round((monthly_requests / tenant.max_monthly_requests) * 100, 1) if tenant.max_monthly_requests > 0 else 0,
        },
        "plan": tenant.plan,
        "status": tenant.status,
    }
