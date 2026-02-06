"""
OpenAI TTS Provider
Implements TTS using OpenAI's Text-to-Speech API.

Pricing (as of 2025):
- tts-1: $0.015 per 1,000 characters
- tts-1-hd: $0.030 per 1,000 characters
"""

import os
import logging
import tempfile
from typing import Dict, List, Optional, Any
from pathlib import Path

from openai import OpenAI

from .tts_provider import (
    TTSProvider,
    TTSRequest,
    TTSResponse,
    VoiceInfo,
    ProviderStatus
)
from services.api_key_service import get_api_key


logger = logging.getLogger(__name__)


class OpenAITTSProvider(TTSProvider):
    """
    OpenAI TTS Provider.
    Premium quality text-to-speech using OpenAI's API.

    Supports:
    - 6 voices: alloy, echo, fable, onyx, nova, shimmer
    - 2 models: tts-1 (standard), tts-1-hd (high quality)
    - Multiple formats: mp3, opus, aac, flac, wav, pcm
    - Speed adjustment: 0.25 to 4.0x
    """

    # Available voices
    VOICES = {
        "alloy": VoiceInfo(
            voice_id="alloy",
            name="Alloy",
            language="en",
            gender="neutral",
            description="Balanced, neutral voice",
            provider="openai"
        ),
        "echo": VoiceInfo(
            voice_id="echo",
            name="Echo",
            language="en",
            gender="male",
            description="Clear, professional voice",
            provider="openai"
        ),
        "fable": VoiceInfo(
            voice_id="fable",
            name="Fable",
            language="en",
            gender="neutral",
            description="Expressive storytelling voice",
            provider="openai"
        ),
        "onyx": VoiceInfo(
            voice_id="onyx",
            name="Onyx",
            language="en",
            gender="male",
            description="Deep, authoritative voice",
            provider="openai"
        ),
        "nova": VoiceInfo(
            voice_id="nova",
            name="Nova",
            language="en",
            gender="female",
            description="Warm, conversational voice",
            provider="openai"
        ),
        "shimmer": VoiceInfo(
            voice_id="shimmer",
            name="Shimmer",
            language="en",
            gender="female",
            description="Bright, energetic voice",
            provider="openai"
        ),
    }

    # Available models with pricing
    MODELS = {
        "tts-1": {"name": "Standard", "cost_per_1k": 0.015},
        "tts-1-hd": {"name": "HD Quality", "cost_per_1k": 0.030},
    }

    # Supported formats
    SUPPORTED_FORMATS = ["mp3", "opus", "aac", "flac", "wav", "pcm"]

    def __init__(self, db=None, token_tracker=None):
        super().__init__(db=db, token_tracker=token_tracker)
        self.client: Optional[OpenAI] = None
        self._api_key: Optional[str] = None

    def get_provider_name(self) -> str:
        return "openai"

    def get_display_name(self) -> str:
        return "OpenAI TTS"

    def _get_api_key(self) -> Optional[str]:
        """Get OpenAI API key from database or environment."""
        if self._api_key:
            return self._api_key

        # Try database first
        if self.db:
            key = get_api_key("openai", self.db)
            if key:
                self._api_key = key
                return key

        # Fall back to environment variable
        key = os.getenv("OPENAI_API_KEY")
        if key:
            self._api_key = key

        return self._api_key

    def _get_client(self) -> Optional[OpenAI]:
        """Get or create OpenAI client."""
        if self.client:
            return self.client

        api_key = self._get_api_key()
        if not api_key:
            return None

        self.client = OpenAI(api_key=api_key)
        return self.client

    def get_available_voices(self) -> List[VoiceInfo]:
        return list(self.VOICES.values())

    def get_default_voice(self) -> str:
        return "nova"

    def get_supported_formats(self) -> List[str]:
        return self.SUPPORTED_FORMATS.copy()

    def get_supported_languages(self) -> List[str]:
        # OpenAI TTS supports many languages but defaults to the voice's native language
        return ["en", "es", "fr", "de", "it", "pt", "pl", "ja", "zh", "ko", "ru", "ar", "hi"]

    def get_speed_range(self) -> tuple:
        return (0.25, 4.0)

    def get_pricing_info(self) -> Dict[str, Any]:
        return {
            "model": "tts-1",
            "cost_per_1k_chars": 0.015,
            "currency": "USD",
            "is_free": False,
            "models": self.MODELS
        }

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """
        Synthesize audio using OpenAI TTS API.

        Args:
            request: TTSRequest with text and configuration

        Returns:
            TTSResponse with audio file path or error
        """
        try:
            # Get client
            client = self._get_client()
            if not client:
                return TTSResponse(
                    success=False,
                    provider=self.provider_name,
                    error="OpenAI API key not configured"
                )

            # Validate and normalize parameters
            voice = request.voice if request.voice in self.VOICES else "nova"
            model = "tts-1"  # Default model
            response_format = request.response_format if request.response_format in self.SUPPORTED_FORMATS else "opus"
            speed = max(0.25, min(4.0, request.speed))

            # Truncate text if too long (API limit is ~4096 characters)
            text = request.text
            max_chars = 4000
            if len(text) > max_chars:
                self.logger.warning(f"Text too long ({len(text)} chars), truncating to {max_chars}")
                text = text[:max_chars] + "..."

            self.logger.info(
                f"Generating OpenAI TTS: {len(text)} chars, voice={voice}, "
                f"model={model}, format={response_format}"
            )

            # Create audio file in shared volume directory (accessible by MCP containers)
            # Map format to file extension (WhatsApp compatibility)
            extension_map = {
                "opus": "ogg",
                "mp3": "mp3",
                "aac": "m4a",  # AAC in M4A container for WhatsApp
                "flac": "flac",
                "wav": "wav",
                "pcm": "pcm",
            }
            file_extension = extension_map.get(response_format, response_format)

            # Use shared tsushin_audio directory (Docker volume shared with MCP containers)
            temp_dir = Path(tempfile.gettempdir()) / "tsushin_audio"
            temp_dir.mkdir(exist_ok=True)

            audio_path = str(temp_dir / f"openai_{request.message_id or 'response'}.{file_extension}")

            try:
                # Call OpenAI TTS API
                response = client.audio.speech.create(
                    model=model,
                    voice=voice,
                    input=text,
                    response_format=response_format,
                    speed=speed
                )

                # Write audio data to file with explicit flush
                with open(audio_path, "wb") as f:
                    for chunk in response.iter_bytes():
                        f.write(chunk)
                    f.flush()
                    os.fsync(f.fileno())

                # Get file size
                audio_size = os.path.getsize(audio_path)

                # Calculate cost
                char_count = len(text)
                cost_per_1k = self.MODELS[model]["cost_per_1k"]
                estimated_cost = (char_count / 1000.0) * cost_per_1k

                self.logger.info(f"OpenAI TTS generated: {audio_path} ({audio_size} bytes)")

                # Track usage
                self._track_usage(
                    char_count=char_count,
                    model_name=model,
                    agent_id=request.agent_id,
                    sender_key=request.sender_key,
                    message_id=request.message_id
                )

                return TTSResponse(
                    success=True,
                    audio_path=audio_path,
                    provider=self.provider_name,
                    audio_size_bytes=audio_size,
                    format=response_format,
                    characters_processed=char_count,
                    estimated_cost=estimated_cost,
                    voice_used=voice,
                    language_used=request.language or "en",  # VOICE-002 Fix: Add for consistency with Kokoro
                    speed_used=speed,
                    metadata={
                        "model": model,
                        "is_audio_response": True
                    }
                )

            except Exception as e:
                # Clean up temp file on error
                if os.path.exists(audio_path):
                    try:
                        os.unlink(audio_path)
                    except:
                        pass
                raise e

        except Exception as e:
            self.logger.error(f"OpenAI TTS synthesis failed: {e}", exc_info=True)
            return TTSResponse(
                success=False,
                provider=self.provider_name,
                error=f"OpenAI TTS synthesis failed: {str(e)}"
            )

    async def health_check(self) -> ProviderStatus:
        """
        Check OpenAI API availability.

        Returns:
            ProviderStatus with health information
        """
        try:
            api_key = self._get_api_key()
            if not api_key:
                return ProviderStatus(
                    provider=self.provider_name,
                    status="not_configured",
                    message="OpenAI API key not configured",
                    available=False,
                    details={"hint": "Add OpenAI API key in Hub settings"}
                )

            # Try to create client (validates key format)
            client = self._get_client()
            if not client:
                return ProviderStatus(
                    provider=self.provider_name,
                    status="unavailable",
                    message="Failed to initialize OpenAI client",
                    available=False
                )

            # Note: We don't make an actual API call to avoid costs
            # Just verify the key is present and client can be created
            return ProviderStatus(
                provider=self.provider_name,
                status="healthy",
                message="OpenAI TTS is available",
                available=True,
                details={
                    "voices": len(self.VOICES),
                    "models": list(self.MODELS.keys()),
                    "api_key_configured": True
                }
            )

        except Exception as e:
            self.logger.error(f"OpenAI health check failed: {e}")
            return ProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message=f"Health check failed: {str(e)}",
                available=False
            )
