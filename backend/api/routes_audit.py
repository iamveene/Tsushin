"""
Audit Log Routes — Tenant-Scoped Audit Events (v0.6.0)
Provides query, export, and stats endpoints for tenant audit logs.
Uses regular JWT auth with audit.read / audit.export permissions.
"""

import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from db import get_db
from models_rbac import User
from auth_dependencies import require_permission, get_tenant_context, TenantContext
from services.audit_service import TenantAuditService

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class AuditEventResponse(BaseModel):
    id: int
    action: str
    user_id: Optional[int] = None
    user_name: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    details: Optional[dict] = None
    ip_address: Optional[str] = None
    channel: Optional[str] = None
    severity: str = "info"
    created_at: str

    class Config:
        from_attributes = True


class AuditEventsListResponse(BaseModel):
    events: List[AuditEventResponse]
    total: int


class AuditStatsResponse(BaseModel):
    events_today: int
    events_this_week: int
    critical_count: int
    top_actors: List[dict]
    by_category: Dict[str, int]


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/api/audit-logs", response_model=AuditEventsListResponse)
async def get_audit_events(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    action: Optional[str] = Query(None, description="Filter by action prefix (e.g. 'auth', 'agent.create')"),
    resource_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    severity: Optional[str] = Query(None, description="info, warning, or critical"),
    channel: Optional[str] = Query(None, description="web, api, whatsapp, telegram, system"),
    from_date: Optional[str] = Query(None, description="ISO date string"),
    to_date: Optional[str] = Query(None, description="ISO date string"),
    current_user: User = Depends(require_permission("audit.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    List tenant-scoped audit events with filtering and pagination.
    Requires audit.read permission.
    """
    # Parse date strings
    try:
        parsed_from = datetime.fromisoformat(from_date) if from_date else None
        parsed_to = datetime.fromisoformat(to_date) if to_date else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601 (e.g. 2026-01-15)")

    service = TenantAuditService(ctx.db)
    events = service.get_events(
        tenant_id=ctx.tenant_id,
        action=action,
        resource_type=resource_type,
        user_id=user_id,
        severity=severity,
        channel=channel,
        from_date=parsed_from,
        to_date=parsed_to,
        limit=limit,
        offset=offset,
    )
    total = service.get_event_count(
        tenant_id=ctx.tenant_id,
        action=action,
        resource_type=resource_type,
        user_id=user_id,
        severity=severity,
        channel=channel,
        from_date=parsed_from,
        to_date=parsed_to,
    )

    # Resolve user names
    user_cache: Dict[int, str] = {}
    event_list = []
    for e in events:
        user_name = None
        if e.user_id:
            if e.user_id not in user_cache:
                user = ctx.db.query(User).filter(User.id == e.user_id, User.tenant_id == ctx.tenant_id).first()
                user_cache[e.user_id] = (user.full_name or user.email) if user else f"User #{e.user_id}"
            user_name = user_cache[e.user_id]

        event_list.append(AuditEventResponse(
            id=e.id,
            action=e.action,
            user_id=e.user_id,
            user_name=user_name,
            resource_type=e.resource_type,
            resource_id=e.resource_id,
            details=e.details,
            ip_address=e.ip_address,
            channel=e.channel,
            severity=e.severity or "info",
            created_at=e.created_at.isoformat() if e.created_at else "",
        ))

    return AuditEventsListResponse(events=event_list, total=total)


@router.get("/api/audit-logs/stats", response_model=AuditStatsResponse)
async def get_audit_stats(
    current_user: User = Depends(require_permission("audit.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Get audit event summary statistics for the current tenant.
    Requires audit.read permission.
    """
    service = TenantAuditService(ctx.db)
    stats = service.get_stats(ctx.tenant_id)
    return AuditStatsResponse(**stats)


@router.get("/api/audit-logs/export")
async def export_audit_events(
    action: Optional[str] = Query(None),
    resource_type: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    severity: Optional[str] = Query(None),
    channel: Optional[str] = Query(None),
    from_date: Optional[str] = Query(None),
    to_date: Optional[str] = Query(None),
    current_user: User = Depends(require_permission("audit.export")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Export tenant audit events as CSV.
    Requires audit.export permission.
    """
    try:
        parsed_from = datetime.fromisoformat(from_date) if from_date else None
        parsed_to = datetime.fromisoformat(to_date) if to_date else None
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use ISO 8601 (e.g. 2026-01-15)")

    service = TenantAuditService(ctx.db)
    csv_generator = service.export_events_csv(
        tenant_id=ctx.tenant_id,
        action=action,
        resource_type=resource_type,
        user_id=user_id,
        severity=severity,
        channel=channel,
        from_date=parsed_from,
        to_date=parsed_to,
    )

    filename = f"audit_logs_{ctx.tenant_id}_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        csv_generator,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
