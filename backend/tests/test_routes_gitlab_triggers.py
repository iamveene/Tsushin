"""GitLab trigger route and inbound webhook tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api import routes_gitlab_inbound as inbound  # noqa: E402
from api.routes_gitlab_triggers import (  # noqa: E402
    GitLabCriteriaTestRequest,
    GitLabTriggerCreate,
    GitLabTriggerUpdate,
    create_gitlab_trigger,
    dry_run_gitlab_criteria_unsaved,
    list_gitlab_triggers,
    rotate_gitlab_trigger_secret,
    update_gitlab_trigger,
)
from api import routes_gitlab_triggers as triggers  # noqa: E402
from channels.gitlab import trigger as gitlab_trigger  # noqa: E402
from models import (  # noqa: E402
    Agent,
    Base,
    Contact,
    FlowTriggerBinding,
    GitLabChannelInstance,
    GitLabIntegration,
    HubIntegration,
)
from models_rbac import Tenant, User  # noqa: E402


TEST_MASTER_KEY = "gitlab-test-master-key"


class _RequestStub:
    def __init__(self, body: bytes):
        self._body = body

    async def body(self) -> bytes:
        return self._body


@pytest.fixture
def db_session(monkeypatch):
    from config import feature_flags
    from services import encryption_key_service

    monkeypatch.setattr(encryption_key_service, "get_api_key_encryption_key", lambda db: TEST_MASTER_KEY)
    monkeypatch.setattr(encryption_key_service, "get_webhook_encryption_key", lambda db: TEST_MASTER_KEY)
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
            GitLabIntegration.__table__,
            GitLabChannelInstance.__table__,
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


def _seed_gitlab_integration(
    db,
    *,
    integration_id: int,
    tenant_id: str,
    name: str = "GitLab Production",
) -> GitLabIntegration:
    integration = GitLabIntegration(
        id=integration_id,
        tenant_id=tenant_id,
        type="gitlab",
        name=name,
        display_name=name,
        provider="gitlab",
        auth_method="pat",
        provider_mode="programmatic",
        is_active=True,
    )
    db.add(integration)
    return integration


def _seed_gitlab_trigger(
    db,
    *,
    instance_id: int,
    tenant_id: str,
    created_by: int,
    gitlab_integration_id: int,
    default_agent_id: int | None = None,
    project_path: str = "group/project",
    webhook_secret_plain: str = "secret-token",
) -> GitLabChannelInstance:
    encrypted = gitlab_trigger.encrypt_webhook_secret(db, tenant_id, webhook_secret_plain)
    instance = GitLabChannelInstance(
        id=instance_id,
        tenant_id=tenant_id,
        integration_name=f"GitLab {tenant_id}",
        gitlab_integration_id=gitlab_integration_id,
        project_path=project_path,
        webhook_secret_encrypted=encrypted,
        webhook_secret_preview="secr...oken",
        events=["push"],
        branch_filter="main",
        path_filters=["src/**"],
        author_filter="alice",
        default_agent_id=default_agent_id,
        created_by=created_by,
        is_active=True,
        status="active",
    )
    db.add(instance)
    return instance


def _gitlab_request(payload: dict):
    body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return _RequestStub(body)


def test_create_gitlab_trigger_links_integration_and_lists_only_tenant_rows(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, contact_id=102, agent_id=202)
    _seed_gitlab_integration(db_session, integration_id=21, tenant_id="tenant-a", name="Tenant A GitLab")
    _seed_gitlab_integration(db_session, integration_id=22, tenant_id="tenant-b", name="Tenant B GitLab")
    db_session.commit()

    created = create_gitlab_trigger(
        payload=GitLabTriggerCreate(
            integration_name="Repo Watch",
            gitlab_integration_id=21,
            project_path="group/project",
            webhook_secret="secret-token",
            events=["Push Hook", "Merge Request Hook"],
            default_agent_id=201,
        ),
        ctx=_ctx("tenant-a"),
        current_user=SimpleNamespace(id=1),
        db=db_session,
    )

    listed = list_gitlab_triggers(ctx=_ctx("tenant-a"), _user=SimpleNamespace(id=1), db=db_session)
    assert [item.id for item in listed] == [created.id]
    assert created.gitlab_integration_id == 21
    assert created.gitlab_integration_name == "Tenant A GitLab"
    assert created.project_path == "group/project"
    assert created.events == ["push", "merge_request"]
    assert created.inbound_url == f"/api/triggers/gitlab/{created.id}/inbound"

    stored = db_session.query(GitLabChannelInstance).filter(GitLabChannelInstance.id == created.id).one()
    assert stored.gitlab_integration_id == 21
    assert stored.webhook_secret_encrypted != "secret-token"

    with pytest.raises(HTTPException) as exc_info:
        create_gitlab_trigger(
            payload=GitLabTriggerCreate(
                integration_name="Foreign",
                gitlab_integration_id=22,
                project_path="group/project",
            ),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 404
    assert "GitLab integration not found" in exc_info.value.detail


def test_update_gitlab_trigger_relinks_integration_and_normalizes_filters(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_gitlab_integration(db_session, integration_id=21, tenant_id="tenant-a", name="GitLab Prod")
    _seed_gitlab_integration(db_session, integration_id=23, tenant_id="tenant-a", name="GitLab Staging")
    trigger = _seed_gitlab_trigger(
        db_session,
        instance_id=901,
        tenant_id="tenant-a",
        created_by=1,
        gitlab_integration_id=21,
    )
    db_session.commit()

    updated = update_gitlab_trigger(
        trigger.id,
        payload=GitLabTriggerUpdate(
            gitlab_integration_id=23,
            project_path="/new-group/new-project/",
            path_filters=["backend/**", "backend/**", ""],
            author_filter=" bob ",
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert updated.gitlab_integration_id == 23
    assert updated.gitlab_integration_name == "GitLab Staging"
    assert updated.project_path == "new-group/new-project"
    assert updated.path_filters == ["backend/**"]
    assert updated.author_filter == "bob"


def test_rotate_gitlab_trigger_secret_is_tenant_scoped(db_session, monkeypatch):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, contact_id=102, agent_id=202)
    _seed_gitlab_integration(db_session, integration_id=21, tenant_id="tenant-a")
    _seed_gitlab_integration(db_session, integration_id=22, tenant_id="tenant-b")
    trigger_a = _seed_gitlab_trigger(
        db_session,
        instance_id=901,
        tenant_id="tenant-a",
        created_by=1,
        gitlab_integration_id=21,
        default_agent_id=201,
        webhook_secret_plain="old-secret-token",
    )
    trigger_b = _seed_gitlab_trigger(
        db_session,
        instance_id=902,
        tenant_id="tenant-b",
        created_by=2,
        gitlab_integration_id=22,
        default_agent_id=202,
    )
    db_session.commit()
    old_encrypted = trigger_a.webhook_secret_encrypted
    monkeypatch.setattr(triggers, "generate_webhook_secret", lambda: "rotated-token-5678")

    rotated = rotate_gitlab_trigger_secret(
        trigger_id=trigger_a.id,
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert rotated.webhook_secret_once == "rotated-token-5678"
    assert rotated.webhook_secret_preview == "rota...5678"
    assert "not be shown again" in rotated.warning
    refreshed = db_session.query(GitLabChannelInstance).filter_by(id=trigger_a.id).one()
    assert refreshed.webhook_secret_preview == "rota...5678"
    assert refreshed.webhook_secret_encrypted != old_encrypted
    assert refreshed.webhook_secret_encrypted != "rotated-token-5678"

    with pytest.raises(HTTPException) as exc_info:
        rotate_gitlab_trigger_secret(
            trigger_id=trigger_b.id,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 404


def test_signed_gitlab_inbound_filters_and_dispatches(db_session, monkeypatch):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_gitlab_integration(db_session, integration_id=21, tenant_id="tenant-a")
    trigger = _seed_gitlab_trigger(
        db_session,
        instance_id=901,
        tenant_id="tenant-a",
        created_by=1,
        gitlab_integration_id=21,
        default_agent_id=201,
    )
    db_session.commit()

    captured = {}

    class FakeDispatchService:
        def __init__(self, db):
            self.db = db

        def dispatch(self, event):
            captured["event"] = event
            return SimpleNamespace(
                status="dispatched",
                wake_event_id=55,
                continuous_run_ids=[77],
                team_run_ids=[88],
            )

    monkeypatch.setattr(inbound, "TriggerDispatchService", FakeDispatchService)
    payload = {
        "object_kind": "push",
        "project": {"path_with_namespace": "group/project"},
        "ref": "refs/heads/main",
        "user_username": "alice",
        "commits": [{"added": ["src/app.py"], "modified": [], "removed": []}],
    }

    response = asyncio.run(
        inbound.receive_gitlab_webhook(
            trigger.id,
            request=_gitlab_request(payload),
            x_gitlab_token="secret-token",
            x_gitlab_event="Push Hook",
            x_gitlab_event_uuid="delivery-1",
            db=db_session,
        )
    )

    event = captured["event"]
    assert response["status"] == "accepted"
    assert response["delivery_id"] == "delivery-1"
    assert event.trigger_type == "gitlab"
    assert event.instance_id == trigger.id
    assert event.event_type == "gitlab.push"
    assert event.dedupe_key == "delivery-1"
    assert event.sender_key == "gitlab_901_alice"
    assert event.payload["project"]["path"] == "group/project"
    assert event.payload["repository"]["full_name"] == "group/project"

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(
            inbound.receive_gitlab_webhook(
                trigger.id,
                request=_gitlab_request(payload),
                x_gitlab_token="wrong",
                x_gitlab_event="Push Hook",
                x_gitlab_event_uuid="delivery-bad",
                db=db_session,
            )
        )
    assert exc_info.value.status_code == 403


def test_gitlab_repository_criteria_dry_run():
    payload = {
        "provider": "gitlab",
        "provider_event": "merge_request",
        "action": "open",
        "target_branch": "main",
        "actor": {"username": "alice"},
        "object": {
            "title": "Add billing export",
            "body": "Touches the billing report.",
        },
    }

    response = dry_run_gitlab_criteria_unsaved(
        payload=GitLabCriteriaTestRequest(
            criteria={
                "criteria_version": 1,
                "event": "pull_request",
                "actions": ["open"],
                "filters": {
                    "target_branch_filter": "main",
                    "author_filter": "alice",
                    "title_contains": "billing",
                },
            },
            payload=payload,
            provider_event="merge_request",
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=SimpleNamespace(),
    )
    assert response.matched is True
    assert response.reason == "matched"
