"""Focused regressions for per-agent timezone propagation and scheduling."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest
from pydantic import ValidationError


BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


from agent.skills.base import InboundMessage, SkillResult  # noqa: E402
from agent.skills.flows_skill import FlowsSkill  # noqa: E402
from agent.skills.scheduler.base import SchedulerEvent  # noqa: E402
from agent.skills.scheduler.calendar_provider import GoogleCalendarProvider  # noqa: E402
from agent.skills.scheduler_skill import SchedulerSkill  # noqa: E402
from agent.skills.skill_manager import SkillManager  # noqa: E402
from api.routes_agents import AgentCreate, AgentUpdate  # noqa: E402
from api.v1.routes_agents import AgentCreateRequest, AgentUpdateRequest  # noqa: E402
from constants.agent_config import DEFAULT_AGENT_TIMEZONE  # noqa: E402
from services.queue_router import _invoke_agent_for_continuous_run  # noqa: E402
from utils.agent_timezone import (  # noqa: E402
    localize_wall_time,
    to_utc_naive,
    utc_to_local,
)


@pytest.mark.parametrize(
    "schema,payload",
    [
        (AgentUpdate, {"timezone": "America/New_York"}),
        (AgentCreate, {"contact_id": 1, "system_prompt": "hello", "timezone": "Europe/Lisbon"}),
        (AgentUpdateRequest, {"timezone": "America/Los_Angeles"}),
        (
            AgentCreateRequest,
            {"name": "Agent", "system_prompt": "hello", "timezone": "Asia/Tokyo"},
        ),
    ],
)
def test_agent_api_schemas_round_trip_valid_timezone(schema, payload):
    parsed = schema(**payload)
    assert parsed.model_dump(exclude_unset=True)["timezone"] == payload["timezone"]


@pytest.mark.parametrize("schema", [AgentUpdate, AgentUpdateRequest])
def test_agent_api_schemas_reject_invalid_timezone(schema):
    with pytest.raises(ValidationError):
        schema(timezone="Mars/Olympus_Mons")


def test_default_and_dst_aware_wall_time_conversion():
    # The default remains São Paulo when no agent override exists.
    assert to_utc_naive(datetime(2026, 1, 15, 9, 0), None) == datetime(2026, 1, 15, 12, 0)
    assert DEFAULT_AGENT_TIMEZONE == "America/Sao_Paulo"

    # New York changes from UTC-5 in winter to UTC-4 in summer.
    assert to_utc_naive(datetime(2026, 1, 15, 9, 0), "America/New_York") == datetime(2026, 1, 15, 14, 0)
    assert to_utc_naive(datetime(2026, 7, 15, 9, 0), "America/New_York") == datetime(2026, 7, 15, 13, 0)

    # Aware inputs represent an instant and must not be reinterpreted as wall time.
    aware_utc = datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
    assert to_utc_naive(aware_utc, "America/New_York") == datetime(2026, 7, 15, 13, 0)
    assert utc_to_local(aware_utc, "America/New_York").hour == 9


def test_nonexistent_dst_wall_time_is_rejected():
    with pytest.raises(ValueError, match="does not exist"):
        localize_wall_time(datetime(2026, 3, 8, 2, 30), "America/New_York")


def test_flow_event_display_converts_stored_utc_to_agent_timezone():
    skill = FlowsSkill()
    event = SchedulerEvent(
        id="flows_1",
        provider="flows",
        title="Reminder",
        start=datetime(2026, 1, 15, 14, 0),
    )
    displayed = skill._event_datetime_for_display(
        event,
        {"timezone": "America/New_York"},
    )
    assert displayed.strftime("%Y-%m-%d %H:%M %Z") == "2026-01-15 09:00 EST"


def test_google_calendar_conversion_preserves_timed_event_instant():
    provider = GoogleCalendarProvider.__new__(GoogleCalendarProvider)
    event = provider._google_event_to_scheduler_event({
        "id": "evt-1",
        "summary": "Meeting",
        "status": "confirmed",
        "start": {"dateTime": "2026-07-15T13:00:00Z"},
        "end": {"dateTime": "2026-07-15T14:00:00Z"},
    })
    assert event.start == datetime(2026, 7, 15, 13, 0, tzinfo=timezone.utc)
    displayed = FlowsSkill()._event_datetime_for_display(
        event,
        {"timezone": "America/New_York"},
    )
    assert displayed.strftime("%Y-%m-%d %H:%M %Z") == "2026-07-15 09:00 EDT"


def test_builtin_scheduler_uses_agent_timezone_for_absolute_time():
    skill = SchedulerSkill()
    parsed = skill._parse_natural_language_datetime(
        "dia 15/01/2027 às 09:00",
        {"timezone": "America/New_York"},
    )
    assert parsed == datetime(2027, 1, 15, 14, 0)


def test_skill_manager_agent_timezone_overrides_saved_skill_config():
    agent = SimpleNamespace(tenant_id="tenant-a", timezone="America/New_York")

    class FakeQuery:
        def filter(self, *_args, **_kwargs):
            return self

        def first(self):
            return agent

    class FakeDB:
        def query(self, *_args, **_kwargs):
            return FakeQuery()

    manager = SkillManager.__new__(SkillManager)
    db = FakeDB()
    saved_config = {"timezone": "America/Los_Angeles", "custom": True}
    runtime = manager.build_runtime_config(db, 42, saved_config)

    assert runtime["timezone"] == "America/New_York"
    assert runtime["tenant_id"] == "tenant-a"
    assert runtime["agent_id"] == 42
    assert runtime["custom"] is True
    assert saved_config == {"timezone": "America/Los_Angeles", "custom": True}


def test_flows_builtin_scheduler_receives_runtime_timezone():
    skill = FlowsSkill()
    captured = {}

    class FakeScheduler:
        async def process(self, _message, config):
            captured.update(config)
            return SkillResult(success=True, output="created", metadata={})

    async def detect_create(_text, _model=None):
        return "create"

    skill._scheduler = FakeScheduler()
    skill._get_provider = lambda _config: SimpleNamespace(
        provider_type=SimpleNamespace(value="flows"),
        provider_name="Built-in Flows",
    )
    skill._resolve_intent_detection_model = lambda _config: "gpt-4o-mini"
    skill._detect_flow_intent = detect_create

    message = InboundMessage(
        id="timezone-test",
        sender="user",
        sender_key="user",
        body="remind me tomorrow",
        chat_id="chat",
        chat_name=None,
        is_group=False,
        timestamp=datetime.utcnow(),
        channel="test",
    )
    result = asyncio.run(
        skill.process(
            message,
            {"agent_id": 7, "tenant_id": "tenant-a", "timezone": "Europe/London"},
        )
    )

    assert result.success is True
    assert captured["timezone"] == "Europe/London"
    assert captured["agent_id"] == 7


def test_continuous_agent_service_config_includes_timezone(monkeypatch):
    captured = {}

    class FakeAgentService:
        def __init__(self, config, **_kwargs):
            captured.update(config)

        async def process_message(self, **_kwargs):
            return {"answer": "ok"}

    import agent.agent_service as agent_service_module

    monkeypatch.setattr(agent_service_module, "AgentService", FakeAgentService)
    agent = SimpleNamespace(
        id=1,
        tenant_id="tenant-a",
        timezone="America/Los_Angeles",
        system_prompt="hello",
        model_provider="openai",
        model_name="gpt-4o-mini",
        memory_size=10,
        context_message_count=10,
        context_char_limit=1000,
        enable_semantic_search=False,
        semantic_search_results=5,
        semantic_similarity_threshold=0.3,
        persona_id=None,
    )
    continuous_agent = SimpleNamespace(id=2, execution_mode="hybrid")
    run = SimpleNamespace(id=3, tenant_id="tenant-a")

    asyncio.run(
        _invoke_agent_for_continuous_run(
            db=SimpleNamespace(),
            agent=agent,
            continuous_agent=continuous_agent,
            run=run,
            sender_key="continuous:3",
            message_text="wake up",
        )
    )

    assert captured["timezone"] == "America/Los_Angeles"
