"""Tests for the Gemini multimodal ASR provider."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from hub.providers.asr_provider import ASRRequest
from hub.providers.gemini_asr_provider import (
    GeminiASRProvider,
    _INLINE_AUDIO_LIMIT_BYTES,
    _guess_audio_mime,
)


def _make_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(text=text, candidates=[])


def test_gemini_asr_provider_missing_api_key_returns_error(tmp_path):
    audio_path = tmp_path / "audio.ogg"
    audio_path.write_bytes(b"ogg-data")

    provider = GeminiASRProvider(api_key=None)
    result = asyncio.run(
        provider.transcribe(
            ASRRequest(audio_path=str(audio_path), model="gemini-3.5-flash")
        )
    )

    assert result.success is False
    assert result.provider == "gemini"
    assert result.error == "missing_api_key"


def test_gemini_asr_provider_returns_transcript_for_inline_audio(tmp_path):
    audio_path = tmp_path / "audio.ogg"
    audio_path.write_bytes(b"small-ogg-bytes")

    captured = {}

    fake_part_from_bytes = MagicMock(return_value="AUDIO_PART")
    fake_part_from_uri = MagicMock()

    def _generate_content(*, model, contents):
        captured["model"] = model
        captured["contents"] = contents
        return _make_response("transcribed text")

    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=_generate_content),
        files=SimpleNamespace(upload=MagicMock()),
    )

    db = MagicMock()
    provider = GeminiASRProvider(api_key="g-key", db=db, tenant_id="tenant-test")

    with patch("google.genai.Client", return_value=fake_client), \
         patch("google.genai.types.Part.from_bytes", fake_part_from_bytes), \
         patch("google.genai.types.Part.from_uri", fake_part_from_uri):
        result = asyncio.run(
            provider.transcribe(
                ASRRequest(
                    audio_path=str(audio_path),
                    model="gemini-3.5-flash",
                    language="pt",
                    prompt="Termos: Tsushin",
                    hotwords="archsec",
                    tenant_id="tenant-test",
                )
            )
        )

    assert result.success is True
    assert result.provider == "gemini"
    assert result.text == "transcribed text"
    assert result.metadata["model"] == "gemini-3.5-flash"
    assert result.metadata["used_files_api"] is False
    assert captured["model"] == "gemini-3.5-flash"
    # Prompt + audio part are passed positionally to generate_content
    assert len(captured["contents"]) == 2
    prompt_text = captured["contents"][0]
    assert "Transcribe this audio verbatim" in prompt_text
    assert "language code 'pt'" in prompt_text
    assert "Tsushin" in prompt_text
    assert "archsec" in prompt_text
    fake_part_from_bytes.assert_called_once()
    fake_part_from_uri.assert_not_called()
    db.rollback.assert_called_once()


def test_gemini_asr_provider_uses_files_api_for_large_audio(tmp_path):
    audio_path = tmp_path / "big.ogg"
    audio_path.write_bytes(b"x" * (_INLINE_AUDIO_LIMIT_BYTES + 1))

    upload_mock = MagicMock(return_value=SimpleNamespace(uri="files/abc", mime_type="audio/ogg"))
    from_bytes_mock = MagicMock()
    from_uri_mock = MagicMock(return_value="FILES_PART")

    fake_client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda model, contents: _make_response("ok-big")
        ),
        files=SimpleNamespace(upload=upload_mock),
    )

    provider = GeminiASRProvider(api_key="g-key")
    with patch("google.genai.Client", return_value=fake_client), \
         patch("google.genai.types.Part.from_bytes", from_bytes_mock), \
         patch("google.genai.types.Part.from_uri", from_uri_mock):
        result = asyncio.run(
            provider.transcribe(
                ASRRequest(audio_path=str(audio_path), model="gemini-3.5-flash")
            )
        )

    assert result.success is True
    assert result.metadata["used_files_api"] is True
    upload_mock.assert_called_once()
    from_uri_mock.assert_called_once()
    from_bytes_mock.assert_not_called()


def test_gemini_asr_provider_retries_on_transient_error(tmp_path):
    audio_path = tmp_path / "audio.ogg"
    audio_path.write_bytes(b"bytes")

    call_counter = {"n": 0}

    def _generate_content(*, model, contents):
        call_counter["n"] += 1
        if call_counter["n"] == 1:
            raise RuntimeError("503 ServiceUnavailable")
        return _make_response("retried text")

    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=_generate_content),
        files=SimpleNamespace(upload=MagicMock()),
    )

    provider = GeminiASRProvider(api_key="g-key")
    with patch("google.genai.Client", return_value=fake_client), \
         patch("google.genai.types.Part.from_bytes", MagicMock()), \
         patch("google.genai.types.Part.from_uri", MagicMock()), \
         patch("hub.providers.gemini_asr_provider.asyncio.sleep", return_value=None):
        result = asyncio.run(
            provider.transcribe(
                ASRRequest(audio_path=str(audio_path), model="gemini-3.5-flash")
            )
        )

    assert result.success is True
    assert result.text == "retried text"
    assert result.metadata["retried"] is True
    assert call_counter["n"] == 2


def test_gemini_asr_provider_does_not_retry_on_permanent_error(tmp_path):
    audio_path = tmp_path / "audio.ogg"
    audio_path.write_bytes(b"bytes")

    call_counter = {"n": 0}

    def _generate_content(*, model, contents):
        call_counter["n"] += 1
        raise ValueError("invalid_argument: bad audio")

    fake_client = SimpleNamespace(
        models=SimpleNamespace(generate_content=_generate_content),
        files=SimpleNamespace(upload=MagicMock()),
    )

    provider = GeminiASRProvider(api_key="g-key")
    with patch("google.genai.Client", return_value=fake_client), \
         patch("google.genai.types.Part.from_bytes", MagicMock()), \
         patch("google.genai.types.Part.from_uri", MagicMock()):
        result = asyncio.run(
            provider.transcribe(
                ASRRequest(audio_path=str(audio_path), model="gemini-3.5-flash")
            )
        )

    assert result.success is False
    assert call_counter["n"] == 1
    assert "bad audio" in result.error


def test_gemini_asr_provider_empty_text_returns_failure(tmp_path):
    audio_path = tmp_path / "audio.ogg"
    audio_path.write_bytes(b"bytes")

    fake_client = SimpleNamespace(
        models=SimpleNamespace(
            generate_content=lambda model, contents: _make_response("   ")
        ),
        files=SimpleNamespace(upload=MagicMock()),
    )
    provider = GeminiASRProvider(api_key="g-key")
    with patch("google.genai.Client", return_value=fake_client), \
         patch("google.genai.types.Part.from_bytes", MagicMock()), \
         patch("google.genai.types.Part.from_uri", MagicMock()):
        result = asyncio.run(
            provider.transcribe(
                ASRRequest(audio_path=str(audio_path), model="gemini-3.5-flash")
            )
        )

    assert result.success is False
    assert result.error == "empty_transcription"


def test_guess_audio_mime_handles_common_extensions(tmp_path):
    assert _guess_audio_mime(str(tmp_path / "x.ogg")) == "audio/ogg"
    assert _guess_audio_mime(str(tmp_path / "x.opus")) == "audio/ogg"
    assert _guess_audio_mime(str(tmp_path / "x.mp3")) == "audio/mpeg"
    assert _guess_audio_mime(str(tmp_path / "x.m4a")) == "audio/mp4"
    assert _guess_audio_mime(str(tmp_path / "x.wav")) == "audio/wav"
    assert _guess_audio_mime(str(tmp_path / "x.flac")) == "audio/flac"
    assert _guess_audio_mime(str(tmp_path / "x.webm")) == "audio/webm"
    assert _guess_audio_mime(str(tmp_path / "x.unknown")) == "audio/ogg"
