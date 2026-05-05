"""Agent Teams Phase 2 line-orchestrator tests."""

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
from services.team_orchestrator_service import (  # noqa: E402
    TeamRunOrchestrator,
    TeamValidationError,
)


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
    tenant = Tenant(
        id=tenant_id,
        name=f"Tenant {tenant_id}",
        slug=tenant_id,
        plan="dev",
    )
    db_session.add(tenant)
    db_session.flush()
    return tenant


def _create_agent(db_session, *, tenant_id: str, name: str, active: bool = True) -> Agent:
    contact = Contact(
        friendly_name=name,
        role="agent",
        tenant_id=tenant_id,
        is_active=True,
    )
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


def _create_line_team(
    db_session,
    *,
    tenant_id: str,
    name: str = "Line Team",
    agents: list[Agent],
    topology: str = TeamTopology.LINE.value,
    max_total_tokens=None,
) -> AgentTeam:
    team = AgentTeam(
        tenant_id=tenant_id,
        name=name,
        description="Line orchestrator test team",
        goal_text="Investigate, summarize, and recommend next action.",
        topology=topology,
        status=TeamStatus.ACTIVE.value,
        max_steps=10,
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


def _answer(label: str) -> str:
    return (
        f"Normal output from {label}.\n\n"
        '{"summary": "summary from '
        + label
        + '", "key_findings": ["finding"], "open_questions": []}'
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


def test_line_runs_all_members_in_order_and_chains_context(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="First"),
        _create_agent(db_session, tenant_id="tenant-a", name="Second"),
        _create_agent(db_session, tenant_id="tenant-a", name="Third"),
    ]
    team = _create_line_team(db_session, tenant_id="tenant-a", agents=agents)
    calls = []

    async def fake_invoke(**kwargs):
        calls.append(kwargs)
        label = f"agent-{kwargs['agent'].id}"
        return {
            "answer": _answer(label),
            "tokens": {"prompt": kwargs["agent"].id, "completion": kwargs["agent"].id + 10},
        }

    run = asyncio.run(
        TeamRunOrchestrator(
            db_session,
            tenant_id="tenant-a",
            team_id=team.id,
            agent_invoke_fn=fake_invoke,
        ).run_line()
    )

    assert run.status == TeamRunStatus.COMPLETED.value
    assert [call["agent"].id for call in calls] == [agent.id for agent in agents]
    assert "summary from agent-" in calls[1]["message_text"]
    assert "Normal output from agent-" in calls[1]["message_text"]
    assert run.completed_steps == 3
    assert run.failed_steps == 0
    assert run.total_input_tokens == sum(agent.id for agent in agents)
    assert run.total_output_tokens == sum(agent.id + 10 for agent in agents)
    assert run.final_output_summary == f"summary from agent-{agents[-1].id}"

    rows = _member_runs(db_session, run.id)
    assert [row.status for row in rows] == [TeamMemberRunStatus.COMPLETED.value] * 3
    assert [row.output_summary for row in rows] == [f"summary from agent-{agent.id}" for agent in agents]


def test_line_stops_between_steps_when_run_cancelled_by_another_session(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="First"),
        _create_agent(db_session, tenant_id="tenant-a", name="Second"),
        _create_agent(db_session, tenant_id="tenant-a", name="Third"),
    ]
    team = _create_line_team(db_session, tenant_id="tenant-a", agents=agents)
    calls = []

    async def fake_invoke(**kwargs):
        calls.append(kwargs["agent"].id)
        _cancel_run_from_separate_session(db_session, kwargs["team_run"].id)
        return {"answer": _answer(str(kwargs["agent"].id)), "tokens": {"prompt": 1, "completion": 1}}

    run = asyncio.run(
        TeamRunOrchestrator(
            db_session,
            tenant_id="tenant-a",
            team_id=team.id,
            agent_invoke_fn=fake_invoke,
        ).run_line()
    )

    assert calls == [agents[0].id]
    assert run.status == TeamRunStatus.CANCELLED.value
    assert run.completed_at is not None
    assert run.error_json["reason"] == TeamRunStatus.CANCELLED.value
    assert run.completed_steps == 1
    assert run.failed_steps == 0
    rows = _member_runs(db_session, run.id)
    assert [row.status for row in rows] == [
        TeamMemberRunStatus.COMPLETED.value,
        TeamMemberRunStatus.SKIPPED.value,
        TeamMemberRunStatus.SKIPPED.value,
    ]


def test_line_aborts_on_member_failure_and_skips_remaining(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="First"),
        _create_agent(db_session, tenant_id="tenant-a", name="Second"),
        _create_agent(db_session, tenant_id="tenant-a", name="Third"),
    ]
    team = _create_line_team(db_session, tenant_id="tenant-a", agents=agents)

    async def fake_invoke(**kwargs):
        if kwargs["agent"].id == agents[1].id:
            return {"answer": None, "error": "model_unavailable"}
        return {"answer": _answer(str(kwargs["agent"].id)), "tokens": {"prompt": 1, "completion": 1}}

    run = asyncio.run(
        TeamRunOrchestrator(
            db_session,
            tenant_id="tenant-a",
            team_id=team.id,
            agent_invoke_fn=fake_invoke,
        ).run_line()
    )

    assert run.status == TeamRunStatus.FAILED.value
    assert run.failed_steps == 1
    assert run.error_json["reason"] == "member_error"
    rows = _member_runs(db_session, run.id)
    assert [row.status for row in rows] == [
        TeamMemberRunStatus.COMPLETED.value,
        TeamMemberRunStatus.FAILED.value,
        TeamMemberRunStatus.SKIPPED.value,
    ]


def test_line_respects_wall_clock_timeout(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="First"),
        _create_agent(db_session, tenant_id="tenant-a", name="Second"),
    ]
    team = _create_line_team(db_session, tenant_id="tenant-a", agents=agents)

    async def slow_invoke(**_kwargs):
        await asyncio.sleep(0.05)
        return {"answer": _answer("late"), "tokens": {"prompt": 1, "completion": 1}}

    run = asyncio.run(
        TeamRunOrchestrator(
            db_session,
            tenant_id="tenant-a",
            team_id=team.id,
            wall_clock_seconds=0.01,
            agent_invoke_fn=slow_invoke,
        ).run_line()
    )

    assert run.status == TeamRunStatus.TIMEOUT.value
    rows = _member_runs(db_session, run.id)
    assert [row.status for row in rows] == [
        TeamMemberRunStatus.FAILED.value,
        TeamMemberRunStatus.SKIPPED.value,
    ]


def test_line_records_malformed_summary_with_fallback(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Fallback")
    team = _create_line_team(db_session, tenant_id="tenant-a", agents=[agent])

    async def fake_invoke(**_kwargs):
        return {"answer": "plain unstructured answer", "tokens": {"prompt": 1, "completion": 2}}

    run = asyncio.run(
        TeamRunOrchestrator(
            db_session,
            tenant_id="tenant-a",
            team_id=team.id,
            agent_invoke_fn=fake_invoke,
        ).run_line()
    )

    assert run.status == TeamRunStatus.COMPLETED.value
    row = _member_runs(db_session, run.id)[0]
    assert row.output_summary == "plain unstructured answer"
    assert row.input_context_json["parsed_summary"]["parse_fallback"] is True


def test_line_enforces_max_total_tokens(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="First"),
        _create_agent(db_session, tenant_id="tenant-a", name="Second"),
    ]
    team = _create_line_team(db_session, tenant_id="tenant-a", agents=agents, max_total_tokens=2)

    async def fake_invoke(**_kwargs):
        return {"answer": _answer("too-expensive"), "tokens": {"prompt": 2, "completion": 2}}

    run = asyncio.run(
        TeamRunOrchestrator(
            db_session,
            tenant_id="tenant-a",
            team_id=team.id,
            agent_invoke_fn=fake_invoke,
        ).run_line()
    )

    assert run.status == TeamRunStatus.FAILED.value
    assert run.error_json["reason"] == "max_total_tokens_exceeded"
    rows = _member_runs(db_session, run.id)
    assert [row.status for row in rows] == [
        TeamMemberRunStatus.COMPLETED.value,
        TeamMemberRunStatus.SKIPPED.value,
    ]


def test_line_rejects_empty_team_non_line_topology_and_wrong_tenant(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Only")

    empty_team = AgentTeam(
        tenant_id="tenant-a",
        name="Empty",
        topology=TeamTopology.LINE.value,
        status=TeamStatus.ACTIVE.value,
    )
    db_session.add(empty_team)
    db_session.flush()
    mesh_team = _create_line_team(
        db_session,
        tenant_id="tenant-a",
        name="Mesh",
        agents=[agent],
        topology=TeamTopology.MESH.value,
    )
    db_session.commit()

    with pytest.raises(TeamValidationError, match="team_has_no_members"):
        asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", empty_team.id).run_line())
    with pytest.raises(TeamValidationError, match="unsupported_topology"):
        asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", mesh_team.id).run_line())
    with pytest.raises(TeamValidationError, match="team_not_found"):
        asyncio.run(TeamRunOrchestrator(db_session, "tenant-b", mesh_team.id).run_line())

    assert db_session.query(AgentTeamRun).count() == 0


def test_line_rejects_inactive_team_member_agent(db_session):
    _create_tenant(db_session, "tenant-a")
    inactive_agent = _create_agent(db_session, tenant_id="tenant-a", name="Inactive", active=False)
    team = _create_line_team(db_session, tenant_id="tenant-a", agents=[inactive_agent])

    with pytest.raises(TeamValidationError, match="team_member_agent_inactive"):
        asyncio.run(TeamRunOrchestrator(db_session, "tenant-a", team.id).run_line())

    assert db_session.query(AgentTeamRun).count() == 0
