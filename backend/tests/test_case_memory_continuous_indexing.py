"""v0.7.0 Trigger Case Memory MVP — ContinuousRun indexing path."""

from __future__ import annotations

import asyncio
import os
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._case_memory_test_helpers import (  # noqa: E402
    FakeEmbedder,
    RecordingProvider,
    install_test_stubs,
    make_db_session,
    seed_continuous_run,
    seed_wake_event,
    seed_world,
)

install_test_stubs()


@pytest.fixture
def db_session():
    db = make_db_session()
    try:
        yield db
    finally:
        db.close()


def _flag_on(monkeypatch):
    """v0.7.x — kept as a thin no-op helper. The case-memory subsystem is
    always active now (no global env kill-switch). Per-trigger opt-in lives
    on TriggerRecapConfig.enabled. This helper is preserved so the existing
    tests remain readable without forcing every call site to drop the
    monkeypatch line."""
    return None


def _patch_indexer_io(monkeypatch, *, dimension: int = 384):
    """Replace the embedder + bridge writer with in-memory fakes."""
    from services import case_memory_service as cms

    embedder = FakeEmbedder(dimension=dimension)
    monkeypatch.setattr(cms, "_embed_texts", embedder)

    provider = RecordingProvider()

    async def fake_write(
        db,
        *,
        tenant_id,
        agent,
        case_id,
        wake_event_id,
        origin_kind,
        run_id,
        trigger_kind,
        contract,
        vectors,
        **_kwargs,
    ):
        for kind, text, emb in vectors:
            metadata = {
                "tenant_id": tenant_id,
                "agent_id": agent.id,
                "case_id": case_id,
                "wake_event_id": wake_event_id,
                "vector_store_instance_id": contract.vector_store_instance_id,
                "origin_kind": origin_kind,
                "trigger_kind": trigger_kind,
                "vector_kind": kind,
                "embedding_provider": contract.provider,
                "embedding_model": contract.model,
                "embedding_dims": contract.dimensions,
                "embedding_metric": contract.metric,
            }
            await provider.add_message(
                message_id=f"case_{origin_kind}_{run_id}_{kind}",
                sender_key=f"case:{origin_kind}:{run_id}",
                text=text,
                metadata=metadata,
            )
        return [kind for kind, _, _ in vectors]

    monkeypatch.setattr(cms, "_write_vectors_via_bridge", fake_write)
    return embedder, provider


def test_terminal_continuous_run_enqueues_case_index(db_session, monkeypatch):
    _flag_on(monkeypatch)

    from models import MessageQueue
    from services import queue_router as queue_router_module
    from services.message_queue_service import MessageQueueService
    from services.queue_router import QueueRouter

    seeded = seed_world(db_session)
    wake = seed_wake_event(
        db_session,
        tenant_id=seeded["tenant_id"],
        continuous_agent_id=seeded["continuous_agent_id"],
    )
    run = seed_continuous_run(
        db_session,
        tenant_id=seeded["tenant_id"],
        continuous_agent_id=seeded["continuous_agent_id"],
        wake_event_id=wake.id,
        status="queued",
    )
    queue_item = MessageQueueService(db_session).enqueue(
        channel="continuous",
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        sender_key=f"continuous:{seeded['continuous_agent_id']}",
        payload={
            "continuous_run_id": run.id,
            "wake_event_id": wake.id,
        },
        message_type="continuous_task",
    )
    db_session.commit()

    async def fake_invoke(*, db, agent, continuous_agent, run, sender_key, message_text):
        return {"answer": "ok", "error": None, "tokens": {}}

    monkeypatch.setattr(
        queue_router_module, "_invoke_agent_for_continuous_run", fake_invoke
    )

    asyncio.run(QueueRouter().dispatch(SimpleNamespace(), db_session, queue_item))

    case_index_rows = (
        db_session.query(MessageQueue)
        .filter(MessageQueue.message_type == "case_index")
        .all()
    )
    assert len(case_index_rows) == 1, [
        (r.id, r.message_type, r.payload) for r in case_index_rows
    ]
    payload = case_index_rows[0].payload
    assert payload["origin_kind"] == "continuous_run"
    assert payload["continuous_run_id"] == run.id
    assert payload["wake_event_id"] == wake.id


def test_indexer_creates_case_memory_row(db_session, monkeypatch):
    _flag_on(monkeypatch)
    embedder, provider = _patch_indexer_io(monkeypatch)

    from models import CaseMemory
    from services.case_memory_service import index_case

    seeded = seed_world(db_session)
    wake = seed_wake_event(
        db_session,
        tenant_id=seeded["tenant_id"],
        continuous_agent_id=seeded["continuous_agent_id"],
        channel_type="jira",
        event_type="issue.created",
    )
    run = seed_continuous_run(
        db_session,
        tenant_id=seeded["tenant_id"],
        continuous_agent_id=seeded["continuous_agent_id"],
        wake_event_id=wake.id,
        status="succeeded",
        outcome_state={"answer": "Replaced firewall rule per playbook FW-12."},
    )
    db_session.commit()

    case = index_case(
        db_session,
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        origin_kind="continuous_run",
        run_id=run.id,
        wake_event_id=wake.id,
    )

    assert case is not None
    assert case.tenant_id == seeded["tenant_id"]
    assert case.agent_id == seeded["agent_id"]
    assert case.origin_kind == "continuous_run"
    assert case.continuous_run_id == run.id
    assert case.flow_run_id is None
    assert case.trigger_kind == "jira"
    assert case.outcome_label == "resolved"
    assert case.embedding_provider == "local"
    assert case.embedding_dims == 384
    assert case.embedding_metric == "cosine"
    assert case.index_status == "indexed"
    # Vector refs include problem (and others when summary text exists)
    kinds = {ref["kind"] for ref in (case.vector_refs_json or [])}
    assert "problem" in kinds

    rows = db_session.query(CaseMemory).all()
    assert len(rows) == 1


def test_indexer_idempotent(db_session, monkeypatch):
    _flag_on(monkeypatch)
    _patch_indexer_io(monkeypatch)

    from models import CaseMemory
    from services.case_memory_service import index_case

    seeded = seed_world(db_session)
    wake = seed_wake_event(
        db_session,
        tenant_id=seeded["tenant_id"],
        continuous_agent_id=seeded["continuous_agent_id"],
    )
    run = seed_continuous_run(
        db_session,
        tenant_id=seeded["tenant_id"],
        continuous_agent_id=seeded["continuous_agent_id"],
        wake_event_id=wake.id,
        status="succeeded",
    )
    db_session.commit()

    first = index_case(
        db_session,
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        origin_kind="continuous_run",
        run_id=run.id,
        wake_event_id=wake.id,
    )
    second = index_case(
        db_session,
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        origin_kind="continuous_run",
        run_id=run.id,
        wake_event_id=wake.id,
    )

    assert first.id == second.id
    rows = db_session.query(CaseMemory).all()
    assert len(rows) == 1
