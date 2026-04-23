"""
Unit tests for GeminiTTSProvider — focuses on the multi-model wiring added in
the v0.6.0 addendum (model resolution, SDK plumb-through, usage tracking).

Run with:
    docker exec tsushin-backend pytest backend/tests/test_gemini_tts_provider.py -v
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Allow direct invocation without docker exec — the provider lives under backend/
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from hub.providers.gemini_tts_provider import GeminiTTSProvider  # noqa: E402
from hub.providers.tts_provider import TTSRequest  # noqa: E402


# ---------------------------------------------------------------------------
# _resolve_model
# ---------------------------------------------------------------------------

def test_resolve_model_default_when_none():
    p = GeminiTTSProvider()
    assert p._resolve_model(None) == GeminiTTSProvider.DEFAULT_MODEL


def test_resolve_model_each_supported_passes_through():
    p = GeminiTTSProvider()
    for model_id in GeminiTTSProvider.SUPPORTED_MODELS.keys():
        assert p._resolve_model(model_id) == model_id


def test_resolve_model_invalid_falls_back_to_default_with_warning(caplog):
    p = GeminiTTSProvider()
    with caplog.at_level(logging.WARNING, logger=p.logger.name):
        result = p._resolve_model("gemini-fake-model-2099")
    assert result == GeminiTTSProvider.DEFAULT_MODEL
    assert any(
        "Unknown Gemini TTS model" in record.message
        and "gemini-fake-model-2099" in record.message
        for record in caplog.records
    ), f"Expected warning about unknown model, got: {[r.message for r in caplog.records]}"


# ---------------------------------------------------------------------------
# SUPPORTED_MODELS catalog integrity
# ---------------------------------------------------------------------------

def test_supported_models_includes_all_three_preview_models():
    expected = {
        "gemini-3.1-flash-tts-preview",
        "gemini-2.5-flash-tts-preview",
        "gemini-2.5-pro-tts-preview",
    }
    assert expected.issubset(set(GeminiTTSProvider.SUPPORTED_MODELS.keys()))


def test_default_model_is_in_supported_models():
    assert GeminiTTSProvider.DEFAULT_MODEL in GeminiTTSProvider.SUPPORTED_MODELS


def test_pricing_info_lists_all_models_and_default():
    info = GeminiTTSProvider().get_pricing_info()
    assert set(info["models"]) == set(GeminiTTSProvider.SUPPORTED_MODELS.keys())
    assert info["default_model"] == GeminiTTSProvider.DEFAULT_MODEL


# ---------------------------------------------------------------------------
# _invoke_gemini routes the requested model into the SDK call
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("model", list(GeminiTTSProvider.SUPPORTED_MODELS.keys()))
def test_invoke_gemini_passes_requested_model_to_sdk(model):
    """The model arg threaded into _invoke_gemini must reach client.models.generate_content."""
    p = GeminiTTSProvider()

    fake_client = MagicMock()
    fake_client.models.generate_content = MagicMock(return_value=MagicMock())

    fake_genai_module = MagicMock()
    fake_genai_module.Client = MagicMock(return_value=fake_client)
    fake_types_module = MagicMock()

    google_pkg = MagicMock()
    google_pkg.genai = fake_genai_module
    google_pkg.genai.types = fake_types_module

    with patch.dict(sys.modules, {
        "google": google_pkg,
        "google.genai": fake_genai_module,
        "google.genai.types": fake_types_module,
    }):
        asyncio.run(p._invoke_gemini(api_key="fake-key", text="hello", voice="Zephyr", model=model))

    args, kwargs = fake_client.models.generate_content.call_args
    assert kwargs.get("model") == model, (
        f"Expected SDK call with model={model}, got kwargs={kwargs}"
    )


# ---------------------------------------------------------------------------
# synthesize() routes the requested model end-to-end and tracks usage with it
# ---------------------------------------------------------------------------

def _fake_pcm_response(pcm_bytes: bytes = b"\x00\x00" * 100) -> MagicMock:
    """Build a minimal Gemini SDK response that _extract_audio_bytes accepts."""
    inline_data = MagicMock()
    inline_data.data = pcm_bytes

    part = MagicMock()
    part.inline_data = inline_data

    content = MagicMock()
    content.parts = [part]

    candidate = MagicMock()
    candidate.content = content

    response = MagicMock()
    response.candidates = [candidate]
    return response


@pytest.mark.parametrize("requested_model", list(GeminiTTSProvider.SUPPORTED_MODELS.keys()))
def test_synthesize_threads_model_through_to_sdk_and_tracker(requested_model, tmp_path):
    tracker = MagicMock()
    p = GeminiTTSProvider(token_tracker=tracker)
    p._api_key = "fake-key"  # bypass DB lookup

    fake_response = _fake_pcm_response()

    async def _run():
        with patch.object(p, "_invoke_gemini", return_value=fake_response) as mock_invoke:
            request = TTSRequest(
                text="hello world",
                voice="Zephyr",
                language="en",
                model=requested_model,
                agent_id=42,
                message_id="m-test",
            )
            response = await p.synthesize(request)
        return mock_invoke, response

    mock_invoke, response = asyncio.run(_run())

    assert response.success is True, f"synthesize failed: {response.error}"
    assert response.metadata["model"] == requested_model

    _, kwargs = mock_invoke.call_args
    assert kwargs.get("model") == requested_model or mock_invoke.call_args[0][-1] == requested_model

    tracker.track_usage.assert_called_once()
    _, track_kwargs = tracker.track_usage.call_args
    assert track_kwargs["model_name"] == requested_model

    if response.audio_path and os.path.exists(response.audio_path):
        os.remove(response.audio_path)


def test_synthesize_unknown_model_falls_back_to_default(tmp_path, caplog):
    tracker = MagicMock()
    p = GeminiTTSProvider(token_tracker=tracker)
    p._api_key = "fake-key"

    fake_response = _fake_pcm_response()

    async def _run():
        with patch.object(p, "_invoke_gemini", return_value=fake_response) as mock_invoke:
            request = TTSRequest(
                text="hi",
                voice="Zephyr",
                model="gemini-totally-fake-2099",
                message_id="m-fb",
            )
            with caplog.at_level(logging.WARNING, logger=p.logger.name):
                response = await p.synthesize(request)
        return mock_invoke, response

    mock_invoke, response = asyncio.run(_run())
    assert response.success is True
    assert response.metadata["model"] == GeminiTTSProvider.DEFAULT_MODEL

    # The warning came from _resolve_model
    assert any("Unknown Gemini TTS model" in r.message for r in caplog.records)

    if response.audio_path and os.path.exists(response.audio_path):
        os.remove(response.audio_path)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
