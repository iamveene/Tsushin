"""
Hub Integration API Routes
Phase 7.9.2: Added tenant isolation for multi-tenancy support

Provides REST API endpoints for Hub integrations (Asana, Slack, etc.).
"""

import logging
from typing import Dict, List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from pydantic import BaseModel

from models import AsanaIntegration, HubIntegration, Agent, CalendarIntegration, GmailIntegration
from models_rbac import User
from hub.asana.oauth_handler import AsanaOAuthHandler
from hub.asana.asana_service import AsanaService
from hub.google.calendar_service import CalendarService
from hub.google.gmail_service import GmailService
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission,
    get_current_user_required
)
from services.encryption_key_service import get_asana_encryption_key
import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/hub", tags=["Hub Integrations"])

# Global engine reference (set by main app.py)
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


# ============================================================================
# Request/Response Models
# ============================================================================

class OAuthAuthorizeRequest(BaseModel):
    redirect_url: Optional[str] = None
    workspace_name: Optional[str] = None  # User-provided workspace name


class OAuthAuthorizeResponse(BaseModel):
    authorization_url: str
    state_token: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


class OAuthCallbackResponse(BaseModel):
    integration_id: int
    workspace_gid: str
    workspace_name: str
    user_gid: str
    redirect_url: Optional[str] = None
    all_workspaces: List[Dict]


class IntegrationResponse(BaseModel):
    id: int
    type: str
    name: str
    is_active: bool
    health_status: str
    health_status_reason: Optional[str] = None
    tenant_id: Optional[str] = None
    workspace_gid: Optional[str] = None
    workspace_name: Optional[str] = None
    default_assignee_name: Optional[str] = None
    default_assignee_gid: Optional[str] = None
    email: Optional[str] = None
    display_name: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    last_check: str
    details: Dict
    errors: List[str]


class ToolResponse(BaseModel):
    name: str
    description: str
    input_schema: Dict


class ToolExecuteRequest(BaseModel):
    tool_name: str
    arguments: Dict


class ResolveUserRequest(BaseModel):
    name: str


class ResolveUserResponse(BaseModel):
    gid: str
    name: str


class UpdateDefaultAssigneeRequest(BaseModel):
    assignee_name: Optional[str] = None  # Set to null to clear


# ============================================================================
# Helper Functions
# ============================================================================

def get_asana_oauth_handler(
    db: Session = Depends(get_db),
    ctx: TenantContext = Depends(get_tenant_context)
) -> AsanaOAuthHandler:
    """
    Get Asana OAuth handler with Dynamic Client Registration support.

    Encryption key loaded from database or environment.
    Client ID/Secret obtained via Dynamic Client Registration on first use.

    Phase 7.9.2: Passes tenant_id for creating tenant-scoped integrations.
    """
    import os

    encryption_key = get_asana_encryption_key(db)
    if not encryption_key:
        raise HTTPException(
            status_code=500,
            detail="ASANA_ENCRYPTION_KEY not configured in database or environment. Generate with: python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'"
        )

    redirect_uri = os.getenv("ASANA_REDIRECT_URI", "http://localhost:3030/hub/asana/callback")

    # Load client credentials from database (if already registered)
    from models import Config
    config = db.query(Config).first()

    client_id = config.asana_mcp_client_id if config and config.asana_mcp_registered else None
    client_secret = config.asana_mcp_client_secret if config and config.asana_mcp_registered else None

    handler = AsanaOAuthHandler(
        db=db,
        encryption_key=encryption_key,
        redirect_uri=redirect_uri,
        client_id=client_id,
        client_secret=client_secret
    )
    # Store tenant_id for use in callback
    handler._tenant_id = ctx.tenant_id
    return handler


def _create_asana_service(integration_id: int, db: Session) -> AsanaService:
    """
    Internal helper to create AsanaService instance.

    Note: Caller is responsible for calling service.close() when done.
    """
    import os
    from models import Config

    encryption_key = get_asana_encryption_key(db)
    if not encryption_key:
        raise HTTPException(status_code=500, detail="ASANA_ENCRYPTION_KEY not configured in database or environment")

    redirect_uri = os.getenv("ASANA_REDIRECT_URI", "http://localhost:3030/hub/asana/callback")

    # Load client credentials from database
    config = db.query(Config).first()
    client_id = config.asana_mcp_client_id if config else None
    client_secret = config.asana_mcp_client_secret if config else None

    try:
        return AsanaService(
            db=db,
            integration_id=integration_id,
            encryption_key=encryption_key,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


async def get_asana_service(integration_id: int, db: Session = Depends(get_db)):
    """
    FastAPI dependency to get Asana service with automatic cleanup.

    Uses async generator pattern to ensure MCP connection is closed after request.
    """
    service = _create_asana_service(integration_id, db)
    try:
        yield service
    finally:
        # Close MCP connection to prevent TaskGroup errors
        await service.close()


def verify_integration_access(
    integration: HubIntegration,
    ctx: TenantContext
) -> None:
    """
    Verify user can access an integration.

    Phase 7.9.2: Checks tenant isolation.
    """
    if not ctx.can_access_resource(integration.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this integration")


# ============================================================================
# OAuth Endpoints
# ============================================================================

@router.post("/asana/oauth/authorize", response_model=OAuthAuthorizeResponse)
async def asana_oauth_authorize(
    request: OAuthAuthorizeRequest,
    oauth_handler: AsanaOAuthHandler = Depends(get_asana_oauth_handler),
    current_user: User = Depends(require_permission("hub.write"))
):
    """
    Generate Asana OAuth authorization URL.

    Starts the OAuth flow by generating an authorization URL with CSRF state token.
    Automatically registers MCP client on first use (Dynamic Client Registration).

    Phase 7.9.2: Requires hub.write permission.
    """
    try:
        auth_url, state_token = await oauth_handler.generate_authorization_url(
            redirect_url=request.redirect_url,
            workspace_name=request.workspace_name
        )

        return OAuthAuthorizeResponse(
            authorization_url=auth_url,
            state_token=state_token
        )
    except Exception as e:
        logger.error(f"OAuth authorize failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/asana/oauth/callback", response_model=OAuthCallbackResponse)
async def asana_oauth_callback(
    request: OAuthCallbackRequest,
    db: Session = Depends(get_db),
    oauth_handler: AsanaOAuthHandler = Depends(get_asana_oauth_handler),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Handle OAuth callback from Asana.

    Validates state token (CSRF protection), exchanges code for tokens,
    and creates/updates integration in database.

    Phase 7.9.2: Assigns integration to user's tenant.
    """
    try:
        result = await oauth_handler.handle_callback(
            code=request.code,
            state=request.state
        )

        # Update the integration with tenant_id
        if result.get('integration_id') and ctx.tenant_id:
            integration = db.query(HubIntegration).filter(
                HubIntegration.id == result['integration_id']
            ).first()
            if integration and not integration.tenant_id:
                integration.tenant_id = ctx.tenant_id
                db.commit()

        return OAuthCallbackResponse(**result)
    except ValueError as e:
        logger.error(f"OAuth callback failed: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"OAuth callback error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/asana/oauth/disconnect/{integration_id}")
async def asana_oauth_disconnect(
    integration_id: int,
    db: Session = Depends(get_db),
    oauth_handler: AsanaOAuthHandler = Depends(get_asana_oauth_handler),
    current_user: User = Depends(require_permission("hub.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Disconnect Asana integration and revoke tokens.

    Phase 7.9.2: Verifies user can access this integration (tenant check).
    """
    try:
        # Get integration
        integration = db.query(AsanaIntegration).filter(
            AsanaIntegration.id == integration_id
        ).first()

        if not integration:
            raise HTTPException(status_code=404, detail="Integration not found")

        # Verify tenant access
        verify_integration_access(integration, ctx)

        # Disconnect
        await oauth_handler.disconnect_integration(
            integration_id=integration_id,
            workspace_gid=integration.workspace_gid
        )

        return {"message": "Integration disconnected successfully"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Disconnect failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# Integration Management
# ============================================================================

@router.get("/integrations", response_model=List[IntegrationResponse])
async def list_integrations(
    active_only: bool = Query(True),
    refresh_health: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List all Hub integrations.

    Args:
        active_only: Only return active integrations
        refresh_health: Trigger health check for all integrations before returning

    Phase 7.9.2: Returns integrations for user's tenant AND shared (NULL tenant_id).
    """
    # Query base integrations first
    query = db.query(HubIntegration)

    # Apply tenant filtering
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"[list_integrations] User tenant_id: {ctx.tenant_id}, is_global_admin: {ctx.is_global_admin}")

    query = ctx.filter_by_tenant(query, HubIntegration.tenant_id)

    if active_only:
        # Also include unavailable integrations (need re-auth) so the UI can show them
        from sqlalchemy import or_
        query = query.filter(or_(
            HubIntegration.is_active == True,
            HubIntegration.health_status == "unavailable"
        ))

    hub_integrations = query.all()
    logger.info(f"[list_integrations] Found {len(hub_integrations)} integrations: {[(h.id, h.type, h.tenant_id) for h in hub_integrations]}")

    integrations = []
    for hub in hub_integrations:
        # Get type-specific data by checking the type
        asana = None
        calendar = None
        gmail = None

        if hub.type == 'asana':
            asana = db.query(AsanaIntegration).filter(AsanaIntegration.id == hub.id).first()
            # Optionally refresh health
            if refresh_health:
                service = None
                try:
                    service = _create_asana_service(hub.id, db)
                    health_result = await service.check_health()
                    hub.health_status = health_result['status']
                    hub.last_health_check = datetime.utcnow()
                    db.commit()
                except Exception as e:
                    logger.warning(f"Health check failed for integration {hub.id}: {e}")
                finally:
                    if service:
                        await service.close()
        elif hub.type == 'calendar':
            calendar = db.query(CalendarIntegration).filter(CalendarIntegration.id == hub.id).first()
            # Optionally refresh health for calendar integrations
            if refresh_health:
                try:
                    service = CalendarService(db, hub.id)
                    health_result = await service.check_health()
                    hub.health_status = health_result['status']
                    hub.last_health_check = datetime.utcnow()
                    db.commit()
                except Exception as e:
                    logger.warning(f"Calendar health check failed for integration {hub.id}: {e}")
                    hub.health_status = 'unavailable'
                    db.commit()
        elif hub.type == 'gmail':
            gmail = db.query(GmailIntegration).filter(GmailIntegration.id == hub.id).first()
            # Optionally refresh health for gmail integrations
            if refresh_health:
                try:
                    service = GmailService(db, hub.id)
                    health_result = await service.check_health()
                    hub.health_status = health_result['status']
                    hub.last_health_check = datetime.utcnow()
                    db.commit()
                except Exception as e:
                    logger.warning(f"Gmail health check failed for integration {hub.id}: {e}")
                    hub.health_status = 'unavailable'
                    db.commit()

        # Build response with type-specific data
        response = IntegrationResponse(
            id=hub.id,
            type=hub.type,
            name=hub.name,
            is_active=hub.is_active,
            health_status=hub.health_status,
            health_status_reason=getattr(hub, 'health_status_reason', None),
            tenant_id=hub.tenant_id,
            workspace_gid=asana.workspace_gid if asana else None,
            workspace_name=asana.workspace_name if asana else None,
            default_assignee_name=asana.default_assignee_name if asana else None,
            default_assignee_gid=asana.default_assignee_gid if asana else None,
            # Add email for calendar/gmail integrations
            email=(calendar.email_address if calendar else (gmail.email_address if gmail else None)),
            display_name=hub.display_name
        )
        integrations.append(response)

    return integrations


@router.get("/asana/{integration_id}/health", response_model=HealthResponse)
async def asana_health_check(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Check health of Asana integration.

    Phase 7.9.2: Verifies user can access this integration (tenant check).
    """
    # Verify access first
    integration = db.query(HubIntegration).filter(HubIntegration.id == integration_id).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    verify_integration_access(integration, ctx)

    service = None
    try:
        service = _create_asana_service(integration_id, db)
        health = await service.check_health()
        return HealthResponse(**health)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if service:
            await service.close()


# ============================================================================
# Tool Management
# ============================================================================

@router.get("/asana/{integration_id}/tools", response_model=List[ToolResponse])
async def asana_list_tools(
    integration_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List available Asana tools for integration.

    Phase 7.9.2: Verifies user can access this integration (tenant check).
    """
    # Verify access first
    integration = db.query(HubIntegration).filter(HubIntegration.id == integration_id).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    verify_integration_access(integration, ctx)

    service = None
    try:
        service = _create_asana_service(integration_id, db)
        tools = await service.list_tools()

        return [
            ToolResponse(
                name=tool.name,
                description=tool.description,
                input_schema=tool.input_schema
            )
            for tool in tools
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"List tools failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if service:
            await service.close()


@router.post("/asana/{integration_id}/tools/execute")
async def asana_execute_tool(
    integration_id: int,
    request: ToolExecuteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Execute Asana tool.

    For testing and manual execution. Agents use this via AsanaService.

    Phase 7.9.2: Verifies user can access this integration (tenant check).
    """
    # Verify access first
    integration = db.query(HubIntegration).filter(HubIntegration.id == integration_id).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    verify_integration_access(integration, ctx)

    service = None
    try:
        service = _create_asana_service(integration_id, db)
        result = await service.execute_tool(
            tool_name=request.tool_name,
            arguments=request.arguments
        )

        return {"result": result}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tool execution failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if service:
            await service.close()


# ============================================================================
# Agent Integration - DEPRECATED
# ============================================================================
# Agent integration endpoints removed - use AgentSkillIntegration instead
# Integrations (e.g., Asana) are now configured as skill providers via:
#   - /api/agents/{agent_id}/skill-integrations/{skill_type} (routes_agents_protected.py)
# Migration: See backend/migrations/migrate_hub_integration_to_skills.py


@router.post("/asana/{integration_id}/resolve-user", response_model=ResolveUserResponse)
async def resolve_asana_user(
    integration_id: int,
    request: ResolveUserRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Resolve Asana user name to GID.

    Searches for user by name in the workspace (case-insensitive, partial match).

    Phase 7.9.2: Verifies user can access this integration (tenant check).
    """
    integration = db.query(AsanaIntegration).filter(
        AsanaIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Verify tenant access
    verify_integration_access(integration, ctx)

    if not integration.is_active:
        raise HTTPException(status_code=400, detail="Integration is not active")

    # Create Asana service
    service = None
    try:
        service = _create_asana_service(integration_id, db)

        # Resolve user
        user_info = await service.resolve_user_by_name(request.name)

        if not user_info:
            raise HTTPException(
                status_code=404,
                detail=f"No user found matching '{request.name}' in workspace"
            )

        return ResolveUserResponse(
            gid=user_info["gid"],
            name=user_info["name"]
        )

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error resolving user: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to resolve user")
    finally:
        if service:
            await service.close()


@router.patch("/asana/{integration_id}/default-assignee")
async def update_default_assignee(
    integration_id: int,
    request: UpdateDefaultAssigneeRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Update default assignee for Asana integration.

    If assignee_name is provided, resolves it to GID and stores both.
    If assignee_name is null, clears the default assignee.

    Phase 7.9.2: Verifies user can access this integration (tenant check).
    """
    integration = db.query(AsanaIntegration).filter(
        AsanaIntegration.id == integration_id
    ).first()

    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")

    # Verify tenant access
    verify_integration_access(integration, ctx)

    # Clear assignee if name is null
    if request.assignee_name is None:
        integration.default_assignee_name = None
        integration.default_assignee_gid = None
        db.commit()
        return {
            "message": "Default assignee cleared",
            "default_assignee_name": None,
            "default_assignee_gid": None
        }

    # Resolve name to GID
    service = None
    try:
        service = _create_asana_service(integration_id, db)

        user_info = await service.resolve_user_by_name(request.assignee_name)

        if not user_info:
            raise HTTPException(
                status_code=404,
                detail=f"No user found matching '{request.assignee_name}' in workspace"
            )

        # Update integration
        integration.default_assignee_name = user_info["name"]
        integration.default_assignee_gid = user_info["gid"]
        db.commit()

        return {
            "message": "Default assignee updated successfully",
            "default_assignee_name": user_info["name"],
            "default_assignee_gid": user_info["gid"]
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating default assignee: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to update default assignee")
    finally:
        if service:
            await service.close()
