from __future__ import annotations

import os
import sys
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.api_auth import ApiCaller  # noqa: E402
from auth_dependencies import TenantContext  # noqa: E402
from api.routes_agent_communication import (  # noqa: E402
    PermissionCreateRequest,
    PermissionUpdateRequest,
    create_permission,
    delete_permission,
    update_permission,
)
from api.routes_agents_protected import (  # noqa: E402
    SkillIntegrationRequest,
    get_agent_expand_data,
    get_agent_protected,
    get_agent_skill_integrations,
    get_agents_graph_preview,
    get_comm_enabled_agents,
    list_agents_protected,
    set_agent_skill_integration,
)
from api.routes_playground import get_available_agents  # noqa: E402
from api.v1.routes_studio import (  # noqa: E402
    StudioAgentSaveData,
    StudioSaveRequest,
    clone_agent,
    get_builder_data,
    save_builder_data,
)
from api.v1.routes_agents import AgentUpdateRequest, get_agent, list_agents, update_agent  # noqa: E402
from api.v1.routes_chat import ChatRequest, send_chat_message  # noqa: E402
from models import (  # noqa: E402
    Agent,
    AgentCommunicationPermission,
    AgentKnowledge,
    AgentSandboxedTool,
    AgentSkill,
    AgentSkillIntegration,
    Base,
    Contact,
    Persona,
    SandboxedTool,
    SentinelAgentConfig,
    TonePreset,
    TelegramBotInstance,
    WebhookIntegration,
    WhatsAppMCPInstance,
)
from models_rbac import Tenant, User  # noqa: E402


@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            Contact.__table__,
            Agent.__table__,
            AgentSkill.__table__,
            AgentSkillIntegration.__table__,
            AgentKnowledge.__table__,
            SentinelAgentConfig.__table__,
            AgentCommunicationPermission.__table__,
            WhatsAppMCPInstance.__table__,
            TelegramBotInstance.__table__,
            WebhookIntegration.__table__,
            AgentSandboxedTool.__table__,
            SandboxedTool.__table__,
            Persona.__table__,
            TonePreset.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _caller(tenant_id: str = "tenant-a") -> ApiCaller:
    return ApiCaller(
        tenant_id=tenant_id,
        user_id=1,
        permissions={"agents.read", "agents.write", "agents.execute"},
    )


def _user(tenant_id: str = "tenant-a") -> SimpleNamespace:
    return SimpleNamespace(id=1, tenant_id=tenant_id, is_global_admin=False)


def _ctx(db, tenant_id: str = "tenant-a") -> TenantContext:
    return TenantContext(user=_user(tenant_id), db=db)


def _seed_agent(db, *, agent_id: int, name: str, tenant_id: str = "tenant-a", is_internal: bool = False) -> Agent:
    contact = Contact(id=agent_id + 1000, tenant_id=tenant_id, friendly_name=name, role="agent")
    agent = Agent(
        id=agent_id,
        tenant_id=tenant_id,
        contact_id=contact.id,
        system_prompt=f"You are {name}.",
        model_provider="gemini",
        model_name="gemini-2.5-pro",
        response_template="{response}",
        enabled_channels=["playground"],
        is_active=True,
        is_internal=is_internal,
    )
    db.add(contact)
    db.add(agent)
    db.commit()
    return agent


def _seed_permission(
    db,
    *,
    permission_id: int,
    source_agent_id: int,
    target_agent_id: int,
    tenant_id: str = "tenant-a",
    is_enabled: bool = True,
) -> AgentCommunicationPermission:
    permission = AgentCommunicationPermission(
        id=permission_id,
        tenant_id=tenant_id,
        source_agent_id=source_agent_id,
        target_agent_id=target_agent_id,
        is_enabled=is_enabled,
        max_depth=3,
        rate_limit_rpm=30,
        allow_target_skills=False,
    )
    db.add(permission)
    db.commit()
    return permission


@pytest.mark.asyncio
async def test_public_v1_agent_list_hides_internal_agents(db_session):
    _seed_agent(db_session, agent_id=1, name="Visible Agent")
    _seed_agent(db_session, agent_id=2, name="Hidden Coordinator", is_internal=True)

    response = await list_agents(
        page=1,
        per_page=20,
        is_active=None,
        search=None,
        channel=None,
        db=db_session,
        caller=_caller(),
    )

    assert [row["id"] for row in response["data"]] == [1]
    assert response["meta"]["total"] == 1


@pytest.mark.asyncio
async def test_public_v1_agent_read_and_write_reject_internal_agents(db_session):
    _seed_agent(db_session, agent_id=2, name="Hidden Coordinator", is_internal=True)

    with pytest.raises(HTTPException) as read_exc:
        await get_agent(agent_id=2, db=db_session, caller=_caller())
    assert read_exc.value.status_code == 404

    with pytest.raises(HTTPException) as write_exc:
        await update_agent(
            agent_id=2,
            request=AgentUpdateRequest(description="should not update"),
            db=db_session,
            caller=_caller(),
        )
    assert write_exc.value.status_code == 403


@pytest.mark.asyncio
async def test_public_v1_chat_rejects_internal_agents_before_execution(db_session):
    _seed_agent(db_session, agent_id=2, name="Hidden Coordinator", is_internal=True)

    with pytest.raises(HTTPException) as exc:
        await send_chat_message(
            agent_id=2,
            request=ChatRequest(message="hello"),
            db=db_session,
            caller=_caller(),
        )

    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_playground_agent_list_hides_internal_agents(db_session):
    _seed_agent(db_session, agent_id=1, name="Visible Agent")
    _seed_agent(db_session, agent_id=2, name="Hidden Coordinator", is_internal=True)

    response = await get_available_agents(db=db_session, current_user=_user())

    assert [row["id"] for row in response] == [1]


@pytest.mark.asyncio
async def test_studio_v1_get_save_clone_reject_internal_agents(db_session):
    _seed_agent(db_session, agent_id=2, name="Hidden Coordinator", is_internal=True)

    with pytest.raises(HTTPException) as get_exc:
        await get_builder_data(agent_id=2, db=db_session, caller=_caller())
    assert get_exc.value.status_code == 404

    with pytest.raises(HTTPException) as save_exc:
        await save_builder_data(
            agent_id=2,
            data=StudioSaveRequest(agent=StudioAgentSaveData(avatar="robot")),
            db=db_session,
            caller=_caller(),
        )
    assert save_exc.value.status_code == 404
    assert db_session.get(Agent, 2).avatar is None

    with pytest.raises(HTTPException) as clone_exc:
        await clone_agent(agent_id=2, db=db_session, caller=_caller())
    assert clone_exc.value.status_code == 404
    assert db_session.query(Agent).count() == 1


@pytest.mark.asyncio
async def test_protected_v2_agent_lists_and_reads_hide_internal_agents(db_session):
    _seed_agent(db_session, agent_id=1, name="Visible Agent")
    _seed_agent(db_session, agent_id=2, name="Hidden Coordinator", is_internal=True)
    ctx = _ctx(db_session)

    list_response = await list_agents_protected(ctx=ctx)
    assert [row["id"] for row in list_response["agents"]] == [1]

    graph_response = await get_agents_graph_preview(ctx=ctx)
    assert [agent.id for agent in graph_response.agents] == [1]

    with pytest.raises(HTTPException) as detail_exc:
        await get_agent_protected(agent_id=2, ctx=ctx)
    assert detail_exc.value.status_code == 404

    with pytest.raises(HTTPException) as integrations_exc:
        await get_agent_skill_integrations(agent_id=2, ctx=ctx)
    assert integrations_exc.value.status_code == 404

    with pytest.raises(HTTPException) as expand_exc:
        await get_agent_expand_data(agent_id=2, ctx=ctx)
    assert expand_exc.value.status_code == 404


@pytest.mark.asyncio
async def test_protected_v2_skill_integration_mutation_rejects_internal_agent_before_write(db_session):
    _seed_agent(db_session, agent_id=2, name="Hidden Coordinator", is_internal=True)
    ctx = _ctx(db_session)

    with pytest.raises(HTTPException) as exc:
        await set_agent_skill_integration(
            agent_id=2,
            skill_type="gmail",
            data=SkillIntegrationRequest(config={"provider": "x"}),
            ctx=ctx,
        )

    assert exc.value.status_code == 404
    assert db_session.query(AgentSkillIntegration).count() == 0


@pytest.mark.asyncio
async def test_comm_enabled_filters_internal_agents_and_permissions(db_session):
    _seed_agent(db_session, agent_id=1, name="Visible Source")
    _seed_agent(db_session, agent_id=2, name="Hidden Coordinator", is_internal=True)
    _seed_agent(db_session, agent_id=3, name="Visible Target")
    db_session.add(AgentSkill(agent_id=1, skill_type="agent_communication", is_enabled=True))
    _seed_permission(db_session, permission_id=10, source_agent_id=1, target_agent_id=2)
    _seed_permission(db_session, permission_id=11, source_agent_id=1, target_agent_id=3)

    response = await get_comm_enabled_agents(ctx=_ctx(db_session))

    assert [agent.id for agent in response.agents] == [1]
    assert [permission.id for permission in response.permissions] == [11]


@pytest.mark.asyncio
async def test_a2a_permission_mutations_reject_internal_agents_before_write(db_session):
    _seed_agent(db_session, agent_id=1, name="Visible Source")
    _seed_agent(db_session, agent_id=2, name="Hidden Coordinator", is_internal=True)
    _seed_agent(db_session, agent_id=3, name="Visible Target")
    permission = _seed_permission(db_session, permission_id=10, source_agent_id=1, target_agent_id=2)
    ctx = _ctx(db_session)

    with pytest.raises(HTTPException) as create_exc:
        await create_permission(
            body=PermissionCreateRequest(source_agent_id=2, target_agent_id=3),
            current_user=_user(),
            ctx=ctx,
            db=db_session,
        )
    assert create_exc.value.status_code == 404
    assert db_session.query(AgentCommunicationPermission).count() == 1

    with pytest.raises(HTTPException) as update_exc:
        await update_permission(
            permission_id=10,
            body=PermissionUpdateRequest(is_enabled=False),
            current_user=_user(),
            ctx=ctx,
            db=db_session,
        )
    assert update_exc.value.status_code == 404
    db_session.refresh(permission)
    assert permission.is_enabled is True

    with pytest.raises(HTTPException) as delete_exc:
        await delete_permission(
            permission_id=10,
            current_user=_user(),
            ctx=ctx,
            db=db_session,
        )
    assert delete_exc.value.status_code == 404
    assert db_session.get(AgentCommunicationPermission, 10) is not None
