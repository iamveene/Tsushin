from __future__ import annotations

import json
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

from api.routes_schedule_triggers import (  # noqa: E402
    ScheduleTriggerCreate,
    ScheduleTriggerPreviewRequest,
    ScheduleTriggerUpdate,
    create_schedule_trigger,
    delete_schedule_trigger,
    list_schedule_triggers,
    preview_schedule_trigger,
    update_schedule_trigger,
)
import channels.schedule.trigger as schedule_trigger_module  # noqa: E402
from channels.schedule.trigger import ScheduleTrigger  # noqa: E402
from models import (  # noqa: E402
    Agent,
    Base,
    BudgetPolicy,
    ChannelEventDedupe,
    Contact,
    ContinuousAgent,
    ContinuousRun,
    ContinuousSubscription,
    DeliveryPolicy,
    ScheduleChannelInstance,
    SentinelProfile,
    WakeEvent,
)
from models_rbac import Tenant, User  # noqa: E402
from services.trigger_dispatch_service import TriggerDispatchService  # noqa: E402


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
            ScheduleChannelInstance.__table__,
            SentinelProfile.__table__,
            DeliveryPolicy.__table__,
            BudgetPolicy.__table__,
            ContinuousAgent.__table__,
            ContinuousSubscription.__table__,
            WakeEvent.__table__,
            ContinuousRun.__table__,
            ChannelEventDedupe.__table__,
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


def _seed_tenant_user_agent(db, *, tenant_id: str, user_id: int, contact_id: int, agent_id: int):
    db.add(Tenant(id=tenant_id, name=tenant_id.title(), slug=tenant_id))
    _seed_user(db, user_id=user_id, tenant_id=tenant_id, email=f"{tenant_id}@example.com")
    _seed_contact(db, contact_id=contact_id, tenant_id=tenant_id, friendly_name=f"Agent {tenant_id}")
    _seed_agent(db, agent_id=agent_id, tenant_id=tenant_id, contact_id=contact_id)


def _seed_continuous_agent(db, *, continuous_agent_id: int, tenant_id: str, agent_id: int):
    continuous_agent = ContinuousAgent(
        id=continuous_agent_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        name=f"CA {tenant_id}",
        execution_mode="hybrid",
        status="active",
    )
    db.add(continuous_agent)
    return continuous_agent


def _seed_subscription(db, *, subscription_id: int, tenant_id: str, continuous_agent_id: int, instance_id: int):
    subscription = ContinuousSubscription(
        id=subscription_id,
        tenant_id=tenant_id,
        continuous_agent_id=continuous_agent_id,
        channel_type="schedule",
        channel_instance_id=instance_id,
        event_type="schedule.fire",
        status="active",
    )
    db.add(subscription)
    return subscription


def test_preview_schedule_trigger_returns_next_five_utc_times(db_session):
    db_session.add(Tenant(id="tenant-a", name="Tenant A", slug="tenant-a"))
    db_session.commit()

    preview = preview_schedule_trigger(
        payload=ScheduleTriggerPreviewRequest(
            cron_expression="*/15 * * * *",
            timezone="UTC",
            base_time=datetime(2026, 1, 2, 3, 4, 0),
        ),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    assert preview.next_fire_preview == [
        datetime(2026, 1, 2, 3, 15),
        datetime(2026, 1, 2, 3, 30),
        datetime(2026, 1, 2, 3, 45),
        datetime(2026, 1, 2, 4, 0),
        datetime(2026, 1, 2, 4, 15),
    ]


def test_create_schedule_trigger_persists_and_lists(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    db_session.commit()

    created = create_schedule_trigger(
        payload=ScheduleTriggerCreate(
            integration_name="Daily Brief",
            cron_expression="0 9 * * *",
            timezone="UTC",
            payload_template={"kind": "brief"},
            default_agent_id=201,
        ),
        ctx=_ctx("tenant-a"),
        current_user=SimpleNamespace(id=1),
        db=db_session,
    )
    listed = list_schedule_triggers(ctx=_ctx("tenant-a"), _user=SimpleNamespace(id=1), db=db_session)

    assert created.integration_name == "Daily Brief"
    assert created.default_agent_name == "Agent tenant-a"
    assert created.next_fire_at is not None
    assert len(created.next_fire_preview) == 5
    assert [row.integration_name for row in listed] == ["Daily Brief"]


def test_create_schedule_trigger_rejects_foreign_default_agent(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, contact_id=102, agent_id=202)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_schedule_trigger(
            payload=ScheduleTriggerCreate(
                integration_name="Daily Brief",
                cron_expression="0 9 * * *",
                timezone="UTC",
                default_agent_id=202,
            ),
            ctx=_ctx("tenant-a"),
            current_user=SimpleNamespace(id=1),
            db=db_session,
        )

    assert exc_info.value.status_code == 404
    assert exc_info.value.detail == "Agent not found"


def test_update_schedule_trigger_can_pause_existing_row(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    trigger = ScheduleChannelInstance(
        tenant_id="tenant-a",
        integration_name="Daily Brief",
        cron_expression="0 9 * * *",
        timezone="UTC",
        default_agent_id=201,
        next_fire_at=datetime(2026, 1, 2, 9),
        created_by=1,
    )
    db_session.add(trigger)
    db_session.commit()

    updated = update_schedule_trigger(
        trigger_id=trigger.id,
        payload=ScheduleTriggerUpdate(is_active=False, payload_template={"paused": True}),
        ctx=_ctx("tenant-a"),
        _user=SimpleNamespace(id=1),
        db=db_session,
    )

    stored = db_session.query(ScheduleChannelInstance).filter(ScheduleChannelInstance.id == trigger.id).first()
    assert updated.is_active is False
    assert updated.status == "paused"
    assert stored.payload_template == {"paused": True}


def test_delete_schedule_trigger_is_tenant_scoped(db_session):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    _seed_tenant_user_agent(db_session, tenant_id="tenant-b", user_id=2, contact_id=102, agent_id=202)
    trigger_a = ScheduleChannelInstance(
        tenant_id="tenant-a",
        integration_name="Tenant A Trigger",
        cron_expression="0 9 * * *",
        timezone="UTC",
        created_by=1,
    )
    trigger_b = ScheduleChannelInstance(
        tenant_id="tenant-b",
        integration_name="Tenant B Trigger",
        cron_expression="0 9 * * *",
        timezone="UTC",
        created_by=2,
    )
    db_session.add_all([trigger_a, trigger_b])
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        delete_schedule_trigger(
            trigger_id=trigger_b.id,
            ctx=_ctx("tenant-a"),
            _user=SimpleNamespace(id=1),
            db=db_session,
        )
    assert exc_info.value.status_code == 404
    assert db_session.query(ScheduleChannelInstance).count() == 2


def test_poll_due_dispatches_schedule_wake_and_advances_cursor(db_session, tmp_path, monkeypatch):
    _seed_tenant_user_agent(db_session, tenant_id="tenant-a", user_id=1, contact_id=101, agent_id=201)
    trigger = ScheduleChannelInstance(
        id=701,
        tenant_id="tenant-a",
        integration_name="Every Five",
        cron_expression="*/5 * * * *",
        timezone="UTC",
        payload_template={"kind": "tick"},
        default_agent_id=201,
        is_active=True,
        status="active",
        next_fire_at=datetime(2026, 1, 2, 3, 0),
        created_by=1,
    )
    db_session.add(trigger)
    _seed_continuous_agent(db_session, continuous_agent_id=301, tenant_id="tenant-a", agent_id=201)
    _seed_subscription(db_session, subscription_id=501, tenant_id="tenant-a", continuous_agent_id=301, instance_id=701)
    db_session.commit()

    class TmpDispatchService(TriggerDispatchService):
        def __init__(self, db):
            super().__init__(db, payload_dir=tmp_path / "backend" / "data" / "wake_events")

    monkeypatch.setattr(schedule_trigger_module, "TriggerDispatchService", TmpDispatchService)

    results = ScheduleTrigger.poll_due(db_session, now=datetime(2026, 1, 2, 3, 0, 5))
    second_results = ScheduleTrigger.poll_due(db_session, now=datetime(2026, 1, 2, 3, 0, 6))

    stored = db_session.query(ScheduleChannelInstance).filter(ScheduleChannelInstance.id == 701).one()
    wake = db_session.query(WakeEvent).one()
    payload_file = tmp_path / wake.payload_ref
    payload = json.loads(payload_file.read_text(encoding="utf-8"))

    assert [result.dispatch_status for result in results] == ["dispatched"]
    assert second_results == []
    assert wake.channel_type == "schedule"
    assert wake.event_type == "schedule.fire"
    assert wake.dedupe_key == "schedule:701:2026-01-02T03:00:00Z"
    assert payload["payload"]["kind"] == "tick"
    assert payload["payload"]["schedule"]["scheduled_at"] == "2026-01-02T03:00:00Z"
    assert stored.last_fire_at == datetime(2026, 1, 2, 3, 0)
    assert stored.last_activity_at == datetime(2026, 1, 2, 3, 0, 5)
    assert stored.last_cursor == "2026-01-02T03:00:00Z"
    assert stored.next_fire_at == datetime(2026, 1, 2, 3, 5)
    assert db_session.query(ContinuousRun).one().status == "queued"
    assert db_session.query(ChannelEventDedupe).one().dedupe_key == wake.dedupe_key
