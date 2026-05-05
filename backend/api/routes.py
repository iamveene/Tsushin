from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Dict, List, Optional
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Config, MessageCache, AgentRun
from models_rbac import User, Tenant
from schemas import (
    ConfigResponse, ConfigUpdate,
    MessageResponse, AgentRunResponse,
    TriggerTestRequest, TriggerTestResponse
)
from auth_dependencies import require_permission, require_global_admin, get_current_user_optional, get_tenant_context, TenantContext
from services.audit_service import log_tenant_event, TenantAuditActions
from agent.router import AgentRouter
# Import SenderMemory from the old location (agent/memory.py)
import importlib.util
spec = importlib.util.spec_from_file_location("sender_memory", "agent/memory.py")
sender_memory_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sender_memory_module)
SenderMemory = sender_memory_module.SenderMemory

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str


class ReadinessComponentStatus(BaseModel):
    status: str
    error: Optional[str] = None


class ReadinessResponse(BaseModel):
    status: str
    service: str
    version: str
    timestamp: str
    components: Dict[str, ReadinessComponentStatus]

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
        try:
            db.rollback()
        except Exception:
            pass
        db.close()


@router.get("/api/health", response_model=HealthResponse)
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


@router.get("/api/system/public-info")
def public_system_info():
    """
    BUG-720: small public-info endpoint that lets client components reason
    about the install (currently: SSL mode, so the beacon registration UI
    can emit `curl -k` for self-signed deployments). No tenant data, no
    secrets — only deployment-level posture flags.
    """
    import os
    import settings

    raw_mode = (
        os.environ.get("TSN_SSL_MODE")
        or os.environ.get("SSL_MODE")
        or ""
    ).strip().lower()
    if raw_mode in ("", "off", "none", "disabled"):
        normalized_mode = "disabled"
    elif raw_mode in ("self-signed", "selfsigned"):
        normalized_mode = "selfsigned"
    elif raw_mode in ("letsencrypt", "le"):
        normalized_mode = "letsencrypt"
    elif raw_mode == "manual":
        normalized_mode = "manual"
    else:
        normalized_mode = raw_mode

    return {
        "ssl_mode": normalized_mode,
        "version": settings.SERVICE_VERSION,
    }


@router.get("/api/readiness", response_model=ReadinessResponse)
def readiness_check():
    """
    Readiness probe — checks that critical dependencies are available.

    Returns 200 when all components are healthy, 503 when any is degraded.
    /api/health remains a lightweight liveness probe; this endpoint performs
    real connectivity checks suitable for Kubernetes readiness gates.
    """
    from datetime import datetime
    from fastapi.responses import JSONResponse
    import settings
    import logging

    logger = logging.getLogger(__name__)
    timestamp = datetime.utcnow().isoformat() + "Z"

    # Guard against cold-start path where engine is not yet initialized
    if _engine is None:
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "service": settings.SERVICE_NAME,
                "version": settings.SERVICE_VERSION,
                "timestamp": timestamp,
                "components": {
                    "postgresql": {"status": "unhealthy", "error": "engine not initialized"},
                },
            },
        )

    components = {}

    # --- PostgreSQL check ---
    # BUG-604/607: Use the module-level session factory (same one FastAPI's
    # `Depends(get_db)` uses) and always rollback before close. A per-call
    # `sessionmaker(bind=_engine)` combined with a missing rollback leaks an
    # `idle in transaction` connection on every probe — under k8s / monitoring
    # polling that exhausts the pool, which manifests as auth/login stalls
    # (BUG-604) while /api/health (DB-free) stays green (BUG-607).
    try:
        from db import get_session_factory
        db = get_session_factory()()
        try:
            db.execute(
                __import__("sqlalchemy").text("SELECT 1")
            )
            components["postgresql"] = {"status": "healthy"}
        finally:
            try:
                db.rollback()
            except Exception:
                pass
            db.close()
    except Exception as exc:
        logger.warning(f"Readiness: PostgreSQL check failed: {exc}")
        components["postgresql"] = {"status": "unhealthy", "error": "database connection failed"}

    # --- Aggregate ---
    all_healthy = all(c["status"] == "healthy" for c in components.values())
    payload = {
        "status": "ready" if all_healthy else "degraded",
        "service": settings.SERVICE_NAME,
        "version": settings.SERVICE_VERSION,
        "timestamp": timestamp,
        "components": components,
    }

    status_code = 200 if all_healthy else 503
    return JSONResponse(content=payload, status_code=status_code)


@router.get("/api/user-guide")
def get_user_guide():
    """Serve USER_GUIDE.md content for the in-app help panel."""
    from fastapi.responses import PlainTextResponse
    from pathlib import Path

    guide_path = Path("/app/USER_GUIDE.md")
    if not guide_path.exists():
        raise HTTPException(status_code=404, detail="User guide not found")
    return PlainTextResponse(guide_path.read_text(encoding="utf-8"), media_type="text/markdown")


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
    # Note: enabled_tools removed - use AgentSkill table
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
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    import json
    import logging
    logger = logging.getLogger(__name__)

    config = db.query(Config).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    # BUG-067 FIX: Restrict global-scoped URL fields to global admin only
    GLOBAL_ADMIN_ONLY_FIELDS = {"ollama_base_url"}
    update_data = update.model_dump(exclude_unset=True)
    restricted_fields = GLOBAL_ADMIN_ONLY_FIELDS & set(update_data.keys())
    if restricted_fields and not getattr(current_user, 'is_global_admin', False):
        raise HTTPException(
            status_code=403,
            detail=f"Only global admins can modify: {', '.join(restricted_fields)}"
        )

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
        # enabled_tools removed - use AgentSkill table

        # Check if filter-related field changed
        if key in filter_related_fields:
            filter_fields_changed = True
        if key == "whatsapp_conversation_delay_seconds":
            delay_changed = True

        setattr(config, key, value)

    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)

    log_tenant_event(db, ctx.tenant_id, current_user.id, TenantAuditActions.SETTINGS_UPDATE, "config", str(config.id), {"fields": list(update.model_dump(exclude_unset=True).keys())}, request)

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
    # Note: enabled_tools removed - use AgentSkill table
    config_dict = {
        **config.__dict__,
        "contact_mappings": json.loads(config.contact_mappings) if config.contact_mappings else {},
        "group_keywords": json.loads(config.group_keywords) if config.group_keywords else []
    }
    return config_dict


def _resolve_caller_tenant(current_user: User, db: Session) -> Tenant:
    """Resolve the Tenant row for the caller, or 400 if they have none."""
    if not current_user.tenant_id:
        raise HTTPException(
            status_code=400,
            detail="No tenant scope for this user. Global admins must use the global endpoints."
        )
    tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")
    return tenant


@router.post("/api/system/emergency-stop")
def emergency_stop(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """
    Tenant-scoped emergency stop. Halts all message processing for the
    caller's tenant only. Other tenants are unaffected. For the global
    kill switch, see /api/system/global-emergency-stop.
    """
    tenant = _resolve_caller_tenant(current_user, db)
    tenant.emergency_stop = True
    tenant.updated_at = datetime.utcnow()
    db.commit()

    try:
        log_tenant_event(
            db,
            tenant_id=tenant.id,
            user_id=current_user.id,
            action=TenantAuditActions.SETTINGS_UPDATE,
            resource_type="tenant",
            resource_id=str(tenant.id),
            details={"emergency_stop": True, "scope": "tenant"},
        )
    except Exception:
        pass

    return {
        "status": "stopped",
        "scope": "tenant",
        "message": f"Emergency stop activated for tenant {tenant.name} — all message processing halted for this tenant",
        "tenant_emergency_stop": True,
    }


@router.post("/api/system/resume")
def resume_operations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """Resume tenant-scoped processing. Does not clear the global kill switch."""
    tenant = _resolve_caller_tenant(current_user, db)
    tenant.emergency_stop = False
    tenant.updated_at = datetime.utcnow()
    db.commit()

    try:
        log_tenant_event(
            db,
            tenant_id=tenant.id,
            user_id=current_user.id,
            action=TenantAuditActions.SETTINGS_UPDATE,
            resource_type="tenant",
            resource_id=str(tenant.id),
            details={"emergency_stop": False, "scope": "tenant"},
        )
    except Exception:
        pass

    return {
        "status": "resumed",
        "scope": "tenant",
        "message": f"Operations resumed for tenant {tenant.name}",
        "tenant_emergency_stop": False,
    }


@router.post("/api/system/global-emergency-stop")
def global_emergency_stop(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_global_admin())
):
    """GLOBAL kill switch — halts message processing for every tenant. Global admin only."""
    config = db.query(Config).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    config.emergency_stop = True
    config.updated_at = datetime.utcnow()
    db.commit()

    return {
        "status": "stopped",
        "scope": "global",
        "message": "GLOBAL emergency stop activated — all tenants halted",
        "global_emergency_stop": True,
    }


@router.post("/api/system/global-resume")
def global_resume_operations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_global_admin())
):
    """Clear the GLOBAL kill switch. Per-tenant stops remain in effect."""
    config = db.query(Config).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    config.emergency_stop = False
    config.updated_at = datetime.utcnow()
    db.commit()

    return {
        "status": "resumed",
        "scope": "global",
        "message": "GLOBAL emergency stop cleared. Per-tenant stops (if any) remain in effect.",
        "global_emergency_stop": False,
    }


@router.get("/api/system/status")
def get_system_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read"))
):
    """
    Return tenant + global emergency stop state and maintenance mode.

    Both flags are always returned so the frontend can show the user
    whether a global halt is blocking their tenant. Only global admins
    should be able to *toggle* the global flag — the UI enforces that
    based on ``is_global_admin``.
    """
    config = db.query(Config).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    global_flag = bool(getattr(config, "emergency_stop", False))

    tenant_flag = False
    tenant_id = None
    tenant_name = None
    if current_user.tenant_id:
        tenant = db.query(Tenant).filter(Tenant.id == current_user.tenant_id).first()
        if tenant:
            tenant_flag = bool(getattr(tenant, "emergency_stop", False))
            tenant_id = tenant.id
            tenant_name = tenant.name

    return {
        # Legacy field name — preserved so older clients still read the
        # global flag they used to see. New clients should prefer the
        # explicit tenant/global fields below.
        "emergency_stop": tenant_flag or global_flag,
        "tenant_emergency_stop": tenant_flag,
        "global_emergency_stop": global_flag,
        "is_global_admin": bool(current_user.is_global_admin),
        "tenant_id": tenant_id,
        "tenant_name": tenant_name,
        "maintenance_mode": config.maintenance_mode,
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

    def _looks_like_raw_identifier(value: Optional[str]) -> bool:
        if not value:
            return True
        normalized = value.strip()
        if not normalized:
            return True
        if "@" in normalized:
            normalized = normalized.split("@")[0]
        normalized = normalized.lstrip("+")
        return normalized.isdigit()

    enriched_messages = []
    contact_services = {}

    for message in messages:
        enriched = {
            "id": message.id,
            "source_id": message.source_id,
            "chat_name": message.chat_name,
            "sender": message.sender,
            "sender_name": message.sender_name,
            "body": message.body,
            "timestamp": message.timestamp,
            "is_group": message.is_group,
            "matched_filter": message.matched_filter,
            "seen_at": message.seen_at,
            "channel": message.channel,
        }

        tenant_id = getattr(message, "tenant_id", None)
        if tenant_id:
            from agent.contact_service_cached import CachedContactService

            contact_service = contact_services.get(tenant_id)
            if contact_service is None:
                contact_service = CachedContactService(db, tenant_id=tenant_id)
                contact_services[tenant_id] = contact_service

            resolved_contact = None
            for candidate in [
                message.sender,
                message.sender_name,
                message.chat_name,
            ]:
                if not candidate:
                    continue
                resolved_contact = contact_service.identify_sender(candidate)
                if resolved_contact:
                    break

            if resolved_contact:
                friendly_name = resolved_contact.friendly_name

                if (
                    not enriched["sender_name"] or
                    _looks_like_raw_identifier(enriched["sender_name"])
                ):
                    enriched["sender_name"] = friendly_name

                if (
                    not message.is_group and (
                        not enriched["chat_name"] or
                        _looks_like_raw_identifier(enriched["chat_name"]) or
                        enriched["chat_name"] == enriched["sender"]
                    )
                ):
                    enriched["chat_name"] = friendly_name
            elif (
                not message.is_group and
                enriched["chat_name"] and
                not _looks_like_raw_identifier(enriched["chat_name"]) and
                (
                    not enriched["sender_name"] or
                    _looks_like_raw_identifier(enriched["sender_name"])
                )
            ):
                enriched["sender_name"] = enriched["chat_name"]

        enriched_messages.append(enriched)

    return enriched_messages


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
    from services.default_agent_service import get_default_agent

    # Load agent configuration with tenant check
    if request.agent_id:
        agent = ctx.filter_by_tenant(
            db.query(Agent), Agent.tenant_id
        ).filter(Agent.id == request.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found or access denied")
    else:
        resolved_agent_id = get_default_agent(
            db=db,
            tenant_id=ctx.tenant_id,
            channel_type="playground",
            user_identifier=request.sender_key,
        )
        if not resolved_agent_id:
            raise HTTPException(status_code=404, detail="No default agent found for this tenant")
        agent = ctx.filter_by_tenant(
            db.query(Agent), Agent.tenant_id
        ).filter(Agent.id == resolved_agent_id).first()

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
        # enabled_tools removed - use AgentSkill table
        "response_template": agent.response_template,
        "enable_semantic_search": agent.enable_semantic_search,
        "context_message_count": agent.context_message_count or 10,
    }

    agent_router = AgentRouter(db, config_dict, tenant_id=agent.tenant_id)  # V060-CHN-006

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
        # BUG-LOG-015: Memory now has tenant_id — filter directly at row level.
        stats["senders_in_memory"] = db.query(Memory).filter(
            Memory.tenant_id == ctx.tenant_id
        ).count()
        agents = db.query(Agent).filter(Agent.tenant_id == ctx.tenant_id).all()

    # Semantic search state is per-agent; the global Config.enable_semantic_search
    # flag is vestigial and unused at runtime. Aggregate the per-agent flags so
    # the Watcher badge reflects what's actually configured on agents in scope.
    total_agents = len(agents)
    agents_with_semantic_search = sum(1 for a in agents if a.enable_semantic_search)
    stats["total_agents"] = total_agents
    stats["agents_with_semantic_search"] = agents_with_semantic_search
    stats["semantic_search_enabled"] = agents_with_semantic_search > 0

    # If any in-scope agent has semantic search enabled, aggregate embedding counts
    if stats["semantic_search_enabled"]:
        try:
            from pathlib import Path
            from agent.memory.vector_store_manager import get_vector_store

            total_embeddings = 0
            agent_embeddings = {}

            # Aggregate embeddings only from agents that actually have semantic search on
            for agent in agents:
                if not agent.enable_semantic_search:
                    continue
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

    # BUG-450: Also check for external vector store instances (Qdrant, MongoDB, etc.)
    # Runs unconditionally — a tenant can have an external store without ChromaDB's
    # enable_semantic_search flag enabled.
    try:
        from models import VectorStoreInstance

        vs_query = db.query(VectorStoreInstance).filter(
            VectorStoreInstance.is_active == True,
        )
        if not ctx.is_global_admin:
            vs_query = vs_query.filter(
                VectorStoreInstance.tenant_id == ctx.tenant_id
            )

        active_instances = vs_query.all()

        if active_instances:
            if "vector_store" not in stats:
                stats["vector_store"] = {
                    "total_embeddings": 0,
                    "per_agent_embeddings": {},
                }

            external_stores = []
            for inst in active_instances:
                external_stores.append({
                    "id": inst.id,
                    "vendor": inst.vendor,
                    "instance_name": inst.instance_name,
                    "health_status": inst.health_status or "unknown",
                    "is_default": inst.is_default,
                    "is_auto_provisioned": getattr(inst, 'is_auto_provisioned', False),
                })

            stats["vector_store"]["external_stores"] = external_stores
            stats["vector_store"]["external_store_count"] = len(external_stores)
            healthy_count = sum(1 for s in external_stores if s["health_status"] == "healthy")
            stats["vector_store"]["external_healthy_count"] = healthy_count
    except Exception as e:
        logger.warning(f"Failed to query external vector stores: {e}")

    return stats
