"""
TTS Provider - Abstract Base Class
Defines the interface that all TTS providers must implement.

Provider-agnostic text-to-speech architecture enabling agents to use
different TTS services (OpenAI, Kokoro, ElevenLabs) without code changes.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
import logging


@dataclass
class VoiceInfo:
    """
    Information about an available voice.
    Provider-agnostic representation of a voice option.
    """
    voice_id: str                  # Provider-specific voice ID (e.g., "nova", "af_bella")
    name: str                      # Human-readable name
    language: str                  # Language code (e.g., "en", "pt")
    gender: Optional[str] = None   # "male", "female", or None
    description: Optional[str] = None
    preview_url: Optional[str] = None
    is_premium: bool = False       # Whether voice requires premium/paid tier
    provider: Optional[str] = None # Provider name for UI display

    def __str__(self) -> str:
        return f"{self.name} ({self.voice_id}) - {self.language}"


@dataclass
class TTSRequest:
    """
    Standardized TTS request.
    Provider-agnostic representation of synthesis parameters.
    """
    text: str                      # Text to synthesize (required)
    voice: str = "nova"            # Voice ID (provider-specific)
    language: str = "en"           # Language code for synthesis
    speed: float = 1.0             # Speech speed multiplier
    response_format: str = "opus"  # Audio format: mp3, opus, aac, flac, wav, pcm

    # Optional tracking metadata
    agent_id: Optional[int] = None
    sender_key: Optional[str] = None
    message_id: Optional[str] = None

    def __post_init__(self):
        """Validate request parameters"""
        if not self.text or not self.text.strip():
            raise ValueError("Text cannot be empty")

        if len(self.text) > 10000:
            raise ValueError("Text exceeds maximum length of 10000 characters")

        if self.speed < 0.25 or self.speed > 4.0:
            raise ValueError("Speed must be between 0.25 and 4.0")

        valid_formats = {"mp3", "opus", "aac", "flac", "wav", "pcm", "ogg"}
        if self.response_format not in valid_formats:
            raise ValueError(f"Invalid format. Must be one of: {valid_formats}")


@dataclass
class TTSResponse:
    """
    Standardized TTS response.
    Contains synthesis results and metadata from any provider.
    """
    success: bool
    audio_path: Optional[str] = None   # Path to generated audio file
    audio_data: Optional[bytes] = None # Raw audio data (optional)
    provider: str = ""                 # Provider identifier (e.g., "openai", "kokoro")
    error: Optional[str] = None

    # Audio metadata
    duration_seconds: Optional[float] = None
    audio_size_bytes: Optional[int] = None
    format: Optional[str] = None

    # Cost tracking
    characters_processed: int = 0
    estimated_cost: float = 0.0        # Cost in USD

    # Request metadata
    voice_used: Optional[str] = None
    language_used: Optional[str] = None
    speed_used: Optional[float] = None

    metadata: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __str__(self) -> str:
        if self.success:
            return f"TTSResponse(provider={self.provider}, size={self.audio_size_bytes}B, cost=${self.estimated_cost:.4f})"
        return f"TTSResponse(error={self.error})"


@dataclass
class ProviderStatus:
    """
    TTS provider health status.
    """
    provider: str
    status: str                    # "healthy", "degraded", "unavailable", "not_configured"
    message: str
    available: bool = False
    latency_ms: Optional[int] = None
    details: Dict = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.utcnow)


class TTSProvider(ABC):
    """
    Abstract base class for TTS providers.
    All TTS providers (OpenAI, Kokoro, ElevenLabs, etc.) must implement this interface.

    This enables provider-agnostic text-to-speech where agents can switch
    between different providers without code changes.
    """

    def __init__(self, db=None, token_tracker=None):
        """
        Initialize provider.

        Args:
            db: Database session (optional, for API key lookup)
            token_tracker: TokenTracker instance for usage tracking
        """
        self.db = db
        self.token_tracker = token_tracker
        self.provider_name = self.get_provider_name()
        self.logger = logging.getLogger(f"{__name__}.{self.provider_name}")

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Return provider identifier.

        Returns:
            Provider name (e.g., 'openai', 'kokoro', 'elevenlabs')
        """
        pass

    @abstractmethod
    def get_display_name(self) -> str:
        """
        Return human-readable provider name.

        Returns:
            Display name (e.g., 'OpenAI TTS', 'Kokoro', 'ElevenLabs')
        """
        pass

    @abstractmethod
    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """
        Synthesize audio from text.

        Args:
            request: Standardized TTS request

        Returns:
            TTSResponse with audio file path or error
        """
        pass

    @abstractmethod
    def get_available_voices(self) -> List[VoiceInfo]:
        """
        Get list of available voices for this provider.

        Returns:
            List of VoiceInfo objects describing available voices
        """
        pass

    @abstractmethod
    async def health_check(self) -> ProviderStatus:
        """
        Check provider service availability.

        Returns:
            ProviderStatus with health information
        """
        pass

    def get_default_voice(self) -> str:
        """
        Get default voice for this provider.

        Returns:
            Default voice ID
        """
        voices = self.get_available_voices()
        if voices:
            return voices[0].voice_id
        return "default"

    def get_supported_formats(self) -> List[str]:
        """
        Get list of supported audio formats.

        Returns:
            List of format strings (e.g., ["mp3", "opus", "wav"])
        """
        return ["mp3", "opus", "aac", "flac", "wav"]

    def get_supported_languages(self) -> List[str]:
        """
        Get list of supported language codes.

        Returns:
            List of language codes (e.g., ["en", "pt", "es"])
        """
        return ["en"]

    def get_speed_range(self) -> tuple:
        """
        Get valid speed range for this provider.

        Returns:
            Tuple of (min_speed, max_speed)
        """
        return (0.5, 2.0)

    def get_pricing_info(self) -> Dict[str, Any]:
        """
        Get pricing information for this provider.

        Returns:
            Dict with pricing details
        """
        return {
            "model": "unknown",
            "cost_per_1k_chars": 0.0,
            "currency": "USD",
            "is_free": False
        }

    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get provider information and capabilities.

        Returns:
            Provider info dict
        """
        return {
            "name": self.provider_name,
            "display_name": self.get_display_name(),
            "supported_formats": self.get_supported_formats(),
            "supported_languages": self.get_supported_languages(),
            "speed_range": self.get_speed_range(),
            "pricing": self.get_pricing_info(),
            "voice_count": len(self.get_available_voices()),
            "default_voice": self.get_default_voice()
        }

    def _track_usage(
        self,
        char_count: int,
        model_name: str,
        agent_id: Optional[int] = None,
        sender_key: Optional[str] = None,
        message_id: Optional[str] = None
    ):
        """
        Track TTS usage for analytics.

        Args:
            char_count: Number of characters processed
            model_name: Model name used
            agent_id, sender_key, message_id: Tracking metadata
        """
        if self.token_tracker:
            try:
                # INT-001 Note: prompt_tokens = character count for TTS
                # (Different from audio_transcript which uses seconds)
                self.token_tracker.track_usage(
                    operation_type="audio_tts",
                    model_provider=self.provider_name,
                    model_name=model_name,
                    prompt_tokens=char_count,  # Character count for TTS
                    completion_tokens=0,
                    agent_id=agent_id,
                    skill_type="audio_tts",
                    sender_key=sender_key,
                    message_id=message_id,
                )
            except Exception as e:
                self.logger.warning(f"Failed to track TTS usage: {e}")
