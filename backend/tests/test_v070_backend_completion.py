"""Targeted backend coverage for the v0.7.0 070fix completion slice."""

from __future__ import annotations

import os
import sys
import types
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

from api import routes_email_triggers, routes_github_triggers, routes_jira_triggers  # noqa: E402
from api.routes_continuous import (  # noqa: E402
    ContinuousAgentCreate,
    ContinuousAgentUpdate,
    ContinuousCaller,
    create_continuous_agent,
    update_continuous_agent,
)
from api.routes_email_triggers import delete_email_trigger  # noqa: E402
from api.routes_flow_trigger_bindings import (  # noqa: E402
    FlowTriggerBindingCreate,
    FlowTriggerBindingUpdate,
    create_binding,
    list_bindings,
    update_binding,
)
from api.routes_github_integrations import (  # noqa: E402
    _to_read as github_integration_to_read,
    delete_github_integration,
)
from api.routes_github_triggers import _to_read as github_trigger_to_read  # noqa: E402
from api.routes_wizards import get_wizard_manifests  # noqa: E402
from models import (  # noqa: E402
    Agent,
    AgentSkillIntegration,
    Base,
    Contact,
    ContinuousAgent,
    ContinuousSubscription,
    EmailChannelInstance,
    FlowDefinition,
    FlowNode,
    FlowNodeRun,
    FlowRun,
    FlowTriggerBinding,
    GitHubChannelInstance,
    GitHubIntegration,
    HubIntegration,
    JiraChannelInstance,
    WebhookIntegration,
)
from models_rbac import Tenant, User  # noqa: E402


LONG_PURPOSE = "Review incoming activity and decide the next safe operational step."


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
            HubIntegration.__table__,
            GitHubIntegration.__table__,
            AgentSkillIntegration.__table__,
            EmailChannelInstance.__table__,
            JiraChannelInstance.__table__,
            GitHubChannelInstance.__table__,
            WebhookIntegration.__table__,
            FlowDefinition.__table__,
            FlowNode.__table__,
            FlowRun.__table__,
            FlowNodeRun.__table__,
            FlowTriggerBinding.__table__,
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


def _ctx(tenant_id: str):
    return SimpleNamespace(
        tenant_id=tenant_id,
        can_access_resource=lambda resource_tenant_id: resource_tenant_id == tenant_id,
    )


def _seed_tenant_user_agent(
    db,
    *,
    tenant_id: str = "tenant-a",
    user_id: int = 1,
    contact_id: int = 101,
    agent_id: int = 201,
):
    db.add(Tenant(id=tenant_id, name=tenant_id.title(), slug=tenant_id))
    db.add(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email=f"{tenant_id}-{user_id}@example.com",
            password_hash="x",
            is_active=True,
        )
    )
    db.add(Contact(id=contact_id, tenant_id=tenant_id, friendly_name=f"Agent {tenant_id}", role="agent"))
    db.add(
        Agent(
            id=agent_id,
            tenant_id=tenant_id,
            contact_id=contact_id,
            system_prompt="prompt",
            model_provider="gemini",
            model_name="gemini-2.5-pro",
            response_template="{response}",
            is_active=True,
        )
    )


def test_wizard_manifests_expose_per_kind_dependencies():
    manifests = {manifest.id: manifest for manifest in get_wizard_manifests()}

    productivity_kinds = {dep.kind: dep for dep in manifests["productivity"].kind_dependencies}
    trigger_kinds = {dep.kind: dep for dep in manifests["triggers"].kind_dependencies}
    flow_kinds = {dep.kind: dep for dep in manifests["flows"].kind_dependencies}
    continuous_kinds = {dep.kind: dep for dep in manifests["continuous-agents"].kind_dependencies}

    assert productivity_kinds["gmail"].create_endpoint == "/api/google/gmail/oauth/authorize"
    assert trigger_kinds["email"].required_dependency == "gmail_integration"
    assert trigger_kinds["email"].request_field == "gmail_integration_id"
    assert trigger_kinds["jira"].request_field == "jira_integration_id"
    assert trigger_kinds["github"].request_field == "github_integration_id"
    assert trigger_kinds["webhook"].required_dependency is None
    assert flow_kinds["flow"].create_endpoint == "/api/flows/create"
    assert continuous_kinds["continuous_agent"].request_field == "agent_id"


def test_flow_trigger_bindings_reject_schedule_and_validate_trigger_tenant(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, contact_id=102, agent_id=202)
    flow = FlowDefinition(id=501, tenant_id="tenant-a", name="Flow", execution_method="triggered")
    source = FlowNode(id=601, flow_definition_id=501, type="source", position=1, config_json="{}")
    foreign_trigger = EmailChannelInstance(
        id=701,
        tenant_id="tenant-b",
        integration_name="Foreign Email",
        created_by=2,
    )
    local_trigger = EmailChannelInstance(
        id=702,
        tenant_id="tenant-a",
        integration_name="Local Email",
        created_by=1,
    )
    schedule_binding = FlowTriggerBinding(
        id=801,
        tenant_id="tenant-a",
        flow_definition_id=501,
        trigger_kind="schedule",
        trigger_instance_id=999,
        is_active=True,
    )
    db_session.add_all([flow, source, foreign_trigger, local_trigger, schedule_binding])
    db_session.commit()

    with pytest.raises(ValidationError):
        FlowTriggerBindingCreate(flow_definition_id=501, trigger_kind="schedule", trigger_instance_id=1)

    with pytest.raises(HTTPException) as exc_info:
        create_binding(
            FlowTriggerBindingCreate(flow_definition_id=501, trigger_kind="email", trigger_instance_id=701),
            db=db_session,
            ctx=_ctx("tenant-a"),
        )
    assert exc_info.value.status_code == 403

    created = create_binding(
        FlowTriggerBindingCreate(flow_definition_id=501, trigger_kind="email", trigger_instance_id=702),
        db=db_session,
        ctx=_ctx("tenant-a"),
    )
    assert created.trigger_kind == "email"
    assert created.source_node_id == 601

    listed = list_bindings(db=db_session, ctx=_ctx("tenant-a"))
    assert [binding.trigger_kind for binding in listed] == ["email"]

    with pytest.raises(HTTPException) as hidden_exc:
        update_binding(
            801,
            FlowTriggerBindingUpdate(is_active=False),
            db=db_session,
            ctx=_ctx("tenant-a"),
        )
    assert hidden_exc.value.status_code == 404


def test_continuous_agent_update_persists_purpose_and_action_kind(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    db_session.commit()

    created = create_continuous_agent(
        ContinuousAgentCreate(
            agent_id=201,
            name="Watcher",
            purpose=LONG_PURPOSE,
            action_kind="react_only",
            execution_mode="hybrid",
        ),
        caller=ContinuousCaller(tenant_id="tenant-a", user_id=1),
        db=db_session,
    )
    updated = update_continuous_agent(
        created.id,
        ContinuousAgentUpdate(
            purpose="Send concise operational summaries after every qualifying wake event.",
            action_kind="send_message",
        ),
        caller=ContinuousCaller(tenant_id="tenant-a", user_id=1),
        db=db_session,
    )

    stored = db_session.query(ContinuousAgent).filter(ContinuousAgent.id == created.id).one()
    assert updated.purpose == "Send concise operational summaries after every qualifying wake event."
    assert updated.action_kind == "send_message"
    assert stored.purpose == updated.purpose
    assert stored.action_kind == "send_message"


def test_email_trigger_delete_cleans_bindings_system_flow_and_system_subscriptions(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    trigger = EmailChannelInstance(
        id=701,
        tenant_id="tenant-a",
        integration_name="Inbox",
        created_by=1,
    )
    flow = FlowDefinition(
        id=501,
        tenant_id="tenant-a",
        name="Email: Inbox",
        execution_method="triggered",
        is_system_owned=True,
    )
    source = FlowNode(id=601, flow_definition_id=501, type="source", position=1, config_json="{}")
    binding = FlowTriggerBinding(
        id=801,
        tenant_id="tenant-a",
        flow_definition_id=501,
        trigger_kind="email",
        trigger_instance_id=701,
        source_node_id=601,
        is_system_managed=True,
    )
    continuous_agent = ContinuousAgent(
        id=901,
        tenant_id="tenant-a",
        agent_id=201,
        name="Email Triage: Inbox",
        execution_mode="hybrid",
        status="active",
        is_system_owned=True,
    )
    subscription = ContinuousSubscription(
        id=1001,
        tenant_id="tenant-a",
        continuous_agent_id=901,
        channel_type="email",
        channel_instance_id=701,
        event_type="email.message.received",
        status="active",
        is_system_owned=True,
    )
    db_session.add_all([trigger, flow, source, binding, continuous_agent, subscription])
    db_session.commit()

    delete_email_trigger(trigger_id=701, ctx=_ctx("tenant-a"), _user=SimpleNamespace(id=1), db=db_session)

    assert db_session.query(EmailChannelInstance).filter(EmailChannelInstance.id == 701).first() is None
    assert db_session.query(FlowTriggerBinding).filter(FlowTriggerBinding.id == 801).first() is None
    assert db_session.query(FlowDefinition).filter(FlowDefinition.id == 501).first() is None
    assert db_session.query(ContinuousSubscription).filter(ContinuousSubscription.id == 1001).first() is None
    assert db_session.query(ContinuousAgent).filter(ContinuousAgent.id == 901).first() is None


def test_github_integration_count_delete_and_name_lookup_use_fk_and_tenant(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, contact_id=102, agent_id=202)
    integration = GitHubIntegration(
        id=11,
        tenant_id="tenant-a",
        type="github",
        name="GitHub A",
        display_name="GitHub A",
        provider="github",
        auth_method="pat",
        provider_mode="programmatic",
    )
    foreign_integration = GitHubIntegration(
        id=12,
        tenant_id="tenant-b",
        type="github",
        name="GitHub B",
        display_name="GitHub B",
        provider="github",
        auth_method="pat",
        provider_mode="programmatic",
    )
    linked_trigger = GitHubChannelInstance(
        id=301,
        tenant_id="tenant-a",
        integration_name="Repo 1",
        github_integration_id=11,
        repo_owner="octo",
        repo_name="one",
        events=["push"],
        created_by=1,
    )
    second_linked_trigger = GitHubChannelInstance(
        id=302,
        tenant_id="tenant-a",
        integration_name="Repo 2",
        github_integration_id=11,
        repo_owner="octo",
        repo_name="two",
        events=["push"],
        created_by=1,
    )
    foreign_linked_trigger = GitHubChannelInstance(
        id=303,
        tenant_id="tenant-a",
        integration_name="Foreign Link",
        github_integration_id=12,
        repo_owner="octo",
        repo_name="foreign",
        events=["push"],
        created_by=1,
    )
    db_session.add_all([integration, foreign_integration, linked_trigger, second_linked_trigger, foreign_linked_trigger])
    db_session.commit()

    assert github_integration_to_read(db_session, integration).trigger_count == 2
    assert github_trigger_to_read(db_session, foreign_linked_trigger).github_integration_name is None

    with pytest.raises(HTTPException) as exc_info:
        delete_github_integration(11, ctx=_ctx("tenant-a"), _user=SimpleNamespace(id=1), db=db_session)
    assert exc_info.value.status_code == 409
    assert "referenced by one or more triggers" in exc_info.value.detail


def test_legacy_jira_email_notification_subscription_routes_are_removed():
    email_paths = {route.path for route in routes_email_triggers.router.routes}
    jira_paths = {route.path for route in routes_jira_triggers.router.routes}

    assert "/{trigger_id}/notification-subscription" not in email_paths
    assert "/{trigger_id}/notification-subscription" not in jira_paths
