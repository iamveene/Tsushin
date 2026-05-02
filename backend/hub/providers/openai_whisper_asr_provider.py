"""
OpenAI Whisper ASR provider — wraps the openai/whisper Python package via the
``onerahmet/openai-whisper-asr-webservice`` HTTP service.

Endpoint shape differs from Speaches/faster-whisper (which is OpenAI-compatible
on ``/v1/audio/transcriptions``); this service exposes ``POST /asr`` taking
``audio_file`` as a multipart field plus query parameters for language/task/output.
The container image runs the upstream openai-whisper engine when started with
``ASR_ENGINE=openai_whisper``.
"""

from pathlib import Path
from typing import Any, Dict

import httpx

from .asr_provider import ASRProvider, ASRRequest, ASRResponse
from services.whisper_instance_service import WhisperInstanceService


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

        token = WhisperInstanceService.resolve_api_token(self.instance, self.db)

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

        with Path(request.audio_path).open("rb") as audio_file:
            files = {
                "audio_file": (
                    Path(request.audio_path).name,
                    audio_file,
                    "application/octet-stream",
                )
            }
            async with httpx.AsyncClient(timeout=180) as client:
                response = await client.post(
                    f"{self.instance.base_url.rstrip('/')}/asr",
                    headers=headers,
                    params=params,
                    files=files,
                )

        if response.status_code != 200:
            return ASRResponse(
                success=False,
                provider=self.provider_name,
                error=f"http_{response.status_code}: {response.text[:300]}",
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
            )

        metadata["model"] = request.model or self.instance.default_model
        return ASRResponse(
            success=True,
            provider=self.provider_name,
            text=text,
            metadata=metadata,
        )
