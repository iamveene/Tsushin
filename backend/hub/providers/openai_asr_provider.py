"""
OpenAI ASR provider.

Preserves the existing Whisper transcription path behind the provider
abstraction so Track D can layer local ASR instances on top without removing
the current fallback.
"""

from pathlib import Path

from openai import OpenAI

from .asr_provider import ASRProvider, ASRRequest, ASRResponse
from services.api_key_service import get_api_key


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

        if self._client is None:
            self._client = OpenAI(api_key=api_key)

        with Path(request.audio_path).open("rb") as audio_file:
            params = {
                "model": request.model or "whisper-1",
                "file": audio_file,
            }
            if request.language and request.language != "auto":
                params["language"] = request.language
            response = self._client.audio.transcriptions.create(**params)

        text = (response.text or "").strip()
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
            metadata={"model": request.model},
        )
