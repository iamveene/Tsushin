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
