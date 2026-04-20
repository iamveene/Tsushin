"""
Agent-to-Agent Communication API Routes (v0.6.0 Item 15)

Provides REST API endpoints for:
- Communication session listing and detail
- Permission rule CRUD
- Communication statistics
"""

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session

from models import (
    Agent,
    Contact,
    AgentCommunicationPermission,
    AgentCommunicationSession,
    AgentCommunicationMessage,
)
from models_rbac import User
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from services.agent_communication_service import AgentCommunicationService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent-communication", tags=["Agent Communication"])

# Global engine reference
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
        try:
            db.rollback()
        except Exception:
            pass
        db.close()


# =============================================================================
# Helpers
# =============================================================================

def _resolve_agent_name(db: Session, agent_id: int) -> str:
    """Resolve an agent's friendly name via Agent -> Contact join."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        return f"Agent #{agent_id} (deleted)"
    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
    if not contact:
        return f"Agent #{agent_id}"
    return contact.friendly_name


def _build_agent_name_map(db: Session, agent_ids: set, tenant_id: str = None) -> dict:
    """Batch-resolve agent IDs to friendly names to avoid N+1 queries."""
    if not agent_ids:
        return {}
    q = (
        db.query(Agent.id, Contact.friendly_name)
        .join(Contact, Contact.id == Agent.contact_id)
        .filter(Agent.id.in_(agent_ids))
    )
    if tenant_id:
        q = q.filter(Agent.tenant_id == tenant_id)
    rows = q.all()
    name_map = {row[0]: row[1] for row in rows}
    # Fill in any missing (deleted agents)
    for aid in agent_ids:
        if aid not in name_map:
            name_map[aid] = f"Agent #{aid} (deleted)"
    return name_map


# Valid session statuses for query validation
VALID_SESSION_STATUSES = {"pending", "in_progress", "completed", "failed", "timeout", "blocked"}


# =============================================================================
# Pydantic Schemas
# =============================================================================

class SessionMessageResponse(BaseModel):
    """Response model for a single message in a communication session."""
    id: int
    session_id: int
    from_agent_id: int
    from_agent_name: str = ""
    to_agent_id: int
    to_agent_name: str = ""
    direction: str
    message_preview: Optional[str] = None
    message_content: Optional[str] = None
    model_used: Optional[str] = None
    execution_time_ms: Optional[int] = None
    sentinel_analyzed: bool = False
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_serializer("created_at")
    def serialize_created_at(self, value: datetime, _info) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat() + "Z"


class SessionListItem(BaseModel):
    """Response model for session list (compact)."""
    id: int
    initiator_agent_id: int
    initiator_agent_name: str = ""
    target_agent_id: int
    target_agent_name: str = ""
    session_type: str
    status: str
    depth: int
    max_depth: int = 3
    total_messages: int
    original_message_preview: Optional[str] = None
    error_text: Optional[str] = None
    parent_session_id: Optional[int] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_serializer("started_at", "completed_at")
    def serialize_datetimes(self, value: datetime, _info) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat() + "Z"


class SessionDetailResponse(SessionListItem):
    """Response model for session detail — includes messages."""
    max_depth: int = 3
    timeout_seconds: int = 30
    original_sender_key: Optional[str] = None
    messages: List[SessionMessageResponse] = []


class SessionListResponse(BaseModel):
    """Paginated session list."""
    items: List[SessionListItem]
    total: int
    limit: int
    offset: int


class PermissionResponse(BaseModel):
    """Response model for a communication permission rule."""
    id: int
    source_agent_id: int
    source_agent_name: str = ""
    target_agent_id: int
    target_agent_name: str = ""
    is_enabled: bool
    max_depth: int
    rate_limit_rpm: int
    allow_target_skills: bool = False
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_serializer("created_at", "updated_at")
    def serialize_datetimes(self, value: datetime, _info) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat() + "Z"


class PermissionCreateRequest(BaseModel):
    """Request model for creating a communication permission."""
    source_agent_id: int = Field(..., description="ID of the agent initiating communication")
    target_agent_id: int = Field(..., description="ID of the agent receiving communication")
    max_depth: int = Field(default=3, ge=1, le=10, description="Maximum delegation depth")
    rate_limit_rpm: int = Field(default=30, ge=1, le=1000, description="Rate limit (requests per minute)")
    allow_target_skills: bool = Field(
        default=False,
        description="Allow the target agent to use its own skills (gmail, sandboxed_tools, …) during A2A calls from this source",
    )

    class Config:
        extra = "forbid"


class PermissionUpdateRequest(BaseModel):
    """Request model for updating a communication permission."""
    is_enabled: Optional[bool] = None
    max_depth: Optional[int] = Field(None, ge=1, le=10)
    rate_limit_rpm: Optional[int] = Field(None, ge=1, le=1000)
    allow_target_skills: Optional[bool] = None

    class Config:
        extra = "forbid"


class StatsResponse(BaseModel):
    """Response model for communication statistics."""
    total_sessions: int
    completed_sessions: int
    blocked_sessions: int
    success_rate: float
    avg_response_time_ms: int


# =============================================================================
# Session Endpoints
# =============================================================================

@router.get("/sessions", response_model=SessionListResponse)
async def list_sessions(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    status: Optional[str] = Query(default=None, description="Filter by status (pending, in_progress, completed, failed, timeout, blocked)"),
    agent_id: Optional[int] = Query(default=None, description="Filter by agent (as initiator or target)"),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List agent communication sessions with pagination and optional filters."""
    # Validate status parameter
    if status and status not in VALID_SESSION_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status '{status}'. Allowed: {', '.join(sorted(VALID_SESSION_STATUSES))}")

    svc = AgentCommunicationService(db, ctx.tenant_id)
    sessions = svc.list_sessions(limit=limit, offset=offset, status=status, agent_id=agent_id)

    # Batch-resolve agent names
    agent_ids = set()
    for s in sessions:
        agent_ids.add(s.initiator_agent_id)
        agent_ids.add(s.target_agent_id)
    name_map = _build_agent_name_map(db, agent_ids, tenant_id=ctx.tenant_id)

    # Count total for pagination
    from sqlalchemy import func
    total_q = db.query(func.count(AgentCommunicationSession.id)).filter(
        AgentCommunicationSession.tenant_id == ctx.tenant_id
    )
    if status:
        total_q = total_q.filter(AgentCommunicationSession.status == status)
    if agent_id:
        total_q = total_q.filter(
            (AgentCommunicationSession.initiator_agent_id == agent_id)
            | (AgentCommunicationSession.target_agent_id == agent_id)
        )
    total = total_q.scalar() or 0

    items = []
    for s in sessions:
        items.append(SessionListItem(
            id=s.id,
            initiator_agent_id=s.initiator_agent_id,
            initiator_agent_name=name_map.get(s.initiator_agent_id, ""),
            target_agent_id=s.target_agent_id,
            target_agent_name=name_map.get(s.target_agent_id, ""),
            session_type=s.session_type,
            status=s.status,
            depth=s.depth,
            max_depth=s.max_depth,
            total_messages=s.total_messages,
            original_message_preview=s.original_message_preview,
            error_text=s.error_text,
            parent_session_id=s.parent_session_id,
            started_at=s.started_at,
            completed_at=s.completed_at,
        ))

    return SessionListResponse(items=items, total=total, limit=limit, offset=offset)


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session_detail(
    session_id: int,
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get a single communication session with all messages."""
    svc = AgentCommunicationService(db, ctx.tenant_id)
    session = svc.get_session_detail(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Communication session not found")

    # Collect all agent IDs from session + messages for batch resolve
    agent_ids = {session.initiator_agent_id, session.target_agent_id}
    for msg in session.messages:
        agent_ids.add(msg.from_agent_id)
        agent_ids.add(msg.to_agent_id)
    name_map = _build_agent_name_map(db, agent_ids, tenant_id=ctx.tenant_id)

    messages = []
    for msg in sorted(session.messages, key=lambda m: m.created_at or datetime.min):
        messages.append(SessionMessageResponse(
            id=msg.id,
            session_id=msg.session_id,
            from_agent_id=msg.from_agent_id,
            from_agent_name=name_map.get(msg.from_agent_id, ""),
            to_agent_id=msg.to_agent_id,
            to_agent_name=name_map.get(msg.to_agent_id, ""),
            direction=msg.direction,
            message_preview=msg.message_preview,
            message_content=msg.message_content,
            model_used=msg.model_used,
            execution_time_ms=msg.execution_time_ms,
            sentinel_analyzed=msg.sentinel_analyzed,
            created_at=msg.created_at,
        ))

    # Mask original_sender_key PII (show only last 4 chars)
    masked_sender_key = None
    if session.original_sender_key:
        key = session.original_sender_key
        masked_sender_key = f"***{key[-4:]}" if len(key) > 4 else "***"

    return SessionDetailResponse(
        id=session.id,
        initiator_agent_id=session.initiator_agent_id,
        initiator_agent_name=name_map.get(session.initiator_agent_id, ""),
        target_agent_id=session.target_agent_id,
        target_agent_name=name_map.get(session.target_agent_id, ""),
        session_type=session.session_type,
        status=session.status,
        depth=session.depth,
        max_depth=session.max_depth,
        timeout_seconds=session.timeout_seconds,
        total_messages=session.total_messages,
        original_sender_key=masked_sender_key,
        original_message_preview=session.original_message_preview,
        error_text=session.error_text,
        parent_session_id=session.parent_session_id,
        started_at=session.started_at,
        completed_at=session.completed_at,
        messages=messages,
    )


# =============================================================================
# Permission Endpoints
# =============================================================================

@router.get("/permissions", response_model=List[PermissionResponse])
async def list_permissions(
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List all agent communication permission rules for the tenant."""
    svc = AgentCommunicationService(db, ctx.tenant_id)
    perms = svc.list_permissions()

    # Batch-resolve agent names
    agent_ids = set()
    for p in perms:
        agent_ids.add(p.source_agent_id)
        agent_ids.add(p.target_agent_id)
    name_map = _build_agent_name_map(db, agent_ids, tenant_id=ctx.tenant_id)

    result = []
    for p in perms:
        result.append(PermissionResponse(
            id=p.id,
            source_agent_id=p.source_agent_id,
            source_agent_name=name_map.get(p.source_agent_id, ""),
            target_agent_id=p.target_agent_id,
            target_agent_name=name_map.get(p.target_agent_id, ""),
            is_enabled=p.is_enabled,
            max_depth=p.max_depth,
            rate_limit_rpm=p.rate_limit_rpm,
            allow_target_skills=bool(getattr(p, "allow_target_skills", False)),
            created_at=p.created_at,
            updated_at=p.updated_at,
        ))

    return result


@router.post("/permissions", response_model=PermissionResponse, status_code=201)
async def create_permission(
    body: PermissionCreateRequest,
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Create a new agent communication permission rule."""
    # Validate both agents exist and belong to the tenant
    for aid, label in [(body.source_agent_id, "Source"), (body.target_agent_id, "Target")]:
        agent = (
            db.query(Agent)
            .join(Contact, Contact.id == Agent.contact_id)
            .filter(Agent.id == aid, Agent.tenant_id == ctx.tenant_id)
            .first()
        )
        if not agent:
            raise HTTPException(status_code=404, detail=f"{label} agent {aid} not found in this tenant")

    if body.source_agent_id == body.target_agent_id:
        raise HTTPException(status_code=400, detail="Source and target agents must be different")

    # Check duplicate
    existing = (
        db.query(AgentCommunicationPermission)
        .filter(
            AgentCommunicationPermission.tenant_id == ctx.tenant_id,
            AgentCommunicationPermission.source_agent_id == body.source_agent_id,
            AgentCommunicationPermission.target_agent_id == body.target_agent_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(status_code=409, detail="Permission rule already exists for this agent pair")

    svc = AgentCommunicationService(db, ctx.tenant_id)
    perm = svc.create_permission(
        source_agent_id=body.source_agent_id,
        target_agent_id=body.target_agent_id,
        max_depth=body.max_depth,
        rate_limit_rpm=body.rate_limit_rpm,
        allow_target_skills=body.allow_target_skills,
    )

    name_map = _build_agent_name_map(db, {perm.source_agent_id, perm.target_agent_id}, tenant_id=ctx.tenant_id)

    return PermissionResponse(
        id=perm.id,
        source_agent_id=perm.source_agent_id,
        source_agent_name=name_map.get(perm.source_agent_id, ""),
        target_agent_id=perm.target_agent_id,
        target_agent_name=name_map.get(perm.target_agent_id, ""),
        is_enabled=perm.is_enabled,
        max_depth=perm.max_depth,
        rate_limit_rpm=perm.rate_limit_rpm,
        allow_target_skills=bool(getattr(perm, "allow_target_skills", False)),
        created_at=perm.created_at,
        updated_at=perm.updated_at,
    )


@router.put("/permissions/{permission_id}", response_model=PermissionResponse)
async def update_permission(
    permission_id: int,
    body: PermissionUpdateRequest,
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Update an existing agent communication permission rule."""
    svc = AgentCommunicationService(db, ctx.tenant_id)
    update_data = body.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    perm = svc.update_permission(permission_id, **update_data)
    if not perm:
        raise HTTPException(status_code=404, detail="Permission rule not found")

    name_map = _build_agent_name_map(db, {perm.source_agent_id, perm.target_agent_id}, tenant_id=ctx.tenant_id)

    return PermissionResponse(
        id=perm.id,
        source_agent_id=perm.source_agent_id,
        source_agent_name=name_map.get(perm.source_agent_id, ""),
        target_agent_id=perm.target_agent_id,
        target_agent_name=name_map.get(perm.target_agent_id, ""),
        is_enabled=perm.is_enabled,
        max_depth=perm.max_depth,
        rate_limit_rpm=perm.rate_limit_rpm,
        allow_target_skills=bool(getattr(perm, "allow_target_skills", False)),
        created_at=perm.created_at,
        updated_at=perm.updated_at,
    )


@router.delete("/permissions/{permission_id}", status_code=204)
async def delete_permission(
    permission_id: int,
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Delete an agent communication permission rule."""
    svc = AgentCommunicationService(db, ctx.tenant_id)
    deleted = svc.delete_permission(permission_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Permission rule not found")
    return None


# =============================================================================
# Statistics Endpoint
# =============================================================================

@router.get("/stats", response_model=StatsResponse)
async def get_communication_stats(
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get aggregate communication statistics for the tenant."""
    svc = AgentCommunicationService(db, ctx.tenant_id)
    stats = svc.get_stats()
    return StatsResponse(**stats)
