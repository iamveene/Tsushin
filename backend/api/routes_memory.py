"""
Memory Management API Routes for Phase 5.0
Phase 7.9.2: Added tenant verification for agent ownership
Provides endpoints for inspecting, cleaning, and resetting agent memory.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel, Field
import logging

from agent.memory.memory_management_service import MemoryManagementService
from models import Agent, Contact
from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission
)

router = APIRouter()
logger = logging.getLogger(__name__)

# Global engine reference
_engine = None

def set_engine(engine):
    """Set the global engine reference"""
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
        raise HTTPException(status_code=404, detail="Agent not found")

    return agent


def get_agent_name(agent: Agent, db: Session) -> str:
    """Get agent's friendly name from contact."""
    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
    return contact.friendly_name if contact else "Unknown"


# Pydantic models for request/response
class CleanMessagesRequest(BaseModel):
    older_than_days: int = Field(..., ge=1, le=365, description="Delete messages older than N days")
    dry_run: bool = Field(True, description="Preview only, don't actually delete")


class ResetMemoryRequest(BaseModel):
    confirm_token: str = Field(..., description="Agent name as confirmation")


# API Endpoints

@router.get("/agents/{agent_id}/memory/stats")
async def get_memory_stats(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get memory statistics for an agent.

    Returns:
        - total_conversations: Number of unique conversations
        - total_messages: Total messages across all conversations
        - total_embeddings: Number of vector embeddings
        - storage_size_mb: Estimated storage size
        - decay_config: Temporal decay configuration (Item 37)
        - freshness_distribution: Counts per freshness label (when decay enabled)

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    agent = verify_agent_access(agent_id, db, ctx)

    try:
        service = MemoryManagementService(db, agent_id)
        stats = await service.get_memory_stats()
        result = stats.to_dict()

        # Item 37: Add decay config and freshness distribution
        from agent.memory.temporal_decay import DecayConfig, compute_freshness_label
        decay_config = DecayConfig.from_agent(agent)
        result['decay_config'] = {
            'enabled': decay_config.enabled,
            'decay_lambda': decay_config.decay_lambda,
            'archive_threshold': decay_config.archive_threshold,
            'mmr_lambda': decay_config.mmr_lambda,
        }

        if decay_config.enabled:
            from models import SemanticKnowledge
            from datetime import datetime
            now = datetime.utcnow()
            facts = db.query(SemanticKnowledge).filter(
                SemanticKnowledge.agent_id == agent_id
            ).all()
            freshness_dist = {'fresh': 0, 'fading': 0, 'stale': 0, 'archived': 0}
            for fact in facts:
                last_accessed = getattr(fact, 'last_accessed_at', None)
                label = compute_freshness_label(
                    last_accessed, now, decay_config.decay_lambda, decay_config.archive_threshold
                )
                freshness_dist[label['freshness']] += 1
            result['freshness_distribution'] = freshness_dist

        return result
    except Exception as e:
        logger.error(f"Error getting memory stats for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/memory/conversations")
async def list_conversations(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List all conversations for an agent.

    Returns list of:
        - sender_key: Conversation identifier
        - sender_name: Friendly name (if available)
        - message_count: Number of messages in conversation
        - last_activity: Timestamp of last message

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    try:
        service = MemoryManagementService(db, agent_id)
        conversations = await service.list_conversations()
        return [conv.to_dict() for conv in conversations]
    except Exception as e:
        logger.error(f"Error listing conversations for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/memory/conversation/{sender_key}")
async def get_conversation(
    agent_id: int,
    sender_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get detailed conversation data for a specific sender.

    Returns:
        - working_memory: Recent messages (ring buffer)
        - episodic_memory: Semantically similar messages from past
        - semantic_facts: Learned facts about the user

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    try:
        service = MemoryManagementService(db, agent_id)
        details = await service.get_conversation(sender_key)
        return details.to_dict()
    except Exception as e:
        logger.error(f"Error getting conversation {sender_key} for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}/memory/conversation/{sender_key}")
async def delete_conversation(
    agent_id: int,
    sender_key: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Delete all memory for a specific conversation.

    This removes:
    - Ring buffer messages
    - Vector embeddings
    - Semantic facts

    This action cannot be undone.

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    try:
        service = MemoryManagementService(db, agent_id)
        success = await service.delete_conversation(sender_key)

        if success:
            return {"success": True, "message": f"Conversation {sender_key} deleted"}
        else:
            raise HTTPException(status_code=500, detail="Deletion failed")

    except Exception as e:
        logger.error(f"Error deleting conversation {sender_key} for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/agents/{agent_id}/memory/clean")
async def clean_old_messages(
    agent_id: int,
    request: CleanMessagesRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Clean messages older than specified days.

    Use dry_run=true to preview what would be deleted.
    Use dry_run=false to actually delete.

    Returns:
        - deleted_count: Number of conversations that would be/were deleted
        - preview: List of conversation identifiers (first 10)

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    verify_agent_access(agent_id, db, ctx)

    try:
        service = MemoryManagementService(db, agent_id)
        report = await service.clean_old_messages(
            older_than_days=request.older_than_days,
            dry_run=request.dry_run
        )
        return report.to_dict()
    except Exception as e:
        logger.error(f"Error cleaning old messages for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}/memory/reset")
async def reset_agent_memory(
    agent_id: int,
    request: ResetMemoryRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.delete")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Reset ALL memory for an agent (nuclear option).

    This deletes:
    - All conversations
    - All ring buffer messages
    - All vector embeddings
    - All semantic facts

    This action cannot be undone.

    Requires confirmation token (agent name).

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    # Verify agent access
    agent = verify_agent_access(agent_id, db, ctx)

    try:
        # Get agent name for confirmation
        agent_name = get_agent_name(agent, db)

        # Verify confirmation token matches agent name
        if request.confirm_token != agent_name:
            raise HTTPException(
                status_code=400,
                detail="Confirmation token does not match agent name"
            )

        # Perform reset
        service = MemoryManagementService(db, agent_id)
        result = await service.reset_agent_memory()

        return result

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error resetting memory for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


class ArchiveDecayedRequest(BaseModel):
    dry_run: bool = Field(True, description="Preview only, don't actually archive")


@router.post("/agents/{agent_id}/memory/archive-decayed")
async def archive_decayed_facts(
    agent_id: int,
    request: ArchiveDecayedRequest = ArchiveDecayedRequest(),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Archive (delete) facts whose decayed confidence falls below the agent's archive threshold.

    Item 37: Temporal Memory Decay.

    Use dry_run=true (default) to preview what would be archived.
    Use dry_run=false to actually delete.

    Returns:
        - total_facts: Total facts for this agent
        - archived_count: Number of facts archived (or would be)
        - archived_facts: List of archived fact details
        - dry_run: Whether this was a preview
    """
    agent = verify_agent_access(agent_id, db, ctx)

    try:
        from agent.memory.temporal_decay import DecayConfig
        from agent.memory.knowledge_service import KnowledgeService

        decay_config = DecayConfig.from_agent(agent)
        if not decay_config.enabled:
            return {
                "total_facts": 0,
                "archived_count": 0,
                "archived_facts": [],
                "dry_run": request.dry_run,
                "message": "Temporal decay is not enabled for this agent"
            }

        knowledge_service = KnowledgeService(db)
        result = knowledge_service.archive_decayed_facts(
            agent_id=agent_id,
            decay_lambda=decay_config.decay_lambda,
            archive_threshold=decay_config.archive_threshold,
            dry_run=request.dry_run
        )
        return result

    except Exception as e:
        logger.error(f"Error archiving decayed facts for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
