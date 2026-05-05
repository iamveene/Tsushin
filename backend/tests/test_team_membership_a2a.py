"""Phase 4 Agent Team membership A2A snapshot/restore tests."""

import json
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
    AgentCommunicationPermission,
    AgentTeam,
    AgentTeamMember,
    AgentTeamMemberA2ASnapshot,
    Base,
    Contact,
    TeamMemberRole,
    TeamStatus,
    TeamTopology,
)
from models_rbac import Tenant  # noqa: E402
from services.team_membership_service import (  # noqa: E402
    SERVICE_CREATED_GRANT_KIND,
    TeamMembershipError,
    TeamMembershipService,
    serialize_a2a_permission_payload,
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
    tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=tenant_id, plan="dev")
    db_session.add(tenant)
    db_session.flush()
    return tenant


def _create_agent(db_session, *, tenant_id: str, name: str, is_internal: bool = False) -> Agent:
    contact = Contact(friendly_name=name, role="agent", tenant_id=tenant_id, is_active=True)
    db_session.add(contact)
    db_session.flush()
    agent = Agent(
        contact_id=contact.id,
        tenant_id=tenant_id,
        system_prompt=f"You are {name}",
        model_provider="openai",
        model_name="gpt-4o-mini",
        is_active=True,
        is_internal=is_internal,
    )
    db_session.add(agent)
    db_session.flush()
    return agent


def _create_team(db_session, *, tenant_id: str, name: str) -> AgentTeam:
    team = AgentTeam(
        tenant_id=tenant_id,
        name=name,
        topology=TeamTopology.MESH.value,
        status=TeamStatus.ACTIVE.value,
    )
    db_session.add(team)
    db_session.flush()
    return team


def _add_member(
    db_session,
    *,
    tenant_id: str,
    team: AgentTeam,
    agent: Agent,
    role: str = TeamMemberRole.MEMBER.value,
    execution_order: int = 1,
) -> AgentTeamMember:
    member = AgentTeamMember(
        tenant_id=tenant_id,
        team_id=team.id,
        agent_id=agent.id,
        role=role,
        execution_order=execution_order,
        is_required=True,
    )
    db_session.add(member)
    agent.is_team_member = True
    agent.current_team_id = team.id
    db_session.flush()
    return member


def _create_permission(
    db_session,
    *,
    tenant_id: str,
    source: Agent,
    target: Agent,
    is_enabled: bool = True,
    max_depth: int = 3,
    rate_limit_rpm: int = 30,
    allow_target_skills: bool = False,
) -> AgentCommunicationPermission:
    permission = AgentCommunicationPermission(
        tenant_id=tenant_id,
        source_agent_id=source.id,
        target_agent_id=target.id,
        is_enabled=is_enabled,
        max_depth=max_depth,
        rate_limit_rpm=rate_limit_rpm,
        allow_target_skills=allow_target_skills,
    )
    db_session.add(permission)
    db_session.flush()
    return permission


def _payload_bytes(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def test_add_disables_and_snapshots_external_permissions(db_session):
    _create_tenant(db_session, "tenant-a")
    joining_agent = _create_agent(db_session, tenant_id="tenant-a", name="Joining")
    teammate = _create_agent(db_session, tenant_id="tenant-a", name="Teammate")
    outsider = _create_agent(db_session, tenant_id="tenant-a", name="Outsider")
    team = _create_team(db_session, tenant_id="tenant-a", name="Snapshot Team")
    _add_member(db_session, tenant_id="tenant-a", team=team, agent=teammate)
    outbound_external = _create_permission(
        db_session,
        tenant_id="tenant-a",
        source=joining_agent,
        target=outsider,
        max_depth=2,
        rate_limit_rpm=12,
        allow_target_skills=True,
    )
    inbound_external = _create_permission(
        db_session,
        tenant_id="tenant-a",
        source=outsider,
        target=joining_agent,
        max_depth=4,
        rate_limit_rpm=8,
    )
    existing_in_team = _create_permission(
        db_session,
        tenant_id="tenant-a",
        source=joining_agent,
        target=teammate,
        max_depth=5,
        rate_limit_rpm=6,
    )
    expected_payloads = {
        outbound_external.id: serialize_a2a_permission_payload(outbound_external),
        inbound_external.id: serialize_a2a_permission_payload(inbound_external),
    }
    db_session.commit()

    change = TeamMembershipService(db_session, "tenant-a").add_agent_to_team(
        team_id=team.id,
        agent_id=joining_agent.id,
    )

    assert set(change.disabled_permission_ids) == {outbound_external.id, inbound_external.id}
    db_session.refresh(outbound_external)
    db_session.refresh(inbound_external)
    db_session.refresh(existing_in_team)
    assert outbound_external.is_enabled is False
    assert inbound_external.is_enabled is False
    assert existing_in_team.is_enabled is True

    snapshots = (
        db_session.query(AgentTeamMemberA2ASnapshot)
        .filter(
            AgentTeamMemberA2ASnapshot.tenant_id == "tenant-a",
            AgentTeamMemberA2ASnapshot.team_id == team.id,
            AgentTeamMemberA2ASnapshot.agent_id == joining_agent.id,
        )
        .order_by(AgentTeamMemberA2ASnapshot.permission_id)
        .all()
    )
    external_snapshots = [
        snapshot
        for snapshot in snapshots
        if snapshot.permission_payload_json.get("snapshot_kind") != SERVICE_CREATED_GRANT_KIND
    ]
    assert [snapshot.permission_id for snapshot in external_snapshots] == [
        outbound_external.id,
        inbound_external.id,
    ]
    assert {
        snapshot.permission_id: snapshot.permission_payload_json
        for snapshot in external_snapshots
    } == expected_payloads


def test_later_teammate_join_reenables_permission_disabled_by_first_join(db_session):
    _create_tenant(db_session, "tenant-a")
    member_a = _create_agent(db_session, tenant_id="tenant-a", name="Member A")
    member_b = _create_agent(db_session, tenant_id="tenant-a", name="Member B")
    team = _create_team(db_session, tenant_id="tenant-a", name="Sequential Team")
    permission = _create_permission(
        db_session,
        tenant_id="tenant-a",
        source=member_a,
        target=member_b,
        max_depth=7,
        rate_limit_rpm=11,
        allow_target_skills=True,
    )
    db_session.commit()

    service = TeamMembershipService(db_session, "tenant-a")
    service.add_agent_to_team(team_id=team.id, agent_id=member_a.id)
    db_session.refresh(permission)
    assert permission.is_enabled is False

    service.add_agent_to_team(team_id=team.id, agent_id=member_b.id)

    db_session.refresh(permission)
    assert permission.is_enabled is True
    assert permission.max_depth == 7
    assert permission.rate_limit_rpm == 11
    assert permission.allow_target_skills is True


def test_membership_service_can_defer_commit_and_rollback_for_bulk_callers(db_session, monkeypatch):
    _create_tenant(db_session, "tenant-a")
    member = _create_agent(db_session, tenant_id="tenant-a", name="Bulk Member")
    team = _create_team(db_session, tenant_id="tenant-a", name="Bulk Team")
    db_session.commit()
    commit_calls = []
    rollback_calls = []

    def _track_commit():
        commit_calls.append(True)

    def _track_rollback():
        rollback_calls.append(True)

    monkeypatch.setattr(db_session, "commit", _track_commit)
    monkeypatch.setattr(db_session, "rollback", _track_rollback)
    service = TeamMembershipService(db_session, "tenant-a", auto_commit=False)

    change = service.add_agent_to_team(team_id=team.id, agent_id=member.id)
    with pytest.raises(TeamMembershipError, match="agent_not_found_for_tenant"):
        service.add_agent_to_team(team_id=team.id, agent_id=member.id + 999, commit=False)

    assert change.membership_id is not None
    assert commit_calls == []
    assert rollback_calls == []
    assert (
        db_session.query(AgentTeamMember)
        .filter(
            AgentTeamMember.tenant_id == "tenant-a",
            AgentTeamMember.team_id == team.id,
            AgentTeamMember.agent_id == member.id,
        )
        .count()
        == 1
    )


def test_remove_restores_snapshot_payload_byte_equivalently_and_cleans_state(db_session):
    _create_tenant(db_session, "tenant-a")
    joining_agent = _create_agent(db_session, tenant_id="tenant-a", name="Joining")
    teammate = _create_agent(db_session, tenant_id="tenant-a", name="Teammate")
    outsider = _create_agent(db_session, tenant_id="tenant-a", name="Outsider")
    team = _create_team(db_session, tenant_id="tenant-a", name="Restore Team")
    _add_member(db_session, tenant_id="tenant-a", team=team, agent=teammate)
    external_permission = _create_permission(
        db_session,
        tenant_id="tenant-a",
        source=joining_agent,
        target=outsider,
        max_depth=2,
        rate_limit_rpm=12,
        allow_target_skills=True,
    )
    original_payload_bytes = _payload_bytes(serialize_a2a_permission_payload(external_permission))
    db_session.commit()

    TeamMembershipService(db_session, "tenant-a").add_agent_to_team(
        team_id=team.id,
        agent_id=joining_agent.id,
    )
    external_permission.max_depth = 99
    external_permission.rate_limit_rpm = 1
    external_permission.allow_target_skills = False
    db_session.commit()

    change = TeamMembershipService(db_session, "tenant-a").remove_agent_from_team(
        team_id=team.id,
        agent_id=joining_agent.id,
    )

    db_session.refresh(external_permission)
    db_session.refresh(joining_agent)
    assert change.restored_permission_ids == (external_permission.id,)
    assert _payload_bytes(serialize_a2a_permission_payload(external_permission)) == original_payload_bytes
    assert joining_agent.is_team_member is False
    assert joining_agent.current_team_id is None
    assert (
        db_session.query(AgentTeamMember)
        .filter(
            AgentTeamMember.tenant_id == "tenant-a",
            AgentTeamMember.team_id == team.id,
            AgentTeamMember.agent_id == joining_agent.id,
        )
        .count()
        == 0
    )
    assert (
        db_session.query(AgentTeamMemberA2ASnapshot)
        .filter(
            AgentTeamMemberA2ASnapshot.tenant_id == "tenant-a",
            AgentTeamMemberA2ASnapshot.team_id == team.id,
            AgentTeamMemberA2ASnapshot.agent_id == joining_agent.id,
        )
        .count()
        == 0
    )
    assert (
        db_session.query(AgentCommunicationPermission)
        .filter(
            AgentCommunicationPermission.tenant_id == "tenant-a",
            AgentCommunicationPermission.source_agent_id == joining_agent.id,
            AgentCommunicationPermission.target_agent_id == teammate.id,
        )
        .count()
        == 0
    )


def test_in_team_grants_are_idempotent_and_only_service_created_grants_are_removed(db_session):
    _create_tenant(db_session, "tenant-a")
    member_a = _create_agent(db_session, tenant_id="tenant-a", name="Member A")
    member_b = _create_agent(db_session, tenant_id="tenant-a", name="Member B")
    member_c = _create_agent(db_session, tenant_id="tenant-a", name="Member C")
    team = _create_team(db_session, tenant_id="tenant-a", name="Grant Team")
    _add_member(db_session, tenant_id="tenant-a", team=team, agent=member_a, execution_order=1)
    _add_member(db_session, tenant_id="tenant-a", team=team, agent=member_c, execution_order=2)
    manual_permission = _create_permission(
        db_session,
        tenant_id="tenant-a",
        source=member_a,
        target=member_b,
        max_depth=7,
        rate_limit_rpm=11,
    )
    db_session.commit()

    service = TeamMembershipService(db_session, "tenant-a")
    first_change = service.add_agent_to_team(team_id=team.id, agent_id=member_b.id)
    second_change = service.add_agent_to_team(team_id=team.id, agent_id=member_b.id)

    permissions = (
        db_session.query(AgentCommunicationPermission)
        .filter(AgentCommunicationPermission.tenant_id == "tenant-a")
        .all()
    )
    assert len(permissions) == 6
    assert second_change.created_in_team_permission_ids == ()
    db_session.refresh(manual_permission)
    assert manual_permission.max_depth == 7
    assert manual_permission.rate_limit_rpm == 11

    service_created_markers = [
        snapshot
        for snapshot in db_session.query(AgentTeamMemberA2ASnapshot)
        .filter(AgentTeamMemberA2ASnapshot.tenant_id == "tenant-a")
        .all()
        if snapshot.permission_payload_json.get("snapshot_kind") == SERVICE_CREATED_GRANT_KIND
    ]
    assert len(service_created_markers) == len(first_change.created_in_team_permission_ids)
    assert len(service_created_markers) == 5

    remove_change = service.remove_agent_from_team(team_id=team.id, agent_id=member_b.id)

    db_session.refresh(manual_permission)
    remaining_pairs = {
        (permission.source_agent_id, permission.target_agent_id)
        for permission in db_session.query(AgentCommunicationPermission)
        .filter(AgentCommunicationPermission.tenant_id == "tenant-a")
        .all()
    }
    assert manual_permission.id not in remove_change.removed_in_team_permission_ids
    assert (member_a.id, member_b.id) in remaining_pairs
    assert (member_a.id, member_c.id) in remaining_pairs
    assert (member_c.id, member_a.id) in remaining_pairs
    assert (member_b.id, member_a.id) not in remaining_pairs
    assert (member_b.id, member_c.id) not in remaining_pairs
    assert (member_c.id, member_b.id) not in remaining_pairs


def test_membership_service_rejects_cross_tenant_team_and_agent(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agent_a = _create_agent(db_session, tenant_id="tenant-a", name="Tenant A Agent")
    agent_b = _create_agent(db_session, tenant_id="tenant-b", name="Tenant B Agent")
    team_a = _create_team(db_session, tenant_id="tenant-a", name="Tenant A Team")
    team_b = _create_team(db_session, tenant_id="tenant-b", name="Tenant B Team")
    db_session.commit()

    service = TeamMembershipService(db_session, "tenant-a")
    with pytest.raises(TeamMembershipError, match="agent_not_found_for_tenant"):
        service.add_agent_to_team(team_id=team_a.id, agent_id=agent_b.id)
    with pytest.raises(TeamMembershipError, match="team_not_found_for_tenant"):
        service.add_agent_to_team(team_id=team_b.id, agent_id=agent_a.id)


def test_membership_service_refuses_internal_coordinator_members(db_session):
    _create_tenant(db_session, "tenant-a")
    coordinator = _create_agent(db_session, tenant_id="tenant-a", name="Coordinator", is_internal=True)
    team = _create_team(db_session, tenant_id="tenant-a", name="Coordinator Team")
    team.coordinator_agent_id = coordinator.id
    db_session.commit()

    with pytest.raises(TeamMembershipError, match="internal_coordinator_cannot_be_user_member"):
        TeamMembershipService(db_session, "tenant-a").add_agent_to_team(
            team_id=team.id,
            agent_id=coordinator.id,
        )
