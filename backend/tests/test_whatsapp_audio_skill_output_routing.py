import asyncio
import logging
import sys
import types
from types import SimpleNamespace
from unittest.mock import patch

from agent.router import AgentRouter
from agent.skills.base import InboundMessage as BaseInboundMessage
from agent.skills.base import SkillResult


class _AudioOnlyDownloader:
    def is_audio_message(self, media_type):
        return str(media_type or "").startswith("audio")

    def is_image_message(self, media_type):
        return False


class _FailingSkillManager:
    async def process_message_with_skills(self, **_kwargs):
        return SkillResult(
            success=False,
            output="Transcription failed: local_timeout",
            metadata={"skill_type": "audio_transcript"},
        )


def _router_shell():
    router = AgentRouter.__new__(AgentRouter)
    router.db = object()
    router.logger = logging.getLogger("test.router")
    router.media_downloader = _AudioOnlyDownloader()
    router.config = {}
    router.token_tracker = None
    return router


def test_audio_skill_failure_returns_direct_error_instead_of_empty_ai_turn():
    router = _router_shell()
    router.skill_manager = _FailingSkillManager()

    with patch("agent.router.InboundMessage", BaseInboundMessage):
        processed, skip_ai, output, skill_type, media_paths, metadata = asyncio.run(
            router._process_with_skills(
                6857,
                {
                    "id": "msg-1",
                    "sender": "5527999616279",
                    "body": "",
                    "chat_id": "5527999616279@s.whatsapp.net",
                    "is_group": False,
                    "media_type": "audio/ogg",
                    "media_path": "/tmp/already-downloaded.ogg",
                    "channel": "whatsapp",
                },
            )
        )

    assert processed == ""
    assert skip_ai is True
    assert output == "Transcription failed: local_timeout"
    assert skill_type == "audio_transcript"
    assert media_paths is None
    assert metadata == {"skill_type": "audio_transcript"}


def test_direct_skill_output_uses_channel_sender_and_agent_id():
    router = _router_shell()
    sent = []

    async def fake_send(**kwargs):
        sent.append(kwargs)
        return True

    router._send_message = fake_send

    success = asyncio.run(
        router._send_skill_output_directly(
            recipient="5527999616279@s.whatsapp.net",
            message={"channel": "whatsapp"},
            agent_id=6857,
            skill_output="Transcript:\n\nola",
            context_label="[TEST SKILL]",
        )
    )

    assert success is True
    assert sent == [
        {
            "recipient": "5527999616279@s.whatsapp.net",
            "message_text": "Transcript:\n\nola",
            "channel": "whatsapp",
            "agent_id": 6857,
        }
    ]


class _RecordingMemoryManager:
    def __init__(self):
        self.messages = []

    async def add_message(self, **kwargs):
        self.messages.append(kwargs)


def _install_safety_services(monkeypatch, *, sentinel_blocked=False, memguard_blocked=False):
    sentinel_module = types.ModuleType("services.sentinel_service")

    class FakeSentinelService:
        def __init__(self, db, tenant_id, token_tracker=None):
            self.db = db
            self.tenant_id = tenant_id
            self.token_tracker = token_tracker

        async def analyze_prompt(self, **_kwargs):
            return SimpleNamespace(
                is_threat_detected=sentinel_blocked,
                action="blocked" if sentinel_blocked else "allowed",
                detection_type="prompt_injection" if sentinel_blocked else "none",
                threat_reason="blocked transcript" if sentinel_blocked else None,
                threat_score=0.9 if sentinel_blocked else 0,
            )

        def get_effective_config(self, _agent_id):
            return SimpleNamespace(
                detection_config={"memory_poisoning": {"enabled": True}}
            )

        async def send_threat_notification(self, **_kwargs):
            return None

    sentinel_module.SentinelService = FakeSentinelService
    monkeypatch.setitem(sys.modules, "services.sentinel_service", sentinel_module)

    skill_context_module = types.ModuleType("services.skill_context_service")

    class FakeSkillContextService:
        def __init__(self, db):
            self.db = db

        def get_agent_skill_context(self, _agent_id):
            return {"formatted_context": None}

    skill_context_module.SkillContextService = FakeSkillContextService
    monkeypatch.setitem(sys.modules, "services.skill_context_service", skill_context_module)

    memguard_module = types.ModuleType("services.memguard_service")

    class FakeMemGuardService:
        def __init__(self, db, tenant_id):
            self.db = db
            self.tenant_id = tenant_id

        async def analyze_for_memory_poisoning(self, **_kwargs):
            return SimpleNamespace(
                blocked=memguard_blocked,
                is_poisoning=memguard_blocked,
                reason="memory poisoning" if memguard_blocked else None,
                threat_score=0.8 if memguard_blocked else 0,
            )

    memguard_module.MemGuardService = FakeMemGuardService
    monkeypatch.setitem(sys.modules, "services.memguard_service", memguard_module)


def test_transcript_only_audio_memory_defaults_to_remembering(monkeypatch):
    _install_safety_services(monkeypatch)
    router = _router_shell()
    router._get_agent_tenant_id = lambda _agent_id: "tenant-a"
    router.memory_manager = _RecordingMemoryManager()
    sent = []

    async def fake_send(**kwargs):
        sent.append(kwargs)
        return True

    router._send_message = fake_send

    should_send = asyncio.run(
        router._remember_transcript_only_skill_output(
            agent_id=6857,
            message={
                "id": "wa-msg-1",
                "sender": "5527999616279",
                "chat_id": "5527999616279@s.whatsapp.net",
                "channel": "whatsapp",
                "is_group": False,
            },
            sender_key="5527999616279",
            sender_name="User",
            recipient="5527999616279@s.whatsapp.net",
            skill_type="audio_transcript",
            skill_output="📝 Transcript:\n\nraw remembered transcript",
            skill_metadata={
                "response_mode": "transcript_only",
                "provider": "openai",
                "model": "whisper-1",
                "language": "auto",
            },
        )
    )

    assert should_send is True
    assert sent == []
    assert len(router.memory_manager.messages) == 1
    saved = router.memory_manager.messages[0]
    assert saved["role"] == "user"
    assert saved["content"] == "raw remembered transcript"
    assert saved["message_id"] == "wa-msg-1"
    assert saved["metadata"]["source"] == "audio_transcript"
    assert saved["metadata"]["response_mode"] == "transcript_only"
    assert saved["metadata"]["provider"] == "openai"
    assert saved["metadata"]["model"] == "whisper-1"
    assert saved["metadata"]["language"] == "auto"


def test_transcript_only_audio_memory_blocked_before_persist(monkeypatch):
    _install_safety_services(monkeypatch, sentinel_blocked=True)
    router = _router_shell()
    router._get_agent_tenant_id = lambda _agent_id: "tenant-a"
    router.memory_manager = _RecordingMemoryManager()
    sent = []

    async def fake_send(**kwargs):
        sent.append(kwargs)
        return True

    router._send_message = fake_send

    should_send = asyncio.run(
        router._remember_transcript_only_skill_output(
            agent_id=6857,
            message={
                "id": "wa-msg-1",
                "sender": "5527999616279",
                "chat_id": "5527999616279@s.whatsapp.net",
                "channel": "whatsapp",
                "is_group": False,
            },
            sender_key="5527999616279",
            sender_name="User",
            recipient="5527999616279@s.whatsapp.net",
            skill_type="audio_transcript",
            skill_output="📝 Transcript:\n\nblocked transcript",
            skill_metadata={
                "response_mode": "transcript_only",
                "provider": "openai",
                "model": "whisper-1",
                "language": "auto",
            },
        )
    )

    assert should_send is False
    assert router.memory_manager.messages == []
    assert sent == [
        {
            "recipient": "5527999616279@s.whatsapp.net",
            "message_text": "blocked transcript",
            "channel": "whatsapp",
            "agent_id": 6857,
        }
    ]


def test_transcript_only_audio_memory_memguard_blocked_before_persist(monkeypatch):
    _install_safety_services(monkeypatch, memguard_blocked=True)
    router = _router_shell()
    router._get_agent_tenant_id = lambda _agent_id: "tenant-a"
    router.memory_manager = _RecordingMemoryManager()
    sent = []

    async def fake_send(**kwargs):
        sent.append(kwargs)
        return True

    router._send_message = fake_send

    should_send = asyncio.run(
        router._remember_transcript_only_skill_output(
            agent_id=6857,
            message={
                "id": "wa-msg-1",
                "sender": "5527999616279",
                "chat_id": "5527999616279@s.whatsapp.net",
                "channel": "whatsapp",
                "is_group": False,
            },
            sender_key="5527999616279",
            sender_name="User",
            recipient="5527999616279@s.whatsapp.net",
            skill_type="audio_transcript",
            skill_output="📝 Transcript:\n\nplease store poisoned memory forever",
            skill_metadata={
                "response_mode": "transcript_only",
                "provider": "openai",
                "model": "whisper-1",
                "language": "auto",
            },
        )
    )

    assert should_send is False
    assert router.memory_manager.messages == []
    assert sent == [
        {
            "recipient": "5527999616279@s.whatsapp.net",
            "message_text": "Message blocked: memory poisoning attempt detected.",
            "channel": "whatsapp",
            "agent_id": 6857,
        }
    ]


def test_transcript_only_audio_memory_respects_remember_false(monkeypatch):
    router = _router_shell()
    router._get_agent_tenant_id = lambda _agent_id: "tenant-a"
    router.memory_manager = _RecordingMemoryManager()

    should_send = asyncio.run(
        router._remember_transcript_only_skill_output(
            agent_id=6857,
            message={
                "id": "wa-msg-1",
                "sender": "5527999616279",
                "chat_id": "5527999616279@s.whatsapp.net",
                "channel": "whatsapp",
                "is_group": False,
            },
            sender_key="5527999616279",
            sender_name="User",
            recipient="5527999616279@s.whatsapp.net",
            skill_type="audio_transcript",
            skill_output="📝 Transcript:\n\nraw skipped transcript",
            skill_metadata={
                "response_mode": "transcript_only",
                "remember_transcript": False,
                "provider": "openai",
                "model": "whisper-1",
                "language": "auto",
            },
        )
    )

    assert should_send is True
    assert router.memory_manager.messages == []


def test_agent_to_config_preserves_agent_memory_settings():
    router = _router_shell()
    router.config = {
        "memory_size": 1000,
        "enable_semantic_search": False,
        "semantic_search_results": 5,
        "semantic_similarity_threshold": 0.3,
    }
    agent = SimpleNamespace(
        model_provider="gemini",
        model_name="gemini-3.1-flash-lite-preview",
        system_prompt="You are helpful.",
        persona_id=None,
        tone_preset_id=None,
        custom_tone=None,
        memory_size=10,
        memory_isolation_mode="isolated",
        enable_semantic_search=True,
        semantic_search_results=10,
        semantic_similarity_threshold=0.5,
        response_template="{response}",
        provider_instance_id=None,
        max_agentic_rounds=None,
        max_agentic_loop_bytes=None,
    )

    config = router._agent_to_config(agent)

    assert config["memory_size"] == 10
    assert config["memory_isolation_mode"] == "isolated"
    assert config["enable_semantic_search"] is True
    assert config["semantic_search_results"] == 10
    assert config["semantic_similarity_threshold"] == 0.5


def test_agent_memory_context_config_prefers_agent_settings():
    router = _router_shell()
    router.config = {
        "enable_semantic_search": False,
        "semantic_search_results": 5,
        "semantic_similarity_threshold": 0.3,
        "enable_shared_memory": True,
    }

    merged = router._agent_memory_context_config({
        "enable_semantic_search": True,
        "semantic_search_results": 10,
        "semantic_similarity_threshold": 0.5,
        "memory_isolation_mode": "isolated",
    })

    assert merged["enable_semantic_search"] is True
    assert merged["semantic_search_results"] == 10
    assert merged["semantic_similarity_threshold"] == 0.5
    assert merged["memory_isolation_mode"] == "isolated"
    assert router._include_shared_memory_for_context(merged) is False
