"""
Targeted regressions for Playground thread-aware memory resolution.
"""

import asyncio
import os
import sys
import types
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

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

json_repair_stub = types.ModuleType("json_repair")
json_repair_stub.repair_json = lambda value: value
sys.modules.setdefault("json_repair", json_repair_stub)

sentence_transformers_stub = types.ModuleType("sentence_transformers")


class _SentenceTransformer:
    def __init__(self, *_args, **_kwargs):
        pass


sentence_transformers_stub.SentenceTransformer = _SentenceTransformer
sys.modules.setdefault("sentence_transformers", sentence_transformers_stub)

chromadb_stub = types.ModuleType("chromadb")


class _DummyCollection:
    def count(self):
        return 0

    def query(self, *args, **kwargs):
        return {"ids": [[]], "distances": [[]], "documents": [[]], "metadatas": [[]]}

    def upsert(self, *args, **kwargs):
        return None


class _PersistentClient:
    def __init__(self, *args, **kwargs):
        pass

    def get_or_create_collection(self, *args, **kwargs):
        return _DummyCollection()


chromadb_stub.PersistentClient = _PersistentClient
chromadb_config_stub = types.ModuleType("chromadb.config")


class _Settings:
    def __init__(self, *args, **kwargs):
        pass


chromadb_config_stub.Settings = _Settings
sys.modules.setdefault("chromadb", chromadb_stub)
sys.modules.setdefault("chromadb.config", chromadb_config_stub)


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


from api.routes_playground import get_memory_layers
from models import Base, Agent, Contact, ConversationThread, Memory
from services.playground_service import PlaygroundService
from services.playground_thread_service import (
    PlaygroundThreadService,
    build_playground_channel_id,
    build_playground_thread_recipient,
    resolve_playground_identity,
)


def _make_session():
    engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session()


def _seed_agent(session, isolation_mode: str) -> Agent:
    contact = Contact(
        id=101,
        friendly_name="Playground Agent",
        role="agent",
        tenant_id="tenant-playground",
    )
    agent = Agent(
        id=201,
        contact_id=contact.id,
        system_prompt="You are helpful.",
        tenant_id="tenant-playground",
        model_provider="openai",
        model_name="gpt-4o-mini",
        enabled_channels=["playground"],
        memory_isolation_mode=isolation_mode,
        enable_semantic_search=False,
        is_active=True,
    )
    session.add_all([contact, agent])
    session.commit()
    return agent


def _seed_threads(session, agent_id: int):
    thread_one = ConversationThread(
        id=301,
        tenant_id="tenant-playground",
        user_id=7,
        agent_id=agent_id,
        thread_type="playground",
        title="Thread One",
        recipient=build_playground_thread_recipient(7, agent_id, 301),
        status="active",
        is_archived=False,
    )
    thread_two = ConversationThread(
        id=302,
        tenant_id="tenant-playground",
        user_id=7,
        agent_id=agent_id,
        thread_type="playground",
        title="Thread Two",
        recipient=build_playground_thread_recipient(7, agent_id, 302),
        status="active",
        is_archived=False,
    )
    session.add_all([thread_one, thread_two])
    session.commit()
    return thread_one, thread_two


def _seed_channel_memory(session, agent_id: int, thread_one: ConversationThread, thread_two: ConversationThread):
    memory = Memory(
        tenant_id="tenant-playground",
        agent_id=agent_id,
        sender_key=f"channel_{build_playground_channel_id(thread_one.user_id)}",
        messages_json=[
            {
                "role": "user",
                "content": "thread one user",
                "timestamp": "2026-04-10T12:00:00Z",
                "metadata": {"thread_id": thread_one.id},
            },
            {
                "role": "assistant",
                "content": "thread one assistant",
                "timestamp": "2026-04-10T12:00:01Z",
                "metadata": {"thread_id": thread_one.id},
            },
            {
                "role": "user",
                "content": "thread two user",
                "timestamp": "2026-04-10T12:01:00Z",
                "metadata": {"thread_id": thread_two.id},
            },
        ],
    )
    session.add(memory)
    session.commit()
    return memory


def test_resolve_playground_identity_matches_memory_modes():
    isolated = resolve_playground_identity(
        user_id=7,
        agent_id=11,
        isolation_mode="isolated",
        thread_id=22,
    )
    assert isolated["sender_key"] == "playground_u7_a11_t22"
    assert isolated["chat_id"] == "playground_7"

    channel_scoped = resolve_playground_identity(
        user_id=7,
        agent_id=11,
        isolation_mode="channel_isolated",
        thread_id=22,
    )
    assert channel_scoped["sender_key"] == "playground_7"
    assert channel_scoped["thread_recipient"] == "playground_u7_a11_t22"

    shared = resolve_playground_identity(
        user_id=7,
        agent_id=11,
        isolation_mode="shared",
        thread_id=22,
        sender_key_override="playground_7",
    )
    assert shared["sender_key"] == "shared"


def test_thread_service_counts_messages_per_thread_for_channel_memory():
    session = _make_session()
    try:
        agent = _seed_agent(session, "channel_isolated")
        thread_one, thread_two = _seed_threads(session, agent.id)
        _seed_channel_memory(session, agent.id, thread_one, thread_two)

        service = PlaygroundThreadService(session)

        assert service.count_thread_messages(thread_one) == 2
        assert service.count_thread_messages(thread_two) == 1
    finally:
        session.close()


def test_playground_service_history_reads_only_requested_thread_slice():
    session = _make_session()
    try:
        agent = _seed_agent(session, "channel_isolated")
        thread_one, thread_two = _seed_threads(session, agent.id)
        _seed_channel_memory(session, agent.id, thread_one, thread_two)

        service = PlaygroundService(session)
        history = asyncio.run(
            service.get_conversation_history(
                user_id=7,
                agent_id=agent.id,
                thread_id=thread_one.id,
                tenant_id="tenant-playground",
            )
        )

        assert [message["content"] for message in history] == [
            "thread one user",
            "thread one assistant",
        ]
    finally:
        session.close()


def test_playground_service_clear_history_preserves_other_threads_in_channel_memory():
    session = _make_session()
    try:
        agent = _seed_agent(session, "channel_isolated")
        thread_one, thread_two = _seed_threads(session, agent.id)
        memory = _seed_channel_memory(session, agent.id, thread_one, thread_two)

        service = PlaygroundService(session)
        result = asyncio.run(
            service.clear_conversation_history(
                user_id=7,
                agent_id=agent.id,
                thread_id=thread_one.id,
                tenant_id="tenant-playground",
            )
        )

        session.refresh(memory)
        assert result["success"] is True
        assert [message["content"] for message in memory.messages_json] == ["thread two user"]
    finally:
        session.close()


def test_memory_layers_thread_id_filters_channel_memory():
    session = _make_session()
    try:
        agent = _seed_agent(session, "channel_isolated")
        thread_one, thread_two = _seed_threads(session, agent.id)
        _seed_channel_memory(session, agent.id, thread_one, thread_two)

        current_user = SimpleNamespace(id=7, tenant_id="tenant-playground")
        response = asyncio.run(
            get_memory_layers(
                agent_id=agent.id,
                thread_id=thread_one.id,
                db=session,
                current_user=current_user,
            )
        )

        assert [message["content"] for message in response.working_memory] == [
            "thread one user",
            "thread one assistant",
        ]
        assert response.stats["sender_key"] == "playground_7"
        assert response.stats["memory_mode"] == "channel_isolated"
    finally:
        session.close()


def test_playground_detect_only_keeps_thread_transcript_but_not_context_reuse(monkeypatch):
    session = _make_session()
    try:
        agent = _seed_agent(session, "isolated")
        thread_one, _ = _seed_threads(session, agent.id)

        sentinel_module = types.ModuleType("services.sentinel_service")

        class FakeSentinelService:
            def __init__(self, db, tenant_id):
                self.db = db
                self.tenant_id = tenant_id

            async def analyze_prompt(self, prompt, agent_id, sender_key, source=None, skill_context=None):
                if "alpha-123" in prompt:
                    return SimpleNamespace(
                        is_threat_detected=True,
                        action="allowed",
                        detection_type="prompt_injection",
                        threat_reason="Keep transcript, skip reuse",
                    )
                return SimpleNamespace(
                    is_threat_detected=False,
                    action="allowed",
                    detection_type="none",
                    threat_reason=None,
                )

        sentinel_module.SentinelService = FakeSentinelService
        monkeypatch.setitem(sys.modules, "services.sentinel_service", sentinel_module)

        token_tracker_module = types.ModuleType("analytics.token_tracker")

        class FakeTokenTracker:
            def __init__(self, db):
                self.db = db

        token_tracker_module.TokenTracker = FakeTokenTracker
        monkeypatch.setitem(sys.modules, "analytics.token_tracker", token_tracker_module)

        agent_service_module = types.ModuleType("agent.agent_service")
        captured_messages = []

        class FakeAgentService:
            def __init__(self, *args, **kwargs):
                self.ai_client = None

            async def process_message(self, *, sender_key, message_text, original_query):
                captured_messages.append(message_text)
                return {"answer": f"response for {original_query}"}

        agent_service_module.AgentService = FakeAgentService
        monkeypatch.setitem(sys.modules, "agent.agent_service", agent_service_module)

        skill_manager_module = types.ModuleType("agent.skills.skill_manager")

        class FakeSkillManager:
            def __init__(self, *args, **kwargs):
                self.registry = {}

            async def get_agent_skills(self, db, agent_id):
                return []

            async def process_message_with_skills(self, *args, **kwargs):
                return None

        skill_manager_module.SkillManager = FakeSkillManager
        skill_manager_module.get_skill_manager = lambda: FakeSkillManager()
        monkeypatch.setitem(sys.modules, "agent.skills.skill_manager", skill_manager_module)

        playground_module = sys.modules["services.playground_service"]
        monkeypatch.setattr(playground_module, "emit_agent_processing_async", lambda *args, **kwargs: None)

        service = PlaygroundService(session)
        first_result = asyncio.run(
            service.send_message(
                user_id=7,
                agent_id=agent.id,
                message_text="remember this exact token: alpha-123",
                thread_id=thread_one.id,
                tenant_id="tenant-playground",
            )
        )
        second_result = asyncio.run(
            service.send_message(
                user_id=7,
                agent_id=agent.id,
                message_text="what was the token?",
                thread_id=thread_one.id,
                tenant_id="tenant-playground",
            )
        )

        history = asyncio.run(
            service.get_conversation_history(
                user_id=7,
                agent_id=agent.id,
                thread_id=thread_one.id,
                tenant_id="tenant-playground",
            )
        )

        assert first_result["status"] == "success"
        assert second_result["status"] == "success"
        assert any(msg["content"] == "remember this exact token: alpha-123" for msg in history)
        assert any(msg["content"] == "response for remember this exact token: alpha-123" for msg in history)
        assert "alpha-123" in captured_messages[0]
        assert "alpha-123" not in captured_messages[1]
    finally:
        session.close()
