"""
Sentinel Security Profiles API Routes — v1.6.0 Phase C

Provides REST API endpoints for:
- Profile CRUD (create, read, update, delete, clone)
- Profile assignment at tenant/agent/skill levels
- Effective configuration preview
- Security hierarchy visualization
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_serializer, field_validator
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from models import SentinelProfile, SentinelProfileAssignment, Agent
from models_rbac import User
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from services.sentinel_profiles_service import SentinelProfilesService
from services.sentinel_detections import DETECTION_REGISTRY

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sentinel/profiles", tags=["Sentinel Security Profiles"])

# Global engine reference
_engine = None


def set_engine(engine):
    """Set the database engine (called from app.py during startup)."""
    global _engine
    _engine = engine


def get_db():
    """Database session dependency."""
    from sqlalchemy.orm import sessionmaker
    SessionLocal = sessionmaker(bind=_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class SentinelProfileResponse(BaseModel):
    """Response model for a Sentinel security profile."""
    id: int
    name: str
    slug: str
    description: Optional[str] = None
    tenant_id: Optional[str] = None
    is_system: bool
    is_default: bool

    # Global settings
    is_enabled: bool
    detection_mode: str
    aggressiveness_level: int

    # Component toggles
    enable_prompt_analysis: bool
    enable_tool_analysis: bool
    enable_shell_analysis: bool
    enable_slash_command_analysis: bool

    # LLM configuration
    llm_provider: str
    llm_model: str
    llm_max_tokens: int
    llm_temperature: float

    # Performance
    cache_ttl_seconds: int
    max_input_chars: int
    timeout_seconds: float

    # Actions
    block_on_detection: bool
    log_all_analyses: bool

    # Notifications
    enable_notifications: bool
    notification_on_block: bool
    notification_on_detect: bool
    notification_recipient: Optional[str] = None
    notification_message_template: Optional[str] = None

    # Audit
    created_by: Optional[int] = None
    updated_by: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True

    @field_serializer('created_at', 'updated_at')
    def serialize_datetimes(self, value: datetime, _info) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat() + "Z"


class DetectionConfigItem(BaseModel):
    """Individual detection type configuration with resolution source."""
    detection_type: str
    name: str
    description: str
    severity: str
    applies_to: List[str]
    enabled: bool
    custom_prompt: Optional[str] = None
    source: str  # 'explicit' | 'registry_default'


class SentinelProfileDetailResponse(SentinelProfileResponse):
    """Extended profile response with resolved detection configurations."""
    detection_overrides_raw: str = "{}"
    resolved_detections: List[DetectionConfigItem] = []


class SentinelProfileCreate(BaseModel):
    """Request model for creating a new profile."""
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9\-]+$")
    description: Optional[str] = Field(None, max_length=500)
    is_default: bool = False

    # Global settings
    is_enabled: bool = True
    detection_mode: str = Field(default="block", pattern=r"^(block|detect_only|off)$")
    aggressiveness_level: int = Field(default=1, ge=0, le=3)

    # Component toggles
    enable_prompt_analysis: bool = True
    enable_tool_analysis: bool = True
    enable_shell_analysis: bool = True
    enable_slash_command_analysis: bool = True

    # LLM configuration
    llm_provider: str = Field(default="gemini", max_length=20)
    llm_model: str = Field(default="gemini-2.5-flash-lite", max_length=100)
    llm_max_tokens: int = Field(default=256, ge=64, le=1024)
    llm_temperature: float = Field(default=0.1, ge=0.0, le=1.0)

    # Performance
    cache_ttl_seconds: int = Field(default=300, ge=0, le=3600)
    max_input_chars: int = Field(default=5000, ge=100, le=10000)
    timeout_seconds: float = Field(default=5.0, ge=1.0, le=30.0)

    # Actions
    block_on_detection: bool = True
    log_all_analyses: bool = False

    # Notifications
    enable_notifications: bool = True
    notification_on_block: bool = True
    notification_on_detect: bool = False
    notification_recipient: Optional[str] = Field(None, max_length=100)
    notification_message_template: Optional[str] = Field(None, max_length=2000)

    # Detection overrides (JSON string)
    detection_overrides: str = Field(default="{}")

    @field_validator('detection_overrides')
    @classmethod
    def validate_detection_overrides(cls, v: str) -> str:
        try:
            data = json.loads(v)
            if not isinstance(data, dict):
                raise ValueError("detection_overrides must be a JSON object")
            return v
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")


class SentinelProfileUpdate(BaseModel):
    """Request model for updating a profile. All fields optional."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    slug: Optional[str] = Field(None, min_length=1, max_length=100, pattern=r"^[a-z0-9\-]+$")
    description: Optional[str] = Field(None, max_length=500)
    is_default: Optional[bool] = None

    # Global settings
    is_enabled: Optional[bool] = None
    detection_mode: Optional[str] = Field(None, pattern=r"^(block|detect_only|off)$")
    aggressiveness_level: Optional[int] = Field(None, ge=0, le=3)

    # Component toggles
    enable_prompt_analysis: Optional[bool] = None
    enable_tool_analysis: Optional[bool] = None
    enable_shell_analysis: Optional[bool] = None
    enable_slash_command_analysis: Optional[bool] = None

    # LLM configuration
    llm_provider: Optional[str] = Field(None, max_length=20)
    llm_model: Optional[str] = Field(None, max_length=100)
    llm_max_tokens: Optional[int] = Field(None, ge=64, le=1024)
    llm_temperature: Optional[float] = Field(None, ge=0.0, le=1.0)

    # Performance
    cache_ttl_seconds: Optional[int] = Field(None, ge=0, le=3600)
    max_input_chars: Optional[int] = Field(None, ge=100, le=10000)
    timeout_seconds: Optional[float] = Field(None, ge=1.0, le=30.0)

    # Actions
    block_on_detection: Optional[bool] = None
    log_all_analyses: Optional[bool] = None

    # Notifications
    enable_notifications: Optional[bool] = None
    notification_on_block: Optional[bool] = None
    notification_on_detect: Optional[bool] = None
    notification_recipient: Optional[str] = Field(None, max_length=100)
    notification_message_template: Optional[str] = Field(None, max_length=2000)

    # Detection overrides (JSON string)
    detection_overrides: Optional[str] = None

    @field_validator('detection_overrides')
    @classmethod
    def validate_detection_overrides(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        try:
            data = json.loads(v)
            if not isinstance(data, dict):
                raise ValueError("detection_overrides must be a JSON object")
            return v
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON: {e}")


class SentinelProfileCloneRequest(BaseModel):
    """Request model for cloning a profile."""
    name: str = Field(..., min_length=1, max_length=100)
    slug: str = Field(..., min_length=1, max_length=100, pattern=r"^[a-z0-9\-]+$")


class SentinelProfileAssignmentResponse(BaseModel):
    """Response model for a profile assignment."""
    id: int
    tenant_id: str
    agent_id: Optional[int] = None
    skill_type: Optional[str] = None
    profile_id: int
    assigned_by: Optional[int] = None
    assigned_at: Optional[datetime] = None

    # Enriched profile info
    profile_name: Optional[str] = None
    profile_slug: Optional[str] = None

    class Config:
        from_attributes = True

    @field_serializer('assigned_at')
    def serialize_datetime(self, value: datetime, _info) -> Optional[str]:
        if value is None:
            return None
        return value.isoformat() + "Z"


class SentinelProfileAssignRequest(BaseModel):
    """Request model for assigning a profile to a scope."""
    profile_id: int
    agent_id: Optional[int] = None
    skill_type: Optional[str] = Field(None, max_length=50)


class DetectionEffectiveItem(BaseModel):
    """Detection configuration with source tracking."""
    detection_type: str
    name: str
    enabled: bool
    custom_prompt: Optional[str] = None
    source: str  # 'explicit' | 'registry_default'


class SentinelEffectiveConfigResponse(BaseModel):
    """Response model for effective configuration preview."""
    profile_id: int
    profile_name: str
    profile_source: str

    # Global settings
    is_enabled: bool
    detection_mode: str
    aggressiveness_level: int

    # Component toggles
    enable_prompt_analysis: bool
    enable_tool_analysis: bool
    enable_shell_analysis: bool
    enable_slash_command_analysis: bool

    # LLM
    llm_provider: str
    llm_model: str
    llm_max_tokens: int
    llm_temperature: float

    # Performance
    cache_ttl_seconds: int
    max_input_chars: int
    timeout_seconds: float

    # Actions
    block_on_detection: bool
    log_all_analyses: bool

    # Notifications
    enable_notifications: bool
    notification_on_block: bool
    notification_on_detect: bool
    notification_recipient: Optional[str] = None
    notification_message_template: Optional[str] = None

    # Resolved detections
    detections: List[DetectionEffectiveItem]


# =============================================================================
# Helper Functions
# =============================================================================

def _resolve_detections(profile: SentinelProfile) -> List[DetectionConfigItem]:
    """Resolve detection configurations from registry + profile overrides."""
    try:
        overrides = json.loads(profile.detection_overrides or "{}")
    except (json.JSONDecodeError, TypeError):
        overrides = {}

    resolved = []
    for det_type, registry_info in DETECTION_REGISTRY.items():
        override = overrides.get(det_type, {})
        has_explicit = "enabled" in override or ("custom_prompt" in override and override["custom_prompt"] is not None)

        resolved.append(DetectionConfigItem(
            detection_type=det_type,
            name=registry_info["name"],
            description=registry_info["description"],
            severity=registry_info["severity"],
            applies_to=registry_info.get("applies_to", []),
            enabled=override.get("enabled", registry_info.get("default_enabled", True)),
            custom_prompt=override.get("custom_prompt"),
            source="explicit" if has_explicit else "registry_default",
        ))

    return resolved


def _build_assignment_response(
    assignment: SentinelProfileAssignment,
    service: SentinelProfilesService,
) -> SentinelProfileAssignmentResponse:
    """Build enriched assignment response with profile info."""
    profile = service.get_profile(assignment.profile_id)
    return SentinelProfileAssignmentResponse(
        id=assignment.id,
        tenant_id=assignment.tenant_id,
        agent_id=assignment.agent_id,
        skill_type=assignment.skill_type,
        profile_id=assignment.profile_id,
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at,
        profile_name=profile.name if profile else None,
        profile_slug=profile.slug if profile else None,
    )


# =============================================================================
# Endpoints — Static paths FIRST (before /{profile_id} path parameter)
# =============================================================================

# --- Assignment endpoints (static paths) ---

@router.get("/assignments", response_model=List[SentinelProfileAssignmentResponse])
async def list_assignments(
    agent_id: Optional[int] = Query(None, description="Filter by agent ID"),
    skill_type: Optional[str] = Query(None, description="Filter by skill type"),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List profile assignments for this tenant."""
    service = SentinelProfilesService(db, ctx.tenant_id)
    assignments = service.list_assignments(agent_id=agent_id, skill_type=skill_type)
    return [_build_assignment_response(a, service) for a in assignments]


@router.post("/assign", response_model=SentinelProfileAssignmentResponse)
async def assign_profile(
    data: SentinelProfileAssignRequest,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Assign a profile to a scope (tenant/agent/skill).

    UPSERT: replaces existing assignment at the same scope level.
    """
    service = SentinelProfilesService(db, ctx.tenant_id)

    # Validate profile is accessible before assigning
    profile = service.get_profile(data.profile_id)
    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    # Validate agent belongs to tenant
    if data.agent_id:
        agent = db.query(Agent).filter(Agent.id == data.agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        if not ctx.can_access_resource(agent.tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to this agent")

    try:
        assignment = service.assign_profile(
            profile_id=data.profile_id,
            agent_id=data.agent_id,
            skill_type=data.skill_type,
            assigned_by=current_user.id,
        )
        return _build_assignment_response(assignment, service)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/assignments/{assignment_id}")
async def remove_assignment(
    assignment_id: int,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Remove a profile assignment. The scope falls back to the parent level."""
    service = SentinelProfilesService(db, ctx.tenant_id)

    if not service.remove_assignment(assignment_id):
        raise HTTPException(status_code=404, detail="Assignment not found")

    return {"deleted": True, "assignment_id": assignment_id}


# --- Effective config and hierarchy (static paths) ---

@router.get("/effective", response_model=SentinelEffectiveConfigResponse)
async def get_effective_config(
    agent_id: Optional[int] = Query(None, description="Agent ID for resolution"),
    skill_type: Optional[str] = Query(None, description="Skill type for resolution"),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Preview the effective security configuration for a given scope.

    Shows which profile applies and the fully resolved detection settings.
    """
    service = SentinelProfilesService(db, ctx.tenant_id)

    # Validate agent access
    if agent_id:
        agent = db.query(Agent).filter(Agent.id == agent_id).first()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        if not ctx.can_access_resource(agent.tenant_id):
            raise HTTPException(status_code=403, detail="Access denied to this agent")

    effective = service.get_effective_config(agent_id=agent_id, skill_type=skill_type)

    if not effective:
        raise HTTPException(
            status_code=404,
            detail="No profile found. Configure a tenant-level profile or ensure a system default exists.",
        )

    # Build detection items with source tracking
    detections = []
    for det_type, det_config in effective.detection_config.items():
        registry_info = DETECTION_REGISTRY.get(det_type, {})
        registry_default = registry_info.get("default_enabled", True)
        is_explicit = det_config.get("enabled") != registry_default or det_config.get("custom_prompt") is not None

        detections.append(DetectionEffectiveItem(
            detection_type=det_type,
            name=registry_info.get("name", det_type),
            enabled=det_config.get("enabled", True),
            custom_prompt=det_config.get("custom_prompt"),
            source="explicit" if is_explicit else "registry_default",
        ))

    return SentinelEffectiveConfigResponse(
        profile_id=effective.profile_id,
        profile_name=effective.profile_name,
        profile_source=effective.profile_source,
        is_enabled=effective.is_enabled,
        detection_mode=effective.detection_mode,
        aggressiveness_level=effective.aggressiveness_level,
        enable_prompt_analysis=effective.enable_prompt_analysis,
        enable_tool_analysis=effective.enable_tool_analysis,
        enable_shell_analysis=effective.enable_shell_analysis,
        enable_slash_command_analysis=effective.enable_slash_command_analysis,
        llm_provider=effective.llm_provider,
        llm_model=effective.llm_model,
        llm_max_tokens=effective.llm_max_tokens,
        llm_temperature=effective.llm_temperature,
        cache_ttl_seconds=effective.cache_ttl_seconds,
        max_input_chars=effective.max_input_chars,
        timeout_seconds=effective.timeout_seconds,
        block_on_detection=effective.block_on_detection,
        log_all_analyses=effective.log_all_analyses,
        enable_notifications=effective.enable_notifications,
        notification_on_block=effective.notification_on_block,
        notification_on_detect=effective.notification_on_detect,
        notification_recipient=effective.notification_recipient,
        notification_message_template=effective.notification_message_template,
        detections=detections,
    )


@router.get("/hierarchy")
async def get_hierarchy(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Get the full security hierarchy tree for graph visualization.

    Returns tenant -> agents -> skills with assigned and effective profiles.
    """
    service = SentinelProfilesService(db, ctx.tenant_id)
    return service.get_hierarchy()


# --- Profile CRUD (parameterized paths LAST) ---

@router.get("", response_model=List[SentinelProfileResponse])
async def list_profiles(
    include_system: bool = Query(True, description="Include system built-in profiles"),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """List all security profiles accessible to this tenant."""
    service = SentinelProfilesService(db, ctx.tenant_id)
    return service.list_profiles(include_system=include_system)


@router.post("", response_model=SentinelProfileResponse, status_code=201)
async def create_profile(
    data: SentinelProfileCreate,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Create a new tenant-scoped security profile."""
    service = SentinelProfilesService(db, ctx.tenant_id)

    try:
        profile = service.create_profile(
            data=data.model_dump(exclude_unset=False),
            created_by=current_user.id,
        )
        return profile
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Profile with slug '{data.slug}' already exists for this tenant",
        )


@router.get("/{profile_id}", response_model=SentinelProfileDetailResponse)
async def get_profile(
    profile_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get a specific profile with resolved detection configurations."""
    service = SentinelProfilesService(db, ctx.tenant_id)
    profile = service.get_profile(profile_id)

    if not profile:
        raise HTTPException(status_code=404, detail="Profile not found")

    resolved_detections = _resolve_detections(profile)

    return SentinelProfileDetailResponse(
        id=profile.id,
        name=profile.name,
        slug=profile.slug,
        description=profile.description,
        tenant_id=profile.tenant_id,
        is_system=profile.is_system,
        is_default=profile.is_default,
        is_enabled=profile.is_enabled,
        detection_mode=profile.detection_mode,
        aggressiveness_level=profile.aggressiveness_level,
        enable_prompt_analysis=profile.enable_prompt_analysis,
        enable_tool_analysis=profile.enable_tool_analysis,
        enable_shell_analysis=profile.enable_shell_analysis,
        enable_slash_command_analysis=profile.enable_slash_command_analysis,
        llm_provider=profile.llm_provider,
        llm_model=profile.llm_model,
        llm_max_tokens=profile.llm_max_tokens,
        llm_temperature=profile.llm_temperature,
        cache_ttl_seconds=profile.cache_ttl_seconds,
        max_input_chars=profile.max_input_chars,
        timeout_seconds=profile.timeout_seconds,
        block_on_detection=profile.block_on_detection,
        log_all_analyses=profile.log_all_analyses,
        enable_notifications=profile.enable_notifications,
        notification_on_block=profile.notification_on_block,
        notification_on_detect=profile.notification_on_detect,
        notification_recipient=profile.notification_recipient,
        notification_message_template=profile.notification_message_template,
        created_by=profile.created_by,
        updated_by=profile.updated_by,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        detection_overrides_raw=profile.detection_overrides or "{}",
        resolved_detections=resolved_detections,
    )


@router.put("/{profile_id}", response_model=SentinelProfileResponse)
async def update_profile(
    profile_id: int,
    data: SentinelProfileUpdate,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Update an existing profile. Cannot modify system profiles."""
    service = SentinelProfilesService(db, ctx.tenant_id)

    existing = service.get_profile(profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Profile not found")

    if existing.is_system:
        raise HTTPException(
            status_code=403,
            detail="Cannot modify system profiles. Clone it to create a custom version.",
        )

    try:
        profile = service.update_profile(
            profile_id=profile_id,
            data=data.model_dump(exclude_unset=True),
            updated_by=current_user.id,
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Profile not found")
        return profile
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Profile with slug '{data.slug}' already exists for this tenant",
        )


@router.delete("/{profile_id}")
async def delete_profile(
    profile_id: int,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Delete a profile. Cannot delete system profiles or profiles with active assignments."""
    service = SentinelProfilesService(db, ctx.tenant_id)

    existing = service.get_profile(profile_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Profile not found")

    if existing.is_system:
        raise HTTPException(status_code=403, detail="Cannot delete system profiles")

    result = service.delete_profile(profile_id)

    if not result["deleted"]:
        if result.get("error") == "Profile has active assignments":
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Cannot delete profile with active assignments",
                    "assignment_count": result.get("assignment_count", 0),
                    "assignments": result.get("assignments", []),
                },
            )
        raise HTTPException(status_code=400, detail=result.get("error", "Delete failed"))

    return {"deleted": True, "profile_id": profile_id}


@router.post("/{profile_id}/clone", response_model=SentinelProfileResponse, status_code=201)
async def clone_profile(
    profile_id: int,
    data: SentinelProfileCloneRequest,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Clone an existing profile with a new name and slug."""
    service = SentinelProfilesService(db, ctx.tenant_id)

    try:
        profile = service.clone_profile(
            profile_id=profile_id,
            new_name=data.name,
            new_slug=data.slug,
            created_by=current_user.id,
        )
        if not profile:
            raise HTTPException(status_code=404, detail="Source profile not found")
        return profile
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail=f"Profile with slug '{data.slug}' already exists for this tenant",
        )
