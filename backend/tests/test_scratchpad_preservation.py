"""
BUG-707 regression: a no-tool turn must NOT overwrite the agentic_scratchpad.

This test verifies the fix lives in the right places and that the contract
between agent_service.process_message() and the persisters
(agent.router.WhatsAppRouter and services.playground_service.PlaygroundService)
is honoured: scratchpad is only written back to the thread when a tool fired.

We don't spin up the full FastAPI stack here — we exercise the persister
guard logic directly with a simulated 3-turn conversation and confirm the
scratchpad survives the no-tool turn in the middle.
"""

from __future__ import annotations

from pathlib import Path
import sys
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def _apply_router_guard(thread, result):
    """Mirror of the BUG-707 guard inside agent.router.handle_thread_message."""
    if result.get("agentic_scratchpad") is not None and (
        result.get("tool_was_called") or result.get("tool_used")
    ):
        thread.agentic_scratchpad = result.get("agentic_scratchpad")


def test_scratchpad_survives_no_tool_turn():
    thread = SimpleNamespace(agentic_scratchpad=None)

    # Turn 1: a tool fires (e.g. nmap quick_scan). Scratchpad gets a row.
    turn1 = {
        "agentic_scratchpad": [
            {"round": 1, "tool_call": {"tool_name": "nmap"},
             "tool_result": {"skill_type": "nmap", "data": {"ip": "93.184.216.34"}}}
        ],
        "tool_used": "skill:nmap",
        "tool_was_called": True,
    }
    _apply_router_guard(thread, turn1)
    assert thread.agentic_scratchpad == turn1["agentic_scratchpad"]

    # Turn 2: user asks "what was the IP?". Followup detector wins, no tool
    # fires. process_message() returns scratchpad=[] (or the prior, doesn't
    # matter) but tool_was_called is False — the guard MUST keep the prior
    # trace intact.
    turn2 = {
        "agentic_scratchpad": [],
        "tool_used": None,
        "tool_was_called": False,
    }
    _apply_router_guard(thread, turn2)
    assert thread.agentic_scratchpad == turn1["agentic_scratchpad"], (
        "BUG-707 regression: a no-tool turn wiped the scratchpad."
    )

    # Turn 3: another tool turn — the guard re-opens and writes through.
    turn3 = {
        "agentic_scratchpad": [
            {"round": 1, "tool_call": {"tool_name": "dig"},
             "tool_result": {"skill_type": "dig", "data": {"a": "1.2.3.4"}}}
        ],
        "tool_used": "skill:dig",
        "tool_was_called": True,
    }
    _apply_router_guard(thread, turn3)
    assert thread.agentic_scratchpad == turn3["agentic_scratchpad"]


def test_router_source_persists_only_when_tool_fired():
    """Static check on backend/agent/router.py — the guard must be present."""
    text = (Path(__file__).resolve().parents[1] / "agent" / "router.py").read_text()
    assert 'result.get("tool_was_called") or result.get("tool_used")' in text, (
        "router.py must gate scratchpad persistence on tool_was_called/tool_used"
    )


def test_playground_source_persists_only_when_tool_fired():
    text = (
        Path(__file__).resolve().parents[1] / "services" / "playground_service.py"
    ).read_text()
    assert 'tool_was_called' in text
    assert 'Preserving agentic scratchpad: no tool fired this turn' in text


def test_agent_service_emits_tool_was_called_flag():
    text = (
        Path(__file__).resolve().parents[1] / "agent" / "agent_service.py"
    ).read_text()
    # The flag is initialised, set on tool execution, and shipped in the
    # final return dict.
    assert "tool_was_called = False" in text
    assert "tool_was_called = True" in text
    assert '"tool_was_called": tool_was_called or bool(tool_used)' in text
