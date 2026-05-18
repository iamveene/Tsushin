"""
Speaches-backed ASR provider.

Uses the per-tenant ASRInstance row plus its encrypted token to call the
OpenAI-compatible /v1/audio/transcriptions endpoint.
"""

import asyncio
from pathlib import Path

import httpx

from .asr_provider import ASRProvider, ASRRequest, ASRResponse
from services.whisper_instance_service import WhisperInstanceService


_RETRY_BACKOFFS_SEC = (1.0, 3.0, 7.0)


def _is_retryable_status(status_code: int) -> bool:
    return status_code == 429 or 500 <= status_code <= 599


class WhisperASRProvider(ASRProvider):
    def __init__(self, instance, **kwargs):
        super().__init__(**kwargs)
        self.instance = instance

    def get_provider_name(self) -> str:
        return "speaches"

    async def transcribe(self, request: ASRRequest) -> ASRResponse:
        if not self.db:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error="missing_db_session",
                metadata={"attempts": 0, "retried": False},
            )
        if not self.instance or not self.instance.base_url:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error="missing_base_url",
                metadata={"attempts": 0, "retried": False},
            )

        base_url = self.instance.base_url
        default_model = self.instance.default_model
        token = WhisperInstanceService.resolve_api_token(self.instance, self.db)
        if not token:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error="missing_api_token",
                metadata={"attempts": 0, "retried": False},
            )

        try:
            self.db.rollback()
        except Exception as rollback_err:
            self.logger.warning(
                "Failed to release DB transaction before Speaches ASR call: %s",
                rollback_err,
            )

        model = request.model or default_model
        # BUG-703: Speaches expects `Authorization: Bearer <token>`. Basic auth
        # and X-API-Key both produce 403 against the upstream Speaches API.
        headers = {
            "Authorization": f"Bearer {token}",
        }

        audio_path = Path(request.audio_path)
        attempts = 0
        last_error: str | None = None
        response = None
        max_attempts = 1 + len(_RETRY_BACKOFFS_SEC)
        for attempt in range(max_attempts):
            attempts = attempt + 1
            try:
                with audio_path.open("rb") as audio_file:
                    files = {
                        "file": (audio_path.name, audio_file, "application/octet-stream")
                    }
                    data = {"model": model}
                    if request.language and request.language != "auto":
                        data["language"] = request.language
                    if request.vad_filter is not None:
                        data["vad_filter"] = "true" if request.vad_filter else "false"
                    # 600s timeout: even Speaches/faster-whisper can queue requests
                    # under CPU bursts. See openai_whisper_asr_provider for context.
                    async with httpx.AsyncClient(timeout=600) as client:
                        response = await client.post(
                            f"{base_url.rstrip('/')}/v1/audio/transcriptions",
                            headers=headers,
                            files=files,
                            data=data,
                        )
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                detail = str(exc) or repr(exc) or "no exception detail"
                last_error = f"request_error: {type(exc).__name__}: {detail}"
                if attempt < max_attempts - 1:
                    delay = _RETRY_BACKOFFS_SEC[attempt]
                    self.logger.warning(
                        "Speaches ASR transient failure (attempt %s/%s): %s; retrying in %.1fs",
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

            if (
                response.status_code
                and _is_retryable_status(response.status_code)
                and attempt < max_attempts - 1
            ):
                last_error = f"http_{response.status_code}: {response.text[:300]}"
                delay = _RETRY_BACKOFFS_SEC[attempt]
                self.logger.warning(
                    "Speaches ASR transient HTTP %s (attempt %s/%s); retrying in %.1fs",
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

        payload = response.json()
        text = (payload.get("text") or "").strip() if isinstance(payload, dict) else ""
        if not text and isinstance(payload, str):
            text = payload.strip()
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
            metadata={
                "model": model,
                "vad_filter": request.vad_filter,
                "attempts": attempts,
                "retried": attempts > 1,
            },
        )
