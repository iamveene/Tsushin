"""Focused Agent Team trigger queue integration tests."""

from __future__ import annotations

import asyncio

from models import AgentTeamRun, MessageQueue, TeamRunStatus, WakeEvent
from services.queue_router import QueueRouter
from services.trigger_dispatch_service import TriggerDispatchInput, TriggerDispatchService
from test_trigger_dispatch_service import (  # noqa: F401
    _seed_team_trigger,
    _seed_tenant_user_agent,
    _seed_webhook,
    db_session,
)


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
