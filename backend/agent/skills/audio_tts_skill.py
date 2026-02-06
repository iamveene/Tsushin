"""
Audio TTS Response Skill
Converts text responses to audio using pluggable TTS providers.

Uses the TTSProviderRegistry to support multiple providers:
- OpenAI TTS: Premium quality, costs $15-30/1M chars
- Kokoro TTS: Free open-source, supports PTBR and multiple languages
- ElevenLabs: Coming soon (premium voice AI)
"""

import logging
from typing import Dict, Any, Optional, TYPE_CHECKING

from agent.skills.base import BaseSkill, InboundMessage, SkillResult
from hub.providers import TTSProviderRegistry, TTSRequest

if TYPE_CHECKING:
    from analytics.token_tracker import TokenTracker

logger = logging.getLogger(__name__)


class AudioTTSSkill(BaseSkill):
    """
    Multi-provider Audio TTS: Convert text responses to audio.

    When enabled, this skill converts ALL agent responses to audio messages.
    It does NOT handle incoming messages - it transforms outgoing responses.

    PROVIDERS (via TTSProviderRegistry):
    - OpenAI TTS: Premium quality, costs $15-30/1M chars
    - Kokoro TTS: Free open-source, supports PTBR and multiple languages
    - ElevenLabs: Coming soon

    Configuration:
    {
        "provider": "kokoro",          # "openai", "kokoro", or "elevenlabs"
        "voice": "pf_dora",            # Provider-specific voice
        "response_format": "opus",     # Audio format: mp3, opus, aac, flac, wav
        "speed": 1.0,                  # OpenAI: 0.25-4.0, Kokoro: 0.5-2.0
        "language": "pt"               # Kokoro only: pt, en, es, ja, etc.
    }
    """

    skill_type = "audio_tts"
    skill_name = "Audio TTS Response"
    skill_description = "Convert text responses to audio using OpenAI, Kokoro, or ElevenLabs TTS"
    execution_mode = "passive"  # Response processing hook for TTS conversion

    def __init__(self, token_tracker: Optional["TokenTracker"] = None):
        super().__init__()
        self.token_tracker = token_tracker

    async def can_handle(self, message: InboundMessage) -> bool:
        """
        This skill NEVER handles incoming messages.
        It only transforms outgoing responses via process_response().

        Returns:
            Always False - this skill doesn't process incoming messages
        """
        return False

    async def process(self, message: InboundMessage, config: Dict[str, Any]) -> SkillResult:
        """
        Not used - this skill only processes outgoing responses.
        """
        return SkillResult(
            success=False,
            output="❌ AudioTTSSkill only processes responses, not incoming messages",
            metadata={"error": "wrong_method"}
        )

    async def process_response(
        self,
        response_text: str,
        config: Dict[str, Any],
        agent_id: Optional[int] = None,
        sender_key: Optional[str] = None,
        message_id: Optional[str] = None
    ) -> SkillResult:
        """
        Convert text response to audio using configured TTS provider.

        Uses TTSProviderRegistry to dynamically select and use the appropriate
        provider based on configuration.

        Args:
            response_text: The text to convert to audio
            config: Skill configuration with provider, voice, format, speed
            agent_id: Agent ID for token tracking (optional)
            sender_key: Sender identifier for token tracking (optional)
            message_id: Message ID for token tracking (optional)

        Returns:
            SkillResult with audio file path or error
        """
        # Get provider from config (default to kokoro - FREE!)
        provider_name = config.get("provider", "kokoro").lower()

        # Get provider instance from registry
        # TTS-001 Fix: Pass db_session for API key lookup (required by OpenAI, ElevenLabs)
        provider = TTSProviderRegistry.get_provider(
            provider_name,
            db=self._db_session,
            token_tracker=self.token_tracker
        )

        if not provider:
            # Try to give helpful error message
            available = TTSProviderRegistry.get_available_providers()
            return SkillResult(
                success=False,
                output=f"❌ TTS provider '{provider_name}' not available",
                metadata={
                    "error": "provider_not_available",
                    "requested_provider": provider_name,
                    "available_providers": available
                }
            )

        # Check provider status for coming_soon providers
        provider_config = TTSProviderRegistry.get_provider_config(provider_name)
        if provider_config.get("status") == "coming_soon":
            return SkillResult(
                success=False,
                output=f"❌ {provider.get_display_name()} is coming soon!",
                metadata={
                    "error": "provider_coming_soon",
                    "provider": provider_name
                }
            )

        # Build TTS request
        try:
            request = TTSRequest(
                text=response_text,
                voice=config.get("voice", provider.get_default_voice()),
                language=config.get("language", "pt"),
                speed=config.get("speed", 1.0),
                response_format=config.get("response_format", "opus"),
                agent_id=agent_id,
                sender_key=sender_key,
                message_id=message_id
            )
        except ValueError as e:
            return SkillResult(
                success=False,
                output=f"❌ Invalid TTS request: {str(e)}",
                metadata={"error": "invalid_request", "details": str(e)}
            )

        # Synthesize audio
        logger.info(
            f"TTS synthesis: provider={provider_name}, voice={request.voice}, "
            f"text_length={len(response_text)}"
        )

        tts_response = await provider.synthesize(request)

        # Convert TTSResponse to SkillResult
        if tts_response.success:
            return SkillResult(
                success=True,
                output=f"🔊 Audio generated ({tts_response.audio_size_bytes} bytes, {provider_name})",
                metadata={
                    "audio_path": tts_response.audio_path,
                    "provider": tts_response.provider,
                    "voice": tts_response.voice_used,
                    "language": tts_response.language_used,
                    "format": tts_response.format,
                    "speed": tts_response.speed_used,
                    "text_length": tts_response.characters_processed,
                    "audio_size": tts_response.audio_size_bytes,
                    "cost": tts_response.estimated_cost,
                    "is_audio_response": True,  # Flag for router to send as audio
                    **tts_response.metadata
                },
                processed_content=tts_response.audio_path
            )
        else:
            return SkillResult(
                success=False,
                output=f"❌ TTS generation failed: {tts_response.error}",
                metadata={
                    "error": tts_response.error,
                    "provider": provider_name,
                    **tts_response.metadata
                }
            )

    @classmethod
    def get_available_providers(cls) -> list:
        """
        Get list of available TTS providers.

        Returns:
            List of provider info dicts
        """
        return TTSProviderRegistry.list_providers()

    @classmethod
    def get_default_config(cls) -> Dict[str, Any]:
        """
        Get default configuration for TTS.

        Returns:
            Dict with default config values
        """
        return {
            "provider": "kokoro",  # Default to FREE Kokoro
            "voice": "pf_dora",    # Kokoro PT-BR female voice
            "response_format": "opus",  # WhatsApp-compatible format
            "speed": 1.0,          # Normal speed
            "language": "pt"       # Portuguese (Kokoro only)
        }

    @classmethod
    def get_config_schema(cls) -> Dict[str, Any]:
        """
        Get JSON schema for skill configuration (for UI validation).

        Returns:
            Dict with JSON schema for configuration fields
        """
        # Get available providers from registry
        available_providers = TTSProviderRegistry.get_registered_providers()
        if not available_providers:
            available_providers = ["openai", "kokoro"]

        return {
            "type": "object",
            "properties": {
                "provider": {
                    "type": "string",
                    "title": "TTS Provider",
                    "description": "Text-to-speech provider to use",
                    "default": "kokoro",
                    "enum": available_providers,
                    "enumDescriptions": {
                        "openai": "OpenAI TTS ($15-30/1M chars, premium quality)",
                        "kokoro": "Kokoro TTS (FREE, open-source, PTBR support)",
                        "elevenlabs": "ElevenLabs (coming soon)"
                    }
                },
                "voice": {
                    "type": "string",
                    "title": "Voice",
                    "description": "Voice profile (provider-specific)",
                    "default": "pf_dora",
                    "enum": [
                        # Kokoro Portuguese
                        "pf_dora", "pm_alex", "pm_santa",
                        # Kokoro English
                        "af_bella", "af_sarah", "am_adam", "am_michael",
                        "bf_emma", "bm_george",
                        # OpenAI
                        "alloy", "echo", "fable", "onyx", "nova", "shimmer"
                    ],
                    "enumDescriptions": {
                        "pf_dora": "Kokoro PT-BR female (recommended, FREE)",
                        "pm_alex": "Kokoro PT-BR male (FREE)",
                        "pm_santa": "Kokoro PT-BR male alternative (FREE)",
                        "af_bella": "Kokoro American EN female (FREE)",
                        "af_sarah": "Kokoro American EN female professional (FREE)",
                        "am_adam": "Kokoro American EN male (FREE)",
                        "am_michael": "Kokoro American EN male casual (FREE)",
                        "bf_emma": "Kokoro British EN female (FREE)",
                        "bm_george": "Kokoro British EN male (FREE)",
                        "alloy": "OpenAI balanced, neutral",
                        "echo": "OpenAI clear, professional",
                        "fable": "OpenAI expressive storytelling",
                        "onyx": "OpenAI deep, authoritative",
                        "nova": "OpenAI warm, conversational",
                        "shimmer": "OpenAI bright, energetic"
                    }
                },
                "language": {
                    "type": "string",
                    "title": "Language",
                    "description": "Language for synthesis (Kokoro only)",
                    "default": "pt",
                    "enum": ["pt", "en", "es", "ja", "zh", "fr", "de", "it"],
                    "enumDescriptions": {
                        "pt": "Portuguese (PTBR)",
                        "en": "English",
                        "es": "Spanish",
                        "ja": "Japanese",
                        "zh": "Chinese",
                        "fr": "French",
                        "de": "German",
                        "it": "Italian"
                    }
                },
                "response_format": {
                    "type": "string",
                    "title": "Audio Format",
                    "description": "Audio output format",
                    "default": "opus",
                    "enum": ["mp3", "opus", "aac", "flac", "wav"],
                    "enumDescriptions": {
                        "opus": "WhatsApp-compatible (recommended)",
                        "mp3": "Universal compatibility",
                        "aac": "Good quality, smaller files",
                        "flac": "Lossless audio",
                        "wav": "Uncompressed audio"
                    }
                },
                "speed": {
                    "type": "number",
                    "title": "Speed",
                    "description": "Speech speed (OpenAI: 0.25-4.0, Kokoro: 0.5-2.0)",
                    "default": 1.0,
                    "minimum": 0.25,
                    "maximum": 4.0
                }
            },
            "required": []
        }
