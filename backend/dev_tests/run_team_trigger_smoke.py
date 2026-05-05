"""Deterministic Agent Team trigger-dispatch smoke test.

Run inside the backend container:
    python /app/dev_tests/run_team_trigger_smoke.py

Set KEEP_AGENT_TEAM_TRIGGER_SMOKE_FIXTURES=1 to leave rows behind for inspection.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import settings  # noqa: E402
from db import get_engine  # noqa: E402
from models import (  # noqa: E402
    Agent,
    AgentTeam,
    AgentTeamMember,
    AgentTeamRun,
    AgentTeamTrigger,
    ChannelEventDedupe,
    Contact,
    MessageQueue,
    TeamRunStatus,
    TeamStatus,
    TeamTopology,
    WakeEvent,
    WebhookIntegration,
)
from models_rbac import Tenant, User  # noqa: E402
from services.trigger_dispatch_service import TriggerDispatchInput, TriggerDispatchService  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


TENANT_ID = "agent-team-trigger-smoke"


def _cleanup(session) -> None:
    session.query(MessageQueue).filter(MessageQueue.tenant_id == TENANT_ID).delete(synchronize_session=False)
    session.query(AgentTeamRun).filter(AgentTeamRun.tenant_id == TENANT_ID).delete(synchronize_session=False)
    session.query(AgentTeamTrigger).filter(AgentTeamTrigger.tenant_id == TENANT_ID).delete(synchronize_session=False)
    session.query(AgentTeamMember).filter(AgentTeamMember.tenant_id == TENANT_ID).delete(synchronize_session=False)
    session.query(AgentTeam).filter(AgentTeam.tenant_id == TENANT_ID).delete(synchronize_session=False)
    session.query(ChannelEventDedupe).filter(ChannelEventDedupe.tenant_id == TENANT_ID).delete(synchronize_session=False)
    session.query(WakeEvent).filter(WakeEvent.tenant_id == TENANT_ID).delete(synchronize_session=False)
    session.query(WebhookIntegration).filter(WebhookIntegration.tenant_id == TENANT_ID).delete(synchronize_session=False)
    agent_rows = session.query(Agent).filter(Agent.tenant_id == TENANT_ID).all()
    contact_ids = [agent.contact_id for agent in agent_rows if agent.contact_id is not None]
    session.query(Agent).filter(Agent.tenant_id == TENANT_ID).delete(synchronize_session=False)
    if contact_ids:
        session.query(Contact).filter(Contact.id.in_(contact_ids)).delete(synchronize_session=False)
    session.query(User).filter(User.tenant_id == TENANT_ID).delete(synchronize_session=False)
    session.query(Tenant).filter(Tenant.id == TENANT_ID).delete(synchronize_session=False)
    session.commit()


def _seed(session) -> tuple[WebhookIntegration, AgentTeam]:
    tenant = Tenant(id=TENANT_ID, name="Agent Team Trigger Smoke", slug=TENANT_ID, plan="dev")
    session.add(tenant)
    session.flush()

    user = User(
        tenant_id=TENANT_ID,
        email="agent-team-trigger-smoke@example.com",
        password_hash="x",
        is_active=True,
    )
    session.add(user)
    session.flush()

    contact = Contact(friendly_name="Trigger Smoke Agent", role="agent", tenant_id=TENANT_ID, is_active=True)
    session.add(contact)
    session.flush()
    agent = Agent(
        contact_id=contact.id,
        tenant_id=TENANT_ID,
        system_prompt="You are the trigger smoke agent.",
        model_provider="openai",
        model_name="gpt-4o-mini",
        is_active=True,
        is_default=False,
    )
    session.add(agent)
    session.flush()

    webhook = WebhookIntegration(
        tenant_id=TENANT_ID,
        integration_name="Agent Team Trigger Smoke Webhook",
        slug="agent-team-trigger-smoke-webhook",
        api_secret_encrypted="secret",
        api_secret_preview="whsec_smoke",
        created_by=user.id,
        default_agent_id=None,
        is_active=True,
        status="active",
    )
    session.add(webhook)
    session.flush()

    team = AgentTeam(
        tenant_id=TENANT_ID,
        name="Trigger Smoke Team",
        goal_text="Handle a webhook trigger as a team.",
        topology=TeamTopology.LINE.value,
        status=TeamStatus.ACTIVE.value,
        coordinator_agent_id=agent.id,
        max_steps=3,
        max_concurrent_runs=1,
        created_by_user_id=user.id,
    )
    session.add(team)
    session.flush()
    session.add(
        AgentTeamMember(
            tenant_id=TENANT_ID,
            team_id=team.id,
            agent_id=agent.id,
            execution_order=1,
        )
    )
    session.add(
        AgentTeamTrigger(
            tenant_id=TENANT_ID,
            team_id=team.id,
            trigger_kind="webhook",
            config_json={
                "trigger_instance_id": webhook.id,
                "event_types": ["message.created"],
                "filters": {
                    "jsonpath_matchers": [
                        {"path": "$.raw_event.action", "operator": "equals", "value": "opened"}
                    ]
                },
            },
            is_enabled=True,
        )
    )
    session.commit()
    session.refresh(webhook)
    session.refresh(team)
    return webhook, team


def main() -> None:
    engine = get_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    keep = os.getenv("KEEP_AGENT_TEAM_TRIGGER_SMOKE_FIXTURES") == "1"
    try:
        _cleanup(session)
        webhook, team = _seed(session)
        result = TriggerDispatchService(session).dispatch(
            TriggerDispatchInput(
                trigger_type="webhook",
                instance_id=webhook.id,
                event_type="message.created",
                dedupe_key=f"team-trigger-smoke-{datetime.utcnow().isoformat()}",
                occurred_at=datetime.utcnow(),
                payload={"raw_event": {"action": "opened"}, "message": "hello team"},
            )
        )
        assert result.status == "dispatched", result
        assert len(result.team_run_ids) == 1, result
        team_run = session.get(AgentTeamRun, result.team_run_ids[0])
        assert team_run is not None, "team run was not persisted"
        assert team_run.team_id == team.id
        assert team_run.status == TeamRunStatus.PENDING.value
        queue_item = (
            session.query(MessageQueue)
            .filter(
                MessageQueue.tenant_id == TENANT_ID,
                MessageQueue.message_type == "team_run",
                MessageQueue.team_run_id == team_run.id,
            )
            .one()
        )
        assert queue_item.agent_id is None
        assert queue_item.team_id == team.id
        print(
            "Agent Team trigger smoke passed: "
            f"wake_event_id={result.wake_event_id}, team_run_id={team_run.id}, queue_id={queue_item.id}"
        )
    finally:
        if keep:
            session.commit()
            print("KEEP_AGENT_TEAM_TRIGGER_SMOKE_FIXTURES=1 set; smoke fixtures preserved.")
        else:
            _cleanup(session)
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
