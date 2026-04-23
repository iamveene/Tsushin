import asyncio
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

from agent.followup_detector import is_followup_to_prior_skill
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
    rev_0058, down_0058, _ = load_revision("0058_add_agent_max_agentic_rounds.py")

    assert (rev_0049, down_0049) == ("0049", "0050")
    assert (rev_0057, down_0057) == ("0057", "0049")
    assert (rev_0058, down_0058) == ("0058", "0057")
    assert "conversation_thread" in text_0049
    assert "continuous_run" not in text_0049


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
    assert with_trace.agentic_scratchpad == [{"round": 1, "tool_name": "gmail"}]


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
