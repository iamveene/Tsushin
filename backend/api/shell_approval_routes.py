"""
Shell Approval Routes - Phase 5: Security & Approval Workflow

REST API endpoints for managing shell command approvals:
- List pending approvals
- Approve/reject commands
- Get approval statistics
"""

import logging
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission,
    get_current_user_required
)
from services.shell_approval_service import get_approval_service
from services.shell_security_service import get_security_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/shell/approvals", tags=["Shell Approvals"])

# Global engine reference (set by main app.py)
_engine = None


def set_engine(engine):
    """Set the global engine reference"""
    global _engine
    _engine = engine


def get_db():
    """Dependency to get database session"""
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Request/Response Models
# ============================================================================

class PendingApprovalResponse(BaseModel):
    """Response model for pending approval."""
    command_id: str
    shell_id: int
    commands: List[str]
    initiated_by: str
    queued_at: str
    expires_at: str
    time_remaining_seconds: int
    risk_level: str
    security_warnings: List[str]


class ApprovalDecisionRequest(BaseModel):
    """Request model for approval decision."""
    notes: Optional[str] = Field(None, max_length=500, description="Optional notes")


class RejectionDecisionRequest(BaseModel):
    """Request model for rejection decision."""
    reason: str = Field(..., min_length=1, max_length=500, description="Rejection reason")


class ApprovalDecisionResponse(BaseModel):
    """Response model for approval decision."""
    success: bool
    command_id: str
    status: str
    message: str


class SecurityCheckRequest(BaseModel):
    """Request model for security check."""
    commands: List[str] = Field(..., min_items=1, description="Commands to check")


class SecurityCheckResponse(BaseModel):
    """Response model for security check."""
    allowed: bool
    risk_level: str
    requires_approval: bool
    blocked_reason: Optional[str]
    matched_patterns: List[str]
    warnings: List[str]
    summary: str


class ApprovalStatsResponse(BaseModel):
    """Response model for approval statistics."""
    pending_count: int
    approved_today: int
    rejected_today: int
    expired_today: int
    average_approval_time_seconds: Optional[float]


# ============================================================================
# Approval Endpoints
# ============================================================================

@router.get("/pending", response_model=List[PendingApprovalResponse])
async def list_pending_approvals(
    shell_id: Optional[int] = Query(None, description="Filter by shell integration"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.approve")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List all pending approval requests for the tenant.

    Requires shell.approve permission.
    """
    service = get_approval_service(db)
    pending = service.get_pending_approvals(ctx.tenant_id, shell_id)

    return [PendingApprovalResponse(**p) for p in pending]


@router.post("/{command_id}/approve", response_model=ApprovalDecisionResponse)
async def approve_command(
    command_id: str,
    request: ApprovalDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.approve")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Approve a pending shell command.

    Requires shell.approve permission.
    """
    service = get_approval_service(db)

    # Verify command belongs to tenant
    from models import ShellCommand
    command = db.query(ShellCommand).filter(
        ShellCommand.id == command_id
    ).first()

    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    if not ctx.can_access_resource(command.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    result = service.approve_command(
        command_id=command_id,
        approved_by=current_user.email,
        notes=request.notes
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return ApprovalDecisionResponse(
        success=result["success"],
        command_id=result["command_id"],
        status=result["status"],
        message=result["message"]
    )


@router.post("/{command_id}/reject", response_model=ApprovalDecisionResponse)
async def reject_command(
    command_id: str,
    request: RejectionDecisionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.approve")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Reject a pending shell command.

    Requires shell.approve permission.
    """
    service = get_approval_service(db)

    # Verify command belongs to tenant
    from models import ShellCommand
    command = db.query(ShellCommand).filter(
        ShellCommand.id == command_id
    ).first()

    if not command:
        raise HTTPException(status_code=404, detail="Command not found")

    if not ctx.can_access_resource(command.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    result = service.reject_command(
        command_id=command_id,
        rejected_by=current_user.email,
        reason=request.reason
    )

    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])

    return ApprovalDecisionResponse(
        success=result["success"],
        command_id=result["command_id"],
        status=result["status"],
        message=result["message"]
    )


@router.get("/stats", response_model=ApprovalStatsResponse)
async def get_approval_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get approval workflow statistics.

    Requires shell.read permission.
    """
    from models import ShellCommand
    from datetime import date

    today_start = datetime.combine(date.today(), datetime.min.time())

    # Count pending
    pending_count = db.query(ShellCommand).filter(
        ShellCommand.tenant_id == ctx.tenant_id,
        ShellCommand.status == "pending_approval"
    ).count()

    # Count approved today
    approved_today = db.query(ShellCommand).filter(
        ShellCommand.tenant_id == ctx.tenant_id,
        ShellCommand.approved_at >= today_start,
        ShellCommand.approved_at.isnot(None)
    ).count()

    # Count rejected today
    rejected_today = db.query(ShellCommand).filter(
        ShellCommand.tenant_id == ctx.tenant_id,
        ShellCommand.status == "rejected",
        ShellCommand.completed_at >= today_start
    ).count()

    # Count expired today
    expired_today = db.query(ShellCommand).filter(
        ShellCommand.tenant_id == ctx.tenant_id,
        ShellCommand.status == "expired",
        ShellCommand.completed_at >= today_start
    ).count()

    # Calculate average approval time (for approved commands today)
    approved_commands = db.query(ShellCommand).filter(
        ShellCommand.tenant_id == ctx.tenant_id,
        ShellCommand.approved_at >= today_start,
        ShellCommand.approved_at.isnot(None)
    ).all()

    avg_approval_time = None
    if approved_commands:
        total_time = sum(
            (cmd.approved_at - cmd.queued_at).total_seconds()
            for cmd in approved_commands
            if cmd.approved_at and cmd.queued_at
        )
        avg_approval_time = total_time / len(approved_commands)

    return ApprovalStatsResponse(
        pending_count=pending_count,
        approved_today=approved_today,
        rejected_today=rejected_today,
        expired_today=expired_today,
        average_approval_time_seconds=avg_approval_time
    )


# ============================================================================
# Security Check Endpoint (Preview)
# ============================================================================

@router.post("/check-security", response_model=SecurityCheckResponse)
async def check_command_security(
    request: SecurityCheckRequest,
    current_user: User = Depends(require_permission("shell.read")),
):
    """
    Check commands for security risks without executing.

    Use this to preview what risk level and warnings a command would trigger.
    """
    security = get_security_service()

    allowed, result = security.check_commands(request.commands)

    return SecurityCheckResponse(
        allowed=allowed,
        risk_level=result.risk_level.value,
        requires_approval=result.requires_approval,
        blocked_reason=result.blocked_reason,
        matched_patterns=result.matched_patterns,
        warnings=result.warnings,
        summary=security.get_risk_summary(result)
    )


# ============================================================================
# Admin Maintenance Endpoints
# ============================================================================

@router.post("/expire-old")
async def expire_old_approvals(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("shell.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Manually expire old pending approvals.

    This is normally handled automatically, but can be triggered manually.
    """
    service = get_approval_service(db)
    count = service.expire_old_approvals()

    return {"expired_count": count, "message": f"Expired {count} pending approvals"}
