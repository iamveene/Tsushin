from __future__ import annotations

import asyncio
import base64
import os
import sys
import types
from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

from channels.email.trigger import EMAIL_EVENT_TYPE, EmailTrigger  # noqa: E402
from models import (  # noqa: E402
    Agent,
    Base,
    BudgetPolicy,
    Contact,
    ContinuousAgent,
    ContinuousRun,
    ContinuousSubscription,
    DeliveryPolicy,
    EmailChannelInstance,
    GmailIntegration,
    HubIntegration,
    SentinelProfile,
)
from models_rbac import Tenant, User  # noqa: E402
from services.trigger_dispatch_service import TriggerDispatchResult  # noqa: E402


class FakeGmail:
    def __init__(self, messages):
        self.messages = {message["id"]: message for message in messages}
        self.refs = [{"id": message["id"]} for message in messages]
        self.search_queries: list[str] = []
        self.list_calls = 0

    async def list_messages(self, max_results: int = 20, **kwargs):
        self.list_calls += 1
        return self.refs[:max_results]

    async def search_messages(self, query: str, max_results: int = 20, **kwargs):
        self.search_queries.append(query)
        return self.refs[:max_results]

    async def get_message(self, message_id: str, format: str = "full"):
        return self.messages[message_id]


class RecordingDispatcher:
    def __init__(self, sink):
        self.sink = sink

    def dispatch(self, event):
        self.sink.append(event)
        return TriggerDispatchResult(
            status="dispatched",
            tenant_id="tenant-a",
            matched_agent_id=201,
            continuous_run_ids=[],
            continuous_subscription_ids=[],
        )


def _message(message_id: str, internal_ms: int, *, subject: str, sender: str) -> dict:
    body = base64.urlsafe_b64encode(f"Body for {subject}".encode("utf-8")).decode("utf-8")
    return {
        "id": message_id,
        "threadId": f"thread-{message_id}",
        "historyId": str(internal_ms),
        "internalDate": str(internal_ms),
        "labelIds": ["INBOX", "UNREAD"],
        "snippet": f"Snippet for {subject}",
        "payload": {
            "headers": [
                {"name": "Subject", "value": subject},
                {"name": "From", "value": sender},
                {"name": "To", "value": "agent@example.com"},
                {"name": "Date", "value": "Fri, 24 Apr 2026 10:00:00 +0000"},
            ],
            "mimeType": "text/plain",
            "body": {"data": body},
        },
    }


def _seed(db):
    db.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    db.add(User(id=1, tenant_id="tenant-a", email="owner@example.com", password_hash="x", is_active=True))
    db.add(Contact(id=101, tenant_id="tenant-a", friendly_name="Alpha", role="agent"))
    db.add(
        Agent(
            id=201,
            tenant_id="tenant-a",
            contact_id=101,
            system_prompt="prompt",
            model_provider="gemini",
            model_name="gemini-2.5-pro",
            response_template="{response}",
            is_active=True,
        )
    )
    gmail = GmailIntegration(
        id=301,
        tenant_id="tenant-a",
        type="gmail",
        name="Gmail",
        display_name="Support Gmail",
        is_active=True,
        health_status="healthy",
        email_address="support@example.com",
        authorized_at=datetime.utcnow(),
    )
    db.add(gmail)
    trigger = EmailChannelInstance(
        id=401,
        tenant_id="tenant-a",
        integration_name="Inbox Watcher",
        provider="gmail",
        gmail_integration_id=301,
        default_agent_id=201,
        created_by=1,
        is_active=True,
        status="active",
    )
    db.add(trigger)
    db.commit()
    return trigger


def _db():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            Contact.__table__,
            Agent.__table__,
            DeliveryPolicy.__table__,
            BudgetPolicy.__table__,
            SentinelProfile.__table__,
            ContinuousAgent.__table__,
            ContinuousSubscription.__table__,
            ContinuousRun.__table__,
            HubIntegration.__table__,
            GmailIntegration.__table__,
            EmailChannelInstance.__table__,
        ],
    )
    return sessionmaker(bind=engine)()


def test_email_trigger_polls_new_messages_oldest_first_and_updates_cursor():
    db = _db()
    try:
        _seed(db)
        fake_gmail = FakeGmail(
            [
                _message("msg-new", 2000, subject="Newer", sender="New <new@example.com>"),
                _message("msg-old", 1000, subject="Older", sender="Old <old@example.com>"),
            ]
        )
        events = []

        result = asyncio.run(
            EmailTrigger.poll_active(
                db,
                gmail_service_factory=lambda _db, _integration_id: fake_gmail,
                dispatcher_factory=lambda _db: RecordingDispatcher(events),
            )
        )[0]

        trigger = db.query(EmailChannelInstance).filter(EmailChannelInstance.id == 401).one()
        assert result.status == "ok"
        assert result.fetched_count == 2
        assert result.dispatched_count == 2
        assert [event.source_id for event in events] == ["msg-old", "msg-new"]
        assert [event.event_type for event in events] == [EMAIL_EVENT_TYPE, EMAIL_EVENT_TYPE]
        assert trigger.last_cursor.endswith(":msg-new")
        assert trigger.health_status == "healthy"
    finally:
        db.close()


def test_email_trigger_cursor_prevents_second_poll_fanout():
    db = _db()
    try:
        _seed(db)
        fake_gmail = FakeGmail(
            [_message("msg-new", 2000, subject="Newer", sender="New <new@example.com>")]
        )
        events = []

        first = asyncio.run(
            EmailTrigger.poll_active(
                db,
                gmail_service_factory=lambda _db, _integration_id: fake_gmail,
                dispatcher_factory=lambda _db: RecordingDispatcher(events),
            )
        )[0]
        second = asyncio.run(
            EmailTrigger.poll_active(
                db,
                gmail_service_factory=lambda _db, _integration_id: fake_gmail,
                dispatcher_factory=lambda _db: RecordingDispatcher(events),
                force=True,
            )
        )[0]

        assert first.dispatched_count == 1
        assert second.dispatched_count == 0
        assert second.skipped_count == 1
        assert len(events) == 1
    finally:
        db.close()


def test_email_trigger_respects_poll_interval_between_runs():
    db = _db()
    try:
        _seed(db)
        fake_gmail = FakeGmail(
            [_message("msg-new", 2000, subject="Newer", sender="New <new@example.com>")]
        )
        events = []

        first = asyncio.run(
            EmailTrigger.poll_active(
                db,
                gmail_service_factory=lambda _db, _integration_id: fake_gmail,
                dispatcher_factory=lambda _db: RecordingDispatcher(events),
            )
        )[0]
        second = asyncio.run(
            EmailTrigger.poll_active(
                db,
                gmail_service_factory=lambda _db, _integration_id: fake_gmail,
                dispatcher_factory=lambda _db: RecordingDispatcher(events),
            )
        )[0]

        assert first.status == "ok"
        assert second.status == "skipped"
        assert second.reason == "poll_interval_not_elapsed"
        assert fake_gmail.list_calls == 1
        assert len(events) == 1
    finally:
        db.close()


def test_email_trigger_uses_search_query_when_configured():
    db = _db()
    try:
        trigger = _seed(db)
        trigger.search_query = "label:unread newer_than:1d"
        db.commit()
        fake_gmail = FakeGmail(
            [_message("msg-new", 2000, subject="Newer", sender="New <new@example.com>")]
        )

        asyncio.run(
            EmailTrigger.poll_active(
                db,
                gmail_service_factory=lambda _db, _integration_id: fake_gmail,
                dispatcher_factory=lambda _db: RecordingDispatcher([]),
            )
        )

        assert fake_gmail.search_queries == ["label:unread newer_than:1d"]
        assert fake_gmail.list_calls == 0
    finally:
        db.close()


def test_email_trigger_rejects_cross_tenant_gmail_integration():
    db = _db()
    try:
        trigger = _seed(db)
        db.add(Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"))
        db.add(
            GmailIntegration(
                id=302,
                tenant_id="tenant-b",
                type="gmail",
                name="Foreign Gmail",
                display_name="Foreign Gmail",
                is_active=True,
                health_status="healthy",
                email_address="foreign@example.com",
                authorized_at=datetime.utcnow(),
            )
        )
        trigger.gmail_integration_id = 302
        db.commit()
        events = []
        fake_gmail = FakeGmail(
            [_message("msg-new", 2000, subject="Newer", sender="New <new@example.com>")]
        )

        result = asyncio.run(
            EmailTrigger.poll_active(
                db,
                gmail_service_factory=lambda _db, _integration_id: fake_gmail,
                dispatcher_factory=lambda _db: RecordingDispatcher(events),
            )
        )[0]

        stored = db.query(EmailChannelInstance).filter(EmailChannelInstance.id == 401).one()
        assert result.status == "error"
        assert result.reason == "gmail_integration_tenant_mismatch"
        assert stored.health_status == "unhealthy"
        assert stored.health_status_reason == "gmail_integration_tenant_mismatch"
        assert events == []
        assert fake_gmail.list_calls == 0
    finally:
        db.close()


def test_email_trigger_rejects_disconnected_gmail_integration():
    db = _db()
    try:
        _seed(db)
        integration = db.query(GmailIntegration).filter(GmailIntegration.id == 301).one()
        integration.health_status = "disconnected"
        db.commit()
        events = []

        result = asyncio.run(
            EmailTrigger.poll_active(
                db,
                gmail_service_factory=lambda _db, _integration_id: FakeGmail([]),
                dispatcher_factory=lambda _db: RecordingDispatcher(events),
            )
        )[0]

        assert result.status == "error"
        assert result.reason == "gmail_integration_inactive"
        assert events == []
    finally:
        db.close()


def test_email_trigger_processes_system_owned_triage_subscription(monkeypatch):
    db = _db()
    try:
        _seed(db)
        db.add(
            ContinuousAgent(
                id=501,
                tenant_id="tenant-a",
                agent_id=201,
                name="Email Triage: Inbox Watcher",
                execution_mode="hybrid",
                status="active",
                is_system_owned=True,
            )
        )
        db.add(
            ContinuousSubscription(
                id=601,
                tenant_id="tenant-a",
                continuous_agent_id=501,
                channel_type="email",
                channel_instance_id=401,
                event_type=EMAIL_EVENT_TYPE,
                status="active",
                is_system_owned=True,
            )
        )
        db.add(
            ContinuousRun(
                id=701,
                tenant_id="tenant-a",
                continuous_agent_id=501,
                wake_event_ids=[1],
                execution_mode="hybrid",
                status="queued",
            )
        )
        db.commit()
        fake_gmail = FakeGmail(
            [_message("msg-new", 2000, subject="Newer", sender="New <new@example.com>")]
        )
        draft_calls = []

        class TriageDispatcher:
            def dispatch(self, event):
                return TriggerDispatchResult(
                    status="dispatched",
                    tenant_id="tenant-a",
                    matched_agent_id=201,
                    continuous_run_ids=[701],
                    continuous_subscription_ids=[601],
                )

        async def fake_create_triage_draft(_db, **kwargs):
            draft_calls.append(kwargs)
            return {
                "success": True,
                "output": "Draft created",
                "metadata": {"draft_id": "draft-1"},
            }

        monkeypatch.setattr("channels.email.trigger.create_triage_draft", fake_create_triage_draft)

        result = asyncio.run(
            EmailTrigger.poll_active(
                db,
                gmail_service_factory=lambda _db, _integration_id: fake_gmail,
                dispatcher_factory=lambda _db: TriageDispatcher(),
            )
        )[0]

        run = db.query(ContinuousRun).filter(ContinuousRun.id == 701).one()
        assert result.status == "ok"
        assert result.dispatched_count == 1
        assert len(draft_calls) == 1
        assert draft_calls[0]["trigger"].id == 401
        assert draft_calls[0]["continuous_agent"].id == 501
        assert draft_calls[0]["email_payload"]["message"]["id"] == "msg-new"
        assert run.status == "succeeded"
        assert run.outcome_state["triage_draft"]["metadata"]["draft_id"] == "draft-1"
    finally:
        db.close()
