import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from hub.providers.asr_provider import ASRRequest
from hub.providers.openai_asr_provider import OpenAIASRProvider


def test_openai_asr_provider_returns_structured_error_and_releases_db(tmp_path):
    audio_path = tmp_path / "audio.ogg"
    audio_path.write_bytes(b"ogg-data")

    class _FailingTranscriptions:
        def create(self, **_kwargs):
            raise RuntimeError("bad key")

    class _FailingClient:
        audio = SimpleNamespace(transcriptions=_FailingTranscriptions())

    db = MagicMock()
    provider = OpenAIASRProvider(api_key="sk-test", db=db, tenant_id="tenant-test")

    with patch("hub.providers.openai_asr_provider.OpenAI", return_value=_FailingClient()):
        result = asyncio.run(
            provider.transcribe(
                ASRRequest(
                    audio_path=str(audio_path),
                    model="whisper-1",
                    language="auto",
                    tenant_id="tenant-test",
                )
            )
        )

    assert result.success is False
    assert result.provider == "openai"
    assert "bad key" in result.error
    db.rollback.assert_called_once()


def test_openai_asr_provider_passes_prompt_to_transcriptions(tmp_path):
    audio_path = tmp_path / "audio.ogg"
    audio_path.write_bytes(b"ogg-data")
    captured = {}

    class _Transcriptions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text="texto")

    class _Client:
        audio = SimpleNamespace(transcriptions=_Transcriptions())

    provider = OpenAIASRProvider(api_key="sk-test")

    with patch("hub.providers.openai_asr_provider.OpenAI", return_value=_Client()):
        result = asyncio.run(
            provider.transcribe(
                ASRRequest(
                    audio_path=str(audio_path),
                    model="whisper-1",
                    language="pt",
                    prompt="Termos esperados: Tsushin, ArchSec.",
                    hotwords="ignored by OpenAI provider",
                )
            )
        )

    assert result.success is True
    assert captured["language"] == "pt"
    assert captured["prompt"] == "Termos esperados: Tsushin, ArchSec."
    assert "hotwords" not in captured
