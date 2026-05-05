from __future__ import annotations

import os
import sys
import types
import asyncio
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)

argon2_stub = types.ModuleType("argon2")


class _PasswordHasher:
    def hash(self, value):
        return value

    def verify(self, hashed, plain):
        return hashed == plain


argon2_stub.PasswordHasher = _PasswordHasher
argon2_exceptions_stub = types.ModuleType("argon2.exceptions")
argon2_exceptions_stub.VerifyMismatchError = ValueError
argon2_exceptions_stub.InvalidHashError = ValueError
sys.modules.setdefault("argon2", argon2_stub)
sys.modules.setdefault("argon2.exceptions", argon2_exceptions_stub)

from api import routes_email_triggers as email_routes  # noqa: E402
from api.routes_email_triggers import (  # noqa: E402
    EmailTriggerCreate,
    EmailTriggerUpdate,
    create_email_trigger,
    create_email_triage_subscription,
    delete_email_trigger,
    list_email_triggers,
    run_saved_email_test_query,
    update_email_trigger,
)
from api.routes_triggers import list_triggers  # noqa: E402
from models import (  # noqa: E402
    Agent,
    Contact,
    ContinuousAgent,
    ContinuousSubscription,
    BudgetPolicy,
    ChannelEventDedupe,
    Config,
    DeliveryPolicy,
    EmailChannelInstance,
    FlowDefinition,
    FlowNode,
    FlowNodeRun,
    FlowRun,
    FlowTriggerBinding,
    GmailIntegration,
    GitHubChannelInstance,
    HubIntegration,
    JiraChannelInstance,
    JiraIntegration,
    OAuthToken,
    SentinelProfile,
    WakeEvent,
    WebhookIntegration,
    WhatsAppMCPInstance,
    Base,
)
from models_rbac import Tenant, User  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            Contact.__table__,
            Agent.__table__,
            Config.__table__,
            WhatsAppMCPInstance.__table__,
            DeliveryPolicy.__table__,
            BudgetPolicy.__table__,
            SentinelProfile.__table__,
            ContinuousAgent.__table__,
            ContinuousSubscription.__table__,
            WakeEvent.__table__,
            ChannelEventDedupe.__table__,
            HubIntegration.__table__,
            OAuthToken.__table__,
            GmailIntegration.__table__,
            JiraIntegration.__table__,
            FlowDefinition.__table__,
            FlowNode.__table__,
            FlowRun.__table__,
            FlowNodeRun.__table__,
            FlowTriggerBinding.__table__,
            EmailChannelInstance.__table__,
            WebhookIntegration.__table__,
            JiraChannelInstance.__table__,
            GitHubChannelInstance.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ctx(tenant_id: str):
    return SimpleNamespace(tenant_id=tenant_id)


def _seed_user(db, *, user_id: int, tenant_id: str, email: str):
    user = User(
        id=user_id,
        tenant_id=tenant_id,
        email=email,
        password_hash="hashed",
        is_active=True,
    )
    db.add(user)
    return user


def _seed_contact(db, *, contact_id: int, tenant_id: str, friendly_name: str):
    contact = Contact(id=contact_id, tenant_id=tenant_id, friendly_name=friendly_name, role="agent")
    db.add(contact)
    return contact


def _seed_agent(db, *, agent_id: int, tenant_id: str, contact_id: int):
    agent = Agent(
        id=agent_id,
        tenant_id=tenant_id,
        contact_id=contact_id,
        system_prompt=f"prompt-{agent_id}",
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        response_template="{response}",
        is_active=True,
    )
    db.add(agent)
    return agent


def _seed_whatsapp_instance(db, *, instance_id: int, tenant_id: str, user_id: int):
    instance = WhatsAppMCPInstance(
        id=instance_id,
        tenant_id=tenant_id,
        container_name=f"mcp-{tenant_id}-{instance_id}",
        phone_number="+5527999616279",
        display_name="Agent WhatsApp",
        instance_type="agent",
        mcp_api_url="http://127.0.0.1:8088/api",
        mcp_port=8088,
        messages_db_path="/tmp/messages.db",
        session_data_path="/tmp/session",
        status="running",
        health_status="healthy",
        created_by=user_id,
        api_secret="secret",
    )
    db.add(instance)
    return instance


def _seed_gmail_integration(
    db,
    *,
    tenant_id: str,
    email_address: str,
    health_status: str = "healthy",
    is_active: bool = True,
    scopes: str = (
        "https://www.googleapis.com/auth/gmail.readonly "
        "https://www.googleapis.com/auth/gmail.send "
        "https://www.googleapis.com/auth/gmail.compose"
    ),
):
    integration = GmailIntegration(
        tenant_id=tenant_id,
        type="gmail",
        name=f"Gmail - {email_address}",
        display_name=f"{tenant_id.title()} Gmail",
        is_active=is_active,
        health_status=health_status,
        email_address=email_address,
        authorized_at=datetime.utcnow(),
    )
    db.add(integration)
    db.flush()
    db.add(
        OAuthToken(
            integration_id=integration.id,
            access_token_encrypted="encrypted-access",
            refresh_token_encrypted="encrypted-refresh",
            expires_at=datetime.utcnow() + timedelta(hours=1),
            scope=scopes,
        )
    )
    db.flush()
    return integration


def test_create_email_trigger_persists_and_lists(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    gmail = _seed_gmail_integration(db_session, tenant_id="tenant-a", email_address="support@example.com")
    db_session.commit()

    created = create_email_trigger(
        payload=EmailTriggerCreate(
            integration_name="Inbox Watcher",
            gmail_integration_id=gmail.id,
            default_agent_id=201,
            search_query="label:inbox newer_than:1d",
            trigger_criteria={
                "criteria_version": 1,
                "filters": {"email": {"search_query": "label:inbox newer_than:1d"}},
                "window": {"mode": "since_cursor"},
                "ordering": "oldest_first",
            },
        ),
        ctx=_ctx("tenant-a"),
        current_user=SimpleNamespace(id=1),
        db=db_session,
    )

    listed = list_email_triggers(ctx=_ctx("tenant-a"), _user=SimpleNamespace(id=1), db=db_session)

    assert created.integration_name == "Inbox Watcher"
    assert created.gmail_account_email == "support@example.com"
    assert created.default_agent_name == "Alpha"
    assert created.trigger_criteria["filters"]["email"]["search_query"] == "label:inbox newer_than:1d"
    assert created.status == "active"
    assert [row.integration_name for row in listed] == ["Inbox Watcher"]


def test_create_email_trigger_rejects_foreign_gmail_integration(db_session):
    db_session.add_all(
        [
            Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"),
            Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"),
        ]
    )
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    gmail = _seed_gmail_integration(db_session, tenant_id="tenant-b", email_address="support@example.com")
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_email_trigger(
            payload=EmailTriggerCreate(
                integration_name="Inbox Watcher",
                gmail_integration_id=gmail.id,
                default_agent_id=201,
            ),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Gmail integration not found"


def test_update_email_trigger_can_pause_existing_row(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    gmail = _seed_gmail_integration(db_session, tenant_id="tenant-a", email_address="support@example.com")
    trigger = EmailChannelInstance(
        tenant_id="tenant-a",
        integration_name="Inbox Watcher",
        provider="gmail",
        gmail_integration_id=gmail.id,
        default_agent_id=201,
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    updated = update_email_trigger(
        trigger_id=trigger.id,
        payload=EmailTriggerUpdate(
            is_active=False,
            search_query="label:unread",
            trigger_criteria={
                "criteria_version": 1,
                "filters": {"email": {"search_query": "label:unread"}},
                "window": {"mode": "since_cursor"},
                "ordering": "oldest_first",
            },
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    stored = db_session.query(EmailChannelInstance).filter(EmailChannelInstance.id == trigger.id).first()
    assert updated.is_active is False
    assert updated.status == "paused"
    assert stored.search_query == "label:unread"
    assert stored.trigger_criteria["filters"]["email"]["search_query"] == "label:unread"


def test_email_trigger_rejects_invalid_trigger_criteria():
    with pytest.raises(ValidationError):
        EmailTriggerCreate(
            integration_name="Inbox Watcher",
            gmail_integration_id=1,
            trigger_criteria={"criteria_version": 1, "filters": {}},
        )


def test_update_email_trigger_syncs_managed_flow_default_agent(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    _seed_contact(db_session, contact_id=102, tenant_id="tenant-a", friendly_name="Beta")
    _seed_agent(db_session, agent_id=202, tenant_id="tenant-a", contact_id=102)
    gmail = _seed_gmail_integration(db_session, tenant_id="tenant-a", email_address="support@example.com")
    trigger = EmailChannelInstance(
        tenant_id="tenant-a",
        integration_name="Inbox Watcher",
        provider="gmail",
        gmail_integration_id=gmail.id,
        default_agent_id=201,
        created_by=1,
    )
    flow = FlowDefinition(
        id=801,
        tenant_id="tenant-a",
        name="Email: Inbox Watcher",
        execution_method="triggered",
        default_agent_id=201,
        is_system_owned=True,
    )
    conversation = FlowNode(
        id=802,
        flow_definition_id=801,
        type="conversation",
        position=3,
        name="Default agent",
        agent_id=201,
        config_json="{}",
    )
    binding = FlowTriggerBinding(
        id=803,
        tenant_id="tenant-a",
        flow_definition_id=801,
        trigger_kind="email",
        trigger_instance_id=1,
        is_system_managed=True,
        is_active=True,
        suppress_default_agent=False,
    )
    db_session.add_all([trigger, flow, conversation, binding])
    db_session.flush()
    binding.trigger_instance_id = trigger.id
    db_session.commit()

    updated = update_email_trigger(
        trigger_id=trigger.id,
        payload=EmailTriggerUpdate(default_agent_id=202),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    db_session.refresh(flow)
    db_session.refresh(conversation)
    assert updated.default_agent_id == 202
    assert flow.default_agent_id == 202
    assert conversation.agent_id == 202


def test_delete_email_trigger_is_tenant_scoped(db_session):
    db_session.add_all(
        [
            Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"),
            Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"),
        ]
    )
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    gmail_a = _seed_gmail_integration(db_session, tenant_id="tenant-a", email_address="a@example.com")
    gmail_b = _seed_gmail_integration(db_session, tenant_id="tenant-b", email_address="b@example.com")
    trigger_a = EmailChannelInstance(
        tenant_id="tenant-a",
        integration_name="Tenant A Trigger",
        provider="gmail",
        gmail_integration_id=gmail_a.id,
        created_by=1,
    )
    trigger_b = EmailChannelInstance(
        tenant_id="tenant-b",
        integration_name="Tenant B Trigger",
        provider="gmail",
        gmail_integration_id=gmail_b.id,
        created_by=1,
    )
    db_session.add_all([trigger_a, trigger_b])
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_email_trigger(
            trigger_id=trigger_b.id,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 404

    delete_email_trigger(
        trigger_id=trigger_a.id,
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    remaining = db_session.query(EmailChannelInstance.integration_name).order_by(
        EmailChannelInstance.integration_name.asc()
    ).all()
    assert [row.integration_name for row in remaining] == ["Tenant B Trigger"]


def test_trigger_catalog_marks_email_as_configured(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    gmail = _seed_gmail_integration(db_session, tenant_id="tenant-a", email_address="support@example.com")
    db_session.add(
        EmailChannelInstance(
            tenant_id="tenant-a",
            integration_name="Inbox Watcher",
            provider="gmail",
            gmail_integration_id=gmail.id,
            default_agent_id=201,
            created_by=1,
        )
    )
    db_session.commit()

    triggers = list_triggers(ctx=_ctx("tenant-a"), db=db_session)
    trigger_map = {entry.id: entry.tenant_has_configured for entry in triggers}

    assert trigger_map["email"] is True
    assert "webhook" in trigger_map


def test_create_email_triage_subscription_is_idempotent(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    gmail = _seed_gmail_integration(db_session, tenant_id="tenant-a", email_address="support@example.com")
    trigger = EmailChannelInstance(
        tenant_id="tenant-a",
        integration_name="Inbox Watcher",
        provider="gmail",
        gmail_integration_id=gmail.id,
        default_agent_id=201,
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    first = create_email_triage_subscription(
        trigger_id=trigger.id,
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )
    second = create_email_triage_subscription(
        trigger_id=trigger.id,
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert first.created_agent is True
    assert first.created_subscription is True
    assert second.created_agent is False
    assert second.created_subscription is False
    assert second.continuous_agent_id == first.continuous_agent_id
    assert second.continuous_subscription_id == first.continuous_subscription_id
    assert db_session.query(ContinuousAgent).count() == 1
    assert db_session.query(ContinuousSubscription).count() == 1


def test_create_email_triage_subscription_requires_default_agent(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    gmail = _seed_gmail_integration(db_session, tenant_id="tenant-a", email_address="support@example.com")
    trigger = EmailChannelInstance(
        tenant_id="tenant-a",
        integration_name="Inbox Watcher",
        provider="gmail",
        gmail_integration_id=gmail.id,
        default_agent_id=None,
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_email_triage_subscription(
            trigger_id=trigger.id,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 400
    assert "default agent" in exc_info.value.detail


def test_create_email_triage_subscription_rejects_cross_tenant_gmail_integration(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    db_session.add(Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    foreign_gmail = _seed_gmail_integration(
        db_session,
        tenant_id="tenant-b",
        email_address="foreign@example.com",
    )
    trigger = EmailChannelInstance(
        tenant_id="tenant-a",
        integration_name="Inbox Watcher",
        provider="gmail",
        gmail_integration_id=foreign_gmail.id,
        default_agent_id=201,
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_email_triage_subscription(
            trigger_id=trigger.id,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 400
    assert "tenant-owned Gmail integration" in exc_info.value.detail
    assert db_session.query(ContinuousAgent).count() == 0
    assert db_session.query(ContinuousSubscription).count() == 0


def test_create_email_triage_subscription_rejects_disconnected_gmail_integration(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    gmail = _seed_gmail_integration(
        db_session,
        tenant_id="tenant-a",
        email_address="support@example.com",
        health_status="disconnected",
    )
    trigger = EmailChannelInstance(
        tenant_id="tenant-a",
        integration_name="Inbox Watcher",
        provider="gmail",
        gmail_integration_id=gmail.id,
        default_agent_id=201,
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_email_triage_subscription(
            trigger_id=trigger.id,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 400
    assert "tenant-owned Gmail integration" in exc_info.value.detail
    assert db_session.query(ContinuousAgent).count() == 0
    assert db_session.query(ContinuousSubscription).count() == 0


def test_create_email_triage_subscription_rejects_send_only_gmail_integration(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    gmail = _seed_gmail_integration(
        db_session,
        tenant_id="tenant-a",
        email_address="support@example.com",
        scopes=(
            "https://www.googleapis.com/auth/gmail.readonly "
            "https://www.googleapis.com/auth/gmail.send"
        ),
    )
    trigger = EmailChannelInstance(
        tenant_id="tenant-a",
        integration_name="Inbox Watcher",
        provider="gmail",
        gmail_integration_id=gmail.id,
        default_agent_id=201,
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_email_triage_subscription(
            trigger_id=trigger.id,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 400
    assert "gmail.compose" in exc_info.value.detail
    assert db_session.query(ContinuousAgent).count() == 0
    assert db_session.query(ContinuousSubscription).count() == 0


def test_email_trigger_read_does_not_expose_foreign_gmail_details(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    db_session.add(Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    foreign_gmail = _seed_gmail_integration(
        db_session,
        tenant_id="tenant-b",
        email_address="foreign@example.com",
    )
    trigger = EmailChannelInstance(
        tenant_id="tenant-a",
        integration_name="Inbox Watcher",
        provider="gmail",
        gmail_integration_id=foreign_gmail.id,
        search_query="XYZ",
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    rows = list_email_triggers(
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert len(rows) == 1
    assert rows[0].gmail_account_email is None
    assert rows[0].gmail_integration_name is None


def test_saved_email_test_query_returns_message_samples(db_session, monkeypatch):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    gmail = _seed_gmail_integration(db_session, tenant_id="tenant-a", email_address="support@example.com")
    trigger = EmailChannelInstance(
        tenant_id="tenant-a",
        integration_name="Inbox Watcher",
        provider="gmail",
        gmail_integration_id=gmail.id,
        search_query="XYZ",
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    class FakeGmailService:
        def __init__(self, db, integration_id):
            self.integration_id = integration_id

        async def search_messages(self, query, max_results=20, **kwargs):
            assert query == "XYZ"
            return [{"id": "msg-xyz"}]

        async def list_messages(self, max_results=20, **kwargs):
            return []

        async def get_message(self, message_id, format="full"):
            return {
                "id": message_id,
                "threadId": "thread-xyz",
                "internalDate": "2000",
                "snippet": "Snippet XYZ",
                "payload": {
                    "headers": [
                        {"name": "Subject", "value": "Keyword XYZ"},
                        {"name": "From", "value": "Sender <sender@example.com>"},
                        {"name": "To", "value": "support@example.com"},
                    ],
                    "mimeType": "text/plain",
                    "body": {"data": "Qm9keSBYWVo="},
                },
            }

    monkeypatch.setattr(email_routes, "GmailService", FakeGmailService)

    response = asyncio.run(
        run_saved_email_test_query(
            trigger_id=trigger.id,
            payload=email_routes.EmailTestQueryRequest(max_results=3),
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    )

    assert response.success is True
    assert response.message_count == 1
    assert response.sample_messages[0].subject == "Keyword XYZ"
    assert response.sample_messages[0].description_preview == "Body XYZ"
