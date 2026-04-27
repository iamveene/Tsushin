import asyncio
import importlib.util
import json
import re
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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

playground_service_stub = types.ModuleType("services.playground_service")
playground_service_stub.PlaygroundService = object
sys.modules.setdefault("services.playground_service", playground_service_stub)

playground_message_service_stub = types.ModuleType("services.playground_message_service")
playground_message_service_stub.PlaygroundMessageService = object
sys.modules.setdefault("services.playground_message_service", playground_message_service_stub)

playground_thread_service_stub = types.ModuleType("services.playground_thread_service")
playground_thread_service_stub.PlaygroundThreadService = object
playground_thread_service_stub.build_api_channel_id = lambda api_client_id=None, user_id=None: (
    f"api_client_{api_client_id}" if api_client_id else f"api_user_{user_id}"
)
playground_thread_service_stub.build_api_thread_recipient = lambda thread_id, api_client_id=None, user_id=None: (
    f"api_client_{api_client_id}_thread_{thread_id}" if api_client_id else f"api_user_{user_id}_thread_{thread_id}"
)
sys.modules.setdefault("services.playground_thread_service", playground_thread_service_stub)

knowledge_service_stub = types.ModuleType("agent.knowledge.knowledge_service")
knowledge_service_stub.KnowledgeService = object
# `api/routes_knowledge_base.py` imports `KnowledgeMetadataError` from this
# module; downstream tests in the same pytest session that import
# `from app import app` will fail with ImportError if the stub doesn't expose
# this attribute when it lands in sys.modules ahead of the real module.
knowledge_service_stub.KnowledgeMetadataError = type(
    "KnowledgeMetadataError", (RuntimeError,), {}
)
sys.modules.setdefault("agent.knowledge.knowledge_service", knowledge_service_stub)

from agent.followup_detector import build_data_block, is_followup_to_prior_skill
from models import Agent, AgentSkill, Config, ConversationThread


def test_track_f_migration_chain_and_columns_are_scoped():
    versions = Path(__file__).resolve().parents[1] / "alembic" / "versions"

    def load_revision(filename: str):
        text = (versions / filename).read_text()
        revision = re.search(r'revision:\s*str\s*=\s*"([^"]+)"', text)
        down_revision = re.search(r'down_revision:\s*Union\[str,\s*None\]\s*=\s*"([^"]+)"', text)
        assert revision is not None
        assert down_revision is not None
        return revision.group(1), down_revision.group(1), text

    rev_0049, down_0049, text_0049 = load_revision("0049_add_agent_skill_tool_result_columns.py")
    rev_0057, down_0057, _ = load_revision("0057_add_platform_agentic_bounds.py")
    rev_0058, down_0058, text_0058 = load_revision("0058_add_agent_max_agentic_rounds.py")

    assert (rev_0049, down_0049) == ("0049", "0050")
    assert (rev_0057, down_0057) == ("0057", "0049")
    assert (rev_0058, down_0058) == ("0058", "0057")
    assert "conversation_thread" in text_0049
    assert "continuous_run" not in text_0049
    assert "bool_columns" in text_0049
    assert "int_columns" in text_0049
    assert "(config::jsonb - :key)::json" in text_0049
    assert 'server_default="1"' in text_0058


def test_track_f_model_columns_exist():
    assert hasattr(ConversationThread, "agentic_scratchpad")
    assert hasattr(AgentSkill, "auto_inject_results")
    assert hasattr(AgentSkill, "skip_ai_on_data_fetch")
    assert hasattr(AgentSkill, "max_result_bytes")
    assert hasattr(AgentSkill, "max_results_retained")
    assert hasattr(AgentSkill, "max_turns_lookback")
    assert hasattr(Config, "platform_min_agentic_rounds")
    assert hasattr(Config, "platform_max_agentic_rounds")
    assert hasattr(Agent, "max_agentic_rounds")
    assert hasattr(Agent, "max_agentic_loop_bytes")


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("Which of these is most important?", "gmail"),
        ("qual desses é mais importante?", "gmail"),
        ("Compare those for me", "gmail"),
        ("resume isso", "gmail"),
        ("what about the second one?", "gmail"),
        ("entre eles, qual parece urgente?", "gmail"),
        ("show me the latest emails", None),
        ("emails novos por favor", None),
        ("buscar emails recentes", None),
        ("hello there", None),
    ],
)
def test_followup_detector_pronouns_and_fresh_fetch_override(message, expected):
    history = [
        {"role": "user", "content": "list my emails"},
        {
            "role": "assistant",
            "content": "Here are your emails",
            "tool_result": {
                "skill_type": "gmail",
                "operation": "list_emails",
                "data": {"emails": [{"subject": "Budget"}, {"subject": "Launch"}]},
            },
        },
    ]

    assert is_followup_to_prior_skill(message, history) == expected


def test_sender_memory_promotes_structured_tool_result_to_message_top_level():
    memory_path = Path(__file__).resolve().parents[1] / "agent" / "memory.py"
    spec = importlib.util.spec_from_file_location("track_f_sender_memory", memory_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)

    memory = module.SenderMemory(max_size=5)
    structured = {
        "skill_type": "gmail",
        "operation": "list_emails",
        "summary": "2 emails",
        "data": {"emails": [{"subject": "Budget"}]},
        "ts": "2026-04-23T00:00:00Z",
    }

    memory.add_message(
        "sender-a",
        "assistant",
        "Here are your emails",
        metadata={"tool_result": structured, "tool_used": "skill:gmail"},
        message_id="msg-1",
    )

    [message] = memory.get_messages("sender-a")
    assert message["tool_result"] == structured
    assert message["metadata"]["tool_result"] == structured


def test_data_block_bounds_structured_tool_results():
    block = build_data_block(
        [
            {
                "skill_type": "gmail",
                "operation": "list_emails",
                "data": {"emails": [{"subject": "Budget"}, {"subject": "Launch"}]},
            }
        ],
        max_bytes=220,
    )

    assert block.startswith("DATA:\n")
    assert "gmail" in block
    assert len(block.encode("utf-8")) < 400


def test_followup_data_reuse_suppresses_matching_tool_call():
    service_text = (Path(__file__).resolve().parents[1] / "services" / "playground_service.py").read_text()
    agent_service_text = (Path(__file__).resolve().parents[1] / "agent" / "agent_service.py").read_text()

    assert '"skill_type": skill_type' in service_text
    assert 'config_dict["suppress_followup_tool_skill_type"]' in service_text
    assert 'getattr(thread, "agentic_scratchpad", None)' in service_text
    assert "suppress_direct_skill_processing = True" in service_text
    assert "Skipping direct skill processing for follow-up DATA reuse" in service_text
    assert "Preserving structured tool DATA scratchpad after follow-up reuse" in service_text
    assert "suppress_followup_tool_skill_type" in agent_service_text
    assert "Suppressing redundant follow-up tool call" in agent_service_text
    assert "operation_type=\"tool_followup_reuse\"" in agent_service_text


def test_agent_service_agentic_caps_preserve_single_round_and_bound_payload(monkeypatch):
    skills_stub = types.ModuleType("agent.skills")
    skills_stub.get_skill_manager = lambda: None
    monkeypatch.setitem(sys.modules, "agent.skills", skills_stub)

    from agent.agent_service import AgentService

    service = object.__new__(AgentService)
    service.config = {
        "max_agentic_rounds": 1,
        "platform_min_agentic_rounds": 1,
        "platform_max_agentic_rounds": 8,
    }
    assert service._get_max_agentic_rounds() == 1

    service.config = {
        "max_agentic_rounds": 12,
        "platform_min_agentic_rounds": 2,
        "platform_max_agentic_rounds": 4,
    }
    assert service._get_max_agentic_rounds() == 4

    scratchpad = [
        {"round": idx, "tool_result": {"data": "x" * 200}}
        for idx in range(5)
    ]
    bounded = service._bound_scratchpad(scratchpad, 500)

    assert bounded[-1]["round"] == 4
    assert len(json.dumps(bounded, ensure_ascii=False).encode("utf-8")) <= 500


class _FakeQuery:
    def __init__(self, item):
        self.item = item

    def filter(self, *_args):
        return self

    def first(self):
        return self.item

    def count(self):
        return 0


class _FakeDB:
    def __init__(self, item):
        self.item = item

    def query(self, _model):
        return _FakeQuery(self.item)


def test_api_v1_queue_status_includes_scratchpad_only_when_requested():
    from api.v1.routes_chat import poll_queue_status

    item = SimpleNamespace(
        id=42,
        tenant_id="tenant-a",
        status="completed",
        payload={
            "api_client_id": "client-a",
            "result": {
                "status": "success",
                "thread_id": 7,
                "agentic_scratchpad": [{"round": 1, "tool_name": "gmail"}],
            },
        },
    )
    caller = SimpleNamespace(tenant_id="tenant-a", is_api_client=True, client_id="client-a")

    without = asyncio.run(poll_queue_status(42, include_scratchpad=False, db=_FakeDB(item), caller=caller))
    with_trace = asyncio.run(poll_queue_status(42, include_scratchpad=True, db=_FakeDB(item), caller=caller))

    assert without.agentic_scratchpad is None
    assert "agentic_scratchpad" not in without.result
    assert with_trace.agentic_scratchpad == [{"round": 1, "tool_name": "gmail"}]
    assert "agentic_scratchpad" not in with_trace.result


def test_api_v1_queue_status_rejects_other_api_client_queue_item():
    from api.v1.routes_chat import poll_queue_status

    item = SimpleNamespace(
        id=42,
        tenant_id="tenant-a",
        status="completed",
        payload={"api_client_id": "client-a", "result": {"status": "success"}},
    )
    caller = SimpleNamespace(tenant_id="tenant-a", is_api_client=True, client_id="client-b")

    with pytest.raises(HTTPException) as exc_info:
        asyncio.run(poll_queue_status(42, include_scratchpad=True, db=_FakeDB(item), caller=caller))

    assert exc_info.value.status_code == 404
