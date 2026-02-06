"""
Flight Providers API Routes
Endpoints for managing flight search providers and agent configuration.

Security: HIGH-008 fix - All endpoints require authentication (2026-02-02)
- Provider listing requires hub.read permission
- Agent config read requires agents.read permission
- Agent config update and Amadeus management require hub.write permission
- Tenant isolation enforced for agent-based endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Optional
from pydantic import BaseModel
import logging
import os

from db import get_db
from models import Agent, HubIntegration, AmadeusIntegration
from models_rbac import User
from auth_dependencies import require_permission, get_tenant_context, TenantContext
from hub.providers import FlightProviderRegistry
from hub.security import TokenEncryption
from services.encryption_key_service import get_amadeus_encryption_key


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/flight-providers", tags=["flight_providers"])


def verify_agent_access(agent_id: int, ctx: TenantContext, db: Session) -> Agent:
    """
    Verify that the current user has access to the specified agent.

    Args:
        agent_id: ID of the agent to access
        ctx: Tenant context from authentication
        db: Database session

    Returns:
        Agent object if access is granted

    Raises:
        HTTPException: If agent not found or access denied
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found"
        )

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this agent"
        )

    return agent


# Pydantic models
class ProviderInfo(BaseModel):
    """Provider information response"""
    id: str
    name: str
    class_name: str
    supported: bool
    configured: bool = False
    health_status: Optional[str] = None


class AgentFlightProviderResponse(BaseModel):
    """Agent's flight provider configuration"""
    provider: Optional[str] = None
    settings: Dict = {}


class AgentFlightProviderUpdate(BaseModel):
    """Update agent's flight provider"""
    provider: str
    settings: Optional[Dict] = {}


class AmadeusConfigCreate(BaseModel):
    """Create Amadeus integration configuration"""
    name: str
    api_key: str
    api_secret: str
    environment: str = "test"  # "test" or "production"
    default_currency: str = "BRL"
    max_results: int = 5
    # Note: tenant_id is derived from authenticated user, not from request


@router.get("", response_model=List[ProviderInfo])
def list_flight_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read"))
):
    """
    List all available flight search providers.

    Returns provider information including configuration status.

    Requires: hub.read permission
    """
    try:
        providers = FlightProviderRegistry.list_available_providers(db)

        return [
            ProviderInfo(
                id=p["id"],
                name=p["name"],
                class_name=p["class"],
                supported=p["supported"],
                configured=p.get("configured", False),
                health_status=p.get("health_status")
            )
            for p in providers
        ]
    except Exception as e:
        logger.error(f"Failed to list providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list providers: {str(e)}"
        )


@router.get("/agents/{agent_id}/provider", response_model=AgentFlightProviderResponse)
def get_agent_flight_provider(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get current flight provider configuration for an agent.

    Returns the selected provider and settings from agent.config JSON.

    Requires: agents.read permission
    """
    agent = verify_agent_access(agent_id, ctx, db)

    config = agent.config or {}
    skills = config.get("skills", {})
    flight_search = skills.get("flight_search", {})

    return AgentFlightProviderResponse(
        provider=flight_search.get("provider"),
        settings=flight_search.get("settings", {})
    )


@router.put("/agents/{agent_id}/provider")
def update_agent_flight_provider(
    agent_id: int,
    update: AgentFlightProviderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Update agent's flight search provider configuration.

    Sets which provider the agent should use for flight searches.

    Requires: agents.write permission
    """
    agent = verify_agent_access(agent_id, ctx, db)

    # Validate provider exists
    if not FlightProviderRegistry.is_provider_registered(update.provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{update.provider}' is not registered"
        )

    # Check if provider is configured
    integration = db.query(HubIntegration).filter(
        HubIntegration.type == update.provider,
        HubIntegration.is_active == True
    ).first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{update.provider}' is not configured. Please configure it first."
        )

    # Update agent config
    config = agent.config or {}
    if "skills" not in config:
        config["skills"] = {}

    config["skills"]["flight_search"] = {
        "enabled": True,
        "provider": update.provider,
        "settings": update.settings or {
            "default_currency": "BRL",
            "max_results": 5,
            "prefer_direct_flights": False
        }
    }

    agent.config = config
    db.commit()

    logger.info(f"Agent {agent_id} flight provider updated to '{update.provider}' by user {current_user.id}")

    return {
        "success": True,
        "message": f"Flight provider updated to '{update.provider}'",
        "provider": update.provider,
        "settings": config["skills"]["flight_search"]["settings"]
    }


@router.post("/amadeus/configure")
def configure_amadeus(
    config: AmadeusConfigCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Configure Amadeus flight search integration.

    Creates or updates the Amadeus integration with API credentials.

    Requires: hub.write permission
    """
    try:
        # Get Amadeus-specific encryption key from database (MED-001 security fix)
        encryption_key = get_amadeus_encryption_key(db)
        if not encryption_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="AMADEUS_ENCRYPTION_KEY not configured in database or environment"
            )

        # Check if integration already exists for this tenant
        existing = db.query(AmadeusIntegration).filter(
            AmadeusIntegration.type == "amadeus",
            AmadeusIntegration.tenant_id == ctx.tenant_id
        ).first()

        if existing:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Amadeus integration already configured. Use update endpoint."
            )

        # Encrypt API secret
        token_encryption = TokenEncryption(encryption_key.encode())
        encrypted_secret = token_encryption.encrypt(
            config.api_secret,
            f"amadeus_new"  # Temporary key, will be updated with integration ID
        )

        # Create integration with tenant from authenticated user
        integration = AmadeusIntegration(
            type="amadeus",
            name=config.name,
            is_active=True,
            tenant_id=ctx.tenant_id,  # Use authenticated user's tenant
            environment=config.environment,
            api_key=config.api_key,
            api_secret_encrypted=encrypted_secret,
            default_currency=config.default_currency,
            max_results=config.max_results,
            health_status="unknown"
        )

        db.add(integration)
        db.commit()
        db.refresh(integration)

        # Re-encrypt with proper key using integration ID
        encrypted_secret = token_encryption.encrypt(
            config.api_secret,
            f"amadeus_{integration.id}"
        )
        integration.api_secret_encrypted = encrypted_secret
        db.commit()

        logger.info(f"Amadeus integration configured: {integration.id} by user {current_user.id}")

        return {
            "success": True,
            "message": "Amadeus integration configured successfully",
            "integration_id": integration.id,
            "environment": integration.environment
        }

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to configure Amadeus: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to configure Amadeus: {str(e)}"
        )


@router.get("/amadeus/status")
def get_amadeus_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get Amadeus integration status.

    Returns configuration and health information.

    Requires: hub.read permission
    """
    # Filter by tenant for non-global-admin users
    query = db.query(AmadeusIntegration).filter(
        AmadeusIntegration.type == "amadeus",
        AmadeusIntegration.is_active == True
    )

    if not ctx.is_global_admin:
        query = query.filter(AmadeusIntegration.tenant_id == ctx.tenant_id)

    integration = query.first()

    if not integration:
        return {
            "configured": False,
            "message": "Amadeus integration not configured"
        }

    return {
        "configured": True,
        "integration_id": integration.id,
        "name": integration.name,
        "environment": integration.environment,
        "health_status": integration.health_status,
        "last_health_check": integration.last_health_check.isoformat() if integration.last_health_check else None,
        "default_currency": integration.default_currency,
        "max_results": integration.max_results,
        "rate_limit": f"{integration.requests_last_minute}/150 per minute"
    }


@router.post("/amadeus/test")
async def test_amadeus_connection(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Test Amadeus API connectivity.

    Validates credentials and performs a health check.

    Requires: hub.write permission
    """
    # Filter by tenant for non-global-admin users
    query = db.query(AmadeusIntegration).filter(
        AmadeusIntegration.type == "amadeus",
        AmadeusIntegration.is_active == True
    )

    if not ctx.is_global_admin:
        query = query.filter(AmadeusIntegration.tenant_id == ctx.tenant_id)

    integration = query.first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Amadeus integration not configured"
        )

    try:
        # Initialize service and test connection
        from hub.amadeus.amadeus_service import AmadeusService

        service = AmadeusService(integration, db)
        health = await service.health_check()

        # Update health status
        integration.health_status = health["status"]
        from datetime import datetime
        integration.last_health_check = datetime.utcnow()
        db.commit()

        return health

    except Exception as e:
        logger.error(f"Amadeus connection test failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Connection test failed: {str(e)}"
        )


@router.delete("/amadeus")
def delete_amadeus_integration(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.delete")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Delete Amadeus integration configuration.

    Removes the integration and all associated data.

    Requires: hub.delete permission
    """
    # Filter by tenant for non-global-admin users
    query = db.query(AmadeusIntegration).filter(
        AmadeusIntegration.type == "amadeus"
    )

    if not ctx.is_global_admin:
        query = query.filter(AmadeusIntegration.tenant_id == ctx.tenant_id)

    integration = query.first()

    if not integration:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Amadeus integration not found"
        )

    try:
        integration_id = integration.id
        db.delete(integration)
        db.commit()

        logger.info(f"Amadeus integration deleted: {integration_id} by user {current_user.id}")

        return {
            "success": True,
            "message": "Amadeus integration deleted successfully"
        }

    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete Amadeus integration: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete integration: {str(e)}"
        )
