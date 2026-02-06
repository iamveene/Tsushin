"""
Knowledge API Routes - Phase 4.8 Week 3
Phase 7.9.2: Added tenant verification for agent ownership

REST API endpoints for managing semantic knowledge (learned facts).

Endpoints:
- GET /api/agents/{agent_id}/knowledge - List all facts for agent
- GET /api/agents/{agent_id}/knowledge/user/{user_id} - Get user facts
- POST /api/agents/{agent_id}/knowledge - Create/update fact
- DELETE /api/agents/{agent_id}/knowledge/{fact_id} - Delete fact
- GET /api/agents/{agent_id}/knowledge/search - Search facts
- GET /api/agents/{agent_id}/knowledge/stats - Get statistics
- POST /api/agents/{agent_id}/knowledge/extract/{user_id} - Trigger extraction
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field

from agent.memory.knowledge_service import KnowledgeService
from agent.memory.agent_memory_system import AgentMemorySystem
from models import Agent, SemanticKnowledge
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


# Request/Response Models
class FactCreate(BaseModel):
    user_id: str = Field(..., description="User identifier")
    topic: str = Field(..., description="Fact topic/category")
    key: str = Field(..., description="Fact key/identifier")
    value: str = Field(..., description="Fact value/content")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")


class FactResponse(BaseModel):
    id: int
    agent_id: int
    user_id: str
    topic: str
    key: str
    value: str
    confidence: float
    learned_at: Optional[str]
    updated_at: Optional[str]


class FactsListResponse(BaseModel):
    facts: List[FactResponse]
    total: int


class KnowledgeStatsResponse(BaseModel):
    agent_id: int
    total_facts: int
    unique_users: int
    topics: dict
    avg_confidence: float
    recent_facts: int


# Endpoints
@router.get("/agents/{agent_id}/knowledge", response_model=FactsListResponse)
def list_agent_knowledge(
    agent_id: int,
    user_id: Optional[str] = Query(None, description="Filter by user"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0, description="Minimum confidence"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List all facts for an agent with optional filtering.

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    knowledge_service = KnowledgeService(db)

    if user_id:
        facts = knowledge_service.get_user_facts(
            agent_id=agent_id,
            user_id=user_id,
            topic=topic,
            min_confidence=min_confidence
        )
    else:
        # Get all facts for agent (across all users)
        facts = []
        # This would require a new method in KnowledgeService
        # For now, return empty if no user_id specified
        pass

    return FactsListResponse(
        facts=[FactResponse(**f) for f in facts],
        total=len(facts)
    )


@router.get("/agents/{agent_id}/knowledge/user/{user_id}", response_model=FactsListResponse)
def get_user_knowledge(
    agent_id: int,
    user_id: str,
    topic: Optional[str] = Query(None, description="Filter by topic"),
    min_confidence: float = Query(0.0, ge=0.0, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get all facts known about a specific user.

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    knowledge_service = KnowledgeService(db)
    facts = knowledge_service.get_user_facts(
        agent_id=agent_id,
        user_id=user_id,
        topic=topic,
        min_confidence=min_confidence
    )

    return FactsListResponse(
        facts=[FactResponse(**f) for f in facts],
        total=len(facts)
    )


@router.post("/agents/{agent_id}/knowledge", response_model=FactResponse)
def create_or_update_fact(
    agent_id: int,
    fact: FactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Create or update a fact.

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    knowledge_service = KnowledgeService(db)

    success = knowledge_service.store_fact(
        agent_id=agent_id,
        user_id=fact.user_id,
        topic=fact.topic,
        key=fact.key,
        value=fact.value,
        confidence=fact.confidence
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to store fact")

    # Retrieve the stored fact
    stored_fact = knowledge_service.get_fact(
        agent_id=agent_id,
        user_id=fact.user_id,
        topic=fact.topic,
        key=fact.key
    )

    if not stored_fact:
        raise HTTPException(status_code=500, detail="Fact stored but could not be retrieved")

    return FactResponse(**stored_fact)


@router.delete("/agents/{agent_id}/knowledge/{fact_id}")
def delete_fact(
    agent_id: int,
    fact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Delete a specific fact by ID.

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    # Find and delete fact
    fact = db.query(SemanticKnowledge).filter(
        SemanticKnowledge.id == fact_id,
        SemanticKnowledge.agent_id == agent_id
    ).first()

    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    db.delete(fact)
    db.commit()

    return {"message": "Fact deleted successfully", "fact_id": fact_id}


@router.delete("/agents/{agent_id}/knowledge/user/{user_id}")
def delete_user_knowledge(
    agent_id: int,
    user_id: str,
    topic: Optional[str] = Query(None, description="Delete only specific topic"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Delete all facts for a user (optionally filtered by topic).

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    knowledge_service = KnowledgeService(db)
    deleted_count = knowledge_service.delete_user_facts(
        agent_id=agent_id,
        user_id=user_id,
        topic=topic
    )

    return {
        "message": f"Deleted {deleted_count} facts",
        "deleted_count": deleted_count,
        "user_id": user_id,
        "topic": topic
    }


@router.get("/agents/{agent_id}/knowledge/search", response_model=FactsListResponse)
def search_knowledge(
    agent_id: int,
    q: str = Query(..., description="Search query"),
    user_id: Optional[str] = Query(None, description="Filter by user"),
    topic: Optional[str] = Query(None, description="Filter by topic"),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Search facts by key or value content.

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    knowledge_service = KnowledgeService(db)
    facts = knowledge_service.search_facts(
        agent_id=agent_id,
        search_query=q,
        user_id=user_id,
        topic=topic,
        limit=limit
    )

    return FactsListResponse(
        facts=[FactResponse(**f) for f in facts],
        total=len(facts)
    )


@router.get("/agents/{agent_id}/knowledge/stats", response_model=KnowledgeStatsResponse)
def get_knowledge_stats(
    agent_id: int,
    user_id: Optional[str] = Query(None, description="Filter by user"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get knowledge statistics for an agent.

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    knowledge_service = KnowledgeService(db)
    stats = knowledge_service.get_statistics(
        agent_id=agent_id,
        user_id=user_id
    )

    return KnowledgeStatsResponse(
        agent_id=agent_id,
        **stats
    )


@router.post("/agents/{agent_id}/knowledge/extract/{user_id}")
async def trigger_fact_extraction(
    agent_id: int,
    user_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Manually trigger fact extraction for a user conversation.

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    agent = verify_agent_access(agent_id, db, ctx)

    # Create memory system instance
    # Note: This is a simplified version. In production, you'd want to use
    # a shared memory system instance or service
    from models import Config

    config_row = db.query(Config).first()
    if not config_row:
        raise HTTPException(status_code=500, detail="Configuration not found")

    config = {
        "memory_size": config_row.memory_size,
        "enable_semantic_search": config_row.enable_semantic_search,
        "semantic_search_results": config_row.semantic_search_results,
        "semantic_similarity_threshold": config_row.semantic_similarity_threshold,
        "auto_extract_facts": True,  # Enable fact extraction
        "fact_extraction_threshold": 5  # Min messages before extraction
    }
    persist_dir = f"./data/chroma/agent_{agent_id}"

    memory_system = AgentMemorySystem(
        agent_id=agent_id,
        db_session=db,
        config=config,
        persist_directory=persist_dir
    )

    # Trigger extraction
    facts = await memory_system.extract_facts_now(user_id)

    return {
        "message": f"Extracted {len(facts)} facts",
        "facts": facts,
        "user_id": user_id
    }


@router.get("/agents/{agent_id}/knowledge/topics")
def get_knowledge_topics(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get list of all topics used by this agent.

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    knowledge_service = KnowledgeService(db)
    topics = knowledge_service.get_topics(agent_id)

    return {
        "agent_id": agent_id,
        "topics": topics,
        "count": len(topics)
    }
