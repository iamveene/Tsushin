"""
BUG-705 regression: webhook signature replay must be blocked.

The previous implementation derived the dedupe key from wall-clock millis,
so replaying the same signed envelope within the 300s skew window was
accepted twice. This test asserts the second replay is rejected with 409.
"""

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

# docker stub mirrors test_webhook_trigger_dispatch_foundation.py — receive_webhook
# pulls in models that trigger docker imports lazily on some paths.
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
    """Minimal Request stub that returns a fixed body."""

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


def _seed_base(db):
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
        default_agent_id=agent.id,
        is_active=True,
        status="active",
    )
    db.add(integration)
    db.commit()
    return agent, integration


def _sign(body: bytes, timestamp: str, secret: bytes = b"secret") -> str:
    signed_input = f"{timestamp}.".encode("utf-8") + body
    return "sha256=" + hmac.new(secret, signed_input, hashlib.sha256).hexdigest()


def _post(db, body: bytes, signature: str, timestamp: str, slug: str = "wh-tenant-a"):
    return asyncio.run(
        inbound.receive_webhook(
            slug=slug,
            request=_RequestStub(body),
            x_tsushin_signature=signature,
            x_tsushin_timestamp=timestamp,
            db=db,
        )
    )


def test_replay_of_identical_signed_envelope_is_rejected_with_409(db_session, monkeypatch):
    """
    BUG-705: posting the exact same (body, signature, timestamp) twice must
    return 409 on the second attempt and create only one MessageQueue row.
    """
    _seed_base(db_session)

    # Force the trigger-dispatch bridge off so the test exercises the
    # direct-queue path and we can count MessageQueue rows deterministically.
    async def no_dispatch(**kwargs):
        return None

    monkeypatch.setattr(inbound, "_maybe_dispatch_trigger_event", no_dispatch)

    body = json.dumps(
        {"message": "fire missiles", "sender_id": "attacker", "source_id": "explicit-id"},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    timestamp = str(int(time.time()))
    signature = _sign(body, timestamp)

    # First call: should succeed.
    first = _post(db_session, body, signature, timestamp)
    assert first["status"] == "queued"
    first_queue_id = first["queue_id"]

    # Second call with the EXACT same envelope: must be 409.
    with pytest.raises(HTTPException) as exc_info:
        _post(db_session, body, signature, timestamp)

    assert exc_info.value.status_code == 409
    assert "duplicate" in str(exc_info.value.detail).lower()

    # Only one MessageQueue row was written.
    assert db_session.query(MessageQueue).count() == 1
    # And the replay row in channel_event_dedupe is keyed on the sha256 of the
    # signed envelope, NOT the wall-clock-millis source_id.
    dedupe_rows = db_session.query(ChannelEventDedupe).all()
    assert len(dedupe_rows) == 1
    row = dedupe_rows[0]
    assert row.tenant_id == "tenant-a"
    assert row.channel_type == "webhook"
    assert row.instance_id == 301
    # Dedupe key must be a 64-char hex digest (sha256), not the legacy
    # `whk_<id>_<millis>` shape.
    assert len(row.dedupe_key) == 64
    assert all(c in "0123456789abcdef" for c in row.dedupe_key)


def test_distinct_signatures_are_not_blocked_by_replay_dedupe(db_session, monkeypatch):
    """
    BUG-705 negative case: two requests with different timestamps (and so
    different signatures) must NOT be blocked by replay protection. Each
    signed envelope is a fresh event from the caller's standpoint.
    """
    _seed_base(db_session)

    async def no_dispatch(**kwargs):
        return None

    monkeypatch.setattr(inbound, "_maybe_dispatch_trigger_event", no_dispatch)

    body1 = json.dumps({"message": "first"}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    body2 = json.dumps({"message": "second"}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ts = str(int(time.time()))

    r1 = _post(db_session, body1, _sign(body1, ts), ts)
    r2 = _post(db_session, body2, _sign(body2, ts), ts)

    assert r1["status"] == "queued"
    assert r2["status"] == "queued"
    # Two distinct MessageQueue rows + two distinct dedupe rows.
    assert db_session.query(MessageQueue).count() == 2
    assert db_session.query(ChannelEventDedupe).count() == 2
