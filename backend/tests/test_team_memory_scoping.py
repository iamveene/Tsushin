import asyncio
import os
import sys
import types
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

services_stub = types.ModuleType("services")
services_stub.__path__ = [os.path.join(backend_dir, "services")]
sys.modules.setdefault("services", services_stub)

sentence_transformers_stub = types.ModuleType("sentence_transformers")


class _SentenceTransformerStub:
    def __init__(self, *args, **kwargs):
        pass

    def encode(self, texts, *args, **kwargs):
        if isinstance(texts, str):
            return [0.0]
        return [[0.0] for _ in texts]


sentence_transformers_stub.SentenceTransformer = _SentenceTransformerStub
sys.modules.setdefault("sentence_transformers", sentence_transformers_stub)

chromadb_stub = types.ModuleType("chromadb")
chromadb_config_stub = types.ModuleType("chromadb.config")
chromadb_config_stub.Settings = object
sys.modules.setdefault("chromadb", chromadb_stub)
sys.modules.setdefault("chromadb.config", chromadb_config_stub)

json_repair_stub = types.ModuleType("json_repair")
json_repair_stub.repair_json = lambda text: text
sys.modules.setdefault("json_repair", json_repair_stub)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


import models_rbac  # noqa: F401,E402
from agent.memory.multi_agent_memory import MultiAgentMemoryManager  # noqa: E402
from agent.skills.base import InboundMessage, SkillResult  # noqa: E402
from agent.skills.skill_manager import SkillManager  # noqa: E402
from models import (  # noqa: E402
    Agent,
    AgentTeam,
    AgentTeamMember,
    AgentTeamRun,
    Base,
    Contact,
    Memory,
    TeamMemberRole,
    TeamRunStatus,
    TeamStatus,
    TeamTopology,
)
from models_rbac import Tenant  # noqa: E402
from services.team_run_scratch_service import (  # noqa: E402
    TeamRunScratchService,
    TeamRunScratchValidationError,
)


class FakeVectorStore:
    def __init__(self):
        self.embedding_service = object()
        self.records = {}

    async def add_message(self, message_id, sender_key, text, metadata=None):
        self.records[message_id] = {
            "message_id": message_id,
            "sender_key": sender_key,
            "text": text,
            "metadata": metadata or {},
        }

    async def search_similar(self, query_text, limit=5, sender_key=None):
        matches = [
            {
                "message_id": record["message_id"],
                "sender_key": record["sender_key"],
                "text": record["text"],
                "distance": 0.0,
                **record["metadata"],
            }
            for record in self.records.values()
            if sender_key is None or record["sender_key"] == sender_key
        ]
        return matches[:limit]

    async def search_similar_with_embeddings(self, query_text, limit=5, sender_key=None):
        return await self.search_similar(query_text, limit, sender_key), [], []

    def update_access_time(self, message_ids):
        return None

    def delete_by_sender(self, sender_key):
        self.records = {
            message_id: record
            for message_id, record in self.records.items()
            if record["sender_key"] != sender_key
        }

    def get_stats(self):
        return {"total_messages": len(self.records), "collection_name": "fake"}


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


def _create_agent(db_session, *, tenant_id: str, name: str, is_internal: bool = False) -> Agent:
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
        memory_isolation_mode="isolated",
        enable_semantic_search=True,
        is_active=True,
        is_internal=is_internal,
    )
    db_session.add(agent)
    db_session.flush()
    return agent


def _create_team(db_session, *, tenant_id: str, name: str, agent: Agent) -> AgentTeam:
    team = AgentTeam(
        tenant_id=tenant_id,
        name=name,
        topology=TeamTopology.LINE.value,
        status=TeamStatus.ACTIVE.value,
    )
    db_session.add(team)
    db_session.flush()
    db_session.add(
        AgentTeamMember(
            tenant_id=tenant_id,
            team_id=team.id,
            agent_id=agent.id,
            role=TeamMemberRole.MEMBER.value,
            execution_order=1,
        )
    )
    db_session.flush()
    return team


def _create_run(
    db_session,
    *,
    tenant_id: str,
    team: AgentTeam,
    status: str = TeamRunStatus.RUNNING.value,
) -> AgentTeamRun:
    run = AgentTeamRun(
        tenant_id=tenant_id,
        team_id=team.id,
        status=status,
        goal_text_snapshot="Prove scoped memory.",
        topology_snapshot=TeamTopology.LINE.value,
    )
    db_session.add(run)
    db_session.flush()
    return run


def _new_memory_manager(db_session, monkeypatch) -> MultiAgentMemoryManager:
    fake_store = FakeVectorStore()
    monkeypatch.setattr(
        MultiAgentMemoryManager,
        "_resolve_vector_store",
        lambda self, agent_id, persist_dir: fake_store,
    )
    return MultiAgentMemoryManager(
        db_session,
        {
            "auto_extract_facts": False,
            "enable_semantic_search": True,
            "semantic_search_results": 5,
            "semantic_similarity_threshold": 0.0,
            "memory_size": 10,
        },
    )


def _contents(messages):
    return [message["content"] for message in messages]


def test_team_run_memory_is_run_scoped_and_hidden_from_direct_context(db_session, monkeypatch):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Scoped Agent")
    team = _create_team(db_session, tenant_id="tenant-a", name="Scoped Team", agent=agent)
    run = _create_run(db_session, tenant_id="tenant-a", team=team, status=TeamRunStatus.COMPLETED.value)
    db_session.commit()

    manager = _new_memory_manager(db_session, monkeypatch)

    asyncio.run(
        manager.add_message(
            agent_id=agent.id,
            sender_key="user-1",
            role="user",
            content="team run secret",
            message_id="run-message",
            use_contact_mapping=False,
            team_run_id=run.id,
        )
    )

    run_memory = db_session.query(Memory).filter(Memory.team_run_id == run.id).one()
    assert run_memory.sender_key == f"team_run:{run.id}:sender_user-1"
    assert run_memory.messages_json[0]["content"] == "team run secret"

    direct_context = asyncio.run(
        manager.get_context(
            agent_id=agent.id,
            sender_key="user-1",
            current_message="secret",
            include_knowledge=False,
            include_shared=False,
            use_contact_mapping=False,
        )
    )
    assert "team run secret" not in _contents(direct_context["working_memory"])
    assert "team run secret" not in _contents(direct_context["episodic_memories"])

    team_context = asyncio.run(
        manager.get_context(
            agent_id=agent.id,
            sender_key="user-1",
            current_message="secret",
            include_knowledge=False,
            include_shared=False,
            use_contact_mapping=False,
            team_run_id=run.id,
        )
    )
    assert "team run secret" in _contents(team_context["working_memory"])
    assert "team run secret" in _contents(team_context["episodic_memories"])

    asyncio.run(
        manager.add_message(
            agent_id=agent.id,
            sender_key="user-1",
            role="user",
            content="direct hello",
            message_id="direct-message",
            use_contact_mapping=False,
        )
    )
    direct_memory = db_session.query(Memory).filter(Memory.team_run_id.is_(None)).one()
    assert direct_memory.sender_key == "sender_user-1"
    assert direct_memory.messages_json[0]["content"] == "direct hello"

    direct_context_after_direct_write = asyncio.run(
        manager.get_context(
            agent_id=agent.id,
            sender_key="user-1",
            current_message="hello",
            include_knowledge=False,
            include_shared=False,
            use_contact_mapping=False,
        )
    )
    assert "direct hello" in _contents(direct_context_after_direct_write["working_memory"])
    assert "team run secret" not in _contents(direct_context_after_direct_write["working_memory"])
    assert "team run secret" not in _contents(direct_context_after_direct_write["episodic_memories"])


def test_team_run_scratch_is_isolated_by_tenant_team_and_run(db_session):
    _create_tenant(db_session, "tenant-a")
    _create_tenant(db_session, "tenant-b")
    agent_a = _create_agent(db_session, tenant_id="tenant-a", name="Tenant A Agent")
    agent_b = _create_agent(db_session, tenant_id="tenant-b", name="Tenant B Agent")
    team_a = _create_team(db_session, tenant_id="tenant-a", name="Tenant A Team", agent=agent_a)
    team_b = _create_team(db_session, tenant_id="tenant-b", name="Tenant B Team", agent=agent_b)
    run_a1 = _create_run(db_session, tenant_id="tenant-a", team=team_a)
    run_a2 = _create_run(db_session, tenant_id="tenant-a", team=team_a)
    run_b = _create_run(db_session, tenant_id="tenant-b", team=team_b)
    db_session.commit()

    service = TeamRunScratchService(db_session)
    service.set(
        tenant_id="tenant-a",
        team_id=team_a.id,
        team_run_id=run_a1.id,
        key="handoff",
        value={"summary": "tenant a run 1"},
    )
    service.set(
        tenant_id="tenant-a",
        team_id=team_a.id,
        team_run_id=run_a2.id,
        key="handoff",
        value={"summary": "tenant a run 2"},
    )
    service.set(
        tenant_id="tenant-b",
        team_id=team_b.id,
        team_run_id=run_b.id,
        key="handoff",
        value={"summary": "tenant b"},
    )

    assert service.get(
        tenant_id="tenant-a",
        team_id=team_a.id,
        team_run_id=run_a1.id,
        key="handoff",
    ) == {"summary": "tenant a run 1"}
    assert service.get(
        tenant_id="tenant-a",
        team_id=team_a.id,
        team_run_id=run_a2.id,
        key="handoff",
    ) == {"summary": "tenant a run 2"}
    assert service.get(
        tenant_id="tenant-b",
        team_id=team_b.id,
        team_run_id=run_b.id,
        key="handoff",
    ) == {"summary": "tenant b"}
    assert service.list_keys(tenant_id="tenant-a", team_id=team_a.id, team_run_id=run_a1.id) == ["handoff"]

    with pytest.raises(TeamRunScratchValidationError):
        service.get(
            tenant_id="tenant-a",
            team_id=team_a.id,
            team_run_id=run_b.id,
            key="handoff",
        )
    with pytest.raises(TeamRunScratchValidationError):
        service.get(
            tenant_id="tenant-a",
            team_id=team_b.id,
            team_run_id=run_a1.id,
            key="handoff",
        )
    with pytest.raises(TeamRunScratchValidationError):
        service.list_keys(tenant_id="tenant-b", team_id=team_a.id, team_run_id=run_a1.id)


def test_team_scratch_tool_requires_team_run_context(db_session):
    _create_tenant(db_session, "tenant-a")
    agent = _create_agent(db_session, tenant_id="tenant-a", name="Tool Agent")
    outsider = _create_agent(db_session, tenant_id="tenant-a", name="Outsider")
    internal_agent = _create_agent(db_session, tenant_id="tenant-a", name="Internal", is_internal=True)
    team = _create_team(db_session, tenant_id="tenant-a", name="Tool Team", agent=agent)
    db_session.add(
        AgentTeamMember(
            tenant_id="tenant-a",
            team_id=team.id,
            agent_id=internal_agent.id,
            role=TeamMemberRole.COORDINATOR.value,
            execution_order=2,
        )
    )
    run = _create_run(db_session, tenant_id="tenant-a", team=team)
    db_session.commit()

    manager = SkillManager()
    no_context = asyncio.run(
        manager.execute_tool_call(
            db=db_session,
            agent_id=agent.id,
            tool_name="team_scratch_set",
            arguments={"key": "handoff", "value": {"summary": "blocked"}},
            return_full_result=True,
        )
    )
    assert no_context == "Error: Tool 'team_scratch_set' is not enabled for this agent"

    message = InboundMessage(
        id="tool_call_team_scratch_set",
        sender="team",
        sender_key="team",
        body="",
        chat_id="tool_execution",
        chat_name=None,
        is_group=False,
        timestamp=datetime.utcnow(),
        channel="tool",
        metadata={"team_run_id": run.id},
    )
    stored = asyncio.run(
        manager.execute_tool_call(
            db=db_session,
            agent_id=agent.id,
            tool_name="team_scratch_set",
            arguments={"key": "handoff", "value": {"summary": "safe"}},
            message=message,
            return_full_result=True,
        )
    )
    assert isinstance(stored, SkillResult)
    assert stored.success is True

    outsider_result = asyncio.run(
        manager.execute_tool_call(
            db=db_session,
            agent_id=outsider.id,
            tool_name="team_scratch_set",
            arguments={"key": "handoff", "value": {"summary": "spoofed"}},
            message=message,
            return_full_result=True,
        )
    )
    assert isinstance(outsider_result, SkillResult)
    assert outsider_result.success is False
    assert outsider_result.metadata["error"] == "team_run_membership_required"

    internal_result = asyncio.run(
        manager.execute_tool_call(
            db=db_session,
            agent_id=internal_agent.id,
            tool_name="team_scratch_set",
            arguments={"key": "handoff", "value": {"summary": "internal"}},
            message=message,
            return_full_result=True,
        )
    )
    assert isinstance(internal_result, SkillResult)
    assert internal_result.success is False
    assert internal_result.metadata["error"] == "team_run_membership_required"

    read = asyncio.run(
        manager.execute_tool_call(
            db=db_session,
            agent_id=agent.id,
            tool_name="team_scratch_get",
            arguments={"key": "handoff"},
            message=message,
            return_full_result=True,
        )
    )
    assert isinstance(read, SkillResult)
    assert read.success is True
    assert '"summary": "safe"' in read.output
