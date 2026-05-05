"""Deterministic Agent Teams mesh-orchestrator smoke test.

Run inside the backend container:
    python /app/dev_tests/run_team_mesh_smoke.py

Set KEEP_AGENT_TEAM_SMOKE_FIXTURES=1 to leave rows behind for inspection.
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_ROOT))

import settings  # noqa: E402
from db import get_engine  # noqa: E402
from models import (  # noqa: E402
    Agent,
    AgentTeam,
    AgentTeamMember,
    AgentTeamMemberA2ASnapshot,
    AgentTeamMemberRun,
    AgentTeamRun,
    Contact,
    TeamMemberRole,
    TeamRunScratch,
    TeamRunStatus,
    TeamStatus,
    TeamTopology,
)
from models_rbac import Tenant  # noqa: E402
from services.team_orchestrator_service import TeamRunOrchestrator  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402


TENANT_ID = "agent-team-mesh-smoke"


def _cleanup(session) -> None:
    teams = session.query(AgentTeam).filter(AgentTeam.tenant_id == TENANT_ID).all()
    team_ids = [team.id for team in teams]
    run_ids = [row.id for row in session.query(AgentTeamRun.id).filter(AgentTeamRun.tenant_id == TENANT_ID).all()]
    if run_ids:
        session.query(TeamRunScratch).filter(TeamRunScratch.team_run_id.in_(run_ids)).delete(synchronize_session=False)
        session.query(AgentTeamMemberRun).filter(AgentTeamMemberRun.team_run_id.in_(run_ids)).delete(synchronize_session=False)
        session.query(AgentTeamRun).filter(AgentTeamRun.id.in_(run_ids)).delete(synchronize_session=False)
    if team_ids:
        session.query(AgentTeamMemberA2ASnapshot).filter(AgentTeamMemberA2ASnapshot.team_id.in_(team_ids)).delete(synchronize_session=False)
        session.query(AgentTeamMember).filter(AgentTeamMember.team_id.in_(team_ids)).delete(synchronize_session=False)
        session.query(AgentTeam).filter(AgentTeam.id.in_(team_ids)).delete(synchronize_session=False)

    agent_rows = session.query(Agent).filter(Agent.tenant_id == TENANT_ID).all()
    contact_ids = [agent.contact_id for agent in agent_rows]
    if agent_rows:
        session.query(Agent).filter(Agent.tenant_id == TENANT_ID).delete(synchronize_session=False)
    if contact_ids:
        session.query(Contact).filter(Contact.id.in_(contact_ids)).delete(synchronize_session=False)
    session.query(Tenant).filter(Tenant.id == TENANT_ID).delete(synchronize_session=False)
    session.commit()


def _seed(session) -> AgentTeam:
    tenant = Tenant(id=TENANT_ID, name="Agent Team Mesh Smoke", slug=TENANT_ID, plan="dev")
    session.add(tenant)
    session.flush()

    agents = []
    for name in ("Smoke Researcher", "Smoke Reviewer"):
        contact = Contact(friendly_name=name, role="agent", tenant_id=TENANT_ID, is_active=True)
        session.add(contact)
        session.flush()
        agent = Agent(
            contact_id=contact.id,
            tenant_id=TENANT_ID,
            system_prompt=f"You are {name}.",
            model_provider="openai",
            model_name="gpt-4o-mini",
            is_active=True,
        )
        session.add(agent)
        session.flush()
        agents.append(agent)

    team = AgentTeam(
        tenant_id=TENANT_ID,
        name="Smoke Mesh Team",
        goal_text="Produce a deterministic mesh smoke-test summary.",
        topology=TeamTopology.MESH.value,
        status=TeamStatus.ACTIVE.value,
        max_steps=6,
        max_total_tokens=100,
        max_concurrent_runs=1,
    )
    session.add(team)
    session.flush()
    for index, agent in enumerate(agents, start=1):
        session.add(
            AgentTeamMember(
                tenant_id=TENANT_ID,
                team_id=team.id,
                agent_id=agent.id,
                role=TeamMemberRole.MEMBER.value,
                execution_order=index,
            )
        )
    session.commit()
    session.refresh(team)
    return team


async def _fake_invoke(**kwargs):
    member = kwargs["member"]
    if member.role == TeamMemberRole.COORDINATOR.value:
        if "Recent mesh transcript JSON:\n[]" in kwargs["message_text"]:
            member_ids = [
                row.id
                for row in sorted(kwargs["team"].members, key=lambda item: item.execution_order or 0)
                if row.role == TeamMemberRole.MEMBER.value
            ]
            return {
                "answer": (
                    'Dispatching.\n{"command":"dispatch","dispatches":['
                    f'{{"member_id":{member_ids[0]},"message":"research smoke"}},'
                    f'{{"member_id":{member_ids[1]},"message":"review smoke"}}'
                    '],"reason":"need deterministic member evidence"}'
                ),
                "tokens": {"prompt": 3, "completion": 4},
            }
        return {
            "answer": '{"command":"finish","summary":"mesh smoke complete","key_findings":["smoke"],"open_questions":[]}',
            "tokens": {"prompt": 3, "completion": 4},
        }
    return {
        "answer": (
            f"{member.id} completed smoke dispatch.\n"
            '{"summary":"mesh member smoke summary","key_findings":["smoke"],"open_questions":[]}'
        ),
        "tokens": {"prompt": 3, "completion": 4},
    }


def main() -> None:
    engine = get_engine(settings.DATABASE_URL)
    Session = sessionmaker(bind=engine)
    session = Session()
    keep = os.getenv("KEEP_AGENT_TEAM_SMOKE_FIXTURES") == "1"
    try:
        _cleanup(session)
        team = _seed(session)
        run = asyncio.run(
            TeamRunOrchestrator(
                session,
                tenant_id=TENANT_ID,
                team_id=team.id,
                agent_invoke_fn=_fake_invoke,
            ).run_mesh()
        )
        rows = (
            session.query(AgentTeamMemberRun)
            .filter(AgentTeamMemberRun.team_run_id == run.id)
            .order_by(AgentTeamMemberRun.step_index)
            .all()
        )
        assert run.status == TeamRunStatus.COMPLETED.value, run.status
        assert run.final_output_summary == "mesh smoke complete"
        assert len(rows) == 4, f"expected 4 member runs, got {len(rows)}"
        assert rows[0].team_member.role == TeamMemberRole.COORDINATOR.value
        assert rows[-1].team_member.role == TeamMemberRole.COORDINATOR.value
        print(
            "Agent Team mesh smoke passed: "
            f"run_id={run.id}, final_output_summary={run.final_output_summary!r}"
        )
    finally:
        if keep:
            session.commit()
            print("KEEP_AGENT_TEAM_SMOKE_FIXTURES=1 set; smoke fixtures preserved.")
        else:
            _cleanup(session)
        session.close()
        engine.dispose()


if __name__ == "__main__":
    main()
