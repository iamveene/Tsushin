"""
Phase 3.1 Gmail send checkpoint tests.

Small, fast unit-style tests that prove the Track G scope:
- GmailService can build/send outbound requests for send/draft/reply
- GmailService blocks outbound calls when gmail.send is unavailable
- GmailSkill dispatches outbound tool actions and respects capability gating
"""

import asyncio
import base64
import os
import sys
import types
import importlib.util
from types import SimpleNamespace


BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


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


docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

_ensure_package("agent", "agent")
_ensure_package("agent.skills", os.path.join("agent", "skills"))
_ensure_package("hub", "hub")
_ensure_package("hub.google", os.path.join("hub", "google"))

_load_module("agent.skills.base", os.path.join("agent", "skills", "base.py"))
GmailSkill = _load_module(
    "agent.skills.gmail_skill",
    os.path.join("agent", "skills", "gmail_skill.py"),
).GmailSkill
GmailService = _load_module(
    "hub.google.gmail_service",
    os.path.join("hub", "google", "gmail_service.py"),
).GmailService


def _decode_raw(raw_message: str) -> str:
    return base64.urlsafe_b64decode(raw_message.encode("utf-8")).decode("utf-8", errors="replace")


def _make_service(scope: str = "https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/gmail.send"):
    service = object.__new__(GmailService)
    service.integration_id = 123
    service._get_latest_token = lambda: SimpleNamespace(scope=scope) if scope is not None else None
    service._get_integration = lambda: SimpleNamespace(email_address="agent@example.com")
    service._log_info = lambda *_args, **_kwargs: None
    service._log_error = lambda *_args, **_kwargs: None
    return service


def test_gmail_service_send_message_posts_raw_payload():
    service = _make_service()
    captured = {}

    async def fake_make_request(method, endpoint, params=None, json_data=None, timeout=10.0):
        captured.update(
            {
                "method": method,
                "endpoint": endpoint,
                "params": params,
                "json_data": json_data,
                "timeout": timeout,
            }
        )
        return {"id": "msg-123", "threadId": "thread-123"}

    service._make_request = fake_make_request

    result = asyncio.run(
        service.send_message(
            to=["to@example.com"],
            subject="Checkpoint Subject",
            body_text="Checkpoint Body",
            cc="cc@example.com",
        )
    )

    raw = _decode_raw(captured["json_data"]["raw"])
    assert captured["method"] == "POST"
    assert captured["endpoint"] == "/users/me/messages/send"
    assert "To: to@example.com" in raw
    assert "Cc: cc@example.com" in raw
    assert "Subject: Checkpoint Subject" in raw
    assert "Checkpoint Body" in raw
    assert result["id"] == "msg-123"


def test_gmail_service_create_draft_wraps_message_payload():
    service = _make_service()
    captured = {}

    async def fake_make_request(method, endpoint, params=None, json_data=None, timeout=10.0):
        captured.update({"method": method, "endpoint": endpoint, "json_data": json_data})
        return {"id": "draft-123", "message": {"id": "msg-draft-123"}}

    service._make_request = fake_make_request

    result = asyncio.run(
        service.create_draft(
            to="draft@example.com",
            subject="Draft Subject",
            body_text="Draft Body",
        )
    )

    raw = _decode_raw(captured["json_data"]["message"]["raw"])
    assert captured["method"] == "POST"
    assert captured["endpoint"] == "/users/me/drafts"
    assert "To: draft@example.com" in raw
    assert "Subject: Draft Subject" in raw
    assert "Draft Body" in raw
    assert result["id"] == "draft-123"


def test_gmail_service_reply_to_message_uses_thread_headers_and_reply_all():
    service = _make_service()

    async def fake_get_message(message_id, format="full"):
        assert message_id == "orig-msg"
        assert format == "full"
        return {
            "threadId": "thread-789",
            "payload": {
                "headers": [
                    {"name": "From", "value": "Sender <sender@example.com>"},
                    {"name": "To", "value": "Agent <agent@example.com>, Teammate <teammate@example.com>"},
                    {"name": "Cc", "value": "Copy <copy@example.com>"},
                    {"name": "Subject", "value": "Original Subject"},
                    {"name": "Message-Id", "value": "<orig@example.com>"},
                    {"name": "References", "value": "<older@example.com>"},
                ]
            },
        }

    captured = {}

    async def fake_send_message(**kwargs):
        captured.update(kwargs)
        return {"id": "reply-123", "threadId": kwargs["thread_id"]}

    service.get_message = fake_get_message
    service.send_message = fake_send_message

    result = asyncio.run(
        service.reply_to_message(
            "orig-msg",
            body_text="Reply body",
            reply_all=True,
            cc="extra@example.com",
        )
    )

    assert captured["to"] == ["sender@example.com"]
    assert captured["thread_id"] == "thread-789"
    assert captured["in_reply_to"] == "<orig@example.com>"
    assert captured["references"] == "<older@example.com> <orig@example.com>"
    assert captured["subject"] == "Re: Original Subject"
    assert captured["body_text"] == "Reply body"
    assert captured["cc"] == ["teammate@example.com", "copy@example.com", "extra@example.com"]
    assert result["id"] == "reply-123"


def test_gmail_service_send_requires_gmail_send_scope():
    service = _make_service(scope="https://www.googleapis.com/auth/gmail.readonly")

    try:
        asyncio.run(
            service.send_message(
                to="to@example.com",
                subject="No Scope",
                body_text="Blocked",
            )
        )
    except PermissionError as exc:
        assert "gmail.send" in str(exc)
    else:
        raise AssertionError("send_message should require gmail.send")


def test_gmail_skill_outbound_actions_dispatch_to_service():
    skill = GmailSkill()
    calls = []

    class FakeService:
        async def send_message(self, **kwargs):
            calls.append(("send", kwargs))
            return {"id": "sent-1", "threadId": "thread-sent"}

        async def create_draft(self, **kwargs):
            calls.append(("draft", kwargs))
            return {"id": "draft-1", "message": {"id": "msg-draft-1"}}

        async def reply_to_message(self, message_id, **kwargs):
            calls.append(("reply", {"message_id": message_id, **kwargs}))
            return {"id": "reply-1", "threadId": "thread-reply"}

    fake_service = FakeService()
    skill._get_gmail_service = lambda config=None: fake_service
    config = skill.get_default_config()

    send_result = asyncio.run(
        skill.execute_tool(
            {"action": "send", "to": "to@example.com", "subject": "Hi", "body": "Hello"},
            message=None,
            config=config,
        )
    )
    draft_result = asyncio.run(
        skill.execute_tool(
            {"action": "draft", "to": ["draft@example.com"], "subject": "Draft", "body": "Draft body"},
            message=None,
            config=config,
        )
    )
    reply_result = asyncio.run(
        skill.execute_tool(
            {"action": "reply", "message_id": "orig-123", "body": "Reply body", "reply_all": True},
            message=None,
            config=config,
        )
    )

    assert send_result.success is True
    assert draft_result.success is True
    assert reply_result.success is True
    assert calls[0][0] == "send"
    assert calls[0][1]["to"] == ["to@example.com"]
    assert calls[1][0] == "draft"
    assert calls[1][1]["to"] == ["draft@example.com"]
    assert calls[2][0] == "reply"
    assert calls[2][1]["message_id"] == "orig-123"
    assert calls[2][1]["reply_all"] is True


def test_gmail_skill_send_capability_gate_blocks_outbound_action():
    skill = GmailSkill()
    called = {"service": False}

    class FakeService:
        async def send_message(self, **kwargs):
            called["service"] = True
            return {"id": "sent-1"}

    skill._get_gmail_service = lambda config=None: FakeService()
    config = skill.get_default_config()
    config["capabilities"] = {
        **config["capabilities"],
        "send_email": {"enabled": False},
    }

    result = asyncio.run(
        skill.execute_tool(
            {"action": "send", "to": "to@example.com", "subject": "Blocked", "body": "Nope"},
            message=None,
            config=config,
        )
    )

    assert result.success is False
    assert result.metadata["error"] == "capability_disabled"
    assert called["service"] is False
