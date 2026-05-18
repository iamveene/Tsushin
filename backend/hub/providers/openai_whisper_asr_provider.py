"""
OpenAI Whisper ASR provider — wraps the openai/whisper Python package via the
``onerahmet/openai-whisper-asr-webservice`` HTTP service.

Endpoint shape differs from Speaches/faster-whisper (which is OpenAI-compatible
on ``/v1/audio/transcriptions``); this service exposes ``POST /asr`` taking
``audio_file`` as a multipart field plus query parameters for language/task/output.
The container image runs the upstream openai-whisper engine when started with
``ASR_ENGINE=openai_whisper``.
"""

import asyncio
from pathlib import Path
from typing import Any, Dict

import httpx

from .asr_provider import ASRProvider, ASRRequest, ASRResponse
from services.whisper_instance_service import WhisperInstanceService


# Bursts of audios queue at the (CPU-serialized) local ASR service; transient
# blips — TCP resets while the worker is busy, occasional 502 from a sidecar
# proxy — would silently drop the transcript without retry. Same backoff
# schedule as the OpenAI cloud provider so behavior is uniform.
_RETRY_BACKOFFS_SEC = (1.0, 3.0, 7.0)
_RETRYABLE_HTTP_STATUS = {429, 500, 502, 503, 504}


class OpenAIWhisperASRProvider(ASRProvider):
    """ASR provider that calls a tenant-scoped openai-whisper-asr-webservice container."""

    def __init__(self, instance, **kwargs):
        super().__init__(**kwargs)
        self.instance = instance

    def get_provider_name(self) -> str:
        return "openai_whisper"

    async def transcribe(self, request: ASRRequest) -> ASRResponse:
        if not self.db:
            return ASRResponse(success=False, provider=self.provider_name, error="missing_db_session")
        if not self.instance or not self.instance.base_url:
            return ASRResponse(success=False, provider=self.provider_name, error="missing_base_url")

        base_url = self.instance.base_url
        default_model = self.instance.default_model
        token = WhisperInstanceService.resolve_api_token(self.instance, self.db)

        try:
            self.db.rollback()
        except Exception as rollback_err:
            self.logger.warning(
                "Failed to release DB transaction before OpenAI Whisper ASR call: %s",
                rollback_err,
            )

        headers: Dict[str, str] = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"

        params: Dict[str, Any] = {
            "task": "transcribe",
            "output": "json",
            "encode": "true",
        }
        if request.language and request.language != "auto":
            params["language"] = request.language

        attempts = 0
        last_error: str | None = None
        response = None
        max_attempts = 1 + len(_RETRY_BACKOFFS_SEC)
        for attempt in range(max_attempts):
            attempts = attempt + 1
            try:
                with Path(request.audio_path).open("rb") as audio_file:
                    files = {
                        "audio_file": (
                            Path(request.audio_path).name,
                            audio_file,
                            "application/octet-stream",
                        )
                    }
                    # 600s timeout: onerahmet/openai-whisper-asr-webservice serializes
                    # requests on CPU, so 7 audios in burst can queue ~5 min before
                    # the last one even starts processing. Bumping to 10 min covers
                    # realistic CPU bursts; on GPU the request still returns in
                    # seconds so the higher ceiling is harmless.
                    async with httpx.AsyncClient(timeout=600) as client:
                        response = await client.post(
                            f"{base_url.rstrip('/')}/asr",
                            headers=headers,
                            params=params,
                            files=files,
                        )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last_error = f"request_error: {type(exc).__name__}: {exc or repr(exc)}"
                if attempt < max_attempts - 1:
                    delay = _RETRY_BACKOFFS_SEC[attempt]
                    self.logger.warning(
                        "Local Whisper transient failure (attempt %s/%s): %s — retrying in %.1fs",
                        attempts,
                        max_attempts,
                        last_error,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                return ASRResponse(
                    success=False,
                    provider=self.provider_name,
                    error=last_error,
                    metadata={"attempts": attempts, "retried": True},
                )
            except Exception as exc:
                detail = str(exc) or repr(exc) or "no exception detail"
                return ASRResponse(
                    success=False,
                    provider=self.provider_name,
                    error=f"request_error: {type(exc).__name__}: {detail}",
                    metadata={"attempts": attempts, "retried": attempts > 1},
                )

            if response.status_code in _RETRYABLE_HTTP_STATUS and attempt < max_attempts - 1:
                last_error = f"http_{response.status_code}: {response.text[:300]}"
                delay = _RETRY_BACKOFFS_SEC[attempt]
                self.logger.warning(
                    "Local Whisper transient HTTP %s (attempt %s/%s) — retrying in %.1fs",
                    response.status_code,
                    attempts,
                    max_attempts,
                    delay,
                )
                await asyncio.sleep(delay)
                continue
            break

        if response is None:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error=last_error or "no_response",
                metadata={"attempts": attempts, "retried": attempts > 1},
            )

        if response.status_code != 200:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error=f"http_{response.status_code}: {response.text[:300]}",
                metadata={"attempts": attempts, "retried": attempts > 1},
            )

        text = ""
        metadata: Dict[str, Any] = {}
        try:
            payload = response.json()
        except Exception:
            payload = None

        if isinstance(payload, dict):
            text = (payload.get("text") or "").strip()
            language = payload.get("language")
            if language:
                metadata["language"] = language
        elif isinstance(payload, str):
            text = payload.strip()
        else:
            text = response.text.strip()

        if not text:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error="empty_transcription",
                metadata={"attempts": attempts, "retried": attempts > 1},
            )

        metadata["model"] = request.model or default_model
        metadata["attempts"] = attempts
        metadata["retried"] = attempts > 1
        return ASRResponse(
            success=True,
            provider=self.provider_name,
            text=text,
            metadata=metadata,
        )
