from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Config, MessageCache, AgentRun
from models_rbac import User
from schemas import (
    ConfigResponse, ConfigUpdate,
    MessageResponse, AgentRunResponse,
    TriggerTestRequest, TriggerTestResponse
)
from auth_dependencies import require_permission, get_current_user_optional, get_tenant_context, TenantContext
from agent.router import AgentRouter
# Import SenderMemory from the old location (agent/memory.py)
import importlib.util
spec = importlib.util.spec_from_file_location("sender_memory", "agent/memory.py")
sender_memory_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender_memory_module)
SenderMemory = sender_memory_module.SenderMemory

router = APIRouter()

# Global engine reference
_engine = None

def set_engine(engine):
    """Set the global engine reference"""
    global _engine
    _engine = engine
    # Also set engine for contact routes
    from api.routes_contacts import set_engine as set_contacts_engine
    set_contacts_engine(engine)

    # Also set engine for agent routes (Phase 4.4)
    from api.routes_agents import set_engine as set_agents_engine
    set_agents_engine(engine)

# Include contact routes after engine is available
from api.routes_contacts import router as contacts_router
router.include_router(contacts_router, prefix="/api/contacts", tags=["contacts"])

# Phase 4.4: Include agent management routes
from api.routes_agents import router as agents_router
router.include_router(agents_router, prefix="/api", tags=["agents"])

# Flight providers routes (Flight Search Provider Architecture)
from api.routes_flight_providers import router as flight_providers_router
router.include_router(flight_providers_router, tags=["flight_providers"])

# TTS providers routes (TTS Provider Architecture)
from api.routes_tts_providers import router as tts_providers_router
router.include_router(tts_providers_router, tags=["tts_providers"])

# Dependency to get database session
def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/api/health")
def health_check():
    """Health check endpoint with service metadata"""
    from datetime import datetime
    import settings

    return {
        "status": "healthy",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "timestamp": datetime.utcnow().isoformat() + "Z"
    }


@router.get("/api/config", response_model=ConfigResponse)
def get_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read"))
):
    """Get configuration (requires org.settings.read permission)"""
    import json
    config = db.query(Config).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    # Parse JSON fields
    # Note: enabled_tools removed - use AgentSkill table for web_search, weather, etc.
    config_dict = {
        **config.__dict__,
        "contact_mappings": json.loads(config.contact_mappings) if config.contact_mappings else {},
        "group_keywords": json.loads(config.group_keywords) if config.group_keywords else []
    }
    return config_dict


@router.put("/api/config", response_model=ConfigResponse)
def update_config(
    update: ConfigUpdate,
    db: Session = Depends(get_db),
    request: Request = None,
    current_user: User = Depends(require_permission("org.settings.write"))
):
    import json
    import logging
    logger = logging.getLogger(__name__)

    config = db.query(Config).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    # Track if filter-related fields changed
    filter_fields_changed = False
    delay_changed = False
    filter_related_fields = {'group_filters', 'number_filters', 'dm_auto_mode', 'agent_phone_number', 'agent_name', 'group_keywords'}

    for key, value in update.model_dump(exclude_unset=True).items():
        # Convert dict/list to JSON string for JSON fields
        if key == "contact_mappings" and isinstance(value, dict):
            value = json.dumps(value)
        elif key in ("group_keywords",) and isinstance(value, list):
            value = json.dumps(value)
        # enabled_tools removed - use AgentSkill table for web_search, weather, etc.

        # Check if filter-related field changed
        if key in filter_related_fields:
            filter_fields_changed = True
        if key == "whatsapp_conversation_delay_seconds":
            delay_changed = True

        setattr(config, key, value)

    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)

    # Hot-reload filter configuration if filter fields changed
    if filter_fields_changed and request and hasattr(request.app.state, 'watcher'):
        try:
            from mcp_reader.filters import MessageFilter
            from agent.contact_service import ContactService

            # Get session from app.state
            watcher_session = getattr(request.app.state, 'watcher_session', db)

            # Initialize ContactService
            contact_service = ContactService(watcher_session)

            # Parse JSON fields for new filter
            group_keywords = json.loads(config.group_keywords) if config.group_keywords else []

            # Create new filter with updated configuration
            new_filter = MessageFilter(
                group_filters=config.group_filters or [],
                number_filters=config.number_filters or [],
                agent_number=config.agent_number,
                dm_auto_mode=config.dm_auto_mode,
                agent_phone_number=config.agent_phone_number,
                agent_name=config.agent_name,
                group_keywords=group_keywords,
                contact_service=contact_service,
                db_session=watcher_session
            )

            # Reload filter
            request.app.state.watcher.reload_filter(new_filter)
            logger.info(f"MCP Watcher filter reloaded - changes applied without restart")

        except Exception as e:
            logger.error(f"Failed to reload filter: {e}", exc_info=True)
            # Don't fail the request - config was saved successfully

    # Hot-apply WhatsApp conversation delay across active watchers
    if delay_changed and request and hasattr(request.app.state, 'watchers'):
        try:
            import settings

            delay_value = config.whatsapp_conversation_delay_seconds
            if delay_value is None:
                delay_value = settings.WHATSAPP_CONVERSATION_DELAY_SECONDS

            for watcher in request.app.state.watchers.values():
                watcher.whatsapp_conversation_delay_seconds = max(0.0, float(delay_value))

            logger.info(f"Updated WhatsApp conversation delay to {delay_value}s for active watchers")
        except Exception as e:
            logger.error(f"Failed to apply WhatsApp conversation delay: {e}", exc_info=True)

    # Parse JSON fields for response
    # Note: enabled_tools removed - use AgentSkill table for web_search, weather, etc.
    config_dict = {
        **config.__dict__,
        "contact_mappings": json.loads(config.contact_mappings) if config.contact_mappings else {},
        "group_keywords": json.loads(config.group_keywords) if config.group_keywords else []
    }
    return config_dict


@router.post("/api/system/emergency-stop")
def emergency_stop(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Emergency Stop - Immediately stops all agent message processing.
    Bug Fix 2026-01-06: Prevents uncontrollable message loops.
    """
    config = db.query(Config).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    config.emergency_stop = True
    config.updated_at = datetime.utcnow()
    db.commit()

    return {
        "status": "stopped",
        "message": "Emergency stop activated - all message processing halted",
        "emergency_stop": True
    }


@router.post("/api/system/resume")
def resume_operations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Resume Operations - Re-enables agent message processing after emergency stop.
    Bug Fix 2026-01-06: Restores normal operations.
    """
    config = db.query(Config).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    config.emergency_stop = False
    config.updated_at = datetime.utcnow()
    db.commit()

    return {
        "status": "resumed",
        "message": "Operations resumed - message processing enabled",
        "emergency_stop": False
    }


@router.get("/api/system/status")
def get_system_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read"))
):
    """
    Get system status including emergency stop state.
    Bug Fix 2026-01-06: Check if emergency stop is active.
    Security Fix CRIT-007: Added authentication requirement.
    """
    config = db.query(Config).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    return {
        "emergency_stop": config.emergency_stop if hasattr(config, 'emergency_stop') else False,
        "maintenance_mode": config.maintenance_mode
    }


@router.get("/api/messages", response_model=List[MessageResponse])
def get_messages(
    limit: int = Query(100, le=500),
    after: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("watcher.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get recent messages from cache.
    Security Fix CRIT-007: Added authentication requirement.
    Security Fix HIGH-012: Added tenant isolation for MessageCache.
    """
    # HIGH-012: Apply tenant filtering to MessageCache
    query = db.query(MessageCache)

    if not ctx.is_global_admin:
        query = query.filter(MessageCache.tenant_id == ctx.tenant_id)

    query = query.order_by(MessageCache.timestamp.desc())

    if after:
        try:
            after_dt = datetime.fromisoformat(after)
            query = query.filter(MessageCache.seen_at > after_dt)
        except ValueError:
            pass

    messages = query.limit(limit).all()
    return messages


@router.get("/api/agent-runs", response_model=List[AgentRunResponse])
def get_agent_runs(
    limit: int = Query(100, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("watcher.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get recent agent runs.
    Security Fix CRIT-007: Added authentication and tenant filtering.
    """
    from models import Agent, Contact

    if ctx.is_global_admin:
        # Global admin sees all agent runs
        runs = db.query(AgentRun).order_by(AgentRun.created_at.desc()).limit(limit).all()
    else:
        # Filter by tenant's agents
        runs = db.query(AgentRun).join(
            Agent, AgentRun.agent_id == Agent.id
        ).filter(Agent.tenant_id == ctx.tenant_id).order_by(
            AgentRun.created_at.desc()
        ).limit(limit).all()

    # Manually construct response with agent_name
    result = []
    for run in runs:
        agent_name = None
        if run.agent_id:
            agent = db.query(Agent).filter(Agent.id == run.agent_id).first()
            if agent and agent.contact_id:
                contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
                if contact:
                    agent_name = contact.friendly_name

        result.append({
            "id": run.id,
            "agent_id": run.agent_id,
            "agent_name": agent_name,
            "triggered_by": run.triggered_by,
            "sender_key": run.sender_key,
            "input_preview": run.input_preview,
            "skill_type": run.skill_type,
            "tool_used": run.tool_used,
            "tool_result": run.tool_result,
            "model_used": run.model_used,
            "output_preview": run.output_preview,
            "status": run.status,
            "error_text": run.error_text,
            "execution_time_ms": run.execution_time_ms,
            "created_at": run.created_at
        })

    return result


@router.post("/api/trigger/test", response_model=TriggerTestResponse)
async def trigger_test(
    request: TriggerTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.execute")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Manual agent trigger for testing.
    Security Fix CRIT-007: Added authentication and tenant filtering.
    """
    from models import Agent, Contact
    import json

    # Load agent configuration with tenant check
    if request.agent_id:
        agent = ctx.filter_by_tenant(
            db.query(Agent), Agent.tenant_id
        ).filter(Agent.id == request.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found or access denied")
    else:
        # Use default agent from user's tenant
        agent = ctx.filter_by_tenant(
            db.query(Agent), Agent.tenant_id
        ).filter(Agent.is_default == True).first()
        if not agent:
            raise HTTPException(status_code=404, detail="No default agent found for this tenant")

    # Build config_dict from agent
    # Get agent name from contact relationship
    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
    agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

    config_dict = {
        "agent_id": agent.id,
        "agent_name": agent_name,
        "model_provider": agent.model_provider,
        "model_name": agent.model_name,
        "system_prompt": agent.system_prompt,
        "memory_size": agent.memory_size or 5000,
        # enabled_tools removed - use AgentSkill table for web_search, weather, etc.
        "response_template": agent.response_template,
        "enable_semantic_search": agent.enable_semantic_search,
        "context_message_count": agent.context_message_count or 10,
    }

    agent_router = AgentRouter(db, config_dict)

    result = await agent_router.agent_service.process_message(
        sender_key=request.sender_key,
        message_text=request.text
    )

    return result


@router.get("/api/messages/count")
def get_message_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("watcher.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get total count of messages in cache.
    Security Fix CRIT-007: Added authentication requirement.
    Security Fix HIGH-012: Added tenant isolation for MessageCache.
    """
    # HIGH-012: Apply tenant filtering to MessageCache count
    if ctx.is_global_admin:
        total = db.query(MessageCache).count()
    else:
        total = db.query(MessageCache).filter(
            MessageCache.tenant_id == ctx.tenant_id
        ).count()

    return {"total": total}


@router.get("/api/agent-runs/count")
def get_agent_runs_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("watcher.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get total count of agent runs.
    Security Fix CRIT-007: Added authentication and tenant filtering.
    """
    from models import Agent

    if ctx.is_global_admin:
        total = db.query(AgentRun).count()
    else:
        total = db.query(AgentRun).join(
            Agent, AgentRun.agent_id == Agent.id
        ).filter(Agent.tenant_id == ctx.tenant_id).count()

    return {"total": total}


@router.get("/api/stats/memory")
async def get_memory_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("watcher.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get memory and semantic search statistics.
    Security Fix CRIT-007: Added authentication and tenant filtering.
    Security Fix HIGH-012: Added tenant isolation for MessageCache stats.
    """
    config = db.query(Config).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    from models import Memory, MessageCache, Agent

    # Base stats
    stats = {
        "semantic_search_enabled": config.enable_semantic_search if hasattr(config, 'enable_semantic_search') else False,
        "ring_buffer_size": config.memory_size,
    }

    # HIGH-012: Apply tenant filtering to MessageCache stats
    if ctx.is_global_admin:
        stats["total_messages_cached"] = db.query(MessageCache).count()
    else:
        stats["total_messages_cached"] = db.query(MessageCache).filter(
            MessageCache.tenant_id == ctx.tenant_id
        ).count()

    if ctx.is_global_admin:
        # Global admin sees all stats
        stats["senders_in_memory"] = db.query(Memory).count()
        agents = db.query(Agent).all()
    else:
        # Filter Memory and Agents by tenant
        tenant_agents = db.query(Agent).filter(Agent.tenant_id == ctx.tenant_id).all()
        tenant_agent_ids = [a.id for a in tenant_agents]

        if tenant_agent_ids:
            stats["senders_in_memory"] = db.query(Memory).filter(Memory.agent_id.in_(tenant_agent_ids)).count()
        else:
            stats["senders_in_memory"] = 0

        agents = tenant_agents

    # If semantic search is enabled, get vector store stats for visible agents
    if stats["semantic_search_enabled"]:
        try:
            from pathlib import Path
            from agent.memory.vector_store_manager import get_vector_store

            total_embeddings = 0
            agent_embeddings = {}

            # Aggregate embeddings from each agent's ChromaDB using VectorStore manager
            for agent in agents:
                agent_chroma_path = f"./data/chroma/agent_{agent.id}"
                if Path(agent_chroma_path).exists():
                    try:
                        # Use VectorStore manager to prevent singleton conflicts
                        vector_store = get_vector_store(agent_chroma_path)
                        agent_count = vector_store.collection.count()
                        total_embeddings += agent_count
                        agent_embeddings[f"agent_{agent.id}"] = agent_count
                    except Exception as agent_error:
                        agent_embeddings[f"agent_{agent.id}"] = f"Error: {str(agent_error)}"

            stats["vector_store"] = {
                "total_embeddings": total_embeddings,
                "per_agent_embeddings": agent_embeddings,
                "persist_directory": "./data/chroma"
            }
        except Exception as e:
            stats["vector_store"] = {"error": str(e)}

    return stats
