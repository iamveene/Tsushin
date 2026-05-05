"""Focused Agent Team trigger queue integration tests."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from models import AgentTeam, AgentTeamRun, MessageQueue, TeamRunStatus, WakeEvent
from test_trigger_dispatch_service import (  # noqa: F401
    _seed_team_trigger,
    _seed_tenant_user_agent,
    _seed_webhook,
    db_session,
)
from services.message_queue_service import MessageQueueService
from services.queue_worker import QueueWorker
from services.queue_router import QueueRouter
from services.trigger_dispatch_service import TriggerDispatchInput, TriggerDispatchService


def test_team_run_stale_reset_uses_orchestrator_sized_threshold(db_session):
    _seed_tenant_user_agent(
        db_session,
        tenant_id="tenant-a",
        user_id=1,
        contact_id=101,
        agent_id=201,
    )
    trigger = _seed_team_trigger(db_session, tenant_id="tenant-a")
    team_run = AgentTeamRun(
        tenant_id="tenant-a",
        team_id=trigger.team_id,
        status=TeamRunStatus.RUNNING.value,
        goal_text_snapshot="Goal",
        topology_snapshot="line",
    )
    db_session.add(team_run)
    db_session.flush()
    processing_started_at = datetime.utcnow() - timedelta(seconds=310)
    team_queue = MessageQueue(
        tenant_id="tenant-a",
        channel="team",
        message_type="team_run",
        status="processing",
        agent_id=None,
        team_id=trigger.team_id,
        team_run_id=team_run.id,
        sender_key=f"team:{trigger.team_id}:run:{team_run.id}",
        payload={"team_run_id": team_run.id, "team_id": trigger.team_id},
        processing_started_at=processing_started_at,
    )
    agent_queue = MessageQueue(
        tenant_id="tenant-a",
        channel="api",
        message_type="inbound_message",
        status="processing",
        agent_id=201,
        sender_key="api-user",
        payload={"message": "hello"},
        processing_started_at=processing_started_at,
    )
    db_session.add_all([team_queue, agent_queue])
    db_session.commit()

    reset_count = MessageQueueService(db_session).reset_stale()

    assert reset_count == 1
    assert db_session.get(MessageQueue, team_queue.id).status == "processing"
    assert db_session.get(MessageQueue, agent_queue.id).status == "pending"


def test_worker_leaves_trigger_queue_pending_when_manual_run_uses_capacity(db_session, tmp_path):
    _seed_tenant_user_agent(
        db_session,
        tenant_id="tenant-a",
        user_id=1,
        contact_id=101,
        agent_id=201,
    )
    _seed_webhook(
        db_session,
        instance_id=401,
        tenant_id="tenant-a",
        created_by=1,
        default_agent_id=None,
    )
    trigger = _seed_team_trigger(db_session, tenant_id="tenant-a")
    team = db_session.get(AgentTeam, trigger.team_id)
    team.max_concurrent_runs = 1
    manual_run = AgentTeamRun(
        tenant_id="tenant-a",
        team_id=trigger.team_id,
        status=TeamRunStatus.PENDING.value,
        goal_text_snapshot="Manual goal",
        topology_snapshot="line",
    )
    db_session.add(manual_run)
    db_session.commit()

    result = TriggerDispatchService(
        db_session,
        payload_dir=tmp_path / "backend" / "data" / "wake_events",
    ).dispatch(
        TriggerDispatchInput(
            trigger_type="webhook",
            instance_id=401,
            event_type="message.created",
            dedupe_key="team-trigger-capacity-1",
            payload={"raw_event": {"action": "opened"}},
        )
    )
    queue_item = db_session.query(MessageQueue).filter(MessageQueue.message_type == "team_run").one()
    assert result.status == "dispatched"
    assert MessageQueueService(db_session).count_active_non_queued_team_runs("tenant-a", trigger.team_id) == 1

    worker = QueueWorker(db_session.get_bind())
    worker._running = True
    asyncio.run(worker._poll_and_dispatch())

    db_session.expire_all()
    queue_item = db_session.get(MessageQueue, queue_item.id)
    assert queue_item.status == "pending"
    assert queue_item.processing_started_at is None
    assert worker._active_team_tasks == {}


def test_webhook_team_trigger_enqueues_and_dispatches_team_run(db_session, tmp_path, monkeypatch):
    _seed_tenant_user_agent(
        db_session,
        tenant_id="tenant-a",
        user_id=1,
        contact_id=101,
        agent_id=201,
    )
    _seed_webhook(
        db_session,
        instance_id=401,
        tenant_id="tenant-a",
        created_by=1,
        default_agent_id=None,
    )
    _seed_team_trigger(db_session, tenant_id="tenant-a")
    db_session.commit()

    result = TriggerDispatchService(
        db_session,
        payload_dir=tmp_path / "backend" / "data" / "wake_events",
    ).dispatch(
        TriggerDispatchInput(
            trigger_type="webhook",
            instance_id=401,
            event_type="message.created",
            dedupe_key="team-trigger-e2e-1",
            payload={"raw_event": {"action": "opened"}},
        )
    )

    assert result.status == "dispatched"
    assert len(result.team_run_ids) == 1
    queue_item = db_session.query(MessageQueue).filter(MessageQueue.message_type == "team_run").one()
    team_run = db_session.get(AgentTeamRun, result.team_run_ids[0])
    wake_event = db_session.get(WakeEvent, result.wake_event_id)
    assert queue_item.agent_id is None
    assert queue_item.team_id == team_run.team_id
    assert queue_item.team_run_id == team_run.id
    assert wake_event.status == "pending"

    import services.team_orchestrator_service as orchestrator_module

    class FakeTeamRunOrchestrator:
        def __init__(self, db, *, tenant_id, team_id, existing_run_id):
            self.db = db
            self.tenant_id = tenant_id
            self.team_id = team_id
            self.existing_run_id = existing_run_id

        async def run(self, trigger_event_id=None):
            assert trigger_event_id == result.wake_event_id
            run = self.db.get(AgentTeamRun, self.existing_run_id)
            run.status = TeamRunStatus.COMPLETED.value
            self.db.add(run)
            self.db.commit()
            self.db.refresh(run)
            return run

    monkeypatch.setattr(orchestrator_module, "TeamRunOrchestrator", FakeTeamRunOrchestrator)

    dispatch_result = asyncio.run(QueueRouter().dispatch(None, db_session, queue_item))

    assert dispatch_result["status"] == TeamRunStatus.COMPLETED.value
    assert db_session.get(WakeEvent, result.wake_event_id).status == "processed"


def test_team_queue_enqueue_failure_emits_watcher_event(db_session, tmp_path, monkeypatch):
    _seed_tenant_user_agent(
        db_session,
        tenant_id="tenant-a",
        user_id=1,
        contact_id=101,
        agent_id=201,
    )
    _seed_webhook(
        db_session,
        instance_id=401,
        tenant_id="tenant-a",
        created_by=1,
        default_agent_id=None,
    )
    trigger = _seed_team_trigger(db_session, tenant_id="tenant-a")
    db_session.commit()
    events: list[dict] = []

    def fail_enqueue(self, *args, **kwargs):
        raise RuntimeError("queue unavailable")

    import services.watcher_activity_service as watcher_activity_module

    monkeypatch.setattr(MessageQueueService, "enqueue", fail_enqueue)
    monkeypatch.setattr(
        watcher_activity_module,
        "emit_team_run_async",
        lambda **kwargs: events.append(kwargs),
    )

    result = TriggerDispatchService(
        db_session,
        payload_dir=tmp_path / "backend" / "data" / "wake_events",
    ).dispatch(
        TriggerDispatchInput(
            trigger_type="webhook",
            instance_id=401,
            event_type="message.created",
            dedupe_key="team-trigger-enqueue-failure-1",
            payload={"raw_event": {"action": "opened"}},
        )
    )

    assert result.status == "enqueue_failed"
    assert result.reason == "team_run_queue_enqueue_failed"
    team_run = db_session.get(AgentTeamRun, result.team_run_ids[0])
    wake_event = db_session.get(WakeEvent, result.wake_event_id)
    assert team_run.status == TeamRunStatus.FAILED.value
    assert team_run.error_json == {"reason": "team_run_queue_enqueue_failed"}
    assert wake_event.status == "failed"
    assert events == [
        {
            "tenant_id": "tenant-a",
            "team_run_id": team_run.id,
            "team_id": trigger.team_id,
            "status": TeamRunStatus.FAILED.value,
            "event": "failed",
            "team_name": f"Team {trigger.team_id}",
            "error_json": {"reason": "team_run_queue_enqueue_failed"},
        }
    ]
