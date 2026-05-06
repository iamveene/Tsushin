import asyncio
import logging
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
    return router


def test_audio_skill_failure_returns_direct_error_instead_of_empty_ai_turn():
    router = _router_shell()
    router.skill_manager = _FailingSkillManager()

    with patch("agent.router.InboundMessage", BaseInboundMessage):
        processed, skip_ai, output, skill_type, media_paths = asyncio.run(
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
