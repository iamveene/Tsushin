"""
Agent Builder Batch Endpoints — Phase I Backend Optimization

Provides two consolidated endpoints for the Agent Studio builder:
1. GET  /{agent_id}/builder-data  — Batch load all builder data in one call
2. POST /{agent_id}/builder-save  — Atomic transactional save of all builder changes

These replace 8+ individual API calls with 2 batch calls, improving performance
and ensuring save atomicity (no more partial-save failures).
"""

import json
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from datetime import datetime

from db import get_db
from models import (
    Agent, AgentSkill, AgentSkillIntegration, AgentKnowledge,
    SandboxedTool, AgentSandboxedTool, Contact, Persona,
    SentinelProfile, SentinelProfileAssignment,
    HubIntegration, GmailIntegration, CalendarIntegration,
)
from models_rbac import User
from auth_dependencies import (
    get_current_user_required,
    get_tenant_context,
    require_permission,
    TenantContext,
)

router = APIRouter(prefix="/api/v2/agents", tags=["agent-builder"])

# Reuse the same skill metadata from routes_agents_protected
SKILL_METADATA = {
    "web_search": {"category": "search", "name": "Web Search", "description": "Search the web for information"},
    "weather": {"category": "integration", "name": "Weather", "description": "Get weather forecasts"},
    "web_scraping": {"category": "search", "name": "Web Scraping", "description": "Scrape content from websites"},
    "audio_transcript": {"category": "audio", "name": "Audio Transcript", "description": "Transcribe audio to text"},
    "audio_tts": {"category": "audio", "name": "Text to Speech", "description": "Convert text to speech"},
    "gmail": {"category": "email", "name": "Email", "description": "Read and send emails"},
    "email": {"category": "email", "name": "Email", "description": "Read and send emails"},
    "calendar": {"category": "integration", "name": "Calendar", "description": "Manage calendar events"},
    "asana": {"category": "integration", "name": "Asana", "description": "Manage Asana tasks"},
    "flows": {"category": "automation", "name": "Flows", "description": "Execute automation flows"},
    "scheduler": {"category": "scheduler", "name": "Scheduler", "description": "Schedule events and reminders"},
    "browser_automation": {"category": "automation", "name": "Browser Automation", "description": "Control web browsers"},
    "shell": {"category": "automation", "name": "Shell", "description": "Execute shell commands"},
    "sandboxed_tools": {"category": "automation", "name": "Sandboxed Tools", "description": "Execute tools in sandboxed environment"},
    "image": {"category": "media", "name": "Image Generation", "description": "Generate and edit images"},
    "flight_search": {"category": "flight_search", "name": "Flight Search", "description": "Search for flights"},
    "adaptive_personality": {"category": "special", "name": "Adaptive Personality", "description": "Dynamic tone adaptation"},
    "knowledge_sharing": {"category": "special", "name": "Knowledge Sharing", "description": "Share knowledge across agents"},
    "agent_switcher": {"category": "special", "name": "Agent Switcher", "description": "Switch between agents in DM"},
}

EXCLUDED_SKILL_TYPES = {"automation"}

SENSITIVE_CONFIG_PATTERNS = {"api_key", "secret", "token", "password", "credential", "key"}


# =============================================================================
# Pydantic Models — builder-data response
# =============================================================================

class BuilderAgentDetail(BaseModel):
    id: int
    contact_name: str
    persona_id: Optional[int] = None
    persona_name: Optional[str] = None
    model_provider: str
    model_name: str
    is_active: bool
    is_default: bool
    enabled_channels: List[str]
    whatsapp_integration_id: Optional[int] = None
    telegram_integration_id: Optional[int] = None
    memory_size: Optional[int] = None
    memory_isolation_mode: str
    enable_semantic_search: bool


class BuilderSkillInfo(BaseModel):
    id: int
    skill_type: str
    skill_name: str
    skill_description: str
    category: str
    is_enabled: bool
    provider_name: Optional[str] = None
    provider_type: Optional[str] = None
    integration_id: Optional[int] = None
    config: Optional[Dict[str, Any]] = None


class BuilderKnowledgeDoc(BaseModel):
    id: int
    document_name: str
    document_type: str
    file_size_bytes: int
    num_chunks: int
    status: str
    error_message: Optional[str] = None


class BuilderSentinelAssignment(BaseModel):
    id: int
    profile_id: int
    profile_name: Optional[str] = None
    profile_slug: Optional[str] = None
    agent_id: Optional[int] = None
    skill_type: Optional[str] = None


class BuilderToolMapping(BaseModel):
    id: int
    sandboxed_tool_id: int
    tool_name: str
    tool_type: str
    is_enabled: bool


# Global palette items (when include_globals=true)
class BuilderAgentListItem(BaseModel):
    id: int
    contact_name: str
    is_active: bool
    is_default: bool
    model_provider: str
    model_name: str


class BuilderPersonaItem(BaseModel):
    id: int
    name: str
    role_description: Optional[str] = None
    personality_traits: Optional[str] = None
    is_active: bool
    is_system: bool


class BuilderSandboxedToolItem(BaseModel):
    id: int
    name: str
    tool_type: str
    is_enabled: bool


class BuilderSentinelProfileItem(BaseModel):
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    is_system: bool
    is_default: bool
    detection_mode: str


class BuilderGlobals(BaseModel):
    agents: List[BuilderAgentListItem]
    personas: List[BuilderPersonaItem]
    sandboxed_tools: List[BuilderSandboxedToolItem]
    sentinel_profiles: List[BuilderSentinelProfileItem]


class BuilderDataResponse(BaseModel):
    agent: BuilderAgentDetail
    skills: List[BuilderSkillInfo]
    knowledge: List[BuilderKnowledgeDoc]
    sentinel_assignments: List[BuilderSentinelAssignment]
    tool_mappings: List[BuilderToolMapping]
    globals: Optional[BuilderGlobals] = None


# =============================================================================
# Pydantic Models — builder-save request/response
# =============================================================================

class SkillSaveItem(BaseModel):
    skill_type: str
    is_enabled: bool
    config: Optional[Dict[str, Any]] = None


class ToolOverrideItem(BaseModel):
    mapping_id: int
    is_enabled: bool


class SentinelSaveData(BaseModel):
    action: str  # "assign" | "remove" | "unchanged"
    profile_id: Optional[int] = None
    assignment_id: Optional[int] = None


class AgentSaveData(BaseModel):
    memory_size: Optional[int] = None
    memory_isolation_mode: Optional[str] = None
    enable_semantic_search: Optional[bool] = None


class BuilderSaveRequest(BaseModel):
    agent: Optional[AgentSaveData] = None
    skills: Optional[List[SkillSaveItem]] = None
    tool_overrides: Optional[List[ToolOverrideItem]] = None
    sentinel: Optional[SentinelSaveData] = None


class BuilderSaveResponse(BaseModel):
    success: bool
    agent_id: int
    changes: Dict[str, Any]


# =============================================================================
# Helper: Enrich skill data (reused from expand-data logic)
# =============================================================================

def _enrich_skill(skill: AgentSkill, skill_integration_map: Dict, db: Session) -> BuilderSkillInfo:
    """Enrich a skill record with metadata, provider info, and safe config."""
    effective_skill_type = skill.skill_type

    skill_integration = skill_integration_map.get(skill.skill_type)
    scheduler_provider = None
    if skill_integration:
        scheduler_provider = skill_integration.scheduler_provider

    if skill.skill_type == "flows" and scheduler_provider in ("google_calendar", "asana"):
        effective_skill_type = "scheduler"

    metadata = SKILL_METADATA.get(effective_skill_type, {
        "category": "other",
        "name": effective_skill_type.replace("_", " ").title(),
        "description": f"Agent skill: {effective_skill_type}",
    })

    provider_name = None
    provider_type = None
    integration_id = None

    if skill_integration:
        integration_id = skill_integration.integration_id

        if scheduler_provider:
            provider_type = scheduler_provider
            provider_name = {
                "flows": "Flows (Built-in)",
                "google_calendar": "Google Calendar",
                "asana": "Asana",
            }.get(provider_type, provider_type.replace("_", " ").title())

        if integration_id:
            hub = db.query(HubIntegration).filter(HubIntegration.id == integration_id).first()
            if hub:
                provider_type = hub.type
                if hub.type == "gmail":
                    gmail = db.query(GmailIntegration).filter(GmailIntegration.id == integration_id).first()
                    provider_name = f"Gmail ({gmail.email_address})" if gmail and gmail.email_address else hub.name or "Gmail"
                elif hub.type == "calendar":
                    cal = db.query(CalendarIntegration).filter(CalendarIntegration.id == integration_id).first()
                    provider_name = f"Google Calendar ({cal.email_address})" if cal and cal.email_address else hub.name or "Google Calendar"
                elif hub.type == "google_flights":
                    provider_name = hub.name or "Google Flights"
                elif hub.type == "amadeus":
                    provider_name = hub.name or "Amadeus"
                else:
                    provider_name = hub.name or hub.type.replace("_", " ").title()

    if not provider_name and skill.config:
        config_provider = (
            skill.config.get("provider") or skill.config.get("provider_name") or
            skill.config.get("search_provider") or skill.config.get("tts_provider") or
            skill.config.get("image_provider")
        )
        if config_provider:
            provider_type = config_provider.lower().replace(" ", "_")
            provider_name = config_provider.replace("_", " ").title()

    safe_config = None
    if skill.config:
        safe_config = {
            k: v for k, v in skill.config.items()
            if not any(p in k.lower() for p in SENSITIVE_CONFIG_PATTERNS)
        }

    return BuilderSkillInfo(
        id=skill.id,
        skill_type=effective_skill_type,
        skill_name=metadata["name"],
        skill_description=metadata["description"],
        category=metadata["category"],
        is_enabled=skill.is_enabled,
        provider_name=provider_name,
        provider_type=provider_type,
        integration_id=integration_id,
        config=safe_config,
    )


def _parse_enabled_channels(agent: Agent) -> List[str]:
    """Parse enabled_channels field which may be JSON string or list."""
    if isinstance(agent.enabled_channels, list):
        return agent.enabled_channels
    elif isinstance(agent.enabled_channels, str) and agent.enabled_channels:
        try:
            return json.loads(agent.enabled_channels)
        except (json.JSONDecodeError, TypeError):
            return ["playground", "whatsapp"]
    return ["playground", "whatsapp"]


# =============================================================================
# GET /api/v2/agents/{agent_id}/builder-data
# =============================================================================

@router.get(
    "/{agent_id}/builder-data",
    response_model=BuilderDataResponse,
    dependencies=[Depends(require_permission("agents.read"))],
)
async def get_builder_data(
    agent_id: int,
    include_globals: bool = Query(False, description="Include global palette data (agents, personas, tools, profiles)"),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Batch endpoint for Agent Studio builder data.

    Consolidates 4-8 individual API calls into a single request:
    - Agent details + persona name
    - Skills with metadata/config (excluding internal skill types)
    - Knowledge documents list
    - Sentinel profile assignments
    - Tool mappings with enabled state
    - (Optional) Global palette data when include_globals=true
    """
    db = ctx.db

    # 1. Agent + Contact name + Persona name
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
    contact_name = contact.friendly_name if contact else "Unknown"

    persona_name = None
    if agent.persona_id:
        persona = db.query(Persona).filter(Persona.id == agent.persona_id).first()
        persona_name = persona.name if persona else None

    agent_detail = BuilderAgentDetail(
        id=agent.id,
        contact_name=contact_name,
        persona_id=agent.persona_id,
        persona_name=persona_name,
        model_provider=agent.model_provider or "gemini",
        model_name=agent.model_name or "gemini-2.5-pro",
        is_active=agent.is_active,
        is_default=agent.is_default or False,
        enabled_channels=_parse_enabled_channels(agent),
        whatsapp_integration_id=agent.whatsapp_integration_id,
        telegram_integration_id=agent.telegram_integration_id,
        memory_size=agent.memory_size,
        memory_isolation_mode=agent.memory_isolation_mode or "isolated",
        enable_semantic_search=agent.enable_semantic_search if agent.enable_semantic_search is not None else True,
    )

    # 2. Skills (all, not just enabled — builder needs full state for diff)
    skills_db = db.query(AgentSkill).filter(
        AgentSkill.agent_id == agent_id,
        AgentSkill.skill_type.notin_(EXCLUDED_SKILL_TYPES),
    ).all()

    skill_integrations = db.query(AgentSkillIntegration).filter(
        AgentSkillIntegration.agent_id == agent_id
    ).all()
    skill_integration_map = {si.skill_type: si for si in skill_integrations}

    skills = [_enrich_skill(s, skill_integration_map, db) for s in skills_db]

    # 3. Knowledge documents (metadata only)
    knowledge_db = db.query(AgentKnowledge).filter(
        AgentKnowledge.agent_id == agent_id
    ).all()
    knowledge = [
        BuilderKnowledgeDoc(
            id=doc.id,
            document_name=doc.document_name,
            document_type=doc.document_type or "unknown",
            file_size_bytes=doc.file_size_bytes or 0,
            num_chunks=doc.num_chunks or 0,
            status=doc.status or "unknown",
            error_message=doc.error_message,
        )
        for doc in knowledge_db
    ]

    # 4. Sentinel profile assignments (with profile name/slug)
    assignment_rows = (
        db.query(SentinelProfileAssignment, SentinelProfile.name, SentinelProfile.slug)
        .join(SentinelProfile, SentinelProfileAssignment.profile_id == SentinelProfile.id)
        .filter(
            SentinelProfileAssignment.tenant_id == ctx.tenant_id,
            SentinelProfileAssignment.agent_id == agent_id,
        )
        .all()
    )
    sentinel_assignments = [
        BuilderSentinelAssignment(
            id=row[0].id,
            profile_id=row[0].profile_id,
            profile_name=row[1],
            profile_slug=row[2],
            agent_id=row[0].agent_id,
            skill_type=row[0].skill_type,
        )
        for row in assignment_rows
    ]

    # 5. Tool mappings (with tool name/type)
    tool_rows = (
        db.query(AgentSandboxedTool, SandboxedTool.name, SandboxedTool.tool_type)
        .join(SandboxedTool, AgentSandboxedTool.sandboxed_tool_id == SandboxedTool.id)
        .filter(AgentSandboxedTool.agent_id == agent_id)
        .all()
    )
    tool_mappings = [
        BuilderToolMapping(
            id=row[0].id,
            sandboxed_tool_id=row[0].sandboxed_tool_id,
            tool_name=row[1] or "Unknown",
            tool_type=row[2] or "command",
            is_enabled=row[0].is_enabled,
        )
        for row in tool_rows
    ]

    # 6. Optional global palette data
    globals_data = None
    if include_globals:
        # Agents list
        agents_query = db.query(Agent, Contact.friendly_name).join(Contact, Agent.contact_id == Contact.id)
        agents_query = ctx.filter_by_tenant(agents_query, Agent.tenant_id)
        agents_rows = agents_query.all()

        global_agents = [
            BuilderAgentListItem(
                id=a.id,
                contact_name=cn or "Unknown",
                is_active=a.is_active,
                is_default=a.is_default or False,
                model_provider=a.model_provider or "gemini",
                model_name=a.model_name or "gemini-2.5-pro",
            )
            for a, cn in agents_rows
        ]

        # Personas
        personas_query = db.query(Persona).filter(Persona.is_active == True)
        personas_db = personas_query.all()
        # Filter: system personas + tenant-specific
        global_personas = [
            BuilderPersonaItem(
                id=p.id, name=p.name,
                role_description=p.role_description,
                personality_traits=p.personality_traits,
                is_active=p.is_active, is_system=p.is_system,
            )
            for p in personas_db
            if p.is_system or p.tenant_id is None or p.tenant_id == ctx.tenant_id
        ]

        # Sandboxed tools
        tools_query = db.query(SandboxedTool)
        tools_db = tools_query.all()
        global_tools = [
            BuilderSandboxedToolItem(
                id=t.id, name=t.name, tool_type=t.tool_type, is_enabled=t.is_enabled,
            )
            for t in tools_db
            if t.tenant_id is None or t.tenant_id == ctx.tenant_id
        ]

        # Sentinel profiles (include system + tenant)
        profiles_db = db.query(SentinelProfile).filter(
            (SentinelProfile.is_system == True) | (SentinelProfile.tenant_id == ctx.tenant_id)
        ).all()
        global_profiles = [
            BuilderSentinelProfileItem(
                id=p.id, name=p.name, slug=p.slug,
                description=p.description, is_system=p.is_system,
                is_default=p.is_default, detection_mode=p.detection_mode,
            )
            for p in profiles_db
        ]

        globals_data = BuilderGlobals(
            agents=global_agents,
            personas=global_personas,
            sandboxed_tools=global_tools,
            sentinel_profiles=global_profiles,
        )

    return BuilderDataResponse(
        agent=agent_detail,
        skills=skills,
        knowledge=knowledge,
        sentinel_assignments=sentinel_assignments,
        tool_mappings=tool_mappings,
        globals=globals_data,
    )


# =============================================================================
# POST /api/v2/agents/{agent_id}/builder-save
# =============================================================================

@router.post(
    "/{agent_id}/builder-save",
    response_model=BuilderSaveResponse,
    dependencies=[Depends(require_permission("agents.write"))],
)
async def save_builder_data(
    agent_id: int,
    data: BuilderSaveRequest,
    ctx: TenantContext = Depends(get_tenant_context),
):
    """
    Atomic save for Agent Studio builder.

    All changes are applied within a single database transaction.
    If any step fails, all changes are rolled back — no partial saves.

    Replaces 1 + N_skills + N_tools + 2 sentinel = 10+ sequential calls.
    """
    db = ctx.db
    changes: Dict[str, Any] = {}

    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    try:
        # --- Step 1: Agent core fields ---
        if data.agent:
            if data.agent.memory_size is not None:
                agent.memory_size = data.agent.memory_size
            if data.agent.memory_isolation_mode is not None:
                if data.agent.memory_isolation_mode not in ("isolated", "shared", "channel_isolated"):
                    raise HTTPException(status_code=400, detail="Invalid memory_isolation_mode")
                agent.memory_isolation_mode = data.agent.memory_isolation_mode
            if data.agent.enable_semantic_search is not None:
                agent.enable_semantic_search = data.agent.enable_semantic_search
            agent.updated_at = datetime.utcnow()
            changes["agent_updated"] = True

        # --- Step 2: Skills ---
        if data.skills is not None:
            skills_updated = []
            skills_created = []

            current_skills = {
                s.skill_type: s
                for s in db.query(AgentSkill).filter(AgentSkill.agent_id == agent_id).all()
            }

            desired_skills = {s.skill_type: s for s in data.skills}

            for skill_data in data.skills:
                existing = current_skills.get(skill_data.skill_type)
                if existing:
                    changed = False
                    if existing.is_enabled != skill_data.is_enabled:
                        existing.is_enabled = skill_data.is_enabled
                        changed = True
                    if skill_data.config is not None:
                        existing.config = skill_data.config
                        changed = True
                    if changed:
                        existing.updated_at = datetime.utcnow()
                        skills_updated.append(skill_data.skill_type)
                else:
                    new_skill = AgentSkill(
                        agent_id=agent_id,
                        skill_type=skill_data.skill_type,
                        is_enabled=skill_data.is_enabled,
                        config=skill_data.config or {},
                    )
                    db.add(new_skill)
                    skills_created.append(skill_data.skill_type)

            # Disable skills not in the desired list
            for skill_type, existing_skill in current_skills.items():
                if skill_type not in desired_skills and existing_skill.is_enabled:
                    existing_skill.is_enabled = False
                    existing_skill.updated_at = datetime.utcnow()
                    skills_updated.append(skill_type)

            if skills_updated:
                changes["skills_updated"] = skills_updated
            if skills_created:
                changes["skills_created"] = skills_created

        # --- Step 3: Tool overrides ---
        if data.tool_overrides:
            tools_updated = []
            for override in data.tool_overrides:
                mapping = db.query(AgentSandboxedTool).filter(
                    AgentSandboxedTool.id == override.mapping_id,
                    AgentSandboxedTool.agent_id == agent_id,
                ).first()
                if mapping and mapping.is_enabled != override.is_enabled:
                    mapping.is_enabled = override.is_enabled
                    mapping.updated_at = datetime.utcnow()
                    tools_updated.append(override.mapping_id)
            if tools_updated:
                changes["tools_updated"] = tools_updated

        # --- Step 4: Sentinel profile assignment ---
        sentinel_changed = False
        if data.sentinel and data.sentinel.action != "unchanged":
            if data.sentinel.action == "assign" and data.sentinel.profile_id:
                profile = db.query(SentinelProfile).filter(
                    SentinelProfile.id == data.sentinel.profile_id
                ).first()
                if not profile:
                    raise HTTPException(status_code=400, detail=f"Sentinel profile {data.sentinel.profile_id} not found")

                # Upsert: find existing agent-level assignment or create
                existing_assignment = db.query(SentinelProfileAssignment).filter(
                    SentinelProfileAssignment.tenant_id == ctx.tenant_id,
                    SentinelProfileAssignment.agent_id == agent_id,
                    SentinelProfileAssignment.skill_type.is_(None),
                ).first()

                if existing_assignment:
                    existing_assignment.profile_id = data.sentinel.profile_id
                    existing_assignment.assigned_by = ctx.user.id
                else:
                    new_assignment = SentinelProfileAssignment(
                        tenant_id=ctx.tenant_id,
                        agent_id=agent_id,
                        profile_id=data.sentinel.profile_id,
                        assigned_by=ctx.user.id,
                    )
                    db.add(new_assignment)

                changes["sentinel_action"] = "assign"
                sentinel_changed = True

            elif data.sentinel.action == "remove":
                if data.sentinel.assignment_id:
                    assignment = db.query(SentinelProfileAssignment).filter(
                        SentinelProfileAssignment.id == data.sentinel.assignment_id,
                        SentinelProfileAssignment.tenant_id == ctx.tenant_id,
                    ).first()
                    if assignment:
                        db.delete(assignment)
                else:
                    db.query(SentinelProfileAssignment).filter(
                        SentinelProfileAssignment.tenant_id == ctx.tenant_id,
                        SentinelProfileAssignment.agent_id == agent_id,
                        SentinelProfileAssignment.skill_type.is_(None),
                    ).delete()

                changes["sentinel_action"] = "remove"
                sentinel_changed = True

        # --- COMMIT: All or nothing ---
        db.commit()

        # Invalidate sentinel cache if sentinel changed
        if sentinel_changed:
            try:
                from services.sentinel_profiles_service import SentinelProfilesService
                SentinelProfilesService._invalidate_cache()
            except ImportError:
                pass  # Sentinel service not available

        return BuilderSaveResponse(
            success=True,
            agent_id=agent_id,
            changes=changes,
        )

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save builder data: {str(e)}")
