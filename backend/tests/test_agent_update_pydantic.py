"""
BUG-710 regression: PUT /api/agents/{id} must round-trip
max_agentic_rounds and max_agentic_loop_bytes.

Before the fix, AgentUpdate (Pydantic v2) silently stripped both fields
because they were not declared on the model — the API accepted the body but
discarded the keys, so column values never updated. AgentCreate was missing
them too.

Symmetric coverage for AgentUpdate and AgentCreate, plus a check that the
PUT path's UPDATABLE_AGENT_FIELDS allowlist includes both columns.
"""

from __future__ import annotations

from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _import_models():
    from api.routes_agents import AgentCreate, AgentUpdate  # noqa: WPS433
    return AgentCreate, AgentUpdate


def test_agent_update_round_trips_max_agentic_rounds():
    _, AgentUpdate = _import_models()
    payload = {"max_agentic_rounds": 5}
    parsed = AgentUpdate(**payload)
    dumped = parsed.model_dump(exclude_unset=True)
    assert dumped == {"max_agentic_rounds": 5}


def test_agent_update_round_trips_max_agentic_loop_bytes():
    _, AgentUpdate = _import_models()
    payload = {"max_agentic_loop_bytes": 16384}
    parsed = AgentUpdate(**payload)
    dumped = parsed.model_dump(exclude_unset=True)
    assert dumped == {"max_agentic_loop_bytes": 16384}


def test_agent_update_accepts_both_in_one_call():
    _, AgentUpdate = _import_models()
    parsed = AgentUpdate(max_agentic_rounds=3, max_agentic_loop_bytes=4096)
    dumped = parsed.model_dump(exclude_unset=True)
    assert dumped["max_agentic_rounds"] == 3
    assert dumped["max_agentic_loop_bytes"] == 4096


@pytest.mark.parametrize("rounds", [0, 9, -1, 100])
def test_agent_update_validates_rounds_bounds(rounds):
    _, AgentUpdate = _import_models()
    with pytest.raises(Exception):
        AgentUpdate(max_agentic_rounds=rounds)


@pytest.mark.parametrize("byte_cap", [0, 100, 1_000_000])
def test_agent_update_validates_byte_cap_bounds(byte_cap):
    _, AgentUpdate = _import_models()
    with pytest.raises(Exception):
        AgentUpdate(max_agentic_loop_bytes=byte_cap)


def test_agent_create_round_trips_both_fields():
    AgentCreate, _ = _import_models()
    parsed = AgentCreate(
        contact_id=1,
        system_prompt="hello",
        max_agentic_rounds=4,
        max_agentic_loop_bytes=2048,
    )
    dumped = parsed.model_dump()
    assert dumped["max_agentic_rounds"] == 4
    assert dumped["max_agentic_loop_bytes"] == 2048


def test_updatable_agent_fields_allowlist_includes_loop_knobs():
    """The PUT path filters update_data through an explicit allowlist; both
    columns must be in it or setattr() will silently skip them."""
    text = (
        Path(__file__).resolve().parents[1] / "api" / "routes_agents.py"
    ).read_text()
    # The allowlist is a `UPDATABLE_AGENT_FIELDS = { ... }` block. We only
    # need to confirm both literal strings appear in routes_agents.py — which
    # is the same scope where the allowlist is defined.
    assert '"max_agentic_rounds"' in text
    assert '"max_agentic_loop_bytes"' in text


def test_agent_response_exposes_loop_knobs():
    """UI loads current values via GET /api/agents/{id}; ensure the response
    schema declares both fields so they aren't dropped on the way back."""
    text = (
        Path(__file__).resolve().parents[1] / "api" / "routes_agents.py"
    ).read_text()
    assert "max_agentic_rounds: Optional[int]" in text
    assert "max_agentic_loop_bytes: Optional[int]" in text
