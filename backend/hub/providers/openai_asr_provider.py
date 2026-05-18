"""
OpenAI ASR provider.

Preserves the existing Whisper transcription path behind the provider
abstraction so Track D can layer local ASR instances on top without removing
the current fallback.
"""

import asyncio
from pathlib import Path

from openai import (
    OpenAI,
    APIConnectionError,
    APITimeoutError,
    InternalServerError,
    RateLimitError,
)

from .asr_provider import ASRProvider, ASRRequest, ASRResponse
from services.api_key_service import get_api_key


# Bursts of audios (3-6 voice notes back-to-back) fan out to several
# concurrent transcribe calls; OpenAI occasionally answers with 429 or a
# transient 5xx. Without retry the audio's transcript would silently drop,
# so we retry transient failures with exponential backoff before giving up.
_TRANSIENT_OPENAI_EXC = (
    APIConnectionError,
    APITimeoutError,
    RateLimitError,
    InternalServerError,
)
_RETRY_BACKOFFS_SEC = (1.0, 3.0, 7.0)


class OpenAIASRProvider(ASRProvider):
    def __init__(self, api_key: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self._api_key = api_key
        self._client = None

    def get_provider_name(self) -> str:
        return "openai"

    async def transcribe(self, request: ASRRequest) -> ASRResponse:
        api_key = self._api_key
        if not api_key and self.db is not None:
            api_key = get_api_key("openai", self.db, tenant_id=self.tenant_id)
        if not api_key:
            return ASRResponse(success=False, provider=self.provider_name, error="missing_api_key")

        if self.db is not None:
            try:
                self.db.rollback()
            except Exception as rollback_err:
                self.logger.warning(
                    "Failed to release DB transaction before OpenAI ASR call: %s",
                    rollback_err,
                )

        if self._client is None:
            self._client = OpenAI(api_key=api_key)

        attempts = 0
        last_transient_error: str | None = None
        response = None
        max_attempts = 1 + len(_RETRY_BACKOFFS_SEC)
        for attempt in range(max_attempts):
            attempts = attempt + 1
            try:
                # File must be re-opened each attempt: the SDK reads to EOF
                # on the first call and the stream cannot be reused.
                with Path(request.audio_path).open("rb") as audio_file:
                    params = {
                        "model": request.model or "whisper-1",
                        "file": audio_file,
                    }
                    if request.language and request.language != "auto":
                        params["language"] = request.language
                    if request.prompt:
                        params["prompt"] = request.prompt
                    response = self._client.audio.transcriptions.create(**params)
                break
            except _TRANSIENT_OPENAI_EXC as exc:
                last_transient_error = f"{type(exc).__name__}: {exc}"
                if attempt < max_attempts - 1:
                    delay = _RETRY_BACKOFFS_SEC[attempt]
                    self.logger.warning(
                        "OpenAI ASR transient failure (attempt %s/%s): %s — retrying in %.1fs",
                        attempts,
                        max_attempts,
                        last_transient_error,
                        delay,
                    )
                    await asyncio.sleep(delay)
                    continue
                return ASRResponse(
                    success=False,
                    provider=self.provider_name,
                    error=last_transient_error,
                    metadata={"attempts": attempts, "retried": True},
                )
            except Exception as exc:
                return ASRResponse(
                    success=False,
                    provider=self.provider_name,
                    error=str(exc),
                    metadata={"attempts": attempts, "retried": attempts > 1},
                )

        text = (getattr(response, "text", "") or "").strip()
        if not text:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error="empty_transcription",
                metadata={"attempts": attempts, "retried": attempts > 1},
            )
        return ASRResponse(
            success=True,
            provider=self.provider_name,
            text=text,
            metadata={"model": request.model, "attempts": attempts, "retried": attempts > 1},
        )
