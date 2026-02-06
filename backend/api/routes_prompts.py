"""
Admin API Routes for Prompts & Patterns Management
Provides CRUD endpoints for system-level prompt configuration:
- Global config (system prompt, response template)
- Tone presets
- Slash commands
- Project command patterns
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime
import logging
import re
import json as json_module

from models import Config, TonePreset, SlashCommand, ProjectCommandPattern, Agent
from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/prompts", tags=["prompts"])

# Global engine reference (set by main app.py)
_engine = None

def set_engine(engine):
    global _engine
    _engine = engine

def get_db():
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# ============================================================================
# Global Config Models
# ============================================================================

class PromptConfigResponse(BaseModel):
    system_prompt: str
    response_template: str
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class PromptConfigUpdate(BaseModel):
    system_prompt: Optional[str] = None
    response_template: Optional[str] = None


# ============================================================================
# Tone Preset Models
# ============================================================================

class TonePresetResponse(BaseModel):
    id: int
    name: str
    description: str
    is_system: bool
    tenant_id: Optional[str] = None
    usage_count: Optional[int] = 0  # Number of personas/agents using this tone
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TonePresetCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=50)
    description: str = Field(..., min_length=1)


class TonePresetUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=50)
    description: Optional[str] = Field(None, min_length=1)


# ============================================================================
# Slash Command Models
# ============================================================================

class SlashCommandResponse(BaseModel):
    id: int
    tenant_id: str
    category: str
    command_name: str
    language_code: str
    pattern: str
    aliases: List[str]
    description: Optional[str]
    handler_type: str
    handler_config: Optional[dict] = {}
    is_enabled: bool
    is_system: bool  # Computed field: True if tenant_id == "_system"
    sort_order: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class SlashCommandCreate(BaseModel):
    category: str = Field(..., pattern="^(project|agent|tool|memory|system)$")
    command_name: str = Field(..., min_length=1, max_length=50)
    language_code: str = Field(default="en", pattern="^[a-z]{2}$")
    pattern: str = Field(..., min_length=1, max_length=300)
    aliases: List[str] = Field(default_factory=list)
    description: Optional[str] = None
    handler_type: str = Field(default="built-in")
    handler_config: dict = Field(default_factory=dict)
    is_enabled: bool = True
    sort_order: int = Field(default=0)


class SlashCommandUpdate(BaseModel):
    category: Optional[str] = Field(None, pattern="^(project|agent|tool|memory|system)$")
    command_name: Optional[str] = Field(None, min_length=1, max_length=50)
    language_code: Optional[str] = Field(None, pattern="^[a-z]{2}$")
    pattern: Optional[str] = Field(None, min_length=1, max_length=300)
    aliases: Optional[List[str]] = None
    description: Optional[str] = None
    handler_type: Optional[str] = None
    handler_config: Optional[dict] = None
    is_enabled: Optional[bool] = None
    sort_order: Optional[int] = None


# ============================================================================
# Project Command Pattern Models
# ============================================================================

class ProjectCommandPatternResponse(BaseModel):
    id: int
    tenant_id: str
    command_type: str
    language_code: str
    pattern: str
    response_template: str
    is_active: bool
    is_system: bool  # Computed field: True if tenant_id == "_system"
    created_at: datetime

    class Config:
        from_attributes = True


class ProjectCommandPatternCreate(BaseModel):
    command_type: str = Field(..., pattern="^(enter|exit|upload|list|help)$")
    language_code: str = Field(default="en", pattern="^[a-z]{2}$")
    pattern: str = Field(..., min_length=1, max_length=200)
    response_template: str = Field(..., min_length=1)
    is_active: bool = True


class ProjectCommandPatternUpdate(BaseModel):
    command_type: Optional[str] = Field(None, pattern="^(enter|exit|upload|list|help)$")
    language_code: Optional[str] = Field(None, pattern="^[a-z]{2}$")
    pattern: Optional[str] = Field(None, min_length=1, max_length=200)
    response_template: Optional[str] = Field(None, min_length=1)
    is_active: Optional[bool] = None


# ============================================================================
# Global Config Endpoints
# ============================================================================

@router.get("/config", response_model=PromptConfigResponse)
def get_prompt_config(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read"))
):
    """Get global system prompt configuration."""
    config = db.query(Config).filter(Config.id == 1).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    return PromptConfigResponse(
        system_prompt=config.system_prompt,
        response_template=config.response_template,
        updated_at=config.updated_at
    )


@router.put("/config", response_model=PromptConfigResponse)
def update_prompt_config(
    data: PromptConfigUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write"))
):
    """Update global system prompt configuration."""
    config = db.query(Config).filter(Config.id == 1).first()
    if not config:
        raise HTTPException(status_code=404, detail="Config not found")

    if data.system_prompt is not None:
        config.system_prompt = data.system_prompt
    if data.response_template is not None:
        config.response_template = data.response_template

    config.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(config)

    logger.info(f"Updated global prompt config by user {current_user.email}")

    return PromptConfigResponse(
        system_prompt=config.system_prompt,
        response_template=config.response_template,
        updated_at=config.updated_at
    )


# ============================================================================
# Tone Preset Endpoints
# ============================================================================

@router.get("/tone-presets", response_model=List[TonePresetResponse])
def list_tone_presets(
    search: Optional[str] = Query(None, description="Search by name or description"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List all tone presets with usage statistics."""
    query = db.query(TonePreset)

    # Apply tenant filtering - include tenant's presets AND shared (NULL tenant_id)
    query = ctx.filter_by_tenant(query, TonePreset.tenant_id)

    # Apply search filter
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                TonePreset.name.ilike(search_pattern),
                TonePreset.description.ilike(search_pattern)
            )
        )

    presets = query.order_by(TonePreset.is_system.desc(), TonePreset.name).all()

    # Calculate usage counts (personas using each tone)
    result = []
    for preset in presets:
        usage_count = db.query(func.count(Agent.id)).filter(
            Agent.tone_preset_id == preset.id
        ).scalar()

        result.append(TonePresetResponse(
            id=preset.id,
            name=preset.name,
            description=preset.description,
            is_system=preset.is_system,
            tenant_id=preset.tenant_id,
            usage_count=usage_count or 0,
            created_at=preset.created_at,
            updated_at=preset.updated_at
        ))

    return result


@router.post("/tone-presets", response_model=TonePresetResponse)
def create_tone_preset(
    data: TonePresetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new tone preset."""
    # Check for duplicate name within tenant
    query = db.query(TonePreset).filter(TonePreset.name == data.name)
    query = ctx.filter_by_tenant(query, TonePreset.tenant_id)
    existing = query.first()
    if existing:
        raise HTTPException(status_code=400, detail="Tone preset with this name already exists")

    preset = TonePreset(
        name=data.name,
        description=data.description,
        is_system=False,
        tenant_id=ctx.tenant_id
    )

    db.add(preset)
    db.commit()
    db.refresh(preset)

    logger.info(f"Created tone preset '{data.name}' by user {current_user.email}")

    return TonePresetResponse(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        is_system=preset.is_system,
        tenant_id=preset.tenant_id,
        usage_count=0,
        created_at=preset.created_at,
        updated_at=preset.updated_at
    )


@router.put("/tone-presets/{preset_id}", response_model=TonePresetResponse)
def update_tone_preset(
    preset_id: int,
    data: TonePresetUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Update a tone preset."""
    preset = db.query(TonePreset).filter(TonePreset.id == preset_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="Tone preset not found")

    # Verify user can access this preset
    if not ctx.can_access_resource(preset.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tone preset")

    # System presets cannot be modified
    if preset.is_system:
        raise HTTPException(status_code=403, detail="Cannot modify system tone preset")

    # Check for duplicate name if renaming
    if data.name and data.name != preset.name:
        query = db.query(TonePreset).filter(TonePreset.name == data.name)
        query = ctx.filter_by_tenant(query, TonePreset.tenant_id)
        existing = query.first()
        if existing:
            raise HTTPException(status_code=400, detail="Tone preset with this name already exists")

    if data.name:
        preset.name = data.name
    if data.description:
        preset.description = data.description

    preset.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(preset)

    # Get usage count
    usage_count = db.query(func.count(Agent.id)).filter(
        Agent.tone_preset_id == preset.id
    ).scalar()

    logger.info(f"Updated tone preset '{preset.name}' by user {current_user.email}")

    return TonePresetResponse(
        id=preset.id,
        name=preset.name,
        description=preset.description,
        is_system=preset.is_system,
        tenant_id=preset.tenant_id,
        usage_count=usage_count or 0,
        created_at=preset.created_at,
        updated_at=preset.updated_at
    )


@router.delete("/tone-presets/{preset_id}")
def delete_tone_preset(
    preset_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Delete a tone preset."""
    preset = db.query(TonePreset).filter(TonePreset.id == preset_id).first()
    if not preset:
        raise HTTPException(status_code=404, detail="Tone preset not found")

    # Verify user can access this preset
    if not ctx.can_access_resource(preset.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this tone preset")

    if preset.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system tone preset")

    # Check if any agents are using this preset
    usage_count = db.query(func.count(Agent.id)).filter(
        Agent.tone_preset_id == preset.id
    ).scalar()

    if usage_count > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete tone preset: {usage_count} agent(s) are using it"
        )

    db.delete(preset)
    db.commit()

    logger.info(f"Deleted tone preset '{preset.name}' by user {current_user.email}")

    return {"message": "Tone preset deleted successfully"}


# ============================================================================
# Slash Command Endpoints
# ============================================================================

@router.get("/slash-commands", response_model=List[SlashCommandResponse])
def list_slash_commands(
    search: Optional[str] = Query(None, description="Search by command name or category"),
    category: Optional[str] = Query(None, description="Filter by category"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List all slash commands."""
    query = db.query(SlashCommand)

    # Tenant filtering: include tenant's commands AND shared (_system)
    if ctx.is_global_admin:
        pass  # Global admin sees all
    else:
        query = query.filter(
            or_(
                SlashCommand.tenant_id == ctx.tenant_id,
                SlashCommand.tenant_id == "_system"
            )
        )

    # Apply filters
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                SlashCommand.command_name.ilike(search_pattern),
                SlashCommand.category.ilike(search_pattern),
                SlashCommand.description.ilike(search_pattern)
            )
        )

    if category:
        query = query.filter(SlashCommand.category == category)

    if is_active is not None:
        query = query.filter(SlashCommand.is_enabled == is_active)

    commands = query.order_by(
        SlashCommand.category,
        SlashCommand.sort_order,
        SlashCommand.command_name
    ).all()

    # Convert to response, handling JSON deserialization
    results = []
    for cmd in commands:
        # Deserialize JSON fields if they're stored as strings
        aliases = cmd.aliases
        if isinstance(aliases, str):
            try:
                aliases = json_module.loads(aliases)
            except:
                aliases = []

        handler_config = cmd.handler_config
        if handler_config is None:
            handler_config = {}
        elif isinstance(handler_config, str):
            try:
                handler_config = json_module.loads(handler_config)
            except:
                handler_config = {}

        results.append(SlashCommandResponse(
            id=cmd.id,
            tenant_id=cmd.tenant_id,
            category=cmd.category,
            command_name=cmd.command_name,
            language_code=cmd.language_code,
            pattern=cmd.pattern,
            aliases=aliases if aliases else [],
            description=cmd.description,
            handler_type=cmd.handler_type,
            handler_config=handler_config,
            is_enabled=cmd.is_enabled if cmd.is_enabled is not None else True,
            is_system=cmd.tenant_id == "_system",  # System commands have tenant_id="_system"
            sort_order=cmd.sort_order if cmd.sort_order is not None else 0,
            created_at=cmd.created_at,
            updated_at=cmd.updated_at
        ))

    return results


@router.post("/slash-commands", response_model=SlashCommandResponse)
def create_slash_command(
    data: SlashCommandCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new slash command."""
    # Validate regex pattern
    try:
        re.compile(data.pattern)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {str(e)}")

    # Check for duplicate command name + language within tenant
    existing = db.query(SlashCommand).filter(
        SlashCommand.tenant_id == ctx.tenant_id,
        SlashCommand.command_name == data.command_name,
        SlashCommand.language_code == data.language_code
    ).first()

    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Command '{data.command_name}' already exists for language '{data.language_code}'"
        )

    command = SlashCommand(
        tenant_id=ctx.tenant_id,
        category=data.category,
        command_name=data.command_name,
        language_code=data.language_code,
        pattern=data.pattern,
        aliases=data.aliases,
        description=data.description,
        handler_type=data.handler_type,
        handler_config=data.handler_config,
        is_enabled=data.is_enabled,
        sort_order=data.sort_order
    )

    db.add(command)
    db.commit()
    db.refresh(command)

    logger.info(f"Created slash command '{data.command_name}' by user {current_user.email}")

    return SlashCommandResponse(
        id=command.id,
        tenant_id=command.tenant_id,
        category=command.category,
        command_name=command.command_name,
        language_code=command.language_code,
        pattern=command.pattern,
        aliases=command.aliases if command.aliases else [],
        description=command.description,
        handler_type=command.handler_type,
        handler_config=command.handler_config if command.handler_config else {},
        is_enabled=command.is_enabled if command.is_enabled is not None else True,
        is_system=command.tenant_id == "_system",
        sort_order=command.sort_order if command.sort_order is not None else 0,
        created_at=command.created_at,
        updated_at=command.updated_at
    )


@router.put("/slash-commands/{command_id}", response_model=SlashCommandResponse)
def update_slash_command(
    command_id: int,
    data: SlashCommandUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Update a slash command."""
    command = db.query(SlashCommand).filter(SlashCommand.id == command_id).first()
    if not command:
        raise HTTPException(status_code=404, detail="Slash command not found")

    # Verify access
    if not ctx.is_global_admin and command.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this command")

    # System commands cannot be modified (tenant_id == "_system")
    if command.tenant_id == "_system":
        raise HTTPException(status_code=403, detail="Cannot modify system command")

    # Validate regex pattern if provided
    if data.pattern:
        try:
            re.compile(data.pattern)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {str(e)}")

    # Update fields
    if data.category:
        command.category = data.category
    if data.command_name:
        command.command_name = data.command_name
    if data.language_code:
        command.language_code = data.language_code
    if data.pattern:
        command.pattern = data.pattern
    if data.aliases is not None:
        command.aliases = data.aliases
    if data.description is not None:
        command.description = data.description
    if data.handler_type:
        command.handler_type = data.handler_type
    if data.handler_config is not None:
        command.handler_config = data.handler_config
    if data.is_enabled is not None:
        command.is_enabled = data.is_enabled
    if data.sort_order is not None:
        command.sort_order = data.sort_order

    command.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(command)

    logger.info(f"Updated slash command '{command.command_name}' by user {current_user.email}")

    return SlashCommandResponse(
        id=command.id,
        tenant_id=command.tenant_id,
        category=command.category,
        command_name=command.command_name,
        language_code=command.language_code,
        pattern=command.pattern,
        aliases=command.aliases if command.aliases else [],
        description=command.description,
        handler_type=command.handler_type,
        handler_config=command.handler_config if command.handler_config else {},
        is_enabled=command.is_enabled if command.is_enabled is not None else True,
        is_system=command.tenant_id == "_system",
        sort_order=command.sort_order if command.sort_order is not None else 0,
        created_at=command.created_at,
        updated_at=command.updated_at
    )


@router.delete("/slash-commands/{command_id}")
def delete_slash_command(
    command_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Delete a slash command."""
    command = db.query(SlashCommand).filter(SlashCommand.id == command_id).first()
    if not command:
        raise HTTPException(status_code=404, detail="Slash command not found")

    # Verify access
    if not ctx.is_global_admin and command.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this command")

    if command.tenant_id == "_system":
        raise HTTPException(status_code=403, detail="Cannot delete system command")

    db.delete(command)
    db.commit()

    logger.info(f"Deleted slash command '{command.command_name}' by user {current_user.email}")

    return {"message": "Slash command deleted successfully"}


# ============================================================================
# Project Command Pattern Endpoints
# ============================================================================

@router.get("/project-patterns", response_model=List[ProjectCommandPatternResponse])
def list_project_patterns(
    search: Optional[str] = Query(None, description="Search by command type or pattern"),
    command_type: Optional[str] = Query(None, description="Filter by command type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """List all project command patterns."""
    query = db.query(ProjectCommandPattern)

    # Tenant filtering: include tenant's patterns AND shared (_system)
    if ctx.is_global_admin:
        pass  # Global admin sees all
    else:
        query = query.filter(
            or_(
                ProjectCommandPattern.tenant_id == ctx.tenant_id,
                ProjectCommandPattern.tenant_id == "_system"
            )
        )

    # Apply filters
    if search:
        search_pattern = f"%{search}%"
        query = query.filter(
            or_(
                ProjectCommandPattern.command_type.ilike(search_pattern),
                ProjectCommandPattern.pattern.ilike(search_pattern)
            )
        )

    if command_type:
        query = query.filter(ProjectCommandPattern.command_type == command_type)

    if is_active is not None:
        query = query.filter(ProjectCommandPattern.is_active == is_active)

    patterns = query.order_by(
        ProjectCommandPattern.command_type,
        ProjectCommandPattern.language_code
    ).all()

    return [
        ProjectCommandPatternResponse(
            id=p.id,
            tenant_id=p.tenant_id,
            command_type=p.command_type,
            language_code=p.language_code,
            pattern=p.pattern,
            response_template=p.response_template,
            is_active=p.is_active if p.is_active is not None else True,
            is_system=p.tenant_id == "_system",
            created_at=p.created_at
        )
        for p in patterns
    ]


@router.post("/project-patterns", response_model=ProjectCommandPatternResponse)
def create_project_pattern(
    data: ProjectCommandPatternCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Create a new project command pattern."""
    # Validate regex pattern
    try:
        re.compile(data.pattern)
    except re.error as e:
        raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {str(e)}")

    pattern = ProjectCommandPattern(
        tenant_id=ctx.tenant_id,
        command_type=data.command_type,
        language_code=data.language_code,
        pattern=data.pattern,
        response_template=data.response_template,
        is_active=data.is_active
    )

    db.add(pattern)
    db.commit()
    db.refresh(pattern)

    logger.info(f"Created project pattern '{data.command_type}' ({data.language_code}) by user {current_user.email}")

    return ProjectCommandPatternResponse(
        id=pattern.id,
        tenant_id=pattern.tenant_id,
        command_type=pattern.command_type,
        language_code=pattern.language_code,
        pattern=pattern.pattern,
        response_template=pattern.response_template,
        is_active=pattern.is_active if pattern.is_active is not None else True,
        is_system=pattern.tenant_id == "_system",
        created_at=pattern.created_at
    )


@router.put("/project-patterns/{pattern_id}", response_model=ProjectCommandPatternResponse)
def update_project_pattern(
    pattern_id: int,
    data: ProjectCommandPatternUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Update a project command pattern."""
    pattern = db.query(ProjectCommandPattern).filter(ProjectCommandPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Project command pattern not found")

    # Verify access
    if not ctx.is_global_admin and pattern.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this pattern")

    # System patterns cannot be modified (tenant_id == "_system")
    if pattern.tenant_id == "_system":
        raise HTTPException(status_code=403, detail="Cannot modify system pattern")

    # Validate regex pattern if provided
    if data.pattern:
        try:
            re.compile(data.pattern)
        except re.error as e:
            raise HTTPException(status_code=400, detail=f"Invalid regex pattern: {str(e)}")

    # Update fields
    if data.command_type:
        pattern.command_type = data.command_type
    if data.language_code:
        pattern.language_code = data.language_code
    if data.pattern:
        pattern.pattern = data.pattern
    if data.response_template:
        pattern.response_template = data.response_template
    if data.is_active is not None:
        pattern.is_active = data.is_active

    pattern.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(pattern)

    logger.info(f"Updated project pattern '{pattern.command_type}' by user {current_user.email}")

    return ProjectCommandPatternResponse(
        id=pattern.id,
        tenant_id=pattern.tenant_id,
        command_type=pattern.command_type,
        language_code=pattern.language_code,
        pattern=pattern.pattern,
        response_template=pattern.response_template,
        is_active=pattern.is_active if pattern.is_active is not None else True,
        is_system=pattern.tenant_id == "_system",
        created_at=pattern.created_at
    )


@router.delete("/project-patterns/{pattern_id}")
def delete_project_pattern(
    pattern_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """Delete a project command pattern."""
    pattern = db.query(ProjectCommandPattern).filter(ProjectCommandPattern.id == pattern_id).first()
    if not pattern:
        raise HTTPException(status_code=404, detail="Project command pattern not found")

    # Verify access
    if not ctx.is_global_admin and pattern.tenant_id != ctx.tenant_id:
        raise HTTPException(status_code=403, detail="Access denied to this pattern")

    if pattern.tenant_id == "_system":
        raise HTTPException(status_code=403, detail="Cannot delete system pattern")

    db.delete(pattern)
    db.commit()

    logger.info(f"Deleted project pattern '{pattern.command_type}' by user {current_user.email}")

    return {"message": "Project command pattern deleted successfully"}
