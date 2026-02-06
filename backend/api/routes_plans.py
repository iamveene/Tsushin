"""
Subscription Plans API Routes
Phase: User Management & SSO

Provides REST API endpoints for subscription plan management.
- Public endpoints for listing active plans
- Global admin endpoints for CRUD operations
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional, List
from datetime import datetime
import json

from db import get_db
from models_rbac import SubscriptionPlan, Tenant, User
from auth_dependencies import (
    get_current_user_required,
    get_current_user_optional,
    require_global_admin,
)
from services.audit_service import log_admin_action, AuditActions

router = APIRouter(prefix="/api/plans", tags=["plans"])


# Request/Response Models
class PlanFeatures(BaseModel):
    """Features included in a plan."""
    basic_support: bool = False
    priority_support: bool = False
    dedicated_support: bool = False
    playground: bool = True
    custom_tools: bool = False
    api_access: bool = False
    sso: bool = False
    audit_logs: bool = False
    advanced_analytics: bool = False
    sla: bool = False
    on_premise: bool = False
    custom_integrations: bool = False


class PlanCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50, pattern=r'^[a-z0-9_]+$')
    display_name: str = Field(..., min_length=2, max_length=100)
    description: Optional[str] = None
    price_monthly: int = Field(0, ge=0, description="Price in cents")
    price_yearly: int = Field(0, ge=0, description="Price in cents")
    max_users: int = Field(1, ge=-1, description="-1 for unlimited")
    max_agents: int = Field(1, ge=-1)
    max_monthly_requests: int = Field(1000, ge=-1)
    max_knowledge_docs: int = Field(10, ge=-1)
    max_flows: int = Field(5, ge=-1)
    max_mcp_instances: int = Field(1, ge=-1)
    features: Optional[List[str]] = None
    is_active: bool = True
    is_public: bool = True
    sort_order: int = 0


class PlanUpdate(BaseModel):
    display_name: Optional[str] = None
    description: Optional[str] = None
    price_monthly: Optional[int] = None
    price_yearly: Optional[int] = None
    max_users: Optional[int] = None
    max_agents: Optional[int] = None
    max_monthly_requests: Optional[int] = None
    max_knowledge_docs: Optional[int] = None
    max_flows: Optional[int] = None
    max_mcp_instances: Optional[int] = None
    features: Optional[List[str]] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None
    sort_order: Optional[int] = None


class PlanResponse(BaseModel):
    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    price_monthly: int
    price_yearly: int
    max_users: int
    max_agents: int
    max_monthly_requests: int
    max_knowledge_docs: int
    max_flows: int
    max_mcp_instances: int
    features: List[str] = []
    is_active: bool
    is_public: bool
    sort_order: int
    tenant_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class PlanListResponse(BaseModel):
    plans: List[PlanResponse]
    total: int


class PlanStatsResponse(BaseModel):
    total_plans: int
    active_plans: int
    public_plans: int
    tenants_per_plan: dict


# Helper functions
def plan_to_response(plan: SubscriptionPlan, db: Session, include_tenant_count: bool = False) -> PlanResponse:
    """Convert SubscriptionPlan model to response."""
    # Parse features JSON
    features = []
    if plan.features_json:
        try:
            features = json.loads(plan.features_json)
        except json.JSONDecodeError:
            features = []

    # Get tenant count if requested
    tenant_count = 0
    if include_tenant_count:
        tenant_count = db.query(Tenant).filter(
            Tenant.plan_id == plan.id,
            Tenant.deleted_at.is_(None)
        ).count()

    return PlanResponse(
        id=plan.id,
        name=plan.name,
        display_name=plan.display_name,
        description=plan.description,
        price_monthly=plan.price_monthly or 0,
        price_yearly=plan.price_yearly or 0,
        max_users=plan.max_users or 1,
        max_agents=plan.max_agents or 1,
        max_monthly_requests=plan.max_monthly_requests or 1000,
        max_knowledge_docs=plan.max_knowledge_docs or 10,
        max_flows=plan.max_flows or 5,
        max_mcp_instances=plan.max_mcp_instances or 1,
        features=features,
        is_active=plan.is_active,
        is_public=plan.is_public,
        sort_order=plan.sort_order or 0,
        tenant_count=tenant_count,
        created_at=plan.created_at.isoformat() if plan.created_at else None,
        updated_at=plan.updated_at.isoformat() if plan.updated_at else None,
    )


# Public Endpoints

@router.get("/", response_model=PlanListResponse)
async def list_plans(
    include_private: bool = Query(False, description="Include private plans (admin only)"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """
    List subscription plans.

    By default, only returns active public plans.
    Global admins can include private plans.
    """
    query = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True)

    # Only show public plans unless admin requests private
    if not include_private or not (current_user and current_user.is_global_admin):
        query = query.filter(SubscriptionPlan.is_public == True)

    plans = query.order_by(SubscriptionPlan.sort_order.asc()).all()

    # Include tenant counts only for admins
    include_counts = current_user and current_user.is_global_admin

    return PlanListResponse(
        plans=[plan_to_response(p, db, include_tenant_count=include_counts) for p in plans],
        total=len(plans),
    )


@router.get("/all", response_model=PlanListResponse)
async def list_all_plans(
    include_inactive: bool = Query(False, description="Include inactive plans"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    List all subscription plans including inactive (global admin only).
    """
    query = db.query(SubscriptionPlan)

    if not include_inactive:
        query = query.filter(SubscriptionPlan.is_active == True)

    plans = query.order_by(SubscriptionPlan.sort_order.asc()).all()

    return PlanListResponse(
        plans=[plan_to_response(p, db, include_tenant_count=True) for p in plans],
        total=len(plans),
    )


@router.get("/stats", response_model=PlanStatsResponse)
async def get_plan_stats(
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Get subscription plan statistics (global admin only).
    """
    total_plans = db.query(SubscriptionPlan).count()
    active_plans = db.query(SubscriptionPlan).filter(SubscriptionPlan.is_active == True).count()
    public_plans = db.query(SubscriptionPlan).filter(
        SubscriptionPlan.is_active == True,
        SubscriptionPlan.is_public == True
    ).count()

    # Get tenant count per plan
    plans = db.query(SubscriptionPlan).all()
    tenants_per_plan = {}
    for plan in plans:
        count = db.query(Tenant).filter(
            Tenant.plan_id == plan.id,
            Tenant.deleted_at.is_(None)
        ).count()
        tenants_per_plan[plan.name] = count

    return PlanStatsResponse(
        total_plans=total_plans,
        active_plans=active_plans,
        public_plans=public_plans,
        tenants_per_plan=tenants_per_plan,
    )


@router.get("/{plan_id}", response_model=PlanResponse)
async def get_plan(
    plan_id: int,
    current_user: Optional[User] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """
    Get a specific plan by ID.

    Public plans are accessible to all.
    Private plans require global admin access.
    """
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )

    # Check access for private plans
    if not plan.is_public and not (current_user and current_user.is_global_admin):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )

    include_counts = current_user and current_user.is_global_admin
    return plan_to_response(plan, db, include_tenant_count=include_counts)


# Admin Endpoints (Global Admin Only)

@router.post("/", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def create_plan(
    request: PlanCreate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Create a new subscription plan (global admin only).
    """
    # Check if plan name already exists
    existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == request.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plan with name '{request.name}' already exists"
        )

    # Create plan
    plan = SubscriptionPlan(
        name=request.name,
        display_name=request.display_name,
        description=request.description,
        price_monthly=request.price_monthly,
        price_yearly=request.price_yearly,
        max_users=request.max_users,
        max_agents=request.max_agents,
        max_monthly_requests=request.max_monthly_requests,
        max_knowledge_docs=request.max_knowledge_docs,
        max_flows=request.max_flows,
        max_mcp_instances=request.max_mcp_instances,
        features_json=json.dumps(request.features) if request.features else None,
        is_active=request.is_active,
        is_public=request.is_public,
        sort_order=request.sort_order,
    )

    db.add(plan)
    db.commit()
    db.refresh(plan)

    # Log admin action
    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.PLAN_CREATE,
        resource_type="subscription_plan",
        resource_id=str(plan.id),
        details={"plan_name": plan.name},
    )

    return plan_to_response(plan, db, include_tenant_count=True)


@router.put("/{plan_id}", response_model=PlanResponse)
async def update_plan(
    plan_id: int,
    request: PlanUpdate,
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Update a subscription plan (global admin only).

    Note: Changing limits does not retroactively affect existing tenants.
    """
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )

    # Update fields
    update_data = request.model_dump(exclude_unset=True)

    # Handle features separately (convert to JSON)
    if 'features' in update_data:
        update_data['features_json'] = json.dumps(update_data.pop('features'))

    for field, value in update_data.items():
        setattr(plan, field, value)

    plan.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(plan)

    # Log admin action
    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.PLAN_UPDATE,
        resource_type="subscription_plan",
        resource_id=str(plan.id),
        details={"updated_fields": list(update_data.keys())},
    )

    return plan_to_response(plan, db, include_tenant_count=True)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_plan(
    plan_id: int,
    force: bool = Query(False, description="Force delete even if tenants are using this plan"),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Delete (deactivate) a subscription plan (global admin only).

    By default, cannot delete plans that have active tenants.
    Use force=true to deactivate anyway (tenants keep their current limits).
    """
    plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()

    if not plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Plan not found"
        )

    # Check for tenants using this plan
    tenant_count = db.query(Tenant).filter(
        Tenant.plan_id == plan_id,
        Tenant.deleted_at.is_(None)
    ).count()

    if tenant_count > 0 and not force:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot delete plan: {tenant_count} tenant(s) are using this plan. Use force=true to deactivate anyway."
        )

    # Soft delete (deactivate)
    plan.is_active = False
    plan.is_public = False
    plan.updated_at = datetime.utcnow()
    db.commit()

    # Log admin action
    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.PLAN_DELETE,
        resource_type="subscription_plan",
        resource_id=str(plan.id),
        details={"plan_name": plan.name, "forced": force, "affected_tenants": tenant_count},
    )


@router.post("/{plan_id}/duplicate", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
async def duplicate_plan(
    plan_id: int,
    new_name: str = Query(..., min_length=2, max_length=50, pattern=r'^[a-z0-9_]+$'),
    new_display_name: str = Query(..., min_length=2, max_length=100),
    current_user: User = Depends(get_current_user_required),
    db: Session = Depends(get_db),
    _: None = Depends(require_global_admin()),
):
    """
    Duplicate an existing plan with a new name (global admin only).
    """
    # Get source plan
    source_plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_id).first()

    if not source_plan:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Source plan not found"
        )

    # Check if new name exists
    existing = db.query(SubscriptionPlan).filter(SubscriptionPlan.name == new_name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Plan with name '{new_name}' already exists"
        )

    # Create duplicate
    new_plan = SubscriptionPlan(
        name=new_name,
        display_name=new_display_name,
        description=source_plan.description,
        price_monthly=source_plan.price_monthly,
        price_yearly=source_plan.price_yearly,
        max_users=source_plan.max_users,
        max_agents=source_plan.max_agents,
        max_monthly_requests=source_plan.max_monthly_requests,
        max_knowledge_docs=source_plan.max_knowledge_docs,
        max_flows=source_plan.max_flows,
        max_mcp_instances=source_plan.max_mcp_instances,
        features_json=source_plan.features_json,
        is_active=False,  # Start as inactive
        is_public=False,
        sort_order=source_plan.sort_order + 1,
    )

    db.add(new_plan)
    db.commit()
    db.refresh(new_plan)

    # Log admin action
    log_admin_action(
        db=db,
        admin=current_user,
        action=AuditActions.PLAN_DUPLICATE,
        resource_type="subscription_plan",
        resource_id=str(new_plan.id),
        details={"duplicated_from": source_plan.name, "new_name": new_name},
    )

    return plan_to_response(new_plan, db, include_tenant_count=True)
