"""
Agent CRUD — Public API v1
Provides agent management endpoints including create, read, update, delete,
and profile/skill assignment.
"""

import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from db import get_db
from models import Agent, Contact, AgentSkill, AgentSandboxedTool, SandboxedTool, Persona, TonePreset
from api.api_auth import ApiCaller, require_api_permission
from api.sanitizers import strip_html_tags, sanitize_text_field
from api.v1.schemas import (
    PaginationMeta, StatusResponse, COMMON_RESPONSES, NOT_FOUND_RESPONSE, VALIDATION_RESPONSE,
)

logger = logging.getLogger(__name__)
router = APIRouter()

VALID_CHANNELS = {"playground", "whatsapp", "telegram", "slack", "discord"}


# ============================================================================
# Schemas
# ============================================================================

class AgentSkillInfo(BaseModel):
    skill_type: str
    is_enabled: bool
    config: Optional[dict] = None


class AgentSummary(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    model_provider: str
    model_name: str
    is_active: bool
    is_default: bool
    avatar: Optional[str] = None
    enabled_channels: Optional[List[str]] = None
    persona: Optional[dict] = None
    skills: List[str] = []
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class PaginatedAgentResponse(BaseModel):
    data: List[AgentSummary] = Field(description="List of agents")
    meta: PaginationMeta = Field(description="Pagination metadata")


class AgentCreateRequest(BaseModel):
    model_config = {"populate_by_name": True}

    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    system_prompt: str = Field(..., min_length=1)
    model_provider: str = Field(default="gemini", pattern="^(openai|anthropic|gemini|ollama|openrouter|groq|grok|deepseek)$")
    model_name: str = Field(default="gemini-2.5-pro", validation_alias="model")
    persona_id: Optional[int] = None
    keywords: List[str] = Field(default_factory=list)
    enabled_channels: List[str] = Field(default_factory=lambda: ["playground"])
    avatar: Optional[str] = None
    memory_size: Optional[int] = Field(None, ge=1, le=5000)
    memory_isolation_mode: Optional[str] = Field(None, pattern="^(isolated|shared|channel_isolated)$")
    trigger_dm_enabled: Optional[bool] = None
    enable_semantic_search: Optional[bool] = None
    is_active: bool = True
    is_default: bool = False
    skill_types: Optional[List[str]] = None
    sandboxed_tool_ids: Optional[List[int]] = None

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str) -> str:
        """Strip HTML tags from agent name to prevent stored XSS."""
        cleaned = strip_html_tags(v)
        if not cleaned or not cleaned.strip():
            raise ValueError("Name must not be empty after removing HTML tags")
        return cleaned.strip()

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: str | None) -> str | None:
        """Strip HTML tags from description to prevent stored XSS."""
        if v is None:
            return v
        return strip_html_tags(v).strip() or None

    @field_validator("system_prompt")
    @classmethod
    def sanitize_system_prompt(cls, v: str) -> str:
        """Strip HTML tags from system_prompt to prevent stored XSS."""
        return strip_html_tags(v)

    @field_validator("keywords")
    @classmethod
    def sanitize_keywords(cls, v: List[str]) -> List[str]:
        """Strip HTML tags from each keyword to prevent stored XSS."""
        return [strip_html_tags(k) for k in v]

    @field_validator("enabled_channels")
    @classmethod
    def validate_enabled_channels(cls, v: List[str]) -> List[str]:
        """Validate that each channel is allowed and deduplicate."""
        invalid = set(v) - VALID_CHANNELS
        if invalid:
            raise ValueError(
                f"Invalid channel(s): {', '.join(sorted(invalid))}. "
                f"Allowed: {', '.join(sorted(VALID_CHANNELS))}"
            )
        return list(dict.fromkeys(v))


class AgentUpdateRequest(BaseModel):
    model_config = {"populate_by_name": True}

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    description: Optional[str] = Field(None, max_length=500)
    system_prompt: Optional[str] = None
    model_provider: Optional[str] = Field(None, pattern="^(openai|anthropic|gemini|ollama|openrouter|groq|grok|deepseek)$")
    model_name: Optional[str] = Field(None, validation_alias="model")
    persona_id: Optional[int] = None
    keywords: Optional[List[str]] = None
    enabled_channels: Optional[List[str]] = None
    avatar: Optional[str] = None
    memory_size: Optional[int] = Field(None, ge=1, le=5000)
    memory_isolation_mode: Optional[str] = Field(None, pattern="^(isolated|shared|channel_isolated)$")
    trigger_dm_enabled: Optional[bool] = None
    enable_semantic_search: Optional[bool] = None
    is_active: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def sanitize_name(cls, v: str | None) -> str | None:
        """Strip HTML tags from agent name to prevent stored XSS."""
        if v is None:
            return v
        cleaned = strip_html_tags(v)
        if not cleaned or not cleaned.strip():
            raise ValueError("Name must not be empty after removing HTML tags")
        return cleaned.strip()

    @field_validator("description")
    @classmethod
    def sanitize_description(cls, v: str | None) -> str | None:
        """Strip HTML tags from description to prevent stored XSS."""
        if v is None:
            return v
        return strip_html_tags(v).strip() or None

    @field_validator("system_prompt")
    @classmethod
    def sanitize_system_prompt(cls, v: str | None) -> str | None:
        """Strip HTML tags from system_prompt to prevent stored XSS."""
        if v is None:
            return v
        return strip_html_tags(v)

    @field_validator("keywords")
    @classmethod
    def sanitize_keywords(cls, v: List[str] | None) -> List[str] | None:
        """Strip HTML tags from each keyword to prevent stored XSS."""
        if v is None:
            return v
        return [strip_html_tags(k) for k in v]

    @field_validator("enabled_channels")
    @classmethod
    def validate_enabled_channels(cls, v: List[str] | None) -> List[str] | None:
        """Validate that each channel is allowed and deduplicate."""
        if v is None:
            return v
        invalid = set(v) - VALID_CHANNELS
        if invalid:
            raise ValueError(
                f"Invalid channel(s): {', '.join(sorted(invalid))}. "
                f"Allowed: {', '.join(sorted(VALID_CHANNELS))}"
            )
        return list(dict.fromkeys(v))


class SkillAssignRequest(BaseModel):
    skill_types: List[str]
    replace: bool = False


class PersonaAssignRequest(BaseModel):
    persona_id: Optional[int]


class SecurityProfileAssignRequest(BaseModel):
    security_profile_id: Optional[int]


# ============================================================================
# Helpers
# ============================================================================

def _enrich_agent(agent: Agent, db: Session) -> dict:
    """Build a rich agent summary from database records."""
    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
    agent_name = contact.friendly_name if contact else f"Agent {agent.id}"

    # Use the stored description if set; otherwise fall back to deriving
    # a short summary from the first line of system_prompt.
    description = agent.description
    if description is None and agent.system_prompt:
        first_line = agent.system_prompt.split('\n')[0]
        if len(first_line) < 200:
            description = first_line

    persona_info = None
    if agent.persona_id:
        persona = db.query(Persona).filter(Persona.id == agent.persona_id).first()
        if persona:
            persona_info = {"id": persona.id, "name": persona.name}

    skills = db.query(AgentSkill).filter(
        AgentSkill.agent_id == agent.id,
        AgentSkill.is_enabled == True,
    ).all()
    skill_types = [s.skill_type for s in skills]

    channels = agent.enabled_channels
    if isinstance(channels, str):
        try:
            channels = json.loads(channels)
        except (json.JSONDecodeError, TypeError):
            channels = ["playground", "whatsapp"]

    return {
        "id": agent.id,
        "name": agent_name,
        "description": description,
        "model_provider": agent.model_provider,
        "model_name": agent.model_name,
        "is_active": agent.is_active,
        "is_default": agent.is_default,
        "avatar": agent.avatar,
        "enabled_channels": channels,
        "persona": persona_info,
        "skills": skill_types,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


def _get_agent_detail(agent: Agent, db: Session) -> dict:
    """Build a detailed agent response including all configuration."""
    base = _enrich_agent(agent, db)
    base.update({
        "system_prompt": agent.system_prompt,
        "persona_id": agent.persona_id,
        "tone_preset_id": agent.tone_preset_id,
        "keywords": agent.keywords or [],
        "memory_size": agent.memory_size,
        "memory_isolation_mode": agent.memory_isolation_mode,
        "trigger_dm_enabled": agent.trigger_dm_enabled,
        "trigger_group_filters": agent.trigger_group_filters,
        "trigger_number_filters": agent.trigger_number_filters,
        "context_message_count": agent.context_message_count,
        "context_char_limit": agent.context_char_limit,
        "enable_semantic_search": agent.enable_semantic_search,
        "semantic_search_results": agent.semantic_search_results,
        "semantic_similarity_threshold": agent.semantic_similarity_threshold,
        "response_template": agent.response_template,
        "contact_id": agent.contact_id,
        "tenant_id": agent.tenant_id,
    })

    # Add sandboxed tools
    tool_assignments = db.query(AgentSandboxedTool).filter(
        AgentSandboxedTool.agent_id == agent.id,
        AgentSandboxedTool.is_enabled == True,
    ).all()
    tool_ids = [t.sandboxed_tool_id for t in tool_assignments]
    base["sandboxed_tool_ids"] = tool_ids

    # Add skill details
    skills = db.query(AgentSkill).filter(AgentSkill.agent_id == agent.id).all()
    base["skills_detail"] = [
        {"skill_type": s.skill_type, "is_enabled": s.is_enabled, "config": s.config}
        for s in skills
    ]

    return base


# ============================================================================
# Endpoints
# ============================================================================

@router.get(
    "/api/v1/agents",
    response_model=PaginatedAgentResponse,
    responses=COMMON_RESPONSES,
)
async def list_agents(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    per_page: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    search: Optional[str] = Query(None, description="Search by agent name"),
    channel: Optional[str] = Query(None, description="Filter by enabled channel"),
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    """
    List agents with pagination and filtering.

    Returns a paginated list of agents belonging to the caller's tenant.
    Supports filtering by active status, name search, and enabled channel.
    Requires `agents.read` permission.
    """
    from sqlalchemy import func

    query = db.query(Agent).filter(Agent.tenant_id == caller.tenant_id)

    if is_active is not None:
        query = query.filter(Agent.is_active == is_active)

    # Push search filter to DB using join
    if search:
        query = query.join(Contact, Agent.contact_id == Contact.id).filter(
            Contact.friendly_name.ilike(f"%{search}%")
        )

    # Filter by channel at DB level where possible
    if channel:
        # enabled_channels stored as JSON array — use LIKE for DB-level filtering
        query = query.filter(Agent.enabled_channels.ilike(f'%"{channel}"%'))

    # Get total count before pagination
    total = query.count()

    # Apply SQL-level pagination
    page_agents = query.order_by(Agent.id).offset((page - 1) * per_page).limit(per_page).all()

    return {
        "data": [_enrich_agent(a, db) for a in page_agents],
        "meta": {
            "total": total,
            "page": page,
            "per_page": per_page,
        },
    }


@router.get(
    "/api/v1/agents/{agent_id}",
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def get_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.read")),
):
    """
    Get detailed agent configuration.

    Returns the full agent configuration including system prompt, skills,
    sandboxed tools, memory settings, and channel configuration.
    Requires `agents.read` permission.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _get_agent_detail(agent, db)


@router.post(
    "/api/v1/agents",
    status_code=201,
    responses={**COMMON_RESPONSES, **VALIDATION_RESPONSE},
)
async def create_agent(
    request: AgentCreateRequest,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    """
    Create a new agent with auto-generated Contact record.

    Accepts agent configuration including name, model provider, system prompt,
    skills, and sandboxed tools. Requires `agents.write` permission.
    """
    # Auto-create contact for the agent
    contact = Contact(
        friendly_name=request.name,
        role="agent",
        tenant_id=caller.tenant_id,
    )
    db.add(contact)
    db.commit()
    db.refresh(contact)

    # Handle default agent
    if request.is_default:
        db.query(Agent).filter(
            Agent.tenant_id == caller.tenant_id,
            Agent.is_default == True,
        ).update({"is_default": False})
        db.commit()

    # Validate persona_id if provided (tenant isolation)
    if request.persona_id is not None:
        persona = db.query(Persona).filter(
            Persona.id == request.persona_id,
            (Persona.is_system == True) | (Persona.tenant_id == caller.tenant_id) | (Persona.tenant_id.is_(None)),
        ).first()
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")

    agent = Agent(
        contact_id=contact.id,
        description=request.description,
        system_prompt=request.system_prompt,
        persona_id=request.persona_id,
        keywords=request.keywords,
        model_provider=request.model_provider,
        model_name=request.model_name,
        enabled_channels=request.enabled_channels,
        avatar=request.avatar,
        memory_size=request.memory_size,
        memory_isolation_mode=request.memory_isolation_mode or "isolated",
        trigger_dm_enabled=request.trigger_dm_enabled,
        enable_semantic_search=request.enable_semantic_search if request.enable_semantic_search is not None else True,
        is_active=request.is_active,
        is_default=request.is_default,
        tenant_id=caller.tenant_id,
        user_id=caller.user_id,
    )
    db.add(agent)
    db.commit()
    db.refresh(agent)

    # Add default agent_switcher skill
    default_skill = AgentSkill(
        agent_id=agent.id,
        skill_type="agent_switcher",
        is_enabled=True,
        config={"auto_detect": True},
    )
    db.add(default_skill)

    # Add requested skills
    if request.skill_types:
        for skill_type in request.skill_types:
            if skill_type != "agent_switcher":
                skill = AgentSkill(
                    agent_id=agent.id,
                    skill_type=skill_type,
                    is_enabled=True,
                    config={},
                )
                db.add(skill)

    # Add sandboxed tools
    if request.sandboxed_tool_ids:
        for tool_id in request.sandboxed_tool_ids:
            tool = db.query(SandboxedTool).filter(
                SandboxedTool.id == tool_id,
                SandboxedTool.tenant_id == caller.tenant_id,
            ).first()
            if tool:
                assignment = AgentSandboxedTool(
                    agent_id=agent.id,
                    sandboxed_tool_id=tool_id,
                    is_enabled=True,
                )
                db.add(assignment)

    db.commit()

    logger.info(f"API created agent '{request.name}' (id={agent.id}) for tenant={caller.tenant_id}")
    return _get_agent_detail(agent, db)


@router.put(
    "/api/v1/agents/{agent_id}",
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, **VALIDATION_RESPONSE},
)
async def update_agent(
    agent_id: int,
    request: AgentUpdateRequest,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    """
    Update agent configuration (partial update).

    Only provided fields are updated; omitted fields remain unchanged.
    Requires `agents.write` permission.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Validate persona_id if provided (tenant isolation)
    if request.persona_id is not None:
        persona = db.query(Persona).filter(
            Persona.id == request.persona_id,
            (Persona.is_system == True) | (Persona.tenant_id == caller.tenant_id) | (Persona.tenant_id.is_(None)),
        ).first()
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")

    # Update contact name if name is provided
    if request.name is not None:
        contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
        if contact:
            contact.friendly_name = request.name

    update_fields = request.model_dump(exclude_unset=True, exclude={"name"})
    for field, value in update_fields.items():
        if hasattr(agent, field):
            setattr(agent, field, value)

    agent.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(agent)

    return _get_agent_detail(agent, db)


@router.delete(
    "/api/v1/agents/{agent_id}",
    status_code=204,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE, 400: {"description": "Cannot delete the only agent"}},
)
async def delete_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.delete")),
):
    """
    Delete an agent permanently.

    Cannot delete the last remaining agent for a tenant. If the deleted agent
    is the default, another agent is automatically promoted. Requires `agents.delete` permission.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Cannot delete default agent if it's the only one for this tenant
    if agent.is_default:
        total_agents = db.query(Agent).filter(
            Agent.tenant_id == caller.tenant_id,
        ).count()
        if total_agents == 1:
            raise HTTPException(status_code=400, detail="Cannot delete the only agent")

        # Set another agent as default
        next_agent = db.query(Agent).filter(
            Agent.tenant_id == caller.tenant_id,
            Agent.id != agent_id,
        ).first()
        if next_agent:
            next_agent.is_default = True

    db.delete(agent)
    db.commit()


@router.post(
    "/api/v1/agents/{agent_id}/skills",
    response_model=StatusResponse,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def assign_skills(
    agent_id: int,
    request: SkillAssignRequest,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    """
    Assign skills to an agent.

    Adds the specified skill types to the agent. Use `replace: true` to replace
    all existing skills. Requires `agents.write` permission.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if request.replace:
        db.query(AgentSkill).filter(AgentSkill.agent_id == agent.id).delete()

    for skill_type in request.skill_types:
        existing = db.query(AgentSkill).filter(
            AgentSkill.agent_id == agent.id,
            AgentSkill.skill_type == skill_type,
        ).first()
        if not existing:
            skill = AgentSkill(
                agent_id=agent.id,
                skill_type=skill_type,
                is_enabled=True,
                config={},
            )
            db.add(skill)

    db.commit()
    return {"status": "success", "message": f"Skills assigned to agent {agent_id}"}


@router.delete(
    "/api/v1/agents/{agent_id}/skills/{skill_type}",
    status_code=204,
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def remove_skill(
    agent_id: int,
    skill_type: str,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    """
    Remove a skill from an agent.

    Deletes the specified skill type assignment. Returns 404 if the skill is not
    assigned to this agent. Requires `agents.write` permission.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    deleted = db.query(AgentSkill).filter(
        AgentSkill.agent_id == agent.id,
        AgentSkill.skill_type == skill_type,
    ).delete()
    db.commit()

    if not deleted:
        raise HTTPException(status_code=404, detail=f"Skill '{skill_type}' not found on agent")


@router.put(
    "/api/v1/agents/{agent_id}/persona",
    responses={**COMMON_RESPONSES, **NOT_FOUND_RESPONSE},
)
async def assign_persona(
    agent_id: int,
    request: PersonaAssignRequest,
    db: Session = Depends(get_db),
    caller: ApiCaller = Depends(require_api_permission("agents.write")),
):
    """
    Assign or clear a persona on an agent.

    Set `persona_id` to assign a persona, or `null` to clear.
    Validates tenant ownership of the persona. Requires `agents.write` permission.
    """
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == caller.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if request.persona_id is not None:
        persona = db.query(Persona).filter(
            Persona.id == request.persona_id,
            (Persona.is_system == True) | (Persona.tenant_id == caller.tenant_id) | (Persona.tenant_id.is_(None)),
        ).first()
        if not persona:
            raise HTTPException(status_code=404, detail="Persona not found")

    agent.persona_id = request.persona_id
    agent.updated_at = datetime.utcnow()
    db.commit()
    return {"status": "success", "persona_id": request.persona_id}
