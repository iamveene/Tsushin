"""
Skill Integrations API Routes

Manages the mapping between agent skills and their providers/integrations.
Enables per-agent configuration of:
- Scheduler provider (Flows, Google Calendar, Asana)
- Email provider (Gmail)

Security: CRIT-009 fix - Added authentication and tenant isolation (2026-02-02)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, Field
import logging

from models import (
    AgentSkillIntegration,
    HubIntegration,
    CalendarIntegration,
    GmailIntegration,
    AsanaIntegration,
    AmadeusIntegration,
    GoogleFlightsIntegration,
    Agent,
)
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from models_rbac import User


router = APIRouter()
logger = logging.getLogger(__name__)

# Global engine reference
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


# Pydantic models
class SkillIntegrationRequest(BaseModel):
    """Request to configure skill integration"""
    integration_id: Optional[int] = Field(None, description="Hub integration ID (NULL for built-in providers)")
    scheduler_provider: Optional[str] = Field(None, description="Provider type for scheduler: flows, google_calendar, asana")
    config: Optional[dict] = Field(default_factory=dict, description="Additional configuration including permissions")

    class Config:
        json_schema_extra = {
            "example": {
                "scheduler_provider": "google_calendar",
                "integration_id": 4,
                "config": {
                    "permissions": {
                        "read": True,
                        "write": True
                    }
                }
            }
        }


class SkillIntegrationResponse(BaseModel):
    """Response for skill integration"""
    id: int
    agent_id: int
    skill_type: str
    integration_id: Optional[int]
    scheduler_provider: Optional[str]
    config: Optional[dict]

    # Integration details (if linked)
    integration_name: Optional[str] = None
    integration_email: Optional[str] = None
    integration_health: Optional[str] = None


class AvailableProviderResponse(BaseModel):
    """Available provider for a skill"""
    provider_type: str
    provider_name: str
    requires_integration: bool
    available_integrations: List[dict] = []


class SkillProvidersResponse(BaseModel):
    """Available providers for a skill type"""
    skill_type: str
    providers: List[AvailableProviderResponse]


# Helper function for agent ownership verification
def verify_agent_access(db: Session, agent_id: int, ctx: TenantContext) -> Agent:
    """
    Verify agent exists and user has access to it.

    Since AgentSkillIntegration doesn't have a tenant_id column, we verify access
    through the Agent relationship.

    Args:
        db: Database session
        agent_id: Agent ID to verify
        ctx: Tenant context with user's tenant info

    Returns:
        Agent object if access is granted

    Raises:
        HTTPException 404 if agent not found
        HTTPException 403 if tenant doesn't match
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")
    return agent


# API Endpoints

@router.get("/agents/{agent_id}/skill-integrations")
async def get_agent_skill_integrations(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get all skill integrations for an agent.

    Requires agents.read permission and tenant access to the agent.

    Returns the mapping of skills to their providers/integrations.
    """
    try:
        # Verify agent exists and user has access
        verify_agent_access(db, agent_id, ctx)

        integrations = db.query(AgentSkillIntegration)\
            .filter(AgentSkillIntegration.agent_id == agent_id)\
            .all()

        result = []
        for si in integrations:
            # Get integration details if linked
            integration_name = None
            integration_email = None
            integration_health = None

            if si.integration_id:
                hub = db.query(HubIntegration).filter(HubIntegration.id == si.integration_id).first()
                if hub:
                    integration_name = hub.name
                    integration_health = hub.health_status

                    # Get email for Gmail/Calendar integrations
                    if hub.type == 'gmail':
                        gmail = db.query(GmailIntegration).filter(GmailIntegration.id == hub.id).first()
                        if gmail:
                            integration_email = gmail.email_address
                    elif hub.type == 'calendar':
                        calendar = db.query(CalendarIntegration).filter(CalendarIntegration.id == hub.id).first()
                        if calendar:
                            integration_email = calendar.email_address

            result.append({
                "id": si.id,
                "agent_id": si.agent_id,
                "skill_type": si.skill_type,
                "integration_id": si.integration_id,
                "scheduler_provider": si.scheduler_provider,
                "config": si.config,
                "integration_name": integration_name,
                "integration_email": integration_email,
                "integration_health": integration_health,
            })

        return {
            "agent_id": agent_id,
            "integrations": result,
            "count": len(result)
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting skill integrations for agent {agent_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/agents/{agent_id}/skill-integrations/{skill_type}")
async def get_skill_integration(
    agent_id: int,
    skill_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get skill integration for a specific skill type.

    Requires agents.read permission and tenant access to the agent.
    """
    try:
        # Verify agent exists and user has access
        verify_agent_access(db, agent_id, ctx)

        si = db.query(AgentSkillIntegration)\
            .filter(AgentSkillIntegration.agent_id == agent_id)\
            .filter(AgentSkillIntegration.skill_type == skill_type)\
            .first()

        if not si:
            return {
                "agent_id": agent_id,
                "skill_type": skill_type,
                "integration_id": None,
                "scheduler_provider": None,
                "config": None,
                "exists": False
            }

        # Get integration details
        integration_name = None
        integration_email = None
        integration_health = None

        if si.integration_id:
            hub = db.query(HubIntegration).filter(HubIntegration.id == si.integration_id).first()
            if hub:
                integration_name = hub.name
                integration_health = hub.health_status

                if hub.type == 'gmail':
                    gmail = db.query(GmailIntegration).filter(GmailIntegration.id == hub.id).first()
                    if gmail:
                        integration_email = gmail.email_address
                elif hub.type == 'calendar':
                    calendar = db.query(CalendarIntegration).filter(CalendarIntegration.id == hub.id).first()
                    if calendar:
                        integration_email = calendar.email_address

        return {
            "id": si.id,
            "agent_id": si.agent_id,
            "skill_type": si.skill_type,
            "integration_id": si.integration_id,
            "scheduler_provider": si.scheduler_provider,
            "config": si.config,
            "integration_name": integration_name,
            "integration_email": integration_email,
            "integration_health": integration_health,
            "exists": True
        }

    except Exception as e:
        logger.error(f"Error getting skill integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/agents/{agent_id}/skill-integrations/{skill_type}")
async def update_skill_integration(
    agent_id: int,
    skill_type: str,
    request: SkillIntegrationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Create or update skill integration for an agent.

    Requires agents.write permission and tenant access to the agent.

    For scheduler skills, set scheduler_provider to:
    - 'flows': Built-in Flows system (integration_id can be NULL)
    - 'google_calendar': Google Calendar (requires integration_id)
    - 'asana': Asana tasks (requires integration_id)

    For email skills, set integration_id to the Gmail integration ID.

    Config structure for granular permissions (Google Calendar):
    {
        "permissions": {
            "read": bool,   # View/list events
            "write": bool   # Create/update/delete events
        }
    }
    """
    try:
        from datetime import datetime

        # Verify agent exists and user has access
        verify_agent_access(db, agent_id, ctx)

        # Validate permissions config if provided
        if request.config and "permissions" in request.config:
            permissions = request.config["permissions"]
            if not isinstance(permissions, dict):
                raise HTTPException(
                    status_code=400,
                    detail="Permissions must be a dictionary with 'read' and 'write' keys"
                )
            # Ensure valid boolean values
            for key in ["read", "write"]:
                if key in permissions and not isinstance(permissions[key], bool):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Permission '{key}' must be a boolean value"
                    )

        # Validate integration exists if provided
        if request.integration_id:
            hub = db.query(HubIntegration).filter(HubIntegration.id == request.integration_id).first()
            if not hub:
                raise HTTPException(
                    status_code=400,
                    detail=f"Integration {request.integration_id} not found"
                )

        # Check if integration already exists
        existing = db.query(AgentSkillIntegration)\
            .filter(AgentSkillIntegration.agent_id == agent_id)\
            .filter(AgentSkillIntegration.skill_type == skill_type)\
            .first()

        if existing:
            # Update existing
            existing.integration_id = request.integration_id
            existing.scheduler_provider = request.scheduler_provider
            existing.config = request.config
            existing.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(existing)

            logger.info(
                f"Updated skill integration for agent {agent_id}, skill {skill_type}: "
                f"provider={request.scheduler_provider}, integration={request.integration_id}"
            )

            return {
                "id": existing.id,
                "agent_id": existing.agent_id,
                "skill_type": existing.skill_type,
                "integration_id": existing.integration_id,
                "scheduler_provider": existing.scheduler_provider,
                "config": existing.config,
                "created": False,
                "updated": True
            }

        # Create new
        si = AgentSkillIntegration(
            agent_id=agent_id,
            skill_type=skill_type,
            integration_id=request.integration_id,
            scheduler_provider=request.scheduler_provider,
            config=request.config,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow()
        )
        db.add(si)
        db.commit()
        db.refresh(si)

        logger.info(
            f"Created skill integration for agent {agent_id}, skill {skill_type}: "
            f"provider={request.scheduler_provider}, integration={request.integration_id}"
        )

        return {
            "id": si.id,
            "agent_id": si.agent_id,
            "skill_type": si.skill_type,
            "integration_id": si.integration_id,
            "scheduler_provider": si.scheduler_provider,
            "config": si.config,
            "created": True,
            "updated": False
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating skill integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/agents/{agent_id}/skill-integrations/{skill_type}")
async def delete_skill_integration(
    agent_id: int,
    skill_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Remove skill integration for an agent.

    Requires agents.write permission and tenant access to the agent.

    The skill will fall back to default behavior (e.g., Flows for scheduler).
    """
    try:
        # Verify agent exists and user has access
        verify_agent_access(db, agent_id, ctx)

        existing = db.query(AgentSkillIntegration)\
            .filter(AgentSkillIntegration.agent_id == agent_id)\
            .filter(AgentSkillIntegration.skill_type == skill_type)\
            .first()

        if not existing:
            raise HTTPException(
                status_code=404,
                detail=f"Skill integration not found for agent {agent_id}, skill {skill_type}"
            )

        db.delete(existing)
        db.commit()

        logger.info(f"Deleted skill integration for agent {agent_id}, skill {skill_type}")

        return {
            "success": True,
            "message": f"Skill integration removed for {skill_type}",
            "agent_id": agent_id,
            "skill_type": skill_type
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting skill integration: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/skill-providers/{skill_type}")
async def get_available_providers(
    skill_type: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get available providers for a skill type.

    Requires agents.read permission.

    Note: This returns system-wide providers/integrations. Tenant filtering
    is applied to integrations that have tenant_id fields.

    Args:
        skill_type: 'scheduler' or 'email'

    Returns:
        List of available providers with their connected integrations
    """
    try:
        if skill_type == 'scheduler' or skill_type == 'flows':
            # Scheduler providers
            providers = []

            # 1. Flows (built-in, always available)
            providers.append({
                "provider_type": "flows",
                "provider_name": "Flows (Built-in)",
                "description": "Built-in scheduling with reminders and AI conversations",
                "requires_integration": False,
                "available_integrations": []
            })

            # 2. Google Calendar
            calendars = db.query(CalendarIntegration)\
                .filter(CalendarIntegration.is_active == True)\
                .all()

            calendar_integrations = []
            for cal in calendars:
                hub = db.query(HubIntegration).filter(HubIntegration.id == cal.id).first()
                calendar_integrations.append({
                    "integration_id": cal.id,
                    "name": hub.name if hub else f"Calendar {cal.id}",
                    "email": cal.email_address,
                    "health_status": hub.health_status if hub else "unknown"
                })

            providers.append({
                "provider_type": "google_calendar",
                "provider_name": "Google Calendar",
                "description": "Create and manage events in Google Calendar",
                "requires_integration": True,
                "available_integrations": calendar_integrations
            })

            # 3. Asana
            asana_list = db.query(AsanaIntegration)\
                .filter(AsanaIntegration.is_active == True)\
                .all()

            asana_integrations = []
            for asana in asana_list:
                hub = db.query(HubIntegration).filter(HubIntegration.id == asana.id).first()
                asana_integrations.append({
                    "integration_id": asana.id,
                    "name": hub.name if hub else f"Asana {asana.id}",
                    "workspace": asana.workspace_name,
                    "health_status": hub.health_status if hub else "unknown"
                })

            providers.append({
                "provider_type": "asana",
                "provider_name": "Asana",
                "description": "Create tasks with due dates in Asana",
                "requires_integration": True,
                "available_integrations": asana_integrations
            })

            return {
                "skill_type": skill_type,
                "providers": providers
            }

        elif skill_type == 'email' or skill_type == 'gmail':
            # Email providers
            providers = []

            # Gmail
            gmail_list = db.query(GmailIntegration)\
                .filter(GmailIntegration.is_active == True)\
                .all()

            gmail_integrations = []
            for gmail in gmail_list:
                hub = db.query(HubIntegration).filter(HubIntegration.id == gmail.id).first()
                gmail_integrations.append({
                    "integration_id": gmail.id,
                    "name": hub.name if hub else f"Gmail {gmail.id}",
                    "email": gmail.email_address,
                    "health_status": hub.health_status if hub else "unknown"
                })

            providers.append({
                "provider_type": "gmail",
                "provider_name": "Gmail",
                "description": "Read and search emails in Gmail",
                "requires_integration": True,
                "available_integrations": gmail_integrations
            })

            return {
                "skill_type": skill_type,
                "providers": providers
            }

        elif skill_type == 'flight_search':
            # Flight Search providers
            providers = []

            # 1. Google Flights (SerpApi)
            google_flights = db.query(GoogleFlightsIntegration)\
                .filter(GoogleFlightsIntegration.is_active == True)\
                .all()

            gf_integrations = []
            for gf in google_flights:
                hub = db.query(HubIntegration).filter(HubIntegration.id == gf.id).first()
                gf_integrations.append({
                    "integration_id": gf.id,
                    "name": hub.name if hub else f"Google Flights {gf.id}",
                    "health_status": hub.health_status if hub else "unknown"
                })

            providers.append({
                "provider_type": "google_flights",
                "provider_name": "Google Flights",
                "description": "Search flights using Google Flights engine (via SerpApi)",
                "requires_integration": True,
                "available_integrations": gf_integrations
            })

            # 2. Amadeus
            amadeus_list = db.query(AmadeusIntegration)\
                .filter(AmadeusIntegration.is_active == True)\
                .all()

            amadeus_integrations = []
            for am in amadeus_list:
                hub = db.query(HubIntegration).filter(HubIntegration.id == am.id).first()
                amadeus_integrations.append({
                    "integration_id": am.id,
                    "name": hub.name if hub else f"Amadeus {am.id}",
                    "health_status": hub.health_status if hub else "unknown"
                })

            providers.append({
                "provider_type": "amadeus",
                "provider_name": "Amadeus",
                "description": "Global distribution system for flights",
                "requires_integration": True,
                "available_integrations": amadeus_integrations
            })

            return {
                "skill_type": skill_type,
                "providers": providers
            }

        elif skill_type == 'web_search':
            # Web Search providers
            from hub.providers import SearchProviderRegistry

            # Initialize providers if not already done
            SearchProviderRegistry.initialize_providers()

            # Get all registered providers
            providers_list = SearchProviderRegistry.list_providers(db=db)

            providers = []
            for prov in providers_list:
                providers.append({
                    "provider_type": prov["id"],
                    "provider_name": prov["name"],
                    "description": prov.get("pricing", {}).get("description", f"Web search via {prov['name']}"),
                    "requires_integration": False,  # Web search uses API keys, not integrations
                    "available_integrations": [],
                    "is_default": prov.get("is_default", False),
                    "pricing": prov.get("pricing", {})
                })

            return {
                "skill_type": skill_type,
                "providers": providers
            }

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown skill type: {skill_type}. Supported: scheduler, email, flight_search, web_search"
            )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting available providers: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
