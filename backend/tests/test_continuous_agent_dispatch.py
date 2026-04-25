"""Regression tests for BUG-702 / BUG-715.

Validates that ``QueueRouter._dispatch_continuous_task`` consumes a
``continuous_task`` MessageQueue row, drives the subscribed agent against the
wake-event payload, applies BudgetPolicy via ``ContinuousBudgetLimiter``, and
persists run state.

These tests stub out ``AgentService`` so we don't need network/LLM access — the
fix being validated is the dispatch wiring, not the agent itself.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
import types
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Stub out optional dependencies the way other v0.7.0 tests do.
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

from models import (  # noqa: E402
    Agent,
    Base,
    BudgetPolicy,
    Contact,
    ContinuousAgent,
    ContinuousRun,
    ContinuousSubscription,
    DeliveryPolicy,
    MessageQueue,
    SentinelProfile,
    WakeEvent,
)
from models_rbac import Tenant, User  # noqa: E402
from services import queue_router as queue_router_module  # noqa: E402
from services.continuous_agent_service import (  # noqa: E402
    BudgetCheckResult,
    BudgetDecision,
    BudgetKind,
)
from services.message_queue_service import MessageQueueService  # noqa: E402
from services.queue_router import QueueRouter  # noqa: E402


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
            MessageQueue.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _seed_world(
    db,
    *,
    tenant_id: str = "tenant-x",
    agent_id: int = 100,
    contact_id: int = 200,
    continuous_agent_id: int = 300,
    budget_policy: BudgetPolicy | None = None,
):
    db.add(Tenant(id=tenant_id, name=tenant_id.title(), slug=tenant_id))
    db.add(
        User(
            id=1,
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
            friendly_name="Continuous Agent",
            role="agent",
        )
    )
    db.add(
        Agent(
            id=agent_id,
            tenant_id=tenant_id,
            contact_id=contact_id,
            system_prompt="You are a helpful assistant.",
            model_provider="gemini",
            model_name="gemini-2.5-pro",
            response_template="{response}",
            is_active=True,
        )
    )
    if budget_policy is not None:
        db.add(budget_policy)
        db.flush()
    ca = ContinuousAgent(
        id=continuous_agent_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        name="Schedule worker",
        execution_mode="hybrid",
        budget_policy_id=budget_policy.id if budget_policy is not None else None,
        status="active",
    )
    db.add(ca)
    db.flush()
    sub = ContinuousSubscription(
        tenant_id=tenant_id,
        continuous_agent_id=ca.id,
        channel_type="schedule",
        channel_instance_id=42,
        event_type="schedule.fire",
        status="active",
        is_system_owned=False,
    )
    db.add(sub)
    db.flush()
    wake = WakeEvent(
        tenant_id=tenant_id,
        continuous_agent_id=ca.id,
        continuous_subscription_id=sub.id,
        channel_type="schedule",
        channel_instance_id=42,
        event_type="schedule.fire",
        occurred_at=datetime.utcnow(),
        dedupe_key=f"sched-{datetime.utcnow().isoformat()}",
        importance="normal",
        payload_ref=None,
        status="pending",
    )
    db.add(wake)
    db.flush()
    run = ContinuousRun(
        tenant_id=tenant_id,
        continuous_agent_id=ca.id,
        wake_event_ids=[wake.id],
        execution_mode=ca.execution_mode,
        status="queued",
        run_type="continuous",
    )
    db.add(run)
    db.flush()
    queue_item = MessageQueueService(db).enqueue(
        channel="continuous",
        tenant_id=tenant_id,
        agent_id=agent_id,
        sender_key=f"schedule:{sub.id}",
        payload={
            "continuous_run_id": run.id,
            "wake_event_id": wake.id,
            "continuous_agent_id": ca.id,
            "continuous_subscription_id": sub.id,
            "channel_type": "schedule",
            "channel_instance_id": 42,
            "event_type": "schedule.fire",
            "importance": "normal",
            "payload_ref": None,
        },
        message_type="continuous_task",
    )
    return SimpleNamespace(agent=db.query(Agent).get(agent_id), continuous_agent=ca, run=run, wake=wake, queue_item=queue_item)


def _patch_agent_service(monkeypatch, *, answer: str | None = "Run output", error: str | None = None):
    captured: dict = {}

    async def fake_invoke(*, db, agent, continuous_agent, run, sender_key, message_text):
        captured["agent_id"] = agent.id
        captured["continuous_agent_id"] = continuous_agent.id
        captured["run_id"] = run.id
        captured["sender_key"] = sender_key
        captured["message_text"] = message_text
        return {"answer": answer, "error": error, "tokens": {"prompt": 1, "completion": 2}}

    monkeypatch.setattr(queue_router_module, "_invoke_agent_for_continuous_run", fake_invoke)
    return captured


def test_dispatch_continuous_task_runs_agent_and_marks_run_succeeded(db_session, monkeypatch):
    seeded = _seed_world(db_session)
    captured = _patch_agent_service(monkeypatch, answer="Hello from agent")

    router = QueueRouter()
    worker = SimpleNamespace()  # consumer doesn't use worker fields for continuous

    asyncio.run(router.dispatch(worker, db_session, seeded.queue_item))

    db_session.refresh(seeded.run)
    db_session.refresh(seeded.wake)
    assert seeded.run.status == "succeeded", seeded.run.outcome_state
    assert seeded.run.started_at is not None
    assert seeded.run.finished_at is not None
    assert (seeded.run.outcome_state or {}).get("answer") == "Hello from agent"
    assert seeded.wake.status == "processed"
    # Sanity: prompt was built from the wake-event payload.
    assert "schedule" in captured["message_text"]
    assert captured["agent_id"] == seeded.agent.id


def test_dispatch_continuous_task_marks_failed_when_agent_returns_error(db_session, monkeypatch):
    seeded = _seed_world(db_session)
    _patch_agent_service(monkeypatch, answer=None, error="model_unavailable")

    router = QueueRouter()
    worker = SimpleNamespace()

    asyncio.run(router.dispatch(worker, db_session, seeded.queue_item))

    db_session.refresh(seeded.run)
    assert seeded.run.status == "failed"
    assert "model_unavailable" in (seeded.run.outcome_state or {}).get("error", "")


def test_dispatch_continuous_task_skips_when_run_already_started(db_session, monkeypatch):
    seeded = _seed_world(db_session)
    seeded.run.status = "running"
    db_session.add(seeded.run)
    db_session.commit()
    _patch_agent_service(monkeypatch)

    router = QueueRouter()
    result = asyncio.run(router.dispatch(SimpleNamespace(), db_session, seeded.queue_item))

    assert result["status"] == "skipped"
    db_session.refresh(seeded.run)
    assert seeded.run.status == "running"  # untouched


def test_dispatch_continuous_task_pauses_when_budget_exhausted(db_session, monkeypatch):
    """BUG-715: ContinuousBudgetLimiter.check() pauses runs on PAUSE decision."""
    policy = BudgetPolicy(
        tenant_id="tenant-x",
        name="strict",
        max_runs_per_day=1,
        on_exhaustion="pause",
        is_active=True,
    )
    seeded = _seed_world(db_session, budget_policy=policy)

    class _ExhaustedLimiter:
        def check(self, *, tenant_id, continuous_agent_id, policy, budget_kind, amount=1):
            return BudgetCheckResult(
                allowed=False,
                decision=BudgetDecision.PAUSE,
                budget_kind=budget_kind,
                limit=policy.max_runs_per_day,
                remaining=0,
            )

    worker = SimpleNamespace(budget_limiter=_ExhaustedLimiter())
    captured = _patch_agent_service(monkeypatch)

    router = QueueRouter()
    result = asyncio.run(router.dispatch(worker, db_session, seeded.queue_item))

    db_session.refresh(seeded.run)
    assert result["status"] == "skipped"
    assert result["budget_decision"] == "pause"
    assert seeded.run.status == "paused_budget"
    assert (seeded.run.outcome_state or {}).get("budget", {}).get("decision") == "pause"
    assert "agent_id" not in captured  # agent was NOT invoked


def test_dispatch_continuous_task_missing_run_returns_skipped(db_session, monkeypatch):
    seeded = _seed_world(db_session)
    db_session.delete(seeded.run)
    db_session.commit()
    _patch_agent_service(monkeypatch)

    router = QueueRouter()
    result = asyncio.run(router.dispatch(SimpleNamespace(), db_session, seeded.queue_item))

    assert result["status"] == "skipped"
    assert result["reason"] == "continuous_run_not_found"


def test_continuous_task_payload_includes_event_type_in_prompt(db_session, monkeypatch, tmp_path):
    """The prompt must surface payload contents so the agent can act on them."""
    # Write a payload_ref file the dispatcher would have produced, and point
    # the wake event at it via an absolute path.
    payload_doc = {
        "trigger_type": "schedule",
        "instance_id": 42,
        "event_type": "schedule.fire",
        "payload": {"cron": "*/5 * * * *", "tag": "nightly-report"},
    }
    payload_file = tmp_path / "wake.json"
    payload_file.write_text(json.dumps(payload_doc), encoding="utf-8")

    seeded = _seed_world(db_session)
    seeded.wake.payload_ref = str(payload_file)
    db_session.add(seeded.wake)
    db_session.commit()

    captured = _patch_agent_service(monkeypatch)
    router = QueueRouter()
    asyncio.run(router.dispatch(SimpleNamespace(), db_session, seeded.queue_item))

    assert "nightly-report" in captured["message_text"]
    assert "schedule.fire" in captured["message_text"]
