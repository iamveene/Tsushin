"""v0.7.0 Trigger Case Memory MVP — FlowRun indexing path.

Trigger-origin FlowRuns (with ``trigger_event_id``) are indexed even when
no legacy ContinuousRun exists. Manual / scheduled FlowRuns
(``trigger_event_id is None``) are NOT indexed per MVP scope.
"""

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
    seed_flow_run,
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
    # v0.7.x — kept as a thin no-op; the case-memory subsystem is always active.
    return None


def _patch_indexer_io(monkeypatch, *, dimension: int = 384):
    from services import case_memory_service as cms

    embedder = FakeEmbedder(dimension=dimension)
    monkeypatch.setattr(cms, "_embed_texts", embedder)

    provider = RecordingProvider()

    async def fake_write(
        db, *, tenant_id, agent, case_id, wake_event_id, origin_kind,
        run_id, trigger_kind, contract, vectors, **_kwargs,
    ):
        for kind, text, emb in vectors:
            await provider.add_message(
                message_id=f"case_{origin_kind}_{run_id}_{kind}",
                sender_key=f"case:{origin_kind}:{run_id}",
                text=text,
                metadata={
                    "tenant_id": tenant_id,
                    "agent_id": agent.id,
                    "case_id": case_id,
                    "wake_event_id": wake_event_id,
                    "origin_kind": origin_kind,
                    "trigger_kind": trigger_kind,
                    "vector_kind": kind,
                    "embedding_provider": contract.provider,
                    "embedding_model": contract.model,
                    "embedding_dims": contract.dimensions,
                    "embedding_metric": contract.metric,
                    "vector_store_instance_id": contract.vector_store_instance_id,
                },
            )
        return [kind for kind, _, _ in vectors]

    monkeypatch.setattr(cms, "_write_vectors_via_bridge", fake_write)
    return embedder, provider


def test_trigger_origin_flow_run_indexed(db_session, monkeypatch):
    _flag_on(monkeypatch)
    _patch_indexer_io(monkeypatch)

    from models import CaseMemory, MessageQueue
    from services.message_queue_service import MessageQueueService
    from services.queue_router import QueueRouter
    from services.case_memory_service import index_case

    seeded = seed_world(db_session, tenant_id="tenant-flow-a", agent_id=120, contact_id=220, continuous_agent_id=320)
    wake = seed_wake_event(
        db_session,
        tenant_id=seeded["tenant_id"],
        channel_type="github",
        event_type="issues.opened",
    )
    flow_run = seed_flow_run(
        db_session,
        tenant_id=seeded["tenant_id"],
        flow_definition_id=21,
        trigger_event_id=wake.id,
        status="completed",
    )
    db_session.commit()

    # Drive the queue dispatch so the case_index queue item is enqueued.
    queue_item = MessageQueueService(db_session).enqueue(
        channel="flow",
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        sender_key=f"trigger:{wake.id}:flow:21",
        payload={
            "flow_definition_id": 21,
            "binding_id": None,
            "trigger_event_id": wake.id,
            "trigger_context": {},
        },
        message_type="flow_run_triggered",
    )
    db_session.commit()

    class _FakeFlowEngine:
        def __init__(self, db):
            self.db = db

        async def run_flow(self, *, flow_definition_id, trigger_context, initiator,
                           trigger_type, tenant_id, trigger_event_id, binding_id):
            return flow_run

    fake_module = SimpleNamespace(FlowEngine=_FakeFlowEngine)
    monkeypatch.setitem(sys.modules, "flows.flow_engine", fake_module)

    asyncio.run(QueueRouter().dispatch(SimpleNamespace(), db_session, queue_item))

    case_index_rows = (
        db_session.query(MessageQueue)
        .filter(MessageQueue.message_type == "case_index")
        .all()
    )
    assert len(case_index_rows) == 1
    payload = case_index_rows[0].payload
    assert payload["origin_kind"] == "flow_run"
    assert payload["flow_run_id"] == flow_run.id
    assert payload["wake_event_id"] == wake.id

    # Run the indexer manually to assert a CaseMemory row materializes —
    # the queue worker would normally invoke this via _dispatch_case_index.
    case = index_case(
        db_session,
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        origin_kind="flow_run",
        run_id=flow_run.id,
        wake_event_id=wake.id,
    )
    assert case is not None
    assert case.origin_kind == "flow_run"
    assert case.flow_run_id == flow_run.id
    assert case.continuous_run_id is None
    rows = db_session.query(CaseMemory).all()
    assert len(rows) == 1


def test_manual_flow_run_not_indexed(db_session, monkeypatch):
    _flag_on(monkeypatch)
    _patch_indexer_io(monkeypatch)

    from models import CaseMemory, MessageQueue
    from services.message_queue_service import MessageQueueService
    from services.queue_router import QueueRouter

    seeded = seed_world(
        db_session,
        tenant_id="tenant-flow-b",
        agent_id=130,
        contact_id=230,
        continuous_agent_id=330,
    )
    flow_run = seed_flow_run(
        db_session,
        tenant_id=seeded["tenant_id"],
        flow_definition_id=22,
        trigger_event_id=None,
        status="completed",
    )
    db_session.commit()

    queue_item = MessageQueueService(db_session).enqueue(
        channel="flow",
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        sender_key="manual:flow:22",
        payload={
            "flow_definition_id": 22,
            "binding_id": None,
            "trigger_event_id": None,
            "trigger_context": {},
        },
        message_type="flow_run_triggered",
    )
    db_session.commit()

    class _FakeFlowEngine:
        def __init__(self, db):
            self.db = db

        async def run_flow(self, *, flow_definition_id, trigger_context, initiator,
                           trigger_type, tenant_id, trigger_event_id, binding_id):
            return flow_run

    fake_module = SimpleNamespace(FlowEngine=_FakeFlowEngine)
    monkeypatch.setitem(sys.modules, "flows.flow_engine", fake_module)

    asyncio.run(QueueRouter().dispatch(SimpleNamespace(), db_session, queue_item))

    case_index_rows = (
        db_session.query(MessageQueue)
        .filter(MessageQueue.message_type == "case_index")
        .all()
    )
    assert case_index_rows == []
    assert db_session.query(CaseMemory).all() == []
