"""
Studio API — Public API v1
Wraps the Agent Builder batch endpoints (builder-data / builder-save) with
ApiCaller auth for external API access. Also provides agent cloning.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from db import get_db
from models import (
    Agent, AgentSkill, AgentSkillIntegration, AgentKnowledge,
    SandboxedTool, AgentSandboxedTool, Contact, Persona,
    SentinelProfile, SentinelProfileAssignment,
    HubIntegration, GmailIntegration, CalendarIntegration,
)
from api.api_auth import ApiCaller, require_api_permission
from api.v1.schemas import COMMON_RESPONSES, NOT_FOUND_RESPONSE, VALIDATION_RESPONSE

logger = logging.getLogger(__name__)
router = APIRouter()


# ============================================================================
# Schemas
# ============================================================================

class StudioAgentDetail(BaseModel):
    """Agent details as seen in the Studio builder."""
    id: int = Field(description="Agent ID")
    contact_name: str = Field(description="Agent display name", example="Customer Support Bot")
    persona_id: Optional[int] = Field(None, description="Assigned persona ID")
    persona_name: Optional[str] = Field(None, description="Assigned persona name")
    model_provider: str = Field(description="LLM provider", example="gemini")
    model_name: str = Field(description="LLM model name", example="gemini-2.5-pro")
    is_active: bool = Field(description="Whether the agent is active")
    is_default: bool = Field(description="Whether this is the default agent")
    enabled_channels: List[str] = Field(description="Enabled communication channels", example=["playground", "whatsapp"])
    memory_size: Optional[int] = Field(None, description="Memory size (messages)")
    memory_isolation_mode: str = Field(description="Memory isolation mode", example="isolated")
    enable_semantic_search: bool = Field(description="Whether semantic search is enabled")
    avatar: Optional[str] = Field(None, description="Agent avatar URL/identifier")


class StudioSkillInfo(BaseModel):
    """Skill information in Studio context."""
    id: int = Field(description="Skill record ID")
    skill_type: str = Field(description="Skill type identifier", example="web_search")
    skill_name: str = Field(description="Human-readable skill name", example="Web Search")
    skill_description: str = Field(description="Skill description")
    category: str = Field(description="Skill category", example="search")
    is_enabled: bool = Field(description="Whether the skill is enabled")
    provider_name: Optional[str] = Field(None, description="Provider name if applicable")
    provider_type: Optional[str] = Field(None, description="Provider type if applicable")
    integration_id: Optional[int] = Field(None, description="Hub integration ID if linked")
    config: Optional[Dict[str, Any]] = Field(None, description="Skill configuration (sensitive fields redacted)")


class StudioKnowledgeDoc(BaseModel):
    """Knowledge document metadata."""
    id: int = Field(description="Document ID")
    document_name: str = Field(description="Document filename", example="product-guide.pdf")
    document_type: str = Field(description="Document type", example="pdf")
    file_size_bytes: int = Field(description="File size in bytes")
    num_chunks: int = Field(description="Number of vector chunks")
    status: str = Field(description="Processing status", example="processed")
    error_message: Optional[str] = Field(None, description="Error message if processing failed")


class StudioSentinelAssignment(BaseModel):
    """Sentinel profile assignment info."""
    id: int = Field(description="Assignment ID")
    profile_id: int = Field(description="Sentinel profile ID")
    profile_name: Optional[str] = Field(None, description="Profile name")
    profile_slug: Optional[str] = Field(None, description="Profile slug")
    agent_id: Optional[int] = Field(None, description="Agent ID")
    skill_type: Optional[str] = Field(None, description="Skill type scope")


class StudioToolMapping(BaseModel):
    """Agent-to-sandboxed-tool mapping."""
    id: int = Field(description="Mapping ID")
    sandboxed_tool_id: int = Field(description="Sandboxed tool ID")
    tool_name: str = Field(description="Tool name", example="nmap")
    tool_type: str = Field(description="Tool type", example="command")
    is_enabled: bool = Field(description="Whether the tool mapping is enabled")


class StudioBuilderDataResponse(BaseModel):
    """Complete builder data for an agent in Studio."""
    agent: StudioAgentDetail = Field(description="Agent details")
    skills: List[StudioSkillInfo] = Field(description="Skills with metadata")
    knowledge: List[StudioKnowledgeDoc] = Field(description="Knowledge documents")
    sentinel_assignments: List[StudioSentinelAssignment] = Field(description="Sentinel profile assignments")
    tool_mappings: List[StudioToolMapping] = Field(description="Sandboxed tool mappings")


class StudioSkillSaveItem(BaseModel):
    """Skill update item for builder save."""
    skill_type: str = Field(..., description="Skill type identifier", example="web_search")
    is_enabled: bool = Field(..., description="Whether to enable this skill")
    config: Optional[Dict[str, Any]] = Field(None, description="Skill configuration")


class StudioToolOverrideItem(BaseModel):
    """Tool mapping override for builder save."""
    mapping_id: int = Field(..., description="Tool mapping ID")
    is_enabled: bool = Field(..., description="Whether to enable this tool mapping")


class StudioSentinelSaveData(BaseModel):
    """Sentinel assignment changes for builder save."""
    action: str = Field(..., description="Action: assign, remove, or unchanged", example="assign")
    profile_id: Optional[int] = Field(None, description="Profile ID (required for 'assign' action)")
    assignment_id: Optional[int] = Field(None, description="Assignment ID (for 'remove' action)")


class StudioAgentSaveData(BaseModel):
    """Agent core field updates for builder save."""
    persona_id: Optional[int] = Field(None, description="Persona ID (0 to clear)")
    enabled_channels: Optional[List[str]] = Field(None, description="Enabled channels")
    memory_size: Optional[int] = Field(None, ge=1, le=5000, description="Memory size")
    memory_isolation_mode: Optional[str] = Field(None, description="Memory isolation mode")
    enable_semantic_search: Optional[bool] = Field(None, description="Enable semantic search")
    avatar: Optional[str] = Field(None, description="Avatar URL/identifier")


class StudioSaveRequest(BaseModel):
    """Atomic builder save request."""
    agent: Optional[StudioAgentSaveData] = Field(None, description="Agent core field updates")
    skills: Optional[List[StudioSkillSaveItem]] = Field(None, description="Skill updates (full state)")
    tool_overrides: Optional[List[StudioToolOverrideItem]] = Field(None, description="Tool mapping overrides")
    sentinel: Optional[StudioSentinelSaveData] = Field(None, description="Sentinel assignment changes")


class StudioSaveResponse(BaseModel):
    """Result of an atomic builder save."""
    success: bool = Field(description="Whether the save was successful")
    agent_id: int = Field(description="Agent ID")
    changes: Dict[str, Any] = Field(description="Summary of applied changes")


class StudioCloneResponse(BaseModel):
    """Result of cloning an agent."""
    success: bool = Field(description="Whether the clone was successful")
    original_agent_id: int = Field(description="ID of the agent that was cloned")
    new_agent_id: int = Field(description="ID of the newly created agent clone")
    new_agent_name: str = Field(description="Name of the cloned agent")


# ============================================================================
# Constants
# ============================================================================

SKILL_METADATA = {
    "web_search": {"category": "search", "name": "Web Search", "description": "Search the web for information"},
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
VALID_CHANNELS = {"playground", "whatsapp", "telegram", "slack", "discord"}
SENSITIVE_CONFIG_PATTERNS = {"api_key", "secret", "access_token", "auth_token", "password", "credential"}


# ============================================================================
# Helpers
# ============================================================================

def _parse_enabled_channels(agent: Agent) -> List[str]:
    """Parse enabled_channels which may be JSON string or list."""
    if isinstance(agent.enabled_channels, list):
        return agent.enabled_channels
    elif isinstance(agent.enabled_channels, str) and agent.enabled_channels:
        try:
            return json.loads(agent.enabled_channels)
        except (json.JSONDecodeError, TypeError):
            return ["playground", "whatsapp"]
    return ["playground", "whatsapp"]


def _enrich_skill(skill: AgentSkill, skill_integration_map: dict, db: Session) -> dict:
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

    return {
        "id": skill.id,
        "skill_type": effective_skill_type,
        "skill_name": metadata["name"],
        "skill_description": metadata["description"],
        "category": metadata["category"],
        "is_enabled": skill.is_enabled,
        "provider_name": provider_name,
        "provider_type": provider_type,
        "integration_id": integration_id,
        "config": safe_config,
    }


# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "/api/v1/studio/agents/{agent_id}",
    response_model=StudioBuilderDataResponse,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def get_builder_data(
    agent_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    """
    Retrieve the complete Studio builder state for an agent.

    Returns agent details, skills with provider metadata, knowledge documents,
    sentinel profile assignments, and sandboxed tool mappings in a single call.
    Requires the `agents.read` permission.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Agent details
    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
    contact_name = contact.friendly_name if contact else "Unknown"

    persona_name = None
    if agent.persona_id:
        persona = db.query(Persona).filter(Persona.id == agent.persona_id).first()
        persona_name = persona.name if persona else None

    agent_detail = {
        "id": agent.id,
        "contact_name": contact_name,
        "persona_id": agent.persona_id,
        "persona_name": persona_name,
        "model_provider": agent.model_provider or "gemini",
        "model_name": agent.model_name or "gemini-2.5-pro",
        "is_active": agent.is_active,
        "is_default": agent.is_default or False,
        "enabled_channels": _parse_enabled_channels(agent),
        "memory_size": agent.memory_size,
        "memory_isolation_mode": agent.memory_isolation_mode or "isolated",
        "enable_semantic_search": agent.enable_semantic_search if agent.enable_semantic_search is not None else True,
        "avatar": agent.avatar,
    }

    # Skills
    skills_db = db.query(AgentSkill).filter(
        AgentSkill.agent_id == agent_id,
        AgentSkill.skill_type.notin_(EXCLUDED_SKILL_TYPES),
    ).all()

    skill_integrations = db.query(AgentSkillIntegration).filter(
        AgentSkillIntegration.agent_id == agent_id,
    ).all()
    skill_integration_map = {si.skill_type: si for si in skill_integrations}

    skills = [_enrich_skill(s, skill_integration_map, db) for s in skills_db]

    # Knowledge documents
    knowledge_db = db.query(AgentKnowledge).filter(
        AgentKnowledge.agent_id == agent_id,
    ).all()
    knowledge = [
        {
            "id": doc.id,
            "document_name": doc.document_name,
            "document_type": doc.document_type or "unknown",
            "file_size_bytes": doc.file_size_bytes or 0,
            "num_chunks": doc.num_chunks or 0,
            "status": doc.status or "unknown",
            "error_message": doc.error_message,
        }
        for doc in knowledge_db
    ]

    # Sentinel assignments
    assignment_rows = (
        db.query(SentinelProfileAssignment, SentinelProfile.name, SentinelProfile.slug)
        .join(SentinelProfile, SentinelProfileAssignment.profile_id == SentinelProfile.id)
        .filter(
            SentinelProfileAssignment.tenant_id == caller.tenant_id,
            SentinelProfileAssignment.agent_id == agent_id,
        )
        .all()
    )
    sentinel_assignments = [
        {
            "id": row[0].id,
            "profile_id": row[0].profile_id,
            "profile_name": row[1],
            "profile_slug": row[2],
            "agent_id": row[0].agent_id,
            "skill_type": row[0].skill_type,
        }
        for row in assignment_rows
    ]

    # Tool mappings
    tool_rows = (
        db.query(AgentSandboxedTool, SandboxedTool.name, SandboxedTool.tool_type)
        .join(SandboxedTool, AgentSandboxedTool.sandboxed_tool_id == SandboxedTool.id)
        .filter(AgentSandboxedTool.agent_id == agent_id)
        .all()
    )
    tool_mappings = [
        {
            "id": row[0].id,
            "sandboxed_tool_id": row[0].sandboxed_tool_id,
            "tool_name": row[1] or "Unknown",
            "tool_type": row[2] or "command",
            "is_enabled": row[0].is_enabled,
        }
        for row in tool_rows
    ]

    return {
        "agent": agent_detail,
        "skills": skills,
        "knowledge": knowledge,
        "sentinel_assignments": sentinel_assignments,
        "tool_mappings": tool_mappings,
    }


@router.put(
    "/api/v1/studio/agents/{agent_id}",
    response_model=StudioSaveResponse,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE},
)
async def save_builder_data(
    agent_id: int,
    data: StudioSaveRequest,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    """
    Atomically save agent configuration from the Studio builder.

    Applies all changes (core fields, skills, tool overrides, sentinel assignments)
    within a single transaction; rolls back on any failure.
    Requires the `agents.write` permission.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    changes: Dict[str, Any] = {}

    try:
        # --- Agent core fields ---
        if data.agent:
            if data.agent.persona_id is not None:
                if data.agent.persona_id > 0:
                    persona = db.query(Persona).filter(
                        Persona.id == data.agent.persona_id,
                        (Persona.is_system == True) | (Persona.tenant_id == None) | (Persona.tenant_id == caller.tenant_id),
                    ).first()
                    if not persona:
                        raise HTTPException(status_code=400, detail=f"Persona {data.agent.persona_id} not found")
                agent.persona_id = data.agent.persona_id if data.agent.persona_id > 0 else None
            if data.agent.enabled_channels is not None:
                invalid_ch = set(data.agent.enabled_channels) - VALID_CHANNELS
                if invalid_ch:
                    raise HTTPException(status_code=400, detail=f"Invalid channels: {', '.join(invalid_ch)}")
                agent.enabled_channels = data.agent.enabled_channels
            if data.agent.memory_size is not None:
                agent.memory_size = data.agent.memory_size
            if data.agent.memory_isolation_mode is not None:
                if data.agent.memory_isolation_mode not in ("isolated", "shared", "channel_isolated"):
                    raise HTTPException(status_code=400, detail="Invalid memory_isolation_mode")
                agent.memory_isolation_mode = data.agent.memory_isolation_mode
            if data.agent.enable_semantic_search is not None:
                agent.enable_semantic_search = data.agent.enable_semantic_search
            if data.agent.avatar is not None:
                agent.avatar = data.agent.avatar if data.agent.avatar != "" else None
            agent.updated_at = datetime.utcnow()
            changes["agent_updated"] = True

        # --- Skills ---
        if data.skills is not None:
            valid_skill_types = set(SKILL_METADATA.keys())
            skills_updated = []
            skills_created = []

            current_skills = {
                s.skill_type: s
                for s in db.query(AgentSkill).filter(AgentSkill.agent_id == agent_id).all()
            }

            desired_skills = {s.skill_type: s for s in data.skills}

            for skill_data in data.skills:
                if skill_data.skill_type not in valid_skill_types:
                    raise HTTPException(status_code=400, detail=f"Invalid skill_type: {skill_data.skill_type}")

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

            # Disable skills not in desired list
            for skill_type, existing_skill in current_skills.items():
                if skill_type not in desired_skills and existing_skill.is_enabled:
                    existing_skill.is_enabled = False
                    existing_skill.updated_at = datetime.utcnow()
                    skills_updated.append(skill_type)

            if skills_updated:
                changes["skills_updated"] = skills_updated
            if skills_created:
                changes["skills_created"] = skills_created

        # --- Tool overrides ---
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

        # --- Sentinel assignment ---
        sentinel_changed = False
        if data.sentinel and data.sentinel.action != "unchanged":
            if data.sentinel.action == "assign" and data.sentinel.profile_id:
                profile = db.query(SentinelProfile).filter(
                    SentinelProfile.id == data.sentinel.profile_id,
                    (SentinelProfile.is_system == True) | (SentinelProfile.tenant_id == caller.tenant_id) | (SentinelProfile.tenant_id.is_(None)),
                ).first()
                if not profile:
                    raise HTTPException(status_code=400, detail=f"Sentinel profile {data.sentinel.profile_id} not found")

                existing_assignment = db.query(SentinelProfileAssignment).filter(
                    SentinelProfileAssignment.tenant_id == caller.tenant_id,
                    SentinelProfileAssignment.agent_id == agent_id,
                    SentinelProfileAssignment.skill_type.is_(None),
                ).first()

                if existing_assignment:
                    existing_assignment.profile_id = data.sentinel.profile_id
                else:
                    new_assignment = SentinelProfileAssignment(
                        tenant_id=caller.tenant_id,
                        agent_id=agent_id,
                        profile_id=data.sentinel.profile_id,
                        assigned_by=caller.user_id,
                    )
                    db.add(new_assignment)

                changes["sentinel_action"] = "assign"
                sentinel_changed = True

            elif data.sentinel.action == "remove":
                if data.sentinel.assignment_id:
                    assignment = db.query(SentinelProfileAssignment).filter(
                        SentinelProfileAssignment.id == data.sentinel.assignment_id,
                        SentinelProfileAssignment.tenant_id == caller.tenant_id,
                    ).first()
                    if assignment:
                        db.delete(assignment)
                else:
                    db.query(SentinelProfileAssignment).filter(
                        SentinelProfileAssignment.tenant_id == caller.tenant_id,
                        SentinelProfileAssignment.agent_id == agent_id,
                        SentinelProfileAssignment.skill_type.is_(None),
                    ).delete()

                changes["sentinel_action"] = "remove"
                sentinel_changed = True

        db.commit()

        # Invalidate sentinel cache
        if sentinel_changed:
            try:
                from services.sentinel_profiles_service import SentinelProfilesService
                SentinelProfilesService._invalidate_cache()
            except Exception as e:
                logger.warning(f"Failed to invalidate sentinel cache: {e}")

        logger.info(f"API v1 Studio saved builder data for agent {agent_id}, changes={changes}")

        return {
            "success": True,
            "agent_id": agent_id,
            "changes": changes,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Studio builder save failed for agent {agent_id}")
        raise HTTPException(status_code=500, detail="Failed to save builder data. Check server logs for details.")


@router.post(
    "/api/v1/studio/agents/{agent_id}/clone",
    status_code=201,
    response_model=StudioCloneResponse,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def clone_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    """
    Clone an existing agent and all its configuration.

    Creates a full copy (contact, skills, tool assignments) as an inactive agent.
    Knowledge documents and sentinel assignments are not cloned.
    Requires the `agents.write` permission.
    """
    original = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not original:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Get original contact name
    original_contact = db.query(Contact).filter(Contact.id == original.contact_id).first()
    clone_name = f"{original_contact.friendly_name} (Clone)" if original_contact else f"Agent {agent_id} (Clone)"

    try:
        # Create cloned contact
        new_contact = Contact(
            friendly_name=clone_name,
            role="agent",
            tenant_id=caller.tenant_id,
        )
        db.add(new_contact)
        db.commit()
        db.refresh(new_contact)

        # Create cloned agent (inactive by default, not default)
        new_agent = Agent(
            contact_id=new_contact.id,
            system_prompt=original.system_prompt,
            persona_id=original.persona_id,
            tone_preset_id=original.tone_preset_id,
            keywords=original.keywords,
            model_provider=original.model_provider,
            model_name=original.model_name,
            enabled_channels=_parse_enabled_channels(original),
            avatar=original.avatar,
            memory_size=original.memory_size,
            memory_isolation_mode=original.memory_isolation_mode or "isolated",
            trigger_dm_enabled=original.trigger_dm_enabled,
            enable_semantic_search=original.enable_semantic_search,
            semantic_search_results=original.semantic_search_results,
            semantic_similarity_threshold=original.semantic_similarity_threshold,
            context_message_count=original.context_message_count,
            context_char_limit=original.context_char_limit,
            response_template=original.response_template,
            is_active=False,  # Clone starts inactive
            is_default=False,  # Clone is never default
            tenant_id=caller.tenant_id,
            user_id=caller.user_id,
        )
        db.add(new_agent)
        db.commit()
        db.refresh(new_agent)

        # Clone skills
        original_skills = db.query(AgentSkill).filter(AgentSkill.agent_id == agent_id).all()
        for skill in original_skills:
            new_skill = AgentSkill(
                agent_id=new_agent.id,
                skill_type=skill.skill_type,
                is_enabled=skill.is_enabled,
                config=skill.config or {},
            )
            db.add(new_skill)

        # Clone sandboxed tool assignments
        original_tools = db.query(AgentSandboxedTool).filter(AgentSandboxedTool.agent_id == agent_id).all()
        for tool_assignment in original_tools:
            new_assignment = AgentSandboxedTool(
                agent_id=new_agent.id,
                sandboxed_tool_id=tool_assignment.sandboxed_tool_id,
                is_enabled=tool_assignment.is_enabled,
            )
            db.add(new_assignment)

        db.commit()

        logger.info(f"API v1 cloned agent {agent_id} -> {new_agent.id} for tenant={caller.tenant_id}")

        return {
            "success": True,
            "original_agent_id": agent_id,
            "new_agent_id": new_agent.id,
            "new_agent_name": clone_name,
        }

    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.exception(f"Agent clone failed for agent {agent_id}")
        raise HTTPException(status_code=500, detail="Failed to clone agent. Check server logs for details.")
