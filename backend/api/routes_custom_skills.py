"""
Phase 22/23: Custom Skills — CRUD + Script Deployment API Routes

Provides endpoints for creating, reading, updating, and deleting
tenant-created custom skills. Includes Sentinel scan integration
for instruction-based skills, version tracking for audit/rollback,
and Phase 23 additions: deploy, scan, test, and execution history.
"""

import re
import logging
from datetime import datetime
from typing import Optional, List, Any
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from models import CustomSkill, CustomSkillVersion, AgentCustomSkill, CustomSkillExecution
from models_rbac import User
from auth_dependencies import (
    TenantContext,
    get_tenant_context,
    require_permission,
)
from services.audit_service import log_tenant_event, TenantAuditActions

logger = logging.getLogger(__name__)

router = APIRouter()

# ==================== Resource Quotas (Phase 23) ====================

MAX_INSTRUCTION_CHARS = 8000
MAX_SCRIPT_SIZE_BYTES = 256 * 1024  # 256 KB
MAX_SKILLS_PER_TENANT = 50

# Global engine reference
_engine = None


def set_engine(engine):
    """Set the global engine reference"""
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


# ==================== Pydantic Schemas ====================

class CustomSkillCreate(BaseModel):
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    skill_type_variant: str = Field(default="instruction")
    execution_mode: str = Field(default="tool")
    instructions_md: Optional[str] = None
    script_content: Optional[str] = None
    script_entrypoint: Optional[str] = None
    script_language: Optional[str] = None  # python|bash|nodejs
    trigger_mode: str = Field(default="llm_decided")
    trigger_keywords: List[str] = Field(default_factory=list)
    input_schema: Optional[dict] = Field(default_factory=dict)
    config_schema: Optional[list] = Field(default_factory=list)
    timeout_seconds: int = Field(default=30)
    priority: int = Field(default=50)
    sentinel_profile_id: Optional[int] = None
    mcp_server_id: Optional[int] = None
    mcp_tool_name: Optional[str] = None


class CustomSkillUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    icon: Optional[str] = None
    skill_type_variant: Optional[str] = None
    execution_mode: Optional[str] = None
    instructions_md: Optional[str] = None
    script_content: Optional[str] = None
    script_entrypoint: Optional[str] = None
    script_language: Optional[str] = None
    trigger_mode: Optional[str] = None
    trigger_keywords: Optional[List[str]] = None
    input_schema: Optional[dict] = None
    config_schema: Optional[list] = None
    timeout_seconds: Optional[int] = None
    priority: Optional[int] = None
    is_enabled: Optional[bool] = None
    sentinel_profile_id: Optional[int] = None
    mcp_server_id: Optional[int] = None
    mcp_tool_name: Optional[str] = None


class CustomSkillTestRequest(BaseModel):
    """Request body for testing a custom skill."""
    message: Optional[str] = None
    arguments: Optional[dict] = Field(default_factory=dict)


class CustomSkillExecutionResponse(BaseModel):
    """Response for a skill execution record."""
    id: int
    tenant_id: str
    agent_id: Optional[int] = None
    custom_skill_id: Optional[int] = None
    skill_name: Optional[str] = None
    input_json: Optional[dict] = None
    output: Optional[str] = None
    error: Optional[str] = None
    status: str
    execution_time_ms: Optional[int] = None
    sentinel_result: Optional[dict] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


class CustomSkillResponse(BaseModel):
    id: int
    tenant_id: str
    source: str
    slug: str
    name: str
    description: Optional[str] = None
    icon: Optional[str] = None
    skill_type_variant: str
    execution_mode: str
    instructions_md: Optional[str] = None
    script_content: Optional[str] = None
    script_entrypoint: Optional[str] = None
    script_language: Optional[str] = None
    script_content_hash: Optional[str] = None
    input_schema: Optional[dict] = None
    output_schema: Optional[dict] = None
    config_schema: Optional[list] = None
    trigger_mode: str
    trigger_keywords: Optional[List[str]] = None
    priority: int
    sentinel_profile_id: Optional[int] = None
    timeout_seconds: int
    is_enabled: bool
    scan_status: str
    last_scan_result: Optional[dict] = None
    version: str
    mcp_server_id: Optional[int] = None
    mcp_tool_name: Optional[str] = None
    created_by: Optional[int] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    class Config:
        from_attributes = True


class CustomSkillVersionResponse(BaseModel):
    id: int
    custom_skill_id: int
    version: str
    snapshot_json: dict
    changed_by: Optional[int] = None
    changed_at: Optional[str] = None

    class Config:
        from_attributes = True


# ==================== Helpers ====================

def _slugify(name: str) -> str:
    """Generate a URL-safe slug from a skill name."""
    slug = name.lower().strip()
    slug = re.sub(r'[^a-z0-9\s-]', '', slug)
    slug = re.sub(r'[\s]+', '-', slug)
    slug = re.sub(r'-+', '-', slug)
    return slug.strip('-')


def _to_response(skill: CustomSkill) -> CustomSkillResponse:
    """Convert a CustomSkill model to a response schema."""
    return CustomSkillResponse(
        id=skill.id,
        tenant_id=skill.tenant_id,
        source=skill.source,
        slug=skill.slug,
        name=skill.name,
        description=skill.description,
        icon=skill.icon,
        skill_type_variant=skill.skill_type_variant,
        execution_mode=skill.execution_mode,
        instructions_md=skill.instructions_md,
        script_content=skill.script_content,
        script_entrypoint=skill.script_entrypoint,
        script_language=skill.script_language,
        script_content_hash=skill.script_content_hash,
        input_schema=skill.input_schema,
        output_schema=skill.output_schema,
        config_schema=skill.config_schema,
        trigger_mode=skill.trigger_mode,
        trigger_keywords=skill.trigger_keywords,
        priority=skill.priority,
        sentinel_profile_id=skill.sentinel_profile_id,
        timeout_seconds=skill.timeout_seconds,
        is_enabled=skill.is_enabled,
        scan_status=skill.scan_status,
        last_scan_result=skill.last_scan_result,
        version=skill.version,
        mcp_server_id=skill.mcp_server_id,
        mcp_tool_name=skill.mcp_tool_name,
        created_by=skill.created_by,
        created_at=skill.created_at.isoformat() if skill.created_at else None,
        updated_at=skill.updated_at.isoformat() if skill.updated_at else None,
    )


def _to_version_response(v: CustomSkillVersion) -> CustomSkillVersionResponse:
    """Convert a CustomSkillVersion model to a response schema."""
    return CustomSkillVersionResponse(
        id=v.id,
        custom_skill_id=v.custom_skill_id,
        version=v.version,
        snapshot_json=v.snapshot_json,
        changed_by=v.changed_by,
        changed_at=v.changed_at.isoformat() if v.changed_at else None,
    )


async def _scan_instructions(instructions: str, db, tenant_id: str = None, sentinel_profile_id: int = None) -> dict:
    """Run Sentinel scan on skill instruction content using skill-optimized analysis. Fail-open if unavailable."""
    try:
        from services.sentinel_service import SentinelService
        sentinel = SentinelService(db, tenant_id=tenant_id)

        # Resolve effective skill-scan profile for metadata
        config = sentinel._resolve_skill_scan_config(sentinel_profile_id)
        profile_meta = {
            "profile_name": config.profile_name,
            "profile_id": config.profile_id if config.profile_id != -1 else None,
            "profile_source": config.profile_source,
            "detection_mode": config.detection_mode,
            "scanned_at": datetime.utcnow().isoformat() + "Z",
        }

        result = await sentinel.analyze_skill_instructions(
            instructions=instructions,
            skill_profile_id=sentinel_profile_id,
        )
        if hasattr(result, 'is_threat_detected') and result.is_threat_detected:
            return {
                "scan_status": "rejected",
                "last_scan_result": {
                    "reason": getattr(result, 'threat_reason', 'Unknown'),
                    "detection_type": getattr(result, 'detection_type', None),
                    "threat_score": getattr(result, 'threat_score', None),
                    **profile_meta,
                },
            }
        return {"scan_status": "clean", "last_scan_result": {**profile_meta}}
    except Exception as e:
        logger.warning(f"Sentinel scan failed, defaulting to clean: {e}")
        return {"scan_status": "clean", "last_scan_result": None}


def _snapshot_skill(skill: CustomSkill) -> dict:
    """Create a JSON snapshot of the current skill state for versioning."""
    return {
        "name": skill.name,
        "description": skill.description,
        "icon": skill.icon,
        "skill_type_variant": skill.skill_type_variant,
        "execution_mode": skill.execution_mode,
        "instructions_md": skill.instructions_md,
        "script_content": skill.script_content,
        "script_entrypoint": skill.script_entrypoint,
        "script_language": skill.script_language,
        "input_schema": skill.input_schema,
        "output_schema": skill.output_schema,
        "config_schema": skill.config_schema,
        "trigger_mode": skill.trigger_mode,
        "trigger_keywords": skill.trigger_keywords,
        "priority": skill.priority,
        "timeout_seconds": skill.timeout_seconds,
        "version": skill.version,
        "mcp_server_id": skill.mcp_server_id,
        "mcp_tool_name": skill.mcp_tool_name,
    }


# ==================== Endpoints ====================

@router.get("/custom-skills", response_model=List[CustomSkillResponse])
async def list_custom_skills(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List all custom skills for the current tenant."""
    query = db.query(CustomSkill)
    query = ctx.filter_by_tenant(query, CustomSkill.tenant_id)
    skills = query.order_by(CustomSkill.name).all()
    return [_to_response(s) for s in skills]


@router.post("/custom-skills", response_model=CustomSkillResponse, status_code=status.HTTP_201_CREATED)
async def create_custom_skill(
    payload: CustomSkillCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.create")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Create a new custom skill with optional Sentinel scan."""
    tenant_id = ctx.tenant_id

    # Resource quota: max skills per tenant
    skill_count = db.query(CustomSkill).filter(
        CustomSkill.tenant_id == tenant_id
    ).count()
    if skill_count >= MAX_SKILLS_PER_TENANT:
        raise HTTPException(
            status_code=400,
            detail=f"Tenant skill limit reached ({MAX_SKILLS_PER_TENANT}). Delete unused skills first.",
        )

    # Resource quota: instruction size
    if payload.instructions_md and len(payload.instructions_md) > MAX_INSTRUCTION_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Instructions exceed maximum length ({MAX_INSTRUCTION_CHARS} characters).",
        )

    # Resource quota: script size
    if payload.script_content and len(payload.script_content.encode('utf-8')) > MAX_SCRIPT_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Script content exceeds maximum size ({MAX_SCRIPT_SIZE_BYTES // 1024} KB).",
        )

    # Generate slug
    slug = _slugify(payload.name)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid skill name (cannot generate slug)")

    # Check uniqueness
    existing = db.query(CustomSkill).filter(
        CustomSkill.tenant_id == tenant_id,
        CustomSkill.slug == slug,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"A skill with slug '{slug}' already exists")

    # Validate skill_type_variant
    if payload.skill_type_variant not in ('instruction', 'script', 'mcp_server'):
        raise HTTPException(status_code=400, detail="skill_type_variant must be one of: instruction, script, mcp_server")

    # Validate execution_mode
    if payload.execution_mode not in ('tool', 'hybrid', 'passive'):
        raise HTTPException(status_code=400, detail="execution_mode must be one of: tool, hybrid, passive")

    # Validate trigger_mode
    if payload.trigger_mode not in ('keyword', 'always_on', 'llm_decided'):
        raise HTTPException(status_code=400, detail="trigger_mode must be one of: keyword, always_on, llm_decided")

    # Validate script_language if provided
    if payload.script_language and payload.script_language not in ('python', 'bash', 'nodejs'):
        raise HTTPException(status_code=400, detail="script_language must be one of: python, bash, nodejs")

    # Validate MCP server for mcp_server type
    if payload.skill_type_variant == 'mcp_server':
        if not payload.mcp_server_id:
            raise HTTPException(status_code=400, detail="mcp_server_id is required for mcp_server skill type")
        from models import MCPServerConfig, MCPDiscoveredTool
        mcp_server = db.query(MCPServerConfig).filter(
            MCPServerConfig.id == payload.mcp_server_id,
            MCPServerConfig.tenant_id == tenant_id,
        ).first()
        if not mcp_server:
            raise HTTPException(status_code=404, detail="MCP server not found or does not belong to this tenant")
        # If tool name provided, auto-populate input_schema from discovered tool
        if payload.mcp_tool_name:
            tool = db.query(MCPDiscoveredTool).filter(
                MCPDiscoveredTool.server_id == payload.mcp_server_id,
                MCPDiscoveredTool.tool_name == payload.mcp_tool_name,
            ).first()
            if tool and tool.input_schema and not payload.input_schema:
                payload.input_schema = tool.input_schema

    # Create skill
    skill = CustomSkill(
        tenant_id=tenant_id,
        source='tenant',
        slug=slug,
        name=payload.name,
        description=payload.description,
        icon=payload.icon,
        skill_type_variant=payload.skill_type_variant,
        execution_mode=payload.execution_mode,
        instructions_md=payload.instructions_md,
        script_content=payload.script_content,
        script_entrypoint=payload.script_entrypoint,
        script_language=payload.script_language,
        input_schema=payload.input_schema or {},
        config_schema=payload.config_schema or [],
        trigger_mode=payload.trigger_mode,
        trigger_keywords=payload.trigger_keywords or [],
        priority=payload.priority,
        sentinel_profile_id=payload.sentinel_profile_id,
        timeout_seconds=payload.timeout_seconds,
        mcp_server_id=payload.mcp_server_id,
        mcp_tool_name=payload.mcp_tool_name,
        is_enabled=True,
        scan_status='pending',
        version='1.0.0',
        created_by=current_user.id,
    )

    db.add(skill)
    db.flush()

    # Run Sentinel scan on instructions if provided
    if payload.instructions_md:
        scan_result = await _scan_instructions(payload.instructions_md, db, tenant_id=ctx.tenant_id, sentinel_profile_id=payload.sentinel_profile_id)
        skill.scan_status = scan_result["scan_status"]
        skill.last_scan_result = scan_result.get("last_scan_result")
    else:
        skill.scan_status = 'clean'

    # Security H-1: Scan script skills for network imports (non-blocking advisory)
    if payload.skill_type_variant == 'script' and payload.script_content:
        from services.shell_security_service import ShellSecurityService
        network_warnings = ShellSecurityService.scan_for_network_imports(payload.script_content)
        if network_warnings:
            existing_scan = skill.last_scan_result or {}
            existing_scan["network_import_warnings"] = network_warnings
            skill.last_scan_result = existing_scan
            logger.info(f"Network import warnings for skill '{skill.name}': {network_warnings}")

    db.commit()
    db.refresh(skill)

    log_tenant_event(db, ctx.tenant_id, current_user.id, TenantAuditActions.SKILL_CREATE, "skill", str(skill.id), {"name": skill.name}, request)
    # Audit log auto-scan result on creation
    if skill.scan_status and skill.scan_status != 'pending':
        scan_severity = "warning" if skill.scan_status == "rejected" else "info"
        log_tenant_event(db, ctx.tenant_id, current_user.id,
            TenantAuditActions.SECURITY_SKILL_SCAN, "skill", str(skill.id),
            {"name": skill.name, "scan_status": skill.scan_status, "trigger": "auto_create"}, request, severity=scan_severity)
    logger.info(f"Custom skill created: {skill.name} (slug={skill.slug}, tenant={tenant_id})")
    return _to_response(skill)


@router.get("/custom-skills/{skill_id}", response_model=CustomSkillResponse)
async def get_custom_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Get a single custom skill by ID."""
    query = db.query(CustomSkill).filter(CustomSkill.id == skill_id)
    query = ctx.filter_by_tenant(query, CustomSkill.tenant_id)
    skill = query.first()

    if not skill:
        raise HTTPException(status_code=404, detail="Custom skill not found")

    return _to_response(skill)


@router.put("/custom-skills/{skill_id}", response_model=CustomSkillResponse)
async def update_custom_skill(
    skill_id: int,
    payload: CustomSkillUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.create")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Update a custom skill. Creates a version snapshot before applying changes."""
    # Resource quota: instruction size
    if payload.instructions_md and len(payload.instructions_md) > MAX_INSTRUCTION_CHARS:
        raise HTTPException(
            status_code=400,
            detail=f"Instructions exceed maximum length ({MAX_INSTRUCTION_CHARS} characters).",
        )

    # Resource quota: script size
    if payload.script_content and len(payload.script_content.encode('utf-8')) > MAX_SCRIPT_SIZE_BYTES:
        raise HTTPException(
            status_code=400,
            detail=f"Script content exceeds maximum size ({MAX_SCRIPT_SIZE_BYTES // 1024} KB).",
        )

    # Validate script_language if provided
    if payload.script_language and payload.script_language not in ('python', 'bash', 'nodejs'):
        raise HTTPException(status_code=400, detail="script_language must be one of: python, bash, nodejs")

    query = db.query(CustomSkill).filter(CustomSkill.id == skill_id)
    query = ctx.filter_by_tenant(query, CustomSkill.tenant_id)
    skill = query.first()

    if not skill:
        raise HTTPException(status_code=404, detail="Custom skill not found")

    # Create version snapshot before updating
    version_entry = CustomSkillVersion(
        custom_skill_id=skill.id,
        version=skill.version,
        snapshot_json=_snapshot_skill(skill),
        changed_by=current_user.id,
    )
    db.add(version_entry)

    # Track if instructions or script changed for re-scan
    instructions_changed = False
    script_changed = False

    # Apply updates
    update_data = payload.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        if field == 'instructions_md' and value != skill.instructions_md:
            instructions_changed = True
        if field == 'script_content' and value != skill.script_content:
            script_changed = True
        setattr(skill, field, value)

    # Bump version
    parts = skill.version.split('.')
    try:
        parts[-1] = str(int(parts[-1]) + 1)
        skill.version = '.'.join(parts)
    except (ValueError, IndexError):
        skill.version = '1.0.1'

    skill.updated_at = datetime.utcnow()

    # Re-scan if instructions changed
    if instructions_changed and skill.instructions_md:
        scan_result = await _scan_instructions(skill.instructions_md, db, tenant_id=ctx.tenant_id, sentinel_profile_id=skill.sentinel_profile_id)
        skill.scan_status = scan_result["scan_status"]
        skill.last_scan_result = scan_result.get("last_scan_result")

    # Security H-1: Re-scan script for network imports if script_content changed (non-blocking advisory)
    if script_changed and skill.script_content and skill.skill_type_variant == 'script':
        from services.shell_security_service import ShellSecurityService
        network_warnings = ShellSecurityService.scan_for_network_imports(skill.script_content)
        existing_scan = skill.last_scan_result or {}
        if network_warnings:
            existing_scan["network_import_warnings"] = network_warnings
        else:
            # Clear previous warnings if script no longer has network imports
            existing_scan.pop("network_import_warnings", None)
        skill.last_scan_result = existing_scan

    db.commit()
    db.refresh(skill)

    log_tenant_event(db, ctx.tenant_id, current_user.id, TenantAuditActions.SKILL_UPDATE, "skill", str(skill_id), {"name": skill.name}, request)
    # Audit log auto-scan result on update (if instructions changed)
    if instructions_changed and skill.scan_status and skill.scan_status != 'pending':
        scan_severity = "warning" if skill.scan_status == "rejected" else "info"
        log_tenant_event(db, ctx.tenant_id, current_user.id,
            TenantAuditActions.SECURITY_SKILL_SCAN, "skill", str(skill_id),
            {"name": skill.name, "scan_status": skill.scan_status, "trigger": "auto_update"}, request, severity=scan_severity)
    logger.info(f"Custom skill updated: {skill.name} (id={skill.id}, version={skill.version})")
    return _to_response(skill)


@router.delete("/custom-skills/{skill_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_custom_skill(
    skill_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.delete")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Delete a custom skill and all associated data."""
    query = db.query(CustomSkill).filter(CustomSkill.id == skill_id)
    query = ctx.filter_by_tenant(query, CustomSkill.tenant_id)
    skill = query.first()

    if not skill:
        raise HTTPException(status_code=404, detail="Custom skill not found")

    skill_name = skill.name
    db.delete(skill)
    db.commit()

    log_tenant_event(db, ctx.tenant_id, current_user.id, TenantAuditActions.SKILL_DELETE, "skill", str(skill_id), {"name": skill_name}, request)
    logger.info(f"Custom skill deleted: {skill_name} (id={skill_id})")
    return None


@router.get("/custom-skills/{skill_id}/versions", response_model=List[CustomSkillVersionResponse])
async def list_custom_skill_versions(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List version history for a custom skill."""
    # Verify skill belongs to tenant
    skill_query = db.query(CustomSkill).filter(CustomSkill.id == skill_id)
    skill_query = ctx.filter_by_tenant(skill_query, CustomSkill.tenant_id)
    skill = skill_query.first()

    if not skill:
        raise HTTPException(status_code=404, detail="Custom skill not found")

    versions = db.query(CustomSkillVersion).filter(
        CustomSkillVersion.custom_skill_id == skill_id
    ).order_by(CustomSkillVersion.changed_at.desc()).all()

    return [_to_version_response(v) for v in versions]


# ==================== Phase 23: Deploy / Scan / Test / Executions ====================


@router.post("/custom-skills/{skill_id}/deploy")
async def deploy_custom_skill(
    skill_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.create")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Deploy a script-type skill to the tenant's toolbox container."""
    query = db.query(CustomSkill).filter(CustomSkill.id == skill_id)
    query = ctx.filter_by_tenant(query, CustomSkill.tenant_id)
    skill = query.first()

    if not skill:
        raise HTTPException(status_code=404, detail="Custom skill not found")

    if skill.skill_type_variant != 'script':
        raise HTTPException(status_code=400, detail="Only script-type skills can be deployed")

    if not skill.script_content:
        raise HTTPException(status_code=400, detail="Skill has no script content to deploy")

    from services.custom_skill_deploy_service import CustomSkillDeployService
    result = await CustomSkillDeployService.deploy(skill_id, ctx.tenant_id, db)

    if not result.get("success"):
        raise HTTPException(status_code=500, detail=result.get("error", "Deployment failed"))

    log_tenant_event(db, ctx.tenant_id, current_user.id, TenantAuditActions.SKILL_DEPLOY, "skill", str(skill_id), {"name": skill.name}, request)
    logger.info(f"Skill {skill_id} deployed for tenant {ctx.tenant_id}")
    return result


@router.post("/custom-skills/{skill_id}/scan")
async def scan_custom_skill(
    skill_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.create")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Re-run Sentinel scan on a custom skill's content."""
    query = db.query(CustomSkill).filter(CustomSkill.id == skill_id)
    query = ctx.filter_by_tenant(query, CustomSkill.tenant_id)
    skill = query.first()

    if not skill:
        raise HTTPException(status_code=404, detail="Custom skill not found")

    # Scan instruction content
    content_to_scan = skill.instructions_md or ""
    # For script skills, also scan the script content
    if skill.script_content:
        content_to_scan += f"\n\n--- Script Content ---\n{skill.script_content}"

    if not content_to_scan.strip():
        skill.scan_status = 'clean'
        skill.last_scan_result = None
        db.commit()
        return {"scan_status": "clean", "last_scan_result": None}

    scan_result = await _scan_instructions(content_to_scan, db, tenant_id=ctx.tenant_id, sentinel_profile_id=skill.sentinel_profile_id)
    skill.scan_status = scan_result["scan_status"]
    skill.last_scan_result = scan_result.get("last_scan_result")
    db.commit()

    # Audit log the scan result (both clean and rejected)
    scan_details = {"name": skill.name, "scan_status": skill.scan_status}
    if skill.last_scan_result:
        scan_details.update({k: v for k, v in skill.last_scan_result.items() if k in ("reason", "detection_type", "threat_score", "profile_name")})
    severity = "warning" if skill.scan_status == "rejected" else "info"
    log_tenant_event(db, ctx.tenant_id, current_user.id,
        TenantAuditActions.SECURITY_SKILL_SCAN, "skill", str(skill_id),
        scan_details, severity=severity)

    logger.info(f"Skill {skill_id} re-scanned: {skill.scan_status}")
    return {"scan_status": skill.scan_status, "last_scan_result": skill.last_scan_result}


@router.post("/custom-skills/{skill_id}/test")
async def test_custom_skill(
    skill_id: int,
    payload: CustomSkillTestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.execute")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Execute a custom skill with test input and return the result."""
    query = db.query(CustomSkill).filter(CustomSkill.id == skill_id)
    query = ctx.filter_by_tenant(query, CustomSkill.tenant_id)
    skill = query.first()

    if not skill:
        raise HTTPException(status_code=404, detail="Custom skill not found")

    from agent.skills.custom_skill_adapter import CustomSkillAdapter

    adapter = CustomSkillAdapter(skill_record=skill)
    config = {'tenant_id': ctx.tenant_id, 'db': db}

    # Record execution start
    execution = CustomSkillExecution(
        tenant_id=ctx.tenant_id,
        custom_skill_id=skill.id,
        skill_name=skill.name,
        input_json=payload.arguments or {},
        status='running',
    )
    db.add(execution)
    db.flush()

    import time
    start_time = time.time()

    try:
        result = await adapter.execute_tool(
            arguments=payload.arguments or {},
            config=config,
        )
        elapsed_ms = int((time.time() - start_time) * 1000)

        # Update execution record
        execution.status = 'completed' if result.success else 'failed'
        execution.output = result.output[:4000] if result.output else None
        execution.error = result.output[:4000] if not result.success else None
        execution.execution_time_ms = elapsed_ms
        db.commit()

        return {
            "success": result.success,
            "output": result.output,
            "metadata": result.metadata,
            "execution_time_ms": elapsed_ms,
            "execution_id": execution.id,
        }

    except Exception as e:
        elapsed_ms = int((time.time() - start_time) * 1000)
        execution.status = 'failed'
        execution.error = str(e)[:4000]
        execution.execution_time_ms = elapsed_ms
        db.commit()
        raise HTTPException(status_code=500, detail=f"Skill execution failed: {e}")


@router.get("/custom-skills/{skill_id}/executions", response_model=List[CustomSkillExecutionResponse])
async def list_custom_skill_executions(
    skill_id: int,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List execution history for a custom skill (paginated)."""
    # Verify skill belongs to tenant
    skill_query = db.query(CustomSkill).filter(CustomSkill.id == skill_id)
    skill_query = ctx.filter_by_tenant(skill_query, CustomSkill.tenant_id)
    skill = skill_query.first()

    if not skill:
        raise HTTPException(status_code=404, detail="Custom skill not found")

    executions = db.query(CustomSkillExecution).filter(
        CustomSkillExecution.custom_skill_id == skill_id,
        CustomSkillExecution.tenant_id == ctx.tenant_id,
    ).order_by(CustomSkillExecution.created_at.desc()).offset(offset).limit(limit).all()

    return [
        CustomSkillExecutionResponse(
            id=ex.id,
            tenant_id=ex.tenant_id,
            agent_id=ex.agent_id,
            custom_skill_id=ex.custom_skill_id,
            skill_name=ex.skill_name,
            input_json=ex.input_json,
            output=ex.output,
            error=ex.error,
            status=ex.status,
            execution_time_ms=ex.execution_time_ms,
            sentinel_result=ex.sentinel_result,
            created_at=ex.created_at.isoformat() if ex.created_at else None,
        )
        for ex in executions
    ]


# ==================== Agent Custom Skill Assignment ====================

class AgentCustomSkillAssignRequest(BaseModel):
    custom_skill_id: int
    config: Optional[dict] = Field(default_factory=dict)


class AgentCustomSkillUpdateRequest(BaseModel):
    is_enabled: Optional[bool] = None
    config: Optional[dict] = None


class AgentCustomSkillResponse(BaseModel):
    id: int
    agent_id: int
    custom_skill_id: int
    is_enabled: bool
    config: dict
    skill: CustomSkillResponse

    class Config:
        from_attributes = True


@router.get("/agents/{agent_id}/custom-skills", response_model=List[AgentCustomSkillResponse])
async def list_agent_custom_skills(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.read")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """List custom skills assigned to an agent."""
    from models import Agent

    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == ctx.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    assignments = db.query(AgentCustomSkill).filter(
        AgentCustomSkill.agent_id == agent_id,
    ).all()

    result = []
    for assignment in assignments:
        skill = db.query(CustomSkill).filter(CustomSkill.id == assignment.custom_skill_id).first()
        if skill:
            result.append(AgentCustomSkillResponse(
                id=assignment.id,
                agent_id=assignment.agent_id,
                custom_skill_id=assignment.custom_skill_id,
                is_enabled=assignment.is_enabled,
                config=assignment.config or {},
                skill=_to_response(skill),
            ))
    return result


@router.post("/agents/{agent_id}/custom-skills", response_model=AgentCustomSkillResponse, status_code=status.HTTP_201_CREATED)
async def assign_custom_skill(
    agent_id: int,
    payload: AgentCustomSkillAssignRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.create")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Assign a custom skill to an agent."""
    from models import Agent

    # Verify agent belongs to tenant
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == ctx.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    # Verify custom skill belongs to same tenant
    skill = db.query(CustomSkill).filter(
        CustomSkill.id == payload.custom_skill_id,
        CustomSkill.tenant_id == ctx.tenant_id,
    ).first()
    if not skill:
        raise HTTPException(status_code=404, detail="Custom skill not found")

    # Check for duplicate assignment
    existing = db.query(AgentCustomSkill).filter(
        AgentCustomSkill.agent_id == agent_id,
        AgentCustomSkill.custom_skill_id == payload.custom_skill_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Skill already assigned to this agent")

    assignment = AgentCustomSkill(
        agent_id=agent_id,
        custom_skill_id=payload.custom_skill_id,
        is_enabled=True,
        config=payload.config or {},
    )
    db.add(assignment)
    db.commit()
    db.refresh(assignment)

    logger.info(f"Custom skill '{skill.name}' assigned to agent {agent_id}")
    return AgentCustomSkillResponse(
        id=assignment.id,
        agent_id=assignment.agent_id,
        custom_skill_id=assignment.custom_skill_id,
        is_enabled=assignment.is_enabled,
        config=assignment.config or {},
        skill=_to_response(skill),
    )


@router.put("/agents/{agent_id}/custom-skills/{assignment_id}", response_model=AgentCustomSkillResponse)
async def update_custom_skill_assignment(
    agent_id: int,
    assignment_id: int,
    payload: AgentCustomSkillUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.create")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Update a custom skill assignment's config or enabled state."""
    from models import Agent

    # Verify agent belongs to tenant
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == ctx.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    assignment = db.query(AgentCustomSkill).filter(
        AgentCustomSkill.id == assignment_id,
        AgentCustomSkill.agent_id == agent_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    if payload.is_enabled is not None:
        assignment.is_enabled = payload.is_enabled
    if payload.config is not None:
        assignment.config = payload.config

    db.commit()
    db.refresh(assignment)

    skill = db.query(CustomSkill).filter(CustomSkill.id == assignment.custom_skill_id).first()

    logger.info(f"Custom skill assignment {assignment_id} updated for agent {agent_id}")
    return AgentCustomSkillResponse(
        id=assignment.id,
        agent_id=assignment.agent_id,
        custom_skill_id=assignment.custom_skill_id,
        is_enabled=assignment.is_enabled,
        config=assignment.config or {},
        skill=_to_response(skill),
    )


@router.delete("/agents/{agent_id}/custom-skills/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_custom_skill_assignment(
    agent_id: int,
    assignment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("skills.custom.delete")),
    ctx: TenantContext = Depends(get_tenant_context),
):
    """Remove a custom skill assignment from an agent."""
    from models import Agent

    # Verify agent belongs to tenant
    agent = db.query(Agent).filter(
        Agent.id == agent_id,
        Agent.tenant_id == ctx.tenant_id,
    ).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    assignment = db.query(AgentCustomSkill).filter(
        AgentCustomSkill.id == assignment_id,
        AgentCustomSkill.agent_id == agent_id,
    ).first()
    if not assignment:
        raise HTTPException(status_code=404, detail="Assignment not found")

    skill_id = assignment.custom_skill_id
    db.delete(assignment)
    db.commit()

    logger.info(f"Custom skill assignment {assignment_id} (skill {skill_id}) removed from agent {agent_id}")
    return None
