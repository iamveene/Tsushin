"""
v0.6.1: Vector Store Instance Management API Routes

CRUD endpoints for external vector store connections (MongoDB Atlas, Pinecone, Qdrant).
Follows routes_provider_instances.py pattern: tenant isolation, Fernet encryption,
SSRF validation, health checking.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
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
    is_default: bool = False


class VectorStoreInstanceUpdate(BaseModel):
    instance_name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None
    credentials: Optional[Dict[str, Any]] = None
    extra_config: Optional[Dict[str, Any]] = None
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
    health_status: str
    health_status_reason: Optional[str] = None
    last_health_check: Optional[str] = None
    is_default: bool
    is_active: bool
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


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
        "health_status": instance.health_status or "unknown",
        "health_status_reason": instance.health_status_reason,
        "last_health_check": instance.last_health_check.isoformat() if instance.last_health_check else None,
        "is_default": instance.is_default,
        "is_active": instance.is_active,
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
    return [_to_response(inst, db) for inst in instances]


@router.post("/vector-stores", tags=["Vector Stores"], status_code=status.HTTP_201_CREATED)
async def create_vector_store_instance(
    data: VectorStoreInstanceCreate,
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.vector_store_instance_service import VectorStoreInstanceService

    # Check duplicate name
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
            is_default=data.is_default,
        )
        return _to_response(instance, db)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create vector store instance: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create vector store instance",
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
    ctx: TenantContext = Depends(require_permission("org.settings.write")),
    db: Session = Depends(get_db),
):
    from services.vector_store_instance_service import VectorStoreInstanceService
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
