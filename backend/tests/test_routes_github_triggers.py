"""GitHub trigger route tests.

v0.7.0-fix Phase 3 deleted the per-trigger PAT path (auth_method,
installation_id, pat_token, /test-connection, /check-connection) and
replaced it with a required ``github_integration_id`` FK. The trigger
now reads its credentials from the linked Hub ``GitHubIntegration`` at
call time. The test suite mirrors the Jira sibling
(``test_routes_jira_triggers.py``) — seed a Hub integration, then create
the trigger with ``github_integration_id``.
"""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import os
import sys
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

from api import routes_github_inbound as inbound  # noqa: E402
from api import routes_github_triggers as triggers  # noqa: E402
from api.routes_github_triggers import (  # noqa: E402
    GitHubTriggerCreate,
    GitHubTriggerUpdate,
    create_github_trigger,
    delete_github_trigger,
    list_github_triggers,
    update_github_trigger,
)
from channels.github import trigger as github_trigger  # noqa: E402
from models import (  # noqa: E402
    Agent,
    Base,
    Contact,
    FlowTriggerBinding,
    GitHubChannelInstance,
    GitHubIntegration,
    HubIntegration,
)
from models_rbac import Tenant, User  # noqa: E402

TEST_MASTER_KEY = "github-test-master-key"


class _RequestStub:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


@pytest.fixture
def db_session(monkeypatch):
    # Stub the encryption-key lookup so PAT/webhook secrets encrypt deterministically.
    from services import encryption_key_service

    monkeypatch.setattr(
        encryption_key_service, "get_api_key_encryption_key", lambda db: TEST_MASTER_KEY
    )
    monkeypatch.setattr(
        encryption_key_service, "get_webhook_encryption_key", lambda db: TEST_MASTER_KEY
    )
    # Disable auto-flow generation — the unit test scope is the trigger CRUD
    # contract, not the FlowDefinition / FlowTriggerBinding side-effects.
    from config import feature_flags

    monkeypatch.setattr(feature_flags, "flows_auto_generation_enabled", lambda: False)

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
            GitHubChannelInstance.__table__,
            FlowTriggerBinding.__table__,
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


def _seed_tenant_user_agent(
    db,
    *,
    tenant_id: str,
    user_id: int,
    contact_id: int,
    agent_id: int,
):
    db.add(Tenant(id=tenant_id, name=tenant_id.title(), slug=tenant_id))
    db.add(
        User(
            id=user_id,
            tenant_id=tenant_id,
            email=f"{tenant_id}@example.com",
            password_hash="x",
            is_active=True,
        )
    )
    db.add(
        Contact(
            id=contact_id,
            tenant_id=tenant_id,
            friendly_name=f"Agent {tenant_id}",
            role="agent",
        )
    )
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


def _seed_github_integration(
    db,
    *,
    integration_id: int,
    tenant_id: str,
    name: str = "GitHub Production",
    pat_token: str = "ghp_secret7890",
) -> GitHubIntegration:
    encrypted = github_trigger.encrypt_pat_token(db, tenant_id, pat_token)
    integration = GitHubIntegration(
        id=integration_id,
        tenant_id=tenant_id,
        type="github",
        name=name,
        display_name=name,
        provider="github",
        auth_method="pat",
        pat_token_encrypted=encrypted,
        pat_token_preview=f"{pat_token[:4]}...{pat_token[-4:]}",
        provider_mode="programmatic",
        is_active=True,
    )
    db.add(integration)
    return integration


def _seed_github_trigger(
    db,
    *,
    instance_id: int,
    tenant_id: str,
    created_by: int,
    github_integration_id: int,
    default_agent_id: int | None = None,
    repo_owner: str = "octo",
    repo_name: str = "repo",
    webhook_secret_plain: str = "secret",
) -> GitHubChannelInstance:
    encrypted = github_trigger.encrypt_webhook_secret(db, tenant_id, webhook_secret_plain)
    instance = GitHubChannelInstance(
        id=instance_id,
        tenant_id=tenant_id,
        integration_name=f"GitHub {tenant_id}",
        github_integration_id=github_integration_id,
        repo_owner=repo_owner,
        repo_name=repo_name,
        webhook_secret_encrypted=encrypted,
        webhook_secret_preview="secr...cret",
        events=["push"],
        default_agent_id=default_agent_id,
        created_by=created_by,
        is_active=True,
        status="active",
    )
    db.add(instance)
    return instance


def _signed_request(payload: dict, secret: str = "secret"):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    signature = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return _RequestStub(body), f"sha256={signature}"


def test_create_github_trigger_links_integration_and_lists_only_tenant_rows(
    db_session, monkeypatch
):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, contact_id=102, agent_id=202)
    _seed_github_integration(db_session, integration_id=11, tenant_id="tenant-a", name="Tenant A GitHub")
    _seed_github_integration(db_session, integration_id=12, tenant_id="tenant-b", name="Tenant B GitHub")
    db_session.commit()
    monkeypatch.setattr(triggers, "generate_webhook_secret", lambda: "generated-secret-1234")

    created = create_github_trigger(
        payload=GitHubTriggerCreate(
            integration_name="Repo Watcher",
            github_integration_id=11,
            repo_owner=" Octo ",
            repo_name=" repo ",
            events=["push", "pull_request"],
            default_agent_id=201,
        ),
        ctx=_ctx("tenant-a"),
        current_user=SimpleNamespace(id=1),
        db=db_session,
    )
    listed = list_github_triggers(ctx=_ctx("tenant-a"), _user=SimpleNamespace(id=1), db=db_session)
    stored = (
        db_session.query(GitHubChannelInstance)
        .filter(GitHubChannelInstance.tenant_id == "tenant-a")
        .one()
    )

    assert created.integration_name == "Repo Watcher"
    assert created.repo_owner == "Octo"
    assert created.repo_name == "repo"
    assert created.github_integration_id == 11
    assert created.github_integration_name == "Tenant A GitHub"
    assert created.default_agent_name == "Agent tenant-a"
    assert created.webhook_secret_preview == "gene...1234"
    # Per-trigger PAT is gone — no PAT fields exposed in the create response.
    assert not hasattr(created, "pat_token")
    assert not hasattr(created, "pat_token_preview")
    assert not hasattr(created, "has_pat_token")
    assert stored.github_integration_id == 11
    assert stored.webhook_secret_encrypted != "generated-secret-1234"
    assert [row.tenant_id for row in listed] == ["tenant-a"]


def test_create_github_trigger_rejects_foreign_default_agent(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, contact_id=102, agent_id=202)
    _seed_github_integration(db_session, integration_id=11, tenant_id="tenant-a")
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_github_trigger(
            payload=GitHubTriggerCreate(
                integration_name="Repo Watcher",
                github_integration_id=11,
                repo_owner="octo",
                repo_name="repo",
                default_agent_id=202,  # tenant-b's agent
            ),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Agent not found"


def test_create_github_trigger_rejects_foreign_github_integration(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, contact_id=102, agent_id=202)
    _seed_github_integration(db_session, integration_id=12, tenant_id="tenant-b")
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_github_trigger(
            payload=GitHubTriggerCreate(
                integration_name="Repo Watcher",
                github_integration_id=12,  # tenant-b's integration
                repo_owner="octo",
                repo_name="repo",
            ),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    detail = exc_info.value.detail
    assert isinstance(detail, dict)
    assert detail.get("code") == "github_integration_not_found"


def test_create_github_trigger_rejects_missing_github_integration(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_github_trigger(
            payload=GitHubTriggerCreate(
                integration_name="Repo Watcher",
                github_integration_id=99999,
                repo_owner="octo",
                repo_name="repo",
            ),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail.get("code") == "github_integration_not_found"


def test_update_and_delete_github_trigger_are_tenant_scoped(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, contact_id=102, agent_id=202)
    _seed_github_integration(db_session, integration_id=11, tenant_id="tenant-a")
    _seed_github_integration(db_session, integration_id=12, tenant_id="tenant-b")
    trigger_a = _seed_github_trigger(
        db_session,
        instance_id=901,
        tenant_id="tenant-a",
        created_by=1,
        github_integration_id=11,
        default_agent_id=201,
    )
    trigger_b = _seed_github_trigger(
        db_session,
        instance_id=902,
        tenant_id="tenant-b",
        created_by=2,
        github_integration_id=12,
        default_agent_id=202,
    )
    db_session.commit()

    updated = update_github_trigger(
        trigger_id=trigger_a.id,
        payload=GitHubTriggerUpdate(is_active=False, branch_filter="main"),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert updated.is_active is False
    assert updated.status == "paused"
    assert updated.branch_filter == "main"
    # Updates do not expose PAT fields anymore.
    assert not hasattr(updated, "pat_token_preview")

    with pytest.raises(HTTPException) as exc_info:
        delete_github_trigger(
            trigger_id=trigger_b.id,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 404


def test_update_github_trigger_can_relink_integration(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_github_integration(db_session, integration_id=11, tenant_id="tenant-a", name="GitHub Prod")
    _seed_github_integration(db_session, integration_id=13, tenant_id="tenant-a", name="GitHub Staging")
    trigger = _seed_github_trigger(
        db_session,
        instance_id=901,
        tenant_id="tenant-a",
        created_by=1,
        github_integration_id=11,
        default_agent_id=201,
    )
    db_session.commit()

    updated = update_github_trigger(
        trigger_id=trigger.id,
        payload=GitHubTriggerUpdate(github_integration_id=13),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert updated.github_integration_id == 13
    assert updated.github_integration_name == "GitHub Staging"


def test_signed_github_inbound_filters_and_dispatches(db_session, monkeypatch):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_github_integration(db_session, integration_id=11, tenant_id="tenant-a")
    trigger = _seed_github_trigger(
        db_session,
        instance_id=901,
        tenant_id="tenant-a",
        created_by=1,
        github_integration_id=11,
        default_agent_id=201,
    )
    trigger.branch_filter = "main"
    trigger.path_filters = ["src/*"]
    trigger.author_filter = "octocat"
    db_session.commit()
    captured: dict = {}

    class FakeDispatchService:
        def __init__(self, db):
            self.db = db

        def dispatch(self, event):
            captured["event"] = event
            return SimpleNamespace(
                status="dispatched", wake_event_id=77, continuous_run_ids=[88]
            )

    monkeypatch.setattr(inbound, "TriggerDispatchService", FakeDispatchService)
    payload = {
        "ref": "refs/heads/main",
        "repository": {"name": "repo", "owner": {"login": "octo"}, "full_name": "octo/repo"},
        "sender": {"login": "octocat"},
        "commits": [
            {
                "added": ["src/app.py"],
                "modified": [],
                "removed": [],
                "author": {"username": "octocat"},
            }
        ],
    }
    request, signature = _signed_request(payload)

    response = asyncio.run(
        inbound.receive_github_webhook(
            trigger_id=trigger.id,
            request=request,
            x_hub_signature_256=signature,
            x_github_event="push",
            x_github_delivery="delivery-1",
            db=db_session,
        )
    )

    event = captured["event"]
    assert response == {
        "status": "accepted",
        "delivery_id": "delivery-1",
        "wake_event_id": 77,
        "continuous_run_ids": [88],
    }
    assert event.trigger_type == "github"
    assert event.instance_id == trigger.id
    assert event.event_type == "github.push"
    assert event.dedupe_key == "delivery-1"
    assert event.payload["changed_paths"] == ["src/app.py"]
    assert event.sender_key == "github_901_octocat"
    refreshed = db_session.query(GitHubChannelInstance).filter_by(id=trigger.id).one()
    assert refreshed.last_delivery_id == "delivery-1"


def test_signed_github_inbound_rejects_bad_signature_and_ignores_filter_misses(
    db_session, monkeypatch
):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_github_integration(db_session, integration_id=11, tenant_id="tenant-a")
    trigger = _seed_github_trigger(
        db_session,
        instance_id=901,
        tenant_id="tenant-a",
        created_by=1,
        github_integration_id=11,
        default_agent_id=201,
    )
    trigger.branch_filter = "main"
    db_session.commit()
    payload = {
        "ref": "refs/heads/dev",
        "repository": {"name": "repo", "owner": {"login": "octo"}, "full_name": "octo/repo"},
        "sender": {"login": "octocat"},
        "commits": [],
    }
    request, _signature = _signed_request(payload)

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            inbound.receive_github_webhook(
                trigger_id=trigger.id,
                request=request,
                x_hub_signature_256="sha256=bad",
                x_github_event="push",
                x_github_delivery="delivery-bad",
                db=db_session,
            )
        )
    assert exc_info.value.status_code == 403

    class ShouldNotDispatch:
        def __init__(self, db):
            self.db = db

        def dispatch(self, event):
            raise AssertionError("filtered GitHub delivery must not dispatch")

    monkeypatch.setattr(inbound, "TriggerDispatchService", ShouldNotDispatch)
    request, signature = _signed_request(payload)
    response = asyncio.run(
        inbound.receive_github_webhook(
            trigger_id=trigger.id,
            request=request,
            x_hub_signature_256=signature,
            x_github_event="push",
            x_github_delivery="delivery-filtered",
            db=db_session,
        )
    )

    assert response.status_code == 204
