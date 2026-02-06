"""
TTS Providers API Routes
Endpoints for managing TTS providers and agent configuration.

Security: HIGH-008 fix - All endpoints require authentication (2026-02-02)
- Provider listing requires hub.read permission
- Agent config read requires agents.read permission
- Agent config update requires agents.write permission
- Tenant isolation enforced for agent-based endpoints
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Optional, Any
from pydantic import BaseModel
import logging

from db import get_db
from models import Agent
from models_rbac import User
from auth_dependencies import require_permission, get_tenant_context, TenantContext
from hub.providers import TTSProviderRegistry


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/tts-providers", tags=["tts_providers"])


def verify_agent_access(agent_id: int, ctx: TenantContext, db: Session) -> Agent:
    """
    Verify that the current user has access to the specified agent.

    Args:
        agent_id: ID of the agent to access
        ctx: Tenant context from authentication
        db: Database session

    Returns:
        Agent object if access is granted

    Raises:
        HTTPException: If agent not found or access denied
    """
    agent = db.query(Agent).filter(Agent.id == agent_id).first()
    if not agent:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Agent {agent_id} not found"
        )

    if not ctx.can_access_resource(agent.tenant_id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied to this agent"
        )

    return agent


# ============================================================================
# Pydantic Models
# ============================================================================

class VoiceInfoResponse(BaseModel):
    """Voice information response"""
    voice_id: str
    name: str
    language: str
    gender: Optional[str] = None
    description: Optional[str] = None
    provider: Optional[str] = None


class ProviderInfoResponse(BaseModel):
    """TTS provider information response"""
    id: str
    name: str
    class_name: str
    supported: bool
    requires_api_key: bool = True
    is_free: bool = False
    status: str = "available"  # "available", "coming_soon"
    voice_count: int = 0
    default_voice: str = "default"
    supported_formats: List[str] = []
    supported_languages: List[str] = []
    pricing: Dict = {}


class ProviderStatusResponse(BaseModel):
    """Provider health status response"""
    provider: str
    status: str  # "healthy", "degraded", "unavailable", "not_configured"
    message: str
    available: bool = False
    latency_ms: Optional[int] = None
    details: Dict = {}


class AgentTTSProviderResponse(BaseModel):
    """Agent's TTS provider configuration"""
    provider: Optional[str] = None
    voice: Optional[str] = None
    language: Optional[str] = None
    response_format: Optional[str] = None
    speed: Optional[float] = None


class AgentTTSProviderUpdate(BaseModel):
    """Update agent's TTS provider configuration"""
    provider: str
    voice: Optional[str] = None
    language: Optional[str] = None
    response_format: Optional[str] = None
    speed: Optional[float] = None


# ============================================================================
# Provider Endpoints
# ============================================================================

@router.get("", response_model=List[ProviderInfoResponse])
def list_tts_providers(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read"))
):
    """
    List all available TTS providers.

    Returns provider information including capabilities and status.

    Requires: hub.read permission
    """
    try:
        providers = TTSProviderRegistry.list_providers(db)

        return [
            ProviderInfoResponse(
                id=p["id"],
                name=p["name"],
                class_name=p["class"],
                supported=p["supported"],
                requires_api_key=p.get("requires_api_key", True),
                is_free=p.get("is_free", False),
                status=p.get("status", "available"),
                voice_count=p.get("voice_count", 0),
                default_voice=p.get("default_voice", "default"),
                supported_formats=p.get("supported_formats", []),
                supported_languages=p.get("supported_languages", []),
                pricing=p.get("pricing", {})
            )
            for p in providers
        ]
    except Exception as e:
        logger.error(f"Failed to list TTS providers: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list providers: {str(e)}"
        )


@router.get("/{provider_name}/status", response_model=ProviderStatusResponse)
async def get_provider_status(
    provider_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read"))
):
    """
    Get health status for a specific TTS provider.

    Checks if the provider service is available and functioning.

    Requires: hub.read permission
    """
    try:
        status_result = await TTSProviderRegistry.get_provider_status(provider_name, db)

        return ProviderStatusResponse(
            provider=status_result.provider,
            status=status_result.status,
            message=status_result.message,
            available=status_result.available,
            latency_ms=status_result.latency_ms,
            details=status_result.details
        )
    except Exception as e:
        logger.error(f"Failed to get provider status: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get provider status: {str(e)}"
        )


@router.get("/{provider_name}/voices", response_model=List[VoiceInfoResponse])
def get_provider_voices(
    provider_name: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read"))
):
    """
    Get available voices for a specific TTS provider.

    Returns list of voice options with language and gender information.

    Requires: hub.read permission
    """
    provider = TTSProviderRegistry.get_provider(provider_name, db)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Provider '{provider_name}' not found or not configured"
        )

    try:
        voices = provider.get_available_voices()

        return [
            VoiceInfoResponse(
                voice_id=v.voice_id,
                name=v.name,
                language=v.language,
                gender=v.gender,
                description=v.description,
                provider=v.provider
            )
            for v in voices
        ]
    except Exception as e:
        logger.error(f"Failed to get provider voices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get voices: {str(e)}"
        )


# ============================================================================
# Agent Configuration Endpoints
# ============================================================================

@router.get("/agents/{agent_id}/provider", response_model=AgentTTSProviderResponse)
def get_agent_tts_provider(
    agent_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.read")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Get current TTS provider configuration for an agent.

    Returns the selected provider and settings from AgentSkill config.

    Requires: agents.read permission
    """
    from models import AgentSkill

    agent = verify_agent_access(agent_id, ctx, db)

    # Get TTS configuration from AgentSkill table
    skill = db.query(AgentSkill).filter(
        AgentSkill.agent_id == agent_id,
        AgentSkill.skill_type == "audio_tts"
    ).first()

    tts_config = skill.config if skill else {}

    return AgentTTSProviderResponse(
        provider=tts_config.get("provider"),
        voice=tts_config.get("voice"),
        language=tts_config.get("language"),
        response_format=tts_config.get("response_format"),
        speed=tts_config.get("speed")
    )


@router.put("/agents/{agent_id}/provider")
def update_agent_tts_provider(
    agent_id: int,
    update: AgentTTSProviderUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("agents.write")),
    ctx: TenantContext = Depends(get_tenant_context)
):
    """
    Update agent's TTS provider configuration.

    Sets which provider and voice the agent should use for TTS.
    Updates the AgentSkill table for audio_tts skill.

    Requires: agents.write permission
    """
    from models import AgentSkill

    agent = verify_agent_access(agent_id, ctx, db)

    # Validate provider exists
    if not TTSProviderRegistry.is_provider_registered(update.provider):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{update.provider}' is not registered"
        )

    # Check if provider is coming_soon
    provider_config = TTSProviderRegistry.get_provider_config(update.provider)
    if provider_config.get("status") == "coming_soon":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Provider '{update.provider}' is coming soon and not yet available"
        )

    # Get provider to validate voice if provided
    if update.voice:
        provider = TTSProviderRegistry.get_provider(update.provider, db)
        if provider:
            valid_voices = [v.voice_id for v in provider.get_available_voices()]
            if update.voice not in valid_voices:
                logger.warning(
                    f"Voice '{update.voice}' not in provider's voice list, "
                    f"using anyway (may be valid)"
                )

    # Build TTS config
    tts_config = {
        "provider": update.provider
    }

    if update.voice:
        tts_config["voice"] = update.voice
    if update.language:
        tts_config["language"] = update.language
    if update.response_format:
        tts_config["response_format"] = update.response_format
    if update.speed is not None:
        tts_config["speed"] = update.speed

    # Get or create AgentSkill for audio_tts
    skill = db.query(AgentSkill).filter(
        AgentSkill.agent_id == agent_id,
        AgentSkill.skill_type == "audio_tts"
    ).first()

    if skill:
        # Update existing skill
        skill.config = tts_config
        skill.is_enabled = True
    else:
        # Create new skill
        skill = AgentSkill(
            agent_id=agent_id,
            skill_type="audio_tts",
            is_enabled=True,
            config=tts_config
        )
        db.add(skill)

    db.commit()

    logger.info(f"Agent {agent_id} TTS provider updated to '{update.provider}'")

    return {
        "success": True,
        "message": f"TTS provider updated to '{update.provider}'",
        "provider": update.provider,
        "config": tts_config
    }


# ============================================================================
# Kokoro-Specific Endpoints
# ============================================================================

@router.get("/kokoro/status", response_model=ProviderStatusResponse)
async def get_kokoro_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read"))
):
    """
    Get Kokoro TTS service status.

    Specialized endpoint for Kokoro to check service availability.
    Similar to Ollama health check pattern.

    Requires: hub.read permission
    """
    return await get_provider_status("kokoro", db, current_user)


@router.get("/kokoro/voices", response_model=List[VoiceInfoResponse])
def get_kokoro_voices(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read"))
):
    """
    Get available Kokoro voices.

    Returns all Kokoro voices organized by language.

    Requires: hub.read permission
    """
    return get_provider_voices("kokoro", db, current_user)


@router.get("/kokoro/voices/{language}", response_model=List[VoiceInfoResponse])
def get_kokoro_voices_by_language(
    language: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("hub.read"))
):
    """
    Get Kokoro voices filtered by language.

    Args:
        language: Language code (e.g., "pt", "en")

    Returns voices available for the specified language.

    Requires: hub.read permission
    """
    provider = TTSProviderRegistry.get_provider("kokoro", db)
    if not provider:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kokoro provider not available"
        )

    try:
        # Get voices filtered by language
        all_voices = provider.get_available_voices()
        filtered_voices = [v for v in all_voices if v.language == language]

        if not filtered_voices:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No voices found for language '{language}'"
            )

        return [
            VoiceInfoResponse(
                voice_id=v.voice_id,
                name=v.name,
                language=v.language,
                gender=v.gender,
                description=v.description,
                provider=v.provider
            )
            for v in filtered_voices
        ]
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get Kokoro voices: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get voices: {str(e)}"
        )
