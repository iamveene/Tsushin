"""
Focused Track D tests for AudioTranscriptSkill ASR-instance behavior.
"""

import asyncio
import importlib.util
import os
import sys
import tempfile
import types
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, BACKEND_ROOT)


def _ensure_package(package_name: str, relative_path: str):
    module = sys.modules.get(package_name)
    if module is None:
        module = types.ModuleType(package_name)
        module.__path__ = [os.path.join(BACKEND_ROOT, relative_path)]
        sys.modules[package_name] = module
    return module


def _load_module(module_name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(
        module_name,
        os.path.join(BACKEND_ROOT, relative_path),
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_ensure_package("agent", "agent")
_ensure_package("agent.skills", os.path.join("agent", "skills"))
_ensure_package("hub", "hub")
_ensure_package("hub.providers", os.path.join("hub", "providers"))
_ensure_package("services", "services")

# `_ensure_package` only creates a placeholder package — `__init__.py` is
# never executed, so attributes the real package re-exports aren't present.
# Some downstream tests in the same pytest session (test_invitation_scope.py
# via `from app import app`) trigger imports like
# `from agent.skills import get_skill_manager` and
# `from hub.providers import FlightProviderRegistry` that hit these
# placeholders. Populate the placeholders with no-op shims so those imports
# resolve. Real classes get re-bound by _load_module() below where used.
_skills_pkg = sys.modules.get("agent.skills")
if _skills_pkg is not None:
    if not hasattr(_skills_pkg, "get_skill_manager"):
        _skills_pkg.get_skill_manager = lambda *args, **kwargs: None
    if not hasattr(_skills_pkg, "InboundMessage"):
        _skills_pkg.InboundMessage = type("InboundMessage", (), {})

_hub_providers_pkg = sys.modules.get("hub.providers")
if _hub_providers_pkg is not None:
    for _name in (
        "FlightProviderRegistry",
        "FlightProvider",
        "FlightSearchRequest",
        "FlightSearchResponse",
        "TTSProviderRegistry",
        "TTSProvider",
        "TTSRequest",
        "TTSResponse",
        "SearchProviderRegistry",
        "SearchProvider",
        "SearchRequest",
        "SearchResponse",
    ):
        if not hasattr(_hub_providers_pkg, _name):
            setattr(_hub_providers_pkg, _name, type(_name, (), {}))


def _ensure_real_whisper_instance_service():
    """Ensure `services.whisper_instance_service` is the REAL module.

    Other tests (e.g. test_whisper_auth.py) install a lightweight stub at
    sys.modules["services.whisper_instance_service"] during pytest collection.
    These tests exercise the real `WhisperInstanceService.update_instance` and
    `cascade_agent_skill_pins` business logic, so we must drop any stub before
    each test that depends on it.
    """
    existing = sys.modules.get("services.whisper_instance_service")
    if existing is not None and not hasattr(existing, "__file__"):
        sys.modules.pop("services.whisper_instance_service", None)


# Run once at module load time too, so the audio_transcript skill's lazy
# imports resolve against the real module on the first test that triggers
# them.
_ensure_real_whisper_instance_service()

base_module = _load_module("agent.skills.base", os.path.join("agent", "skills", "base.py"))
audio_module = _load_module(
    "agent.skills.audio_transcript",
    os.path.join("agent", "skills", "audio_transcript.py"),
)
asr_provider_module = _load_module(
    "hub.providers.asr_provider",
    os.path.join("hub", "providers", "asr_provider.py"),
)

AudioTranscriptSkill = audio_module.AudioTranscriptSkill
InboundMessage = base_module.InboundMessage
ASRResponse = asr_provider_module.ASRResponse


class _SingleResultQuery:
    def __init__(self, result):
        self._result = result

    def filter(self, *args, **kwargs):
        return self

    def first(self):
        return self._result


class _FakeWhisperDB:
    def __init__(self, *, tenant=None, instance=None):
        self.tenant = tenant
        self.instance = instance
        self.commits = 0
        self.refreshed = []

    def query(self, model):
        if getattr(model, "__name__", "") == "Tenant":
            return _SingleResultQuery(self.tenant)
        return _SingleResultQuery(self.instance)

    def commit(self):
        self.commits += 1

    def refresh(self, instance):
        self.refreshed.append(instance)


class _FakeProvider:
    def __init__(self, response):
        self._response = response

    async def transcribe(self, request):
        return self._response


def _make_message(audio_path: str) -> InboundMessage:
    return InboundMessage(
        id="msg-1",
        sender="user-1",
        sender_key="user-1",
        body="[audio]",
        chat_id="chat-1",
        chat_name=None,
        is_group=False,
        timestamp=datetime.utcnow(),
        media_type="audio/ogg",
        media_path=audio_path,
        channel="playground",
    )


def test_audio_transcript_prefers_asr_instance_when_configured():
    _ensure_real_whisper_instance_service()
    fd, audio_path = tempfile.mkstemp(suffix=".ogg")
    os.close(fd)
    try:
        skill = AudioTranscriptSkill()
        skill.set_db_session(object())
        local_response = ASRResponse(success=True, provider="speaches", text="local transcript")
        asr_instance = SimpleNamespace(
            id=7,
            is_active=True,
            vendor="speaches",
            default_model="Systran/faster-distil-whisper-small.en",
        )

        with patch(
            "services.whisper_instance_service.WhisperInstanceService.get_instance",
            return_value=asr_instance,
        ), patch(
            "agent.skills.audio_transcript.ASRProviderRegistry.get_instance_provider",
            return_value=_FakeProvider(local_response),
        ):
            result = asyncio.run(
                skill.process(
                    _make_message(audio_path),
                    {
                        "tenant_id": "tenant-alpha",
                        "asr_mode": "instance",
                        "asr_instance_id": 7,
                        "model": "whisper-1",
                        "response_mode": "conversational",
                    },
                )
            )

        assert result.success is True
        assert "local transcript" in result.output
        assert result.metadata["provider"] == "speaches"
        assert result.metadata["model"] == "Systran/faster-distil-whisper-small.en"
    finally:
        os.remove(audio_path)


def test_audio_transcript_falls_back_to_openai_when_asr_instance_fails():
    _ensure_real_whisper_instance_service()
    fd, audio_path = tempfile.mkstemp(suffix=".ogg")
    os.close(fd)
    try:
        skill = AudioTranscriptSkill()
        skill.set_db_session(object())
        failing_response = ASRResponse(success=False, provider="speaches", error="boom")
        openai_response = ASRResponse(success=True, provider="openai", text="fallback transcript")
        asr_instance = SimpleNamespace(
            id=7,
            is_active=True,
            vendor="speaches",
            default_model="Systran/faster-distil-whisper-small.en",
        )

        with patch(
            "services.whisper_instance_service.WhisperInstanceService.get_instance",
            return_value=asr_instance,
        ), patch(
            "agent.skills.audio_transcript.ASRProviderRegistry.get_instance_provider",
            return_value=_FakeProvider(failing_response),
        ), patch(
            "agent.skills.audio_transcript.ASRProviderRegistry.get_openai_provider",
            return_value=_FakeProvider(openai_response),
        ), patch(
            "agent.skills.audio_transcript.get_api_key",
            return_value="sk-test",
        ):
            result = asyncio.run(
                skill.process(
                    _make_message(audio_path),
                    {
                        "tenant_id": "tenant-alpha",
                        "asr_mode": "instance",
                        "asr_instance_id": 7,
                        "model": "whisper-1",
                        "response_mode": "transcript_only",
                    },
                )
            )

        assert result.success is True
        assert "fallback transcript" in result.output
        assert result.metadata["provider"] == "openai"
    finally:
        os.remove(audio_path)


# NOTE: tests covering the retired tenant_default ASR mode were removed when
# the tenant-level ASR default concept was rolled back. The replacement
# behavior — collapsing stale ``asr_mode='tenant_default'`` rows to OpenAI —
# is exercised by the AgentSkillsManager normalizer + the skill code path
# below (``test_audio_transcript_openai_mode_uses_cloud``).


def test_audio_transcript_openai_mode_uses_cloud():
    _ensure_real_whisper_instance_service()
    fd, audio_path = tempfile.mkstemp(suffix=".ogg")
    os.close(fd)
    try:
        skill = AudioTranscriptSkill()
        skill.set_db_session(object())
        openai_response = ASRResponse(success=True, provider="openai", text="direct openai transcript")

        with patch(
            "agent.skills.audio_transcript.ASRProviderRegistry.get_openai_provider",
            return_value=_FakeProvider(openai_response),
        ), patch(
            "agent.skills.audio_transcript.get_api_key",
            return_value="sk-test",
        ):
            result = asyncio.run(
                skill.process(
                    _make_message(audio_path),
                    {
                        "tenant_id": "tenant-alpha",
                        "asr_mode": "openai",
                        "model": "whisper-1",
                        "response_mode": "conversational",
                    },
                )
            )

        assert result.success is True
        assert "direct openai transcript" in result.output
        assert result.metadata["provider"] == "openai"
    finally:
        os.remove(audio_path)
