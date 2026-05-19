"""Repository Automation Wizard backend tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
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


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


from api import routes_github_inbound as github_inbound  # noqa: E402
from api.routes_wizards import create_repository_automation  # noqa: E402
from api.schemas.repository_automation import RepositoryAutomationRequest  # noqa: E402
from auth_dependencies import TenantContext  # noqa: E402
from models import (  # noqa: E402
    Agent,
    AgentSkill,
    AgentSkillIntegration,
    AgentTeam,
    AgentTeamMember,
    AgentTeamTrigger,
    Base,
    FlowDefinition,
    FlowTriggerBinding,
    GitHubChannelInstance,
    GitHubIntegration,
    GitLabChannelInstance,
    GitLabIntegration,
)
from models_rbac import Tenant, User  # noqa: E402


@pytest.fixture
def db_session(monkeypatch):
    from services import repository_automation_wizard_service as service
    from config import feature_flags

    monkeypatch.setattr(feature_flags, "flows_auto_generation_enabled", lambda: False)
    monkeypatch.setattr(service, "encrypt_github_webhook_secret", lambda db, tenant_id, secret: f"enc:{secret}")
    monkeypatch.setattr(service, "encrypt_gitlab_webhook_secret", lambda db, tenant_id, secret: f"enc:{secret}")

    engine = create_engine("sqlite:///:memory:", echo=False)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


def _seed_tenant(db, tenant_id: str = "tenant-a", user_id: int = 1):
    db.add(Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=tenant_id, plan="dev"))
    db.add(User(id=user_id, tenant_id=tenant_id, email=f"{tenant_id}@example.com"))
    db.flush()


def _ctx(db, tenant_id: str = "tenant-a", user_id: int = 1) -> TenantContext:
    return TenantContext(user=SimpleNamespace(id=user_id, tenant_id=tenant_id, is_global_admin=False), db=db)


def _user(tenant_id: str = "tenant-a", user_id: int = 1):
    return SimpleNamespace(id=user_id, tenant_id=tenant_id, is_global_admin=False)


def _github_integration(db, tenant_id: str = "tenant-a", *, active: bool = True) -> GitHubIntegration:
    integration = GitHubIntegration(
        tenant_id=tenant_id,
        type="github",
        name="GitHub",
        display_name="GitHub",
        is_active=active,
        provider="github",
    )
    db.add(integration)
    db.flush()
    return integration


def _gitlab_integration(db, tenant_id: str = "tenant-a", *, active: bool = True) -> GitLabIntegration:
    integration = GitLabIntegration(
        tenant_id=tenant_id,
        type="gitlab",
        name="GitLab",
        display_name="GitLab",
        is_active=active,
        provider="gitlab",
    )
    db.add(integration)
    db.flush()
    return integration


def _create(payload: RepositoryAutomationRequest, db, tenant_id: str = "tenant-a"):
    return create_repository_automation(payload, ctx=_ctx(db, tenant_id), current_user=_user(tenant_id), db=db)


def test_github_review_team_creates_trigger_flow_team_agents_and_canonical_binding(db_session):
    _seed_tenant(db_session)
    integration = _github_integration(db_session)
    db_session.commit()

    result = _create(
        RepositoryAutomationRequest(
            provider="github",
            integration_id=integration.id,
            repo_owner="octo",
            repo_name="repo",
            template_id="repository_review_team",
            events=["pull_request"],
            branch_filter="main",
            path_filters=["backend/**"],
            author_filter="dependabot",
        ),
        db_session,
    )

    assert result["integration"]["reused"] is True
    assert result["trigger"]["reused"] is False
    assert result["trigger"]["events"] == ["pull_request"]
    assert result["trigger"]["canonical_events"] == ["github.pull_request"]
    assert result["routing_mode"] == "team_primary"
    assert result["team"]["status"] == "active"
    assert result["team"]["member_count"] == 3
    assert len(result["agents"]) == 3
    assert {
        agent["name"].rsplit(" ", 1)[-1]
        if not agent["name"].endswith("Merge Readiness")
        else "Merge Readiness"
        for agent in result["agents"]
    } == {"Coordinator", "Reviewer", "Merge Readiness"}
    assert all({"agent_communication", "code_repository"} <= set(agent["skills"]) for agent in result["agents"])

    trigger = db_session.get(GitHubChannelInstance, result["trigger"]["id"])
    assert trigger.default_agent_id is None
    assert trigger.branch_filter == "main"
    assert trigger.path_filters == ["backend/**"]

    flow_binding = db_session.query(FlowTriggerBinding).one()
    assert flow_binding.is_system_managed is True
    assert flow_binding.is_active is False
    assert flow_binding.suppress_default_agent is True
    assert db_session.get(FlowDefinition, result["flow"]["id"]) is not None
    assert db_session.query(AgentTeamMember).count() == 3

    team_binding = db_session.query(AgentTeamTrigger).one()
    assert team_binding.config_json["event_types"] == ["github.pull_request"]
    assert result["bindings"][1]["kind"] == "team"


def test_gitlab_standalone_agent_routes_generated_flow_to_reviewer(db_session):
    _seed_tenant(db_session)
    integration = _gitlab_integration(db_session)
    db_session.commit()

    result = _create(
        RepositoryAutomationRequest(
            provider="gitlab",
            integration_id=integration.id,
            project_path="group/project",
            template_id="repository_pr_agent",
            events=["Merge Request Hook"],
            agent_name="MR Reviewer",
        ),
        db_session,
    )

    agent_id = result["agents"][0]["id"]
    assert result["team"] is None
    assert result["routing_mode"] == "agent_flow"
    assert result["trigger"]["events"] == ["merge_request"]
    assert result["trigger"]["canonical_events"] == ["gitlab.merge_request"]
    assert result["flow"]["default_agent_id"] == agent_id

    trigger = db_session.get(GitLabChannelInstance, result["trigger"]["id"])
    assert trigger.default_agent_id == agent_id
    binding = db_session.query(FlowTriggerBinding).one()
    assert binding.is_active is True
    assert binding.suppress_default_agent is True

    skills = {
        row.skill_type
        for row in db_session.query(AgentSkill).filter(AgentSkill.agent_id == agent_id).all()
    }
    assert {"code_repository", "agent_communication"} <= skills
    skill_integration = db_session.query(AgentSkillIntegration).filter_by(agent_id=agent_id).one()
    assert skill_integration.skill_type == "code_repository"
    assert skill_integration.integration_id == integration.id


def test_same_repository_label_keeps_github_and_gitlab_agents_separate(db_session):
    _seed_tenant(db_session)
    github = _github_integration(db_session)
    gitlab = _gitlab_integration(db_session)
    db_session.commit()

    github_result = _create(
        RepositoryAutomationRequest(
            provider="github",
            integration_id=github.id,
            repo_owner="octo",
            repo_name="repo",
            template_id="repository_pr_agent",
            events=["pull_request"],
        ),
        db_session,
    )
    github_agent_id = github_result["agents"][0]["id"]
    assert github_result["agents"][0]["name"] == "GitHub octo/repo Reviewer"

    gitlab_result = _create(
        RepositoryAutomationRequest(
            provider="gitlab",
            integration_id=gitlab.id,
            project_path="octo/repo",
            template_id="repository_review_team",
            events=["merge_request"],
        ),
        db_session,
    )
    gitlab_agent_ids = {agent["id"] for agent in gitlab_result["agents"]}
    assert github_agent_id not in gitlab_agent_ids
    assert gitlab_result["team"]["name"] == "GitLab octo/repo Review Team"
    assert {agent["name"] for agent in gitlab_result["agents"]} == {
        "GitLab octo/repo Coordinator",
        "GitLab octo/repo Reviewer",
        "GitLab octo/repo Merge Readiness",
    }

    github_skill = db_session.query(AgentSkillIntegration).filter_by(
        agent_id=github_agent_id,
        skill_type="code_repository",
    ).one()
    assert github_skill.integration_id == github.id

    gitlab_skills = (
        db_session.query(AgentSkillIntegration)
        .filter(
            AgentSkillIntegration.agent_id.in_(gitlab_agent_ids),
            AgentSkillIntegration.skill_type == "code_repository",
        )
        .all()
    )
    assert len(gitlab_skills) == 3
    assert {row.integration_id for row in gitlab_skills} == {gitlab.id}


def test_trigger_reuse_and_team_binding_are_idempotent(db_session):
    _seed_tenant(db_session)
    integration = _github_integration(db_session)
    db_session.commit()
    payload = RepositoryAutomationRequest(
        provider="github",
        integration_id=integration.id,
        repo_owner="octo",
        repo_name="repo",
        template_id="repository_review_team",
        events=["pull_request"],
        team_name="Repo Review",
    )

    first = _create(payload, db_session)
    second = _create(payload, db_session)

    assert second["trigger"]["id"] == first["trigger"]["id"]
    assert second["trigger"]["reused"] is True
    assert db_session.query(GitHubChannelInstance).count() == 1
    assert db_session.query(AgentTeamTrigger).count() == 1
    assert db_session.query(FlowTriggerBinding).count() == 1


def test_wizard_rolls_back_partial_team_creation_on_binding_failure(db_session, monkeypatch):
    from services.repository_automation_wizard_service import (
        RepositoryAutomationWizardError,
        RepositoryAutomationWizardService,
    )

    _seed_tenant(db_session)
    integration = _github_integration(db_session)
    db_session.commit()

    def fail_binding(self, *args, **kwargs):
        raise RepositoryAutomationWizardError(500, "forced binding failure")

    monkeypatch.setattr(RepositoryAutomationWizardService, "_bind_team_to_trigger", fail_binding)

    with pytest.raises(HTTPException) as exc:
        _create(
            RepositoryAutomationRequest(
                provider="github",
                integration_id=integration.id,
                repo_owner="octo",
                repo_name="repo",
                template_id="repository_review_team",
                events=["pull_request"],
            ),
            db_session,
        )

    assert exc.value.status_code == 500
    assert db_session.query(GitHubChannelInstance).count() == 0
    assert db_session.query(Agent).count() == 0
    assert db_session.query(AgentTeam).count() == 0
    assert db_session.query(AgentTeamMember).count() == 0
    assert db_session.query(FlowTriggerBinding).count() == 0


def test_wizard_rejects_foreign_and_inactive_resources(db_session):
    _seed_tenant(db_session, "tenant-a", 1)
    _seed_tenant(db_session, "tenant-b", 2)
    foreign = _github_integration(db_session, "tenant-b")
    inactive = _github_integration(db_session, "tenant-a", active=False)
    active = _github_integration(db_session, "tenant-a")
    inactive_trigger = GitHubChannelInstance(
        tenant_id="tenant-a",
        integration_name="Paused",
        github_integration_id=active.id,
        repo_owner="octo",
        repo_name="repo",
        events=["pull_request"],
        is_active=False,
        status="paused",
        created_by=1,
    )
    db_session.add(inactive_trigger)
    db_session.commit()

    base = {
        "provider": "github",
        "repo_owner": "octo",
        "repo_name": "repo",
        "template_id": "repository_pr_agent",
    }
    with pytest.raises(HTTPException) as foreign_exc:
        _create(RepositoryAutomationRequest(integration_id=foreign.id, **base), db_session)
    assert foreign_exc.value.status_code == 404

    with pytest.raises(HTTPException) as inactive_integration_exc:
        _create(RepositoryAutomationRequest(integration_id=inactive.id, **base), db_session)
    assert inactive_integration_exc.value.status_code == 409

    with pytest.raises(HTTPException) as inactive_trigger_exc:
        _create(
            RepositoryAutomationRequest(
                integration_id=active.id,
                existing_trigger_id=inactive_trigger.id,
                **base,
            ),
            db_session,
        )
    assert inactive_trigger_exc.value.status_code == 409


def test_event_canonicalization_rejects_unsupported_repository_team_events(db_session):
    _seed_tenant(db_session)
    integration = _github_integration(db_session)
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        _create(
            RepositoryAutomationRequest(
                provider="github",
                integration_id=integration.id,
                repo_owner="octo",
                repo_name="repo",
                template_id="repository_review_team",
                events=["gitlab.merge_request"],
            ),
            db_session,
        )
    assert exc.value.status_code == 422


def test_github_inbound_accepted_response_includes_team_run_ids(monkeypatch):
    instance = SimpleNamespace(
        id=10,
        tenant_id="tenant-a",
        is_active=True,
        status="active",
        webhook_secret_encrypted="enc",
        last_delivery_id=None,
        last_activity_at=None,
    )
    monkeypatch.setattr(github_inbound, "_load_public_instance", lambda db, trigger_id: instance)
    monkeypatch.setattr(github_inbound, "decrypt_webhook_secret", lambda db, tenant_id, encrypted: "secret")
    monkeypatch.setattr(github_inbound, "verify_github_signature", lambda raw, signature, secret: True)
    monkeypatch.setattr(github_inbound, "github_filters_match", lambda instance, event, payload: (True, None))
    monkeypatch.setattr(github_inbound, "occurred_at_for_payload", lambda payload: None)
    monkeypatch.setattr(github_inbound, "sender_key_for_payload", lambda instance_id, payload: "sender")

    class _Dispatcher:
        def __init__(self, db):
            self.db = db

        def dispatch(self, _event):
            return SimpleNamespace(
                status="dispatched",
                wake_event_id=77,
                continuous_run_ids=[88],
                team_run_ids=[99],
            )

    class _Request:
        async def body(self):
            return json.dumps({"repository": {"full_name": "octo/repo"}}).encode("utf-8")

    monkeypatch.setattr(github_inbound, "TriggerDispatchService", _Dispatcher)
    db = SimpleNamespace(commit=lambda: None)

    response = asyncio.run(
        github_inbound.receive_github_webhook(
            10,
            _Request(),
            x_hub_signature_256="sha256=test",
            x_github_event="pull_request",
            x_github_delivery="delivery-1",
            db=db,
        )
    )
    assert response["status"] == "accepted"
    assert response["team_run_ids"] == [99]
