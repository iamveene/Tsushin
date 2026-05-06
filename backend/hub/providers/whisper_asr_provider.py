"""
Speaches-backed ASR provider.

Uses the per-tenant ASRInstance row plus its encrypted token to call the
OpenAI-compatible /v1/audio/transcriptions endpoint.
"""

from pathlib import Path

import httpx

from .asr_provider import ASRProvider, ASRRequest, ASRResponse
from services.whisper_instance_service import WhisperInstanceService


class WhisperASRProvider(ASRProvider):
    def __init__(self, instance, **kwargs):
        super().__init__(**kwargs)
        self.instance = instance

    def get_provider_name(self) -> str:
        return "speaches"

    async def transcribe(self, request: ASRRequest) -> ASRResponse:
        if not self.db:
            return ASRResponse(success=False, provider=self.provider_name, error="missing_db_session")
        if not self.instance or not self.instance.base_url:
            return ASRResponse(success=False, provider=self.provider_name, error="missing_base_url")

        base_url = self.instance.base_url
        default_model = self.instance.default_model
        token = WhisperInstanceService.resolve_api_token(self.instance, self.db)
        if not token:
            return ASRResponse(success=False, provider=self.provider_name, error="missing_api_token")

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

        try:
            with Path(request.audio_path).open("rb") as audio_file:
                files = {
                    "file": (Path(request.audio_path).name, audio_file, "application/octet-stream")
                }
                data = {"model": model}
                if request.language and request.language != "auto":
                    data["language"] = request.language
                async with httpx.AsyncClient(timeout=120) as client:
                    response = await client.post(
                        f"{base_url.rstrip('/')}/v1/audio/transcriptions",
                        headers=headers,
                        files=files,
                        data=data,
                    )
        except Exception as exc:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error=f"request_error: {exc}",
            )

        if response.status_code != 200:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error=f"http_{response.status_code}: {response.text[:300]}",
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
            )
        return ASRResponse(
            success=True,
            provider=self.provider_name,
            text=text,
            metadata={"model": model},
        )
