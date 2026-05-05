"""Agent Teams Phase 1 schema/ORM regression tests.

This file deliberately exercises only persistence, relationships, tenant
scoping, and cascade behavior. Runtime orchestration/API/UI behavior belongs
to later Agent Teams phases.
"""

import os
import sys

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import joinedload, sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


import models_rbac  # noqa: F401
from models import (  # noqa: E402
    Agent,
    AgentCommunicationPermission,
    AgentTeam,
    AgentTeamMember,
    AgentTeamMemberA2ASnapshot,
    AgentTeamMemberRun,
    AgentTeamTrigger,
    AgentTeamRun,
    Base,
    CaseMemory,
    Contact,
    Memory,
    TeamMemberRole,
    TeamRunScratch,
    TeamRunStatus,
    TeamStatus,
    TeamTopology,
    WakeEvent,
)
from models_rbac import Tenant  # noqa: E402


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


def _create_agent(db_session, *, tenant_id: str, name: str) -> Agent:
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
        is_active=True,
    )
    db_session.add(agent)
    db_session.flush()
    return agent


def _create_team(db_session, *, tenant_id: str, name: str, agents: list[Agent]) -> AgentTeam:
    team = AgentTeam(
        tenant_id=tenant_id,
        name=name,
        description="Phase 1 test team",
        goal_text="Prove the schema can persist team configuration.",
        topology=TeamTopology.LINE.value,
        status=TeamStatus.DRAFT.value,
        max_steps=10,
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
                position_x=100.0 * index,
                position_y=50.0,
            )
        )
    db_session.flush()
    return team


def test_create_team_with_members_persists(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="Classifier"),
        _create_agent(db_session, tenant_id="tenant-a", name="Reporter"),
    ]
    team = _create_team(db_session, tenant_id="tenant-a", name="Bug Triage", agents=agents)
    db_session.commit()

    loaded = (
        db_session.query(AgentTeam)
        .options(joinedload(AgentTeam.members).joinedload(AgentTeamMember.agent))
        .filter(AgentTeam.id == team.id)
        .one()
    )

    assert loaded.tenant_id == "tenant-a"
    assert loaded.topology == TeamTopology.LINE.value
    assert [member.agent.contact_id for member in loaded.members] == [
        agents[0].contact_id,
        agents[1].contact_id,
    ]
    assert [member.execution_order for member in loaded.members] == [1, 2]


def test_unique_agent_in_one_team(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Solo")
    _create_team(db_session, tenant_id="tenant-a", name="Team One", agents=[agent])
    db_session.flush()

    second_team = AgentTeam(
        tenant_id="tenant-a",
        name="Team Two",
        topology=TeamTopology.LINE.value,
        status=TeamStatus.DRAFT.value,
    )
    db_session.add(second_team)
    db_session.flush()
    db_session.add(
        AgentTeamMember(
            tenant_id="tenant-a",
            team_id=second_team.id,
            agent_id=agent.id,
            role=TeamMemberRole.MEMBER.value,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_team_run_cascade_deletes_member_runs_and_scratch(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Runner")
    team = _create_team(db_session, tenant_id="tenant-a", name="Run Team", agents=[agent])
    member = team.members[0]
    run = AgentTeamRun(
        tenant_id="tenant-a",
        team_id=team.id,
        status=TeamRunStatus.RUNNING.value,
        goal_text_snapshot="Investigate a bug.",
        topology_snapshot=TeamTopology.LINE.value,
    )
    db_session.add(run)
    db_session.flush()
    db_session.add(
        AgentTeamMemberRun(
            tenant_id="tenant-a",
            team_run_id=run.id,
            agent_team_member_id=member.id,
            agent_id=agent.id,
            step_index=1,
            status="completed",
            output_summary="done",
        )
    )
    db_session.add(
        TeamRunScratch(
            tenant_id="tenant-a",
            team_id=team.id,
            team_run_id=run.id,
            key="handoff",
            value_json={"summary": "done"},
        )
    )
    db_session.commit()

    db_session.delete(run)
    db_session.commit()

    assert db_session.query(AgentTeamMemberRun).count() == 0
    assert db_session.query(TeamRunScratch).count() == 0
    assert db_session.query(AgentTeam).count() == 1


def test_member_run_history_survives_member_removal(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Historical Runner")
    team = _create_team(db_session, tenant_id="tenant-a", name="Historical Team", agents=[agent])
    member = team.members[0]
    run = AgentTeamRun(
        tenant_id="tenant-a",
        team_id=team.id,
        status=TeamRunStatus.COMPLETED.value,
        goal_text_snapshot="Keep the audit row.",
        topology_snapshot=TeamTopology.LINE.value,
    )
    db_session.add(run)
    db_session.flush()
    member_run = AgentTeamMemberRun(
        tenant_id="tenant-a",
        team_run_id=run.id,
        agent_team_member_id=member.id,
        agent_id=agent.id,
        step_index=1,
        status="completed",
        output_summary="done",
    )
    db_session.add(member_run)
    db_session.commit()

    db_session.delete(member)
    db_session.commit()

    loaded = db_session.query(AgentTeamMemberRun).one()
    assert loaded.tenant_id == "tenant-a"
    assert loaded.team_run_id == run.id
    assert loaded.agent_team_member_id is None
    assert loaded.agent_id == agent.id


def test_team_delete_restricted_while_members_exist(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Protected Member")
    team = _create_team(db_session, tenant_id="tenant-a", name="Protected Team", agents=[agent])
    db_session.commit()
    team_id = team.id
    db_session.expire_all()

    team = db_session.query(AgentTeam).filter(AgentTeam.id == team_id).one()
    db_session.delete(team)

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    assert db_session.query(AgentTeam).count() == 1
    assert db_session.query(AgentTeamMember).count() == 1


def test_a2a_snapshot_round_trip(db_session):
    _create_tenant(db_session, "tenant-a")
    source = _create_agent(db_session, tenant_id="tenant-a", name="Source")
    target = _create_agent(db_session, tenant_id="tenant-a", name="Target")
    team = _create_team(db_session, tenant_id="tenant-a", name="Snapshot Team", agents=[source])
    permission = AgentCommunicationPermission(
        tenant_id="tenant-a",
        source_agent_id=source.id,
        target_agent_id=target.id,
        is_enabled=True,
        max_depth=2,
        rate_limit_rpm=12,
        allow_target_skills=True,
    )
    db_session.add(permission)
    db_session.flush()

    payload = {
        "tenant_id": permission.tenant_id,
        "source_agent_id": permission.source_agent_id,
        "target_agent_id": permission.target_agent_id,
        "is_enabled": permission.is_enabled,
        "max_depth": permission.max_depth,
        "rate_limit_rpm": permission.rate_limit_rpm,
        "allow_target_skills": permission.allow_target_skills,
    }
    snapshot = AgentTeamMemberA2ASnapshot(
        tenant_id="tenant-a",
        team_id=team.id,
        agent_id=source.id,
        permission_id=permission.id,
        permission_payload_json=payload,
    )
    db_session.add(snapshot)
    db_session.commit()

    loaded = db_session.query(AgentTeamMemberA2ASnapshot).one()
    assert loaded.permission_payload_json == payload

    permission.is_enabled = False
    permission.max_depth = 99
    permission.rate_limit_rpm = 99
    permission.allow_target_skills = False
    db_session.commit()

    for key, value in loaded.permission_payload_json.items():
        setattr(permission, key, value)
    db_session.commit()
    db_session.refresh(permission)

    restored = {
        "tenant_id": permission.tenant_id,
        "source_agent_id": permission.source_agent_id,
        "target_agent_id": permission.target_agent_id,
        "is_enabled": permission.is_enabled,
        "max_depth": permission.max_depth,
        "rate_limit_rpm": permission.rate_limit_rpm,
        "allow_target_skills": permission.allow_target_skills,
    }
    assert restored == payload


def test_memory_team_run_id_optional(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Memory Agent")
    memory = Memory(
        tenant_id="tenant-a",
        agent_id=agent.id,
        sender_key="direct:user",
        messages_json=[{"role": "user", "content": "hello"}],
    )
    case = CaseMemory(
        tenant_id="tenant-a",
        agent_id=agent.id,
        origin_kind="continuous_run",
        trigger_kind="webhook",
        outcome_label="resolved",
        problem_summary="Problem",
        action_summary="Action",
        outcome_summary="Outcome",
    )
    db_session.add_all([memory, case])
    db_session.commit()

    assert db_session.query(Memory).one().team_run_id is None
    assert db_session.query(CaseMemory).one().team_run_id is None


def test_team_query_filters_by_tenant_id(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agent_a = _create_agent(db_session, tenant_id="tenant-a", name="Tenant A Agent")
    agent_b = _create_agent(db_session, tenant_id="tenant-b", name="Tenant B Agent")
    _create_team(db_session, tenant_id="tenant-a", name="Tenant A Team", agents=[agent_a])
    _create_team(db_session, tenant_id="tenant-b", name="Tenant B Team", agents=[agent_b])
    db_session.commit()

    teams_a = (
        db_session.query(AgentTeam)
        .options(joinedload(AgentTeam.members))
        .filter(AgentTeam.tenant_id == "tenant-a")
        .all()
    )

    assert len(teams_a) == 1
    assert teams_a[0].tenant_id == "tenant-a"
    assert all(member.tenant_id == "tenant-a" for member in teams_a[0].members)


def test_team_member_rejects_cross_tenant_agent(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agent_a = _create_agent(db_session, tenant_id="tenant-a", name="Tenant A Agent")
    agent_b = _create_agent(db_session, tenant_id="tenant-b", name="Tenant B Agent")
    team = _create_team(db_session, tenant_id="tenant-a", name="Tenant A Team", agents=[agent_a])
    db_session.flush()

    db_session.add(
        AgentTeamMember(
            tenant_id="tenant-a",
            team_id=team.id,
            agent_id=agent_b.id,
            role=TeamMemberRole.MEMBER.value,
        )
    )

    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_team_nullable_references_reject_cross_tenant_targets(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agent_a = _create_agent(db_session, tenant_id="tenant-a", name="Tenant A Agent")
    agent_b = _create_agent(db_session, tenant_id="tenant-b", name="Tenant B Agent")
    target_b = _create_agent(db_session, tenant_id="tenant-b", name="Tenant B Target")
    team_a = _create_team(db_session, tenant_id="tenant-a", name="Tenant A Team", agents=[agent_a])
    team_b = _create_team(db_session, tenant_id="tenant-b", name="Tenant B Team", agents=[agent_b])
    wake_b = WakeEvent(
        tenant_id="tenant-b",
        channel_type="webhook",
        channel_instance_id=42,
        event_type="message",
        dedupe_key="tenant-b-event",
    )
    permission_b = AgentCommunicationPermission(
        tenant_id="tenant-b",
        source_agent_id=agent_b.id,
        target_agent_id=target_b.id,
        is_enabled=True,
    )
    db_session.add_all([wake_b, permission_b])
    db_session.commit()

    team_a.coordinator_agent_id = agent_b.id
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    agent_a.current_team_id = team_b.id
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        AgentTeamRun(
            tenant_id="tenant-a",
            team_id=team_a.id,
            status=TeamRunStatus.PENDING.value,
            trigger_event_id=wake_b.id,
            goal_text_snapshot="Bad trigger.",
            topology_snapshot=TeamTopology.LINE.value,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        AgentTeamMemberA2ASnapshot(
            tenant_id="tenant-a",
            team_id=team_a.id,
            agent_id=agent_a.id,
            permission_id=permission_b.id,
            permission_payload_json={"bad": True},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_team_child_rows_reject_cross_tenant_or_cross_team_links(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agent_a = _create_agent(db_session, tenant_id="tenant-a", name="Tenant A Agent")
    agent_b = _create_agent(db_session, tenant_id="tenant-b", name="Tenant B Agent")
    team_a = _create_team(db_session, tenant_id="tenant-a", name="Tenant A Team", agents=[agent_a])
    team_b = _create_team(db_session, tenant_id="tenant-b", name="Tenant B Team", agents=[agent_b])
    run_b = AgentTeamRun(
        tenant_id="tenant-b",
        team_id=team_b.id,
        status=TeamRunStatus.RUNNING.value,
        goal_text_snapshot="Tenant B run.",
        topology_snapshot=TeamTopology.LINE.value,
    )
    run_a = AgentTeamRun(
        tenant_id="tenant-a",
        team_id=team_a.id,
        status=TeamRunStatus.RUNNING.value,
        goal_text_snapshot="Tenant A run.",
        topology_snapshot=TeamTopology.LINE.value,
    )
    db_session.add(run_a)
    db_session.add(run_b)
    db_session.commit()

    db_session.add(
        AgentTeamTrigger(
            tenant_id="tenant-a",
            team_id=team_b.id,
            trigger_kind="webhook",
            is_enabled=True,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        AgentTeamRun(
            tenant_id="tenant-a",
            team_id=team_b.id,
            status=TeamRunStatus.PENDING.value,
            goal_text_snapshot="Bad run.",
            topology_snapshot=TeamTopology.LINE.value,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        AgentTeamMemberRun(
            tenant_id="tenant-a",
            team_run_id=run_b.id,
            agent_team_member_id=team_a.members[0].id,
            agent_id=agent_a.id,
            step_index=1,
            status="running",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        AgentTeamMemberRun(
            tenant_id="tenant-a",
            team_run_id=run_a.id,
            agent_team_member_id=team_b.members[0].id,
            agent_id=agent_a.id,
            step_index=1,
            status="running",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        AgentTeamMemberRun(
            tenant_id="tenant-a",
            team_run_id=run_a.id,
            agent_team_member_id=team_a.members[0].id,
            agent_id=agent_b.id,
            step_index=1,
            status="running",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        TeamRunScratch(
            tenant_id="tenant-a",
            team_id=team_a.id,
            team_run_id=run_b.id,
            key="bad",
            value_json={"bad": True},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()

    db_session.add(
        AgentTeamMemberA2ASnapshot(
            tenant_id="tenant-a",
            team_id=team_a.id,
            agent_id=agent_b.id,
            permission_payload_json={"bad": True},
        )
    )
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
