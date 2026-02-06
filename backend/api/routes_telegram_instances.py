"""
Phase 10.1.1: Telegram Bot Integration
API Routes for Telegram Bot Instance Management
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from db import get_db
from models import TelegramBotInstance, Agent
from models_rbac import User
from services.telegram_bot_service import TelegramBotService
from auth_dependencies import get_current_user_required, require_permission, get_tenant_context, TenantContext

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/telegram/instances",
    tags=["Telegram Instances"],
    redirect_slashes=False
)


# Pydantic Schemas
class TelegramInstanceCreate(BaseModel):
    bot_token: str = Field(..., description="Bot token from @BotFather")

    class Config:
        json_schema_extra = {
            "example": {"bot_token": "123456789:ABCdefGHIjklMNOpqrsTUVwxyz"}
        }


class TelegramInstanceResponse(BaseModel):
    id: int
    tenant_id: str
    bot_username: str
    bot_name: Optional[str]
    bot_id: Optional[str]
    status: str
    health_status: str
    use_webhook: bool
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TelegramHealthResponse(BaseModel):
    status: str
    bot_username: str
    api_reachable: bool
    error: Optional[str]


# API Endpoints
@router.post("/", response_model=TelegramInstanceResponse)
async def create_telegram_instance(
    data: TelegramInstanceCreate,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("telegram.instances.create")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Create and validate new Telegram bot instance."""
    try:
        service = TelegramBotService(db)
        instance = await service.create_instance(
            tenant_id=current_user.tenant_id,
            bot_token=data.bot_token,
            created_by=current_user.id
        )

        # Auto-start: mark instance as active and start watcher
        await service.start_instance(instance.id)

        if hasattr(request.app.state, 'telegram_watcher_manager'):
            await request.app.state.telegram_watcher_manager.start_watcher(instance.id)

        # Auto-link: assign this Telegram instance to agents that have
        # "telegram" enabled but no telegram_integration_id yet
        import json as json_lib

        unlinked_agents = db.query(Agent).filter(
            Agent.tenant_id == current_user.tenant_id,
            Agent.telegram_integration_id == None,
            Agent.is_active == True
        ).all()

        linked_count = 0
        for agent in unlinked_agents:
            enabled_channels = agent.enabled_channels if isinstance(agent.enabled_channels, list) else (
                json_lib.loads(agent.enabled_channels) if agent.enabled_channels else []
            )
            if "telegram" in enabled_channels:
                agent.telegram_integration_id = instance.id
                linked_count += 1

        if linked_count > 0:
            db.commit()
            logger.info(f"Auto-linked Telegram instance {instance.id} to {linked_count} agent(s) in tenant {current_user.tenant_id}")

        # Refresh to get updated status
        db.refresh(instance)
        return TelegramInstanceResponse.model_validate(instance)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Failed to create Telegram instance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/", response_model=List[TelegramInstanceResponse])
async def list_telegram_instances(
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("telegram.instances.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """List all Telegram bot instances for current tenant."""
    query = context.filter_by_tenant(
        db.query(TelegramBotInstance),
        TelegramBotInstance.tenant_id
    )
    instances = query.order_by(TelegramBotInstance.created_at.desc()).all()
    return [TelegramInstanceResponse.model_validate(i) for i in instances]


@router.get("/{instance_id}", response_model=TelegramInstanceResponse)
async def get_telegram_instance(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("telegram.instances.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Get Telegram instance details."""
    instance = db.query(TelegramBotInstance).filter(
        TelegramBotInstance.id == instance_id
    ).first()

    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    return TelegramInstanceResponse.model_validate(instance)


@router.post("/{instance_id}/start")
async def start_telegram_instance(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("telegram.instances.manage")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Start Telegram bot polling."""
    instance = db.query(TelegramBotInstance).filter(
        TelegramBotInstance.id == instance_id
    ).first()

    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        service = TelegramBotService(db)
        await service.start_instance(instance_id)

        if hasattr(request.app.state, 'telegram_watcher_manager'):
            await request.app.state.telegram_watcher_manager.start_watcher(instance_id)

        return {"success": True, "message": "Instance started"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{instance_id}/stop")
async def stop_telegram_instance(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("telegram.instances.manage")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Stop Telegram bot polling."""
    instance = db.query(TelegramBotInstance).filter(
        TelegramBotInstance.id == instance_id
    ).first()

    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        service = TelegramBotService(db)
        await service.stop_instance(instance_id)

        if hasattr(request.app.state, 'telegram_watcher_manager'):
            await request.app.state.telegram_watcher_manager.stop_watcher(instance_id)

        return {"success": True, "message": "Instance stopped"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{instance_id}")
async def delete_telegram_instance(
    instance_id: int,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("telegram.instances.delete")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Delete Telegram bot instance."""
    instance = db.query(TelegramBotInstance).filter(
        TelegramBotInstance.id == instance_id
    ).first()

    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Stop watcher first
        if hasattr(request.app.state, 'telegram_watcher_manager'):
            await request.app.state.telegram_watcher_manager.stop_watcher(instance_id)

        service = TelegramBotService(db)
        service.delete_instance(instance_id)

        return {"success": True, "message": "Instance deleted"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{instance_id}/health", response_model=TelegramHealthResponse)
async def get_telegram_health(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("telegram.instances.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """Check Telegram bot health."""
    instance = db.query(TelegramBotInstance).filter(
        TelegramBotInstance.id == instance_id
    ).first()

    if not instance:
        raise HTTPException(status_code=404, detail="Instance not found")
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        service = TelegramBotService(db)
        health = await service.health_check(instance)
        return TelegramHealthResponse(**health)
    except Exception as e:
        return TelegramHealthResponse(
            status="error",
            bot_username=instance.bot_username,
            api_reachable=False,
            error=str(e)
        )
