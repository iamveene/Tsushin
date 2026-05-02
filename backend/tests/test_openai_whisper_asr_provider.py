"""Unit tests for the OpenAI Whisper ASR provider + container-manager dispatch.

These tests verify:
  * `OpenAIWhisperASRProvider.transcribe` posts to ``/asr`` with the right
    multipart field name (``audio_file``) and query params.
  * The provider tolerates a missing API token (the upstream
    onerahmet/openai-whisper-asr-webservice has no native auth — we rely on
    container-network isolation), so a None token must NOT crash the call.
  * Empty-text responses surface as ``success=False`` with ``empty_transcription``
    so the audio_transcript skill falls back to OpenAI gracefully.
  * The vendor dispatch table in ``WhisperContainerManager`` knows about both
    speaches and openai_whisper, with distinct image factories, internal ports,
    and warm-up endpoints.
  * ``WhisperContainerManager._build_environment`` emits the right env shape
    per vendor — speaches expects ``API_KEY`` + ``PRELOAD_MODELS``; openai_whisper
    expects ``ASR_ENGINE=openai_whisper`` + ``ASR_MODEL`` + ``MODEL_IDLE_TIMEOUT``.

Run via:

    docker exec tsushin-backend pytest backend/tests/test_openai_whisper_asr_provider.py -v
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import importlib
import sys
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

class _MockResponse:
    """Stand-in for an httpx.Response with the bits the provider reads."""

    def __init__(self, status_code: int, payload: Optional[Dict[str, Any]] = None, text: str = ""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class _MockAsyncClient:
    def __init__(self, response: _MockResponse, capture: Dict[str, Any]):
        self._response = response
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def post(self, url, *, headers=None, params=None, files=None, **kwargs):
        self._capture["url"] = url
        self._capture["headers"] = headers
        self._capture["params"] = params
        self._capture["files"] = list(files.keys()) if files else []
        return self._response


def _make_instance(vendor: str = "openai_whisper") -> MagicMock:
    inst = MagicMock()
    inst.id = 42
    inst.tenant_id = "tenant-test"
    inst.base_url = "http://whisper-test:9000"
    inst.default_model = "base"
    inst.vendor = vendor
    inst.is_active = True
    return inst


def _make_audio_path() -> str:
    fd, path = tempfile.mkstemp(suffix=".wav")
    os.write(fd, b"RIFF\x00\x00\x00\x00WAVEfmt ")
    os.close(fd)
    return path


# ---------------------------------------------------------------------------
# Provider tests
# ---------------------------------------------------------------------------

def test_openai_whisper_provider_posts_to_asr_endpoint():
    from hub.providers.asr_provider import ASRRequest
    from hub.providers.openai_whisper_asr_provider import OpenAIWhisperASRProvider

    audio_path = _make_audio_path()
    capture: Dict[str, Any] = {}
    response = _MockResponse(200, payload={"text": "hello world", "language": "en"})

    instance = _make_instance()
    db = MagicMock()

    with patch("hub.providers.openai_whisper_asr_provider.httpx.AsyncClient") as mock_client_cls, \
         patch("hub.providers.openai_whisper_asr_provider.WhisperInstanceService.resolve_api_token") as mock_resolve:
        mock_resolve.return_value = "internal-token"
        mock_client_cls.return_value = _MockAsyncClient(response, capture)

        provider = OpenAIWhisperASRProvider(instance=instance, db=db)
        request = ASRRequest(
            audio_path=audio_path,
            model="base",
            language="en",
            tenant_id="tenant-test",
        )
        result = asyncio.run(provider.transcribe(request))

    assert result.success
    assert result.text == "hello world"
    assert result.provider == "openai_whisper"
    assert result.metadata.get("language") == "en"
    assert result.metadata.get("model") == "base"

    # Endpoint shape: /asr (not /v1/audio/transcriptions)
    assert capture["url"].endswith("/asr"), (
        f"openai_whisper must POST to /asr, got {capture['url']}"
    )
    # Multipart field is `audio_file`, not `file`
    assert capture["files"] == ["audio_file"], (
        f"openai-whisper-asr-webservice expects 'audio_file' multipart field, "
        f"got {capture['files']}"
    )
    # Query params: task=transcribe, language, output, encode
    params = capture["params"] or {}
    assert params.get("task") == "transcribe"
    assert params.get("language") == "en"
    assert params.get("output") == "json"


def test_openai_whisper_provider_skips_auth_header_when_no_token():
    """Upstream image has no native auth — rely on tsushin-network isolation."""
    from hub.providers.asr_provider import ASRRequest
    from hub.providers.openai_whisper_asr_provider import OpenAIWhisperASRProvider

    audio_path = _make_audio_path()
    capture: Dict[str, Any] = {}
    response = _MockResponse(200, payload={"text": "ok"})
    instance = _make_instance()
    db = MagicMock()

    with patch("hub.providers.openai_whisper_asr_provider.httpx.AsyncClient") as mock_client_cls, \
         patch("hub.providers.openai_whisper_asr_provider.WhisperInstanceService.resolve_api_token") as mock_resolve:
        mock_resolve.return_value = None
        mock_client_cls.return_value = _MockAsyncClient(response, capture)

        provider = OpenAIWhisperASRProvider(instance=instance, db=db)
        result = asyncio.run(provider.transcribe(ASRRequest(audio_path=audio_path, model="base", language="en")))

    assert result.success
    headers = capture.get("headers") or {}
    # Either header omitted or no Bearer added — both are acceptable; the upstream
    # webservice will accept the request either way.
    assert "Authorization" not in headers


def test_openai_whisper_provider_returns_empty_transcription_failure():
    from hub.providers.asr_provider import ASRRequest
    from hub.providers.openai_whisper_asr_provider import OpenAIWhisperASRProvider

    audio_path = _make_audio_path()
    capture: Dict[str, Any] = {}
    response = _MockResponse(200, payload={"text": "   "})  # whitespace only
    instance = _make_instance()
    db = MagicMock()

    with patch("hub.providers.openai_whisper_asr_provider.httpx.AsyncClient") as mock_client_cls, \
         patch("hub.providers.openai_whisper_asr_provider.WhisperInstanceService.resolve_api_token") as mock_resolve:
        mock_resolve.return_value = "internal-token"
        mock_client_cls.return_value = _MockAsyncClient(response, capture)

        provider = OpenAIWhisperASRProvider(instance=instance, db=db)
        result = asyncio.run(provider.transcribe(ASRRequest(audio_path=audio_path, model="base", language="en")))

    assert not result.success
    assert result.error == "empty_transcription"


def test_openai_whisper_provider_propagates_http_error():
    from hub.providers.asr_provider import ASRRequest
    from hub.providers.openai_whisper_asr_provider import OpenAIWhisperASRProvider

    audio_path = _make_audio_path()
    capture: Dict[str, Any] = {}
    response = _MockResponse(503, payload=None, text="model still loading")
    instance = _make_instance()
    db = MagicMock()

    with patch("hub.providers.openai_whisper_asr_provider.httpx.AsyncClient") as mock_client_cls, \
         patch("hub.providers.openai_whisper_asr_provider.WhisperInstanceService.resolve_api_token") as mock_resolve:
        mock_resolve.return_value = None
        mock_client_cls.return_value = _MockAsyncClient(response, capture)

        provider = OpenAIWhisperASRProvider(instance=instance, db=db)
        result = asyncio.run(provider.transcribe(ASRRequest(audio_path=audio_path, model="base", language="en")))

    assert not result.success
    assert result.error.startswith("http_503")


def test_openai_whisper_provider_no_db_session_returns_failure():
    from hub.providers.asr_provider import ASRRequest
    from hub.providers.openai_whisper_asr_provider import OpenAIWhisperASRProvider

    instance = _make_instance()
    provider = OpenAIWhisperASRProvider(instance=instance, db=None)
    result = asyncio.run(provider.transcribe(ASRRequest(audio_path="/tmp/none.wav", model="base", language="en")))
    assert not result.success
    assert result.error == "missing_db_session"


# ---------------------------------------------------------------------------
# Container manager dispatch tests
# ---------------------------------------------------------------------------

def test_container_manager_vendor_configs_have_both_engines():
    from services.whisper_container_manager import VENDOR_CONFIGS

    assert {"speaches", "openai_whisper"} <= set(VENDOR_CONFIGS.keys())

    speaches = VENDOR_CONFIGS["speaches"]
    assert speaches["transcribe_path"] == "/v1/audio/transcriptions"
    assert speaches["transcribe_field"] == "file"
    assert speaches["internal_port"] == 8000
    assert speaches["auth_scheme"] == "bearer"

    oai = VENDOR_CONFIGS["openai_whisper"]
    assert oai["transcribe_path"] == "/asr"
    assert oai["transcribe_field"] == "audio_file"
    assert oai["internal_port"] == 9000
    assert oai["auth_scheme"] == "none"
    # Image must be the openai-whisper-asr-webservice (not speaches!)
    image = oai["image_factory"]()
    assert "openai-whisper-asr-webservice" in image, (
        f"openai_whisper VENDOR_CONFIGS must reference onerahmet/"
        f"openai-whisper-asr-webservice, got {image}"
    )
    # Speaches still points at speaches-ai
    assert "speaches-ai/speaches" in speaches["image_factory"]()


def test_container_manager_build_environment_per_vendor():
    from services.whisper_container_manager import WhisperContainerManager

    mgr = WhisperContainerManager()

    speaches_env = mgr._build_environment("speaches", token="abc", default_model="model-a")
    assert speaches_env["API_KEY"] == "abc"
    assert speaches_env["SPEACHES_API_KEY"] == "abc"
    assert "model-a" in speaches_env["PRELOAD_MODELS"]
    assert "ASR_ENGINE" not in speaches_env

    oai_env = mgr._build_environment("openai_whisper", token="abc", default_model="base")
    assert oai_env["ASR_ENGINE"] == "openai_whisper"
    assert oai_env["ASR_MODEL"] == "base"
    # Token is irrelevant for the openai-whisper-asr-webservice (no native auth) —
    # the env must NOT pass API_KEY through (would just be ignored, but keeping
    # it tight avoids accidentally leaking a token where the upstream service
    # might log env at boot).
    assert "API_KEY" not in oai_env
    assert "SPEACHES_API_KEY" not in oai_env


# ---------------------------------------------------------------------------
# WhisperInstanceService vendor support
# ---------------------------------------------------------------------------

def test_supported_vendors_includes_openai_whisper():
    from services.whisper_instance_service import (
        SUPPORTED_VENDORS,
        AUTO_PROVISIONABLE_VENDORS,
        default_model_for_vendor,
    )

    assert "openai_whisper" in SUPPORTED_VENDORS
    assert "openai_whisper" in AUTO_PROVISIONABLE_VENDORS
    # Default model for openai_whisper must be a plain whisper size (not a HF id).
    assert default_model_for_vendor("openai_whisper") == "base"
    # Speaches still defaults to a HF model id.
    assert "/" in default_model_for_vendor("speaches")


# ---------------------------------------------------------------------------
# Registry registration
# ---------------------------------------------------------------------------

def test_asr_registry_includes_openai_whisper():
    from hub.providers.asr_registry import ASRProviderRegistry

    ASRProviderRegistry.initialize_providers()
    assert ASRProviderRegistry.get_provider_class("openai_whisper") is not None
    assert ASRProviderRegistry.get_provider_class("speaches") is not None
    assert ASRProviderRegistry.get_provider_class("openai") is not None
