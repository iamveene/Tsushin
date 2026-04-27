"""
Phase 5.0 Week 3: Audio Transcription Skill
Transcribes audio messages using a tenant ASR instance when configured,
falling back to OpenAI Whisper.
Phase 7.2: Added token tracking for Whisper API usage
"""

import os
import logging
from typing import Dict, Any, Optional, TYPE_CHECKING
from datetime import datetime

from agent.skills.base import BaseSkill, InboundMessage, SkillResult
from services.api_key_service import get_api_key
from hub.providers.asr_provider import ASRRequest
from hub.providers.asr_registry import ASRProviderRegistry

if TYPE_CHECKING:
    from analytics.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class AudioTranscriptSkill(BaseSkill):
    """
    Transcribes audio messages to text using OpenAI Whisper API.

    Supports:
    - Audio formats: ogg, mp3, wav, m4a, flac, webm
    - Automatic language detection
    - Configurable model (whisper-1)

    Configuration:
    {
        "api_key": "sk-...",        # OpenAI API key (required)
        "language": "auto",         # Language code or "auto" for detection
        "model": "whisper-1",       # Whisper model to use
        "response_mode": "conversational"  # "conversational" or "transcript_only"
    }

    Response Modes:
    - "conversational" (default): Transcribe → Pass to AI → Natural response
    - "transcript_only": Transcribe → Return transcript text only (no AI processing)
    """

    skill_type = "audio_transcript"
    skill_name = "Audio Communication"
    skill_description = "Process audio messages with conversational AI or transcription-only mode"
    execution_mode = "special"  # Media-triggered (audio file detection)
    # Wizard metadata: only for audio/hybrid agents; force-enabled for those types.
    applies_to = ["audio", "hybrid"]
    auto_enabled_for = ["audio", "hybrid"]

    # Supported audio MIME types
    SUPPORTED_FORMATS = {
        "audio/ogg",
        "audio/mpeg",
        "audio/mp3",
        "audio/wav",
        "audio/m4a",
        "audio/x-m4a",
        "audio/flac",
        "audio/webm",
    }

    def __init__(self, token_tracker: Optional["TokenTracker"] = None):
        super().__init__()
        self.token_tracker = token_tracker  # Phase 7.2

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        Check if message is an audio message we can transcribe.

        Args:
            message: Inbound message to evaluate

        Returns:
            True if message has audio media type
        """
        if not message.media_type:
            return False

        # Check if media type is audio
        media_type_lower = message.media_type.lower()
        logger.info(f"DEBUG: Checking media_type='{media_type_lower}' against SUPPORTED_FORMATS={self.SUPPORTED_FORMATS}")

        # Check exact match first
        if media_type_lower in self.SUPPORTED_FORMATS:
            logger.info(f"Audio message detected (exact match): {message.media_type}")
            return True

        # Check if it starts with "audio" (handles "audio" without subtype)
        if media_type_lower.startswith("audio"):
            logger.info(f"Audio message detected (starts with audio): {message.media_type}")
            return True

        logger.info(f"Not an audio message: {message.media_type}")
        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Transcribe the audio message using Whisper API.

        Args:
            message: The audio message to transcribe
            config: Skill configuration with api_key, language, model

        Returns:
            SkillResult with transcription text or error
        """
        try:
            # BUG-357 FIX: Prefer the caller-provided DB session (set_db_session)
            # over creating a new one, and pass tenant_id for tenant-scoped keys.
            db = self._db_session
            own_session = False
            if not db:
                from sqlalchemy.orm import sessionmaker
                from db import get_engine
                import settings
                engine = get_engine(settings.DATABASE_URL)
                SessionLocal = sessionmaker(bind=engine)
                db = SessionLocal()
                own_session = True

            # Get audio file path
            audio_path = message.media_path
            if not audio_path or not os.path.exists(audio_path):
                return SkillResult(
                    success=False,
                    output=f"❌ Audio file not found: {audio_path}",
                    metadata={"error": "audio_file_not_found"}
                )

            logger.info(f"Transcribing audio: {audio_path}")

            # Prepare transcription parameters
            language = config.get("language", "auto")
            model = config.get("model", "whisper-1")
            tenant_id = config.get("tenant_id")
            transcript = ""
            provider_name = "openai"
            provider_model = model

            # Track D: resolve ASR in this order:
            # 1. Explicit agent-pinned instance (legacy ``asr_instance_id`` or
            #    ``asr_mode='instance'``)
            # 2. Tenant default instance (``asr_mode='tenant_default'``)
            # 3. OpenAI Whisper fallback (explicit ``asr_mode='openai'`` or no
            #    local/default instance available)
            asr_mode = config.get("asr_mode")
            asr_instance_id = config.get("asr_instance_id")
            resolved_asr_instance_id = asr_instance_id
            resolved_asr_instance = None
            if tenant_id and db and asr_mode != "openai":
                try:
                    from services.whisper_instance_service import WhisperInstanceService

                    if asr_mode == "tenant_default":
                        resolved_asr_instance_id, resolved_asr_instance = (
                            WhisperInstanceService.get_tenant_default(tenant_id, db)
                        )
                    elif asr_instance_id:
                        resolved_asr_instance = WhisperInstanceService.get_instance(
                            asr_instance_id,
                            tenant_id,
                            db,
                        )

                    if (
                        resolved_asr_instance
                        and resolved_asr_instance.is_active
                        and resolved_asr_instance.vendor == "speaches"
                    ):
                        provider = ASRProviderRegistry.get_instance_provider(
                            resolved_asr_instance,
                            db=db,
                            token_tracker=self.token_tracker,
                            tenant_id=tenant_id,
                        )
                        provider_model = (
                            resolved_asr_instance.default_model
                            if model == "whisper-1"
                            else model
                        )
                        response = await provider.transcribe(
                            ASRRequest(
                                audio_path=audio_path,
                                model=provider_model,
                                language=language,
                                tenant_id=tenant_id,
                                agent_id=getattr(message, "agent_id", None),
                                sender_key=getattr(message, "sender", None),
                                message_id=getattr(message, "message_id", None),
                            )
                        )
                        if response.success:
                            transcript = response.text.strip()
                            provider_name = response.provider
                        else:
                            logger.warning(
                                "ASR instance %s transcription failed, falling back to OpenAI: %s",
                                resolved_asr_instance_id,
                                response.error,
                            )
                except Exception as asr_err:
                    logger.warning(
                        "ASR instance %s path failed, falling back to OpenAI: %s",
                        resolved_asr_instance_id,
                        asr_err,
                    )

            if not transcript:
                api_key = None
                provider_instance_id = config.get("provider_instance_id")
                if provider_instance_id and tenant_id:
                    from services.provider_instance_service import ProviderInstanceService

                    instance = ProviderInstanceService.get_instance(provider_instance_id, tenant_id, db)
                    if instance and instance.vendor == "openai" and instance.is_active:
                        api_key = ProviderInstanceService.resolve_api_key(instance, db)

                if not api_key:
                    api_key = get_api_key("openai", db, tenant_id=tenant_id) or config.get("api_key")

                if not api_key:
                    return SkillResult(
                        success=False,
                        output="❌ OpenAI API key not configured",
                        metadata={"error": "missing_api_key"},
                    )

                provider = ASRProviderRegistry.get_openai_provider(
                    db=db,
                    token_tracker=self.token_tracker,
                    tenant_id=tenant_id,
                    api_key=api_key,
                )
                response = await provider.transcribe(
                    ASRRequest(
                        audio_path=audio_path,
                        model=model,
                        language=language,
                        tenant_id=tenant_id,
                        agent_id=getattr(message, "agent_id", None),
                        sender_key=getattr(message, "sender", None),
                        message_id=getattr(message, "message_id", None),
                    )
                )
                if not response.success:
                    return SkillResult(
                        success=False,
                        output=f"❌ Transcription failed: {response.error or 'unknown error'}",
                        metadata={
                            "error": response.error or "transcription_failed",
                            "audio_path": audio_path,
                            "provider": "openai",
                        },
                    )
                transcript = response.text.strip()
                provider_name = response.provider
                provider_model = model

            if not transcript:
                return SkillResult(
                    success=False,
                    output="❌ Transcription returned empty text",
                    metadata={
                        "error": "empty_transcription",
                        "audio_path": audio_path
                    }
                )

            logger.info(f"Transcription successful: {len(transcript)} chars")

            # Phase 7.2: Track Whisper API usage
            # Whisper pricing is per-second, not tokens, but we track for cost visibility
            # Approximate: ~1 token per second of audio (rough estimate for tracking purposes)
            if self.token_tracker:
                try:
                    # Get audio duration (rough estimate from file size if metadata unavailable)
                    import wave
                    import contextlib

                    duration_seconds = 0
                    try:
                        # Try to get actual duration from audio file
                        with contextlib.closing(wave.open(audio_path, 'r')) as f:
                            frames = f.getnframes()
                            rate = f.getframerate()
                            duration_seconds = frames / float(rate)
                    except:
                        # Fallback: rough estimate from transcript length (~150 words/min, ~2 words/sec)
                        words = len(transcript.split())
                        duration_seconds = max(1, words / 2)  # Rough estimate

                    # Whisper charges per second, but we use "tokens" metaphorically for tracking
                    # 1 token = 1 second of audio for cost calculation purposes
                    estimated_tokens = int(duration_seconds)

                    self.token_tracker.track_usage(
                        operation_type="audio_transcript",
                        model_provider=provider_name,
                        model_name=provider_model,
                        prompt_tokens=estimated_tokens,  # Audio duration in seconds
                        completion_tokens=0,  # No output tokens for transcription
                        agent_id=message.agent_id if hasattr(message, 'agent_id') else None,
                        skill_type="audio_transcript",
                        sender_key=message.sender if hasattr(message, 'sender') else None,
                        message_id=message.message_id if hasattr(message, 'message_id') else None,
                    )
                    logger.info(f"Token tracking: {estimated_tokens} tokens (~{duration_seconds:.1f}s audio)")
                except Exception as track_err:
                    logger.warning(f"Failed to track audio transcription usage: {track_err}")

            # Check response mode
            response_mode = config.get("response_mode", "conversational")
            logger.info(f"DEBUG: response_mode from config = '{response_mode}'")
            logger.info(f"DEBUG: full config = {config}")

            if response_mode == "transcript_only":
                # Return transcript only - this will be sent directly to user (no AI processing)
                return SkillResult(
                    success=True,
                    output=f"📝 Transcript:\n\n{transcript}",
                    metadata={
                        "transcript_length": len(transcript),
                        "audio_path": audio_path,
                        "language": language,
                        "model": provider_model,
                        "provider": provider_name,
                        "response_mode": response_mode,
                        "skip_ai": True  # Signal to skip AI processing
                    },
                    processed_content=None  # Don't pass to AI
                )
            else:
                # Conversational mode - pass transcript to AI for natural response
                return SkillResult(
                    success=True,
                    output=f"🎤 Audio transcribed:\n\n{transcript}",
                    metadata={
                        "transcript_length": len(transcript),
                        "audio_path": audio_path,
                        "language": language,
                        "model": provider_model,
                        "provider": provider_name,
                        "response_mode": response_mode
                    },
                    processed_content=transcript  # Pass to AI for processing
                )

        except Exception as e:
            logger.error(f"Error transcribing audio: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Transcription failed: {str(e)}",
                metadata={
                    "error": str(e),
                    "audio_path": message.media_path
                }
            )
        finally:
            if own_session:
                db.close()

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration for audio transcription.

        Returns:
            Dict with default config values
        """
        return {
            "api_key": None,  # Uses OPENAI_API_KEY from env if not provided
            "asr_mode": "openai",  # openai | tenant_default | instance
            "asr_instance_id": None,  # Prefer a local Whisper/Speaches instance when set
            "language": "auto",  # Auto-detect language
            "model": "whisper-1",  # OpenAI Whisper model
            "response_mode": "conversational"  # "conversational" or "transcript_only"
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for skill configuration (for UI validation).

        Returns:
            Dict with JSON schema for configuration fields
        """
        return {
            "type": "object",
            "properties": {
                "api_key": {
                    "type": "string",
                    "description": "OpenAI API key (uses OPENAI_API_KEY env var if not provided)",
                    "format": "password"
                },
                "asr_mode": {
                    "type": "string",
                    "description": "ASR routing mode: use OpenAI directly, the tenant default ASR instance, or a specific ASR instance id.",
                    "default": "openai",
                    "enum": ["openai", "tenant_default", "instance"]
                },
                "asr_instance_id": {
                    "type": ["integer", "null"],
                    "description": "Optional tenant ASR instance ID (Speaches/OpenAI-compatible Whisper endpoint). Used when asr_mode='instance'.",
                    "default": None
                },
                "language": {
                    "type": "string",
                    "description": "Language code for transcription (e.g., 'en', 'pt', 'es') or 'auto' for detection",
                    "default": "auto",
                    "enum": ["auto", "en", "pt", "es", "fr", "de", "it", "ja", "ko", "zh"]
                },
                "model": {
                    "type": "string",
                    "description": "Whisper model to use",
                    "default": "whisper-1",
                    "enum": ["whisper-1"]
                },
                "response_mode": {
                    "type": "string",
                    "description": "Response mode: 'conversational' (AI processes transcript) or 'transcript_only' (return raw transcript)",
                    "default": "conversational",
                    "enum": ["conversational", "transcript_only"]
                }
            },
            "required": []
        }

    async def process_telegram_voice(
        self,
        voice_file_id: str,
        telegram_client,
        config: Dict[str, Any],
        temp_dir: str = "/tmp"
    ) -> SkillResult:
        """
        Phase 10.1.1: Download and transcribe Telegram voice message.

        Telegram voice messages are OGG format with OPUS codec.
        Whisper API handles OGG natively, so no conversion needed.

        Args:
            voice_file_id: Telegram file_id for the voice message
            telegram_client: TelegramClient instance
            config: Skill configuration
            temp_dir: Temporary directory for downloaded files

        Returns:
            SkillResult with transcription
        """
        import tempfile

        try:
            # Download voice file from Telegram
            ogg_path = os.path.join(temp_dir, f"telegram_voice_{voice_file_id}.ogg")
            await telegram_client.download_file(voice_file_id, ogg_path)

            logger.info(f"Downloaded Telegram voice message to {ogg_path}")

            # Create InboundMessage for processing
            voice_message = InboundMessage(
                id=f"telegram_voice_{voice_file_id}",
                sender="telegram_user",
                sender_key="telegram_user",
                body="[Voice Message]",
                chat_id="telegram_dm",
                chat_name=None,
                is_group=False,
                timestamp=datetime.utcnow(),
                media_type="audio/ogg",
                media_path=ogg_path,
                channel="telegram"  # Skills-as-Tools: Telegram voice message
            )

            # Process with standard transcription
            result = await self.process(voice_message, config)

            # Cleanup temporary file
            if os.path.exists(ogg_path):
                os.remove(ogg_path)
                logger.info(f"Cleaned up temporary file: {ogg_path}")

            return result

        except Exception as e:
            logger.error(f"Error processing Telegram voice message: {e}", exc_info=True)
            return SkillResult(
                success=False,
                output=f"❌ Failed to process Telegram voice message: {str(e)}",
                metadata={"error": str(e)}
            )
