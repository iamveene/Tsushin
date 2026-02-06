"""
Kokoro TTS Provider
Implements TTS using Kokoro open-source TTS service.

Kokoro is a FREE, open-source TTS solution running locally via Docker.
Supports multiple languages including Brazilian Portuguese.

Pricing: FREE (zero cost!)
"""

import os
import logging
import tempfile
from typing import Dict, List, Optional, Any
from pathlib import Path
from datetime import datetime
import time

import httpx

from .tts_provider import (
    TTSProvider,
    TTSRequest,
    TTSResponse,
    VoiceInfo,
    ProviderStatus
)


logger = logging.getLogger(__name__)


class KokoroTTSProvider(TTSProvider):
    """
    Kokoro TTS Provider.
    Free, open-source text-to-speech using local ONNX-based inference.

    Supports:
    - Brazilian Portuguese voices (pf_dora, pm_alex, pm_santa)
    - American English voices (af_bella, af_sarah, am_adam, am_michael)
    - British English voices (bf_emma, bm_george)
    - Multiple formats: mp3, opus, aac, wav
    - Speed adjustment: 0.5 to 2.0x
    - Languages: pt, en, es, ja, zh, fr, de, it
    """

    # Available voices organized by language
    VOICES = {
        # Portuguese (Brazilian) - CORRECT for PTBR
        "pf_dora": VoiceInfo(
            voice_id="pf_dora",
            name="Dora",
            language="pt",
            gender="female",
            description="Portuguese female (recommended for PTBR)",
            provider="kokoro"
        ),
        "pm_alex": VoiceInfo(
            voice_id="pm_alex",
            name="Alex",
            language="pt",
            gender="male",
            description="Portuguese male",
            provider="kokoro"
        ),
        "pm_santa": VoiceInfo(
            voice_id="pm_santa",
            name="Santa",
            language="pt",
            gender="male",
            description="Portuguese male alternative",
            provider="kokoro"
        ),
        # American English
        "af_bella": VoiceInfo(
            voice_id="af_bella",
            name="Bella",
            language="en",
            gender="female",
            description="American English female",
            provider="kokoro"
        ),
        "af_sarah": VoiceInfo(
            voice_id="af_sarah",
            name="Sarah",
            language="en",
            gender="female",
            description="American English female (professional)",
            provider="kokoro"
        ),
        "af_nicole": VoiceInfo(
            voice_id="af_nicole",
            name="Nicole",
            language="en",
            gender="female",
            description="American English female",
            provider="kokoro"
        ),
        "af_sky": VoiceInfo(
            voice_id="af_sky",
            name="Sky",
            language="en",
            gender="female",
            description="American English female (young)",
            provider="kokoro"
        ),
        "am_adam": VoiceInfo(
            voice_id="am_adam",
            name="Adam",
            language="en",
            gender="male",
            description="American English male",
            provider="kokoro"
        ),
        "am_michael": VoiceInfo(
            voice_id="am_michael",
            name="Michael",
            language="en",
            gender="male",
            description="American English male (casual)",
            provider="kokoro"
        ),
        # British English
        "bf_emma": VoiceInfo(
            voice_id="bf_emma",
            name="Emma",
            language="en",
            gender="female",
            description="British English female",
            provider="kokoro"
        ),
        "bm_george": VoiceInfo(
            voice_id="bm_george",
            name="George",
            language="en",
            gender="male",
            description="British English male",
            provider="kokoro"
        ),
        "bf_alice": VoiceInfo(
            voice_id="bf_alice",
            name="Alice",
            language="en",
            gender="female",
            description="British English female",
            provider="kokoro"
        ),
        "bm_daniel": VoiceInfo(
            voice_id="bm_daniel",
            name="Daniel",
            language="en",
            gender="male",
            description="British English male",
            provider="kokoro"
        ),
        "bm_lewis": VoiceInfo(
            voice_id="bm_lewis",
            name="Lewis",
            language="en",
            gender="male",
            description="British English male",
            provider="kokoro"
        ),
    }

    # Supported formats
    SUPPORTED_FORMATS = ["mp3", "opus", "aac", "flac", "wav"]

    # Supported languages
    SUPPORTED_LANGUAGES = ["pt", "en", "es", "ja", "zh", "fr", "de", "it"]

    def __init__(self, db=None, token_tracker=None):
        super().__init__(db=db, token_tracker=token_tracker)
        # VOICE-005 Fix: Auto-detect Docker environment for correct default URL
        default_url = "http://kokoro-tts:8880" if os.path.exists("/.dockerenv") else "http://localhost:8880"
        self.service_url = os.getenv("KOKORO_SERVICE_URL", default_url)

    def get_provider_name(self) -> str:
        return "kokoro"

    def get_display_name(self) -> str:
        return "Kokoro (Free)"

    def get_available_voices(self) -> List[VoiceInfo]:
        return list(self.VOICES.values())

    def get_voices_by_language(self, language: str) -> List[VoiceInfo]:
        """Get voices filtered by language code."""
        return [v for v in self.VOICES.values() if v.language == language]

    def get_default_voice(self) -> str:
        return "pf_dora"  # Default to Portuguese female

    def get_supported_formats(self) -> List[str]:
        return self.SUPPORTED_FORMATS.copy()

    def get_supported_languages(self) -> List[str]:
        return self.SUPPORTED_LANGUAGES.copy()

    def get_speed_range(self) -> tuple:
        return (0.5, 2.0)

    def get_pricing_info(self) -> Dict[str, Any]:
        return {
            "model": "kokoro",
            "cost_per_1k_chars": 0.0,
            "currency": "USD",
            "is_free": True,
            "note": "Kokoro is completely free (local inference)"
        }

    def _validate_voice(self, voice: str, language: str) -> str:
        """Validate and possibly correct voice selection based on language."""
        if voice in self.VOICES:
            return voice

        # If invalid voice, select default for language
        language_voices = self.get_voices_by_language(language)
        if language_voices:
            self.logger.warning(f"Invalid voice '{voice}', using default for language '{language}'")
            return language_voices[0].voice_id

        # Fall back to default
        self.logger.warning(f"Invalid voice '{voice}', using default")
        return self.get_default_voice()

    async def synthesize(self, request: TTSRequest) -> TTSResponse:
        """
        Synthesize audio using Kokoro TTS service.

        Uses streaming response handling to ensure complete audio data is received.

        IMPORTANT: For OGG Opus output, we request WAV from Kokoro and convert locally
        using ffmpeg. This works around a bug in Kokoro-FastAPI where OGG Opus files
        are truncated (missing audio data at the end).

        Args:
            request: TTSRequest with text and configuration

        Returns:
            TTSResponse with audio file path or error
        """
        try:
            # Validate and normalize parameters
            language = request.language if request.language in self.SUPPORTED_LANGUAGES else "pt"
            voice = self._validate_voice(request.voice, language)
            requested_format = request.response_format if request.response_format in self.SUPPORTED_FORMATS else "opus"
            speed = max(0.5, min(2.0, request.speed))

            # WORKAROUND: Kokoro-FastAPI has a bug where OGG Opus output is truncated.
            # We request WAV format (which works correctly) and convert to OGG Opus locally.
            needs_conversion = requested_format == "opus"
            kokoro_format = "wav" if needs_conversion else requested_format

            # Truncate text if too long
            text = request.text
            max_chars = 4000
            if len(text) > max_chars:
                self.logger.warning(f"Text too long ({len(text)} chars), truncating to {max_chars}")
                text = text[:max_chars] + "..."

            self.logger.info(
                f"Generating Kokoro TTS: {len(text)} chars, voice={voice}, "
                f"lang={language}, format={requested_format}"
                f"{' (via WAV conversion)' if needs_conversion else ''}"
            )

            # Map format to file extension (WhatsApp compatibility)
            extension_map = {
                "opus": "ogg",
                "mp3": "mp3",
                "aac": "m4a",
                "flac": "flac",
                "wav": "wav",
            }
            file_extension = extension_map.get(requested_format, requested_format)

            # Prepare output paths
            temp_dir = Path(tempfile.gettempdir()) / "tsushin_audio"
            temp_dir.mkdir(exist_ok=True)
            audio_path = temp_dir / f"kokoro_{request.message_id or 'response'}.{file_extension}"

            # Temporary WAV path for conversion
            wav_path = temp_dir / f"kokoro_{request.message_id or 'response'}_temp.wav" if needs_conversion else audio_path

            # Call Kokoro-FastAPI service
            start_time = time.time()
            timeout = httpx.Timeout(90.0, connect=30.0)

            async with httpx.AsyncClient(timeout=timeout) as client:
                try:
                    async with client.stream(
                        "POST",
                        f"{self.service_url}/v1/audio/speech",
                        json={
                            "model": "kokoro",
                            "input": text,
                            "voice": voice,
                            "response_format": kokoro_format,
                            "speed": speed,
                            "language": language
                        }
                    ) as response:
                        # Log response headers for debugging
                        transfer_encoding = response.headers.get("transfer-encoding", "none")
                        content_type = response.headers.get("content-type", "unknown")
                        self.logger.debug(
                            f"Kokoro response: status={response.status_code}, "
                            f"transfer-encoding={transfer_encoding}, content-type={content_type}"
                        )

                        if response.status_code != 200:
                            error_text = await response.aread()
                            error_text = error_text.decode('utf-8', errors='replace')[:200]
                            self.logger.error(f"Kokoro API error {response.status_code}: {error_text}")
                            return TTSResponse(
                                success=False,
                                provider=self.provider_name,
                                error=f"Kokoro TTS failed (HTTP {response.status_code})",
                                metadata={"status": response.status_code, "details": error_text}
                            )

                        # Stream audio data to file
                        total_bytes = 0
                        chunk_count = 0

                        # Write to wav_path (same as audio_path if no conversion needed)
                        with open(wav_path, 'wb') as f:
                            async for chunk in response.aiter_bytes():
                                f.write(chunk)
                                total_bytes += len(chunk)
                                chunk_count += 1
                            f.flush()
                            os.fsync(f.fileno())

                        # Verify file was written
                        wav_size = os.path.getsize(wav_path)
                        if wav_size != total_bytes:
                            self.logger.error(f"FILE SIZE MISMATCH! Written: {total_bytes}, On disk: {wav_size}")
                            return TTSResponse(
                                success=False,
                                provider=self.provider_name,
                                error=f"Audio file incomplete ({wav_size}/{total_bytes} bytes)"
                            )

                        # Convert WAV to OGG Opus if needed
                        if needs_conversion:
                            conversion_success = await self._convert_wav_to_opus(wav_path, audio_path)
                            if not conversion_success:
                                return TTSResponse(
                                    success=False,
                                    provider=self.provider_name,
                                    error="Failed to convert WAV to OGG Opus"
                                )
                            # Clean up temp WAV file
                            try:
                                os.unlink(wav_path)
                            except Exception:
                                pass

                        latency_ms = int((time.time() - start_time) * 1000)
                        actual_size = os.path.getsize(audio_path)

                        self.logger.info(
                            f"Kokoro TTS generated: {actual_size} bytes in {latency_ms}ms "
                            f"({chunk_count} chunks) at {audio_path}"
                            f"{' (converted from WAV)' if needs_conversion else ''}"
                        )

                        # Track usage (free, but tracked for statistics)
                        char_count = len(text)
                        self._track_usage(
                            char_count=char_count,
                            model_name="kokoro",
                            agent_id=request.agent_id,
                            sender_key=request.sender_key,
                            message_id=request.message_id
                        )

                        return TTSResponse(
                            success=True,
                            audio_path=str(audio_path),
                            provider=self.provider_name,
                            audio_size_bytes=actual_size,
                            format=requested_format,
                            characters_processed=char_count,
                            estimated_cost=0.0,  # FREE!
                            voice_used=voice,
                            language_used=language,
                            speed_used=speed,
                            metadata={
                                "model": "kokoro",
                                "latency_ms": latency_ms,
                                "chunks_received": chunk_count,
                                "is_audio_response": True,
                                "cost": 0.0,
                                "converted_from_wav": needs_conversion
                            }
                        )

                except httpx.ConnectError:
                    self.logger.error(f"Cannot connect to Kokoro service at {self.service_url}")
                    return TTSResponse(
                        success=False,
                        provider=self.provider_name,
                        error=f"Kokoro service not reachable at {self.service_url}",
                        metadata={
                            "kokoro_url": self.service_url,
                            "hint": "Start Kokoro with: docker compose --profile tts up -d"
                        }
                    )

                except httpx.TimeoutException:
                    self.logger.error("Kokoro service timeout after 90s")
                    return TTSResponse(
                        success=False,
                        provider=self.provider_name,
                        error="Kokoro TTS timeout (>90s)",
                        metadata={"timeout": 90}
                    )

        except Exception as e:
            self.logger.error(f"Kokoro TTS synthesis failed: {e}", exc_info=True)
            return TTSResponse(
                success=False,
                provider=self.provider_name,
                error=f"Kokoro TTS synthesis failed: {str(e)}"
            )

    async def _convert_wav_to_opus(self, wav_path: Path, opus_path: Path) -> bool:
        """
        Convert WAV file to OGG Opus format using ffmpeg.

        This is a workaround for a bug in Kokoro-FastAPI where OGG Opus output
        is truncated (missing audio data). WAV output is complete, so we convert
        it to OGG Opus locally.

        Args:
            wav_path: Path to source WAV file
            opus_path: Path for output OGG Opus file

        Returns:
            True if conversion succeeded, False otherwise
        """
        import asyncio
        import subprocess

        try:
            # Use ffmpeg to convert WAV to OGG Opus
            # -y: overwrite output file
            # -i: input file
            # -c:a libopus: use Opus codec
            # -b:a 48k: bitrate (good quality for voice)
            # -vbr on: variable bitrate for better quality
            # -application voip: optimize for voice
            cmd = [
                'ffmpeg', '-y', '-i', str(wav_path),
                '-c:a', 'libopus',
                '-b:a', '48k',
                '-vbr', 'on',
                '-application', 'voip',
                str(opus_path)
            ]

            self.logger.debug(f"Converting WAV to Opus: {' '.join(cmd)}")

            # Run ffmpeg
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                self.logger.error(f"ffmpeg conversion failed: {stderr.decode()}")
                return False

            # Verify output file exists and has content
            if not opus_path.exists() or opus_path.stat().st_size < 100:
                self.logger.error("ffmpeg produced empty or no output file")
                return False

            self.logger.debug(f"WAV->Opus conversion successful: {opus_path.stat().st_size} bytes")
            return True

        except FileNotFoundError:
            self.logger.error("ffmpeg not found - install with: apt-get install ffmpeg")
            return False
        except Exception as e:
            self.logger.error(f"WAV to Opus conversion failed: {e}")
            return False

    async def health_check(self) -> ProviderStatus:
        """
        Check Kokoro service availability.

        Returns:
            ProviderStatus with health information
        """
        try:
            start_time = time.time()
            async with httpx.AsyncClient(timeout=10.0) as client:
                try:
                    # Try health endpoint
                    response = await client.get(f"{self.service_url}/health")
                    latency_ms = int((time.time() - start_time) * 1000)

                    if response.status_code == 200:
                        health_data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}

                        return ProviderStatus(
                            provider=self.provider_name,
                            status="healthy",
                            message="Kokoro TTS is available",
                            available=True,
                            latency_ms=latency_ms,
                            details={
                                "service_url": self.service_url,
                                "voices": len(self.VOICES),
                                "languages": self.SUPPORTED_LANGUAGES,
                                "is_free": True,
                                **health_data
                            }
                        )
                    else:
                        return ProviderStatus(
                            provider=self.provider_name,
                            status="degraded",
                            message=f"Kokoro service returned status {response.status_code}",
                            available=False,
                            latency_ms=latency_ms,
                            details={"status_code": response.status_code}
                        )

                except httpx.ConnectError:
                    return ProviderStatus(
                        provider=self.provider_name,
                        status="unavailable",
                        message=f"Cannot connect to Kokoro at {self.service_url}",
                        available=False,
                        details={
                            "service_url": self.service_url,
                            "hint": "Start with: docker compose --profile tts up -d"
                        }
                    )

                except httpx.TimeoutException:
                    return ProviderStatus(
                        provider=self.provider_name,
                        status="unavailable",
                        message="Kokoro service timeout",
                        available=False,
                        details={"timeout_seconds": 10}
                    )

        except Exception as e:
            self.logger.error(f"Kokoro health check failed: {e}")
            return ProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message=f"Health check failed: {str(e)}",
                available=False
            )
