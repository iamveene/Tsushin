"""
Hub API — Public API v1
Provider-agnostic facade for Hub integrations (Asana, Gmail, Calendar).
Provides integration listing, health checks, tool discovery, and tool execution.
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models import HubIntegration, AsanaIntegration, CalendarIntegration, GmailIntegration, GoogleFlightsIntegration
from api.api_auth import ApiCaller, require_api_permission
from api.v1.schemas import COMMON_RESPONSES, NOT_FOUND_RESPONSE


# BUG-347: Capability matrix — defines what each integration type actually supports
INTEGRATION_CAPABILITIES: Dict[str, Dict[str, bool]] = {
    "asana": {"health_check": True, "tools": True, "tool_execution": True},
    "gmail": {"health_check": True, "tools": False, "tool_execution": False},
    "calendar": {"health_check": True, "tools": False, "tool_execution": False},
    "google_flights": {"health_check": False, "tools": False, "tool_execution": False},
}

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class IntegrationSummary(BaseModel):
    """Summary of a Hub integration."""
    id: int = Field(description="Integration ID", example=1)
    type: str = Field(description="Integration type: asana, calendar, gmail", example="asana")
    name: str = Field(description="Integration display name", example="Asana - My Workspace")
    display_name: Optional[str] = Field(None, description="Custom display name")
    is_active: bool = Field(description="Whether the integration is active", example=True)
    health_status: str = Field(description="Health status: healthy, degraded, unavailable, unknown", example="healthy")
    health_status_reason: Optional[str] = Field(None, description="Reason for non-healthy status")
    tenant_id: Optional[str] = Field(None, description="Owning tenant ID")
    created_at: Optional[str] = Field(None, description="Creation timestamp (ISO 8601)")


class IntegrationDetailResponse(BaseModel):
    """Detailed integration information including type-specific data."""
    id: int = Field(description="Integration ID")
    type: str = Field(description="Integration type")
    name: str = Field(description="Integration display name")
    display_name: Optional[str] = Field(None, description="Custom display name")
    is_active: bool = Field(description="Whether the integration is active")
    health_status: str = Field(description="Health status")
    health_status_reason: Optional[str] = Field(None, description="Reason for non-healthy status")
    tenant_id: Optional[str] = Field(None, description="Owning tenant ID")
    last_health_check: Optional[str] = Field(None, description="Last health check timestamp")
    workspace_gid: Optional[str] = Field(None, description="Asana workspace GID (Asana only)")
    workspace_name: Optional[str] = Field(None, description="Asana workspace name (Asana only)")
    email: Optional[str] = Field(None, description="Email address (Gmail/Calendar only)")


class HealthCheckResponse(BaseModel):
    """Integration health check result."""
    integration_id: int = Field(description="Integration ID")
    status: str = Field(description="Health status: healthy, degraded, unavailable", example="healthy")
    last_check: str = Field(description="Timestamp of the health check (ISO 8601)")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional health details")
    errors: List[str] = Field(default_factory=list, description="List of errors if unhealthy")


class ToolInfo(BaseModel):
    """Information about an available tool on an integration."""
    name: str = Field(description="Tool name", example="create_task")
    description: str = Field(description="Tool description", example="Create a new Asana task")
    input_schema: Dict[str, Any] = Field(description="JSON Schema for tool input parameters")


class ToolExecuteRequest(BaseModel):
    """Request body for executing a tool on an integration."""
    tool_name: str = Field(..., description="Name of the tool to execute", example="create_task")
    arguments: Dict[str, Any] = Field(..., description="Tool arguments", example={"name": "New Task", "notes": "Task description"})


class ToolExecuteResponse(BaseModel):
    """Response from tool execution."""
    result: Any = Field(description="Tool execution result")
    integration_id: int = Field(description="Integration ID used")
    tool_name: str = Field(description="Tool that was executed")


class ProviderInfo(BaseModel):
    """Information about a supported provider type."""
    type: str = Field(description="Provider type identifier", example="asana")
    name: str = Field(description="Human-readable provider name", example="Asana")
    description: str = Field(description="Provider description", example="Project and task management")
    supports_oauth: bool = Field(description="Whether this provider supports OAuth", example=True)


# ============================================================================
# Helpers
# ============================================================================

def _get_integration_or_404(db: Session, integration_id: int, tenant_id: str) -> HubIntegration:
    """Get a HubIntegration filtered by tenant, or raise 404."""
    integration = db.query(HubIntegration).filter(
        HubIntegration.id == integration_id,
    ).first()
    if not integration:
        raise HTTPException(status_code=404, detail="Integration not found")
    # Tenant isolation: check integration belongs to caller's tenant or is shared (NULL tenant_id)
    if integration.tenant_id and integration.tenant_id != tenant_id:
        raise HTTPException(status_code=404, detail="Integration not found")
    return integration


def _create_service_for_integration(integration: HubIntegration, db: Session):
    """Create the appropriate service instance based on integration type."""
    if integration.type == "asana":
        return _create_asana_service(integration.id, db)
    elif integration.type == "calendar":
        from hub.google.calendar_service import CalendarService
        return CalendarService(db, integration.id)
    elif integration.type == "gmail":
        from hub.google.gmail_service import GmailService
        return GmailService(db, integration.id)
    elif integration.type == "google_flights":
        raise HTTPException(
            status_code=400,
            detail="Google Flights integration does not support service operations through the Hub API. It is available as an agent skill only.",
        )
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported integration type: {integration.type}")


def _create_asana_service(integration_id: int, db: Session):
    """Create AsanaService instance (extracted from routes_hub)."""
    import os
    from models import Config
    from hub.asana.asana_service import AsanaService
    from services.encryption_key_service import get_asana_encryption_key

    encryption_key = get_asana_encryption_key(db)
    if not encryption_key:
        raise HTTPException(status_code=500, detail="ASANA_ENCRYPTION_KEY not configured")

    redirect_uri = os.getenv("ASANA_REDIRECT_URI", "http://localhost:3030/hub/asana/callback")

    config = db.query(Config).first()
    client_id = config.asana_mcp_client_id if config and config.asana_mcp_registered else None
    client_secret = config.asana_mcp_client_secret if config and config.asana_mcp_registered else None

    try:
        return AsanaService(
            db=db,
            integration_id=integration_id,
            encryption_key=encryption_key,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


def _integration_to_summary(hub: HubIntegration) -> dict:
    """Convert HubIntegration to a summary dict."""
    caps = INTEGRATION_CAPABILITIES.get(hub.type, {"health_check": False, "tools": False, "tool_execution": False})
    return {
        "id": hub.id,
        "type": hub.type,
        "name": hub.name,
        "display_name": hub.display_name,
        "is_active": hub.is_active,
        "health_status": hub.health_status,
        "health_status_reason": getattr(hub, "health_status_reason", None),
        "tenant_id": hub.tenant_id,
        "created_at": hub.created_at.isoformat() if hasattr(hub, "created_at") and hub.created_at else None,
        "capabilities": caps,
    }


# ============================================================================
# Endpoints
# ============================================================================

@router.get("/api/v1/hub/integrations", responses=COMMON_RESPONSES)
async def list_integrations(
    active_only: bool = Query(True, description="Only return active integrations"),
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("hub.read")),
):
    """
    List all Hub integrations with health status.

    Returns integrations belonging to the caller's tenant and shared (NULL tenant_id)
    integrations. Each entry includes type-specific fields (e.g. workspace_gid for
    Asana, email for Gmail/Calendar). Filterable by active status.
    """
    from sqlalchemy import or_

    query = db.query(HubIntegration).filter(
        or_(
            HubIntegration.tenant_id == caller.tenant_id,
            HubIntegration.tenant_id.is_(None),
        )
    )

    if active_only:
        query = query.filter(
            or_(
                HubIntegration.is_active == True,
                HubIntegration.health_status == "unavailable",
            )
        )

    integrations = query.all()

    results = []
    for hub in integrations:
        summary = _integration_to_summary(hub)

        # Add type-specific fields
        if hub.type == "asana":
            asana = db.query(AsanaIntegration).filter(AsanaIntegration.id == hub.id).first()
            if asana:
                summary["workspace_gid"] = asana.workspace_gid
                summary["workspace_name"] = asana.workspace_name
        elif hub.type == "calendar":
            cal = db.query(CalendarIntegration).filter(CalendarIntegration.id == hub.id).first()
            if cal:
                summary["email"] = cal.email_address
        elif hub.type == "gmail":
            gmail = db.query(GmailIntegration).filter(GmailIntegration.id == hub.id).first()
            if gmail:
                summary["email"] = gmail.email_address

        results.append(summary)

    return {"data": results}


@router.get("/api/v1/hub/integrations/{integration_id}", responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE})
async def get_integration(
    integration_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("hub.read")),
):
    """
    Get detailed information about a specific integration.

    Includes type-specific data like workspace name (Asana) or email (Gmail/Calendar).
    Returns 404 if the integration does not exist or belongs to another tenant.
    """
    hub = _get_integration_or_404(db, integration_id, caller.tenant_id)

    result = _integration_to_summary(hub)
    result["last_health_check"] = hub.last_health_check.isoformat() if hub.last_health_check else None

    # Type-specific enrichment
    if hub.type == "asana":
        asana = db.query(AsanaIntegration).filter(AsanaIntegration.id == hub.id).first()
        if asana:
            result["workspace_gid"] = asana.workspace_gid
            result["workspace_name"] = asana.workspace_name
            result["default_assignee_name"] = asana.default_assignee_name
            result["default_assignee_gid"] = asana.default_assignee_gid
    elif hub.type == "calendar":
        cal = db.query(CalendarIntegration).filter(CalendarIntegration.id == hub.id).first()
        if cal:
            result["email"] = cal.email_address
    elif hub.type == "gmail":
        gmail = db.query(GmailIntegration).filter(GmailIntegration.id == hub.id).first()
        if gmail:
            result["email"] = gmail.email_address

    return result


@router.get(
    "/api/v1/hub/integrations/{integration_id}/health",
    response_model=HealthCheckResponse,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def check_integration_health(
    integration_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("hub.read")),
):
    """
    Check the health of a specific integration.

    Performs an active health check against the integration provider and
    returns the current status with any errors.
    """
    hub = _get_integration_or_404(db, integration_id, caller.tenant_id)

    # BUG-347: Check capability before attempting health check
    caps = INTEGRATION_CAPABILITIES.get(hub.type, {})
    if not caps.get("health_check"):
        raise HTTPException(
            status_code=400,
            detail=f"Integration type '{hub.type}' does not support health checks.",
        )

    service = None
    try:
        service = _create_service_for_integration(hub, db)
        health = await service.check_health()

        # Update stored health status
        hub.health_status = health.get("status", "unknown")
        hub.last_health_check = datetime.utcnow()
        db.commit()

        return {
            "integration_id": integration_id,
            "status": health.get("status", "unknown"),
            "last_check": datetime.utcnow().isoformat(),
            "details": health.get("details", {}),
            "errors": health.get("errors", []),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Health check failed for integration {integration_id}: {e}", exc_info=True)
        return {
            "integration_id": integration_id,
            "status": "unavailable",
            "last_check": datetime.utcnow().isoformat(),
            "details": {},
            "errors": [str(e)],
        }
    finally:
        if service and hasattr(service, "close"):
            try:
                await service.close()
            except Exception:
                pass


@router.get(
    "/api/v1/hub/integrations/{integration_id}/tools",
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def list_integration_tools(
    integration_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("hub.read")),
):
    """
    List available tools for a specific integration.

    Returns the tool name, description, and input schema for each tool
    exposed by the integration provider. Returns 404 if the integration
    does not exist or belongs to another tenant.
    """
    hub = _get_integration_or_404(db, integration_id, caller.tenant_id)

    # BUG-347: Check capability before attempting tool listing
    caps = INTEGRATION_CAPABILITIES.get(hub.type, {})
    if not caps.get("tools"):
        raise HTTPException(
            status_code=400,
            detail=f"Integration type '{hub.type}' does not support tool listing. Check the 'capabilities' field in the integration listing.",
        )

    service = None
    try:
        service = _create_service_for_integration(hub, db)

        if not hasattr(service, "list_tools"):
            raise HTTPException(status_code=400, detail=f"Integration type '{hub.type}' does not support tool listing")

        tools = await service.list_tools()

        return {
            "data": [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                }
                for tool in tools
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to list tools for integration {integration_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Failed to list tools. Check server logs for details.")
    finally:
        if service and hasattr(service, "close"):
            try:
                await service.close()
            except Exception:
                pass


@router.post(
    "/api/v1/hub/integrations/{integration_id}/tools/execute",
    response_model=ToolExecuteResponse,
    responses={
        **COMMON_RESPONSES,
        **NOT_FOUND_RESPONSE,
        400: {"description": "Integration inactive or unsupported"},
    },
)
async def execute_integration_tool(
    integration_id: int,
    request: ToolExecuteRequest,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("hub.write")),
):
    """
    Execute a tool on a specific integration.

    Dispatches the tool execution to the correct provider service based on
    the integration type. The tool_name must match one of the available tools
    returned by the tools listing endpoint. Returns 400 if the integration
    is inactive or its type does not support tool execution.
    """
    hub = _get_integration_or_404(db, integration_id, caller.tenant_id)

    if not hub.is_active:
        raise HTTPException(status_code=400, detail="Integration is not active")

    # BUG-347: Check capability before attempting tool execution
    caps = INTEGRATION_CAPABILITIES.get(hub.type, {})
    if not caps.get("tool_execution"):
        raise HTTPException(
            status_code=400,
            detail=f"Integration type '{hub.type}' does not support tool execution. Check the 'capabilities' field in the integration listing.",
        )

    service = None
    try:
        service = _create_service_for_integration(hub, db)

        if not hasattr(service, "execute_tool"):
            raise HTTPException(status_code=400, detail=f"Integration type '{hub.type}' does not support tool execution")

        result = await service.execute_tool(
            tool_name=request.tool_name,
            arguments=request.arguments,
        )

        logger.info(f"API v1 executed tool '{request.tool_name}' on integration {integration_id} for tenant={caller.tenant_id}")

        return {
            "result": result,
            "integration_id": integration_id,
            "tool_name": request.tool_name,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Tool execution failed on integration {integration_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Tool execution failed. Check server logs for details.")
    finally:
        if service and hasattr(service, "close"):
            try:
                await service.close()
            except Exception:
                pass


@router.get("/api/v1/hub/providers", responses=COMMON_RESPONSES)
async def list_providers(
    caller: ApiCaller = Depends(require_api_permission("hub.read")),
):
    """
    List supported integration provider types.

    Returns metadata about each provider type that can be configured in the Hub,
    including whether it supports OAuth authentication.
    """
    providers = [
        {
            "type": "asana",
            "name": "Asana",
            "description": "Project and task management. Create, update, and track tasks and projects.",
            "supports_oauth": True,
            "capabilities": INTEGRATION_CAPABILITIES["asana"],
        },
        {
            "type": "gmail",
            "name": "Gmail",
            "description": "Email integration. Read, search, and draft emails. Tool execution available via agent skills only.",
            "supports_oauth": True,
            "capabilities": INTEGRATION_CAPABILITIES["gmail"],
        },
        {
            "type": "calendar",
            "name": "Google Calendar",
            "description": "Calendar management. List, create, and manage calendar events. Tool execution available via agent skills only.",
            "supports_oauth": True,
            "capabilities": INTEGRATION_CAPABILITIES["calendar"],
        },
        {
            "type": "google_flights",
            "name": "Google Flights",
            "description": "Flight search via SerpApi. Available as an agent skill only — not manageable through the Hub tool API.",
            "supports_oauth": False,
            "capabilities": INTEGRATION_CAPABILITIES["google_flights"],
        },
    ]

    return {"data": providers}
