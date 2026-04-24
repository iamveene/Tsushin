from __future__ import annotations

import os
import sys
import types
import asyncio
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

from api import routes_jira_triggers as jira_routes  # noqa: E402
from api.routes_jira_triggers import (  # noqa: E402
    JiraTestQueryRequest,
    JiraTriggerCreate,
    JiraTriggerUpdate,
    create_jira_trigger,
    delete_jira_trigger,
    list_jira_triggers,
    run_saved_jira_test_query,
    update_jira_trigger,
)
from channels.jira.trigger import JiraTrigger  # noqa: E402
from hub.security import TokenEncryption  # noqa: E402
from models import Agent, Base, Contact, JiraChannelInstance  # noqa: E402
from models_rbac import Tenant, User  # noqa: E402


TEST_MASTER_KEY = "jira-test-master-key"


@pytest.fixture
def db_session(monkeypatch):
    monkeypatch.setattr(jira_routes, "get_webhook_encryption_key", lambda db: TEST_MASTER_KEY)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            Contact.__table__,
            Agent.__table__,
            JiraChannelInstance.__table__,
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


def test_create_jira_trigger_encrypts_token_and_lists_preview_only(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    db_session.commit()

    created = create_jira_trigger(
        payload=JiraTriggerCreate(
            integration_name="Jira Support",
            site_url="https://example.atlassian.net/",
            project_key="help",
            jql="project = HELP ORDER BY updated DESC",
            auth_email="jira@example.com",
            api_token="secret-token-1234",
            default_agent_id=201,
        ),
        ctx=_ctx("tenant-a"),
        current_user=SimpleNamespace(id=1),
        db=db_session,
    )

    stored = db_session.query(JiraChannelInstance).filter(JiraChannelInstance.id == created.id).first()
    listed = list_jira_triggers(ctx=_ctx("tenant-a"), _user=SimpleNamespace(id=1), db=db_session)
    decrypted = TokenEncryption(TEST_MASTER_KEY.encode()).decrypt(
        stored.api_token_encrypted,
        "tenant-a",
    )

    assert created.site_url == "https://example.atlassian.net"
    assert created.project_key == "HELP"
    assert created.api_token_preview == "secr...1234"
    assert created.default_agent_name == "Alpha"
    assert not hasattr(created, "api_token")
    assert stored.api_token_encrypted != "secret-token-1234"
    assert decrypted == "secret-token-1234"
    assert [row.integration_name for row in listed] == ["Jira Support"]


def test_create_jira_trigger_rejects_foreign_default_agent(db_session):
    db_session.add_all(
        [
            Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"),
            Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"),
        ]
    )
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=202, tenant_id="tenant-b", friendly_name="Beta")
    _seed_agent(db_session, agent_id=302, tenant_id="tenant-b", contact_id=202)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_jira_trigger(
            payload=JiraTriggerCreate(
                integration_name="Jira Support",
                site_url="https://example.atlassian.net",
                jql="project = HELP",
                default_agent_id=302,
            ),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Agent not found"


def test_update_jira_trigger_rotates_and_clears_token(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    trigger = JiraChannelInstance(
        tenant_id="tenant-a",
        integration_name="Jira Support",
        site_url="https://example.atlassian.net",
        project_key="HELP",
        jql="project = HELP",
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    updated = update_jira_trigger(
        trigger_id=trigger.id,
        payload=JiraTriggerUpdate(api_token="rotated-token-5678", is_active=False),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )
    stored = db_session.query(JiraChannelInstance).filter(JiraChannelInstance.id == trigger.id).first()
    decrypted = TokenEncryption(TEST_MASTER_KEY.encode()).decrypt(
        stored.api_token_encrypted,
        "tenant-a",
    )

    assert updated.api_token_preview == "rota...5678"
    assert updated.status == "paused"
    assert decrypted == "rotated-token-5678"

    cleared = update_jira_trigger(
        trigger_id=trigger.id,
        payload=JiraTriggerUpdate(api_token=None),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert cleared.api_token_preview is None
    assert stored.api_token_encrypted is None


def test_delete_jira_trigger_is_tenant_scoped(db_session):
    db_session.add_all(
        [
            Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"),
            Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"),
        ]
    )
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    trigger_a = JiraChannelInstance(
        tenant_id="tenant-a",
        integration_name="Tenant A Jira",
        site_url="https://a.atlassian.net",
        jql="project = A",
        created_by=1,
    )
    trigger_b = JiraChannelInstance(
        tenant_id="tenant-b",
        integration_name="Tenant B Jira",
        site_url="https://b.atlassian.net",
        jql="project = B",
        created_by=1,
    )
    db_session.add_all([trigger_a, trigger_b])
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_jira_trigger(
            trigger_id=trigger_b.id,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 404

    delete_jira_trigger(
        trigger_id=trigger_a.id,
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    remaining = db_session.query(JiraChannelInstance.integration_name).all()
    assert [row.integration_name for row in remaining] == ["Tenant B Jira"]


def test_saved_jira_query_decrypts_token_and_returns_small_sample(db_session, monkeypatch):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    encrypted = TokenEncryption(TEST_MASTER_KEY.encode()).encrypt("secret-token", "tenant-a")
    trigger = JiraChannelInstance(
        tenant_id="tenant-a",
        integration_name="Jira Support",
        site_url="https://example.atlassian.net",
        project_key="HELP",
        jql="project = HELP",
        auth_email="jira@example.com",
        api_token_encrypted=encrypted,
        api_token_preview="secr...oken",
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()
    captured = {}

    async def fake_execute_jira_search(**kwargs):
        captured.update(kwargs)
        return {
            "total": 2,
            "issues": [
                {
                    "id": "10001",
                    "key": "HELP-1",
                    "fields": {
                        "summary": "First issue",
                        "status": {"name": "To Do"},
                        "updated": "2026-04-20T10:00:00.000+0000",
                    },
                }
            ],
        }

    monkeypatch.setattr(jira_routes, "_execute_jira_search", fake_execute_jira_search)

    response = asyncio.run(
        run_saved_jira_test_query(
            trigger_id=trigger.id,
            payload=JiraTestQueryRequest(max_results=2),
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    )

    assert captured == {
        "site_url": "https://example.atlassian.net",
        "jql": "project = HELP",
        "auth_email": "jira@example.com",
        "api_token": "secret-token",
        "max_results": 2,
    }
    assert response.total == 2
    assert response.sample_count == 1
    assert response.issues[0].key == "HELP-1"
    assert response.issues[0].summary == "First issue"


def test_jira_trigger_normalizes_issue_to_dispatch_input(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    trigger_row = JiraChannelInstance(
        tenant_id="tenant-a",
        integration_name="Jira Support",
        site_url="https://example.atlassian.net",
        project_key="HELP",
        jql="project = HELP",
        default_agent_id=201,
        created_by=1,
    )
    db_session.add(trigger_row)
    db_session.commit()

    trigger = JiraTrigger(db_session, trigger_row.id, SimpleNamespace())
    dispatch_input = trigger.normalize_issue_payload(
        {
            "id": "10001",
            "key": "HELP-1",
            "fields": {
                "summary": "First issue",
                "updated": "2026-04-20T10:00:00.000+0000",
                "reporter": {"accountId": "reporter-1"},
            },
        }
    )

    assert dispatch_input.trigger_type == "jira"
    assert dispatch_input.instance_id == trigger_row.id
    assert dispatch_input.event_type == "jira.issue.updated"
    assert dispatch_input.dedupe_key == "10001:2026-04-20T10:00:00.000+0000"
    assert dispatch_input.explicit_agent_id == 201
    assert dispatch_input.sender_key == "reporter-1"
    assert dispatch_input.source_id == "HELP-1"
    assert dispatch_input.payload["jira"]["project_key"] == "HELP"
