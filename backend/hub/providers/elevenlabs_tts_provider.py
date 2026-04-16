"""
ElevenLabs TTS Provider
Premium voice AI synthesis with high-quality neural voices.

Features:
- High-quality voice synthesis
- Voice cloning
- Multiple language support
- Emotional tone control
"""

import os
import time
import logging
from typing import Dict, List, Optional, Any

import httpx

from .tts_provider import (
    TTSProvider,
    TTSRequest,
    TTSResponse,
    VoiceInfo,
    ProviderStatus
)


logger = logging.getLogger(__name__)

# Module-level voice cache with TTL
_voices_cache: Optional[List[VoiceInfo]] = None
_voices_cache_time: float = 0
_VOICES_CACHE_TTL = 300  # 5 minutes


class ElevenLabsTTSProvider(TTSProvider):
    """
    ElevenLabs TTS Provider

    Premium voice AI synthesis with high-quality neural voices.

    Pricing:
    - Free tier: 10,000 characters/month
    - Starter: $5/month (30,000 chars)
    - Creator: $22/month (100,000 chars)
    - Pro: $99/month (500,000 chars)
    """

    BASE_URL = "https://api.elevenlabs.io/v1"

    # Default voices (fallback when API is unavailable)
    VOICES = {
        "21m00Tcm4TlvDq8ikWAM": VoiceInfo(
            voice_id="21m00Tcm4TlvDq8ikWAM",
            name="Rachel",
            language="en",
            gender="female",
            description="Warm, conversational American female voice",
            is_premium=True,
            provider="elevenlabs"
        ),
        "AZnzlk1XvdvUeBnXmlld": VoiceInfo(
            voice_id="AZnzlk1XvdvUeBnXmlld",
            name="Domi",
            language="en",
            gender="male",
            description="Strong, authoritative male voice",
            is_premium=True,
            provider="elevenlabs"
        ),
        "EXAVITQu4vr4xnSDxMaL": VoiceInfo(
            voice_id="EXAVITQu4vr4xnSDxMaL",
            name="Bella",
            language="en",
            gender="female",
            description="Soft, gentle female voice",
            is_premium=True,
            provider="elevenlabs"
        ),
        "ErXwobaYiN019PkySvjV": VoiceInfo(
            voice_id="ErXwobaYiN019PkySvjV",
            name="Antoni",
            language="en",
            gender="male",
            description="Well-rounded male voice",
            is_premium=True,
            provider="elevenlabs"
        ),
        "MF3mGyEYCl7XYWbV9V6O": VoiceInfo(
            voice_id="MF3mGyEYCl7XYWbV9V6O",
            name="Elli",
            language="en",
            gender="female",
            description="Young, confident female voice",
            is_premium=True,
            provider="elevenlabs"
        ),
    }

    def __init__(self, db=None, token_tracker=None, tenant_id=None):
        super().__init__(db=db, token_tracker=token_tracker, tenant_id=tenant_id)
        self._api_key: Optional[str] = None

    def _get_api_key(self) -> Optional[str]:
        """Get ElevenLabs API key from database (tenant-specific or system-wide)."""
        if self._api_key:
            return self._api_key

        if self.db:
            from services.api_key_service import get_api_key
            key = get_api_key('elevenlabs', self.db, tenant_id=self.tenant_id)
            if key:
                self._api_key = key
                return key

        return None

    def get_provider_name(self) -> str:
        return "elevenlabs"

    def get_display_name(self) -> str:
        return "ElevenLabs"

    def get_available_voices(self) -> List[VoiceInfo]:
        return list(self.VOICES.values())

    def get_default_voice(self) -> str:
        return "21m00Tcm4TlvDq8ikWAM"  # Rachel

    def get_supported_formats(self) -> List[str]:
        return ["mp3", "opus", "wav", "pcm"]

    def get_supported_languages(self) -> List[str]:
        return ["en", "es", "fr", "de", "it", "pt", "pl", "hi", "ar", "zh", "ja", "ko"]

    def get_speed_range(self) -> tuple:
        return (0.5, 2.0)

    def get_pricing_info(self) -> Dict[str, Any]:
        return {
            "model": "eleven_multilingual_v2",
            "cost_per_1k_chars": 0.03,
            "currency": "USD",
            "is_free": False,
            "tiers": {
                "free": {"chars_per_month": 10000, "cost": 0},
                "starter": {"chars_per_month": 30000, "cost": 5},
                "creator": {"chars_per_month": 100000, "cost": 22},
                "pro": {"chars_per_month": 500000, "cost": 99},
            },
        }

    async def list_voices_from_api(self) -> List[VoiceInfo]:
        """Fetch voices dynamically from ElevenLabs API with caching."""
        global _voices_cache, _voices_cache_time

        # Check cache
        if _voices_cache and (time.time() - _voices_cache_time) < _VOICES_CACHE_TTL:
            return _voices_cache

        api_key = self._get_api_key()
        if not api_key:
            return list(self.VOICES.values())

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/voices",
                    headers={"xi-api-key": api_key}
                )

                if response.status_code == 200:
                    data = response.json()
                    voices = []
                    for v in data.get("voices", []):
                        labels = v.get("labels", {})
                        voices.append(VoiceInfo(
                            voice_id=v["voice_id"],
                            name=v.get("name", "Unknown"),
                            language=labels.get("language", "en"),
                            gender=labels.get("gender"),
                            description=labels.get("description") or v.get("description", ""),
                            preview_url=v.get("preview_url"),
                            is_premium=True,
                            provider="elevenlabs"
                        ))

                    if voices:
                        _voices_cache = voices
                        _voices_cache_time = time.time()
                        return voices

        except Exception as e:
            logger.warning(f"Failed to fetch ElevenLabs voices: {e}")

        return list(self.VOICES.values())

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """
        Synthesize text to speech using ElevenLabs API.

        POST /v1/text-to-speech/{voice_id}
        """
        api_key = self._get_api_key()
        if not api_key:
            return TTSResponse(
                success=False,
                provider=self.provider_name,
                error="ElevenLabs API key not configured. Add it via Settings > Integrations."
            )

        voice_id = request.voice or self.get_default_voice()

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.BASE_URL}/text-to-speech/{voice_id}",
                    headers={
                        "xi-api-key": api_key,
                        "Content-Type": "application/json",
                        "Accept": "audio/mpeg"
                    },
                    json={
                        "text": request.text,
                        "model_id": "eleven_multilingual_v2",
                        "voice_settings": {
                            "stability": 0.5,
                            "similarity_boost": 0.5,
                            "style": 0.0,
                            "use_speaker_boost": True
                        }
                    }
                )

                if response.status_code == 200:
                    audio_data = response.content
                    return TTSResponse(
                        success=True,
                        provider=self.provider_name,
                        audio_data=audio_data,
                        format="mp3",
                        audio_size_bytes=len(audio_data),
                        characters_processed=len(request.text),
                        estimated_cost=len(request.text) * 0.00003,  # ~$0.03/1K chars
                        voice_used=voice_id,
                        language_used=request.language,
                        speed_used=request.speed,
                    )
                elif response.status_code == 401:
                    return TTSResponse(
                        success=False,
                        provider=self.provider_name,
                        error="Invalid ElevenLabs API key"
                    )
                elif response.status_code == 422:
                    return TTSResponse(
                        success=False,
                        provider=self.provider_name,
                        error=f"Invalid request: {response.text}"
                    )
                else:
                    return TTSResponse(
                        success=False,
                        provider=self.provider_name,
                        error=f"ElevenLabs API error: {response.status_code}"
                    )

        except httpx.ConnectError:
            return TTSResponse(
                success=False,
                provider=self.provider_name,
                error="Cannot connect to ElevenLabs API"
            )
        except httpx.TimeoutException:
            return TTSResponse(
                success=False,
                provider=self.provider_name,
                error="ElevenLabs API timeout"
            )
        except Exception as e:
            logger.error(f"ElevenLabs synthesis error: {e}", exc_info=True)
            return TTSResponse(
                success=False,
                provider=self.provider_name,
                error=str(e)
            )

    async def health_check(self) -> ProviderStatus:
        """
        Health check for ElevenLabs - validates API key by calling /v1/user.
        """
        api_key = self._get_api_key()
        if not api_key:
            return ProviderStatus(
                provider=self.provider_name,
                status="not_configured",
                message="ElevenLabs API key not configured",
                available=False,
                details={"hint": "Add your API key via Settings > Integrations"}
            )

        try:
            start = time.time()
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.BASE_URL}/user",
                    headers={"xi-api-key": api_key}
                )
                latency = int((time.time() - start) * 1000)

                if response.status_code == 200:
                    user_data = response.json()
                    subscription = user_data.get("subscription", {})
                    return ProviderStatus(
                        provider=self.provider_name,
                        status="healthy",
                        message="ElevenLabs connected",
                        available=True,
                        latency_ms=latency,
                        details={
                            "tier": subscription.get("tier", "unknown"),
                            "character_count": subscription.get("character_count", 0),
                            "character_limit": subscription.get("character_limit", 0),
                        }
                    )
                elif response.status_code == 401:
                    return ProviderStatus(
                        provider=self.provider_name,
                        status="unavailable",
                        message="Invalid API key",
                        available=False,
                        latency_ms=latency,
                    )
                else:
                    return ProviderStatus(
                        provider=self.provider_name,
                        status="unavailable",
                        message=f"API error: {response.status_code}",
                        available=False,
                        latency_ms=latency,
                    )

        except httpx.ConnectError:
            return ProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message="Cannot connect to ElevenLabs API",
                available=False,
            )
        except httpx.TimeoutException:
            return ProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message="Connection timeout",
                available=False,
            )
        except Exception as e:
            logger.error(f"ElevenLabs health check error: {e}", exc_info=True)
            return ProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message=str(e),
                available=False,
            )
