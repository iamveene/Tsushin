"""
Regression test for BUG-711 — new_contact_welcome flow template.

The first step of the new_contact_welcome template is a Summarization step
configured with `source_step="trigger"`. The handler is supposed to expose
the flow's `trigger_context` (e.g. `{contact_name, contact_phone}`) as the
raw source text so the LLM can compose a personalized welcome message.

Prior to this fix, the BUG-590 path correctly seeded `source_text` from
`flow.trigger_context`, but the immediately-following block unconditionally
re-assigned `source_text` from `source_data.get(...)` — and because there
is no `"trigger"` key in `input_data`, `source_data` was always `{}` and
all the `.get(...)` lookups returned `None`. The clobbered `source_text`
then forced the handler to fall through into the "no thread_id or source
text" failure branch, breaking the template on its very first step.

This test instantiates the handler with a populated trigger context and
asserts the handler reaches the raw-text summarization path with the
trigger payload intact.
"""

import asyncio
import json
import os
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest


sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Stub modules pulled in transitively by flow_engine that aren't relevant
# for handler-level unit testing.
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


from flows.flow_engine import SummarizationStepHandler  # noqa: E402


def _build_handler():
    """Build handler with a db mock that returns None for ConversationThread lookups.

    The handler's BUG-634 fallback queries ConversationThread to recover a
    thread_id when none was provided. With a default MagicMock that fallback
    returns a MagicMock object instead of None, which incorrectly steers the
    handler into Path A (thread-based summarization). Configure the mock so
    the fallback resolves to None and Path B (raw-text summarization) wins.
    """
    db = MagicMock()
    # All db.query(...).join(...).filter(...).order_by(...).first() chains
    # used by the BUG-634 fallback should resolve to None.
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.first.return_value = None
    # Also defang the simple db.query(...).filter(...).first() chain for
    # ConversationThread lookups (Path A entry point).
    db.query.return_value.filter.return_value.first.return_value = None
    handler = SummarizationStepHandler(db=db, mcp_sender=MagicMock())
    return handler


def test_summarization_preserves_trigger_context_source_text(monkeypatch):
    """BUG-711: source_text seeded from trigger_context must NOT be clobbered.

    Reproduces the new_contact_welcome failure mode: when `source_step="trigger"`
    and there is no `"trigger"` key in `input_data`, the handler must keep the
    JSON-dumped trigger_context as the raw source text instead of overwriting
    it with `None`.
    """
    handler = _build_handler()

    # Capture what _summarize_raw_text receives so we can assert the
    # trigger payload reached it intact.
    captured: dict = {}

    async def fake_summarize_raw_text(source_text, config, source_step=None, flow_run=None):
        captured["source_text"] = source_text
        captured["config"] = config
        captured["source_step"] = source_step
        return {
            "status": "completed",
            "summary": "Hi Alice — welcome aboard!",
            "transcript": source_text,
            "source_step": source_step or "previous_step",
        }

    monkeypatch.setattr(handler, "_summarize_raw_text", fake_summarize_raw_text)

    step = SimpleNamespace(
        config_json=json.dumps(
            {
                "source_step": "trigger",
                "output_format": "minimal",
                "summary_prompt": "Compose a 2-sentence welcome for the contact below.",
                "prompt_mode": "replace",
            }
        )
    )

    flow_run = SimpleNamespace(id=1, tenant_id="tenant-test")
    step_run = SimpleNamespace(id=1)

    # `_build_step_context` exposes trigger_context under input_data["flow"].
    # Critically, there is no top-level "trigger" key — that's what triggers
    # the BUG-711 clobber path (source_data == {}).
    trigger_payload = {
        "contact_name": "Alice",
        "contact_phone": "+15551234567",
    }
    input_data = {
        "flow": {
            "id": flow_run.id,
            "trigger_context": trigger_payload,
        },
        "previous_step": None,
        "steps": {},
    }

    result = asyncio.run(handler.execute(step, input_data, flow_run, step_run))

    # The handler should reach the raw-text summarization path, not the
    # "no thread_id or source text found" failure branch.
    assert result["status"] == "completed", (
        f"Handler unexpectedly failed — likely BUG-711 regression. "
        f"Result: {result}"
    )
    assert "source_text" in captured, (
        "Handler did not call _summarize_raw_text — trigger-context source "
        "text was clobbered (BUG-711 regression)."
    )

    # The seeded source_text is the JSON-dumped trigger context. Confirm
    # the contact fields survived.
    assert "Alice" in captured["source_text"]
    assert "+15551234567" in captured["source_text"]
    assert captured["source_step"] == "trigger"


def test_summarization_failure_when_trigger_context_empty():
    """Sanity check: with no trigger_context AND no source_text, handler fails cleanly.

    This guards against the inverse mistake of accidentally accepting an
    empty trigger payload as valid input.
    """
    handler = _build_handler()

    step = SimpleNamespace(
        config_json=json.dumps(
            {
                "source_step": "trigger",
                "output_format": "minimal",
                "summary_prompt": "Welcome.",
                "prompt_mode": "replace",
            }
        )
    )
    flow_run = SimpleNamespace(id=1, tenant_id="tenant-test")
    step_run = SimpleNamespace(id=1)

    input_data = {
        "flow": {"id": flow_run.id, "trigger_context": {}},
        "previous_step": None,
        "steps": {},
    }

    result = asyncio.run(handler.execute(step, input_data, flow_run, step_run))

    assert result["status"] == "failed"
    assert "No thread_id or source text" in result.get("error", "")


def test_summarization_inline_text_in_config_is_preserved():
    """BUG-711 corollary: inline `text`/`content` in config_json should also survive.

    The same clobber path would have nuked inline text if the user supplied
    both `source_step` and `text` (a less-common but valid combination).
    """
    handler = _build_handler()

    captured: dict = {}

    async def fake_summarize_raw_text(source_text, config, source_step=None, flow_run=None):
        captured["source_text"] = source_text
        return {"status": "completed", "summary": "ok", "transcript": source_text}

    handler._summarize_raw_text = fake_summarize_raw_text

    step = SimpleNamespace(
        config_json=json.dumps(
            {
                "source_step": "step_99_does_not_exist",  # absent → source_data == {}
                "text": "Inline text body that must NOT be clobbered.",
                "output_format": "brief",
            }
        )
    )
    flow_run = SimpleNamespace(id=1, tenant_id="tenant-test")
    step_run = SimpleNamespace(id=1)

    input_data = {
        "flow": {"id": 1, "trigger_context": {}},
        "previous_step": None,
        "steps": {},
    }

    result = asyncio.run(handler.execute(step, input_data, flow_run, step_run))

    assert result["status"] == "completed"
    assert captured["source_text"] == "Inline text body that must NOT be clobbered."
