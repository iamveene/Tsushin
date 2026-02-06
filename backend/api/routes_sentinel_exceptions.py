"""
Sentinel Exceptions API Routes - Phase 20 Enhancement

CRUD operations for Sentinel exception rules.
Exceptions allow specific patterns/domains/tools to bypass LLM analysis.
"""

from typing import List, Optional
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session

from models import SentinelException
from models_rbac import User
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from services.sentinel_exceptions_service import SentinelExceptionsService

router = APIRouter(prefix="/sentinel/exceptions", tags=["Sentinel Exceptions"])

# =============================================================================
# Database Session Dependency
# =============================================================================

# Global engine reference (same pattern as routes_sentinel.py)
_engine = None


def set_engine(engine):
    """Set the database engine (called from app.py during startup)."""
    global _engine
    _engine = engine


def get_db():
    """Database session dependency."""
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class ExceptionCreate(BaseModel):
    """Request model for creating an exception."""
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    detection_types: str = Field(default="*", description="Comma-separated detection types or '*' for all")
    exception_type: str = Field(..., pattern="^(pattern|domain|tool|network_target)$")
    pattern: str = Field(..., min_length=1, description="The pattern to match")
    match_mode: str = Field(default="regex", pattern="^(regex|glob|exact)$")
    action: str = Field(default="skip_llm", pattern="^(skip_llm|allow)$")
    agent_id: Optional[int] = None
    priority: int = Field(default=100, ge=1, le=1000)


class ExceptionUpdate(BaseModel):
    """Request model for updating an exception."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = None
    detection_types: Optional[str] = None
    exception_type: Optional[str] = Field(None, pattern="^(pattern|domain|tool|network_target)$")
    pattern: Optional[str] = Field(None, min_length=1)
    match_mode: Optional[str] = Field(None, pattern="^(regex|glob|exact)$")
    action: Optional[str] = Field(None, pattern="^(skip_llm|allow)$")
    agent_id: Optional[int] = None
    priority: Optional[int] = Field(None, ge=1, le=1000)
    is_active: Optional[bool] = None


class ExceptionResponse(BaseModel):
    """Response model for an exception."""
    id: int
    tenant_id: Optional[str]
    agent_id: Optional[int]
    name: str
    description: Optional[str]
    detection_types: str
    exception_type: str
    pattern: str
    match_mode: str
    action: str
    is_active: bool
    priority: int
    created_by: Optional[int]
    created_at: datetime
    updated_by: Optional[int]
    updated_at: datetime

    class Config:
        from_attributes = True

    @field_serializer('created_at', 'updated_at')
    def serialize_datetimes(self, value: datetime, _info) -> str:
        if value is None:
            return None
        return value.isoformat() + "Z"


class ExceptionTestRequest(BaseModel):
    """Request model for testing an exception."""
    test_content: str = Field(..., min_length=1, max_length=5000)
    tool_name: Optional[str] = None
    target_domain: Optional[str] = None


class ExceptionTestResponse(BaseModel):
    """Response model for exception test results."""
    matches: bool
    would_skip_analysis: bool
    exception_id: int
    exception_name: str
    exception_type: str
    pattern: str
    match_mode: str
    extracted_targets: Optional[List[str]] = None
    extracted_domains: Optional[List[str]] = None


# =============================================================================
# API Endpoints
# =============================================================================

@router.get("", response_model=List[ExceptionResponse])
async def list_exceptions(
    agent_id: Optional[int] = Query(None, description="Filter by agent ID"),
    exception_type: Optional[str] = Query(None, description="Filter by exception type"),
    active_only: bool = Query(False, description="Only return active exceptions"),
    include_system: bool = Query(True, description="Include system-level exceptions"),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    List all exceptions accessible to the current tenant.

    Returns system-level exceptions (tenant_id=NULL) and tenant-specific exceptions.
    """
    service = SentinelExceptionsService(db, ctx.tenant_id)
    exceptions = service.list_exceptions(
        agent_id=agent_id,
        exception_type=exception_type,
        active_only=active_only,
        include_system=include_system,
    )
    return exceptions


@router.get("/{exception_id}", response_model=ExceptionResponse)
async def get_exception(
    exception_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get a specific exception by ID."""
    service = SentinelExceptionsService(db, ctx.tenant_id)
    exception = service.get_exception_by_id(exception_id)
    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found")
    return exception


@router.post("", response_model=ExceptionResponse)
async def create_exception(
    data: ExceptionCreate,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Create a new exception rule.

    Requires org.settings.write permission.
    """
    service = SentinelExceptionsService(db, ctx.tenant_id)
    exception = service.create_exception(
        name=data.name,
        description=data.description,
        detection_types=data.detection_types,
        exception_type=data.exception_type,
        pattern=data.pattern,
        match_mode=data.match_mode,
        action=data.action,
        agent_id=data.agent_id,
        priority=data.priority,
        created_by=current_user.id,
    )
    return exception


@router.put("/{exception_id}", response_model=ExceptionResponse)
async def update_exception(
    exception_id: int,
    data: ExceptionUpdate,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Update an exception rule.

    Cannot update system-level exceptions (tenant_id=NULL).
    Requires org.settings.write permission.
    """
    service = SentinelExceptionsService(db, ctx.tenant_id)

    # Check if trying to update a system exception
    existing = service.get_exception_by_id(exception_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Exception not found")

    if existing.tenant_id is None:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify system-level exceptions"
        )

    exception = service.update_exception(
        exception_id=exception_id,
        updated_by=current_user.id,
        **data.model_dump(exclude_unset=True),
    )
    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found or access denied")
    return exception


@router.delete("/{exception_id}")
async def delete_exception(
    exception_id: int,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Delete an exception rule.

    Cannot delete system-level exceptions (tenant_id=NULL).
    Requires org.settings.write permission.
    """
    service = SentinelExceptionsService(db, ctx.tenant_id)

    # Check if trying to delete a system exception
    existing = service.get_exception_by_id(exception_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Exception not found")

    if existing.tenant_id is None:
        raise HTTPException(
            status_code=403,
            detail="Cannot delete system-level exceptions"
        )

    if not service.delete_exception(exception_id):
        raise HTTPException(status_code=404, detail="Exception not found or access denied")

    return {"deleted": True, "id": exception_id}


@router.post("/{exception_id}/test", response_model=ExceptionTestResponse)
async def test_exception(
    exception_id: int,
    data: ExceptionTestRequest,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Test if content would match an exception rule.

    Useful for validating patterns before saving or debugging.
    """
    service = SentinelExceptionsService(db, ctx.tenant_id)
    result = service.test_exception(
        exception_id=exception_id,
        test_content=data.test_content,
        tool_name=data.tool_name,
        target_domain=data.target_domain,
    )

    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])

    return result


@router.patch("/{exception_id}/toggle", response_model=ExceptionResponse)
async def toggle_exception(
    exception_id: int,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Toggle exception active status.

    Requires org.settings.write permission.
    """
    service = SentinelExceptionsService(db, ctx.tenant_id)

    # Check if trying to toggle a system exception
    existing = service.get_exception_by_id(exception_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Exception not found")

    # Allow toggling system exceptions (they can be disabled tenant-wide)
    # But only for viewing purposes - the actual exception remains in system config

    exception = service.toggle_exception(
        exception_id=exception_id,
        updated_by=current_user.id,
    )

    if not exception:
        raise HTTPException(status_code=404, detail="Exception not found or access denied")

    return exception
