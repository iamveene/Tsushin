from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict
from unittest.mock import MagicMock, patch

from hub.providers.asr_provider import ASRRequest
from hub.providers.whisper_asr_provider import WhisperASRProvider


class _MockResponse:
    status_code = 200
    text = '{"text":"olá mundo"}'

    def json(self):
        return {"text": "olá mundo"}


class _MockAsyncClient:
    def __init__(self, capture: Dict[str, Any]):
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, headers=None, files=None, data=None):
        self._capture["url"] = url
        self._capture["headers"] = headers
        self._capture["files"] = list(files.keys()) if files else []
        self._capture["data"] = data or {}
        return _MockResponse()


def test_speaches_provider_posts_prompt_hotwords_and_ptbr_hints(tmp_path: Path):
    audio_path = tmp_path / "voice.ogg"
    audio_path.write_bytes(b"ogg-data")
    capture: Dict[str, Any] = {}
    instance = SimpleNamespace(
        id=1,
        base_url="http://speaches-test:8000",
        default_model="Systran/faster-whisper-small",
    )
    db = MagicMock()

    with patch(
        "hub.providers.whisper_asr_provider.WhisperInstanceService.resolve_api_token",
        return_value="secret-token",
    ), patch(
        "hub.providers.whisper_asr_provider.httpx.AsyncClient",
        return_value=_MockAsyncClient(capture),
    ):
        provider = WhisperASRProvider(instance=instance, db=db)
        result = asyncio.run(
            provider.transcribe(
                ASRRequest(
                    audio_path=str(audio_path),
                    model="Systran/faster-whisper-small",
                    language="pt",
                    vad_filter=False,
                    prompt="Termos esperados: Tsushin, ArchSec.",
                    hotwords="Tsushin\nArchSec\nlinha digitavel",
                    tenant_id="tenant-test",
                )
            )
        )

    assert result.success is True
    assert capture["url"].endswith("/v1/audio/transcriptions")
    assert capture["headers"]["Authorization"] == "Bearer secret-token"
    assert capture["files"] == ["file"]
    assert capture["data"] == {
        "model": "Systran/faster-whisper-small",
        "language": "pt",
        "vad_filter": "false",
        "prompt": "Termos esperados: Tsushin, ArchSec.",
        "hotwords": "Tsushin\nArchSec\nlinha digitavel",
    }
