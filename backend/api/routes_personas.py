"""
Phase 5.1: Persona Management API Routes
Phase 7.9: Added RBAC protection
Phase 7.9.2: Added tenant isolation for multi-tenancy support
Handles CRUD operations for agent personas.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime
import logging

from models import Persona, TonePreset, Agent
from models_rbac import User
from agent.ai_summary_service import AISummaryService
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/personas", tags=["personas"])

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


class PersonaCreate(BaseModel):
    name: str
    description: str
    role: Optional[str] = None
    role_description: Optional[str] = None
    tone_preset_id: Optional[int] = None
    custom_tone: Optional[str] = None
    personality_traits: Optional[str] = None
    enabled_skills: Optional[list] = []
    enabled_sandboxed_tools: Optional[list] = []
    enabled_knowledge_bases: Optional[list] = []
    guardrails: Optional[str] = None
    is_active: bool = True


class PersonaUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    role: Optional[str] = None
    role_description: Optional[str] = None
    tone_preset_id: Optional[int] = None
    custom_tone: Optional[str] = None
    personality_traits: Optional[str] = None
    enabled_skills: Optional[list] = None
    enabled_sandboxed_tools: Optional[list] = None
    enabled_knowledge_bases: Optional[list] = None
    guardrails: Optional[str] = None
    is_active: Optional[bool] = None


class PersonaResponse(BaseModel):
    id: int
    name: str
    description: str
    role: Optional[str]
    role_description: Optional[str]
    tone_preset_id: Optional[int]
    tone_preset_name: Optional[str]  # Joined from TonePreset
    custom_tone: Optional[str]
    personality_traits: Optional[str]
    enabled_skills: list
    enabled_sandboxed_tools: list
    enabled_knowledge_bases: list
    guardrails: Optional[str]
    ai_summary: Optional[str]  # AI-generated summary
    is_active: bool
    is_system: bool
    tenant_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


def to_persona_response(persona: Persona, db: Session) -> PersonaResponse:
    """Convert Persona model to response with tone preset name lookup."""
    tone_preset_name = None
    if persona.tone_preset_id:
        tone_preset = db.query(TonePreset).filter(TonePreset.id == persona.tone_preset_id).first()
        if tone_preset:
            tone_preset_name = tone_preset.name

    return PersonaResponse(
        id=persona.id,
        name=persona.name,
        description=persona.description,
        role=persona.role,
        role_description=persona.role_description,
        tone_preset_id=persona.tone_preset_id,
        tone_preset_name=tone_preset_name,
        custom_tone=persona.custom_tone,
        personality_traits=persona.personality_traits,
        enabled_skills=persona.enabled_skills or [],
        enabled_sandboxed_tools=persona.enabled_sandboxed_tools or [],
        enabled_knowledge_bases=persona.enabled_knowledge_bases or [],
        guardrails=persona.guardrails,
        ai_summary=persona.ai_summary,
        is_active=persona.is_active,
        is_system=persona.is_system,
        tenant_id=persona.tenant_id,
        created_at=persona.created_at,
        updated_at=persona.updated_at
    )


@router.get("/", response_model=List[PersonaResponse])
def get_personas(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get all personas.

    Phase 7.9.2: Returns personas for the user's tenant AND shared (NULL tenant_id) personas.
    Global admins see all personas.
    """
    query = db.query(Persona)

    # Apply tenant filtering - include tenant's personas AND shared (NULL tenant_id)
    query = ctx.filter_by_tenant(query, Persona.tenant_id)

    if active_only:
        query = query.filter(Persona.is_active == True)

    personas = query.order_by(Persona.is_system.desc(), Persona.name).all()

    return [to_persona_response(p, db) for p in personas]


@router.get("/{persona_id}", response_model=PersonaResponse)
def get_persona(
    persona_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get a specific persona by ID.

    Phase 7.9.2: Verifies user can access this persona (tenant check).
    """
    persona = db.query(Persona).filter(Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    # Verify user can access this persona
    if not ctx.can_access_resource(persona.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this persona")

    return to_persona_response(persona, db)


@router.post("/", response_model=PersonaResponse)
def create_persona(
    persona_data: PersonaCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Create a new persona.

    Phase 7.9.2: Assigns persona to user's tenant.
    """
    # Check for duplicate name within tenant (include shared personas)
    query = db.query(Persona).filter(Persona.name == persona_data.name)
    query = ctx.filter_by_tenant(query, Persona.tenant_id)
    existing = query.first()
    if existing:
        raise HTTPException(status_code=400, detail="Persona with this name already exists")

    # Validate tone configuration
    if persona_data.tone_preset_id and persona_data.custom_tone:
        raise HTTPException(status_code=400, detail="Cannot specify both tone_preset_id and custom_tone")

    tone_preset_name = None
    if persona_data.tone_preset_id:
        tone_preset = db.query(TonePreset).filter(TonePreset.id == persona_data.tone_preset_id).first()
        if not tone_preset:
            raise HTTPException(status_code=404, detail="Tone preset not found")
        tone_preset_name = tone_preset.name

    # Generate AI summary for custom personas
    ai_summary = None
    try:
        ai_service = AISummaryService()
        ai_summary = ai_service.generate_persona_summary(
            name=persona_data.name,
            description=persona_data.description,
            role=persona_data.role,
            role_description=persona_data.role_description,
            tone_preset_name=tone_preset_name,
            custom_tone=persona_data.custom_tone,
            personality_traits=persona_data.personality_traits,
            enabled_skills=persona_data.enabled_skills or [],
            guardrails=persona_data.guardrails
        )
        logger.info(f"Generated AI summary for new persona '{persona_data.name}'")
    except Exception as e:
        logger.warning(f"Failed to generate AI summary for persona '{persona_data.name}': {e}")

    persona = Persona(
        name=persona_data.name,
        description=persona_data.description,
        role=persona_data.role,
        role_description=persona_data.role_description,
        tone_preset_id=persona_data.tone_preset_id,
        custom_tone=persona_data.custom_tone,
        personality_traits=persona_data.personality_traits,
        enabled_skills=persona_data.enabled_skills or [],
        enabled_sandboxed_tools=persona_data.enabled_sandboxed_tools or [],
        enabled_knowledge_bases=persona_data.enabled_knowledge_bases or [],
        guardrails=persona_data.guardrails,
        ai_summary=ai_summary,
        is_active=persona_data.is_active,
        is_system=False,
        tenant_id=ctx.tenant_id  # Assign to user's tenant
    )

    db.add(persona)
    db.commit()
    db.refresh(persona)

    return to_persona_response(persona, db)


@router.put("/{persona_id}", response_model=PersonaResponse)
def update_persona(
    persona_id: int,
    persona_data: PersonaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Update an existing persona.

    Phase 7.9.2: Verifies user can access this persona (tenant check).
    """
    persona = db.query(Persona).filter(Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    # Verify user can access this persona
    if not ctx.can_access_resource(persona.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this persona")

    # System personas cannot be modified (only deactivated)
    if persona.is_system and persona_data.name:
        raise HTTPException(status_code=403, detail="Cannot modify system persona name")

    # Check for duplicate name if renaming (within tenant)
    if persona_data.name and persona_data.name != persona.name:
        query = db.query(Persona).filter(Persona.name == persona_data.name)
        query = ctx.filter_by_tenant(query, Persona.tenant_id)
        existing = query.first()
        if existing:
            raise HTTPException(status_code=400, detail="Persona with this name already exists")

    # Update fields
    if persona_data.name:
        persona.name = persona_data.name
    if persona_data.description:
        persona.description = persona_data.description
    if persona_data.role is not None:
        persona.role = persona_data.role
    if persona_data.role_description is not None:
        persona.role_description = persona_data.role_description
    if persona_data.tone_preset_id is not None:
        persona.tone_preset_id = persona_data.tone_preset_id
        persona.custom_tone = None  # Clear custom tone when using preset
    if persona_data.custom_tone is not None:
        persona.custom_tone = persona_data.custom_tone
        persona.tone_preset_id = None  # Clear preset when using custom
    if persona_data.personality_traits is not None:
        persona.personality_traits = persona_data.personality_traits
    if persona_data.enabled_skills is not None:
        persona.enabled_skills = persona_data.enabled_skills
    if persona_data.enabled_sandboxed_tools is not None:
        persona.enabled_sandboxed_tools = persona_data.enabled_sandboxed_tools
    if persona_data.enabled_knowledge_bases is not None:
        persona.enabled_knowledge_bases = persona_data.enabled_knowledge_bases
    if persona_data.guardrails is not None:
        persona.guardrails = persona_data.guardrails
    if persona_data.is_active is not None:
        persona.is_active = persona_data.is_active

    # Regenerate AI summary for custom personas (not system personas)
    if not persona.is_system:
        try:
            # Get tone preset name if applicable
            tone_preset_name = None
            if persona.tone_preset_id:
                tone_preset = db.query(TonePreset).filter(TonePreset.id == persona.tone_preset_id).first()
                if tone_preset:
                    tone_preset_name = tone_preset.name

            ai_service = AISummaryService()
            persona.ai_summary = ai_service.generate_persona_summary(
                name=persona.name,
                description=persona.description,
                role=persona.role,
                role_description=persona.role_description,
                tone_preset_name=tone_preset_name,
                custom_tone=persona.custom_tone,
                personality_traits=persona.personality_traits,
                enabled_skills=persona.enabled_skills or [],
                guardrails=persona.guardrails
            )
            logger.info(f"Regenerated AI summary for persona '{persona.name}'")
        except Exception as e:
            logger.warning(f"Failed to regenerate AI summary for persona '{persona.name}': {e}")

    persona.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(persona)

    return to_persona_response(persona, db)


@router.delete("/{persona_id}")
def delete_persona(
    persona_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.delete")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Delete a persona.

    Phase 7.9.2: Verifies user can access this persona (tenant check).
    """
    persona = db.query(Persona).filter(Persona.id == persona_id).first()
    if not persona:
        raise HTTPException(status_code=404, detail="Persona not found")

    # Verify user can access this persona
    if not ctx.can_access_resource(persona.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied to this persona")

    if persona.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system persona")

    # Check if any agents are using this persona
    agents_using = db.query(Agent).filter(Agent.persona_id == persona_id).count()
    if agents_using > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete persona: {agents_using} agent(s) are using it"
        )

    db.delete(persona)
    db.commit()

    return {"message": "Persona deleted successfully"}
