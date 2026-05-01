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
from api.routes_jira_integrations import (  # noqa: E402
    JiraIntegrationCreate,
    create_jira_integration,
    list_jira_integrations,
)
from api.routes_jira_triggers import (  # noqa: E402
    JiraTestQueryRequest,
    JiraTriggerCreate,
    JiraTriggerUpdate,
    create_jira_trigger,
    delete_jira_trigger,
    list_jira_triggers,
    poll_jira_trigger_now,
    run_saved_jira_test_query,
    update_jira_trigger,
)
from channels.jira.trigger import JiraTrigger  # noqa: E402
from hub.security import TokenEncryption  # noqa: E402
from models import (  # noqa: E402
    Agent,
    Base,
    BudgetPolicy,
    ChannelEventDedupe,
    Config,
    Contact,
    ContinuousAgent,
    ContinuousRun,
    ContinuousSubscription,
    DeliveryPolicy,
    FlowDefinition,
    FlowNode,
    FlowNodeRun,
    FlowRun,
    FlowTriggerBinding,
    HubIntegration,
    JiraChannelInstance,
    JiraIntegration,
    SentinelProfile,
    TriggerRecapConfig,
    WakeEvent,
    WhatsAppMCPInstance,
)
from models_rbac import Tenant, User  # noqa: E402
from services import jira_integration_service  # noqa: E402


TEST_MASTER_KEY = "jira-test-master-key"


@pytest.fixture
def db_session(monkeypatch):
    monkeypatch.setattr(jira_integration_service, "get_webhook_encryption_key", lambda db: TEST_MASTER_KEY)
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
            SentinelProfile.__table__,
            DeliveryPolicy.__table__,
            BudgetPolicy.__table__,
            FlowDefinition.__table__,
            FlowNode.__table__,
            FlowRun.__table__,
            FlowNodeRun.__table__,
            FlowTriggerBinding.__table__,
            HubIntegration.__table__,
            JiraIntegration.__table__,
            ContinuousAgent.__table__,
            ContinuousSubscription.__table__,
            WakeEvent.__table__,
            ContinuousRun.__table__,
            ChannelEventDedupe.__table__,
            JiraChannelInstance.__table__,
            TriggerRecapConfig.__table__,
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


def test_create_jira_integration_encrypts_token_and_lists_preview_only(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    db_session.commit()

    created = create_jira_integration(
        payload=JiraIntegrationCreate(
            integration_name="Jira Production",
            site_url="https://example.atlassian.net/jira/",
            auth_email="jira@example.com",
            api_token="secret-token-1234",
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    stored = db_session.query(JiraIntegration).filter(JiraIntegration.id == created.id).one()
    decrypted = TokenEncryption(TEST_MASTER_KEY.encode()).decrypt(
        stored.api_token_encrypted,
        "tenant-a",
    )
    listed = list_jira_integrations(ctx=_ctx("tenant-a"), _user=SimpleNamespace(id=1), db=db_session)

    assert created.integration_name == "Jira Production"
    assert created.site_url == "https://example.atlassian.net"
    assert created.api_token_preview == "secr...1234"
    assert created.trigger_count == 0
    assert not hasattr(created, "api_token")
    assert stored.type == "jira"
    assert stored.api_token_encrypted != "secret-token-1234"
    assert decrypted == "secret-token-1234"
    assert [row.id for row in listed] == [created.id]


def test_create_jira_trigger_links_integration_and_lists_preview_only(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    db_session.commit()
    integration = create_jira_integration(
        payload=JiraIntegrationCreate(
            integration_name="Jira Production",
            site_url="https://example.atlassian.net/jira/",
            auth_email="jira@example.com",
            api_token="secret-token-1234",
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    created = create_jira_trigger(
        payload=JiraTriggerCreate(
            integration_name="Jira Support",
            jira_integration_id=integration.id,
            project_key="help",
            jql="project = HELP ORDER BY updated DESC",
            default_agent_id=201,
        ),
        ctx=_ctx("tenant-a"),
        current_user=SimpleNamespace(id=1),
        db=db_session,
    )

    stored = db_session.query(JiraChannelInstance).filter(JiraChannelInstance.id == created.id).first()
    listed = list_jira_triggers(ctx=_ctx("tenant-a"), _user=SimpleNamespace(id=1), db=db_session)

    assert created.jira_integration_id == integration.id
    assert created.jira_integration_name == "Jira Production"
    assert created.site_url == "https://example.atlassian.net"
    assert created.project_key == "HELP"
    assert created.default_agent_name == "Alpha"
    assert not hasattr(created, "api_token")
    assert not hasattr(created, "api_token_preview")
    assert stored.jira_integration_id == integration.id
    assert stored.api_token_encrypted is None
    assert [row.integration_name for row in listed] == ["Jira Support"]


def test_create_jira_trigger_uses_hub_jira_integration_credentials(db_session, monkeypatch):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    db_session.commit()

    integration = create_jira_integration(
        payload=JiraIntegrationCreate(
            integration_name="Jira Production",
            site_url="https://example.atlassian.net/jira",
            auth_email="jira@example.com",
            api_token="secret-token",
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )
    created = create_jira_trigger(
        payload=JiraTriggerCreate(
            integration_name="Jira Support",
            jira_integration_id=integration.id,
            jql="project = HELP",
        ),
        ctx=_ctx("tenant-a"),
        current_user=SimpleNamespace(id=1),
        db=db_session,
    )
    captured = {}

    async def fake_execute_jira_search(**kwargs):
        captured.update(kwargs)
        return {
            "total": 1,
            "issues": [
                {
                    "id": "10001",
                    "key": "HELP-1",
                    "fields": {"summary": "First issue", "status": {"name": "To Do"}},
                }
            ],
        }

    monkeypatch.setattr(jira_routes, "_execute_jira_search", fake_execute_jira_search)

    response = asyncio.run(
        run_saved_jira_test_query(
            trigger_id=created.id,
            payload=JiraTestQueryRequest(max_results=2),
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    )

    assert created.jira_integration_id == integration.id
    assert created.jira_integration_name == "Jira Production"
    assert created.site_url == "https://example.atlassian.net"
    assert not hasattr(created, "auth_email")
    assert not hasattr(created, "api_token_preview")
    assert captured == {
        "site_url": "https://example.atlassian.net",
        "jql": "project = HELP",
        "auth_email": "jira@example.com",
        "api_token": "secret-token",
        "max_results": 2,
    }
    assert response.issues[0].key == "HELP-1"


def test_create_jira_trigger_rejects_foreign_jira_integration(db_session):
    db_session.add_all(
        [
            Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"),
            Tenant(id="tenant-b", name="Tenant B", slug="tenant-b"),
        ]
    )
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    db_session.commit()
    integration = create_jira_integration(
        payload=JiraIntegrationCreate(
            integration_name="Tenant B Jira",
            site_url="https://b.atlassian.net",
            auth_email="jira@example.com",
            api_token="secret-token",
        ),
        ctx=_ctx("tenant-b"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    with pytest.raises(HTTPException) as exc_info:
        create_jira_trigger(
            payload=JiraTriggerCreate(
                integration_name="Jira Support",
                jira_integration_id=integration.id,
                jql="project = HELP",
            ),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Jira integration not found"


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
    integration = create_jira_integration(
        payload=JiraIntegrationCreate(
            integration_name="Tenant A Jira",
            site_url="https://a.atlassian.net",
            auth_email="jira@example.com",
            api_token="secret-token",
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    with pytest.raises(HTTPException) as exc_info:
        create_jira_trigger(
            payload=JiraTriggerCreate(
                integration_name="Jira Support",
                jira_integration_id=integration.id,
                jql="project = HELP",
                default_agent_id=302,
            ),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Agent not found"


def test_update_jira_trigger_relinks_integration_and_pauses(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    db_session.commit()
    first_integration = create_jira_integration(
        payload=JiraIntegrationCreate(
            integration_name="Jira Production",
            site_url="https://example.atlassian.net",
            auth_email="jira@example.com",
            api_token="secret-token",
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )
    second_integration = create_jira_integration(
        payload=JiraIntegrationCreate(
            integration_name="Jira Support",
            site_url="https://support.atlassian.net",
            auth_email="support@example.com",
            api_token="rotated-token",
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )
    trigger = JiraChannelInstance(
        tenant_id="tenant-a",
        integration_name="Jira Trigger",
        jira_integration_id=first_integration.id,
        site_url="https://example.atlassian.net",
        project_key="HELP",
        jql="project = HELP",
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    updated = update_jira_trigger(
        trigger_id=trigger.id,
        payload=JiraTriggerUpdate(jira_integration_id=second_integration.id, is_active=False),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )
    stored = db_session.query(JiraChannelInstance).filter(JiraChannelInstance.id == trigger.id).first()

    assert updated.jira_integration_id == second_integration.id
    assert updated.jira_integration_name == "Jira Support"
    assert updated.site_url == "https://support.atlassian.net"
    assert updated.status == "paused"
    assert stored.jira_integration_id == second_integration.id
    assert stored.api_token_encrypted is None


def test_jira_recap_config_get_returns_default_without_saved_row(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    trigger = JiraChannelInstance(
        tenant_id="tenant-a",
        integration_name="Jira Trigger",
        site_url="https://example.atlassian.net",
        project_key="HELP",
        jql="project = HELP",
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    out = jira_routes.get_jira_trigger_recap_config(
        trigger_id=trigger.id,
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert out.id is None
    assert out.tenant_id == "tenant-a"
    assert out.trigger_kind == "jira"
    assert out.trigger_instance_id == trigger.id
    assert out.enabled is False
    assert out.scope == "trigger_instance"
    assert db_session.query(TriggerRecapConfig).count() == 0


def test_jira_recap_config_delete_missing_still_404(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    trigger = JiraChannelInstance(
        tenant_id="tenant-a",
        integration_name="Jira Trigger",
        site_url="https://example.atlassian.net",
        project_key="HELP",
        jql="project = HELP",
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        jira_routes.delete_jira_trigger_recap_config(
            trigger_id=trigger.id,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 404


def test_update_jira_trigger_syncs_managed_flow_default_agent(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    _seed_user(db_session, user_id=1, tenant_id="tenant-a", email="owner@example.com")
    _seed_contact(db_session, contact_id=101, tenant_id="tenant-a", friendly_name="Alpha")
    _seed_agent(db_session, agent_id=201, tenant_id="tenant-a", contact_id=101)
    _seed_contact(db_session, contact_id=102, tenant_id="tenant-a", friendly_name="Beta")
    _seed_agent(db_session, agent_id=202, tenant_id="tenant-a", contact_id=102)
    trigger = JiraChannelInstance(
        tenant_id="tenant-a",
        integration_name="Jira Trigger",
        site_url="https://example.atlassian.net",
        project_key="HELP",
        jql="project = HELP",
        default_agent_id=201,
        created_by=1,
    )
    flow = FlowDefinition(
        id=901,
        tenant_id="tenant-a",
        name="Jira: Jira Trigger",
        execution_method="triggered",
        default_agent_id=201,
        is_system_owned=True,
    )
    conversation = FlowNode(
        id=902,
        flow_definition_id=901,
        type="conversation",
        position=3,
        name="Default agent",
        agent_id=201,
        config_json="{}",
    )
    binding = FlowTriggerBinding(
        id=903,
        tenant_id="tenant-a",
        flow_definition_id=901,
        trigger_kind="jira",
        trigger_instance_id=1,
        is_system_managed=True,
        is_active=True,
        suppress_default_agent=False,
    )
    db_session.add_all([trigger, flow, conversation, binding])
    db_session.flush()
    binding.trigger_instance_id = trigger.id
    db_session.commit()

    updated = update_jira_trigger(
        trigger_id=trigger.id,
        payload=JiraTriggerUpdate(default_agent_id=202),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    db_session.refresh(flow)
    db_session.refresh(conversation)
    assert updated.default_agent_id == 202
    assert flow.default_agent_id == 202
    assert conversation.agent_id == 202


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
    assert response.issues[0].link == "https://example.atlassian.net/browse/HELP-1"


def test_jira_search_uses_current_jql_endpoint(monkeypatch):
    captured = {}

    class FakeResponse:
        status_code = 200

        def json(self):
            return {"issues": [{"id": "10001", "key": "HELP-1", "fields": {"summary": "First"}}]}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            captured["timeout"] = kwargs.get("timeout")

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, *, json, auth=None):
            captured["url"] = url
            captured["json"] = json
            captured["auth"] = auth
            return FakeResponse()

    monkeypatch.setattr(jira_routes.httpx, "AsyncClient", FakeClient)

    result = asyncio.run(
        jira_routes._execute_jira_search(
            site_url="https://example.atlassian.net/jira",
            jql="project = HELP",
            auth_email="jira@example.com",
            api_token="secret-token",
            max_results=3,
        )
    )

    assert captured["url"] == "https://example.atlassian.net/rest/api/3/search/jql"
    assert captured["json"]["jql"] == "project = HELP"
    assert captured["json"]["maxResults"] == 3
    assert captured["json"]["fields"] == [
        "summary",
        "description",
        "status",
        "issuetype",
        "project",
        "priority",
        "reporter",
        "assignee",
        "created",
        "updated",
        "labels",
    ]
    assert "startAt" not in captured["json"]
    assert captured["auth"] == ("jira@example.com", "secret-token")
    assert result["issues"][0]["key"] == "HELP-1"


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
    assert dispatch_input.event_type == "jira.issue.detected"
    assert dispatch_input.dedupe_key == "jira_issue:HELP-1"
    assert dispatch_input.explicit_agent_id == 201
    assert dispatch_input.sender_key == "reporter-1"
    assert dispatch_input.source_id == "HELP-1"
    assert dispatch_input.payload["jira"]["project_key"] == "HELP"
