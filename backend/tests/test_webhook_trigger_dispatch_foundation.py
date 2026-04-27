from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
import time
import types
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

from api import routes_webhook_inbound as inbound  # noqa: E402
from models import (  # noqa: E402
    Agent,
    Base,
    ChannelEventDedupe,
    Config,
    Contact,
    ContinuousAgent,
    ContinuousSubscription,
    MessageQueue,
    WebhookIntegration,
)
from models_rbac import Tenant, User  # noqa: E402


class _RequestStub:
    def __init__(self, body: bytes):
        self._body = body
        self.client = SimpleNamespace(host="127.0.0.1")

    async def body(self) -> bytes:
        return self._body


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            Config.__table__,
            Contact.__table__,
            Agent.__table__,
            WebhookIntegration.__table__,
            MessageQueue.__table__,
            ChannelEventDedupe.__table__,
            ContinuousAgent.__table__,
            ContinuousSubscription.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture(autouse=True)
def webhook_auth(monkeypatch):
    monkeypatch.setattr(inbound, "_decrypt_secret", lambda db, integration: "secret")
    monkeypatch.setattr(inbound.api_rate_limiter, "allow", lambda *args, **kwargs: True)


def _seed_base(db, *, default_agent: bool = True):
    db.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    db.add(
        User(
            id=1,
            tenant_id="tenant-a",
            email="owner@example.com",
            password_hash="hashed",
            is_active=True,
        )
    )
    db.add(Config(id=1, messages_db_path="/tmp/messages.db", emergency_stop=False))
    db.add(Contact(id=101, tenant_id="tenant-a", friendly_name="Webhook Agent", role="agent"))
    agent = Agent(
        id=201,
        tenant_id="tenant-a",
        contact_id=101,
        system_prompt="You handle webhook events.",
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        response_template="{response}",
        enabled_channels=["webhook"],
        is_active=True,
        is_default=False,
    )
    db.add(agent)
    integration = WebhookIntegration(
        id=301,
        tenant_id="tenant-a",
        integration_name="Webhook A",
        slug="wh-tenant-a",
        api_secret_encrypted="encrypted",
        api_secret_preview="whsec_xxx",
        created_by=1,
        default_agent_id=agent.id if default_agent else None,
        is_active=True,
        status="active",
    )
    db.add(integration)
    db.commit()
    return agent, integration


def _signed_request(payload: dict):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    timestamp = str(int(time.time()))
    signed_input = f"{timestamp}.".encode("utf-8") + body
    signature = hmac.new(b"secret", signed_input, hashlib.sha256).hexdigest()
    return _RequestStub(body), f"sha256={signature}", timestamp


def _receive(db, payload: dict, slug: str = "wh-tenant-a"):
    request, signature, timestamp = _signed_request(payload)
    return asyncio.run(
        inbound.receive_webhook(
            slug=slug,
            request=request,
            x_tsushin_signature=signature,
            x_tsushin_timestamp=timestamp,
            db=db,
        )
    )


def test_webhook_trigger_event_queues_direct_agent_message(db_session, monkeypatch):
    agent, integration = _seed_base(db_session)

    async def no_dispatch_service(**kwargs):
        return None

    monkeypatch.setattr(inbound, "_maybe_dispatch_trigger_event", no_dispatch_service)

    response = _receive(
        db_session,
        {
            "message": "Build report",
            "sender_id": "customer-1",
            "sender_name": "Customer One",
            "source_id": "evt-1",
        },
    )

    item = db_session.query(MessageQueue).one()
    assert response == {
        "status": "queued",
        "queue_id": item.id,
        "poll_url": f"/api/v1/queue/{item.id}",
    }
    assert item.channel == "webhook"
    assert item.message_type == "trigger_event"
    assert item.tenant_id == integration.tenant_id
    assert item.agent_id == agent.id
    assert item.sender_key == "webhook_301_customer-1"
    assert item.payload["webhook_id"] == integration.id
    assert item.payload["message_text"] == "Build report"
    assert item.payload["source_id"] == "evt-1"


def test_webhook_duplicate_signed_envelope_returns_409(
    db_session,
):
    """
    BUG-705: posting the same signed envelope twice now returns 409 on the
    second attempt (the dedupe key is derived from the signed inputs, not
    wall-clock millis). The first call writes both a replay-protection row
    AND the trigger-dispatch dedupe row keyed on source_id; the second call
    collides on the replay-protection row and raises before reaching the
    trigger-dispatch path.
    """
    agent, _integration = _seed_base(db_session)

    first_response = _receive(
        db_session,
        {
            "message": "Build report",
            "sender_id": "customer-1",
            "source_id": "evt-dup",
        },
    )
    assert first_response["status"] == "queued"

    with pytest.raises(HTTPException) as exc_info:
        _receive(
            db_session,
            {
                "message": "Build report",
                "sender_id": "customer-1",
                "source_id": "evt-dup",
            },
        )
    assert exc_info.value.status_code == 409
    assert "duplicate" in str(exc_info.value.detail).lower()

    # Only the first call enqueued.
    assert db_session.query(MessageQueue).count() == 1

    # Two dedupe rows from the first call: one replay-protection (sha256 hex,
    # 64 chars) and one trigger-dispatch row keyed on source_id="evt-dup".
    dedupe_rows = (
        db_session.query(ChannelEventDedupe)
        .order_by(ChannelEventDedupe.id.asc())
        .all()
    )
    assert len(dedupe_rows) == 2
    keys = {r.dedupe_key for r in dedupe_rows}
    assert "evt-dup" in keys
    sha_keys = [k for k in keys if len(k) == 64 and all(c in "0123456789abcdef" for c in k)]
    assert len(sha_keys) == 1, f"Expected exactly one sha256-hex dedupe key, got: {keys}"


def test_webhook_without_default_agent_fails_closed_before_queueing(db_session, monkeypatch):
    _seed_base(db_session, default_agent=False)

    async def should_not_dispatch(**kwargs):
        raise AssertionError("dispatch service must not run without an agent")

    monkeypatch.setattr(inbound, "_maybe_dispatch_trigger_event", should_not_dispatch)

    with pytest.raises(HTTPException) as exc_info:
        _receive(
            db_session,
            {
                "message": "Build report",
                "sender_id": "customer-1",
                "source_id": "evt-no-agent",
            },
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "No agent configured for this webhook"
    assert db_session.query(MessageQueue).count() == 0
