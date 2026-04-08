"""
v0.6.0: Vector Store Instance Management API Routes

CRUD endpoints for external vector store connections (MongoDB Atlas, Pinecone, Qdrant).
Follows routes_provider_instances.py pattern: tenant isolation, Fernet encryption,
SSRF validation, health checking.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any, Literal
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy.orm import Session
import logging

from models import VectorStoreInstance
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
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ==================== Pydantic Schemas ====================

class VectorStoreInstanceCreate(BaseModel):
    vendor: str  # mongodb | pinecone | qdrant
    instance_name: str
    description: Optional[str] = None
    base_url: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    extra_config: Optional[Dict[str, Any]] = None
    security_config: Optional[Dict[str, Any]] = None
    is_default: bool = False
    auto_provision: bool = False
    mem_limit: Optional[str] = None  # e.g. "1g", "2g"
    cpu_quota: Optional[int] = None  # microseconds, 100000 = 1 CPU


class VectorStoreInstanceUpdate(BaseModel):
    instance_name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    extra_config: Optional[Dict[str, Any]] = None
    security_config: Optional[Dict[str, Any]] = None
    is_default: Optional[bool] = None
    is_active: Optional[bool] = None


class VectorStoreInstanceResponse(BaseModel):
    id: int
    tenant_id: str
    vendor: str
    instance_name: str
    description: Optional[str] = None
    base_url: Optional[str] = None
    credentials_configured: bool
    credentials_preview: str
    extra_config: Dict[str, Any]
    security_config: Dict[str, Any]
    health_status: str
    health_status_reason: Optional[str] = None
    last_health_check: Optional[str] = None
    is_default: bool
    is_active: bool
    is_auto_provisioned: bool = False
    container_status: Optional[str] = None
    container_name: Optional[str] = None
    container_port: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class DefaultVectorStoreUpdate(BaseModel):
    default_vector_store_instance_id: Optional[int] = None


class TestConnectionResponse(BaseModel):
    success: bool
    message: str
    latency_ms: Optional[int] = None
    vector_count: Optional[int] = None


# ==================== Helpers ====================

def _to_response(instance: VectorStoreInstance, db: Session) -> dict:
    from services.vector_store_instance_service import VectorStoreInstanceService
    return {
        "id": instance.id,
        "tenant_id": instance.tenant_id,
        "vendor": instance.vendor,
        "instance_name": instance.instance_name,
        "description": instance.description,
        "base_url": instance.base_url,
        "credentials_configured": bool(instance.credentials_encrypted),
        "credentials_preview": VectorStoreInstanceService.mask_credentials(instance, db),
        "extra_config": instance.extra_config or {},
        "security_config": (getattr(instance, "security_config", None) or {}),
        "health_status": instance.health_status or "unknown",
        "health_status_reason": instance.health_status_reason,
        "last_health_check": instance.last_health_check.isoformat() if instance.last_health_check else None,
        "is_default": instance.is_default,
        "is_active": instance.is_active,
        "is_auto_provisioned": getattr(instance, 'is_auto_provisioned', False),
        "container_status": getattr(instance, 'container_status', None),
        "container_name": getattr(instance, 'container_name', None),
        "container_port": getattr(instance, 'container_port', None),
        "created_at": instance.created_at.isoformat() if instance.created_at else None,
        "updated_at": instance.updated_at.isoformat() if instance.updated_at else None,
    }


# ==================== CRUD Endpoints ====================

@router.get("/vector-stores", tags=["Vector Stores"])
async def list_vector_store_instances(
    vendor: Optional[str] = None,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.vector_store_instance_service import VectorStoreInstanceService
    instances = VectorStoreInstanceService.list_instances(ctx.tenant_id, db, vendor=vendor)
    return [_to_response(inst, db) for inst in (instances or [])]


@router.post("/vector-stores", tags=["Vector Stores"], status_code=status.HTTP_201_CREATED)
async def create_vector_store_instance(
    data: VectorStoreInstanceCreate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.vector_store_instance_service import VectorStoreInstanceService

    # Check duplicate name (active instances)
    existing = db.query(VectorStoreInstance).filter(
        VectorStoreInstance.tenant_id == ctx.tenant_id,
        VectorStoreInstance.instance_name == data.instance_name,
        VectorStoreInstance.is_active == True,
    ).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Vector store instance '{data.instance_name}' already exists",
        )

    # Hard-delete any soft-deleted instance with the same name (UniqueConstraint)
    db.query(VectorStoreInstance).filter(
        VectorStoreInstance.tenant_id == ctx.tenant_id,
        VectorStoreInstance.instance_name == data.instance_name,
        VectorStoreInstance.is_active == False,
    ).delete()

    try:
        instance = VectorStoreInstanceService.create_instance(
            tenant_id=ctx.tenant_id,
            vendor=data.vendor,
            instance_name=data.instance_name,
            db=db,
            description=data.description,
            base_url=data.base_url,
            credentials=data.credentials,
            extra_config=data.extra_config,
            security_config=data.security_config,
            is_default=data.is_default,
        )

        # Auto-provision Docker container if requested
        if data.auto_provision and data.vendor in ("qdrant", "mongodb"):
            import asyncio
            from services.vector_store_container_manager import VectorStoreContainerManager
            if data.mem_limit:
                instance.mem_limit = data.mem_limit
            if data.cpu_quota:
                instance.cpu_quota = data.cpu_quota
            db.commit()
            mgr = VectorStoreContainerManager()
            await asyncio.get_event_loop().run_in_executor(None, mgr.provision, instance, db)

        return _to_response(instance, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create vector store instance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create vector store instance: {str(e)}",
        )


@router.get("/vector-stores/{instance_id}", tags=["Vector Stores"])
async def get_vector_store_instance(
    instance_id: int,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.vector_store_instance_service import VectorStoreInstanceService
    instance = VectorStoreInstanceService.get_instance(instance_id, ctx.tenant_id, db)
    if not instance:
        raise HTTPException(status_code=404, detail="Vector store instance not found")
    return _to_response(instance, db)


@router.put("/vector-stores/{instance_id}", tags=["Vector Stores"])
async def update_vector_store_instance(
    instance_id: int,
    data: VectorStoreInstanceUpdate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.vector_store_instance_service import VectorStoreInstanceService

    update_data = data.model_dump(exclude_unset=True)
    try:
        instance = VectorStoreInstanceService.update_instance(
            instance_id, ctx.tenant_id, db, **update_data
        )
        if not instance:
            raise HTTPException(status_code=404, detail="Vector store instance not found")
        return _to_response(instance, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to update vector store instance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update vector store instance",
        )


@router.delete("/vector-stores/{instance_id}", tags=["Vector Stores"])
async def delete_vector_store_instance(
    instance_id: int,
    remove_volume: bool = False,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.vector_store_instance_service import VectorStoreInstanceService

    # Deprovision container if auto-provisioned
    instance = VectorStoreInstanceService.get_instance(instance_id, ctx.tenant_id, db)
    if instance and getattr(instance, 'is_auto_provisioned', False):
        try:
            from services.vector_store_container_manager import VectorStoreContainerManager
            mgr = VectorStoreContainerManager()
            mgr.deprovision(instance_id, ctx.tenant_id, db, remove_volume=remove_volume)
        except Exception as e:
            logger.warning(f"Container deprovision failed: {e}")

    success = VectorStoreInstanceService.delete_instance(instance_id, ctx.tenant_id, db)
    if not success:
        raise HTTPException(status_code=404, detail="Vector store instance not found")
    return {"detail": "Vector store instance deleted"}


# ==================== Health & Stats ====================

@router.post("/vector-stores/{instance_id}/test", tags=["Vector Stores"])
async def test_vector_store_connection(
    instance_id: int,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.vector_store_instance_service import VectorStoreInstanceService
    result = await VectorStoreInstanceService.test_connection(instance_id, ctx.tenant_id, db)
    return result


@router.get("/vector-stores/{instance_id}/stats", tags=["Vector Stores"])
async def get_vector_store_stats(
    instance_id: int,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.vector_store_instance_service import VectorStoreInstanceService
    stats = await VectorStoreInstanceService.get_stats(instance_id, ctx.tenant_id, db)
    return stats


# ==================== Container Lifecycle ====================

@router.post("/vector-stores/{instance_id}/container/{action}", tags=["Vector Stores"])
async def vector_store_container_action(
    instance_id: int,
    action: Literal["start", "stop", "restart"],
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):

    from services.vector_store_container_manager import VectorStoreContainerManager
    mgr = VectorStoreContainerManager()
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


@router.get("/vector-stores/{instance_id}/container/status", tags=["Vector Stores"])
async def vector_store_container_status(
    instance_id: int,
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.vector_store_container_manager import VectorStoreContainerManager
    mgr = VectorStoreContainerManager()
    try:
        return mgr.get_status(instance_id, ctx.tenant_id, db)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/vector-stores/{instance_id}/container/logs", tags=["Vector Stores"])
async def vector_store_container_logs(
    instance_id: int,
    tail: int = Query(default=100, ge=1, le=2000),
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    from services.vector_store_container_manager import VectorStoreContainerManager
    mgr = VectorStoreContainerManager()
    try:
        logs = mgr.get_logs(instance_id, ctx.tenant_id, db, tail=tail)
        return {"logs": logs}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# ==================== Default Vector Store Settings ====================

@router.get("/settings/vector-stores/default", tags=["Vector Stores"])
async def get_default_vector_store(
    ctx: TenantContext = Depends(require_permission("org.settings.read")),
    db: Session = Depends(get_db),
):
    # Tenant-scoped: query VectorStoreInstance.is_default (not global Config)
    default_instance = db.query(VectorStoreInstance).filter(
        VectorStoreInstance.tenant_id == ctx.tenant_id,
        VectorStoreInstance.is_default == True,
        VectorStoreInstance.is_active == True,
    ).first()

    return {
        "default_vector_store_instance_id": default_instance.id if default_instance else None,
        "instance": _to_response(default_instance, db) if default_instance else None,
    }


@router.put("/settings/vector-stores/default", tags=["Vector Stores"])
async def set_default_vector_store(
    data: DefaultVectorStoreUpdate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    # Validate instance exists and belongs to tenant
    if data.default_vector_store_instance_id is not None:
        from services.vector_store_instance_service import VectorStoreInstanceService
        instance = VectorStoreInstanceService.get_instance(
            data.default_vector_store_instance_id, ctx.tenant_id, db
        )
        if not instance:
            raise HTTPException(status_code=404, detail="Vector store instance not found")

    # Clear all is_default flags for this tenant, then set the new one
    db.query(VectorStoreInstance).filter(
        VectorStoreInstance.tenant_id == ctx.tenant_id,
    ).update({"is_default": False})

    if data.default_vector_store_instance_id:
        db.query(VectorStoreInstance).filter(
            VectorStoreInstance.id == data.default_vector_store_instance_id,
            VectorStoreInstance.tenant_id == ctx.tenant_id,
        ).update({"is_default": True})

    db.commit()
    return {"default_vector_store_instance_id": data.default_vector_store_instance_id}
