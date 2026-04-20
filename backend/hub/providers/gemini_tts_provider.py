"""
Gemini TTS Provider
Implements TTS using Google's Gemini 3.1 Flash TTS Preview model.

Reference: https://ai.google.dev/gemini-api/docs/models/gemini-3.1-flash-tts-preview

Key characteristics of the preview model:
- Standard generateContent endpoint with response_modalities=["AUDIO"]
- 30 prebuilt voices (Zephyr, Puck, Charon, Kore, ...)
- Output: raw 24 kHz / 16-bit / mono PCM (we wrap in WAV client-side using stdlib `wave`)
- Plain text input + optional inline audio tags ([whispers], [laughs], [excited])
- No SSML, no speed control
- Preview quirk: model occasionally returns text tokens instead of audio → retry up to 2x

Reuses the existing tenant Gemini API key (ApiKey.service = "gemini") — no new credential flow.
"""

import asyncio
import io
import logging
import os
import tempfile
import wave
from pathlib import Path
from typing import Any, Dict, List, Optional

from .tts_provider import (
    ProviderStatus,
    TTSProvider,
    TTSRequest,
    TTSResponse,
    VoiceInfo,
)
from services.api_key_service import get_api_key


logger = logging.getLogger(__name__)


# 30 prebuilt voice presets shipped with gemini-3.1-flash-tts-preview.
# Ordered to match the order in Google's official documentation (2026-04).
_GEMINI_VOICE_PRESETS: List[Dict[str, str]] = [
    {"voice_id": "Zephyr", "description": "Bright"},
    {"voice_id": "Puck", "description": "Upbeat"},
    {"voice_id": "Charon", "description": "Informative"},
    {"voice_id": "Kore", "description": "Firm"},
    {"voice_id": "Fenrir", "description": "Excitable"},
    {"voice_id": "Leda", "description": "Youthful"},
    {"voice_id": "Orus", "description": "Firm"},
    {"voice_id": "Aoede", "description": "Breezy"},
    {"voice_id": "Callirrhoe", "description": "Easy-going"},
    {"voice_id": "Autonoe", "description": "Bright"},
    {"voice_id": "Enceladus", "description": "Breathy"},
    {"voice_id": "Iapetus", "description": "Clear"},
    {"voice_id": "Umbriel", "description": "Easy-going"},
    {"voice_id": "Algieba", "description": "Smooth"},
    {"voice_id": "Despina", "description": "Smooth"},
    {"voice_id": "Erinome", "description": "Clear"},
    {"voice_id": "Algenib", "description": "Gravelly"},
    {"voice_id": "Rasalgethi", "description": "Informative"},
    {"voice_id": "Laomedeia", "description": "Upbeat"},
    {"voice_id": "Achernar", "description": "Soft"},
    {"voice_id": "Alnilam", "description": "Firm"},
    {"voice_id": "Schedar", "description": "Even"},
    {"voice_id": "Gacrux", "description": "Mature"},
    {"voice_id": "Pulcherrima", "description": "Forward"},
    {"voice_id": "Achird", "description": "Friendly"},
    {"voice_id": "Zubenelgenubi", "description": "Casual"},
    {"voice_id": "Vindemiatrix", "description": "Gentle"},
    {"voice_id": "Sadachbia", "description": "Lively"},
    {"voice_id": "Sadaltager", "description": "Knowledgeable"},
    {"voice_id": "Sulafat", "description": "Warm"},
]

_GEMINI_TTS_MODEL = "gemini-3.1-flash-tts-preview"
_GEMINI_PCM_SAMPLE_RATE = 24000
_GEMINI_PCM_SAMPLE_WIDTH = 2  # 16-bit
_GEMINI_PCM_CHANNELS = 1      # mono
_MAX_TEXT_TOKEN_RETRIES = 2


class GeminiTTSProvider(TTSProvider):
    """
    Google Gemini TTS provider (preview).

    Uses gemini-3.1-flash-tts-preview on the standard generateContent endpoint.
    Outputs 24 kHz / 16-bit / mono PCM that we wrap in a WAV container.
    """

    VOICES: Dict[str, VoiceInfo] = {
        entry["voice_id"]: VoiceInfo(
            voice_id=entry["voice_id"],
            name=entry["voice_id"],
            language="auto",
            gender=None,
            description=entry["description"],
            provider="gemini",
        )
        for entry in _GEMINI_VOICE_PRESETS
    }

    SUPPORTED_FORMATS = ["wav", "pcm"]
    SUPPORTED_LANGUAGES = ["auto", "en", "pt", "es", "fr", "de", "it", "ja", "zh", "ko", "hi", "ar"]

    def __init__(self, db=None, token_tracker=None, tenant_id=None):
        super().__init__(db=db, token_tracker=token_tracker, tenant_id=tenant_id)
        self._api_key: Optional[str] = None

    def get_provider_name(self) -> str:
        return "gemini"

    def get_display_name(self) -> str:
        return "Google Gemini TTS"

    def _get_api_key(self) -> Optional[str]:
        if self._api_key:
            return self._api_key
        if self.db:
            key = get_api_key("gemini", self.db, tenant_id=self.tenant_id)
            if key:
                self._api_key = key
        return self._api_key

    def get_available_voices(self) -> List[VoiceInfo]:
        return list(self.VOICES.values())

    def get_default_voice(self) -> str:
        return "Zephyr"

    def get_supported_formats(self) -> List[str]:
        return self.SUPPORTED_FORMATS.copy()

    def get_supported_languages(self) -> List[str]:
        return self.SUPPORTED_LANGUAGES.copy()

    def get_speed_range(self) -> tuple:
        # Gemini TTS preview does not expose speed control.
        return (1.0, 1.0)

    def get_pricing_info(self) -> Dict[str, Any]:
        return {
            "model": _GEMINI_TTS_MODEL,
            "cost_per_1k_chars": 0.0,
            "currency": "USD",
            "is_free": False,
            "notes": "Preview — Google has not published pricing yet (as of 2026-04).",
        }

    @staticmethod
    def _wrap_pcm_as_wav(pcm_bytes: bytes) -> bytes:
        """Wrap raw 24 kHz / 16-bit / mono PCM in a WAV container."""
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as wav_file:
            wav_file.setnchannels(_GEMINI_PCM_CHANNELS)
            wav_file.setsampwidth(_GEMINI_PCM_SAMPLE_WIDTH)
            wav_file.setframerate(_GEMINI_PCM_SAMPLE_RATE)
            wav_file.writeframes(pcm_bytes)
        return buffer.getvalue()

    @staticmethod
    def _extract_audio_bytes(response) -> Optional[bytes]:
        """Pull raw PCM bytes from a Gemini generateContent response, if any."""
        try:
            candidates = getattr(response, "candidates", None) or []
            for candidate in candidates:
                content = getattr(candidate, "content", None)
                if not content:
                    continue
                for part in getattr(content, "parts", []) or []:
                    inline = getattr(part, "inline_data", None)
                    if inline is not None:
                        data = getattr(inline, "data", None)
                        if data:
                            return data
        except Exception:
            # Fall through — caller will treat missing audio as a text-token fallback.
            pass
        return None

    async def _invoke_gemini(self, api_key: str, text: str, voice: str) -> Any:
        """Issue a single generateContent call. Runs the blocking SDK in a thread."""
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=api_key)

        speech_config = types.SpeechConfig(
            voice_config=types.VoiceConfig(
                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=voice)
            )
        )
        generate_config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=speech_config,
        )

        return await asyncio.to_thread(
            client.models.generate_content,
            model=_GEMINI_TTS_MODEL,
            contents=text,
            config=generate_config,
        )

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        try:
            api_key = self._get_api_key()
            if not api_key:
                return TTSResponse(
                    success=False,
                    provider=self.provider_name,
                    error="Gemini API key not configured",
                )

            voice = request.voice if request.voice in self.VOICES else self.get_default_voice()
            text = request.text

            # Keep preview caps modest — the model's input budget is 8K tokens.
            max_chars = 8000
            if len(text) > max_chars:
                self.logger.warning(
                    "Text too long for Gemini TTS (%d chars), truncating to %d",
                    len(text),
                    max_chars,
                )
                text = text[:max_chars]

            self.logger.info(
                "Generating Gemini TTS: %d chars, voice=%s, model=%s",
                len(text),
                voice,
                _GEMINI_TTS_MODEL,
            )

            # Google documents that the TTS preview model occasionally returns text
            # tokens instead of audio. Retry up to 2x before giving up.
            pcm_bytes: Optional[bytes] = None
            last_error: Optional[str] = None
            for attempt in range(_MAX_TEXT_TOKEN_RETRIES + 1):
                try:
                    response = await self._invoke_gemini(api_key, text, voice)
                    pcm_bytes = self._extract_audio_bytes(response)
                    if pcm_bytes:
                        break
                    last_error = "Gemini returned text tokens instead of audio"
                    self.logger.warning(
                        "Gemini TTS attempt %d/%d: %s — retrying",
                        attempt + 1,
                        _MAX_TEXT_TOKEN_RETRIES + 1,
                        last_error,
                    )
                except Exception as call_exc:
                    last_error = str(call_exc)
                    self.logger.warning(
                        "Gemini TTS attempt %d/%d failed: %s",
                        attempt + 1,
                        _MAX_TEXT_TOKEN_RETRIES + 1,
                        last_error,
                    )

            if not pcm_bytes:
                return TTSResponse(
                    success=False,
                    provider=self.provider_name,
                    error=f"Gemini TTS failed after retries: {last_error or 'no audio returned'}",
                )

            wav_bytes = self._wrap_pcm_as_wav(pcm_bytes)

            # Persist under the shared tsushin_audio dir so MCP containers can reach it.
            temp_dir = Path(tempfile.gettempdir()) / "tsushin_audio"
            temp_dir.mkdir(exist_ok=True)
            audio_path = str(
                temp_dir / f"gemini_{request.message_id or 'response'}.wav"
            )

            with open(audio_path, "wb") as f:
                f.write(wav_bytes)
                f.flush()
                os.fsync(f.fileno())

            audio_size = os.path.getsize(audio_path)
            char_count = len(text)

            self._track_usage(
                char_count=char_count,
                model_name=_GEMINI_TTS_MODEL,
                agent_id=request.agent_id,
                sender_key=request.sender_key,
                message_id=request.message_id,
            )

            self.logger.info(
                "Gemini TTS generated: %s (%d bytes)", audio_path, audio_size
            )

            return TTSResponse(
                success=True,
                audio_path=audio_path,
                provider=self.provider_name,
                audio_size_bytes=audio_size,
                format="wav",
                characters_processed=char_count,
                estimated_cost=0.0,  # Pricing TBD
                voice_used=voice,
                language_used=request.language or "auto",
                speed_used=1.0,
                metadata={
                    "model": _GEMINI_TTS_MODEL,
                    "is_audio_response": True,
                    "sample_rate": _GEMINI_PCM_SAMPLE_RATE,
                    "sample_width_bytes": _GEMINI_PCM_SAMPLE_WIDTH,
                    "channels": _GEMINI_PCM_CHANNELS,
                },
            )

        except Exception as e:
            self.logger.error(f"Gemini TTS synthesis failed: {e}", exc_info=True)
            return TTSResponse(
                success=False,
                provider=self.provider_name,
                error=f"Gemini TTS synthesis failed: {str(e)}",
            )

    async def health_check(self) -> ProviderStatus:
        try:
            api_key = self._get_api_key()
            if not api_key:
                return ProviderStatus(
                    provider=self.provider_name,
                    status="not_configured",
                    message="Gemini API key not configured",
                    available=False,
                    details={"hint": "Add Gemini API key in Hub → AI Providers"},
                )

            # Don't burn quota on health checks — just confirm key + SDK are importable.
            try:
                from google import genai  # noqa: F401
                from google.genai import types  # noqa: F401
            except ImportError as ie:
                return ProviderStatus(
                    provider=self.provider_name,
                    status="unavailable",
                    message=f"google-genai SDK not installed: {ie}",
                    available=False,
                )

            return ProviderStatus(
                provider=self.provider_name,
                status="healthy",
                message="Gemini TTS is available (preview)",
                available=True,
                details={
                    "model": _GEMINI_TTS_MODEL,
                    "voices": len(self.VOICES),
                    "api_key_configured": True,
                    "release_stage": "preview",
                },
            )

        except Exception as e:
            self.logger.error(f"Gemini TTS health check failed: {e}")
            return ProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message=f"Health check failed: {str(e)}",
                available=False,
            )
