"""
Protected Agent Management API Routes - Phase 7.6.4
RBAC-protected endpoints with tenant isolation

Includes:
- Agent CRUD operations
- Agent skill-integration assignment endpoints (Phase 9)
- Graph View batch endpoints (Phase 6 - Graph View Performance)
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from db import get_db
from models import (
    Agent, AgentSkillIntegration, HubIntegration, GmailIntegration,
    CalendarIntegration, AsanaIntegration, AgentSkill, AgentKnowledge,
    Contact, WhatsAppMCPInstance, TelegramBotInstance, SentinelAgentConfig
)
from models_rbac import User
from auth_dependencies import (
    get_current_user_required,
    get_tenant_context,
    require_permission,
    TenantContext
)

router = APIRouter(prefix="/api/v2/agents", tags=["agents-protected"])


@router.get("/", dependencies=[Depends(require_permission("agents.read"))])
async def list_agents_protected(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    List all agents (with tenant isolation and permission check)

    - Requires: agents.read permission
    - Returns: Only agents from user's tenant (or all for global admin)
    """
    # Build query
    query = ctx.db.query(Agent).filter(Agent.is_active == True)

    # Apply tenant isolation
    query = ctx.filter_by_tenant(query, Agent.tenant_id)

    agents = query.all()

    return {
        "agents": [
            {
                "id": agent.id,
                "contact_name": agent.contact.friendly_name if agent.contact else "Unknown",
                "keywords": agent.keywords,
                "is_active": agent.is_active,
                "tenant_id": agent.tenant_id,
                "user_id": agent.user_id,
            }
            for agent in agents
        ],
        "count": len(agents),
        "tenant_id": ctx.tenant_id,
        "is_global_admin": ctx.is_global_admin
    }


# =============================================================================
# Graph View Batch Endpoints (Phase 6)
# IMPORTANT: These must be defined BEFORE /{agent_id} routes to avoid path conflicts
# =============================================================================

# Skill metadata for enriched skill display in Graph View
SKILL_METADATA = {
    "web_search": {"category": "search", "name": "Web Search", "description": "Search the web for information"},
    "weather": {"category": "integration", "name": "Weather", "description": "Get weather forecasts"},
    "web_scraping": {"category": "search", "name": "Web Scraping", "description": "Scrape content from websites"},
    "audio_transcript": {"category": "audio", "name": "Audio Transcript", "description": "Transcribe audio to text"},
    "audio_tts": {"category": "audio", "name": "Text to Speech", "description": "Convert text to speech"},
    # Gmail/Email - standalone skill category so it shows at Agent level, not under Integrations
    "gmail": {"category": "email", "name": "Email", "description": "Read and send emails"},
    "email": {"category": "email", "name": "Email", "description": "Read and send emails"},
    "calendar": {"category": "integration", "name": "Calendar", "description": "Manage calendar events"},
    "asana": {"category": "integration", "name": "Asana", "description": "Manage Asana tasks"},
    # Flows - will be dynamically renamed to "Scheduler" if it has a calendar/asana provider
    "flows": {"category": "automation", "name": "Flows", "description": "Execute automation flows"},
    "scheduler": {"category": "scheduler", "name": "Scheduler", "description": "Schedule events and reminders"},
    "browser_automation": {"category": "automation", "name": "Browser Automation", "description": "Control web browsers"},
    "shell": {"category": "automation", "name": "Shell", "description": "Execute shell commands"},
    "sandboxed_tools": {"category": "automation", "name": "Sandboxed Tools", "description": "Execute tools in sandboxed environment"},
    "image": {"category": "media", "name": "Image Generation", "description": "Generate and edit images"},
    # Flight Search - standalone skill category so it shows at Agent level
    "flight_search": {"category": "flight_search", "name": "Flight Search", "description": "Search for flights"},
    "adaptive_personality": {"category": "special", "name": "Adaptive Personality", "description": "Dynamic tone adaptation"},
    "knowledge_sharing": {"category": "special", "name": "Knowledge Sharing", "description": "Share knowledge across agents"},
    "agent_switcher": {"category": "special", "name": "Agent Switcher", "description": "Switch between agents in DM"},
    # Note: "automation" skill type is intentionally EXCLUDED - it's an internal skill that shouldn't show in Graph View
}


class AgentGraphPreviewItem(BaseModel):
    """Agent data optimized for Graph View"""
    id: int
    contact_name: str
    is_active: bool
    is_default: bool
    model_provider: str
    model_name: str
    memory_isolation_mode: str
    enabled_channels: List[str]
    whatsapp_integration_id: Optional[int]
    telegram_integration_id: Optional[int]
    skills_count: int
    knowledge_doc_count: int
    knowledge_chunk_count: int
    sentinel_enabled: bool
    avatar: Optional[str] = None


class WhatsAppChannelInfo(BaseModel):
    """WhatsApp channel info for Graph View"""
    id: int
    phone_number: Optional[str]
    status: str
    health_status: str


class TelegramChannelInfo(BaseModel):
    """Telegram channel info for Graph View"""
    id: int
    bot_username: str
    status: str
    health_status: str


class GraphPreviewResponse(BaseModel):
    """Response for /api/agents/graph-preview endpoint"""
    agents: List[AgentGraphPreviewItem]
    channels: Dict[str, Any]


@router.get("/graph-preview", dependencies=[Depends(require_permission("agents.read"))])
async def get_agents_graph_preview(
    ctx: TenantContext = Depends(get_tenant_context),
) -> GraphPreviewResponse:
    """
    Get optimized agent data for Graph View.

    This batch endpoint replaces multiple individual API calls:
    - GET /agents (for agent list)
    - GET /mcp-instances (for WhatsApp channels)
    - GET /telegram-instances (for Telegram channels)
    - GET /sentinel/agents/{id}/config (N calls for Sentinel status)
    - GET /agents/{id}/knowledge-base (N calls for KB counts)

    Returns all data needed for Graph View in a single request.
    """
    import json

    # Query agents with aggregated skills and knowledge counts
    # Using subqueries for efficiency
    skills_subq = (
        ctx.db.query(
            AgentSkill.agent_id,
            func.count(AgentSkill.id).label('skills_count')
        )
        .filter(AgentSkill.is_enabled == True)
        .group_by(AgentSkill.agent_id)
        .subquery()
    )

    knowledge_subq = (
        ctx.db.query(
            AgentKnowledge.agent_id,
            func.count(AgentKnowledge.id).label('doc_count'),
            func.coalesce(func.sum(AgentKnowledge.num_chunks), 0).label('chunk_count')
        )
        .group_by(AgentKnowledge.agent_id)
        .subquery()
    )

    sentinel_subq = (
        ctx.db.query(
            SentinelAgentConfig.agent_id,
            SentinelAgentConfig.is_enabled.label('sentinel_enabled')
        )
        .subquery()
    )

    # Main agent query with all joins
    query = (
        ctx.db.query(
            Agent,
            Contact.friendly_name.label('contact_name'),
            func.coalesce(skills_subq.c.skills_count, 0).label('skills_count'),
            func.coalesce(knowledge_subq.c.doc_count, 0).label('knowledge_doc_count'),
            func.coalesce(knowledge_subq.c.chunk_count, 0).label('knowledge_chunk_count'),
            func.coalesce(sentinel_subq.c.sentinel_enabled, False).label('sentinel_enabled')
        )
        .join(Contact, Agent.contact_id == Contact.id)
        .outerjoin(skills_subq, Agent.id == skills_subq.c.agent_id)
        .outerjoin(knowledge_subq, Agent.id == knowledge_subq.c.agent_id)
        .outerjoin(sentinel_subq, Agent.id == sentinel_subq.c.agent_id)
    )

    # Apply tenant isolation
    query = ctx.filter_by_tenant(query, Agent.tenant_id)

    results = query.all()

    # Transform to response format
    agents = []
    for row in results:
        agent = row[0]  # Agent object
        contact_name = row[1]
        skills_count = row[2]
        knowledge_doc_count = row[3]
        knowledge_chunk_count = row[4]
        sentinel_enabled = row[5]

        # Parse enabled_channels (may be JSON string or list)
        if isinstance(agent.enabled_channels, list):
            enabled_channels = agent.enabled_channels
        elif isinstance(agent.enabled_channels, str) and agent.enabled_channels:
            try:
                enabled_channels = json.loads(agent.enabled_channels)
            except (json.JSONDecodeError, TypeError):
                enabled_channels = ["playground", "whatsapp"]
        else:
            enabled_channels = ["playground", "whatsapp"]

        agents.append(AgentGraphPreviewItem(
            id=agent.id,
            contact_name=contact_name or "Unknown",
            is_active=agent.is_active,
            is_default=agent.is_default or False,
            model_provider=agent.model_provider or "gemini",
            model_name=agent.model_name or "gemini-2.5-pro",
            memory_isolation_mode=agent.memory_isolation_mode or "isolated",
            enabled_channels=enabled_channels,
            whatsapp_integration_id=agent.whatsapp_integration_id,
            telegram_integration_id=agent.telegram_integration_id,
            skills_count=skills_count,
            knowledge_doc_count=knowledge_doc_count,
            knowledge_chunk_count=knowledge_chunk_count,
            sentinel_enabled=bool(sentinel_enabled),
            avatar=agent.avatar,
        ))

    # Fetch channel instances (excluding test/internal instances)
    whatsapp_query = ctx.db.query(WhatsAppMCPInstance)
    whatsapp_query = ctx.filter_by_tenant(whatsapp_query, WhatsAppMCPInstance.tenant_id)
    # Filter out tester instances (only show agent instances in Graph View)
    whatsapp_query = whatsapp_query.filter(
        WhatsAppMCPInstance.instance_type != "tester"
    )
    whatsapp_instances = whatsapp_query.all()

    telegram_query = ctx.db.query(TelegramBotInstance)
    telegram_query = ctx.filter_by_tenant(telegram_query, TelegramBotInstance.tenant_id)
    telegram_instances = telegram_query.all()

    channels = {
        "whatsapp": [
            WhatsAppChannelInfo(
                id=inst.id,
                phone_number=inst.phone_number,
                status=inst.status or "stopped",
                health_status=inst.health_status or "unknown"
            ).model_dump()
            for inst in whatsapp_instances
        ],
        "telegram": [
            TelegramChannelInfo(
                id=inst.id,
                bot_username=inst.bot_username,
                status=inst.status or "inactive",
                health_status=inst.health_status or "unknown"
            ).model_dump()
            for inst in telegram_instances
        ]
    }

    return GraphPreviewResponse(agents=agents, channels=channels)


# =============================================================================
# Individual Agent Endpoints (with {agent_id} path parameter)
# =============================================================================

@router.get("/{agent_id}", dependencies=[Depends(require_permission("agents.read"))])
async def get_agent_protected(
    agent_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Get specific agent (with tenant isolation)

    - Requires: agents.read permission
    - Returns: Agent details if user has access, 404 otherwise
    """
    agent = ctx.db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check tenant access
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this agent"
        )

    return {
        "id": agent.id,
        "contact_name": agent.contact.friendly_name if agent.contact else "Unknown",
        "system_prompt": agent.system_prompt,
        "keywords": agent.keywords,
        "tenant_id": agent.tenant_id,
        "user_id": agent.user_id,
    }


@router.post("/", dependencies=[Depends(require_permission("agents.write"))])
async def create_agent_protected(
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Create new agent (with automatic tenant assignment)

    - Requires: agents.write permission
    - Automatically sets tenant_id and user_id from context
    """
    # In real implementation, would accept agent data from request body
    # For now, just demonstrate the pattern

    return {
        "message": "Agent creation protected by RBAC",
        "tenant_id": ctx.tenant_id,
        "user_id": ctx.user.id,
        "permissions_checked": "agents.write"
    }


@router.delete("/{agent_id}", dependencies=[Depends(require_permission("agents.delete"))])
async def delete_agent_protected(
    agent_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Delete agent (with tenant isolation and permission check)

    - Requires: agents.delete permission
    - Only allows deleting agents from user's tenant
    """
    agent = ctx.db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Check tenant access
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(
            status_code=403,
            detail="You don't have access to this agent"
        )

    # In real implementation, would delete the agent
    # For now, just demonstrate the pattern

    return {
        "message": f"Agent {agent_id} deletion protected by RBAC",
        "agent_tenant": agent.tenant_id,
        "user_tenant": ctx.tenant_id,
        "can_delete": True
    }


# ============================================
# Agent Skill-Integration Assignment (Phase 9)
# ============================================

class SkillIntegrationRequest(BaseModel):
    """Request body for skill-integration assignment."""
    integration_id: Optional[int] = None
    scheduler_provider: Optional[str] = None  # 'flows', 'google_calendar', 'asana'
    config: Optional[Dict[str, Any]] = None


class SkillIntegrationResponse(BaseModel):
    """Response for skill-integration assignment."""
    skill_type: str
    integration_id: Optional[int]
    integration_name: Optional[str]
    integration_email: Optional[str]
    scheduler_provider: Optional[str]
    config: Optional[Dict[str, Any]]


@router.get("/{agent_id}/skill-integrations", dependencies=[Depends(require_permission("agents.read"))])
async def get_agent_skill_integrations(
    agent_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Get agent's skill-integration configurations.

    Returns which integrations each skill uses for this agent.
    """
    agent = ctx.db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get all skill integrations for this agent
    skill_configs = ctx.db.query(AgentSkillIntegration).filter(
        AgentSkillIntegration.agent_id == agent_id
    ).all()

    result = {}
    for config in skill_configs:
        # Get integration details
        integration_name = None
        integration_email = None

        if config.integration_id:
            integration = ctx.db.query(HubIntegration).filter(
                HubIntegration.id == config.integration_id
            ).first()

            if integration:
                integration_name = integration.display_name or integration.name

                # Get email for Gmail/Calendar integrations
                if integration.type == 'gmail':
                    gmail = ctx.db.query(GmailIntegration).filter(
                        GmailIntegration.id == integration.id
                    ).first()
                    integration_email = gmail.email_address if gmail else None
                elif integration.type == 'calendar':
                    calendar = ctx.db.query(CalendarIntegration).filter(
                        CalendarIntegration.id == integration.id
                    ).first()
                    integration_email = calendar.email_address if calendar else None

        result[config.skill_type] = SkillIntegrationResponse(
            skill_type=config.skill_type,
            integration_id=config.integration_id,
            integration_name=integration_name,
            integration_email=integration_email,
            scheduler_provider=config.scheduler_provider,
            config=config.config
        )

    return result


@router.put("/{agent_id}/skill-integrations/{skill_type}", dependencies=[Depends(require_permission("agents.write"))])
async def set_agent_skill_integration(
    agent_id: int,
    skill_type: str,
    data: SkillIntegrationRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Set which integration a skill uses for this agent.

    For gmail skill: specify integration_id of a Gmail integration
    For flows skill: specify scheduler_provider and optionally integration_id
    """
    agent = ctx.db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Validate integration_id if provided
    if data.integration_id:
        integration = ctx.db.query(HubIntegration).filter(
            HubIntegration.id == data.integration_id
        ).first()

        if not integration:
            raise HTTPException(status_code=404, detail="Integration not found")

        if not ctx.can_access_resource(integration.tenant_id):
            raise HTTPException(status_code=403, detail="Integration access denied")

    # Validate scheduler_provider
    valid_providers = ['flows', 'google_calendar', 'asana']
    if data.scheduler_provider and data.scheduler_provider not in valid_providers:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid scheduler_provider. Must be one of: {valid_providers}"
        )

    # Get or create skill integration config
    existing = ctx.db.query(AgentSkillIntegration).filter(
        AgentSkillIntegration.agent_id == agent_id,
        AgentSkillIntegration.skill_type == skill_type
    ).first()

    if existing:
        # Update
        existing.integration_id = data.integration_id
        existing.scheduler_provider = data.scheduler_provider
        if data.config:
            existing.config = data.config
        existing.updated_at = datetime.utcnow()
    else:
        # Create
        new_config = AgentSkillIntegration(
            agent_id=agent_id,
            skill_type=skill_type,
            integration_id=data.integration_id,
            scheduler_provider=data.scheduler_provider,
            config=data.config
        )
        ctx.db.add(new_config)

    ctx.db.commit()

    return {"status": "updated", "agent_id": agent_id, "skill_type": skill_type}


@router.delete("/{agent_id}/skill-integrations/{skill_type}", dependencies=[Depends(require_permission("agents.write"))])
async def delete_agent_skill_integration(
    agent_id: int,
    skill_type: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Remove skill-integration configuration for an agent.

    Skill will revert to default behavior (e.g., Flows for scheduler).
    """
    agent = ctx.db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Delete config
    deleted = ctx.db.query(AgentSkillIntegration).filter(
        AgentSkillIntegration.agent_id == agent_id,
        AgentSkillIntegration.skill_type == skill_type
    ).delete()

    ctx.db.commit()

    if deleted:
        return {"status": "deleted", "agent_id": agent_id, "skill_type": skill_type}
    else:
        return {"status": "not_found", "agent_id": agent_id, "skill_type": skill_type}


@router.get("/{agent_id}/available-integrations/{skill_type}", dependencies=[Depends(require_permission("agents.read"))])
async def get_available_integrations_for_skill(
    agent_id: int,
    skill_type: str,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Get available integrations for a skill type.

    For gmail: returns all Gmail integrations in tenant
    For flows: returns providers and their available integrations
    """
    agent = ctx.db.query(Agent).filter(Agent.id == agent_id).first()

    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    if skill_type == 'gmail':
        # Return Gmail integrations
        integrations = ctx.db.query(GmailIntegration).join(HubIntegration).filter(
            HubIntegration.tenant_id == ctx.tenant_id,
            HubIntegration.is_active == True
        ).all()

        return {
            "skill_type": "gmail",
            "integrations": [
                {
                    "id": i.id,
                    "name": ctx.db.query(HubIntegration).filter(HubIntegration.id == i.id).first().display_name or f"Gmail - {i.email_address}",
                    "email": i.email_address
                }
                for i in integrations
            ]
        }

    elif skill_type == 'flows':
        # Return providers and their integrations
        providers = [
            {
                "type": "flows",
                "name": "Built-in Flows",
                "description": "Internal reminders and conversations",
                "requires_integration": False,
                "integrations": []
            }
        ]

        # Calendar integrations
        calendar_integrations = ctx.db.query(CalendarIntegration).join(HubIntegration).filter(
            HubIntegration.tenant_id == ctx.tenant_id,
            HubIntegration.is_active == True
        ).all()

        providers.append({
            "type": "google_calendar",
            "name": "Google Calendar",
            "description": "Calendar events and meetings",
            "requires_integration": True,
            "integrations": [
                {
                    "id": i.id,
                    "name": ctx.db.query(HubIntegration).filter(HubIntegration.id == i.id).first().display_name or f"Calendar - {i.email_address}",
                    "email": i.email_address
                }
                for i in calendar_integrations
            ]
        })

        # Asana integrations
        asana_integrations = ctx.db.query(AsanaIntegration).join(HubIntegration).filter(
            HubIntegration.tenant_id == ctx.tenant_id,
            HubIntegration.is_active == True
        ).all()

        providers.append({
            "type": "asana",
            "name": "Asana Tasks",
            "description": "Tasks with due dates",
            "requires_integration": True,
            "integrations": [
                {
                    "id": i.id,
                    "name": ctx.db.query(HubIntegration).filter(HubIntegration.id == i.id).first().display_name or f"Asana - {i.workspace_name}",
                    "workspace": i.workspace_name
                }
                for i in asana_integrations
            ]
        })

        return {
            "skill_type": "flows",
            "providers": providers
        }

    else:
        raise HTTPException(status_code=400, detail=f"Unknown skill type: {skill_type}")


# ============================================
# Agent Expand Data Endpoint (Phase 6)
# ============================================

class SkillExpandInfo(BaseModel):
    """Skill info for expand view"""
    id: int
    skill_type: str
    skill_name: str
    skill_description: str
    category: str
    is_enabled: bool
    provider_name: Optional[str] = None
    provider_type: Optional[str] = None  # e.g., "gmail", "google_calendar", "brave"
    integration_id: Optional[int] = None  # The configured integration ID
    config: Optional[Dict[str, Any]] = None


class KnowledgeSummary(BaseModel):
    """Knowledge base summary for expand view"""
    total_documents: int
    total_chunks: int
    total_size_bytes: int
    document_types: Dict[str, int]
    status_counts: Dict[str, int]
    all_completed: bool


class AgentExpandDataResponse(BaseModel):
    """Response for /api/agents/{agent_id}/expand-data endpoint"""
    agent_id: int
    skills: List[SkillExpandInfo]
    knowledge_summary: KnowledgeSummary


@router.get("/{agent_id}/expand-data", dependencies=[Depends(require_permission("agents.read"))])
async def get_agent_expand_data(
    agent_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
) -> AgentExpandDataResponse:
    """
    Get detailed skill and knowledge data for agent expansion.

    This batch endpoint replaces:
    - GET /agents/{id}/skills
    - GET /agents/{id}/knowledge-base

    Returns enriched skill data with categories and provider info,
    plus aggregated knowledge base summary.
    """
    # Verify agent exists and belongs to tenant
    agent = ctx.db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Skills to exclude from Graph View (internal/system skills)
    EXCLUDED_SKILL_TYPES = {"automation"}  # Multi-Step Automation is internal

    # Fetch skills with metadata enrichment
    skills_db = ctx.db.query(AgentSkill).filter(
        AgentSkill.agent_id == agent_id,
        AgentSkill.is_enabled == True,
        AgentSkill.skill_type.notin_(EXCLUDED_SKILL_TYPES)  # Exclude internal skills
    ).all()

    # Fetch all skill integrations for this agent in one query
    skill_integrations = ctx.db.query(AgentSkillIntegration).filter(
        AgentSkillIntegration.agent_id == agent_id
    ).all()

    # Create lookup map for skill integrations
    skill_integration_map = {si.skill_type: si for si in skill_integrations}

    skills = []
    for skill in skills_db:
        # Determine the effective skill type (may be transformed)
        effective_skill_type = skill.skill_type

        # Check skill integration configuration first to determine transformations
        skill_integration = skill_integration_map.get(skill.skill_type)
        scheduler_provider = None
        if skill_integration:
            scheduler_provider = skill_integration.scheduler_provider

        # Transform "flows" to "scheduler" if it has a calendar/asana provider
        # This shows the skill as "Scheduler" with the calendar/asana as its provider
        if skill.skill_type == "flows" and scheduler_provider in ("google_calendar", "asana"):
            effective_skill_type = "scheduler"

        # Get metadata from mapping using the effective skill type
        metadata = SKILL_METADATA.get(effective_skill_type, {
            "category": "other",
            "name": effective_skill_type.replace("_", " ").title(),
            "description": f"Agent skill: {effective_skill_type}"
        })

        # Get provider info from AgentSkillIntegration
        provider_name = None
        provider_type = None
        integration_id = None

        # Check skill integration configuration
        if skill_integration:
            integration_id = skill_integration.integration_id

            # For scheduler-type skills (flows), get provider type
            if scheduler_provider:
                provider_type = scheduler_provider
                provider_name = {
                    "flows": "Flows (Built-in)",
                    "google_calendar": "Google Calendar",
                    "asana": "Asana"
                }.get(provider_type, provider_type.replace("_", " ").title())

            # For integration-linked skills, get integration details
            if integration_id:
                hub = ctx.db.query(HubIntegration).filter(
                    HubIntegration.id == integration_id
                ).first()
                if hub:
                    provider_type = hub.type  # "gmail", "calendar", "google_flights", etc.
                    # Get more specific name with email if available
                    if hub.type == 'gmail':
                        gmail = ctx.db.query(GmailIntegration).filter(
                            GmailIntegration.id == integration_id
                        ).first()
                        if gmail and gmail.email_address:
                            provider_name = f"Gmail ({gmail.email_address})"
                        else:
                            provider_name = hub.name or "Gmail"
                    elif hub.type == 'calendar':
                        calendar = ctx.db.query(CalendarIntegration).filter(
                            CalendarIntegration.id == integration_id
                        ).first()
                        if calendar and calendar.email_address:
                            provider_name = f"Google Calendar ({calendar.email_address})"
                        else:
                            provider_name = hub.name or "Google Calendar"
                    elif hub.type == 'google_flights':
                        provider_name = hub.name or "Google Flights"
                    elif hub.type == 'amadeus':
                        provider_name = hub.name or "Amadeus"
                    else:
                        provider_name = hub.name or hub.type.replace("_", " ").title()

        # Fallback: Try to extract from skill config
        if not provider_name and skill.config:
            config_provider = (
                skill.config.get("provider") or
                skill.config.get("provider_name") or
                skill.config.get("search_provider") or
                skill.config.get("tts_provider") or
                skill.config.get("image_provider")
            )
            if config_provider:
                provider_type = config_provider.lower().replace(" ", "_")
                provider_name = config_provider.replace("_", " ").title()

        # Filter sensitive fields from config before returning to frontend
        # This prevents accidental exposure of API keys or credentials
        SENSITIVE_CONFIG_PATTERNS = {"api_key", "secret", "token", "password", "credential", "key"}
        safe_config = None
        if skill.config:
            safe_config = {
                k: v for k, v in skill.config.items()
                if not any(pattern in k.lower() for pattern in SENSITIVE_CONFIG_PATTERNS)
            }

        skills.append(SkillExpandInfo(
            id=skill.id,
            skill_type=effective_skill_type,  # Use transformed skill type
            skill_name=metadata["name"],
            skill_description=metadata["description"],
            category=metadata["category"],
            is_enabled=skill.is_enabled,
            provider_name=provider_name,
            provider_type=provider_type,
            integration_id=integration_id,
            config=safe_config
        ))

    # Fetch knowledge base summary
    knowledge_docs = ctx.db.query(AgentKnowledge).filter(
        AgentKnowledge.agent_id == agent_id
    ).all()

    # Aggregate knowledge stats
    total_documents = len(knowledge_docs)
    total_chunks = sum(doc.num_chunks or 0 for doc in knowledge_docs)
    total_size_bytes = sum(doc.file_size_bytes or 0 for doc in knowledge_docs)

    # Count by document type
    document_types: Dict[str, int] = {}
    for doc in knowledge_docs:
        doc_type = doc.document_type or "unknown"
        document_types[doc_type] = document_types.get(doc_type, 0) + 1

    # Count by status
    status_counts: Dict[str, int] = {}
    for doc in knowledge_docs:
        status = doc.status or "unknown"
        status_counts[status] = status_counts.get(status, 0) + 1

    # Check if all completed
    all_completed = all(doc.status == "completed" for doc in knowledge_docs) if knowledge_docs else True

    knowledge_summary = KnowledgeSummary(
        total_documents=total_documents,
        total_chunks=total_chunks,
        total_size_bytes=total_size_bytes,
        document_types=document_types,
        status_counts=status_counts,
        all_completed=all_completed
    )

    return AgentExpandDataResponse(
        agent_id=agent_id,
        skills=skills,
        knowledge_summary=knowledge_summary
    )
