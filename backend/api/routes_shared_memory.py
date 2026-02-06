"""
Shared Memory API Routes - Phase 4.8 Week 4 + Phase 7.9.2 Security (CRIT-010)

REST API endpoints for cross-agent knowledge sharing.

Security: All endpoints require authentication and enforce tenant isolation.

Endpoints:
- GET /api/shared-memory - List accessible knowledge
- POST /api/shared-memory - Share knowledge
- PUT /api/shared-memory/{id} - Update shared knowledge
- DELETE /api/shared-memory/{id} - Delete shared knowledge
- GET /api/shared-memory/search - Search shared knowledge
- GET /api/shared-memory/stats - Get statistics
- GET /api/shared-memory/topics - List topics
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field

from agent.memory.shared_memory_pool import SharedMemoryPool
from models import Agent
from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission
)


router = APIRouter()

# Global engine (set by app.py)
_engine = None

def set_engine(engine):
    global _engine
    _engine = engine

# Dependency to get database session
def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Request/Response Models
class ShareKnowledgeRequest(BaseModel):
    agent_id: int = Field(..., description="Agent sharing the knowledge")
    content: str = Field(..., description="Knowledge content")
    topic: Optional[str] = Field(None, description="Topic/category")
    access_level: str = Field("public", description="Access level: public, restricted, private")
    accessible_to: Optional[List[int]] = Field(None, description="Agent IDs for restricted access")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class UpdateKnowledgeRequest(BaseModel):
    agent_id: int = Field(..., description="Agent updating the knowledge")
    content: Optional[str] = Field(None, description="New content")
    topic: Optional[str] = Field(None, description="New topic")
    accessible_to: Optional[List[int]] = Field(None, description="New access list")
    metadata: Optional[dict] = Field(None, description="New metadata")


class SharedKnowledgeResponse(BaseModel):
    id: int
    content: str
    topic: Optional[str]
    shared_by_agent: int
    accessible_to: List[int]
    metadata: dict
    access_level: str
    created_at: Optional[str]
    updated_at: Optional[str]


class SharedMemoryStatsResponse(BaseModel):
    total_shared: int
    by_topic: dict
    by_access_level: dict
    sharing_agents: int


# CRIT-010: Helper function to verify agent access
def verify_agent_access(agent_id: int, db: Session, ctx: TenantContext) -> Agent:
    """
    Verify agent exists and user has access to it.
    CRIT-010: Tenant isolation for shared memory operations.
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    return agent


# Endpoints
@router.get("/shared-memory", response_model=List[SharedKnowledgeResponse])
def list_accessible_knowledge(
    agent_id: int = Query(..., description="Agent requesting knowledge"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Min confidence"),
    limit: int = Query(20, ge=1, le=100, description="Max results"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("memory.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List knowledge accessible to an agent.
    CRIT-010: Requires authentication and verifies agent ownership.
    """
    # Verify agent exists and user has access
    verify_agent_access(agent_id, db, ctx)

    pool = SharedMemoryPool(db)
    knowledge = pool.get_accessible_knowledge(
        agent_id=agent_id,
        topic=topic,
        min_confidence=min_confidence,
        limit=limit,
        tenant_id=ctx.tenant_id
    )

    return [SharedKnowledgeResponse(**item) for item in knowledge]


@router.post("/shared-memory", response_model=dict)
def share_knowledge(
    request: ShareKnowledgeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("memory.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Share knowledge to the pool.
    CRIT-010: Requires authentication, verifies agent ownership, and sets tenant_id.
    """
    # Verify agent exists and user has access
    verify_agent_access(request.agent_id, db, ctx)

    # Validate access level
    if request.access_level not in ["public", "restricted", "private"]:
        raise HTTPException(status_code=400, detail="Invalid access level")

    # Validate accessible_to if restricted
    if request.access_level == "restricted" and not request.accessible_to:
        raise HTTPException(
            status_code=400,
            detail="Restricted access requires accessible_to list"
        )

    pool = SharedMemoryPool(db)
    success = pool.share_knowledge(
        agent_id=request.agent_id,
        content=request.content,
        topic=request.topic,
        access_level=request.access_level,
        accessible_to=request.accessible_to,
        metadata=request.metadata,
        tenant_id=ctx.tenant_id
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to share knowledge")

    return {
        "message": "Knowledge shared successfully",
        "agent_id": request.agent_id,
        "content_preview": request.content[:50] + "..." if len(request.content) > 50 else request.content,
        "access_level": request.access_level
    }


@router.put("/shared-memory/{knowledge_id}", response_model=dict)
def update_shared_knowledge(
    knowledge_id: int,
    request: UpdateKnowledgeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("memory.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Update shared knowledge (only by sharing agent).
    CRIT-010: Requires authentication and verifies agent ownership.
    """
    # Verify agent exists and user has access
    verify_agent_access(request.agent_id, db, ctx)

    pool = SharedMemoryPool(db)
    success = pool.update_shared_knowledge(
        knowledge_id=knowledge_id,
        agent_id=request.agent_id,
        content=request.content,
        topic=request.topic,
        accessible_to=request.accessible_to,
        metadata=request.metadata
    )

    if not success:
        raise HTTPException(
            status_code=403,
            detail="Failed to update knowledge (not owner or not found)"
        )

    return {
        "message": "Knowledge updated successfully",
        "knowledge_id": knowledge_id
    }


@router.delete("/shared-memory/{knowledge_id}")
def delete_shared_knowledge(
    knowledge_id: int,
    agent_id: int = Query(..., description="Agent requesting deletion"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("memory.delete")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Delete shared knowledge (only by sharing agent).
    CRIT-010: Requires authentication and verifies agent ownership.
    """
    # Verify agent exists and user has access
    verify_agent_access(agent_id, db, ctx)

    pool = SharedMemoryPool(db)
    success = pool.delete_shared_knowledge(
        knowledge_id=knowledge_id,
        agent_id=agent_id
    )

    if not success:
        raise HTTPException(
            status_code=403,
            detail="Failed to delete knowledge (not owner or not found)"
        )

    return {
        "message": "Knowledge deleted successfully",
        "knowledge_id": knowledge_id
    }


@router.get("/shared-memory/search", response_model=List[SharedKnowledgeResponse])
def search_shared_knowledge(
    agent_id: int = Query(..., description="Agent requesting search"),
    query: str = Query(..., description="Search query"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("memory.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Search shared knowledge accessible to an agent.
    CRIT-010: Requires authentication and verifies agent ownership.
    """
    # Verify agent exists and user has access
    verify_agent_access(agent_id, db, ctx)

    pool = SharedMemoryPool(db)
    results = pool.search_shared_knowledge(
        agent_id=agent_id,
        query=query,
        topic=topic,
        limit=limit,
        tenant_id=ctx.tenant_id
    )

    return [SharedKnowledgeResponse(**item) for item in results]


@router.get("/shared-memory/stats", response_model=SharedMemoryStatsResponse)
def get_shared_memory_stats(
    agent_id: Optional[int] = Query(None, description="Filter by agent"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("memory.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get shared memory statistics.
    CRIT-010: Requires authentication and filters by tenant.
    """
    if agent_id:
        # Verify agent exists and user has access
        verify_agent_access(agent_id, db, ctx)

    pool = SharedMemoryPool(db)
    stats = pool.get_statistics(agent_id=agent_id, tenant_id=ctx.tenant_id)

    return SharedMemoryStatsResponse(**stats)


@router.get("/shared-memory/topics", response_model=List[str])
def get_shared_memory_topics(
    agent_id: Optional[int] = Query(None, description="Filter by accessible topics"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("memory.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get list of topics in shared memory.
    CRIT-010: Requires authentication and filters by tenant.
    """
    if agent_id:
        # Verify agent exists and user has access
        verify_agent_access(agent_id, db, ctx)

    pool = SharedMemoryPool(db)
    topics = pool.get_topics(agent_id=agent_id, tenant_id=ctx.tenant_id)

    return topics
