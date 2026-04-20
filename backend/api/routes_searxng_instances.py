"""
v0.6.0-patch.6: SearXNG Instance Management API Routes

CRUD + container-lifecycle endpoints for per-tenant SearXNG instances. Mirrors
routes_tts_instances.py: tenant isolation via TenantContext, soft-delete,
auto-provision-in-background so POST can return 202 immediately.
"""

import logging
import threading
from datetime import datetime
from typing import Optional, Dict, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from models import SearxngInstance, Agent, AgentSkill
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

class SearxngInstanceCreate(BaseModel):
    instance_name: str = "default"
    description: Optional[str] = None
    base_url: Optional[str] = None
    auto_provision: bool = True
    mem_limit: Optional[str] = None
    cpu_quota: Optional[int] = None
    # Wizard convenience: optionally wire the new instance to an agent in one go.
    assign_to_agent_id: Optional[int] = None


class SearxngInstanceUpdate(BaseModel):
    instance_name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    is_active: Optional[bool] = None
    mem_limit: Optional[str] = None
    cpu_quota: Optional[int] = None


class SearxngAssignToAgentRequest(BaseModel):
    agent_id: int


# ============================================================================
# Helpers
# ============================================================================

def _to_response(instance: SearxngInstance) -> Dict[str, Any]:
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
        "is_active": bool(instance.is_active),
        "is_auto_provisioned": bool(instance.is_auto_provisioned),
        "container_status": instance.container_status,
        "container_name": instance.container_name,
        "container_port": instance.container_port,
        "container_image": instance.container_image,
        "volume_name": instance.volume_name,
        "mem_limit": instance.mem_limit,
        "cpu_quota": instance.cpu_quota,
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
        "updated_at": instance.updated_at.isoformat() if instance.updated_at else None,
    }


def _provision_bg(instance_id: int, tenant_id: str, assign_to_agent_id: Optional[int]) -> None:
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        from services.searxng_instance_service import SearxngInstanceService
        instance = SearxngInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            logger.error(f"_provision_bg: searxng instance {instance_id} not found for {tenant_id}")
            return
        SearxngInstanceService.provision_instance(
            instance, db,
            fail_open_on_error=True,
            warning_context=f"SearXNG instance '{instance.instance_name}'",
        )
        # After provisioning completes, auto-link to the agent if requested.
        if assign_to_agent_id is not None:
            try:
                _assign_searxng_to_agent(instance_id, tenant_id, assign_to_agent_id, db)
            except Exception as e:
                logger.warning(f"Auto-assign searxng to agent {assign_to_agent_id} failed: {e}")
    except Exception as e:
        logger.error(f"_provision_bg failed for searxng instance {instance_id}: {e}", exc_info=True)
    finally:
        try:
            db.close()
        except Exception:
            pass


def _assign_searxng_to_agent(
    instance_id: int, tenant_id: str, agent_id: int, db: Session
) -> Dict[str, Any]:
    from services.searxng_instance_service import SearxngInstanceService
    instance = SearxngInstanceService.get_instance(instance_id, tenant_id, db)
    if not instance:
        raise ValueError("SearXNG instance not found")

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent or agent.tenant_id != tenant_id:
        raise ValueError(f"Agent {agent_id} not found for tenant")

    existing = (
        db.query(AgentSkill)
        .filter(AgentSkill.agent_id == agent_id)
        .filter(AgentSkill.skill_type == "web_search")
        .first()
    )
    cfg = {"provider": "searxng", "searxng_instance_id": instance_id}
    if existing:
        merged = dict(existing.config or {})
        merged.update(cfg)
        existing.config = merged
        existing.is_enabled = True
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        skill = existing
    else:
        skill = AgentSkill(
            agent_id=agent_id,
            skill_type="web_search",
            is_enabled=True,
            config=cfg,
        )
        db.add(skill)
        db.commit()
        db.refresh(skill)
    return {
        "agent_id": skill.agent_id,
        "skill_id": skill.id,
        "skill_type": skill.skill_type,
        "is_enabled": skill.is_enabled,
        "config": skill.config or {},
    }


# ============================================================================
# CRUD endpoints
# ============================================================================

@router.get("/hub/searxng/instances", tags=["SearXNG Instances"])
async def list_searxng_instances(
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.searxng_instance_service import SearxngInstanceService
    instances = SearxngInstanceService.list_instances(ctx.tenant_id, db)
    return [_to_response(inst) for inst in (instances or [])]


@router.post(
    "/hub/searxng/instances",
    tags=["SearXNG Instances"],
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_searxng_instance(
    data: SearxngInstanceCreate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.searxng_instance_service import SearxngInstanceService

    # Duplicate-name guard
    existing = db.query(SearxngInstance).filter(
        SearxngInstance.tenant_id == ctx.tenant_id,
        SearxngInstance.instance_name == data.instance_name,
        SearxngInstance.is_active == True,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"SearXNG instance '{data.instance_name}' already exists",
        )

    # Clear any soft-deleted row with the same name (UniqueConstraint)
    db.query(SearxngInstance).filter(
        SearxngInstance.tenant_id == ctx.tenant_id,
        SearxngInstance.instance_name == data.instance_name,
        SearxngInstance.is_active == False,
    ).delete()
    db.commit()

    try:
        instance = SearxngInstanceService.create_instance(
            tenant_id=ctx.tenant_id,
            instance_name=data.instance_name,
            db=db,
            description=data.description,
            base_url=data.base_url,
            mem_limit=data.mem_limit,
            cpu_quota=data.cpu_quota,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create SearXNG instance: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create SearXNG instance: {e}")

    if data.auto_provision:
        SearxngInstanceService.mark_pending_auto_provision(instance, db)
        threading.Thread(
            target=_provision_bg,
            args=(instance.id, ctx.tenant_id, data.assign_to_agent_id),
            daemon=True,
        ).start()
    elif data.assign_to_agent_id is not None:
        # External URL flow — no container to wait on; link now.
        try:
            _assign_searxng_to_agent(instance.id, ctx.tenant_id, data.assign_to_agent_id, db)
        except Exception as e:
            logger.warning(f"Assign searxng to agent failed: {e}")

    return _to_response(instance)


@router.get("/hub/searxng/instances/{instance_id}", tags=["SearXNG Instances"])
async def get_searxng_instance(
    instance_id: int,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.searxng_instance_service import SearxngInstanceService
    instance = SearxngInstanceService.get_instance(instance_id, ctx.tenant_id, db)
    if not instance:
        raise HTTPException(status_code=404, detail="SearXNG instance not found")
    return _to_response(instance)


@router.put("/hub/searxng/instances/{instance_id}", tags=["SearXNG Instances"])
async def update_searxng_instance(
    instance_id: int,
    data: SearxngInstanceUpdate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.searxng_instance_service import SearxngInstanceService
    update_data = data.model_dump(exclude_unset=True)
    try:
        instance = SearxngInstanceService.update_instance(
            instance_id, ctx.tenant_id, db, **update_data
        )
        if not instance:
            raise HTTPException(status_code=404, detail="SearXNG instance not found")
        return _to_response(instance)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update SearXNG instance: {e}")
        raise HTTPException(status_code=500, detail="Failed to update SearXNG instance")


@router.delete("/hub/searxng/instances/{instance_id}", tags=["SearXNG Instances"])
async def delete_searxng_instance(
    instance_id: int,
    remove_volume: bool = True,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.searxng_instance_service import SearxngInstanceService

    instance = SearxngInstanceService.get_instance(instance_id, ctx.tenant_id, db)
    if instance and instance.is_auto_provisioned:
        try:
            from services.searxng_container_manager import SearxngContainerManager
            SearxngContainerManager().deprovision(
                instance_id, ctx.tenant_id, db, remove_volume=remove_volume
            )
        except Exception as e:
            logger.warning(f"SearXNG container deprovision failed: {e}")

    # Unlink this instance from any agent's web_search skill config so the
    # resolver falls back to the default provider after deletion.
    try:
        rows = (
            db.query(AgentSkill)
            .filter(AgentSkill.skill_type == "web_search")
            .all()
        )
        for skill in rows:
            cfg = dict(skill.config or {})
            if cfg.get("searxng_instance_id") == instance_id or cfg.get("provider") == "searxng":
                cfg.pop("searxng_instance_id", None)
                # Revert to default provider (leave unset; search_skill.default = brave)
                if cfg.get("provider") == "searxng":
                    cfg.pop("provider", None)
                skill.config = cfg
                skill.updated_at = datetime.utcnow()
        db.commit()
    except Exception as e:
        logger.warning(f"SearXNG unlink from agents failed: {e}")

    success = SearxngInstanceService.delete_instance(instance_id, ctx.tenant_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="SearXNG instance not found")
    return {"detail": "SearXNG instance deleted"}


# ============================================================================
# Container lifecycle endpoints
# ============================================================================

@router.post("/hub/searxng/instances/{instance_id}/container/{action}", tags=["SearXNG Instances"])
async def searxng_container_action(
    instance_id: int,
    action: Literal["start", "stop", "restart"],
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.searxng_container_manager import SearxngContainerManager
    mgr = SearxngContainerManager()
    try:
        if action == "start":
            s = mgr.start_container(instance_id, ctx.tenant_id, db)
        elif action == "stop":
            s = mgr.stop_container(instance_id, ctx.tenant_id, db)
        else:
            s = mgr.restart_container(instance_id, ctx.tenant_id, db)
        return {"status": s}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Container action failed: {e}")


@router.get("/hub/searxng/instances/{instance_id}/container/status", tags=["SearXNG Instances"])
async def searxng_container_status(
    instance_id: int,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.searxng_container_manager import SearxngContainerManager
    mgr = SearxngContainerManager()
    try:
        return mgr.get_status(instance_id, ctx.tenant_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/hub/searxng/instances/{instance_id}/container/logs", tags=["SearXNG Instances"])
async def searxng_container_logs(
    instance_id: int,
    tail: int = Query(default=100, ge=1, le=2000),
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.searxng_container_manager import SearxngContainerManager
    mgr = SearxngContainerManager()
    try:
        logs = mgr.get_logs(instance_id, ctx.tenant_id, db, tail=tail)
        return {"logs": logs}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ============================================================================
# Assign to agent
# ============================================================================

@router.post(
    "/hub/searxng/instances/{instance_id}/assign-to-agent",
    tags=["SearXNG Instances"],
)
async def assign_searxng_to_agent(
    instance_id: int,
    data: SearxngAssignToAgentRequest,
    _perm=Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    try:
        return _assign_searxng_to_agent(instance_id, ctx.tenant_id, data.agent_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
