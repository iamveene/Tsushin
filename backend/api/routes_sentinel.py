"""
Sentinel Security Agent API Routes - Phase 20

Provides REST API endpoints for:
- Sentinel configuration management (system, tenant, agent)
- Analysis logs and statistics
- LLM configuration
- Security event retrieval for Watcher
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_serializer
from sqlalchemy.orm import Session

from models import (
    SentinelConfig,
    SentinelAgentConfig,
    SentinelAnalysisLog,
    Agent,
)
from models_rbac import User
from auth_dependencies import TenantContext, get_tenant_context, require_permission
from services.sentinel_service import SentinelService
from services.sentinel_detections import DETECTION_REGISTRY, get_detection_types

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sentinel", tags=["Sentinel Security"])

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

class SentinelConfigResponse(BaseModel):
    """Response model for Sentinel configuration."""
    id: int
    tenant_id: Optional[str]
    is_enabled: bool
    enable_prompt_analysis: bool
    enable_tool_analysis: bool
    enable_shell_analysis: bool
    detect_prompt_injection: bool
    detect_agent_takeover: bool
    detect_poisoning: bool
    detect_shell_malicious_intent: bool
    detect_memory_poisoning: bool
    aggressiveness_level: int
    llm_provider: str
    llm_model: str
    llm_max_tokens: int
    llm_temperature: float
    cache_ttl_seconds: int
    max_input_chars: int
    timeout_seconds: float
    block_on_detection: bool
    log_all_analyses: bool
    # Phase 20 Enhancement: Detection mode and slash command toggle
    detection_mode: str = "block"  # 'block', 'warn_only', 'detect_only', 'off'
    enable_slash_command_analysis: bool = True
    # Notification settings
    enable_notifications: bool = True
    notification_on_block: bool = True
    notification_on_detect: bool = False
    notification_recipient: Optional[str] = None
    notification_message_template: Optional[str] = None
    has_custom_prompts: bool = False
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True

    @field_serializer('created_at', 'updated_at')
    def serialize_datetimes(self, value: datetime, _info) -> str:
        if value is None:
            return None
        return value.isoformat() + "Z"


class SentinelConfigUpdate(BaseModel):
    """Request model for updating Sentinel configuration."""
    is_enabled: Optional[bool] = None
    enable_prompt_analysis: Optional[bool] = None
    enable_tool_analysis: Optional[bool] = None
    enable_shell_analysis: Optional[bool] = None
    detect_prompt_injection: Optional[bool] = None
    detect_agent_takeover: Optional[bool] = None
    detect_poisoning: Optional[bool] = None
    detect_shell_malicious_intent: Optional[bool] = None
    detect_memory_poisoning: Optional[bool] = None
    aggressiveness_level: Optional[int] = Field(None, ge=0, le=3)
    llm_provider: Optional[str] = None
    llm_model: Optional[str] = None
    llm_max_tokens: Optional[int] = Field(None, ge=64, le=1024)
    llm_temperature: Optional[float] = Field(None, ge=0.0, le=1.0)
    cache_ttl_seconds: Optional[int] = Field(None, ge=0, le=3600)
    max_input_chars: Optional[int] = Field(None, ge=100, le=10000)
    timeout_seconds: Optional[float] = Field(None, ge=1.0, le=30.0)
    block_on_detection: Optional[bool] = None
    log_all_analyses: Optional[bool] = None
    # Phase 20 Enhancement: Detection mode and slash command toggle
    detection_mode: Optional[str] = Field(None, pattern="^(block|warn_only|detect_only|off)$")
    enable_slash_command_analysis: Optional[bool] = None
    # Notification settings
    enable_notifications: Optional[bool] = None
    notification_on_block: Optional[bool] = None
    notification_on_detect: Optional[bool] = None
    notification_recipient: Optional[str] = Field(None, max_length=100)
    notification_message_template: Optional[str] = Field(None, max_length=2000)


class SentinelAgentConfigResponse(BaseModel):
    """Response model for agent-specific Sentinel override."""
    id: int
    agent_id: int
    is_enabled: Optional[bool]
    enable_prompt_analysis: Optional[bool]
    enable_tool_analysis: Optional[bool]
    enable_shell_analysis: Optional[bool]
    aggressiveness_level: Optional[int]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

    @field_serializer('created_at', 'updated_at')
    def serialize_datetimes(self, value: datetime, _info) -> str:
        if value is None:
            return None
        return value.isoformat() + "Z"


class SentinelAgentConfigUpdate(BaseModel):
    """Request model for updating agent-specific Sentinel override."""
    is_enabled: Optional[bool] = None
    enable_prompt_analysis: Optional[bool] = None
    enable_tool_analysis: Optional[bool] = None
    enable_shell_analysis: Optional[bool] = None
    aggressiveness_level: Optional[int] = Field(None, ge=0, le=3)


class SentinelLogResponse(BaseModel):
    """Response model for Sentinel analysis log entry."""
    id: int
    tenant_id: str
    agent_id: Optional[int]
    analysis_type: str
    detection_type: str
    input_content: str
    is_threat_detected: bool
    threat_score: Optional[float]
    threat_reason: Optional[str]
    action_taken: str
    llm_provider: Optional[str]
    llm_model: Optional[str]
    llm_response_time_ms: Optional[int]
    sender_key: Optional[str]
    message_id: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True

    @field_serializer('created_at')
    def serialize_created_at(self, value: datetime, _info) -> str:
        if value is None:
            return None
        return value.isoformat() + "Z"


class SentinelStatsResponse(BaseModel):
    """Response model for Sentinel statistics."""
    total_analyses: int
    threats_detected: int
    threats_blocked: int
    detection_rate: float
    by_detection_type: dict
    period_days: int


class SentinelTestRequest(BaseModel):
    """Request model for testing Sentinel analysis."""
    input_text: str = Field(..., min_length=1, max_length=5000)
    detection_type: str = Field(default="prompt_injection")

    class Config:
        extra = "forbid"  # Reject unknown fields to prevent silent parameter mistakes


class SentinelTestResponse(BaseModel):
    """Response model for Sentinel test analysis."""
    is_threat_detected: bool
    threat_score: float
    threat_reason: Optional[str]
    action: str
    detection_type: str
    analysis_type: str
    response_time_ms: int


class SentinelPromptResponse(BaseModel):
    """Response model for analysis prompts."""
    detection_type: str
    has_custom_prompt: bool
    custom_prompt: Optional[str]
    default_prompt: str


class SentinelPromptUpdate(BaseModel):
    """Request model for updating custom analysis prompt."""
    prompt: Optional[str] = Field(None, max_length=10000)


class LLMProviderResponse(BaseModel):
    """Response model for LLM provider."""
    name: str
    display_name: str
    models: List[str]


class LLMTestRequest(BaseModel):
    """Request model for testing LLM connection."""
    provider: str
    model: str


class LLMTestResponse(BaseModel):
    """Response model for LLM connection test."""
    success: bool
    message: str
    response_time_ms: int


# =============================================================================
# Configuration Endpoints
# =============================================================================

@router.get("/config", response_model=SentinelConfigResponse)
async def get_sentinel_config(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Get tenant Sentinel configuration.

    Returns the tenant-specific config if it exists, otherwise the system default.
    """
    # Try to get tenant-specific config
    config = db.query(SentinelConfig).filter(
        SentinelConfig.tenant_id == ctx.tenant_id
    ).first()

    # Fall back to system config
    if not config:
        config = db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id.is_(None)
        ).first()

    if not config:
        raise HTTPException(status_code=404, detail="Sentinel configuration not found")

    # Check for custom prompts
    has_custom = any([
        config.prompt_injection_prompt,
        config.agent_takeover_prompt,
        config.poisoning_prompt,
        config.shell_intent_prompt,
        getattr(config, 'memory_poisoning_prompt', None),
    ])

    return SentinelConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        is_enabled=config.is_enabled,
        enable_prompt_analysis=config.enable_prompt_analysis,
        enable_tool_analysis=config.enable_tool_analysis,
        enable_shell_analysis=config.enable_shell_analysis,
        detect_prompt_injection=config.detect_prompt_injection,
        detect_agent_takeover=config.detect_agent_takeover,
        detect_poisoning=config.detect_poisoning,
        detect_shell_malicious_intent=config.detect_shell_malicious_intent,
        detect_memory_poisoning=getattr(config, 'detect_memory_poisoning', True),
        aggressiveness_level=config.aggressiveness_level,
        llm_provider=config.llm_provider,
        llm_model=config.llm_model,
        llm_max_tokens=config.llm_max_tokens,
        llm_temperature=config.llm_temperature,
        cache_ttl_seconds=config.cache_ttl_seconds,
        max_input_chars=config.max_input_chars,
        timeout_seconds=config.timeout_seconds,
        block_on_detection=config.block_on_detection,
        log_all_analyses=config.log_all_analyses,
        detection_mode=config.detection_mode,
        enable_slash_command_analysis=config.enable_slash_command_analysis,
        enable_notifications=getattr(config, 'enable_notifications', True),
        notification_on_block=getattr(config, 'notification_on_block', True),
        notification_on_detect=getattr(config, 'notification_on_detect', False),
        notification_recipient=getattr(config, 'notification_recipient', None),
        notification_message_template=getattr(config, 'notification_message_template', None),
        has_custom_prompts=has_custom,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


@router.put("/config", response_model=SentinelConfigResponse)
async def update_sentinel_config(
    update: SentinelConfigUpdate,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Update tenant Sentinel configuration.

    Creates a tenant-specific config if it doesn't exist.
    """
    # Get or create tenant config
    config = db.query(SentinelConfig).filter(
        SentinelConfig.tenant_id == ctx.tenant_id
    ).first()

    if not config:
        # Get system config as template
        system_config = db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id.is_(None)
        ).first()

        if not system_config:
            raise HTTPException(status_code=500, detail="System Sentinel config not found")

        # Create tenant config with system defaults
        config = SentinelConfig(
            tenant_id=ctx.tenant_id,
            is_enabled=system_config.is_enabled,
            enable_prompt_analysis=system_config.enable_prompt_analysis,
            enable_tool_analysis=system_config.enable_tool_analysis,
            enable_shell_analysis=system_config.enable_shell_analysis,
            detect_prompt_injection=system_config.detect_prompt_injection,
            detect_agent_takeover=system_config.detect_agent_takeover,
            detect_poisoning=system_config.detect_poisoning,
            detect_shell_malicious_intent=system_config.detect_shell_malicious_intent,
            detect_memory_poisoning=getattr(system_config, 'detect_memory_poisoning', True),
            aggressiveness_level=system_config.aggressiveness_level,
            llm_provider=system_config.llm_provider,
            llm_model=system_config.llm_model,
            llm_max_tokens=system_config.llm_max_tokens,
            llm_temperature=system_config.llm_temperature,
            cache_ttl_seconds=system_config.cache_ttl_seconds,
            max_input_chars=system_config.max_input_chars,
            timeout_seconds=system_config.timeout_seconds,
            block_on_detection=system_config.block_on_detection,
            log_all_analyses=system_config.log_all_analyses,
            detection_mode=system_config.detection_mode,
            enable_slash_command_analysis=system_config.enable_slash_command_analysis,
            enable_notifications=getattr(system_config, 'enable_notifications', True),
            notification_on_block=getattr(system_config, 'notification_on_block', True),
            notification_on_detect=getattr(system_config, 'notification_on_detect', False),
            notification_recipient=getattr(system_config, 'notification_recipient', None),
            notification_message_template=getattr(system_config, 'notification_message_template', None),
            created_by=current_user.id,
        )
        db.add(config)

    # Apply updates
    update_data = update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(config, field):
            setattr(config, field, value)

    config.updated_by = current_user.id
    config.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(config)

    # Check for custom prompts
    has_custom = any([
        config.prompt_injection_prompt,
        config.agent_takeover_prompt,
        config.poisoning_prompt,
        config.shell_intent_prompt,
        getattr(config, 'memory_poisoning_prompt', None),
    ])

    return SentinelConfigResponse(
        id=config.id,
        tenant_id=config.tenant_id,
        is_enabled=config.is_enabled,
        enable_prompt_analysis=config.enable_prompt_analysis,
        enable_tool_analysis=config.enable_tool_analysis,
        enable_shell_analysis=config.enable_shell_analysis,
        detect_prompt_injection=config.detect_prompt_injection,
        detect_agent_takeover=config.detect_agent_takeover,
        detect_poisoning=config.detect_poisoning,
        detect_shell_malicious_intent=config.detect_shell_malicious_intent,
        detect_memory_poisoning=getattr(config, 'detect_memory_poisoning', True),
        aggressiveness_level=config.aggressiveness_level,
        llm_provider=config.llm_provider,
        llm_model=config.llm_model,
        llm_max_tokens=config.llm_max_tokens,
        llm_temperature=config.llm_temperature,
        cache_ttl_seconds=config.cache_ttl_seconds,
        max_input_chars=config.max_input_chars,
        timeout_seconds=config.timeout_seconds,
        block_on_detection=config.block_on_detection,
        log_all_analyses=config.log_all_analyses,
        detection_mode=config.detection_mode,
        enable_slash_command_analysis=config.enable_slash_command_analysis,
        enable_notifications=getattr(config, 'enable_notifications', True),
        notification_on_block=getattr(config, 'notification_on_block', True),
        notification_on_detect=getattr(config, 'notification_on_detect', False),
        notification_recipient=getattr(config, 'notification_recipient', None),
        notification_message_template=getattr(config, 'notification_message_template', None),
        has_custom_prompts=has_custom,
        created_at=config.created_at,
        updated_at=config.updated_at,
    )


# =============================================================================
# Agent Override Endpoints
# =============================================================================

@router.get("/config/agent/{agent_id}", response_model=Optional[SentinelAgentConfigResponse])
async def get_agent_sentinel_config(
    agent_id: int,
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get agent-specific Sentinel override configuration."""
    # Verify agent belongs to tenant
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    override = db.query(SentinelAgentConfig).filter(
        SentinelAgentConfig.agent_id == agent_id
    ).first()

    if not override:
        return None

    return SentinelAgentConfigResponse(
        id=override.id,
        agent_id=override.agent_id,
        is_enabled=override.is_enabled,
        enable_prompt_analysis=override.enable_prompt_analysis,
        enable_tool_analysis=override.enable_tool_analysis,
        enable_shell_analysis=override.enable_shell_analysis,
        aggressiveness_level=override.aggressiveness_level,
        created_at=override.created_at,
        updated_at=override.updated_at,
    )


@router.put("/config/agent/{agent_id}", response_model=SentinelAgentConfigResponse)
async def update_agent_sentinel_config(
    agent_id: int,
    update: SentinelAgentConfigUpdate,
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Update agent-specific Sentinel override configuration."""
    # Verify agent belongs to tenant
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    # Get or create agent override
    override = db.query(SentinelAgentConfig).filter(
        SentinelAgentConfig.agent_id == agent_id
    ).first()

    if not override:
        override = SentinelAgentConfig(agent_id=agent_id)
        db.add(override)

    # Apply updates
    update_data = update.dict(exclude_unset=True)
    for field, value in update_data.items():
        if hasattr(override, field):
            setattr(override, field, value)

    override.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(override)

    return SentinelAgentConfigResponse(
        id=override.id,
        agent_id=override.agent_id,
        is_enabled=override.is_enabled,
        enable_prompt_analysis=override.enable_prompt_analysis,
        enable_tool_analysis=override.enable_tool_analysis,
        enable_shell_analysis=override.enable_shell_analysis,
        aggressiveness_level=override.aggressiveness_level,
        created_at=override.created_at,
        updated_at=override.updated_at,
    )


@router.delete("/config/agent/{agent_id}")
async def delete_agent_sentinel_config(
    agent_id: int,
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Delete agent-specific Sentinel override (revert to tenant/system defaults)."""
    # Verify agent belongs to tenant
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(status_code=404, detail="Agent not found")

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(status_code=403, detail="Access denied")

    deleted = db.query(SentinelAgentConfig).filter(
        SentinelAgentConfig.agent_id == agent_id
    ).delete()

    db.commit()

    return {"deleted": deleted > 0, "message": "Agent override deleted" if deleted else "No override found"}


# =============================================================================
# Logs and Statistics Endpoints
# =============================================================================

@router.get("/logs", response_model=List[SentinelLogResponse])
async def get_sentinel_logs(
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    threat_only: bool = Query(False),
    detection_type: Optional[str] = Query(None),
    analysis_type: Optional[str] = Query(None, description="Filter by analysis type: prompt, tool, shell"),
    agent_id: Optional[int] = Query(None),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Get Sentinel analysis logs for Watcher Security tab.

    Supports filtering by threat status, detection type, analysis type, and agent.
    """
    service = SentinelService(db, ctx.tenant_id)
    logs = service.get_logs(
        limit=limit,
        offset=offset,
        threat_only=threat_only,
        detection_type=detection_type,
        analysis_type=analysis_type,
        agent_id=agent_id,
    )

    return [
        SentinelLogResponse(
            id=log.id,
            tenant_id=log.tenant_id,
            agent_id=log.agent_id,
            analysis_type=log.analysis_type,
            detection_type=log.detection_type,
            input_content=log.input_content,
            is_threat_detected=log.is_threat_detected,
            threat_score=log.threat_score,
            threat_reason=log.threat_reason,
            action_taken=log.action_taken,
            llm_provider=log.llm_provider,
            llm_model=log.llm_model,
            llm_response_time_ms=log.llm_response_time_ms,
            sender_key=log.sender_key,
            message_id=log.message_id,
            created_at=log.created_at,
        )
        for log in logs
    ]


@router.get("/stats", response_model=SentinelStatsResponse)
async def get_sentinel_stats(
    days: int = Query(7, ge=1, le=90),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get Sentinel detection statistics for dashboard."""
    service = SentinelService(db, ctx.tenant_id)
    stats = service.get_stats(days=days)

    return SentinelStatsResponse(
        total_analyses=stats["total_analyses"],
        threats_detected=stats["threats_detected"],
        threats_blocked=stats["threats_blocked"],
        detection_rate=stats["detection_rate"],
        by_detection_type=stats["by_detection_type"],
        period_days=stats["period_days"],
    )


# =============================================================================
# Testing Endpoints
# =============================================================================

@router.post("/test", response_model=SentinelTestResponse)
async def test_sentinel_analysis(
    request: SentinelTestRequest,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """
    Test Sentinel analysis on sample input.

    Useful for testing prompts and configuration before deploying.
    """
    if request.detection_type not in DETECTION_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid detection type. Valid types: {list(DETECTION_REGISTRY.keys())}"
        )

    service = SentinelService(db, ctx.tenant_id)

    # Determine analysis type from detection type
    detection_info = DETECTION_REGISTRY[request.detection_type]
    applies_to = detection_info.get("applies_to", ["prompt"])
    analysis_type = applies_to[0] if applies_to else "prompt"

    if analysis_type == "prompt":
        result = await service.analyze_prompt(
            prompt=request.input_text,
            source=None,  # Treat as user input
        )
    elif analysis_type == "shell":
        result = await service.analyze_shell_command(
            command=request.input_text,
        )
    else:
        result = await service.analyze_prompt(
            prompt=request.input_text,
            source=None,
        )

    return SentinelTestResponse(
        is_threat_detected=result.is_threat_detected,
        threat_score=result.threat_score,
        threat_reason=result.threat_reason,
        action=result.action,
        detection_type=result.detection_type,
        analysis_type=result.analysis_type,
        response_time_ms=result.response_time_ms,
    )


# =============================================================================
# Prompts Endpoints
# =============================================================================

@router.get("/prompts", response_model=List[SentinelPromptResponse])
async def get_sentinel_prompts(
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Get all analysis prompts (custom and defaults)."""
    from services.sentinel_detections import get_default_prompt

    # Get tenant config for custom prompts
    config = db.query(SentinelConfig).filter(
        SentinelConfig.tenant_id == ctx.tenant_id
    ).first()

    if not config:
        config = db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id.is_(None)
        ).first()

    prompts = []
    for detection_type in get_detection_types():
        custom_prompt = None
        if config:
            prompt_map = {
                "prompt_injection": config.prompt_injection_prompt,
                "agent_takeover": config.agent_takeover_prompt,
                "poisoning": config.poisoning_prompt,
                "shell_malicious": config.shell_intent_prompt,
                "memory_poisoning": getattr(config, 'memory_poisoning_prompt', None),
            }
            custom_prompt = prompt_map.get(detection_type)

        default_prompt = get_default_prompt(detection_type, 1)  # Get moderate level

        prompts.append(SentinelPromptResponse(
            detection_type=detection_type,
            has_custom_prompt=custom_prompt is not None,
            custom_prompt=custom_prompt,
            default_prompt=default_prompt,
        ))

    return prompts


@router.put("/prompts/{detection_type}")
async def update_sentinel_prompt(
    detection_type: str,
    update: SentinelPromptUpdate,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Update custom analysis prompt for a detection type."""
    if detection_type not in DETECTION_REGISTRY:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid detection type. Valid types: {list(DETECTION_REGISTRY.keys())}"
        )

    # Get or create tenant config
    config = db.query(SentinelConfig).filter(
        SentinelConfig.tenant_id == ctx.tenant_id
    ).first()

    if not config:
        # Create tenant config from system defaults
        system_config = db.query(SentinelConfig).filter(
            SentinelConfig.tenant_id.is_(None)
        ).first()

        if not system_config:
            raise HTTPException(status_code=500, detail="System config not found")

        config = SentinelConfig(
            tenant_id=ctx.tenant_id,
            is_enabled=system_config.is_enabled,
            enable_prompt_analysis=system_config.enable_prompt_analysis,
            enable_tool_analysis=system_config.enable_tool_analysis,
            enable_shell_analysis=system_config.enable_shell_analysis,
            detect_prompt_injection=system_config.detect_prompt_injection,
            detect_agent_takeover=system_config.detect_agent_takeover,
            detect_poisoning=system_config.detect_poisoning,
            detect_shell_malicious_intent=system_config.detect_shell_malicious_intent,
            detect_memory_poisoning=getattr(system_config, 'detect_memory_poisoning', True),
            aggressiveness_level=system_config.aggressiveness_level,
            llm_provider=system_config.llm_provider,
            llm_model=system_config.llm_model,
            created_by=current_user.id,
        )
        db.add(config)

    # Update the specific prompt
    prompt_field_map = {
        "prompt_injection": "prompt_injection_prompt",
        "agent_takeover": "agent_takeover_prompt",
        "poisoning": "poisoning_prompt",
        "shell_malicious": "shell_intent_prompt",
        "memory_poisoning": "memory_poisoning_prompt",
    }

    field_name = prompt_field_map.get(detection_type)
    if field_name:
        setattr(config, field_name, update.prompt)  # None = reset to default

    config.updated_by = current_user.id
    config.updated_at = datetime.utcnow()

    db.commit()

    return {
        "success": True,
        "detection_type": detection_type,
        "prompt_set": update.prompt is not None,
    }


# =============================================================================
# LLM Configuration Endpoints
# =============================================================================

# LLM model lists - kept in sync with Agent configuration (frontend/app/agents/page.tsx)
# Sentinel uses these same models for security analysis
LLM_MODELS = {
    "gemini": [
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
        "gemini-2.5-pro",
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ],
    "anthropic": [
        "claude-sonnet-4-20250514",
        "claude-3-5-sonnet-20241022",
        "claude-3-opus-20240229",
        "claude-3-haiku-20240307",
    ],
    "openai": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4-turbo",
        "gpt-3.5-turbo",
    ],
    "openrouter": [
        "google/gemini-2.5-flash",
        "google/gemini-2.5-pro",
        "google/gemini-2.0-flash-thinking-exp",
        "anthropic/claude-sonnet-4-5",
        "anthropic/claude-3.5-sonnet",
        "anthropic/claude-3-opus",
        "openai/gpt-4o",
        "openai/gpt-4-turbo",
        "meta-llama/llama-3.1-8b-instruct",
        "mistralai/mistral-7b-instruct",
    ],
    "ollama": [
        "llama3.2:latest",
        "llama3.1",
        "mistral",
        "phi3",
    ],
}


@router.get("/llm/providers", response_model=List[LLMProviderResponse])
async def get_llm_providers():
    """Get available LLM providers for Sentinel analysis."""
    return [
        LLMProviderResponse(
            name="gemini",
            display_name="Google Gemini",
            models=LLM_MODELS["gemini"],
        ),
        LLMProviderResponse(
            name="anthropic",
            display_name="Anthropic Claude",
            models=LLM_MODELS["anthropic"],
        ),
        LLMProviderResponse(
            name="openai",
            display_name="OpenAI",
            models=LLM_MODELS["openai"],
        ),
        LLMProviderResponse(
            name="openrouter",
            display_name="OpenRouter",
            models=LLM_MODELS["openrouter"],
        ),
        LLMProviderResponse(
            name="ollama",
            display_name="Ollama (Local)",
            models=LLM_MODELS["ollama"],
        ),
    ]


@router.get("/llm/models/{provider}")
async def get_llm_models(provider: str):
    """Get available models for a specific LLM provider."""
    if provider not in LLM_MODELS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")

    return {"provider": provider, "models": LLM_MODELS[provider]}


@router.post("/llm/test", response_model=LLMTestResponse)
async def test_llm_connection(
    request: LLMTestRequest,
    current_user: User = Depends(require_permission("org.settings.write")),
    ctx: TenantContext = Depends(get_tenant_context),
    db: Session = Depends(get_db),
):
    """Test LLM connection for Sentinel analysis."""
    import time
    from agent.ai_client import AIClient

    start_time = time.time()

    try:
        client = AIClient(
            provider=request.provider,
            model_name=request.model,
            db=db,
            temperature=0.1,
            max_tokens=50,
            tenant_id=ctx.tenant_id,
        )

        result = await client.generate(
            system_prompt="You are a test assistant.",
            user_message="Say 'OK' if you can receive this message.",
            operation_type="sentinel_llm_test",
        )

        response_time_ms = int((time.time() - start_time) * 1000)

        if result.get("error"):
            return LLMTestResponse(
                success=False,
                message=f"Error: {result['error']}",
                response_time_ms=response_time_ms,
            )

        return LLMTestResponse(
            success=True,
            message=f"Connection successful. Response: {result.get('answer', 'OK')[:50]}",
            response_time_ms=response_time_ms,
        )

    except Exception as e:
        response_time_ms = int((time.time() - start_time) * 1000)
        return LLMTestResponse(
            success=False,
            message=f"Connection failed: {str(e)}",
            response_time_ms=response_time_ms,
        )


# =============================================================================
# Memory Cleanup Endpoint - Phase 21
# =============================================================================

class MemoryCleanupResponse(BaseModel):
    """Response model for memory cleanup operation."""
    success: bool
    message: str
    blocked_found: int = 0
    memory_deleted: int = 0
    fts_deleted: int = 0


@router.post("/cleanup-poisoned-memory", response_model=MemoryCleanupResponse)
async def cleanup_poisoned_memory(
    agent_id: Optional[int] = Query(None, description="Optional: limit cleanup to specific agent"),
    db: Session = Depends(get_db),
    tenant: TenantContext = Depends(get_tenant_context),
):
    """
    Phase 21: Remove blocked messages from agent memory to prevent poisoning.

    This cleans up messages that were stored BEFORE the pre-memory Sentinel check
    was implemented. Only affects messages that were previously blocked by Sentinel.

    - Removes from Memory table (PostgreSQL)
    - Removes from FTS5 index (full-text search)

    Returns statistics about what was cleaned up.
    """
    try:
        sentinel = SentinelService(db, tenant.tenant_id)
        stats = sentinel.cleanup_poisoned_memory(agent_id=agent_id)

        if stats["blocked_found"] == 0:
            return MemoryCleanupResponse(
                success=True,
                message="No blocked messages found to clean up",
                **stats
            )

        return MemoryCleanupResponse(
            success=True,
            message=f"Cleaned up {stats['memory_deleted']} poisoned messages from memory",
            **stats
        )
    except Exception as e:
        logger.error(f"Memory cleanup failed: {e}")
        raise HTTPException(status_code=500, detail=f"Cleanup failed: {str(e)}")


# =============================================================================
# Detection Types Endpoint
# =============================================================================

@router.get("/detection-types")
async def get_detection_types_endpoint():
    """Get all available detection types with metadata."""
    return {
        detection_type: {
            "name": info["name"],
            "description": info["description"],
            "severity": info["severity"],
            "applies_to": info["applies_to"],
            "default_enabled": info["default_enabled"],
        }
        for detection_type, info in DETECTION_REGISTRY.items()
    }
