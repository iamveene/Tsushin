"""
Track D: ASR Instance Management API Routes

Backend-only checkpoint for per-tenant Whisper/Speaches instances.
"""

import logging
import threading
from typing import Optional, Dict, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session, sessionmaker

from auth_dependencies import TenantContext, require_permission
from models import ASRInstance

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


class ASRInstanceCreate(BaseModel):
    vendor: str = "speaches"
    instance_name: str
    description: Optional[str] = None
    base_url: Optional[str] = None
    auto_provision: bool = True
    mem_limit: Optional[str] = None
    cpu_quota: Optional[int] = None
    default_model: Optional[str] = None


class ASRInstanceUpdate(BaseModel):
    instance_name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    mem_limit: Optional[str] = None
    cpu_quota: Optional[int] = None
    default_model: Optional[str] = None
    is_active: Optional[bool] = None


def _to_response(instance: ASRInstance) -> Dict[str, Any]:
    return {
        "id": instance.id,
        "tenant_id": instance.tenant_id,
        "vendor": instance.vendor,
        "instance_name": instance.instance_name,
        "description": instance.description,
        "base_url": instance.base_url,
        "auth_username": instance.auth_username,
        "default_model": instance.default_model,
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


def _provision_bg(instance_id: int, tenant_id: str) -> None:
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        from services.whisper_instance_service import WhisperInstanceService

        instance = WhisperInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            logger.error("_provision_bg: ASR instance %s not found for %s", instance_id, tenant_id)
            return
        WhisperInstanceService.provision_instance(
            instance,
            db,
            fail_open_on_error=True,
            warning_context=f"ASR instance '{instance.instance_name}'",
        )
    except Exception as e:
        logger.error("_provision_bg failed for ASR instance %s: %s", instance_id, e, exc_info=True)
    finally:
        try:
            db.close()
        except Exception:
            pass


@router.get("/asr-instances", tags=["ASR Instances"])
async def list_asr_instances(
    vendor: Optional[str] = None,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.whisper_instance_service import WhisperInstanceService

    instances = WhisperInstanceService.list_instances(ctx.tenant_id, db, vendor=vendor)
    return [_to_response(inst) for inst in (instances or [])]


@router.post("/asr-instances", tags=["ASR Instances"], status_code=status.HTTP_202_ACCEPTED)
async def create_asr_instance(
    data: ASRInstanceCreate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.whisper_instance_service import WhisperInstanceService, SUPPORTED_VENDORS

    if data.vendor not in SUPPORTED_VENDORS:
        raise HTTPException(status_code=400, detail=f"Unsupported vendor: {data.vendor}")

    existing = db.query(ASRInstance).filter(
        ASRInstance.tenant_id == ctx.tenant_id,
        ASRInstance.instance_name == data.instance_name,
        ASRInstance.is_active == True,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"ASR instance '{data.instance_name}' already exists",
        )

    db.query(ASRInstance).filter(
        ASRInstance.tenant_id == ctx.tenant_id,
        ASRInstance.instance_name == data.instance_name,
        ASRInstance.is_active == False,
    ).delete()
    db.commit()

    try:
        instance = WhisperInstanceService.create_instance(
            tenant_id=ctx.tenant_id,
            vendor=data.vendor,
            instance_name=data.instance_name,
            db=db,
            description=data.description,
            base_url=data.base_url,
            default_model=data.default_model,
            mem_limit=data.mem_limit,
            cpu_quota=data.cpu_quota,
            auto_provision=data.auto_provision,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to create ASR instance: %s", e)
        raise HTTPException(status_code=500, detail=f"Failed to create ASR instance: {e}")

    if data.auto_provision:
        WhisperInstanceService.mark_pending_auto_provision(instance, db)
        threading.Thread(
            target=_provision_bg,
            args=(instance.id, ctx.tenant_id),
            daemon=True,
        ).start()

    return _to_response(instance)


@router.get("/asr-instances/{instance_id}", tags=["ASR Instances"])
async def get_asr_instance(
    instance_id: int,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.whisper_instance_service import WhisperInstanceService

    instance = WhisperInstanceService.get_instance(instance_id, ctx.tenant_id, db)
    if not instance:
        raise HTTPException(status_code=404, detail="ASR instance not found")
    return _to_response(instance)


@router.put("/asr-instances/{instance_id}", tags=["ASR Instances"])
async def update_asr_instance(
    instance_id: int,
    data: ASRInstanceUpdate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.whisper_instance_service import WhisperInstanceService

    try:
        instance = WhisperInstanceService.update_instance(
            instance_id,
            ctx.tenant_id,
            db,
            **data.model_dump(exclude_unset=True),
        )
        if not instance:
            raise HTTPException(status_code=404, detail="ASR instance not found")
        return _to_response(instance)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/asr-instances/{instance_id}", tags=["ASR Instances"])
async def delete_asr_instance(
    instance_id: int,
    remove_volume: bool = False,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.whisper_container_manager import WhisperContainerManager
    from services.whisper_instance_service import WhisperInstanceService

    instance = WhisperInstanceService.get_instance(instance_id, ctx.tenant_id, db)
    if instance and instance.is_auto_provisioned:
        try:
            WhisperContainerManager().deprovision(
                instance_id,
                ctx.tenant_id,
                db,
                remove_volume=remove_volume,
            )
        except Exception as e:
            logger.warning("ASR container deprovision failed: %s", e)

    success = WhisperInstanceService.delete_instance(instance_id, ctx.tenant_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="ASR instance not found")
    return {"detail": "ASR instance deleted"}


@router.post("/asr-instances/{instance_id}/container/{action}", tags=["ASR Instances"])
async def asr_container_action(
    instance_id: int,
    action: Literal["start", "stop", "restart"],
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.whisper_container_manager import WhisperContainerManager

    mgr = WhisperContainerManager()
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


@router.get("/asr-instances/{instance_id}/container/status", tags=["ASR Instances"])
async def asr_container_status(
    instance_id: int,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.whisper_container_manager import WhisperContainerManager

    mgr = WhisperContainerManager()
    try:
        return mgr.get_status(instance_id, ctx.tenant_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/asr-instances/{instance_id}/container/logs", tags=["ASR Instances"])
async def asr_container_logs(
    instance_id: int,
    tail: int = Query(default=100, ge=1, le=2000),
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.whisper_container_manager import WhisperContainerManager

    mgr = WhisperContainerManager()
    try:
        return {"logs": mgr.get_logs(instance_id, ctx.tenant_id, db, tail=tail)}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
