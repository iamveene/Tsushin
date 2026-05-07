"""Agent Teams Phase 5 CRUD API tests."""

from __future__ import annotations

import os
import sys
import types
import asyncio
from types import SimpleNamespace

import pytest
from fastapi import BackgroundTasks, HTTPException
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


import models_rbac  # noqa: F401
from api.api_auth import ApiCaller  # noqa: E402
from api.routes_teams import (  # noqa: E402
    add_member,
    archive_team,
    cancel_team_run,
    create_team,
    delete_team_permanently,
    get_team,
    get_team_run,
    list_teams,
    list_team_runs,
    remove_member,
    reorder_members,
    start_team_run,
    create_team_trigger_binding,
    delete_team_trigger_binding,
    update_member,
    update_team_trigger_binding,
    update_team,
)
from api.schemas.teams import TeamCreate, TeamMemberAdd, TeamMemberOrderUpdate, TeamMemberPatch, TeamTriggerCreate, TeamTriggerUpdate, TeamUpdate  # noqa: E402
from api.v1.routes_teams import (  # noqa: E402
    create_team_trigger_binding as create_v1_team_trigger_binding,
    delete_team_trigger_binding as delete_v1_team_trigger_binding,
    list_teams as list_v1_teams,
    update_member as update_v1_member,
    update_team_trigger_binding as update_v1_team_trigger_binding,
)
from auth_dependencies import TenantContext  # noqa: E402
from models import (  # noqa: E402
    Agent,
    AgentCommunicationPermission,
    AgentTeam,
    AgentTeamMember,
    AgentTeamMemberRun,
    AgentTeamRun,
    AgentTeamTrigger,
    Base,
    Contact,
    EmailChannelInstance,
    GitHubChannelInstance,
    GitHubIntegration,
    JiraChannelInstance,
    SentinelProfile,
    TeamMemberRole,
    TeamMemberRunStatus,
    TeamRunStatus,
    TeamStatus,
    TeamTopology,
    WebhookIntegration,
)
from models_rbac import Tenant, User  # noqa: E402


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


def _create_tenant(db, tenant_id: str) -> Tenant:
    tenant = Tenant(id=tenant_id, name=f"Tenant {tenant_id}", slug=tenant_id, plan="dev")
    db.add(tenant)
    db.flush()
    user = User(id=1 if tenant_id == "tenant-a" else 2, tenant_id=tenant_id, email=f"{tenant_id}@example.com")
    db.add(user)
    db.flush()
    return tenant


def _user(tenant_id: str = "tenant-a", user_id: int = 1):
    return SimpleNamespace(id=user_id, tenant_id=tenant_id, is_global_admin=False)


def _ctx(db, tenant_id: str = "tenant-a", user_id: int = 1) -> TenantContext:
    return TenantContext(user=_user(tenant_id, user_id), db=db)


def _caller(tenant_id: str = "tenant-a", user_id: int = 1) -> ApiCaller:
    return ApiCaller(
        tenant_id=tenant_id,
        user_id=user_id,
        permissions={"agents.read", "agents.write", "agents.delete", "agents.execute"},
    )


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


def _create_webhook_trigger(db, *, tenant_id: str = "tenant-a", trigger_id: int | None = None, is_active: bool = True) -> WebhookIntegration:
    trigger = WebhookIntegration(
        id=trigger_id,
        tenant_id=tenant_id,
        integration_name=f"Webhook {trigger_id or 'new'}",
        slug=f"wh-{tenant_id}-{trigger_id or 'new'}",
        api_secret_encrypted="secret",
        api_secret_preview="secret...",
        is_active=is_active,
        status="active" if is_active else "paused",
        created_by=1 if tenant_id == "tenant-a" else 2,
    )
    db.add(trigger)
    db.flush()
    return trigger


def _create_jira_trigger(db, *, tenant_id: str = "tenant-a", trigger_id: int | None = None, is_active: bool = True) -> JiraChannelInstance:
    trigger = JiraChannelInstance(
        id=trigger_id,
        tenant_id=tenant_id,
        integration_name=f"Jira {trigger_id or 'new'}",
        site_url="https://example.atlassian.net",
        project_key="QA",
        jql="project = QA",
        is_active=is_active,
        status="active" if is_active else "paused",
        created_by=1 if tenant_id == "tenant-a" else 2,
    )
    db.add(trigger)
    db.flush()
    return trigger


def _create_email_trigger(db, *, tenant_id: str = "tenant-a", trigger_id: int | None = None, is_active: bool = True) -> EmailChannelInstance:
    trigger = EmailChannelInstance(
        id=trigger_id,
        tenant_id=tenant_id,
        integration_name=f"Email {trigger_id or 'new'}",
        provider="gmail",
        search_query="is:unread",
        poll_interval_seconds=60,
        is_active=is_active,
        status="active" if is_active else "paused",
        created_by=1 if tenant_id == "tenant-a" else 2,
    )
    db.add(trigger)
    db.flush()
    return trigger


def _create_github_trigger(db, *, tenant_id: str = "tenant-a", trigger_id: int | None = None, is_active: bool = True) -> GitHubChannelInstance:
    integration = GitHubIntegration(
        tenant_id=tenant_id,
        name=f"GitHub {trigger_id or 'new'}",
        display_name=f"GitHub {trigger_id or 'new'}",
        is_active=True,
        provider="github",
    )
    db.add(integration)
    db.flush()
    trigger = GitHubChannelInstance(
        id=trigger_id,
        tenant_id=tenant_id,
        integration_name=f"GitHub Trigger {trigger_id or 'new'}",
        github_integration_id=integration.id,
        repo_owner="owner",
        repo_name="repo",
        events=["push"],
        is_active=is_active,
        status="active" if is_active else "paused",
        created_by=1 if tenant_id == "tenant-a" else 2,
    )
    db.add(trigger)
    db.flush()
    return trigger


def _create_sentinel_profile(
    db,
    *,
    tenant_id: str | None,
    name: str,
    profile_id: int | None = None,
    is_system: bool = False,
) -> SentinelProfile:
    profile = SentinelProfile(
        id=profile_id,
        tenant_id=tenant_id,
        name=name,
        slug=name.lower().replace(" ", "-"),
        description=f"{name} profile",
        is_system=is_system,
        is_default=False,
        is_enabled=True,
        detection_mode="block",
        okg_detection_mode="block",
        aggressiveness_level=1,
        detection_overrides="{}",
    )
    db.add(profile)
    db.flush()
    return profile


async def _create_active_team(db, agents: list[Agent], name: str = "QA Team") -> dict:
    return await create_team(
        payload=TeamCreate(
            name=name,
            goal_text="Triage incoming issues",
            topology=TeamTopology.LINE.value,
            status=TeamStatus.ACTIVE.value,
            members=[
                {"agent_id": agent.id, "execution_order": index}
                for index, agent in enumerate(agents, start=1)
            ],
        ),
        ctx=_ctx(db),
        current_user=_user(),
    )


def _run(coro):
    return asyncio.run(coro)


def test_legacy_and_v1_team_crud_list_and_detail(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="Researcher"),
        _create_agent(db_session, tenant_id="tenant-a", name="Reviewer"),
    ]

    created = _run(_create_active_team(db_session, agents))
    assert created["status"] == TeamStatus.ACTIVE.value
    assert created["member_count"] == 2
    assert [member["agent_id"] for member in created["members"]] == [agent.id for agent in agents]
    assert db_session.get(Agent, agents[0].id).is_team_member is True

    listed = _run(
        list_teams(
            status_filter=None,
            include_archived=False,
            page=1,
            page_size=20,
            ctx=_ctx(db_session),
            current_user=_user(),
        )
    )
    assert listed["total"] == 1
    assert listed["items"][0]["id"] == created["id"]

    detail = _run(get_team(created["id"], ctx=_ctx(db_session), current_user=_user()))
    assert "tools" not in detail
    assert detail["triggers"] == []

    v1 = _run(
        list_v1_teams(
            status_filter=None,
            include_archived=False,
            page=1,
            per_page=20,
            db=db_session,
            caller=_caller(),
        )
    )
    assert v1["meta"]["total"] == 1
    assert v1["data"][0]["id"] == created["id"]


def test_team_routes_are_tenant_scoped(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agent_a = _create_agent(db_session, tenant_id="tenant-a", name="A")
    created = _run(_create_active_team(db_session, [agent_a]))

    with pytest.raises(HTTPException) as exc:
        _run(get_team(created["id"], ctx=_ctx(db_session, "tenant-b", 2), current_user=_user("tenant-b", 2)))
    assert exc.value.status_code == 404

    v1 = _run(
        list_v1_teams(
            status_filter=None,
            include_archived=False,
            page=1,
            per_page=20,
            db=db_session,
            caller=_caller("tenant-b", 2),
        )
    )
    assert v1["meta"]["total"] == 0


def test_create_validates_active_ready_and_duplicate_members(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="A")

    with pytest.raises(HTTPException) as active_exc:
        _run(create_team(
            payload=TeamCreate(name="No Goal", status=TeamStatus.ACTIVE.value, members=[{"agent_id": agent.id}]),
            ctx=_ctx(db_session),
            current_user=_user(),
        ))
    assert active_exc.value.status_code == 422

    with pytest.raises(HTTPException) as duplicate_exc:
        _run(create_team(
            payload=TeamCreate(
                name="Dupes",
                goal_text="Goal",
                status=TeamStatus.ACTIVE.value,
                members=[{"agent_id": agent.id}, {"agent_id": agent.id}],
            ),
            ctx=_ctx(db_session),
            current_user=_user(),
        ))
    assert duplicate_exc.value.status_code == 422

    with pytest.raises(HTTPException) as archived_exc:
        _run(create_team(
            payload=TeamCreate(name="Archived", status=TeamStatus.ARCHIVED.value),
            ctx=_ctx(db_session),
            current_user=_user(),
        ))
    assert archived_exc.value.status_code == 422


def test_member_add_conflict_and_reorder(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="A"),
        _create_agent(db_session, tenant_id="tenant-a", name="B"),
        _create_agent(db_session, tenant_id="tenant-a", name="C"),
    ]
    created = _run(_create_active_team(db_session, agents[:2]))
    second_team = _run(create_team(
        payload=TeamCreate(name="Other", goal_text="Goal", status=TeamStatus.DRAFT.value),
        ctx=_ctx(db_session),
        current_user=_user(),
    ))

    with pytest.raises(HTTPException) as conflict_exc:
        _run(add_member(
            second_team["id"],
            payload=TeamMemberAdd(agent_id=agents[0].id),
            ctx=_ctx(db_session),
            current_user=_user(),
        ))
    assert conflict_exc.value.status_code == 409

    added = _run(add_member(
        created["id"],
        payload=TeamMemberAdd(agent_id=agents[2].id, execution_order=3),
        ctx=_ctx(db_session),
        current_user=_user(),
    ))
    assert added["agent_id"] == agents[2].id

    reordered = _run(reorder_members(
        created["id"],
        payload=TeamMemberOrderUpdate(
            members=[
                {"agent_id": agents[2].id, "execution_order": 1},
                {"agent_id": agents[0].id, "execution_order": 2},
                {"agent_id": agents[1].id, "execution_order": 3},
            ]
        ),
        ctx=_ctx(db_session),
        current_user=_user(),
    ))
    assert [member["agent_id"] for member in reordered["members"]] == [agents[2].id, agents[0].id, agents[1].id]

    with pytest.raises(HTTPException) as update_archived_exc:
        _run(update_team(
            created["id"],
            payload=TeamUpdate(status=TeamStatus.ARCHIVED.value),
            ctx=_ctx(db_session),
            current_user=_user(),
        ))
    assert update_archived_exc.value.status_code == 422

    _run(remove_member(created["id"], agents[2].id, ctx=_ctx(db_session), current_user=_user()))
    assert db_session.get(Agent, agents[2].id).is_team_member is False


def test_member_patch_updates_layout_and_v1_mirror_blocks_active_runs(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="A"),
        _create_agent(db_session, tenant_id="tenant-a", name="B"),
    ]
    created = _run(_create_active_team(db_session, agents))

    updated = _run(
        update_member(
            created["id"],
            agents[0].id,
            payload=TeamMemberPatch(position_x=42.5, position_y=-7.25, is_required=False, execution_order=9),
            ctx=_ctx(db_session),
            current_user=_user(),
        )
    )
    assert updated["position_x"] == 42.5
    assert updated["position_y"] == -7.25
    assert updated["is_required"] is False
    assert updated["execution_order"] == 9

    v1_updated = _run(
        update_v1_member(
            created["id"],
            agents[0].id,
            payload=TeamMemberPatch(position_x=None, position_y=100.0),
            db=db_session,
            caller=_caller(),
        )
    )
    assert v1_updated["position_x"] is None
    assert v1_updated["position_y"] == 100.0

    db_session.add(
        AgentTeamRun(
            tenant_id="tenant-a",
            team_id=created["id"],
            status=TeamRunStatus.RUNNING.value,
            goal_text_snapshot="Goal",
            topology_snapshot=TeamTopology.LINE.value,
        )
    )
    db_session.commit()

    with pytest.raises(HTTPException) as active_exc:
        _run(
            update_member(
                created["id"],
                agents[0].id,
                payload=TeamMemberPatch(position_x=1.0),
                ctx=_ctx(db_session),
                current_user=_user(),
            )
        )
    assert active_exc.value.status_code == 409


def test_team_sentinel_profile_validation_and_serialization(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="A")
    tenant_profile = _create_sentinel_profile(db_session, tenant_id="tenant-a", name="Team Moderate")
    system_profile = _create_sentinel_profile(db_session, tenant_id=None, name="System Moderate", is_system=True)
    foreign_profile = _create_sentinel_profile(db_session, tenant_id="tenant-b", name="Foreign Moderate")
    db_session.commit()

    created = _run(
        create_team(
            payload=TeamCreate(
                name="Profiled Team",
                goal_text="Goal",
                status=TeamStatus.ACTIVE.value,
                sentinel_profile_id=tenant_profile.id,
                members=[{"agent_id": agent.id}],
            ),
            ctx=_ctx(db_session),
            current_user=_user(),
        )
    )
    assert created["sentinel_profile_id"] == tenant_profile.id

    listed = _run(list_teams(page=1, page_size=20, status_filter=None, include_archived=False, ctx=_ctx(db_session), current_user=_user()))
    assert listed["items"][0]["sentinel_profile_id"] == tenant_profile.id

    updated = _run(
        update_team(
            created["id"],
            payload=TeamUpdate(sentinel_profile_id=system_profile.id),
            ctx=_ctx(db_session),
            current_user=_user(),
        )
    )
    assert updated["sentinel_profile_id"] == system_profile.id

    cleared = _run(update_team(created["id"], payload=TeamUpdate(sentinel_profile_id=None), ctx=_ctx(db_session), current_user=_user()))
    assert cleared["sentinel_profile_id"] is None

    with pytest.raises(HTTPException) as foreign_exc:
        _run(
            update_team(
                created["id"],
                payload=TeamUpdate(sentinel_profile_id=foreign_profile.id),
                ctx=_ctx(db_session),
                current_user=_user(),
            )
        )
    assert foreign_exc.value.status_code == 404


def test_active_team_rejects_removing_last_visible_member(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Solo")
    created = _run(_create_active_team(db_session, [agent]))

    with pytest.raises(HTTPException) as exc:
        _run(remove_member(created["id"], agent.id, ctx=_ctx(db_session), current_user=_user()))

    assert exc.value.status_code == 409
    assert db_session.get(Agent, agent.id).is_team_member is True


def test_archive_refuses_active_run_and_restores_membership(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="A"),
        _create_agent(db_session, tenant_id="tenant-a", name="B"),
    ]
    team = _run(_create_active_team(db_session, agents))
    run = AgentTeamRun(
        tenant_id="tenant-a",
        team_id=team["id"],
        status=TeamRunStatus.RUNNING.value,
        goal_text_snapshot="Goal",
        topology_snapshot=TeamTopology.LINE.value,
    )
    db_session.add(run)
    db_session.commit()

    with pytest.raises(HTTPException) as active_exc:
        _run(archive_team(team["id"], ctx=_ctx(db_session), current_user=_user()))
    assert active_exc.value.status_code == 409

    run.status = TeamRunStatus.COMPLETED.value
    db_session.commit()
    _run(archive_team(team["id"], ctx=_ctx(db_session), current_user=_user()))

    archived = db_session.get(AgentTeam, team["id"])
    assert archived.status == TeamStatus.ARCHIVED.value
    assert db_session.query(AgentTeamMember).filter(AgentTeamMember.team_id == team["id"]).count() == 0
    assert db_session.get(Agent, agents[0].id).is_team_member is False


def test_permanent_delete_refuses_non_archived_team(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [_create_agent(db_session, tenant_id="tenant-a", name="A")]
    team = _run(_create_active_team(db_session, agents))

    with pytest.raises(HTTPException) as exc:
        _run(delete_team_permanently(team["id"], ctx=_ctx(db_session), current_user=_user()))
    assert exc.value.status_code == 409
    assert db_session.get(AgentTeam, team["id"]) is not None


def test_permanent_delete_archived_team_cascades(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [
        _create_agent(db_session, tenant_id="tenant-a", name="A"),
        _create_agent(db_session, tenant_id="tenant-a", name="B"),
    ]
    team = _run(_create_active_team(db_session, agents))
    webhook = _create_webhook_trigger(db_session, trigger_id=901)
    db_session.commit()
    binding = _run(
        create_team_trigger_binding(
            team["id"],
            payload=TeamTriggerCreate(
                trigger_kind="webhook",
                trigger_instance_id=webhook.id,
                event_types=["payload.received"],
            ),
            ctx=_ctx(db_session),
            current_user=_user(),
        )
    )
    run = AgentTeamRun(
        tenant_id="tenant-a",
        team_id=team["id"],
        status=TeamRunStatus.COMPLETED.value,
        goal_text_snapshot="Goal",
        topology_snapshot=TeamTopology.LINE.value,
    )
    db_session.add(run)
    db_session.flush()
    member = db_session.query(AgentTeamMember).filter(AgentTeamMember.team_id == team["id"]).first()
    db_session.add(
        AgentTeamMemberRun(
            tenant_id="tenant-a",
            team_run_id=run.id,
            agent_team_member_id=member.id,
            agent_id=agents[0].id,
            step_index=1,
            status=TeamMemberRunStatus.COMPLETED.value,
        )
    )
    db_session.commit()
    run_id = run.id

    _run(archive_team(team["id"], ctx=_ctx(db_session), current_user=_user()))
    _run(delete_team_permanently(team["id"], ctx=_ctx(db_session), current_user=_user()))

    assert db_session.get(AgentTeam, team["id"]) is None
    assert db_session.get(AgentTeamTrigger, binding["id"]) is None
    assert db_session.get(AgentTeamRun, run_id) is None
    assert db_session.query(AgentTeamMemberRun).filter(AgentTeamMemberRun.team_run_id == run_id).count() == 0
    assert db_session.query(AgentTeamMember).filter(AgentTeamMember.team_id == team["id"]).count() == 0
    for agent in agents:
        refreshed = db_session.get(Agent, agent.id)
        assert refreshed.current_team_id is None


def test_permanent_delete_clears_lingering_members(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [_create_agent(db_session, tenant_id="tenant-a", name="A")]
    team = _run(_create_active_team(db_session, agents))
    _run(archive_team(team["id"], ctx=_ctx(db_session), current_user=_user()))

    stray_agent = _create_agent(db_session, tenant_id="tenant-a", name="Stray")
    db_session.add(
        AgentTeamMember(
            tenant_id="tenant-a",
            team_id=team["id"],
            agent_id=stray_agent.id,
            role=TeamMemberRole.MEMBER.value,
            execution_order=1,
        )
    )
    db_session.commit()
    assert db_session.query(AgentTeamMember).filter(AgentTeamMember.team_id == team["id"]).count() == 1

    _run(delete_team_permanently(team["id"], ctx=_ctx(db_session), current_user=_user()))

    assert db_session.get(AgentTeam, team["id"]) is None
    assert db_session.query(AgentTeamMember).filter(AgentTeamMember.team_id == team["id"]).count() == 0


def test_permanent_delete_tenant_isolation(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agents = [_create_agent(db_session, tenant_id="tenant-a", name="A")]
    team = _run(_create_active_team(db_session, agents))
    _run(archive_team(team["id"], ctx=_ctx(db_session), current_user=_user()))

    with pytest.raises(HTTPException) as exc:
        _run(
            delete_team_permanently(
                team["id"],
                ctx=_ctx(db_session, tenant_id="tenant-b", user_id=2),
                current_user=_user(tenant_id="tenant-b", user_id=2),
            )
        )
    assert exc.value.status_code == 404
    assert db_session.get(AgentTeam, team["id"]) is not None


def test_run_precreate_cancel_and_detail_timeline(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [_create_agent(db_session, tenant_id="tenant-a", name="A")]
    team = _run(_create_active_team(db_session, agents))

    started = _run(start_team_run(
        team["id"],
        background_tasks=BackgroundTasks(),
        ctx=_ctx(db_session),
        current_user=_user(),
    ))
    assert started["status"] == TeamRunStatus.PENDING.value
    run_id = started["run_id"]

    cancelled = _run(cancel_team_run(run_id=run_id, team_id=team["id"], ctx=_ctx(db_session), current_user=_user()))
    assert cancelled["status"] == "cancelled"

    run = db_session.get(AgentTeamRun, run_id)
    member = db_session.query(AgentTeamMember).filter(AgentTeamMember.team_id == team["id"]).first()
    db_session.add(
        AgentTeamMemberRun(
            tenant_id="tenant-a",
            team_run_id=run.id,
            agent_team_member_id=member.id,
            agent_id=agents[0].id,
            step_index=1,
            status=TeamMemberRunStatus.COMPLETED.value,
            output_summary="done",
        )
    )
    db_session.commit()

    detail = _run(get_team_run(team_id=team["id"], run_id=run_id, ctx=_ctx(db_session), current_user=_user()))
    assert detail["member_runs"][0]["output_summary"] == "done"

    runs = _run(list_team_runs(team_id=team["id"], page=1, page_size=20, ctx=_ctx(db_session), current_user=_user()))
    assert runs["total"] == 1


def test_max_concurrent_runs_counts_active_runs(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [_create_agent(db_session, tenant_id="tenant-a", name="A")]
    team = _run(
        create_team(
            payload=TeamCreate(
                name="Parallel QA",
                goal_text="Run bounded parallel checks",
                status=TeamStatus.ACTIVE.value,
                max_concurrent_runs=2,
                members=[{"agent_id": agents[0].id}],
            ),
            ctx=_ctx(db_session),
            current_user=_user(),
        )
    )

    first = _run(start_team_run(team["id"], background_tasks=BackgroundTasks(), ctx=_ctx(db_session), current_user=_user()))
    second = _run(start_team_run(team["id"], background_tasks=BackgroundTasks(), ctx=_ctx(db_session), current_user=_user()))
    assert {first["status"], second["status"]} == {TeamRunStatus.PENDING.value}

    with pytest.raises(HTTPException) as exc:
        _run(start_team_run(team["id"], background_tasks=BackgroundTasks(), ctx=_ctx(db_session), current_user=_user()))
    assert exc.value.status_code == 409

    db_session.get(AgentTeamRun, first["run_id"]).status = TeamRunStatus.COMPLETED.value
    db_session.commit()
    third = _run(start_team_run(team["id"], background_tasks=BackgroundTasks(), ctx=_ctx(db_session), current_user=_user()))
    assert third["status"] == TeamRunStatus.PENDING.value


def test_team_trigger_binding_crud_and_canonical_config_across_prefixes(db_session):
    _create_tenant(db_session, "tenant-a")
    agents = [_create_agent(db_session, tenant_id="tenant-a", name="A")]
    team = _run(_create_active_team(db_session, agents))
    webhook = _create_webhook_trigger(db_session, trigger_id=101)
    github = _create_github_trigger(db_session, trigger_id=102)
    jira = _create_jira_trigger(db_session, trigger_id=103)
    db_session.commit()

    created = _run(
        create_team_trigger_binding(
            team["id"],
            payload=TeamTriggerCreate(
                trigger_kind="webhook",
                trigger_instance_id=webhook.id,
                event_types=["payload.received", "payload.received", " "],
                filters={"severity": "high"},
            ),
            ctx=_ctx(db_session),
            current_user=_user(),
        )
    )
    assert created["trigger_kind"] == "webhook"
    assert created["trigger_instance_id"] == webhook.id
    assert created["event_types"] == ["payload.received"]
    assert created["config_json"] == {
        "trigger_instance_id": webhook.id,
        "event_types": ["payload.received"],
        "filters": {"severity": "high"},
        "is_enabled": True,
    }

    updated = _run(
        update_v1_team_trigger_binding(
            team["id"],
            created["id"],
            payload=TeamTriggerUpdate(
                trigger_instance_id=webhook.id,
                event_types=["payload.updated"],
                filters={"severity": "medium"},
                is_enabled=False,
            ),
            db=db_session,
            caller=_caller(),
        )
    )
    assert updated["config_json"] == {
        "trigger_instance_id": webhook.id,
        "event_types": ["payload.updated"],
        "filters": {"severity": "medium"},
        "is_enabled": False,
    }
    assert db_session.get(AgentTeamTrigger, created["id"]).is_enabled is False

    github_binding = _run(
        create_v1_team_trigger_binding(
            team["id"],
            payload=TeamTriggerCreate(trigger_kind="github", trigger_instance_id=github.id, event_types=["push"]),
            db=db_session,
            caller=_caller(),
        )
    )
    jira_binding = _run(
        create_team_trigger_binding(
            team["id"],
            payload=TeamTriggerCreate(trigger_kind="jira", trigger_instance_id=jira.id, event_types=["issue.updated"]),
            ctx=_ctx(db_session),
            current_user=_user(),
        )
    )
    assert github_binding["trigger_instance_id"] == github.id
    assert jira_binding["trigger_instance_id"] == jira.id

    _run(delete_team_trigger_binding(team["id"], created["id"], ctx=_ctx(db_session), current_user=_user()))
    _run(delete_v1_team_trigger_binding(team["id"], github_binding["id"], db=db_session, caller=_caller()))
    assert db_session.get(AgentTeamTrigger, created["id"]) is None
    assert db_session.get(AgentTeamTrigger, github_binding["id"]) is None


def test_team_trigger_binding_rejects_foreign_and_inactive_triggers(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="A")
    team = _run(_create_active_team(db_session, [agent]))
    inactive_webhook = _create_webhook_trigger(db_session, trigger_id=201, is_active=False)
    foreign_jira = _create_jira_trigger(db_session, tenant_id="tenant-b", trigger_id=202)
    db_session.commit()

    with pytest.raises(HTTPException) as inactive_exc:
        _run(
            create_team_trigger_binding(
                team["id"],
                payload=TeamTriggerCreate(trigger_kind="webhook", trigger_instance_id=inactive_webhook.id),
                ctx=_ctx(db_session),
                current_user=_user(),
            )
        )
    assert inactive_exc.value.status_code == 404

    with pytest.raises(HTTPException) as foreign_exc:
        _run(
            create_team_trigger_binding(
                team["id"],
                payload=TeamTriggerCreate(trigger_kind="jira", trigger_instance_id=foreign_jira.id),
                ctx=_ctx(db_session),
                current_user=_user(),
            )
        )
    assert foreign_exc.value.status_code == 404

    # BUG-731 regression: Gmail bindings with no matching EmailChannelInstance
    # must 404 like every other kind, NOT 422 (which previously meant
    # "Gmail is not supported for teams" — that gate has been removed).
    with pytest.raises(HTTPException) as missing_exc:
        _run(
            create_team_trigger_binding(
                team["id"],
                payload=TeamTriggerCreate(trigger_kind="gmail", trigger_instance_id=99999),
                ctx=_ctx(db_session),
                current_user=_user(),
            )
        )
    assert missing_exc.value.status_code == 404


@pytest.mark.parametrize(
    "kind,fixture",
    [
        ("webhook", "_create_webhook_trigger"),
        ("github", "_create_github_trigger"),
        ("jira", "_create_jira_trigger"),
        ("gmail", "_create_email_trigger"),
    ],
)
def test_team_trigger_binding_supports_every_team_trigger_kind(db_session, kind, fixture):
    """BUG-731 regression: every TeamTriggerKind value must be bindable.

    Previously `gmail` was rejected at the API layer with 422 even though the
    enum advertised it. This test asserts the full matrix end-to-end so a
    future regression can't silently re-introduce a hard-coded reject branch.
    """
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name=f"A-{kind}")
    team = _run(_create_active_team(db_session, [agent]))
    trigger = globals()[fixture](db_session, tenant_id="tenant-a")
    db_session.commit()

    binding = _run(
        create_team_trigger_binding(
            team["id"],
            payload=TeamTriggerCreate(trigger_kind=kind, trigger_instance_id=trigger.id),
            ctx=_ctx(db_session),
            current_user=_user(),
        )
    )
    assert binding["trigger_kind"] == kind
    assert binding["trigger_instance_id"] == trigger.id
    assert binding["is_enabled"] is True

    persisted = db_session.get(AgentTeamTrigger, binding["id"])
    assert persisted is not None
    assert persisted.trigger_kind == kind


def test_hidden_coordinator_members_are_not_returned(db_session):
    _create_tenant(db_session, "tenant-a")
    visible = _create_agent(db_session, tenant_id="tenant-a", name="Visible")
    hidden = _create_agent(db_session, tenant_id="tenant-a", name="Coordinator", is_internal=True)
    created = _run(_create_active_team(db_session, [visible]))
    db_session.add(
        AgentTeamMember(
            tenant_id="tenant-a",
            team_id=created["id"],
            agent_id=hidden.id,
            role=TeamMemberRole.COORDINATOR.value,
            execution_order=0,
        )
    )
    db_session.commit()

    detail = _run(get_team(created["id"], ctx=_ctx(db_session), current_user=_user()))
    assert [member["agent_id"] for member in detail["members"]] == [visible.id]
