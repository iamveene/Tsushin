from __future__ import annotations

import os
import sys
import types
from datetime import datetime
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

from api.routes_default_agents import (  # noqa: E402
    InstanceDefaultUpdate,
    UserChannelDefaultUpsert,
    get_default_agents_settings,
    update_instance_default_agent,
    update_tenant_default_agent,
    upsert_user_channel_default_agent,
)
from models import (  # noqa: E402
    Agent,
    Contact,
    DiscordIntegration,
    EmailChannelInstance,
    GitHubChannelInstance,
    GmailIntegration,
    HubIntegration,
    JiraChannelInstance,
    ScheduleChannelInstance,
    SlackIntegration,
    TelegramBotInstance,
    UserChannelDefaultAgent,
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
            UserChannelDefaultAgent.__table__,
            WhatsAppMCPInstance.__table__,
            TelegramBotInstance.__table__,
            SlackIntegration.__table__,
            DiscordIntegration.__table__,
            WebhookIntegration.__table__,
            HubIntegration.__table__,
            GmailIntegration.__table__,
            EmailChannelInstance.__table__,
            JiraChannelInstance.__table__,
            ScheduleChannelInstance.__table__,
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


def _seed_agent(db, *, agent_id: int, tenant_id: str, contact_id: int, is_default: bool = False):
    agent = Agent(
        id=agent_id,
        tenant_id=tenant_id,
        contact_id=contact_id,
        system_prompt=f"prompt-{agent_id}",
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        response_template="{response}",
        is_active=True,
        is_default=is_default,
    )
    db.add(agent)
    return agent


def _seed_whatsapp_instance(db, *, instance_id: int, tenant_id: str, created_by: int, default_agent_id: int | None):
    instance = WhatsAppMCPInstance(
        id=instance_id,
        tenant_id=tenant_id,
        container_name=f"mcp-{tenant_id}-{instance_id}",
        phone_number=f"+550000000{instance_id:03d}",
        display_name=f"WhatsApp {tenant_id}",
        instance_type="agent",
        mcp_api_url="http://localhost:8080/api",
        mcp_port=8080 + instance_id,
        messages_db_path=f"/tmp/messages-{instance_id}.db",
        session_data_path=f"/tmp/session-{instance_id}",
        created_by=created_by,
        default_agent_id=default_agent_id,
    )
    db.add(instance)
    return instance


def _seed_webhook(db, *, instance_id: int, tenant_id: str, created_by: int, default_agent_id: int | None):
    integration = WebhookIntegration(
        id=instance_id,
        tenant_id=tenant_id,
        integration_name=f"Webhook {tenant_id}",
        slug=f"wh-{tenant_id}-{instance_id}",
        api_secret_encrypted="secret",
        api_secret_preview="whsec_xxx",
        created_by=created_by,
        default_agent_id=default_agent_id,
    )
    db.add(integration)
    return integration


def _seed_gmail_and_email_trigger(db, *, tenant_id: str, created_by: int, trigger_id: int, default_agent_id: int | None):
    gmail = GmailIntegration(
        tenant_id=tenant_id,
        type="gmail",
        name=f"Gmail - {tenant_id}@example.com",
        display_name=f"{tenant_id.title()} Gmail",
        is_active=True,
        health_status="healthy",
        email_address=f"{tenant_id}@example.com",
        authorized_at=datetime.utcnow(),
    )
    db.add(gmail)
    db.flush()
    trigger = EmailChannelInstance(
        id=trigger_id,
        tenant_id=tenant_id,
        integration_name=f"Email Trigger {tenant_id}",
        provider="gmail",
        gmail_integration_id=gmail.id,
        default_agent_id=default_agent_id,
        created_by=created_by,
    )
    db.add(trigger)
    return gmail, trigger


def test_get_default_agents_settings_returns_only_tenant_rows(db_session):
    db_session.add_all(
        [
            Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"),
            Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"),
        ]
    )
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner-a@example.com")
    _seed_user(db_session, user_id=2, tenant_id="tenant-b", email="owner-b@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_contact(db_session, contact_id=102, tenant_id="tenant-b", friendly_name="Beta")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101, is_default=True)
    _seed_agent(db_session, agent_id=202, tenant_id="tenant-b", contact_id=102, is_default=True)
    _seed_whatsapp_instance(db_session, instance_id=301, tenant_id="tenant-a", created_by=1, default_agent_id=201)
    _seed_whatsapp_instance(db_session, instance_id=302, tenant_id="tenant-b", created_by=2, default_agent_id=202)
    _seed_webhook(db_session, instance_id=401, tenant_id="tenant-a", created_by=1, default_agent_id=201)
    _seed_webhook(db_session, instance_id=402, tenant_id="tenant-b", created_by=2, default_agent_id=202)
    _seed_gmail_and_email_trigger(db_session, tenant_id="tenant-a", created_by=1, trigger_id=501, default_agent_id=201)
    _seed_gmail_and_email_trigger(db_session, tenant_id="tenant-b", created_by=2, trigger_id=502, default_agent_id=202)
    db_session.add(
        UserChannelDefaultAgent(
            tenant_id="tenant-a",
            channel_type="whatsapp",
            user_identifier="+5511999999999",
            agent_id=201,
        )
    )
    db_session.commit()

    response = get_default_agents_settings(ctx=_ctx("tenant-a"), _user=SimpleNamespace(id=1), db=db_session)

    assert response.tenant_default_agent_id == 201
    assert response.tenant_default_agent_name == "Alpha"
    assert [agent.id for agent in response.available_agents] == [201]
    assert {(item.channel_type, item.instance_id) for item in response.channel_defaults} == {("whatsapp", 301)}
    assert {(item.channel_type, item.instance_id) for item in response.trigger_defaults} == {
        ("webhook", 401),
        ("email", 501),
    }
    assert [(row.channel_type, row.user_identifier, row.agent_id) for row in response.user_defaults] == [
        ("whatsapp", "+5511999999999", 201),
    ]


def test_update_tenant_default_agent_only_mutates_caller_tenant(db_session):
    db_session.add_all(
        [
            Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"),
            Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"),
        ]
    )
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_contact(db_session, contact_id=102, tenant_id="tenant-a", friendly_name="Gamma")
    _seed_contact(db_session, contact_id=103, tenant_id="tenant-b", friendly_name="Beta")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101, is_default=True)
    _seed_agent(db_session, agent_id=202, tenant_id="tenant-a", contact_id=102, is_default=False)
    _seed_agent(db_session, agent_id=203, tenant_id="tenant-b", contact_id=103, is_default=True)
    db_session.commit()

    update_tenant_default_agent(
        payload=SimpleNamespace(agent_id=202),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    tenant_a = {
        row.id: row.is_default
        for row in db_session.query(Agent).filter(Agent.tenant_id == "tenant-a").all()
    }
    tenant_b = {
        row.id: row.is_default
        for row in db_session.query(Agent).filter(Agent.tenant_id == "tenant-b").all()
    }
    assert tenant_a == {201: False, 202: True}
    assert tenant_b == {203: True}


def test_update_instance_default_agent_rejects_foreign_agent(db_session):
    db_session.add_all(
        [
            Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"),
            Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"),
        ]
    )
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner-a@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_contact(db_session, contact_id=102, tenant_id="tenant-b", friendly_name="Beta")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    _seed_agent(db_session, agent_id=202, tenant_id="tenant-b", contact_id=102)
    _seed_whatsapp_instance(db_session, instance_id=301, tenant_id="tenant-a", created_by=1, default_agent_id=201)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        update_instance_default_agent(
            channel_type="whatsapp",
            instance_id=301,
            payload=InstanceDefaultUpdate(agent_id=202),
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Agent not found"


def test_upsert_user_channel_default_agent_updates_existing_row(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_contact(db_session, contact_id=102, tenant_id="tenant-a", friendly_name="Gamma")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    _seed_agent(db_session, agent_id=202, tenant_id="tenant-a", contact_id=102)
    db_session.add(
        UserChannelDefaultAgent(
            tenant_id="tenant-a",
            channel_type="whatsapp",
            user_identifier="+5511999999999",
            agent_id=201,
        )
    )
    db_session.commit()

    response = upsert_user_channel_default_agent(
        payload=UserChannelDefaultUpsert(
            channel_type="whatsapp",
            user_identifier="+5511999999999",
            agent_id=202,
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    stored = db_session.query(UserChannelDefaultAgent).filter(
        UserChannelDefaultAgent.tenant_id == "tenant-a",
        UserChannelDefaultAgent.channel_type == "whatsapp",
        UserChannelDefaultAgent.user_identifier == "+5511999999999",
    ).all()
    assert len(stored) == 1
    assert stored[0].agent_id == 202
    assert response.agent_name == "Gamma"
