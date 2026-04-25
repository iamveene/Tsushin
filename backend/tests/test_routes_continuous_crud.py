"""CRUD tests for continuous-agent and continuous-subscription routes."""

from __future__ import annotations

import os
import sys
import types
from datetime import datetime

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

from api.routes_continuous import (  # noqa: E402
    ContinuousAgentCreate,
    ContinuousAgentUpdate,
    ContinuousCaller,
    ContinuousSubscriptionCreate,
    ContinuousSubscriptionUpdate,
    create_continuous_agent,
    create_continuous_subscription,
    delete_continuous_agent,
    delete_continuous_subscription,
    list_continuous_subscriptions,
    update_continuous_agent,
    update_continuous_subscription,
)
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
    GitHubChannelInstance,
    JiraChannelInstance,
    ScheduleChannelInstance,
    SentinelProfile,
    WakeEvent,
    WebhookIntegration,
    WhatsAppMCPInstance,
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
            SentinelProfile.__table__,
            DeliveryPolicy.__table__,
            BudgetPolicy.__table__,
            ContinuousAgent.__table__,
            ContinuousSubscription.__table__,
            WakeEvent.__table__,
            ContinuousRun.__table__,
            EmailChannelInstance.__table__,
            JiraChannelInstance.__table__,
            ScheduleChannelInstance.__table__,
            GitHubChannelInstance.__table__,
            WebhookIntegration.__table__,
            WhatsAppMCPInstance.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_tenant(db, *, tenant_id: str, user_id: int = 1, agent_id: int = 1, contact_id: int = 1):
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
    db.commit()


def _caller(tenant_id: str, user_id: int = 1) -> ContinuousCaller:
    return ContinuousCaller(tenant_id=tenant_id, user_id=user_id)


def _seed_schedule_instance(db, *, tenant_id: str, user_id: int = 1, instance_id: int = 100):
    instance = ScheduleChannelInstance(
        id=instance_id,
        tenant_id=tenant_id,
        integration_name=f"sched-{instance_id}",
        cron_expression="0 9 * * *",
        timezone="UTC",
        is_active=True,
        status="active",
        created_by=user_id,
    )
    db.add(instance)
    db.commit()
    return instance


# --- Agent CRUD ---


def test_create_continuous_agent_happy_path(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    payload = ContinuousAgentCreate(agent_id=1, name="Watcher", execution_mode="hybrid")
    out = create_continuous_agent(payload, caller=_caller("acme"), db=db_session)
    assert out.id is not None
    assert out.tenant_id == "acme"
    assert out.is_system_owned is False
    assert out.status == "active"
    assert out.execution_mode == "hybrid"
    assert out.subscription_count == 0


def test_create_continuous_agent_cross_tenant_agent_id(db_session):
    _seed_tenant(db_session, tenant_id="acme", user_id=1, agent_id=1, contact_id=1)
    _seed_tenant(db_session, tenant_id="other", user_id=2, agent_id=2, contact_id=2)
    payload = ContinuousAgentCreate(agent_id=2, name="X", execution_mode="hybrid")
    with pytest.raises(HTTPException) as exc:
        create_continuous_agent(payload, caller=_caller("acme"), db=db_session)
    assert exc.value.status_code == 403


def test_create_invalid_execution_mode_rejected(db_session):
    with pytest.raises(ValueError):
        ContinuousAgentCreate(agent_id=1, execution_mode="bogus")


def test_create_status_error_rejected(db_session):
    with pytest.raises(ValueError):
        ContinuousAgentCreate(agent_id=1, status="error")


def test_patch_partial_update(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    created = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    out = update_continuous_agent(
        created.id,
        ContinuousAgentUpdate(name="B"),
        caller=_caller("acme"),
        db=db_session,
    )
    assert out.name == "B"
    assert out.execution_mode == "hybrid"


def test_patch_system_owned_disable_blocked(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    row = ContinuousAgent(
        tenant_id="acme",
        agent_id=1,
        execution_mode="hybrid",
        status="active",
        is_system_owned=True,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    with pytest.raises(HTTPException) as exc:
        update_continuous_agent(
            row.id,
            ContinuousAgentUpdate(status="disabled"),
            caller=_caller("acme"),
            db=db_session,
        )
    assert exc.value.status_code == 403


def test_delete_happy_path(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    created = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    delete_continuous_agent(created.id, force=False, caller=_caller("acme"), db=db_session)
    remaining = db_session.query(ContinuousAgent).filter(ContinuousAgent.id == created.id).first()
    assert remaining is None


def test_delete_system_owned_blocked(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    row = ContinuousAgent(
        tenant_id="acme",
        agent_id=1,
        execution_mode="hybrid",
        status="active",
        is_system_owned=True,
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)
    with pytest.raises(HTTPException) as exc:
        delete_continuous_agent(row.id, force=False, caller=_caller("acme"), db=db_session)
    assert exc.value.status_code == 403


def test_delete_pending_wake_events_409(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    created = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    db_session.add(
        WakeEvent(
            tenant_id="acme",
            continuous_agent_id=created.id,
            channel_type="schedule",
            channel_instance_id=1,
            event_type="tick",
            occurred_at=datetime.utcnow(),
            dedupe_key="k1",
            status="pending",
        )
    )
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        delete_continuous_agent(created.id, force=False, caller=_caller("acme"), db=db_session)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "agent_has_pending_wake_events"
    assert exc.value.detail["count"] == 1


def test_delete_pending_wake_events_force(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    created = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    db_session.add(
        WakeEvent(
            tenant_id="acme",
            continuous_agent_id=created.id,
            channel_type="schedule",
            channel_instance_id=1,
            event_type="tick",
            occurred_at=datetime.utcnow(),
            dedupe_key="k1",
            status="pending",
        )
    )
    db_session.commit()
    delete_continuous_agent(created.id, force=True, caller=_caller("acme"), db=db_session)
    leftover = db_session.query(WakeEvent).filter(WakeEvent.dedupe_key == "k1").first()
    assert leftover is not None
    assert leftover.status == "filtered"
    assert leftover.continuous_agent_id is None


# --- Subscription CRUD ---


def test_subscription_create_happy_path(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    _seed_schedule_instance(db_session, tenant_id="acme", instance_id=200)
    created_agent = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    out = create_continuous_subscription(
        created_agent.id,
        ContinuousSubscriptionCreate(channel_type="schedule", channel_instance_id=200, event_type="tick"),
        caller=_caller("acme"),
        db=db_session,
    )
    assert out.id is not None
    assert out.continuous_agent_id == created_agent.id
    assert out.channel_type == "schedule"
    assert out.is_system_owned is False


def test_subscription_create_dedupe_409(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    _seed_schedule_instance(db_session, tenant_id="acme", instance_id=200)
    created_agent = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    payload = ContinuousSubscriptionCreate(channel_type="schedule", channel_instance_id=200, event_type="tick")
    create_continuous_subscription(created_agent.id, payload, caller=_caller("acme"), db=db_session)
    with pytest.raises(HTTPException) as exc:
        create_continuous_subscription(created_agent.id, payload, caller=_caller("acme"), db=db_session)
    assert exc.value.status_code == 409
    assert exc.value.detail == "subscription_already_exists"


def test_subscription_create_unsupported_channel_type(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    created_agent = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    with pytest.raises(HTTPException) as exc:
        create_continuous_subscription(
            created_agent.id,
            ContinuousSubscriptionCreate(channel_type="bogus", channel_instance_id=99),
            caller=_caller("acme"),
            db=db_session,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "unsupported_channel_type"


def test_subscription_create_missing_channel_instance(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    created_agent = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    with pytest.raises(HTTPException) as exc:
        create_continuous_subscription(
            created_agent.id,
            ContinuousSubscriptionCreate(channel_type="schedule", channel_instance_id=9999),
            caller=_caller("acme"),
            db=db_session,
        )
    assert exc.value.status_code == 400
    assert exc.value.detail == "channel_instance_not_found"


def test_subscription_delete_system_owned_blocked(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    _seed_schedule_instance(db_session, tenant_id="acme", instance_id=200)
    parent = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    sub = ContinuousSubscription(
        tenant_id="acme",
        continuous_agent_id=parent.id,
        channel_type="schedule",
        channel_instance_id=200,
        event_type="tick",
        status="active",
        is_system_owned=True,
    )
    db_session.add(sub)
    db_session.commit()
    db_session.refresh(sub)
    with pytest.raises(HTTPException) as exc:
        delete_continuous_subscription(parent.id, sub.id, caller=_caller("acme"), db=db_session)
    assert exc.value.status_code == 403


def test_subscription_list_returns_paginated(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    _seed_schedule_instance(db_session, tenant_id="acme", instance_id=200)
    _seed_schedule_instance(db_session, tenant_id="acme", user_id=1, instance_id=201)
    parent = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    create_continuous_subscription(
        parent.id,
        ContinuousSubscriptionCreate(channel_type="schedule", channel_instance_id=200, event_type="a"),
        caller=_caller("acme"),
        db=db_session,
    )
    create_continuous_subscription(
        parent.id,
        ContinuousSubscriptionCreate(channel_type="schedule", channel_instance_id=201, event_type="b"),
        caller=_caller("acme"),
        db=db_session,
    )
    page = list_continuous_subscriptions(parent.id, limit=50, offset=0, caller=_caller("acme"), db=db_session)
    assert page.total == 2
    assert len(page.items) == 2


def test_subscription_update_changes_status(db_session):
    _seed_tenant(db_session, tenant_id="acme")
    _seed_schedule_instance(db_session, tenant_id="acme", instance_id=200)
    parent = create_continuous_agent(
        ContinuousAgentCreate(agent_id=1, name="A", execution_mode="hybrid"),
        caller=_caller("acme"),
        db=db_session,
    )
    created = create_continuous_subscription(
        parent.id,
        ContinuousSubscriptionCreate(channel_type="schedule", channel_instance_id=200, event_type="a"),
        caller=_caller("acme"),
        db=db_session,
    )
    out = update_continuous_subscription(
        parent.id,
        created.id,
        ContinuousSubscriptionUpdate(status="paused"),
        caller=_caller("acme"),
        db=db_session,
    )
    assert out.status == "paused"
