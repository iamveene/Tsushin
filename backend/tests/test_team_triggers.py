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


# ---------------------------------------------------------------------------
# BUG-731 regression: Gmail (email) trigger -> team dispatch must fire a run.
# ---------------------------------------------------------------------------

from test_trigger_dispatch_service import _seed_email  # noqa: E402,F401


def test_gmail_email_trigger_dispatches_team_run(db_session, tmp_path):
    """A team bound with trigger_kind='gmail' must fire when an EmailTrigger
    dispatches with trigger_type='email'. Regression for BUG-731 — the
    dispatcher used to gate out trigger_type='email' before reaching team
    matching, and the team-trigger query stored the kind as 'gmail', so no
    Gmail event ever produced an AgentTeamRun.
    """
    _seed_tenant_user_agent(
        db_session,
        tenant_id="tenant-a",
        user_id=1,
        contact_id=101,
        agent_id=201,
    )
    _seed_email(
        db_session,
        instance_id=501,
        tenant_id="tenant-a",
        created_by=1,
        default_agent_id=None,
    )
    _seed_team_trigger(
        db_session,
        tenant_id="tenant-a",
        trigger_kind="gmail",
        config_json={
            "trigger_instance_id": 501,
            "event_types": ["email.message.received"],
        },
    )
    db_session.commit()

    result = TriggerDispatchService(
        db_session,
        payload_dir=tmp_path / "backend" / "data" / "wake_events",
    ).dispatch(
        TriggerDispatchInput(
            trigger_type="email",
            instance_id=501,
            event_type="email.message.received",
            dedupe_key="bug731-email-team-1",
            payload={"message": {"id": "abc", "subject": "test"}},
        )
    )

    assert result.status == "dispatched", result
    assert len(result.team_run_ids) == 1, (
        "Expected the Gmail-bound team trigger to fire exactly one team run; "
        "if this is empty, _matching_team_triggers regressed and is gating out "
        "trigger_type='email' or failing to translate it to trigger_kind='gmail'."
    )
    team_run = db_session.get(AgentTeamRun, result.team_run_ids[0])
    assert team_run is not None
    assert team_run.tenant_id == "tenant-a"


# ---------------------------------------------------------------------------
# Team -> contact notification hook (BUG-731 follow-up).
# ---------------------------------------------------------------------------

def test_team_notify_contact_directive_calls_mcp_sender(db_session, tmp_path, monkeypatch):
    """When a team description carries `[notify:contact:N]`, _finish_run must
    call MCPSender.send_message with the run summary. Failure to deliver must
    not raise.
    """
    from models import (
        AgentTeam,
        AgentTeamRun,
        Contact,
        TeamRunStatus,
        TeamStatus,
        WhatsAppMCPInstance,
    )
    import services.team_orchestrator_service as orch
    from services.team_orchestrator_service import TeamRunOrchestrator

    _seed_tenant_user_agent(
        db_session,
        tenant_id="tenant-a",
        user_id=1,
        contact_id=101,
        agent_id=201,
    )
    contact = Contact(
        id=909,
        tenant_id="tenant-a",
        friendly_name="VINI-TEST",
        phone_number="+5500000000099",
        whatsapp_id="259099000000099",
        role="user",
        is_active=True,
    )
    db_session.add(contact)
    team = AgentTeam(
        id=4242,
        tenant_id="tenant-a",
        name="Notify-Team",
        description="QA — should notify [notify:contact:909]",
        topology="line",
        status=TeamStatus.ACTIVE.value,
        max_steps=3,
        created_by_user_id=1,
    )
    db_session.add(team)

    # whatsapp_mcp_instance is not in the shared db_session fixture's table list;
    # create it on demand for this test only.
    from models import Base
    Base.metadata.create_all(
        db_session.get_bind(),
        tables=[WhatsAppMCPInstance.__table__],
    )

    mcp = WhatsAppMCPInstance(
        id=77,
        tenant_id="tenant-a",
        container_name="t-mcp",
        phone_number="+5500000000050",
        instance_type="agent",
        mcp_api_url="http://mock-mcp:8080/api",
        mcp_port=8080,
        messages_db_path="/tmp/m.db",
        session_data_path="/tmp/s",
        created_by=1,
        is_group_handler=False,
        status="running",
        api_secret="secret",
    )
    db_session.add(mcp)
    team_run = AgentTeamRun(
        tenant_id="tenant-a",
        team_id=team.id,
        topology_snapshot="line",
        status=TeamRunStatus.PENDING.value,
        goal_text_snapshot="x",
        final_output_summary="hello from team",
    )
    db_session.add(team_run)
    db_session.commit()
    db_session.refresh(team_run)

    captured = {}

    class _FakeResponse:
        status_code = 202
        text = "{}"

    def _fake_post(url, json=None, headers=None, timeout=None, **kwargs):
        captured["url"] = url
        captured["json"] = json
        captured["headers"] = headers
        return _FakeResponse()

    import httpx
    monkeypatch.setattr(httpx, "post", _fake_post)

    orchestrator = TeamRunOrchestrator(
        db=db_session,
        tenant_id="tenant-a",
        team_id=team.id,
        existing_run_id=team_run.id,
    )

    orchestrator._maybe_notify_contact_on_completion(team_run)

    assert captured.get("url") == "http://mock-mcp:8080/api/send"
    assert captured.get("json", {}).get("recipient") == "5500000000099"
    assert "hello from team" in (captured.get("json", {}).get("message") or "")
    assert captured.get("headers", {}).get("Authorization") == "Bearer secret"


def test_team_member_prompts_include_trigger_payload(db_session, tmp_path, monkeypatch):
    """Agents must see the actual trigger payload, not just the team goal.

    Pre-fix, _build_line_prompt / _build_mesh_*_prompt only included
    team.goal_text + prior summaries, so agents wrote 'trigger payload is
    missing' for every triggered run. This regression locks in payload
    propagation: dispatcher writes the payload to disk, orchestrator reads
    it via _read_payload_ref, prompts include it.
    """
    from models import (
        AgentTeam,
        AgentTeamMember,
        AgentTeamRun,
        TeamMemberRole,
        TeamRunStatus,
        TeamStatus,
        WakeEvent,
    )
    from services.team_orchestrator_service import TeamRunOrchestrator
    import services.trigger_dispatch_service as dispatch_module

    _seed_tenant_user_agent(
        db_session,
        tenant_id="tenant-a",
        user_id=1,
        contact_id=101,
        agent_id=201,
    )
    team = AgentTeam(
        id=5050,
        tenant_id="tenant-a",
        name="Payload-Team",
        description="QA",
        topology="line",
        status=TeamStatus.ACTIVE.value,
        goal_text="Summarize the issue.",
        max_steps=3,
        created_by_user_id=1,
    )
    db_session.add(team)
    member = AgentTeamMember(
        tenant_id="tenant-a",
        team_id=team.id,
        agent_id=201,
        execution_order=1,
    )
    db_session.add(member)
    wake = WakeEvent(
        id=9999,
        tenant_id="tenant-a",
        channel_type="jira",
        channel_instance_id=401,
        event_type="jira.issue.detected",
        dedupe_key="payload-test-1",
        payload_ref="backend/data/wake_events/payload-test-1.json",
    )
    db_session.add(wake)
    team_run = AgentTeamRun(
        tenant_id="tenant-a",
        team_id=team.id,
        topology_snapshot="line",
        status=TeamRunStatus.PENDING.value,
        goal_text_snapshot="Summarize the issue.",
        trigger_event_id=wake.id,
    )
    db_session.add(team_run)
    db_session.commit()

    fake_payload = {
        "payload": {
            "issue": {"key": "JSM-42", "fields": {"summary": "Outage in checkout flow"}},
            "site_url": "https://example.atlassian.net",
        }
    }
    monkeypatch.setattr(
        dispatch_module.TriggerDispatchService,
        "_read_payload_ref",
        lambda self, ref: fake_payload,
    )

    orchestrator = TeamRunOrchestrator(
        db=db_session,
        tenant_id="tenant-a",
        team_id=team.id,
        existing_run_id=team_run.id,
    )
    orchestrator._load_trigger_payload(wake.id)
    assert "JSM-42" in orchestrator._trigger_payload_summary
    assert "Outage in checkout flow" in orchestrator._trigger_payload_summary

    line_prompt = orchestrator._build_line_prompt(
        team=team,
        step_index=1,
        member=member,
        prior_summaries=[],
        previous_output="",
    )
    assert "Trigger payload (data the team must analyze)" in line_prompt
    assert "JSM-42" in line_prompt
    assert "Outage in checkout flow" in line_prompt

    mesh_coord_prompt = orchestrator._build_mesh_coordinator_prompt(
        team=team,
        coordinator_member=member,
        runnable_members=[],
        transcript=[],
    )
    assert "JSM-42" in mesh_coord_prompt

    mesh_member_prompt = orchestrator._build_mesh_member_prompt(
        team=team,
        dispatch={"message": "do work", "member_id": member.id},
        transcript=[],
        coordinator_reason="because",
    )
    assert "JSM-42" in mesh_member_prompt
