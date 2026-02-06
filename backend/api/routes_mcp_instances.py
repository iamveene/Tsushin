"""
Phase 8: Multi-Tenant MCP Containerization
API Routes for WhatsApp MCP Instance Management

Provides REST API endpoints for managing Docker containers of WhatsApp MCP instances.
Includes RBAC protection and tenant isolation.
"""

import logging
from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from db import get_db
from models import WhatsAppMCPInstance, Agent
from models_rbac import User
from services.mcp_container_manager import MCPContainerManager
from auth_dependencies import get_current_user_required, require_permission, get_tenant_context, TenantContext

logger = logging.getLogger(__name__)
router = APIRouter(
    prefix="/api/mcp/instances",
    tags=["MCP Instances"],
    redirect_slashes=False  # Prevent 307 redirects that lose Authorization header
)

# ============================================================================
# Pydantic Schemas
# ============================================================================

class MCPInstanceCreate(BaseModel):
    """Request schema for creating MCP instance"""
    phone_number: str = Field(..., description="WhatsApp phone number (e.g., +5500000000001)")
    instance_type: str = Field(default="agent", pattern="^(agent|tester)$", description="Instance type: 'agent' (bot) or 'tester' (QA)")

    class Config:
        json_schema_extra = {
            "example": {
                "phone_number": "+5500000000001",
                "instance_type": "agent"
            }
        }


class MCPInstanceResponse(BaseModel):
    """Response schema for MCP instance"""
    id: int
    tenant_id: str
    container_name: str
    phone_number: str
    instance_type: str
    mcp_api_url: str
    mcp_port: int
    messages_db_path: str
    session_data_path: str
    status: str
    health_status: str
    container_id: Optional[str]
    is_group_handler: bool = False  # Phase 10: Group handler flag for deduplication
    # Phase 17: Instance-Level Message Filtering
    group_filters: Optional[List[str]] = None  # WhatsApp group names to monitor
    number_filters: Optional[List[str]] = None  # Phone numbers for DM allowlist
    group_keywords: Optional[List[str]] = None  # Keywords that trigger responses
    dm_auto_mode: bool = False  # Auto-reply to unknown DMs
    created_at: datetime
    last_started_at: Optional[datetime]
    last_stopped_at: Optional[datetime]

    class Config:
        from_attributes = True


class MCPInstanceFiltersUpdate(BaseModel):
    """Request schema for updating instance message filters"""
    group_filters: Optional[List[str]] = Field(None, description="WhatsApp group names to monitor")
    number_filters: Optional[List[str]] = Field(None, description="Phone numbers for DM allowlist")
    group_keywords: Optional[List[str]] = Field(None, description="Keywords that trigger responses")
    dm_auto_mode: Optional[bool] = Field(None, description="Auto-reply to unknown DMs")


class SetGroupHandlerRequest(BaseModel):
    """Request schema for setting group handler"""
    is_group_handler: bool = Field(..., description="Whether this instance should handle group messages")


class MCPHealthResponse(BaseModel):
    """Response schema for health check with enhanced session monitoring"""
    status: str
    container_state: str
    api_reachable: bool
    connected: Optional[bool] = False
    authenticated: Optional[bool] = False
    needs_reauth: Optional[bool] = False
    is_reconnecting: Optional[bool] = False
    reconnect_attempts: Optional[int] = 0
    session_age_sec: Optional[int] = 0
    last_activity_sec: Optional[int] = 0
    error: Optional[str]


class QRCodeResponse(BaseModel):
    """Response schema for QR code"""
    qr_code: Optional[str]
    message: Optional[str]


class LogoutResponse(BaseModel):
    """Response schema for logout/reset authentication"""
    success: bool
    message: str
    qr_code_ready: bool
    backup_path: Optional[str] = None


# ============================================================================
# API Endpoints
# ============================================================================

@router.post("/", response_model=MCPInstanceResponse)
async def create_mcp_instance(
    data: MCPInstanceCreate,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.create")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Create and start new WhatsApp MCP instance

    **Permissions Required:** `mcp.instances.create`

    Creates a Docker container, allocates port, and sets up session storage.
    Returns instance details with `status='starting'`.
    Use `/health` endpoint to monitor startup progress.
    """
    try:
        manager = MCPContainerManager()

        instance = manager.create_instance(
            tenant_id=current_user.tenant_id,
            phone_number=data.phone_number,
            db=db,
            created_by=current_user.id,
            instance_type=data.instance_type
        )

        logger.info(f"MCP instance {instance.id} ({data.instance_type}) created for tenant {current_user.tenant_id}")

        # Start watcher dynamically ONLY for agent instances (not tester)
        if data.instance_type == "agent" and hasattr(request.app.state, 'watcher_manager'):
            watcher_started = await request.app.state.watcher_manager.start_watcher_for_instance(instance.id, db)
            if watcher_started:
                logger.info(f"Watcher started dynamically for new instance {instance.id}")
            else:
                logger.warning(f"Failed to start watcher for new instance {instance.id}")
        elif data.instance_type == "tester":
            logger.info(f"Skipping watcher for tester instance {instance.id}")

        # Auto-link: assign this WhatsApp instance to agents that have
        # "whatsapp" enabled but no whatsapp_integration_id yet (agent instances only)
        if data.instance_type == "agent":
            import json as json_lib

            unlinked_agents = db.query(Agent).filter(
                Agent.tenant_id == current_user.tenant_id,
                Agent.whatsapp_integration_id == None,
                Agent.is_active == True
            ).all()

            linked_count = 0
            for agent in unlinked_agents:
                enabled_channels = agent.enabled_channels if isinstance(agent.enabled_channels, list) else (
                    json_lib.loads(agent.enabled_channels) if agent.enabled_channels else []
                )
                if "whatsapp" in enabled_channels:
                    agent.whatsapp_integration_id = instance.id
                    linked_count += 1

            if linked_count > 0:
                db.commit()
                logger.info(f"Auto-linked WhatsApp instance {instance.id} to {linked_count} agent(s) in tenant {current_user.tenant_id}")

            # Mark first agent instance as group handler if none set yet
            existing_group_handler = db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.tenant_id == current_user.tenant_id,
                WhatsAppMCPInstance.is_group_handler == True
            ).first()
            if not existing_group_handler:
                instance.is_group_handler = True
                db.commit()
                logger.info(f"Marked WhatsApp instance {instance.id} as group handler for tenant {current_user.tenant_id}")

        return MCPInstanceResponse.model_validate(instance)

    except Exception as e:
        logger.error(f"Failed to create MCP instance: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to create MCP instance: {str(e)}")


@router.get("/", response_model=List[MCPInstanceResponse])
async def list_mcp_instances(
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    List all MCP instances for current tenant

    **Permissions Required:** `mcp.instances.read`

    Global admins see all instances across all tenants.
    Regular users see only their tenant's instances.
    """
    query = context.filter_by_tenant(db.query(WhatsAppMCPInstance), WhatsAppMCPInstance.tenant_id)
    instances = query.order_by(WhatsAppMCPInstance.created_at.desc()).all()

    logger.info(f"Returning {len(instances)} MCP instances for tenant {current_user.tenant_id}")

    return [MCPInstanceResponse.model_validate(inst) for inst in instances]


@router.get("/{instance_id}", response_model=MCPInstanceResponse)
async def get_mcp_instance(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Get MCP instance details by ID

    **Permissions Required:** `mcp.instances.read`
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    return MCPInstanceResponse.model_validate(instance)


@router.post("/{instance_id}/start")
async def start_mcp_instance(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.manage")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Start stopped MCP instance

    **Permissions Required:** `mcp.instances.manage`
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        manager = MCPContainerManager()
        manager.start_instance(instance_id, db)

        logger.info(f"MCP instance {instance_id} started by user {current_user.id}")

        # Start watcher dynamically for agent instances (not tester)
        # This ensures the watcher is running to process incoming messages
        from fastapi import Request
        import asyncio

        if instance.instance_type == "agent":
            # Get the request from the context to access app.state
            # Use a background task to start the watcher without blocking
            async def start_watcher_bg():
                from services.watcher_manager import WatcherManager
                from sqlalchemy.orm import sessionmaker
                from db import _global_engine
                try:
                    # Wait a moment for container to be ready
                    await asyncio.sleep(5)

                    if _global_engine is None:
                        logger.error("Database engine not initialized")
                        return

                    # Create new DB session for background task
                    SessionLocal = sessionmaker(bind=_global_engine)
                    bg_db = SessionLocal()
                    try:
                        # Get app state from the global variable set at startup
                        import app as app_module
                        if hasattr(app_module, 'app') and hasattr(app_module.app, 'state'):
                            watcher_manager = WatcherManager(app_module.app.state)
                            started = await watcher_manager.start_watcher_for_instance(instance_id, bg_db)
                            if started:
                                logger.info(f"✅ Watcher started dynamically after instance {instance_id} start")
                            else:
                                logger.warning(f"⚠️ Could not start watcher for instance {instance_id}")
                    finally:
                        bg_db.close()
                except Exception as e:
                    logger.error(f"Error starting watcher for instance {instance_id}: {e}", exc_info=True)

            # Start in background
            asyncio.create_task(start_watcher_bg())

        return {"success": True, "message": f"Instance {instance_id} starting"}

    except Exception as e:
        logger.error(f"Failed to start instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to start instance: {str(e)}")


@router.post("/{instance_id}/stop")
async def stop_mcp_instance(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.manage")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Stop running MCP instance

    **Permissions Required:** `mcp.instances.manage`
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        manager = MCPContainerManager()
        manager.stop_instance(instance_id, db)

        logger.info(f"MCP instance {instance_id} stopped by user {current_user.id}")

        return {"success": True, "message": f"Instance {instance_id} stopped"}

    except Exception as e:
        logger.error(f"Failed to stop instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to stop instance: {str(e)}")


@router.post("/{instance_id}/restart")
async def restart_mcp_instance(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.manage")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Restart MCP instance

    **Permissions Required:** `mcp.instances.manage`
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        manager = MCPContainerManager()
        manager.restart_instance(instance_id, db)

        logger.info(f"MCP instance {instance_id} restarted by user {current_user.id}")

        return {"success": True, "message": f"Instance {instance_id} restarting"}

    except Exception as e:
        logger.error(f"Failed to restart instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to restart instance: {str(e)}")


@router.post("/{instance_id}/pause")
async def pause_watcher_instance(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.manage")),
    context: TenantContext = Depends(get_tenant_context),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Pause watcher for MCP instance - stops message processing without stopping the container
    Bug Fix 2026-01-06: Allow temporary pause of message processing

    **Permissions Required:** `mcp.instances.manage`
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Get watcher manager from app state
        if not request or not hasattr(request.app.state, 'watcher_manager'):
            raise HTTPException(status_code=500, detail="Watcher manager not available")

        watcher_manager = request.app.state.watcher_manager
        success = await watcher_manager.pause_watcher_for_instance(instance_id)

        if not success:
            raise HTTPException(status_code=400, detail="Watcher not found or already paused")

        logger.info(f"Watcher paused for instance {instance_id} by user {current_user.id}")

        return {"success": True, "message": f"Watcher for instance {instance_id} paused"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to pause watcher for instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to pause watcher: {str(e)}")


@router.post("/{instance_id}/resume")
async def resume_watcher_instance(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.manage")),
    context: TenantContext = Depends(get_tenant_context),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Resume watcher for MCP instance - restarts message processing
    Bug Fix 2026-01-06: Resume message processing after pause

    **Permissions Required:** `mcp.instances.manage`
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Get watcher manager from app state
        if not request or not hasattr(request.app.state, 'watcher_manager'):
            raise HTTPException(status_code=500, detail="Watcher manager not available")

        watcher_manager = request.app.state.watcher_manager
        success = await watcher_manager.resume_watcher_for_instance(instance_id)

        if not success:
            raise HTTPException(status_code=400, detail="Watcher not found or not paused")

        logger.info(f"Watcher resumed for instance {instance_id} by user {current_user.id}")

        return {"success": True, "message": f"Watcher for instance {instance_id} resumed"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to resume watcher for instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to resume watcher: {str(e)}")


@router.get("/{instance_id}/watcher-status")
async def get_watcher_status(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.read")),
    context: TenantContext = Depends(get_tenant_context),
    request: Request = None,
    db: Session = Depends(get_db)
):
    """
    Get watcher status for MCP instance
    Bug Fix 2026-01-06: Check if watcher is running/paused

    **Permissions Required:** `mcp.instances.read`
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Get watcher manager from app state
        if not request or not hasattr(request.app.state, 'watcher_manager'):
            return {"exists": False, "running": False, "paused": False}

        watcher_manager = request.app.state.watcher_manager
        status = watcher_manager.get_watcher_status(instance_id)

        return status

    except Exception as e:
        logger.error(f"Failed to get watcher status for instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to get watcher status: {str(e)}")


@router.put("/{instance_id}/group-handler")
async def set_group_handler(
    instance_id: int,
    data: SetGroupHandlerRequest,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.manage")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Set or unset MCP instance as group handler

    **Permissions Required:** `mcp.instances.manage`

    **Phase 10: Group Message Deduplication**
    Only one instance per tenant should be the group handler.
    When setting is_group_handler=True, all other instances for the same tenant
    will have is_group_handler set to False automatically.
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # If setting as group handler, unset all other instances in this tenant
        if data.is_group_handler:
            db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.tenant_id == instance.tenant_id,
                WhatsAppMCPInstance.id != instance_id
            ).update({"is_group_handler": False})

        # Update this instance
        instance.is_group_handler = data.is_group_handler
        db.commit()

        logger.info(
            f"MCP instance {instance_id} {'set as' if data.is_group_handler else 'unset as'} "
            f"group handler by user {current_user.id}"
        )

        return {
            "success": True,
            "message": f"Instance {instance_id} {'is now' if data.is_group_handler else 'is no longer'} the group handler",
            "is_group_handler": data.is_group_handler
        }

    except Exception as e:
        logger.error(f"Failed to set group handler for instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to set group handler: {str(e)}")


@router.put("/{instance_id}/filters", response_model=MCPInstanceResponse)
async def update_instance_filters(
    instance_id: int,
    data: MCPInstanceFiltersUpdate,
    request: Request,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.manage")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Update message filtering configuration for MCP instance

    **Permissions Required:** `mcp.instances.manage`

    Phase 17: Instance-Level Message Filtering
    These settings control which messages trigger agent responses for this WhatsApp instance.

    - **group_filters**: List of WhatsApp group names to monitor
    - **number_filters**: List of phone numbers allowed to DM (allowlist)
    - **group_keywords**: Keywords that trigger responses in groups
    - **dm_auto_mode**: Auto-reply to DMs from unknown senders
    """
    import json

    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Update only provided fields
        if data.group_filters is not None:
            instance.group_filters = data.group_filters
        if data.number_filters is not None:
            instance.number_filters = data.number_filters
        if data.group_keywords is not None:
            instance.group_keywords = data.group_keywords
        if data.dm_auto_mode is not None:
            instance.dm_auto_mode = data.dm_auto_mode

        instance.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(instance)

        logger.info(
            f"MCP instance {instance_id} filters updated by user {current_user.id}: "
            f"groups={len(data.group_filters or [])}, numbers={len(data.number_filters or [])}, "
            f"keywords={len(data.group_keywords or [])}, dm_auto={data.dm_auto_mode}"
        )

        # Hot-reload watcher filter if instance is running
        if hasattr(request.app.state, 'watcher_manager'):
            try:
                watcher_manager = request.app.state.watcher_manager
                watcher_manager.reload_instance_filter(instance_id)
                logger.info(f"Hot-reloaded filter for instance {instance_id}")
            except Exception as e:
                logger.warning(f"Could not hot-reload filter for instance {instance_id}: {e}")

        # Parse JSON fields for response
        response_data = {
            **instance.__dict__,
            "group_filters": instance.group_filters if isinstance(instance.group_filters, list) else (json.loads(instance.group_filters) if instance.group_filters else None),
            "number_filters": instance.number_filters if isinstance(instance.number_filters, list) else (json.loads(instance.number_filters) if instance.number_filters else None),
            "group_keywords": instance.group_keywords if isinstance(instance.group_keywords, list) else (json.loads(instance.group_keywords) if instance.group_keywords else None),
        }

        return MCPInstanceResponse.model_validate(response_data)

    except Exception as e:
        logger.error(f"Failed to update filters for instance {instance_id}: {e}", exc_info=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update filters: {str(e)}")


@router.delete("/{instance_id}")
async def delete_mcp_instance(
    instance_id: int,
    request: Request,
    remove_data: bool = Query(False, description="Delete session data (messages.db, etc.)"),
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.delete")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Delete MCP instance and optionally remove data

    **Permissions Required:** `mcp.instances.delete`

    **CAUTION:** Deleting with `remove_data=true` permanently removes:
    - WhatsApp session (requires QR scan on next creation)
    - Message history (messages.db)
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # Stop watcher BEFORE deleting instance
        if hasattr(request.app.state, 'watcher_manager'):
            watcher_stopped = await request.app.state.watcher_manager.stop_watcher_for_instance(instance_id)
            if watcher_stopped:
                logger.info(f"Watcher stopped dynamically for instance {instance_id}")

        manager = MCPContainerManager()
        manager.delete_instance(instance_id, db, remove_data=remove_data)

        logger.info(f"MCP instance {instance_id} deleted by user {current_user.id} (remove_data={remove_data})")

        return {"success": True, "message": f"Instance {instance_id} deleted"}

    except Exception as e:
        logger.error(f"Failed to delete instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to delete instance: {str(e)}")


@router.get("/{instance_id}/health", response_model=MCPHealthResponse)
async def get_mcp_health(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Check MCP instance health (container + API)

    **Permissions Required:** `mcp.instances.read`

    **Health States:**
    - `healthy`: Container running, API responding
    - `degraded`: Container running, API not responding
    - `unhealthy`: Container stopped or error
    - `unavailable`: Container not found
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        manager = MCPContainerManager()
        health_data = manager.health_check(instance)

        # Log health check results for debugging
        logger.info(
            f"Health check for instance {instance_id}: "
            f"status={health_data['status']}, "
            f"container={health_data['container_state']}, "
            f"authenticated={health_data['authenticated']}, "
            f"connected={health_data['connected']}"
        )

        # Update database with latest health status
        old_status = instance.status
        old_health = instance.health_status

        instance.health_status = health_data['status']
        instance.status = health_data['container_state']
        instance.last_health_check = datetime.utcnow()
        db.commit()

        # Log status changes
        if old_status != health_data['container_state'] or old_health != health_data['status']:
            logger.info(
                f"Instance {instance_id} status changed: "
                f"container {old_status} -> {health_data['container_state']}, "
                f"health {old_health} -> {health_data['status']}"
            )

        return MCPHealthResponse(**health_data)

    except Exception as e:
        logger.error(f"Failed to check health for instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to check health: {str(e)}")


@router.get("/{instance_id}/qr-code", response_model=QRCodeResponse)
async def get_qr_code(
    instance_id: int,
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.read")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Get WhatsApp QR code for authentication

    **Permissions Required:** `mcp.instances.read`

    Returns base64-encoded QR code image that can be scanned with WhatsApp mobile app.
    QR code is only available during initial setup before authentication completes.
    """
    instance = db.query(WhatsAppMCPInstance).filter(WhatsAppMCPInstance.id == instance_id).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # Check tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        manager = MCPContainerManager()
        qr_code = manager.get_qr_code(instance)

        if qr_code:
            return QRCodeResponse(qr_code=qr_code, message="Scan QR code with WhatsApp")
        else:
            return QRCodeResponse(
                qr_code=None,
                message="QR code not available (already authenticated or container not ready)"
            )

    except Exception as e:
        logger.error(f"Failed to fetch QR code for instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to fetch QR code: {str(e)}")


@router.post("/{instance_id}/logout", response_model=LogoutResponse)
async def logout_mcp_instance(
    instance_id: int,
    backup: bool = Query(True, description="Backup session before deletion"),
    current_user: User = Depends(get_current_user_required),
    _: None = Depends(require_permission("mcp.instances.manage")),
    context: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db)
):
    """
    Reset WhatsApp authentication (logout)

    **Permissions Required:** `mcp.instances.manage`

    Deletes WhatsApp session data to force new QR code generation.
    Messages are preserved. Container restarts automatically.

    **Use Cases:**
    - QR code stuck showing "Already authenticated"
    - Need to re-authenticate same WhatsApp number
    - Session expired or lost

    **What happens:**
    1. Container is stopped gracefully
    2. Session file (`whatsapp.db`) is backed up (if backup=True)
    3. Session file is deleted (messages are preserved)
    4. Container is restarted
    5. New QR code is generated within ~30 seconds

    **Parameters:**
    - **instance_id**: MCP instance ID
    - **backup**: Create backup before deletion (default: True)

    **Returns:**
    - **success**: Whether operation succeeded
    - **message**: Human-readable result
    - **qr_code_ready**: Whether QR code is immediately available
    - **backup_path**: Path to backup file (if created)
    """
    # 1. Fetch instance
    instance = db.query(WhatsAppMCPInstance).filter(
        WhatsAppMCPInstance.id == instance_id
    ).first()

    if not instance:
        raise HTTPException(status_code=404, detail=f"MCP instance {instance_id} not found")

    # 2. Verify tenant access
    if not context.can_access_resource(instance.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # 3. Call service layer
    try:
        manager = MCPContainerManager()
        result = manager.logout_instance(instance_id, db, backup=backup)

        # 4. Audit log
        logger.info(f"User {current_user.id} ({current_user.email}) reset auth for instance {instance_id}")

        return LogoutResponse(**result)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        logger.error(f"Logout failed for instance {instance_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Logout failed: {str(e)}")
