"""Watcher Team Runs API and websocket event tests."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
import types
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

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


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


import models_rbac  # noqa: F401,E402
from api.routes_watcher_team_runs import get_watcher_team_run, list_watcher_team_runs  # noqa: E402
from auth_dependencies import TenantContext  # noqa: E402
from models import (  # noqa: E402
    Agent,
    AgentTeam,
    AgentTeamMember,
    AgentTeamMemberRun,
    AgentTeamRun,
    Base,
    Contact,
    TeamMemberRunStatus,
    TeamRunStatus,
    TeamStatus,
    TeamTopology,
)
from models_rbac import Tenant, User  # noqa: E402
from services.watcher_activity_service import WatcherActivityService, emit_team_run_async  # noqa: E402
from services.team_orchestrator_service import TeamRunOrchestrator  # noqa: E402


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


def _user(tenant_id: str | None = "tenant-a", *, user_id: int = 1, global_admin: bool = False):
    return SimpleNamespace(id=user_id, tenant_id=tenant_id, is_global_admin=global_admin)


def _ctx(db, tenant_id: str | None = "tenant-a", *, user_id: int = 1, global_admin: bool = False) -> TenantContext:
    return TenantContext(_user(tenant_id, user_id=user_id, global_admin=global_admin), db)


def _create_tenant(db, tenant_id: str) -> None:
    db.add(Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=tenant_id, plan="dev"))
    db.add(User(id=1 if tenant_id == "tenant-a" else 2, tenant_id=tenant_id, email=f"{tenant_id}@example.com"))
    db.flush()


def _create_agent(db, *, tenant_id: str, name: str, is_internal: bool = False) -> Agent:
    contact = Contact(friendly_name=name, role="agent", tenant_id=tenant_id, is_active=True)
    db.add(contact)
    db.flush()
    agent = Agent(
        contact_id=contact.id,
        tenant_id=tenant_id,
        system_prompt=f"You are {name}.",
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        is_active=True,
        is_internal=is_internal,
    )
    db.add(agent)
    db.flush()
    return agent


def _create_team_run(
    db,
    *,
    tenant_id: str,
    name: str,
    status: str = TeamRunStatus.COMPLETED.value,
    topology: str = TeamTopology.LINE.value,
    created_at: datetime | None = None,
) -> tuple[AgentTeam, AgentTeamRun, Agent]:
    agent = _create_agent(db, tenant_id=tenant_id, name=f"{name} Agent")
    team = AgentTeam(
        tenant_id=tenant_id,
        name=name,
        goal_text="Handle incident",
        topology=topology,
        status=TeamStatus.ACTIVE.value,
    )
    db.add(team)
    db.flush()
    db.add(
        AgentTeamMember(
            tenant_id=tenant_id,
            team_id=team.id,
            agent_id=agent.id,
            execution_order=1,
        )
    )
    run = AgentTeamRun(
        tenant_id=tenant_id,
        team_id=team.id,
        status=status,
        goal_text_snapshot=team.goal_text,
        topology_snapshot=topology,
        total_steps=1,
        completed_steps=1 if status == TeamRunStatus.COMPLETED.value else 0,
        failed_steps=1 if status == TeamRunStatus.FAILED.value else 0,
        final_output_summary="done" if status == TeamRunStatus.COMPLETED.value else None,
        error_json={"reason": status} if status != TeamRunStatus.COMPLETED.value else None,
        created_at=created_at or datetime.utcnow(),
        started_at=created_at or datetime.utcnow(),
        completed_at=created_at or datetime.utcnow(),
    )
    db.add(run)
    db.flush()
    return team, run, agent


def test_watcher_team_runs_are_tenant_scoped_and_filterable(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    old = datetime.utcnow() - timedelta(days=3)
    new = datetime.utcnow()
    team_a, run_a, _agent_a = _create_team_run(db_session, tenant_id="tenant-a", name="A", created_at=old)
    _team_b, run_b, _agent_b = _create_team_run(
        db_session,
        tenant_id="tenant-b",
        name="B",
        status=TeamRunStatus.FAILED.value,
        created_at=new,
    )
    db_session.commit()

    tenant_list = list_watcher_team_runs(
        limit=50,
        offset=0,
        team_id=None,
        status_filter=None,
        created_after=None,
        created_before=None,
        tenant_id=None,
        ctx=_ctx(db_session, "tenant-a"),
        current_user=_user("tenant-a"),
    )
    assert tenant_list["total"] == 1
    assert tenant_list["items"][0]["id"] == run_a.id
    assert tenant_list["items"][0]["team_name"] == "A"
    assert tenant_list["items"][0]["member_count"] == 1

    filtered = list_watcher_team_runs(
        limit=50,
        offset=0,
        team_id=team_a.id,
        status_filter=TeamRunStatus.COMPLETED.value,
        created_after=old - timedelta(minutes=1),
        created_before=old + timedelta(minutes=1),
        tenant_id=None,
        ctx=_ctx(db_session, "tenant-a"),
        current_user=_user("tenant-a"),
    )
    assert filtered["total"] == 1

    global_filtered = list_watcher_team_runs(
        limit=50,
        offset=0,
        team_id=None,
        status_filter=TeamRunStatus.FAILED.value,
        created_after=None,
        created_before=None,
        tenant_id="tenant-b",
        ctx=_ctx(db_session, None, user_id=99, global_admin=True),
        current_user=_user(None, user_id=99, global_admin=True),
    )
    assert global_filtered["total"] == 1
    assert global_filtered["items"][0]["id"] == run_b.id

    with pytest.raises(HTTPException) as exc:
        get_watcher_team_run(
            run_b.id,
            tenant_id=None,
            ctx=_ctx(db_session, "tenant-a"),
            current_user=_user("tenant-a"),
        )
    assert exc.value.status_code == 404


def test_watcher_team_run_detail_includes_member_sentinel_and_coordinator_data(db_session):
    _create_tenant(db_session, "tenant-a")
    _team, run, agent = _create_team_run(
        db_session,
        tenant_id="tenant-a",
        name="Mesh",
        topology=TeamTopology.MESH.value,
    )
    member = db_session.query(AgentTeamMember).filter(AgentTeamMember.team_id == run.team_id).first()
    command = {"command": "dispatch", "dispatches": [{"member_id": member.id, "message": "Investigate"}]}
    db_session.add(
        AgentTeamMemberRun(
            tenant_id="tenant-a",
            team_run_id=run.id,
            agent_team_member_id=member.id,
            agent_id=agent.id,
            step_index=1,
            status=TeamMemberRunStatus.COMPLETED.value,
            output_summary="coordinator sent work",
            sentinel_decision_json={"stage": "team_handoff", "blocked": False},
            input_context_json={"parsed_summary": {"coordinator_command": command}},
        )
    )
    db_session.commit()

    detail = get_watcher_team_run(
        run.id,
        tenant_id=None,
        ctx=_ctx(db_session, "tenant-a"),
        current_user=_user("tenant-a"),
    )

    assert detail["member_runs"][0]["output_summary"] == "coordinator sent work"
    assert detail["member_runs"][0]["sentinel_decision_json"]["stage"] == "team_handoff"
    assert detail["coordinator_commands"][0]["command"] == command
    assert detail["coordinator_commands"][0]["agent_name"] == "Mesh Agent"


def test_watcher_team_run_event_payload_is_broadcast(monkeypatch):
    service = WatcherActivityService.get_instance()
    service.tenant_connections = {"tenant-a": {object()}}
    events: list[dict] = []

    async def fake_broadcast(tenant_id, message):
        events.append({"tenant_id": tenant_id, **message})

    monkeypatch.setattr(service, "_broadcast_to_tenant", fake_broadcast)

    try:
        asyncio.run(
            service.emit_team_run(
                tenant_id="tenant-a",
                team_run_id=10,
                team_id=5,
                status=TeamRunStatus.SENTINEL_BLOCKED.value,
                event="sentinel_blocked",
                team_name="Security Team",
                member_run_id=21,
                step_index=2,
                agent_id=3,
                agent_name="Reviewer",
                coordinator_command={"command": "finish"},
                error_json={"reason": "sentinel_blocked"},
            )
        )
    finally:
        service.tenant_connections = {}

    assert events == [
        {
            "tenant_id": "tenant-a",
            "type": "team_run",
            "team_run_id": 10,
            "team_id": 5,
            "status": "sentinel_blocked",
            "event": "sentinel_blocked",
            "team_name": "Security Team",
            "member_run_id": 21,
            "step_index": 2,
            "agent_id": 3,
            "agent_name": "Reviewer",
            "coordinator_command": {"command": "finish"},
            "error_json": {"reason": "sentinel_blocked"},
            "timestamp": events[0]["timestamp"],
        }
    ]


def test_team_run_event_schedules_on_registered_watcher_loop(monkeypatch):
    service = WatcherActivityService.get_instance()
    websocket = object()
    loop = asyncio.new_event_loop()
    ready = threading.Event()
    delivered = threading.Event()
    events: list[dict] = []

    def _run_loop():
        asyncio.set_event_loop(loop)
        ready.set()
        loop.run_forever()

    async def fake_emit_team_run(**kwargs):
        events.append(kwargs)
        delivered.set()

    monkeypatch.setattr(service, "emit_team_run", fake_emit_team_run)
    thread = threading.Thread(target=_run_loop, daemon=True)
    thread.start()
    ready.wait(timeout=1)
    service.tenant_connections = {"tenant-a": {websocket}}
    service._connection_loops = {websocket: loop}

    try:
        emit_team_run_async(
            tenant_id="tenant-a",
            team_run_id=11,
            team_id=7,
            status=TeamRunStatus.COMPLETED.value,
            event="goal_achieved",
            team_name="Security Team",
        )
        assert delivered.wait(timeout=1)
    finally:
        service.tenant_connections = {}
        service._connection_loops = {}
        loop.call_soon_threadsafe(loop.stop)
        thread.join(timeout=1)
        loop.close()

    assert events == [
        {
            "tenant_id": "tenant-a",
            "team_run_id": 11,
            "team_id": 7,
            "status": "completed",
            "event": "goal_achieved",
            "team_name": "Security Team",
            "member_run_id": None,
            "step_index": None,
            "agent_id": None,
            "agent_name": None,
            "coordinator_command": None,
            "error_json": None,
        }
    ]


def test_api_cancelled_run_is_not_re_emitted_when_orchestrator_observes_it(db_session, monkeypatch):
    _create_tenant(db_session, "tenant-a")
    team, run, _agent = _create_team_run(
        db_session,
        tenant_id="tenant-a",
        name="Cancel",
        status=TeamRunStatus.CANCELLED.value,
    )
    run.error_json = {"reason": "cancelled_by_user"}
    db_session.commit()
    events: list[str] = []
    orchestrator = TeamRunOrchestrator(db_session, tenant_id="tenant-a", team_id=team.id, existing_run_id=run.id)

    monkeypatch.setattr(
        orchestrator,
        "_emit_team_run_event",
        lambda _team_run, event, **_kwargs: events.append(event),
    )

    assert orchestrator._stop_if_cancelled(run, skipped_members=[], first_skipped_step=1) is True
    assert events == []
