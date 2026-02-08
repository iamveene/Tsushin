"""
Agent Management API Routes - Phase 4.4

Provides CRUD operations for agents and tone presets.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from pydantic import BaseModel, Field
from datetime import datetime
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Agent, TonePreset, Contact, ContactAgentMapping, Config, AgentSkill, SandboxedTool, AgentSandboxedTool
from models_rbac import User
from auth_dependencies import TenantContext, get_tenant_context, require_permission

router = APIRouter()

# Global engine reference (set by main routes.py)
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


# ==================== Tone Preset Schemas ====================

class TonePresetResponse(BaseModel):
    id: int
    name: str
    description: str
    is_system: bool
    tenant_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TonePresetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field(..., min_length=1)
    is_system: bool = Field(default=False)


class TonePresetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, min_length=1)


# ==================== Agent Schemas ====================

class AgentResponse(BaseModel):
    id: int
    contact_id: int
    contact_name: str  # Populated from Contact table
    system_prompt: str
    tone_preset_id: Optional[int]
    tone_preset_name: Optional[str]  # Populated from TonePreset table
    custom_tone: Optional[str]
    persona_id: Optional[int]  # ID of assigned Persona
    persona_name: Optional[str]  # Name of assigned Persona
    keywords: List[str]
    # enabled_tools removed - use AgentSkill table for web_search, weather, etc.
    model_provider: str
    model_name: str
    response_template: str

    # Per-agent configuration (Item 10)
    memory_size: Optional[int]  # Messages per sender (1-50)
    memory_isolation_mode: Optional[str] = None  # isolated | shared | channel_isolated
    trigger_dm_enabled: Optional[bool]  # Enable DM auto-response
    trigger_group_filters: Optional[List[str]]  # Group names to monitor
    trigger_number_filters: Optional[List[str]]  # Phone numbers to monitor
    context_message_count: Optional[int]  # Group context messages (1-100)
    context_char_limit: Optional[int]  # Context character limit
    enable_semantic_search: Optional[bool]  # Semantic search enabled
    semantic_search_results: Optional[int]  # Number of semantic results (1-50)
    semantic_similarity_threshold: Optional[float]  # Similarity threshold (0.0-1.0)

    is_active: bool
    is_default: bool
    skills_count: Optional[int] = 0  # Number of enabled skills

    # Phase 10: Channel Configuration
    enabled_channels: Optional[List[str]] = None  # ["playground", "whatsapp", "telegram"]
    whatsapp_integration_id: Optional[int] = None  # Specific MCP instance
    telegram_integration_id: Optional[int] = None  # Future: Telegram bot instance

    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AgentCreate(BaseModel):
    contact_id: int = Field(..., description="ID of the Contact with role='agent'")
    system_prompt: str = Field(..., min_length=1)
    tone_preset_id: Optional[int] = Field(None, description="ID of TonePreset, null for custom tone")
    custom_tone: Optional[str] = Field(None, description="Custom tone description if tone_preset_id is null")
    persona_id: Optional[int] = Field(None, description="ID of Persona to assign to this agent")
    keywords: List[str] = Field(default_factory=list)
    # enabled_tools removed - use AgentSkill table for web_search, weather, etc.
    model_provider: str = Field(default="gemini", pattern="^(openai|anthropic|gemini|ollama|openrouter)$")  # Phase 5.2 + OpenRouter
    model_name: str = Field(default="gemini-2.5-pro")
    response_template: str = Field(default="@{agent_name}: {response}", description="Template for response formatting. Placeholders: {agent_name}, {response}")

    # Per-agent configuration (Item 10)
    memory_size: Optional[int] = Field(None, ge=1, le=5000, description="Messages per sender (1-5000), null uses system default")
    trigger_dm_enabled: Optional[bool] = Field(None, description="Enable DM auto-response, null uses system default")
    trigger_group_filters: Optional[List[str]] = Field(None, description="Group names to monitor, null uses system default")
    trigger_number_filters: Optional[List[str]] = Field(None, description="Phone numbers to monitor, null uses system default")
    context_message_count: Optional[int] = Field(None, ge=1, le=5000, description="Group context messages (1-5000), null uses system default")
    context_char_limit: Optional[int] = Field(None, ge=100, le=100000, description="Context character limit (100-100000), null uses system default")
    # Note: enable_semantic_search is managed via AgentSkill table (/api/agent-skills endpoint)

    # Phase 10: Channel Configuration
    enabled_channels: Optional[List[str]] = Field(default=["playground", "whatsapp"], description="Enabled channels: playground, whatsapp, telegram")
    whatsapp_integration_id: Optional[int] = Field(None, description="Specific WhatsApp MCP instance to use")
    telegram_integration_id: Optional[int] = Field(None, description="Specific Telegram bot instance to use (future)")

    is_active: bool = Field(default=True)
    is_default: bool = Field(default=False)


class AgentUpdate(BaseModel):
    contact_id: Optional[int] = None
    system_prompt: Optional[str] = Field(None, min_length=1)
    tone_preset_id: Optional[int] = None
    custom_tone: Optional[str] = None
    persona_id: Optional[int] = None
    keywords: Optional[List[str]] = None
    # enabled_tools removed - use AgentSkill table for web_search, weather, etc.
    model_provider: Optional[str] = Field(None, pattern="^(openai|anthropic|gemini|ollama|openrouter)$")  # Phase 5.2 + OpenRouter
    model_name: Optional[str] = None
    response_template: Optional[str] = None

    # Per-agent configuration (Item 10)
    memory_size: Optional[int] = Field(None, ge=1, le=5000, description="Messages per sender (1-5000), null uses system default")
    memory_isolation_mode: Optional[str] = Field(None, pattern="^(isolated|shared|channel_isolated)$", description="Memory isolation mode")
    enable_semantic_search: Optional[bool] = Field(None, description="Enable semantic memory search")
    trigger_dm_enabled: Optional[bool] = Field(None, description="Enable DM auto-response, null uses system default")
    trigger_group_filters: Optional[List[str]] = Field(None, description="Group names to monitor, null uses system default")
    trigger_number_filters: Optional[List[str]] = Field(None, description="Phone numbers to monitor, null uses system default")
    context_message_count: Optional[int] = Field(None, ge=1, le=5000, description="Group context messages (1-5000), null uses system default")
    context_char_limit: Optional[int] = Field(None, ge=100, le=100000, description="Context character limit (100-100000), null uses system default")

    # Phase 10: Channel Configuration
    enabled_channels: Optional[List[str]] = Field(None, description="Enabled channels: playground, whatsapp, telegram")
    whatsapp_integration_id: Optional[int] = Field(None, description="Specific WhatsApp MCP instance to use")
    telegram_integration_id: Optional[int] = Field(None, description="Specific Telegram bot instance to use (future)")

    is_active: Optional[bool] = None
    is_default: Optional[bool] = None


# ==================== Tone Preset Routes ====================
# Phase 7.9.2: Added tenant isolation for multi-tenancy support

@router.get("/tones", response_model=List[TonePresetResponse])
def list_tone_presets(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    List all tone presets.

    Phase 7.9.2: Returns presets for user's tenant AND shared (NULL tenant_id) presets.
    """
    query = db.query(TonePreset)
    query = ctx.filter_by_tenant(query, TonePreset.tenant_id)
    tones = query.order_by(TonePreset.is_system.desc(), TonePreset.name).all()
    return tones


@router.get("/tones/{tone_id}", response_model=TonePresetResponse)
def get_tone_preset(
    tone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get a specific tone preset by ID.

    Phase 7.9.2: Verifies user can access this preset (tenant check).
    """
    tone = db.query(TonePreset).filter(TonePreset.id == tone_id).first()
    if not tone:
        raise HTTPException(status_code=404, detail="Tone preset not found")

    if not ctx.can_access_resource(tone.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tone preset")

    return tone


@router.post("/tones", response_model=TonePresetResponse, status_code=201)
def create_tone_preset(
    tone: TonePresetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Create a new tone preset.

    Phase 7.9.2: Assigns preset to user's tenant.
    """
    # Check if name already exists within tenant scope
    query = db.query(TonePreset).filter(TonePreset.name == tone.name)
    query = ctx.filter_by_tenant(query, TonePreset.tenant_id)
    existing = query.first()
    if existing:
        raise HTTPException(status_code=400, detail="Tone preset with this name already exists")

    new_tone = TonePreset(
        **tone.model_dump(),
        tenant_id=ctx.tenant_id  # Assign to user's tenant
    )
    db.add(new_tone)
    db.commit()
    db.refresh(new_tone)
    return new_tone


@router.put("/tones/{tone_id}", response_model=TonePresetResponse)
def update_tone_preset(
    tone_id: int,
    tone: TonePresetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Update an existing tone preset.

    Phase 7.9.2: Verifies user can access this preset (tenant check).
    """
    db_tone = db.query(TonePreset).filter(TonePreset.id == tone_id).first()
    if not db_tone:
        raise HTTPException(status_code=404, detail="Tone preset not found")

    if not ctx.can_access_resource(db_tone.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tone preset")

    # System tones cannot be modified
    if db_tone.is_system:
        raise HTTPException(status_code=403, detail="System tone presets cannot be modified")

    # Check for unique name within tenant scope
    if tone.name and tone.name != db_tone.name:
        query = db.query(TonePreset).filter(
            TonePreset.name == tone.name,
            TonePreset.id != tone_id
        )
        query = ctx.filter_by_tenant(query, TonePreset.tenant_id)
        existing = query.first()
        if existing:
            raise HTTPException(status_code=400, detail="Tone preset with this name already exists")

    # Update fields
    update_data = tone.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_tone, field, value)

    db_tone.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_tone)
    return db_tone


@router.delete("/tones/{tone_id}", status_code=204)
def delete_tone_preset(
    tone_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.delete")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Delete a tone preset.

    Phase 7.9.2: Verifies user can access this preset (tenant check).
    """
    tone = db.query(TonePreset).filter(TonePreset.id == tone_id).first()
    if not tone:
        raise HTTPException(status_code=404, detail="Tone preset not found")

    if not ctx.can_access_resource(tone.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tone preset")

    # System tones cannot be deleted
    if tone.is_system:
        raise HTTPException(status_code=403, detail="System tone presets cannot be deleted")

    # Check if any agents are using this tone
    agents_using = db.query(Agent).filter(Agent.tone_preset_id == tone_id).count()
    if agents_using > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete tone preset: {agents_using} agent(s) are using it"
        )

    db.delete(tone)
    db.commit()
    return None


# ==================== Agent Routes ====================

@router.get("/agents", response_model=List[AgentResponse])
def list_agents(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List all agents with optional filters (requires agents.read permission)"""

    # Apply tenant filtering
    query = ctx.filter_by_tenant(db.query(Agent), Agent.tenant_id)

    if active_only:
        query = query.filter(Agent.is_active == True)

    agents = query.order_by(Agent.is_default.desc(), Agent.id).all()

    # Enrich with contact, tone preset, and persona names
    result = []
    for agent in agents:
        contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
        tone_preset = None
        if agent.tone_preset_id:
            tone_preset = db.query(TonePreset).filter(TonePreset.id == agent.tone_preset_id).first()

        # Get persona if assigned
        from models import Persona
        persona = None
        if agent.persona_id:
            persona = db.query(Persona).filter(Persona.id == agent.persona_id).first()

        # Parse JSON fields if stored as strings
        import json
        # Handle keywords
        if isinstance(agent.keywords, list):
            keywords = agent.keywords
        elif isinstance(agent.keywords, str) and agent.keywords:
            try:
                keywords = json.loads(agent.keywords)
            except (json.JSONDecodeError, TypeError):
                keywords = []
        else:
            keywords = []

        # enabled_tools removed - use AgentSkill table for web_search, weather, etc.

        # Handle trigger_group_filters
        if isinstance(agent.trigger_group_filters, list):
            trigger_group_filters = agent.trigger_group_filters
        elif isinstance(agent.trigger_group_filters, str) and agent.trigger_group_filters:
            try:
                trigger_group_filters = json.loads(agent.trigger_group_filters)
            except (json.JSONDecodeError, TypeError):
                trigger_group_filters = None
        else:
            trigger_group_filters = None

        # Handle trigger_number_filters
        if isinstance(agent.trigger_number_filters, list):
            trigger_number_filters = agent.trigger_number_filters
        elif isinstance(agent.trigger_number_filters, str) and agent.trigger_number_filters:
            try:
                trigger_number_filters = json.loads(agent.trigger_number_filters)
            except (json.JSONDecodeError, TypeError):
                trigger_number_filters = None
        else:
            trigger_number_filters = None

        # Count enabled skills for this agent
        skills_count = db.query(AgentSkill).filter(
            AgentSkill.agent_id == agent.id,
            AgentSkill.is_enabled == True
        ).count()

        agent_dict = {
            "id": agent.id,
            "contact_id": agent.contact_id,
            "contact_name": contact.friendly_name if contact else "Unknown",
            "system_prompt": agent.system_prompt,
            "tone_preset_id": agent.tone_preset_id,
            "tone_preset_name": tone_preset.name if tone_preset else None,
            "custom_tone": agent.custom_tone,
            "persona_id": agent.persona_id,
            "persona_name": persona.name if persona else None,
            "keywords": keywords,
            # enabled_tools removed - use AgentSkill table
            "model_provider": agent.model_provider,
            "model_name": agent.model_name,
            "response_template": agent.response_template if hasattr(agent, 'response_template') else "@{agent_name}: {response}",

            # Per-agent configuration (Item 10)
            "memory_size": agent.memory_size,
            "memory_isolation_mode": agent.memory_isolation_mode,
            "trigger_dm_enabled": agent.trigger_dm_enabled,
            "trigger_group_filters": trigger_group_filters,
            "trigger_number_filters": trigger_number_filters,
            "context_message_count": agent.context_message_count,
            "context_char_limit": agent.context_char_limit,
            "enable_semantic_search": agent.enable_semantic_search,
            "semantic_search_results": agent.semantic_search_results,
            "semantic_similarity_threshold": agent.semantic_similarity_threshold,

            "is_active": agent.is_active,
            "is_default": agent.is_default,
            "skills_count": skills_count,
            "created_at": agent.created_at,
            "updated_at": agent.updated_at
        }
        result.append(AgentResponse(**agent_dict))

    return result


@router.get("/agents/{agent_id}", response_model=AgentResponse)
def get_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get a specific agent by ID.

    Phase 7.9.2: Verifies user can access this agent (tenant check).
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify tenant access
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    # Enrich with contact, tone preset, and persona names
    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
    tone_preset = None
    if agent.tone_preset_id:
        tone_preset = db.query(TonePreset).filter(TonePreset.id == agent.tone_preset_id).first()

    # Get persona if assigned
    from models import Persona
    persona = None
    if agent.persona_id:
        persona = db.query(Persona).filter(Persona.id == agent.persona_id).first()

    # Parse JSON fields if stored as strings
    import json
    # Handle keywords
    if isinstance(agent.keywords, list):
        keywords = agent.keywords
    elif isinstance(agent.keywords, str) and agent.keywords:
        try:
            keywords = json.loads(agent.keywords)
        except (json.JSONDecodeError, TypeError):
            keywords = []
    else:
        keywords = []

    # enabled_tools removed - use AgentSkill table for web_search, weather, etc.

    # Handle trigger_group_filters
    if isinstance(agent.trigger_group_filters, list):
        trigger_group_filters = agent.trigger_group_filters
    elif isinstance(agent.trigger_group_filters, str) and agent.trigger_group_filters:
        try:
            trigger_group_filters = json.loads(agent.trigger_group_filters)
        except (json.JSONDecodeError, TypeError):
            trigger_group_filters = None
    else:
        trigger_group_filters = None

    # Handle trigger_number_filters
    if isinstance(agent.trigger_number_filters, list):
        trigger_number_filters = agent.trigger_number_filters
    elif isinstance(agent.trigger_number_filters, str) and agent.trigger_number_filters:
        try:
            trigger_number_filters = json.loads(agent.trigger_number_filters)
        except (json.JSONDecodeError, TypeError):
            trigger_number_filters = None
    else:
        trigger_number_filters = None

    # Count enabled skills for this agent
    skills_count = db.query(AgentSkill).filter(
        AgentSkill.agent_id == agent.id,
        AgentSkill.is_enabled == True
    ).count()

    agent_dict = {
        "id": agent.id,
        "contact_id": agent.contact_id,
        "contact_name": contact.friendly_name if contact else "Unknown",
        "system_prompt": agent.system_prompt,
        "tone_preset_id": agent.tone_preset_id,
        "tone_preset_name": tone_preset.name if tone_preset else None,
        "custom_tone": agent.custom_tone,
        "persona_id": agent.persona_id,
        "persona_name": persona.name if persona else None,
        "keywords": keywords,
        # enabled_tools removed - use AgentSkill table
        "model_provider": agent.model_provider,
        "model_name": agent.model_name,
        "response_template": agent.response_template if hasattr(agent, 'response_template') else "@{agent_name}: {response}",

        # Per-agent configuration (Item 10)
        "memory_size": agent.memory_size,
        "memory_isolation_mode": agent.memory_isolation_mode,
        "trigger_dm_enabled": agent.trigger_dm_enabled,
        "trigger_group_filters": trigger_group_filters,
        "trigger_number_filters": trigger_number_filters,
        "context_message_count": agent.context_message_count,
        "context_char_limit": agent.context_char_limit,
        "enable_semantic_search": agent.enable_semantic_search,
        "semantic_search_results": agent.semantic_search_results,
        "semantic_similarity_threshold": agent.semantic_similarity_threshold,

        "is_active": agent.is_active,
        "is_default": agent.is_default,
        "skills_count": skills_count,
        # Phase 10: Channel Configuration
        "enabled_channels": agent.enabled_channels if isinstance(agent.enabled_channels, list) else (
            json.loads(agent.enabled_channels) if agent.enabled_channels else ["playground", "whatsapp"]
        ),
        "whatsapp_integration_id": agent.whatsapp_integration_id,
        "telegram_integration_id": agent.telegram_integration_id,

        "created_at": agent.created_at,
        "updated_at": agent.updated_at
    }
    return AgentResponse(**agent_dict)


@router.post("/agents", response_model=AgentResponse, status_code=201)
def create_agent(
    agent: AgentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new agent (requires agents.write permission)"""

    # Validate contact exists and is an agent
    contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")
    if contact.role != "agent":
        raise HTTPException(status_code=400, detail="Contact must have role='agent'")

    # Verify user can access this contact (tenant isolation)
    if not ctx.can_access_resource(contact.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contact")

    # Check if agent for this contact already exists (within tenant)
    query = ctx.filter_by_tenant(db.query(Agent), Agent.tenant_id)
    existing = query.filter(Agent.contact_id == agent.contact_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="Agent for this contact already exists")

    # Validate tone preset if provided
    if agent.tone_preset_id:
        tone = db.query(TonePreset).filter(TonePreset.id == agent.tone_preset_id).first()
        if not tone:
            raise HTTPException(status_code=404, detail="Tone preset not found")

    # If setting as default, unset other defaults
    if agent.is_default:
        db.query(Agent).update({"is_default": False})

    # IMPORTANT: Get model config from Config table to respect user settings
    # Never use hardcoded defaults from Pydantic schema
    config = db.query(Config).first()
    agent_data = agent.model_dump()

    # If model_provider/model_name match Pydantic defaults, use Config table values instead
    if config and agent_data.get("model_provider") == "gemini" and agent_data.get("model_name") == "gemini-2.5-pro":
        # These are the schema defaults - replace with actual config
        agent_data["model_provider"] = config.model_provider
        agent_data["model_name"] = config.model_name

    # Phase 7.6: Assign tenant_id and user_id for multi-tenancy
    agent_data["tenant_id"] = ctx.tenant_id
    agent_data["user_id"] = ctx.user.id

    new_agent = Agent(**agent_data)
    db.add(new_agent)
    db.commit()
    db.refresh(new_agent)

    # Enable agent_switcher skill by default for new agents
    from agent.skills.agent_switcher_skill import AgentSwitcherSkill
    default_switcher_config = AgentSwitcherSkill.get_default_config()
    switcher_skill = AgentSkill(
        agent_id=new_agent.id,
        skill_type="agent_switcher",
        is_enabled=True,
        config=default_switcher_config
    )
    db.add(switcher_skill)
    db.commit()

    # Pass all required parameters when calling get_agent internally
    return get_agent(new_agent.id, db, current_user, ctx)


@router.put("/agents/{agent_id}", response_model=AgentResponse)
def update_agent(
    agent_id: int,
    agent: AgentUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Update an existing agent (requires agents.write permission)"""

    # Get agent with tenant filtering
    query = ctx.filter_by_tenant(db.query(Agent), Agent.tenant_id)
    db_agent = query.filter(Agent.id == agent_id).first()
    if not db_agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify user can access this agent (tenant isolation)
    if not ctx.can_access_resource(db_agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    # Validate contact if being changed
    if agent.contact_id and agent.contact_id != db_agent.contact_id:
        contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
        if not contact:
            raise HTTPException(status_code=404, detail="Contact not found")
        if contact.role != "agent":
            raise HTTPException(status_code=400, detail="Contact must have role='agent'")

        # Check if another agent already uses this contact
        existing = db.query(Agent).filter(
            Agent.contact_id == agent.contact_id,
            Agent.id != agent_id
        ).first()
        if existing:
            raise HTTPException(status_code=400, detail="Agent for this contact already exists")

    # Validate tone preset if provided
    if agent.tone_preset_id:
        tone = db.query(TonePreset).filter(TonePreset.id == agent.tone_preset_id).first()
        if not tone:
            raise HTTPException(status_code=404, detail="Tone preset not found")

    # If setting as default, unset other defaults
    if agent.is_default:
        db.query(Agent).filter(Agent.id != agent_id).update({"is_default": False})

    # Update fields
    update_data = agent.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(db_agent, field, value)

    db_agent.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(db_agent)

    # Pass all required parameters when calling get_agent internally
    return get_agent(agent_id, db, current_user, ctx)


@router.delete("/agents/{agent_id}", status_code=204)
def delete_agent(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.delete")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Delete an agent (requires agents.delete permission)"""

    # Get agent with tenant filtering
    query = ctx.filter_by_tenant(db.query(Agent), Agent.tenant_id)
    agent = query.filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify user can access this agent (tenant isolation)
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    # Cannot delete default agent if it's the only one
    if agent.is_default:
        total_agents = db.query(Agent).count()
        if total_agents == 1:
            raise HTTPException(status_code=400, detail="Cannot delete the only agent")

        # Set another agent as default
        next_agent = db.query(Agent).filter(Agent.id != agent_id).first()
        if next_agent:
            next_agent.is_default = True

    db.delete(agent)
    db.commit()
    return None


# ==================== Contact-Agent Mapping Routes (Phase 4.5) ====================

class ContactAgentMappingResponse(BaseModel):
    id: int
    contact_id: int
    contact_name: str
    agent_id: int
    agent_name: str
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ContactAgentMappingCreate(BaseModel):
    contact_id: int = Field(..., description="ID of the Contact")
    agent_id: int = Field(..., description="ID of the Agent to assign")


@router.get("/contact-agent-mappings", response_model=List[ContactAgentMappingResponse])
def list_contact_agent_mappings(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List all contact-agent mappings for the current tenant (CRIT-011 security fix)."""
    # Filter mappings by tenant: only show mappings where contact belongs to user's tenant
    mappings = db.query(ContactAgentMapping).join(
        Contact, ContactAgentMapping.contact_id == Contact.id
    )
    mappings = ctx.filter_by_tenant(mappings, Contact.tenant_id).all()

    result = []
    for mapping in mappings:
        contact = db.query(Contact).filter(Contact.id == mapping.contact_id).first()
        agent = db.query(Agent).filter(Agent.id == mapping.agent_id).first()

        if contact and agent:
            # Get agent contact name
            agent_contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()

            mapping_dict = {
                "id": mapping.id,
                "contact_id": mapping.contact_id,
                "contact_name": contact.friendly_name,
                "agent_id": mapping.agent_id,
                "agent_name": agent_contact.friendly_name if agent_contact else "Unknown",
                "created_at": mapping.created_at,
                "updated_at": mapping.updated_at
            }
            result.append(ContactAgentMappingResponse(**mapping_dict))

    return result


@router.get("/contact-agent-mappings/contact/{contact_id}")
def get_contact_agent_mapping(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Get agent mapping for a specific contact (CRIT-011 security fix)."""
    # First verify the contact exists and belongs to user's tenant
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if not ctx.can_access_resource(contact.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contact")

    mapping = db.query(ContactAgentMapping).filter(
        ContactAgentMapping.contact_id == contact_id
    ).first()

    if not mapping:
        return None

    agent = db.query(Agent).filter(Agent.id == mapping.agent_id).first()

    if contact and agent:
        agent_contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()

        mapping_dict = {
            "id": mapping.id,
            "contact_id": mapping.contact_id,
            "contact_name": contact.friendly_name,
            "agent_id": mapping.agent_id,
            "agent_name": agent_contact.friendly_name if agent_contact else "Unknown",
            "created_at": mapping.created_at,
            "updated_at": mapping.updated_at
        }
        return ContactAgentMappingResponse(**mapping_dict)

    return None


@router.post("/contact-agent-mappings", response_model=ContactAgentMappingResponse, status_code=201)
def create_contact_agent_mapping(
    mapping: ContactAgentMappingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create or update contact-agent mapping (CRIT-011 security fix)."""
    # Validate contact exists
    contact = db.query(Contact).filter(Contact.id == mapping.contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    # Verify contact belongs to user's tenant
    if not ctx.can_access_resource(contact.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contact")

    # Validate agent exists and is active
    agent = db.query(Agent).filter(Agent.id == mapping.agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")
    if not agent.is_active:
        raise HTTPException(status_code=400, detail="Cannot assign inactive agent")

    # Verify agent belongs to user's tenant (prevent cross-tenant mapping)
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    # Check if mapping already exists
    existing = db.query(ContactAgentMapping).filter(
        ContactAgentMapping.contact_id == mapping.contact_id
    ).first()

    if existing:
        # Update existing mapping
        existing.agent_id = mapping.agent_id
        existing.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)

        # Build response
        agent_contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
        mapping_dict = {
            "id": existing.id,
            "contact_id": existing.contact_id,
            "contact_name": contact.friendly_name,
            "agent_id": existing.agent_id,
            "agent_name": agent_contact.friendly_name if agent_contact else "Unknown",
            "created_at": existing.created_at,
            "updated_at": existing.updated_at
        }
        return ContactAgentMappingResponse(**mapping_dict)
    else:
        # Create new mapping
        new_mapping = ContactAgentMapping(**mapping.model_dump())
        db.add(new_mapping)
        db.commit()
        db.refresh(new_mapping)

        # Build response
        agent_contact = db.query(Contact).filter(Contact.id == agent.contact_id).first()
        mapping_dict = {
            "id": new_mapping.id,
            "contact_id": new_mapping.contact_id,
            "contact_name": contact.friendly_name,
            "agent_id": new_mapping.agent_id,
            "agent_name": agent_contact.friendly_name if agent_contact else "Unknown",
            "created_at": new_mapping.created_at,
            "updated_at": new_mapping.updated_at
        }
        return ContactAgentMappingResponse(**mapping_dict)


@router.delete("/contact-agent-mappings/contact/{contact_id}", status_code=204)
def delete_contact_agent_mapping(
    contact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("contacts.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Delete contact-agent mapping (reverts to default agent) (CRIT-011 security fix)."""
    # Verify the contact exists and belongs to user's tenant
    contact = db.query(Contact).filter(Contact.id == contact_id).first()
    if not contact:
        raise HTTPException(status_code=404, detail="Contact not found")

    if not ctx.can_access_resource(contact.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this contact")

    mapping = db.query(ContactAgentMapping).filter(
        ContactAgentMapping.contact_id == contact_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    db.delete(mapping)
    db.commit()
    return None


# ==================== Agent Custom Tools ====================

class AgentSandboxedToolResponse(BaseModel):
    """Response schema for agent custom tool mapping"""
    id: int
    agent_id: int
    sandboxed_tool_id: int
    tool_name: str
    tool_type: str
    is_enabled: bool
    created_at: datetime
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class AgentSandboxedToolCreate(BaseModel):
    """Schema for creating agent custom tool mapping"""
    sandboxed_tool_id: int = Field(..., gt=0)
    is_enabled: bool = Field(default=True)


class AgentSandboxedToolUpdate(BaseModel):
    """Schema for updating agent custom tool mapping"""
    is_enabled: bool


@router.get("/agents/{agent_id}/custom-tools", response_model=List[AgentSandboxedToolResponse])
def get_agent_custom_tools(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Get all custom tools for an agent (CRIT-011 security fix)."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify agent belongs to user's tenant
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    # Get all mappings with tool details
    mappings = db.query(AgentSandboxedTool).filter(
        AgentSandboxedTool.agent_id == agent_id
    ).all()

    results = []
    for mapping in mappings:
        tool = db.query(SandboxedTool).filter(SandboxedTool.id == mapping.sandboxed_tool_id).first()
        if tool:
            results.append({
                "id": mapping.id,
                "agent_id": mapping.agent_id,
                "sandboxed_tool_id": mapping.sandboxed_tool_id,
                "tool_name": tool.name,
                "tool_type": tool.tool_type,
                "is_enabled": mapping.is_enabled,
                "created_at": mapping.created_at,
                "updated_at": mapping.updated_at
            })

    return results


@router.post("/agents/{agent_id}/custom-tools", response_model=AgentSandboxedToolResponse, status_code=201)
def add_agent_custom_tool(
    agent_id: int,
    data: AgentSandboxedToolCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Add a custom tool to an agent (CRIT-011 security fix)."""
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify agent belongs to user's tenant
    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    tool = db.query(SandboxedTool).filter(SandboxedTool.id == data.sandboxed_tool_id).first()
    if not tool:
        raise HTTPException(status_code=404, detail="Custom tool not found")

    # Verify tool belongs to user's tenant (prevent cross-tenant tool binding)
    if not ctx.can_access_resource(tool.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this custom tool")

    # Check if mapping already exists
    existing = db.query(AgentSandboxedTool).filter(
        AgentSandboxedTool.agent_id == agent_id,
        AgentSandboxedTool.sandboxed_tool_id == data.sandboxed_tool_id
    ).first()

    if existing:
        raise HTTPException(status_code=400, detail="Tool already assigned to agent")

    # Create mapping
    mapping = AgentSandboxedTool(
        agent_id=agent_id,
        sandboxed_tool_id=data.sandboxed_tool_id,
        is_enabled=data.is_enabled
    )
    db.add(mapping)
    db.commit()
    db.refresh(mapping)

    return {
        "id": mapping.id,
        "agent_id": mapping.agent_id,
        "sandboxed_tool_id": mapping.sandboxed_tool_id,
        "tool_name": tool.name,
        "tool_type": tool.tool_type,
        "is_enabled": mapping.is_enabled,
        "created_at": mapping.created_at,
        "updated_at": mapping.updated_at
    }


@router.patch("/agents/{agent_id}/custom-tools/{mapping_id}", response_model=AgentSandboxedToolResponse)
def update_agent_custom_tool(
    agent_id: int,
    mapping_id: int,
    data: AgentSandboxedToolUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Update agent custom tool mapping (toggle enabled/disabled) (CRIT-011 security fix)."""
    # First verify the agent exists and belongs to user's tenant
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    mapping = db.query(AgentSandboxedTool).filter(
        AgentSandboxedTool.id == mapping_id,
        AgentSandboxedTool.agent_id == agent_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    mapping.is_enabled = data.is_enabled
    db.commit()
    db.refresh(mapping)

    tool = db.query(SandboxedTool).filter(SandboxedTool.id == mapping.sandboxed_tool_id).first()

    return {
        "id": mapping.id,
        "agent_id": mapping.agent_id,
        "sandboxed_tool_id": mapping.sandboxed_tool_id,
        "tool_name": tool.name,
        "tool_type": tool.tool_type,
        "is_enabled": mapping.is_enabled,
        "created_at": mapping.created_at,
        "updated_at": mapping.updated_at
    }


@router.delete("/agents/{agent_id}/custom-tools/{mapping_id}")
def delete_agent_custom_tool(
    agent_id: int,
    mapping_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Remove a custom tool from an agent (CRIT-011 security fix)."""
    # First verify the agent exists and belongs to user's tenant
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this agent")

    mapping = db.query(AgentSandboxedTool).filter(
        AgentSandboxedTool.id == mapping_id,
        AgentSandboxedTool.agent_id == agent_id
    ).first()

    if not mapping:
        raise HTTPException(status_code=404, detail="Mapping not found")

    db.delete(mapping)
    db.commit()
    return {"message": "Custom tool removed from agent"}
