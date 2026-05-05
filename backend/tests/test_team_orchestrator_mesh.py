"""Agent Teams Phase 3 mesh-orchestrator tests."""

import asyncio
import os
import sys
import types

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

docker_stub = types.ModuleType("docker")
docker_stub.errors = types.SimpleNamespace(NotFound=Exception, DockerException=Exception)
docker_stub.DockerClient = object
sys.modules.setdefault("docker", docker_stub)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


import models_rbac  # noqa: F401
from models import (  # noqa: E402
    Agent,
    AgentSkill,
    AgentTeam,
    AgentTeamMember,
    AgentTeamMemberRun,
    AgentTeamRun,
    Base,
    Contact,
    TeamMemberRole,
    TeamMemberRunStatus,
    TeamRunStatus,
    TeamStatus,
    TeamTopology,
)
from models_rbac import Tenant  # noqa: E402
from services.team_orchestrator_service import TeamRunOrchestrator, TeamValidationError  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", echo=False)

    @event.listens_for(engine, "connect")
    def _enable_sqlite_fk(dbapi_connection, _connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _create_tenant(db_session, tenant_id: str) -> Tenant:
    tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=tenant_id, plan="dev")
    db_session.add(tenant)
    db_session.flush()
    return tenant


def _create_agent(db_session, *, tenant_id: str, name: str, active: bool = True) -> Agent:
    contact = Contact(friendly_name=name, role="agent", tenant_id=tenant_id, is_active=True)
    db_session.add(contact)
    db_session.flush()
    agent = Agent(
        contact_id=contact.id,
        tenant_id=tenant_id,
        system_prompt=f"You are {name}",
        model_provider="openai",
        model_name="gpt-4o-mini",
        is_active=active,
    )
    db_session.add(agent)
    db_session.flush()
    return agent


def _create_mesh_team(
    db_session,
    *,
    tenant_id: str,
    agents: list[Agent],
    status: str = TeamStatus.ACTIVE.value,
    max_steps: int = 10,
    max_total_tokens=None,
    name: str = "Mesh Team",
) -> AgentTeam:
    team = AgentTeam(
        tenant_id=tenant_id,
        name=name,
        description="Mesh orchestrator test team",
        goal_text="Coordinate a deterministic mesh answer.",
        topology=TeamTopology.MESH.value,
        status=status,
        max_steps=max_steps,
        max_total_tokens=max_total_tokens,
        max_concurrent_runs=1,
    )
    db_session.add(team)
    db_session.flush()
    for index, agent in enumerate(agents, start=1):
        db_session.add(
            AgentTeamMember(
                tenant_id=tenant_id,
                team_id=team.id,
                agent_id=agent.id,
                role=TeamMemberRole.MEMBER.value,
                execution_order=index,
                is_required=True,
            )
        )
    db_session.commit()
    db_session.refresh(team)
    return team


def _member_runs(db_session, run_id: int) -> list[AgentTeamMemberRun]:
    return (
        db_session.query(AgentTeamMemberRun)
        .filter(AgentTeamMemberRun.team_run_id == run_id)
        .order_by(AgentTeamMemberRun.step_index)
        .all()
    )


def _cancel_run_from_separate_session(db_session, run_id: int) -> None:
    Session = sessionmaker(bind=db_session.get_bind())
    other_session = Session()
    try:
        run = other_session.query(AgentTeamRun).filter(AgentTeamRun.id == run_id).one()
        run.status = TeamRunStatus.CANCELLED.value
        other_session.commit()
    finally:
        other_session.close()


def test_mesh_provisions_coordinator_dispatches_members_and_finishes(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="Researcher"),
        _create_agent(db_session, tenant_id="tenant-a", name="Reviewer"),
    ]
    team = _create_mesh_team(db_session, tenant_id="tenant-a", agents=agents)
    member_ids = [member.id for member in sorted(team.members, key=lambda row: row.execution_order or 0)]
    coordinator_agent_ids = []
    calls = []

    async def fake_invoke(**kwargs):
        calls.append((kwargs["member"].role, kwargs["member"].id, kwargs["message_text"]))
        if kwargs["member"].role == TeamMemberRole.COORDINATOR.value:
            coordinator_agent_ids.append(kwargs["agent"].id)
            if len(coordinator_agent_ids) == 1:
                return {
                    "answer": (
                        "Dispatching.\n"
                        '{"command":"dispatch","dispatches":['
                        f'{{"member_id":{member_ids[0]},"message":"research the issue"}},'
                        f'{{"member_id":{member_ids[1]},"message":"review the issue"}}'
                        '],"reason":"need member input"}'
                    ),
                    "tokens": {"prompt": 2, "completion": 3},
                }
            return {
                "answer": (
                    'Done.\n{"command":"finish","summary":"mesh finished",'
                    '"key_findings":["ok"],"open_questions":[]}'
                ),
                "tokens": {"prompt": 2, "completion": 4},
            }
        return {
            "answer": (
                f"Member {kwargs['member'].id} done.\n"
                '{"summary":"member summary","key_findings":["done"],"open_questions":[]}'
            ),
            "tokens": {"prompt": 5, "completion": 7},
        }

    first_run = asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", team.id, agent_invoke_fn=fake_invoke).run())
    db_session.refresh(team)
    coordinator_agent = db_session.query(Agent).filter(Agent.id == team.coordinator_agent_id).one()
    assert coordinator_agent.is_internal is True
    assert coordinator_agent.is_team_member is True
    assert coordinator_agent.current_team_id == team.id
    assert coordinator_agent.provider_instance_id is None
    db_session.add(AgentSkill(agent_id=coordinator_agent.id, skill_type="web_search", is_enabled=True))
    db_session.commit()
    second_run = asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", team.id, agent_invoke_fn=fake_invoke).run_mesh())

    assert first_run.status == TeamRunStatus.COMPLETED.value
    assert first_run.final_output_summary == "mesh finished"
    assert first_run.total_input_tokens == 14
    assert first_run.total_output_tokens == 21
    assert first_run.completed_steps == 2
    assert team.coordinator_agent_id is not None
    assert len(set(coordinator_agent_ids)) == 1
    assert second_run.status == TeamRunStatus.COMPLETED.value
    assert db_session.query(AgentSkill).filter(AgentSkill.agent_id == coordinator_agent.id).count() == 0

    rows = _member_runs(db_session, first_run.id)
    assert [row.status for row in rows] == [TeamMemberRunStatus.COMPLETED.value] * 4
    assert [row.team_member.role for row in rows] == [
        TeamMemberRole.COORDINATOR.value,
        TeamMemberRole.MEMBER.value,
        TeamMemberRole.MEMBER.value,
        TeamMemberRole.COORDINATOR.value,
    ]
    assert "research the issue" in rows[1].input_context_json["prompt"]
    assert calls[0][0] == TeamMemberRole.COORDINATOR.value


def test_mesh_stops_between_steps_when_run_cancelled_by_another_session(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="Researcher"),
        _create_agent(db_session, tenant_id="tenant-a", name="Reviewer"),
    ]
    team = _create_mesh_team(db_session, tenant_id="tenant-a", agents=agents)
    member_ids = [member.id for member in sorted(team.members, key=lambda row: row.execution_order or 0)]
    calls = []

    async def fake_invoke(**kwargs):
        calls.append(kwargs["member"].id)
        if kwargs["member"].role == TeamMemberRole.COORDINATOR.value:
            return {
                "answer": (
                    "Dispatch.\n"
                    '{"command":"dispatch","dispatches":['
                    f'{{"member_id":{member_ids[0]},"message":"research"}},'
                    f'{{"member_id":{member_ids[1]},"message":"review"}}'
                    '],"reason":"need member input"}'
                ),
                "tokens": {"prompt": 1, "completion": 1},
            }
        _cancel_run_from_separate_session(db_session, kwargs["team_run"].id)
        return {
            "answer": '{"summary":"member complete","key_findings":[],"open_questions":[]}',
            "tokens": {"prompt": 1, "completion": 1},
        }

    run = asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", team.id, agent_invoke_fn=fake_invoke).run_mesh())

    assert run.status == TeamRunStatus.CANCELLED.value
    assert run.completed_at is not None
    assert run.error_json["reason"] == TeamRunStatus.CANCELLED.value
    assert len(calls) == 2
    assert calls[1:] == [member_ids[0]]
    rows = _member_runs(db_session, run.id)
    assert [row.status for row in rows] == [
        TeamMemberRunStatus.COMPLETED.value,
        TeamMemberRunStatus.COMPLETED.value,
        TeamMemberRunStatus.SKIPPED.value,
    ]


def test_mesh_parses_escalate_command_as_goal_not_achieved(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Researcher")
    team = _create_mesh_team(db_session, tenant_id="tenant-a", agents=[agent])

    async def fake_invoke(**_kwargs):
        return {
            "answer": 'Need help.\n{"command":"escalate","reason":"missing evidence","summary":"blocked"}',
            "tokens": {"prompt": 1, "completion": 1},
        }

    run = asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", team.id, agent_invoke_fn=fake_invoke).run_mesh())

    assert run.status == TeamRunStatus.GOAL_NOT_ACHIEVED.value
    assert run.error_json["reason"] == "coordinator_escalated"
    assert run.final_output_summary == "blocked"


def test_mesh_detects_repeated_dispatch_loop(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Researcher")
    team = _create_mesh_team(db_session, tenant_id="tenant-a", agents=[agent], max_steps=6)
    member_id = team.members[0].id

    async def fake_invoke(**kwargs):
        if kwargs["member"].role == TeamMemberRole.COORDINATOR.value:
            return {
                "answer": f'Dispatch.\n{{"command":"dispatch","dispatches":[{{"member_id":{member_id},"message":"repeat"}}]}}',
                "tokens": {"prompt": 1, "completion": 1},
            }
        return {
            "answer": 'Done.\n{"summary":"same","key_findings":[],"open_questions":[]}',
            "tokens": {"prompt": 1, "completion": 1},
        }

    run = asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", team.id, agent_invoke_fn=fake_invoke).run_mesh())

    assert run.status == TeamRunStatus.FAILED.value
    assert run.error_json["reason"] == "repeated_dispatch_loop_detected"


def test_mesh_enforces_max_steps_tokens_wall_clock_and_active_gate(db_session):
    _create_tenant(db_session, "tenant-a")
    step_agent = _create_agent(db_session, tenant_id="tenant-a", name="Step Researcher")
    token_agent = _create_agent(db_session, tenant_id="tenant-a", name="Token Researcher")
    paused_agent = _create_agent(db_session, tenant_id="tenant-a", name="Paused Researcher")
    step_team = _create_mesh_team(db_session, tenant_id="tenant-a", agents=[step_agent], max_steps=1, name="Step Mesh")
    token_team = _create_mesh_team(
        db_session,
        tenant_id="tenant-a",
        agents=[token_agent],
        max_steps=5,
        max_total_tokens=1,
        name="Token Mesh",
    )
    paused_team = _create_mesh_team(db_session, tenant_id="tenant-a", agents=[paused_agent], status=TeamStatus.PAUSED.value, name="Paused Mesh")
    member_id = step_team.members[0].id

    async def dispatch_once(**kwargs):
        if kwargs["member"].role == TeamMemberRole.COORDINATOR.value:
            return {
                "answer": f'Dispatch.\n{{"command":"dispatch","dispatches":[{{"member_id":{member_id},"message":"work"}}]}}',
                "tokens": {"prompt": 1, "completion": 1},
            }
        return {"answer": '{"summary":"done","key_findings":[],"open_questions":[]}', "tokens": {"prompt": 1, "completion": 1}}

    async def expensive_finish(**_kwargs):
        return {
            "answer": '{"command":"finish","summary":"too costly","key_findings":[],"open_questions":[]}',
            "tokens": {"prompt": 2, "completion": 2},
        }

    async def slow_finish(**_kwargs):
        await asyncio.sleep(0.05)
        return {
            "answer": '{"command":"finish","summary":"late","key_findings":[],"open_questions":[]}',
            "tokens": {"prompt": 1, "completion": 1},
        }

    step_run = asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", step_team.id, agent_invoke_fn=dispatch_once).run_mesh())
    token_run = asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", token_team.id, agent_invoke_fn=expensive_finish).run_mesh())
    timeout_run = asyncio.run(
        TeamRunOrchestrator(
            db_session,
            "tenant-a",
            step_team.id,
            wall_clock_seconds=0.01,
            agent_invoke_fn=slow_finish,
        ).run_mesh()
    )

    assert step_run.status == TeamRunStatus.FAILED.value
    assert step_run.error_json["reason"] == "max_steps_exceeded"
    assert token_run.status == TeamRunStatus.FAILED.value
    assert token_run.error_json["reason"] == "max_total_tokens_exceeded"
    assert timeout_run.status == TeamRunStatus.TIMEOUT.value
    with pytest.raises(TeamValidationError, match="team_not_active"):
        asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", paused_team.id, agent_invoke_fn=expensive_finish).run())
