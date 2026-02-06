"""
Phase 7.2: Token Analytics API Routes
Phase 7.9.2: Added tenant filtering for multi-tenancy support
Endpoints for viewing token consumption statistics and costs.
"""

from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from models import TokenUsage, Agent, Contact
from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/analytics", tags=["analytics"])

# Global engine reference (set by main app)
_engine = None

def set_engine(engine):
    """Set the database engine for this router"""
    global _engine
    _engine = engine

# Dependency to get database session
def get_db():
    """Get database session"""
    from sqlalchemy.orm import sessionmaker
    if _engine is None:
        raise RuntimeError("Database engine not initialized")
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_tenant_agent_ids(db: Session, ctx: TenantContext) -> List[int]:
    """
    Get list of agent IDs accessible to the current tenant.

    Phase 7.9.2: Tenant isolation for analytics.
    Returns all agent IDs for global admin, or only tenant's agents for regular users.
    """
    if ctx.is_global_admin:
        # Global admin can see all agents
        agents = db.query(Agent.id).all()
    else:
        # Filter by tenant - include tenant's agents AND shared (NULL tenant_id)
        from sqlalchemy import or_
        agents = db.query(Agent.id).filter(
            or_(
                Agent.tenant_id == ctx.tenant_id,
                Agent.tenant_id.is_(None)
            )
        ).all()

    return [a.id for a in agents]


def verify_agent_access(agent_id: int, db: Session, ctx: TenantContext) -> Agent:
    """
    Verify agent exists and user has access to it.

    Phase 7.9.2: Tenant isolation for agent-related endpoints.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    return agent


@router.get("/token-usage/summary")
async def get_token_usage_summary(
    days: int = Query(default=30, ge=1, le=365, description="Number of days to analyze"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get overall token usage summary for the specified time period.

    Returns:
        - total_tokens: Total tokens consumed
        - total_cost: Estimated cost in USD
        - total_requests: Number of AI requests
        - operation_breakdown: Usage by operation type
        - model_breakdown: Usage by model
        - daily_trend: Daily usage trend

    Phase 7.9.2: Returns usage only for agents in user's tenant.
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Get tenant's agent IDs
    tenant_agent_ids = get_tenant_agent_ids(db, ctx)

    # Query only usage for tenant's agents (or NULL agent_id for system operations)
    query = db.query(TokenUsage).filter(TokenUsage.created_at >= since)

    if not ctx.is_global_admin:
        from sqlalchemy import or_
        query = query.filter(
            or_(
                TokenUsage.agent_id.in_(tenant_agent_ids) if tenant_agent_ids else False,
                TokenUsage.agent_id.is_(None)  # System operations
            )
        )

    usages = query.all()

    if not usages:
        return {
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_requests": 0,
            "operation_breakdown": [],
            "model_breakdown": [],
            "daily_trend": [],
        }

    total_tokens = sum(u.total_tokens for u in usages)
    total_cost = sum(u.estimated_cost for u in usages)

    # Operation breakdown
    operation_stats = {}
    for u in usages:
        key = u.operation_type
        if key not in operation_stats:
            operation_stats[key] = {"tokens": 0, "cost": 0.0, "count": 0}
        operation_stats[key]["tokens"] += u.total_tokens
        operation_stats[key]["cost"] += u.estimated_cost
        operation_stats[key]["count"] += 1

    operation_breakdown = [
        {"operation": k, **v}
        for k, v in sorted(operation_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
    ]

    # Model breakdown
    model_stats = {}
    for u in usages:
        key = f"{u.model_provider}/{u.model_name}"
        if key not in model_stats:
            model_stats[key] = {"tokens": 0, "cost": 0.0, "count": 0}
        model_stats[key]["tokens"] += u.total_tokens
        model_stats[key]["cost"] += u.estimated_cost
        model_stats[key]["count"] += 1

    model_breakdown = [
        {"model": k, **v}
        for k, v in sorted(model_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
    ]

    # Daily trend
    daily_stats = {}
    for u in usages:
        day = u.created_at.date().isoformat()
        if day not in daily_stats:
            daily_stats[day] = {"tokens": 0, "cost": 0.0, "count": 0}
        daily_stats[day]["tokens"] += u.total_tokens
        daily_stats[day]["cost"] += u.estimated_cost
        daily_stats[day]["count"] += 1

    daily_trend = [
        {"date": k, **v}
        for k, v in sorted(daily_stats.items())
    ]

    return {
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "total_requests": len(usages),
        "operation_breakdown": operation_breakdown,
        "model_breakdown": model_breakdown,
        "daily_trend": daily_trend,
    }


@router.get("/token-usage/by-agent")
async def get_token_usage_by_agent(
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get token usage summary for all agents.

    Returns list of agents with:
        - agent_id
        - agent_name
        - total_tokens
        - total_cost
        - total_requests

    Phase 7.9.2: Returns usage only for agents in user's tenant.
    """
    since = datetime.utcnow() - timedelta(days=days)

    # Get tenant's agent IDs
    tenant_agent_ids = get_tenant_agent_ids(db, ctx)

    # Query agent usage grouped - filtered by tenant agents
    query = db.query(
        TokenUsage.agent_id,
        func.sum(TokenUsage.total_tokens).label("total_tokens"),
        func.sum(TokenUsage.estimated_cost).label("total_cost"),
        func.count(TokenUsage.id).label("total_requests"),
    ).filter(
        TokenUsage.created_at >= since,
        TokenUsage.agent_id.isnot(None)
    )

    if not ctx.is_global_admin and tenant_agent_ids:
        query = query.filter(TokenUsage.agent_id.in_(tenant_agent_ids))

    results = query.group_by(
        TokenUsage.agent_id
    ).order_by(
        desc("total_cost")
    ).all()

    summaries = []
    for row in results:
        agent = db.query(Agent).filter(Agent.id == row.agent_id).first()
        if agent:
            contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
            agent_name = contact.friendly_name if contact else f"Agent {agent.id}"
        else:
            agent_name = f"Agent {row.agent_id}"

        summaries.append({
            "agent_id": row.agent_id,
            "agent_name": agent_name,
            "total_tokens": row.total_tokens,
            "total_cost": float(row.total_cost),
            "total_requests": row.total_requests,
        })

    return {"agents": summaries, "days": days}


@router.get("/token-usage/agent/{agent_id}")
async def get_agent_token_usage(
    agent_id: int,
    days: int = Query(default=30, ge=1, le=365),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get detailed token usage statistics for a specific agent.

    Returns:
        - agent_id
        - total_tokens
        - total_cost
        - total_requests
        - skill_breakdown: Usage by skill
        - model_breakdown: Usage by model

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    since = datetime.utcnow() - timedelta(days=days)

    usages = db.query(TokenUsage).filter(
        TokenUsage.agent_id == agent_id,
        TokenUsage.created_at >= since
    ).all()

    if not usages:
        return {
            "agent_id": agent_id,
            "total_tokens": 0,
            "total_cost": 0.0,
            "total_requests": 0,
            "skill_breakdown": [],
            "model_breakdown": [],
        }

    total_tokens = sum(u.total_tokens for u in usages)
    total_cost = sum(u.estimated_cost for u in usages)

    # Skill breakdown
    skill_stats = {}
    for u in usages:
        key = u.skill_type or "general"
        if key not in skill_stats:
            skill_stats[key] = {"tokens": 0, "cost": 0.0, "count": 0}
        skill_stats[key]["tokens"] += u.total_tokens
        skill_stats[key]["cost"] += u.estimated_cost
        skill_stats[key]["count"] += 1

    skill_breakdown = [
        {"skill": k, **v}
        for k, v in sorted(skill_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
    ]

    # Model breakdown
    model_stats = {}
    for u in usages:
        key = f"{u.model_provider}/{u.model_name}"
        if key not in model_stats:
            model_stats[key] = {"tokens": 0, "cost": 0.0, "count": 0}
        model_stats[key]["tokens"] += u.total_tokens
        model_stats[key]["cost"] += u.estimated_cost
        model_stats[key]["count"] += 1

    model_breakdown = [
        {"model": k, **v}
        for k, v in sorted(model_stats.items(), key=lambda x: x[1]["cost"], reverse=True)
    ]

    return {
        "agent_id": agent_id,
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "total_requests": len(usages),
        "skill_breakdown": skill_breakdown,
        "model_breakdown": model_breakdown,
    }


@router.get("/token-usage/recent")
async def get_recent_token_usage(
    limit: int = Query(default=100, ge=1, le=500),
    agent_id: Optional[int] = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("analytics.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get recent token usage records.

    Args:
        limit: Maximum number of records (1-500)
        agent_id: Filter by agent (optional)

    Returns list of usage records with:
        - id
        - timestamp
        - agent_name
        - operation_type
        - skill_type
        - model
        - total_tokens
        - estimated_cost

    Phase 7.9.2: Returns usage only for agents in user's tenant.
    """
    # If specific agent_id provided, verify access
    if agent_id:
        verify_agent_access(agent_id, db, ctx)

    # Get tenant's agent IDs
    tenant_agent_ids = get_tenant_agent_ids(db, ctx)

    query = db.query(TokenUsage).order_by(desc(TokenUsage.created_at)).limit(limit)

    if agent_id:
        query = query.filter(TokenUsage.agent_id == agent_id)
    elif not ctx.is_global_admin and tenant_agent_ids:
        # Filter by tenant's agents (include system operations with NULL agent_id)
        from sqlalchemy import or_
        query = query.filter(
            or_(
                TokenUsage.agent_id.in_(tenant_agent_ids),
                TokenUsage.agent_id.is_(None)
            )
        )

    usages = query.all()

    records = []
    for u in usages:
        agent_name = "System"
        if u.agent_id:
            agent = db.query(Agent).filter(Agent.id == u.agent_id).first()
            if agent:
                contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
                agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

        records.append({
            "id": u.id,
            "timestamp": u.created_at.isoformat(),
            "agent_name": agent_name,
            "operation_type": u.operation_type,
            "skill_type": u.skill_type,
            "model": f"{u.model_provider}/{u.model_name}",
            "total_tokens": u.total_tokens,
            "estimated_cost": u.estimated_cost,
        })

    return {"records": records, "count": len(records)}
