"""
v0.6.0-patch.5: TTS Instance Management API Routes

CRUD + container-lifecycle endpoints for per-tenant Kokoro TTS instances.
Mirrors routes_vector_stores.py: tenant isolation via TenantContext, soft-delete,
auto-provision-in-background so POST can return 202 immediately.
"""

import logging
import threading
from datetime import datetime
from typing import Optional, Dict, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from models import TTSInstance, Agent, AgentSkill
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission,
)

logger = logging.getLogger(__name__)

router = APIRouter()

_engine = None


def set_engine(engine):
    global _engine
    _engine = engine


def get_db():
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


# ============================================================================
# Pydantic schemas
# ============================================================================

class TTSInstanceCreate(BaseModel):
    vendor: str  # "kokoro" (only supported for v0.6.0-patch.5)
    instance_name: str
    description: Optional[str] = None
    base_url: Optional[str] = None
    is_default: bool = False
    default_voice: Optional[str] = None
    default_speed: Optional[float] = None
    default_language: Optional[str] = None
    default_format: Optional[str] = None
    auto_provision: bool = False
    mem_limit: Optional[str] = None  # e.g. "1g", "2g"
    cpu_quota: Optional[int] = None  # microseconds, 100000 = 1 CPU


class TTSInstanceUpdate(BaseModel):
    instance_name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    default_voice: Optional[str] = None
    default_speed: Optional[float] = None
    default_language: Optional[str] = None
    default_format: Optional[str] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None
    mem_limit: Optional[str] = None
    cpu_quota: Optional[int] = None


class TTSInstanceResponse(BaseModel):
    id: int
    tenant_id: str
    vendor: str
    instance_name: str
    description: Optional[str] = None
    base_url: Optional[str] = None
    health_status: str
    health_status_reason: Optional[str] = None
    last_health_check: Optional[str] = None
    is_default: bool
    is_active: bool
    is_auto_provisioned: bool
    container_status: Optional[str] = None
    container_name: Optional[str] = None
    container_port: Optional[int] = None
    container_image: Optional[str] = None
    volume_name: Optional[str] = None
    mem_limit: Optional[str] = None
    cpu_quota: Optional[int] = None
    default_voice: Optional[str] = None
    default_speed: Optional[float] = None
    default_language: Optional[str] = None
    default_format: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DefaultTTSUpdate(BaseModel):
    default_tts_instance_id: Optional[int] = None


class TTSAssignToAgentRequest(BaseModel):
    agent_id: int
    voice: Optional[str] = None
    speed: Optional[float] = None
    language: Optional[str] = None
    response_format: Optional[str] = None


# ============================================================================
# Helpers
# ============================================================================

def _to_response(instance: TTSInstance) -> Dict[str, Any]:
    return {
        "id": instance.id,
        "tenant_id": instance.tenant_id,
        "vendor": instance.vendor,
        "instance_name": instance.instance_name,
        "description": instance.description,
        "base_url": instance.base_url,
        "health_status": instance.health_status or "unknown",
        "health_status_reason": instance.health_status_reason,
        "last_health_check": (
            instance.last_health_check.isoformat() if instance.last_health_check else None
        ),
        "is_default": bool(instance.is_default),
        "is_active": bool(instance.is_active),
        "is_auto_provisioned": bool(instance.is_auto_provisioned),
        "container_status": instance.container_status,
        "container_name": instance.container_name,
        "container_port": instance.container_port,
        "container_image": instance.container_image,
        "volume_name": instance.volume_name,
        "mem_limit": instance.mem_limit,
        "cpu_quota": instance.cpu_quota,
        "default_voice": instance.default_voice,
        "default_speed": instance.default_speed,
        "default_language": instance.default_language,
        "default_format": instance.default_format,
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
        "updated_at": instance.updated_at.isoformat() if instance.updated_at else None,
    }


def _provision_bg(instance_id: int, tenant_id: str) -> None:
    """Background-thread provisioning worker. Opens its own Session."""
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        from services.tts_instance_service import TTSInstanceService
        instance = TTSInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            logger.error(
                f"_provision_bg: instance {instance_id} not found for tenant {tenant_id}"
            )
            return
        TTSInstanceService.provision_instance(
            instance,
            db,
            fail_open_on_error=True,
            warning_context=f"TTS instance '{instance.instance_name}'",
        )
    except Exception as e:
        logger.error(
            f"_provision_bg failed for tts instance {instance_id}: {e}",
            exc_info=True,
        )
    finally:
        try:
            db.close()
        except Exception:
            pass


# ============================================================================
# CRUD endpoints
# ============================================================================

@router.get("/tts-instances", tags=["TTS Instances"])
async def list_tts_instances(
    vendor: Optional[str] = None,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.tts_instance_service import TTSInstanceService
    instances = TTSInstanceService.list_instances(ctx.tenant_id, db, vendor=vendor)
    return [_to_response(inst) for inst in (instances or [])]


@router.post(
    "/tts-instances",
    tags=["TTS Instances"],
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_tts_instance(
    data: TTSInstanceCreate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    """Create a TTS instance.

    When `auto_provision=True`, provisioning runs in a background thread and this
    endpoint returns 202 Accepted immediately so the caller can poll the status
    endpoint instead of blocking on a ~30-90s container start.
    """
    from services.tts_instance_service import TTSInstanceService, SUPPORTED_VENDORS

    if data.vendor not in SUPPORTED_VENDORS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported vendor: {data.vendor}",
        )

    # Duplicate-name guard (active rows)
    existing = db.query(TTSInstance).filter(
        TTSInstance.tenant_id == ctx.tenant_id,
        TTSInstance.instance_name == data.instance_name,
        TTSInstance.is_active == True,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"TTS instance '{data.instance_name}' already exists",
        )

    # Remove any soft-deleted row with the same name (UniqueConstraint on tenant+name)
    db.query(TTSInstance).filter(
        TTSInstance.tenant_id == ctx.tenant_id,
        TTSInstance.instance_name == data.instance_name,
        TTSInstance.is_active == False,
    ).delete()
    db.commit()

    try:
        instance = TTSInstanceService.create_instance(
            tenant_id=ctx.tenant_id,
            vendor=data.vendor,
            instance_name=data.instance_name,
            db=db,
            description=data.description,
            base_url=data.base_url,
            is_default=data.is_default,
            default_voice=data.default_voice,
            default_speed=data.default_speed,
            default_language=data.default_language,
            default_format=data.default_format,
            mem_limit=data.mem_limit,
            cpu_quota=data.cpu_quota,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create TTS instance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create TTS instance: {str(e)}",
        )

    # Peer review A-B2: auto-provision runs in background so the HTTP response
    # is not blocked by container startup. Caller polls /container/status.
    if data.auto_provision:
        # BUG-651: flip is_auto_provisioned + container_status BEFORE the
        # thread starts so _to_response() returns the truthful pending state,
        # not the pre-provision defaults (`is_auto_provisioned: false`).
        TTSInstanceService.mark_pending_auto_provision(instance, db)
        threading.Thread(
            target=_provision_bg,
            args=(instance.id, ctx.tenant_id),
            daemon=True,
        ).start()

    return _to_response(instance)


@router.get("/tts-instances/{instance_id}", tags=["TTS Instances"])
async def get_tts_instance(
    instance_id: int,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.tts_instance_service import TTSInstanceService
    instance = TTSInstanceService.get_instance(instance_id, ctx.tenant_id, db)
    if not instance:
        raise HTTPException(status_code=404, detail="TTS instance not found")
    return _to_response(instance)


@router.put("/tts-instances/{instance_id}", tags=["TTS Instances"])
async def update_tts_instance(
    instance_id: int,
    data: TTSInstanceUpdate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.tts_instance_service import TTSInstanceService
    update_data = data.model_dump(exclude_unset=True)
    try:
        instance = TTSInstanceService.update_instance(
            instance_id, ctx.tenant_id, db, **update_data
        )
        if not instance:
            raise HTTPException(status_code=404, detail="TTS instance not found")
        return _to_response(instance)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update TTS instance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update TTS instance",
        )


@router.delete("/tts-instances/{instance_id}", tags=["TTS Instances"])
async def delete_tts_instance(
    instance_id: int,
    remove_volume: bool = False,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.tts_instance_service import TTSInstanceService

    # If auto-provisioned, deprovision the container first (best-effort)
    instance = TTSInstanceService.get_instance(instance_id, ctx.tenant_id, db)
    if instance and instance.is_auto_provisioned:
        try:
            from services.kokoro_container_manager import KokoroContainerManager
            KokoroContainerManager().deprovision(
                instance_id, ctx.tenant_id, db, remove_volume=remove_volume
            )
        except Exception as e:
            logger.warning(f"TTS container deprovision failed: {e}")

    success = TTSInstanceService.delete_instance(instance_id, ctx.tenant_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="TTS instance not found")
    return {"detail": "TTS instance deleted"}


# ============================================================================
# Container lifecycle endpoints
# ============================================================================

@router.post("/tts-instances/{instance_id}/container/{action}", tags=["TTS Instances"])
async def tts_container_action(
    instance_id: int,
    action: Literal["start", "stop", "restart"],
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.kokoro_container_manager import KokoroContainerManager
    mgr = KokoroContainerManager()
    try:
        if action == "start":
            status_val = mgr.start_container(instance_id, ctx.tenant_id, db)
        elif action == "stop":
            status_val = mgr.stop_container(instance_id, ctx.tenant_id, db)
        else:
            status_val = mgr.restart_container(instance_id, ctx.tenant_id, db)
        return {"status": status_val}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Container action failed: {e}")


@router.get("/tts-instances/{instance_id}/container/status", tags=["TTS Instances"])
async def tts_container_status(
    instance_id: int,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.kokoro_container_manager import KokoroContainerManager
    mgr = KokoroContainerManager()
    try:
        return mgr.get_status(instance_id, ctx.tenant_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/tts-instances/{instance_id}/container/logs", tags=["TTS Instances"])
async def tts_container_logs(
    instance_id: int,
    tail: int = Query(default=100, ge=1, le=2000),
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.kokoro_container_manager import KokoroContainerManager
    mgr = KokoroContainerManager()
    try:
        logs = mgr.get_logs(instance_id, ctx.tenant_id, db, tail=tail)
        return {"logs": logs}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Default TTS settings (Config.default_tts_instance_id)
# ============================================================================

@router.get("/settings/tts/default", tags=["TTS Instances"])
async def get_default_tts(
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.tts_instance_service import TTSInstanceService
    default_id, instance = TTSInstanceService.get_config_default(ctx.tenant_id, db)
    return {
        "default_tts_instance_id": default_id,
        "instance": _to_response(instance) if instance else None,
    }


@router.put("/settings/tts/default", tags=["TTS Instances"])
async def set_default_tts(
    data: DefaultTTSUpdate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.tts_instance_service import TTSInstanceService
    try:
        new_id = TTSInstanceService.set_default(
            data.default_tts_instance_id, ctx.tenant_id, db
        )
        return {"default_tts_instance_id": new_id}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to set default TTS instance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to set default TTS instance",
        )


# ============================================================================
# Assign TTS instance to agent (wizard convenience endpoint)
# ============================================================================

@router.post("/tts-instances/{instance_id}/assign-to-agent", tags=["TTS Instances"])
async def assign_tts_instance_to_agent(
    instance_id: int,
    data: TTSAssignToAgentRequest,
    _perm=Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Enable the ``audio_response`` skill on an agent and wire it to this TTS
    instance. Convenience endpoint used by the Kokoro setup wizard so users
    don't have to jump to Agent Studio and configure skills manually.

    Creates a new AgentSkill row if one doesn't already exist for this agent,
    otherwise updates the existing row (preserves any unrelated config keys).

    Tenant isolation is enforced on BOTH the TTS instance and the target agent.
    """
    from services.tts_instance_service import TTSInstanceService

    # 1. Verify the TTS instance belongs to this tenant
    instance = TTSInstanceService.get_instance(instance_id, ctx.tenant_id, db)
    if not instance:
        raise HTTPException(status_code=404, detail="TTS instance not found")

    # 2. Verify the agent belongs to this tenant (double-guard)
    agent = db.query(Agent).filter(Agent.id == data.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {data.agent_id} not found")
    if not ctx.can_access_resource(agent.tenant_id):
        # Same 404 to avoid leaking existence of agents in other tenants
        raise HTTPException(status_code=404, detail=f"Agent {data.agent_id} not found")

    # 3. Build the config payload
    config = {
        "provider": "kokoro",
        "tts_instance_id": instance_id,
        "voice": data.voice or instance.default_voice,
        "language": data.language or instance.default_language,
        "speed": data.speed if data.speed is not None else instance.default_speed,
        "response_format": data.response_format or instance.default_format,
    }

    # 4. Upsert the AgentSkill row
    existing = (
        db.query(AgentSkill)
        .filter(AgentSkill.agent_id == data.agent_id)
        .filter(AgentSkill.skill_type == "audio_response")
        .first()
    )

    if existing:
        # Merge — preserve any unrelated keys callers may have added
        merged = dict(existing.config or {})
        merged.update(config)
        existing.config = merged
        existing.is_enabled = True
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        skill = existing
    else:
        skill = AgentSkill(
            agent_id=data.agent_id,
            skill_type="audio_response",
            is_enabled=True,
            config=config,
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)

    logger.info(
        f"Assigned TTS instance {instance_id} to agent {data.agent_id} "
        f"(tenant={ctx.tenant_id}, voice={config['voice']})"
    )

    return {
        "agent_id": skill.agent_id,
        "skill_id": skill.id,
        "skill_type": skill.skill_type,
        "is_enabled": skill.is_enabled,
        "config": skill.config or {},
    }
