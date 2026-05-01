"""Flow trigger binding route contract tests."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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

from api.routes_flow_trigger_bindings import (  # noqa: E402
    FlowTriggerBindingCreate,
    create_binding,
)
from flows.flow_engine import FlowEngine  # noqa: E402
from models import (  # noqa: E402
    Base,
    EmailChannelInstance,
    FlowDefinition,
    FlowNode,
    FlowNodeRun,
    FlowRun,
    FlowTriggerBinding,
    GitHubChannelInstance,
    JiraChannelInstance,
    WebhookIntegration,
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
            FlowDefinition.__table__,
            FlowNode.__table__,
            FlowNodeRun.__table__,
            FlowRun.__table__,
            FlowTriggerBinding.__table__,
            EmailChannelInstance.__table__,
            JiraChannelInstance.__table__,
            GitHubChannelInstance.__table__,
            WebhookIntegration.__table__,
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


def _seed_tenant(db, tenant_id: str, user_id: int):
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


def _seed_flow_and_email(db, *, tenant_id: str, user_id: int, flow_id: int, trigger_id: int):
    db.add(
        FlowDefinition(
            id=flow_id,
            tenant_id=tenant_id,
            name=f"{tenant_id} flow",
            execution_method="triggered",
        )
    )
    db.add(
        EmailChannelInstance(
            id=trigger_id,
            tenant_id=tenant_id,
            integration_name=f"{tenant_id} email",
            provider="gmail",
            created_by=user_id,
        )
    )
    db.commit()


def test_create_binding_validates_tenant_owned_trigger(db_session):
    _seed_tenant(db_session, "acme", 1)
    _seed_tenant(db_session, "other", 2)
    _seed_flow_and_email(db_session, tenant_id="acme", user_id=1, flow_id=10, trigger_id=20)
    _seed_flow_and_email(db_session, tenant_id="other", user_id=2, flow_id=11, trigger_id=21)

    created = create_binding(
        FlowTriggerBindingCreate(
            flow_definition_id=10,
            trigger_kind="email",
            trigger_instance_id=20,
        ),
        db=db_session,
        ctx=_ctx("acme"),
    )
    assert created.trigger_kind == "email"
    assert created.trigger_instance_id == 20

    with pytest.raises(HTTPException) as exc:
        create_binding(
            FlowTriggerBindingCreate(
                flow_definition_id=10,
                trigger_kind="email",
                trigger_instance_id=21,
            ),
            db=db_session,
            ctx=_ctx("acme"),
        )
    assert exc.value.status_code == 403
    assert exc.value.detail == "email trigger not owned by tenant"


def test_schedule_binding_kind_is_not_accepted():
    with pytest.raises(ValidationError):
        FlowTriggerBindingCreate(
            flow_definition_id=10,
            trigger_kind="schedule",
            trigger_instance_id=20,
        )


def _seed_trigger(db, trigger_kind: str, *, trigger_id: int = 301):
    if trigger_kind == "email":
        trigger = EmailChannelInstance(
            id=trigger_id,
            tenant_id="tenant-a",
            integration_name="Inbox Watcher",
            provider="gmail",
            created_by=1,
        )
    elif trigger_kind == "jira":
        trigger = JiraChannelInstance(
            id=trigger_id,
            tenant_id="tenant-a",
            integration_name="Jira Watcher",
            site_url="https://example.atlassian.net",
            jql="project = HELP",
            created_by=1,
        )
    elif trigger_kind == "github":
        trigger = GitHubChannelInstance(
            id=trigger_id,
            tenant_id="tenant-a",
            integration_name="GitHub Watcher",
            github_integration_id=901,
            repo_owner="acme",
            repo_name="widget",
            created_by=1,
        )
    elif trigger_kind == "webhook":
        trigger = WebhookIntegration(
            id=trigger_id,
            tenant_id="tenant-a",
            integration_name="Webhook Watcher",
            slug=f"webhook-{trigger_id}",
            api_secret_encrypted="encrypted",
            api_secret_preview="whsec_xxx",
            created_by=1,
        )
    else:
        raise AssertionError(f"Unsupported trigger kind: {trigger_kind}")

    db.add(trigger)
    db.commit()
    return trigger


@pytest.mark.parametrize("trigger_kind", ["email", "jira", "github", "webhook"])
def test_generated_trigger_flow_continues_conversation_failure_when_notification_configured(
    db_session,
    trigger_kind,
):
    """BUG-726: notification-enabled generated flows must keep Notification reachable."""
    from services.flow_binding_service import ensure_system_managed_flow_for_trigger

    _seed_tenant(db_session, "tenant-a", 1)
    db_session.commit()
    trigger = _seed_trigger(db_session, trigger_kind)

    flow, _binding, created = ensure_system_managed_flow_for_trigger(
        db_session,
        tenant_id="tenant-a",
        trigger_kind=trigger_kind,
        trigger_instance_id=trigger.id,
        default_agent_id=201,
        notification_recipient="+15551234567",
        notification_enabled=True,
    )

    assert created is True
    nodes = (
        db_session.query(FlowNode)
        .filter(FlowNode.flow_definition_id == flow.id)
        .order_by(FlowNode.position)
        .all()
    )
    assert [node.type for node in nodes] == ["source", "gate", "conversation", "notification"]

    conversation = nodes[2]
    notification = nodes[3]
    assert conversation.on_failure == "continue"
    notification_config = json.loads(notification.config_json)
    assert notification_config["enabled"] is True
    assert notification_config["recipient"] == "+15551234567"


def test_enabling_auto_flow_notification_repairs_existing_conversation_failure_contract(db_session):
    """BUG-726: toggling notification on later must repair old generated flows too."""
    from services.flow_binding_service import (
        ensure_system_managed_flow_for_trigger,
        update_auto_flow_notification,
    )

    _seed_tenant(db_session, "tenant-a", 1)
    db_session.commit()
    trigger = _seed_trigger(db_session, "email")
    flow, _binding, _created = ensure_system_managed_flow_for_trigger(
        db_session,
        tenant_id="tenant-a",
        trigger_kind="email",
        trigger_instance_id=trigger.id,
        default_agent_id=201,
        notification_enabled=False,
    )

    conversation = (
        db_session.query(FlowNode)
        .filter(FlowNode.flow_definition_id == flow.id, FlowNode.type == "conversation")
        .one()
    )
    assert conversation.on_failure is None

    result = update_auto_flow_notification(
        db_session,
        tenant_id="tenant-a",
        trigger_kind="email",
        trigger_instance_id=trigger.id,
        enabled=True,
        recipient_phone="+15551234567",
    )

    db_session.flush()
    db_session.refresh(conversation)
    assert result["enabled"] is True
    assert conversation.on_failure == "continue"


def test_generated_trigger_flow_reaches_notification_after_conversation_failure(db_session):
    """BUG-726 runtime proof: a generated conversation failure does not stop notification."""
    from services.flow_binding_service import ensure_system_managed_flow_for_trigger

    _seed_tenant(db_session, "tenant-a", 1)
    db_session.commit()
    trigger = _seed_trigger(db_session, "email")
    flow, _binding, _created = ensure_system_managed_flow_for_trigger(
        db_session,
        tenant_id="tenant-a",
        trigger_kind="email",
        trigger_instance_id=trigger.id,
        default_agent_id=201,
        notification_recipient="+15551234567",
        notification_enabled=True,
    )
    db_session.commit()

    token_tracker = MagicMock()
    token_tracker.track_request = AsyncMock(return_value=None)
    with patch.object(FlowEngine, "_cleanup_stale_runs", return_value=0):
        engine = FlowEngine(db=db_session, token_tracker=token_tracker)

    async def fail_conversation(step, input_data, flow_run, step_run):
        return {
            "status": "failed",
            "recipient": "",
            "error": "Could not resolve recipient '' to a phone number",
        }

    notification_calls = []

    async def complete_notification(step, input_data, flow_run, step_run):
        notification_calls.append(step.id)
        return {"status": "completed", "recipient": "+15551234567"}

    engine.handlers["conversation"].execute = fail_conversation  # type: ignore[assignment]
    engine.handlers["notification"].execute = complete_notification  # type: ignore[assignment]

    flow_run = asyncio.run(
        engine.run_flow(
            flow_definition_id=flow.id,
            trigger_context={
                "source": {
                    "trigger_kind": "email",
                    "instance_id": trigger.id,
                    "payload": {"subject": "Build report"},
                }
            },
            initiator="system",
            trigger_type="triggered",
            tenant_id="tenant-a",
        )
    )

    step_runs = (
        db_session.query(FlowNodeRun)
        .join(FlowNode, FlowNodeRun.flow_node_id == FlowNode.id)
        .filter(FlowNodeRun.flow_run_id == flow_run.id)
        .order_by(FlowNode.position)
        .all()
    )

    assert notification_calls
    assert [run.step.type for run in step_runs] == ["source", "gate", "conversation", "notification"]
    assert [run.status for run in step_runs] == ["completed", "completed", "failed", "completed"]
    assert flow_run.status == "completed_with_errors"
    assert flow_run.failed_steps == 1
    assert flow_run.completed_steps == 3
