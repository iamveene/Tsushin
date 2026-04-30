"""
Regression test for BUG-713 — flow_run.completed_steps must equal final_report.steps_successful.

After a multi-step flow completes, two fields describe how many steps
succeeded:

1. `flow_run.completed_steps` — column on the FlowRun row, used by the
   UI/list views and `/api/flows/{id}/runs/{run_id}` for the at-a-glance
   "X / N steps" badge.
2. `final_report_json["steps_successful"]` — embedded in the final report
   blob, generated post-hoc by `generate_final_report()` which independently
   sums FlowNodeRun rows with status="completed".

Before this fix the two fields drifted apart on flows with more than one
successful step (observed: 1 vs 3 on the proactive_watcher template).
Root cause: the loop incremented `flow_run.completed_steps` in memory but
the very next iteration started with `self.db.refresh(flow_run)` — which
silently discarded the in-memory increment because it had not been
committed yet. Only the LAST iteration's increment survived.

This test runs a multi-step flow end-to-end (with the AI client mocked out)
and asserts the two fields stay in lock-step.
"""

import asyncio
import json
import os
import sys
import types
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# Stub modules pulled in transitively by flow_engine that aren't relevant
# for handler-level testing.
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


@compiles(JSONB, "sqlite")
def _compile_jsonb_sqlite(_type, _compiler, **_kw):
    return "JSON"


import models_rbac  # noqa: E402, F401  # registers User/Role models so FK resolution works
from flows.flow_engine import ConversationStepHandler, FlowEngine  # noqa: E402
from models import (  # noqa: E402
    Base,
    Contact,
    FlowDefinition,
    FlowNode,
    FlowNodeRun,
    FlowRun,
)


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        echo=False,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine


@pytest.fixture
def db_session(db_engine):
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


def test_resolve_recipient_is_tenant_scoped(db_session):
    db_session.add_all(
        [
            Contact(id=101, tenant_id="tenant-a", friendly_name="Alex", whatsapp_id="wa-a"),
            Contact(id=102, tenant_id="tenant-b", friendly_name="Alex", whatsapp_id="wa-b"),
        ]
    )
    db_session.commit()

    handler = ConversationStepHandler(db_session, MagicMock())

    assert handler._resolve_recipient("@Alex", tenant_id="tenant-a") == "wa-a@lid"
    assert handler._resolve_recipient("@Alex", tenant_id="tenant-b") == "wa-b@lid"
    assert handler._resolve_recipient("@Alex") == "@Alex"


def _make_flow_with_three_message_steps(db_session) -> int:
    """Create a 3-step Message flow definition."""
    flow = FlowDefinition(
        tenant_id="tenant-bug713",
        name="multi-step-counter-test",
        description="3-step flow used to verify BUG-713 counter consolidation.",
        execution_method="immediate",
        flow_type="workflow",
        is_active=True,
        version=1,
    )
    db_session.add(flow)
    db_session.commit()
    db_session.refresh(flow)

    for position in range(1, 4):
        node = FlowNode(
            flow_definition_id=flow.id,
            position=position,
            type="message",
            name=f"step_{position}",
            config_json=json.dumps(
                {
                    "channel": "whatsapp",
                    "recipient": "+15551234567",
                    "message_template": f"Hello from step {position}",
                }
            ),
        )
        db_session.add(node)
    db_session.commit()
    return flow.id


def _stub_message_handler_to_succeed(engine: FlowEngine):
    """Replace the message handler's execute() with a no-op success returning a 'completed' status."""

    async def fake_execute(step, input_data, flow_run, step_run):
        return {
            "status": "completed",
            "channel": "whatsapp",
            "recipients": ["+15551234567"],
            "resolved_recipients": ["+15551234567"],
            "message_sent": True,
        }

    handler = engine.handlers.get("message") or engine.handlers.get("Message")
    handler.execute = fake_execute  # type: ignore[assignment]


def _build_engine(db_session):
    """Construct a FlowEngine with no-op stale-run cleanup and a stub TokenTracker."""
    token_tracker = MagicMock()
    token_tracker.track_request = AsyncMock(return_value=None)
    with patch.object(FlowEngine, "_cleanup_stale_runs", return_value=0):
        engine = FlowEngine(db=db_session, token_tracker=token_tracker)
    return engine


def test_completed_steps_equals_steps_successful_in_final_report(db_engine, db_session):
    """BUG-713: completed_steps must equal final_report.steps_successful for a 3-step success run.

    Without the fix, completed_steps undercounts (==1) while steps_successful
    correctly reports 3. With the fix, both must be 3.
    """
    flow_id = _make_flow_with_three_message_steps(db_session)

    # Build engine bound to the same SQLite session
    Session = sessionmaker(bind=db_engine)
    engine_db = Session()
    engine = _build_engine(engine_db)
    _stub_message_handler_to_succeed(engine)

    # Run the flow
    flow_run = asyncio.run(
        engine.run_flow(
            flow_definition_id=flow_id,
            trigger_context={"unit_test": True},
            initiator="api",
            tenant_id="tenant-bug713",
        )
    )

    # Reload from DB to pick up post-commit values
    db_session.expire_all()
    flow_run_db = db_session.query(FlowRun).filter(FlowRun.id == flow_run.id).one()
    final_report = json.loads(flow_run_db.final_report_json or "{}")

    step_runs = (
        db_session.query(FlowNodeRun)
        .filter(FlowNodeRun.flow_run_id == flow_run_db.id)
        .all()
    )
    successful_step_runs = [sr for sr in step_runs if sr.status == "completed"]

    # Sanity: 3 step_runs, all completed
    assert len(step_runs) == 3, f"expected 3 step_runs, got {len(step_runs)}"
    assert len(successful_step_runs) == 3, (
        f"expected 3 completed step_runs, got {len(successful_step_runs)}"
    )

    # Final report agrees
    assert final_report.get("steps_successful") == 3, (
        f"final_report.steps_successful expected 3, got {final_report.get('steps_successful')}"
    )

    # Core assertion: the column matches the report.
    assert flow_run_db.completed_steps == final_report["steps_successful"], (
        f"BUG-713 regression: flow_run.completed_steps={flow_run_db.completed_steps} "
        f"!= final_report.steps_successful={final_report['steps_successful']}"
    )

    # Also: failed_steps stays in lock-step (both 0 for a clean run).
    assert flow_run_db.failed_steps == final_report.get("steps_failed", 0)

    # And the run is reported as 'completed' (not completed_with_errors / noop).
    assert flow_run_db.status == "completed"

    engine_db.close()


def test_completed_steps_zero_when_first_step_fails(db_engine, db_session):
    """BUG-713 corollary: a flow that fails on step 1 reports 0 successes consistently.

    Both `completed_steps` and `final_report.steps_successful` must agree at 0,
    and `failed_steps` and `final_report.steps_failed` must agree at 1.
    """
    flow_id = _make_flow_with_three_message_steps(db_session)

    Session = sessionmaker(bind=db_engine)
    engine_db = Session()
    engine = _build_engine(engine_db)

    async def fake_execute_fails(step, input_data, flow_run, step_run):
        return {
            "status": "failed",
            "error": "synthetic failure for unit test",
        }

    engine.handlers.get("message").execute = fake_execute_fails  # type: ignore[assignment]

    flow_run = asyncio.run(
        engine.run_flow(
            flow_definition_id=flow_id,
            trigger_context={"unit_test": True},
            initiator="api",
            tenant_id="tenant-bug713",
        )
    )

    db_session.expire_all()
    flow_run_db = db_session.query(FlowRun).filter(FlowRun.id == flow_run.id).one()
    final_report = json.loads(flow_run_db.final_report_json or "{}")

    assert flow_run_db.completed_steps == final_report.get("steps_successful", 0)
    assert flow_run_db.failed_steps == final_report.get("steps_failed", 0)
    assert flow_run_db.completed_steps == 0
    assert flow_run_db.failed_steps == 1
    # Default on_failure is stop, so the run status is "failed".
    assert flow_run_db.status == "failed"

    engine_db.close()
