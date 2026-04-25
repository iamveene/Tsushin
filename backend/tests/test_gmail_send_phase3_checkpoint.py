"""
Phase 3.1 Gmail send checkpoint tests.

Small, fast unit-style tests that prove the Track G scope:
- GmailService can build/send outbound requests for send/draft/reply
- GmailService blocks outbound calls when the required Gmail write scopes are unavailable
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

# `_ensure_package` only creates a placeholder package — `__init__.py` is
# never executed, so `get_skill_manager` / `InboundMessage` aren't on the
# placeholder. Downstream tests in the same pytest session that import
# `from app import app` need those attributes for `agent/agent_service.py`'s
# top-level `from .skills import get_skill_manager` to succeed.
_skills_pkg = sys.modules.get("agent.skills")
if _skills_pkg is not None:
    if not hasattr(_skills_pkg, "get_skill_manager"):
        _skills_pkg.get_skill_manager = lambda *args, **kwargs: None
    if not hasattr(_skills_pkg, "InboundMessage"):
        _skills_pkg.InboundMessage = type("InboundMessage", (), {})

# `api/routes_google.py` does `from hub.google import GoogleOAuthHandler, ...`
# at module import. If our placeholder `hub.google` is the resident module,
# those symbols are missing — populate stubs.
_hub_google_pkg = sys.modules.get("hub.google")
if _hub_google_pkg is not None:
    for _name in (
        "GoogleOAuthHandler",
        "GmailService",
        "CalendarService",
    ):
        if not hasattr(_hub_google_pkg, _name):
            setattr(_hub_google_pkg, _name, type(_name, (), {}))
    if not hasattr(_hub_google_pkg, "get_google_oauth_handler"):
        _hub_google_pkg.get_google_oauth_handler = lambda *args, **kwargs: None

_load_module("agent.skills.base", os.path.join("agent", "skills", "base.py"))
GmailSkill = _load_module(
    "agent.skills.gmail_skill",
    os.path.join("agent", "skills", "gmail_skill.py"),
).GmailSkill
GmailService = _load_module(
    "hub.google.gmail_service",
    os.path.join("hub", "google", "gmail_service.py"),
).GmailService

GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GMAIL_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
GMAIL_COMPOSE_SCOPE = "https://www.googleapis.com/auth/gmail.compose"
GMAIL_MODIFY_SCOPE = "https://www.googleapis.com/auth/gmail.modify"
GMAIL_FULL_ACCESS_SCOPE = "https://mail.google.com/"


def _decode_raw(raw_message: str) -> str:
    return base64.urlsafe_b64decode(raw_message.encode("utf-8")).decode("utf-8", errors="replace")


def _make_service(scope: str = f"{GMAIL_READONLY_SCOPE} {GMAIL_SEND_SCOPE} {GMAIL_COMPOSE_SCOPE}"):
    service = object.__new__(GmailService)
    service.integration_id = 123
    service._get_latest_token = lambda: SimpleNamespace(scope=scope) if scope is not None else None
    service._get_integration = lambda: SimpleNamespace(email_address="agent@example.com")
    service._log_info = lambda *_args, **_kwargs: None
    service._log_error = lambda *_args, **_kwargs: None
    return service


def test_gmail_service_send_message_posts_raw_payload():
    service = _make_service(scope=f"{GMAIL_READONLY_SCOPE} {GMAIL_SEND_SCOPE}")
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


def test_gmail_service_send_accepts_gmail_compose_scope():
    service = _make_service(scope=f"{GMAIL_READONLY_SCOPE} {GMAIL_COMPOSE_SCOPE}")

    async def fake_make_request(method, endpoint, params=None, json_data=None, timeout=10.0):
        assert method == "POST"
        assert endpoint == "/users/me/messages/send"
        assert "raw" in json_data
        return {"id": "msg-compose-123"}

    service._make_request = fake_make_request

    result = asyncio.run(
        service.send_message(
            to="compose@example.com",
            subject="Compose Subject",
            body_text="Compose Body",
        )
    )

    assert result["id"] == "msg-compose-123"


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


def test_gmail_service_create_draft_accepts_draft_compatible_scopes():
    for scope in (GMAIL_COMPOSE_SCOPE, GMAIL_MODIFY_SCOPE, GMAIL_FULL_ACCESS_SCOPE):
        service = _make_service(scope=f"{GMAIL_READONLY_SCOPE} {scope}")

        async def fake_make_request(method, endpoint, params=None, json_data=None, timeout=10.0):
            assert method == "POST"
            assert endpoint == "/users/me/drafts"
            assert "raw" in json_data["message"]
            return {"id": f"draft-{scope}", "message": {"id": "msg-draft"}}

        service._make_request = fake_make_request

        result = asyncio.run(
            service.create_draft(
                to="draft@example.com",
                subject="Draft-compatible scope",
                body_text="Draft Body",
            )
        )

        assert result["id"] == f"draft-{scope}"


def test_gmail_service_reply_to_message_uses_thread_headers_and_reply_all():
    service = _make_service(scope=f"{GMAIL_READONLY_SCOPE} {GMAIL_SEND_SCOPE}")

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


def test_gmail_service_send_requires_send_compatible_scope():
    service = _make_service(scope=GMAIL_READONLY_SCOPE)

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
        assert "gmail.compose" in str(exc)
    else:
        raise AssertionError("send_message should require a send-compatible Gmail scope")


def test_gmail_service_draft_requires_compose_scope():
    service = _make_service(scope=f"{GMAIL_READONLY_SCOPE} {GMAIL_SEND_SCOPE}")

    try:
        asyncio.run(
            service.create_draft(
                to="draft@example.com",
                subject="Draft Scope",
                body_text="Blocked",
            )
        )
    except PermissionError as exc:
        assert "gmail.compose" in str(exc)
        assert "gmail.modify" in str(exc)
        assert "mail.google.com/" in str(exc)
    else:
        raise AssertionError("create_draft should require gmail.compose or broader Gmail write scope")


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
    # GmailSkill defaults send/reply/draft to enabled=False (write actions ship
    # off — same safety stance as JiraSkill). This test exercises the
    # service-dispatch path on purpose, so it must enable the three write
    # capabilities explicitly. The companion gate test
    # `test_gmail_skill_send_capability_gate_blocks_outbound_action`
    # asserts the off-by-default behavior using the unmodified default config.
    config = skill.get_default_config()
    for cap in ("send_email", "reply_email", "draft_email"):
        config["capabilities"][cap]["enabled"] = True

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
