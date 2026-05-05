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
from api.routes_playground import get_available_agents  # noqa: E402
from api.v1.routes_agents import AgentUpdateRequest, get_agent, list_agents, update_agent  # noqa: E402
from api.v1.routes_chat import ChatRequest, send_chat_message  # noqa: E402
from models import (  # noqa: E402
    Agent,
    AgentSandboxedTool,
    AgentSkill,
    Base,
    Contact,
    Persona,
    SandboxedTool,
    TonePreset,
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
    return SimpleNamespace(id=1, tenant_id=tenant_id)


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
