"""v0.7.0 Trigger Case Memory MVP — recall scoping & tenant isolation."""

from __future__ import annotations

import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._case_memory_test_helpers import (  # noqa: E402
    install_test_stubs,
    make_db_session,
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


def _seed_case(
    db,
    *,
    tenant_id: str,
    agent_id: int,
    case_id: int,
    trigger_kind: str,
    problem: str,
):
    from models import CaseMemory

    case = CaseMemory(
        id=case_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        wake_event_id=None,
        continuous_run_id=case_id * 10,
        flow_run_id=None,
        origin_kind="continuous_run",
        trigger_kind=trigger_kind,
        subject_digest=f"digest-{case_id}",
        problem_summary=problem,
        action_summary=f"action for {case_id}",
        outcome_summary=f"outcome for {case_id}",
        outcome_label="resolved",
        vector_store_instance_id=None,
        embedding_provider="local",
        embedding_model="all-MiniLM-L6-v2",
        embedding_dims=384,
        embedding_metric="cosine",
        embedding_task=None,
        vector_refs_json=[{"kind": "problem", "vector_id": f"case_continuous_run_{case_id*10}_problem"}],
        index_status="indexed",
        summary_status="generated",
        occurred_at=datetime.utcnow(),
        indexed_at=datetime.utcnow(),
    )
    db.add(case)
    db.flush()
    return case


def _make_search_record(
    *,
    tenant_id: str,
    agent_id: int,
    case_id: int,
    trigger_kind: str,
    vector_kind: str = "problem",
    distance: float = 0.1,
) -> Dict[str, Any]:
    return {
        "message_id": f"case_continuous_run_{case_id*10}_{vector_kind}",
        "text": f"problem text {case_id}",
        "distance": distance,
        "sender_key": f"case:continuous_run:{case_id*10}",
        "metadata": {
            "tenant_id": tenant_id,
            "agent_id": agent_id,
            "case_id": case_id,
            "wake_event_id": None,
            "vector_store_instance_id": None,
            "origin_kind": "continuous_run",
            "trigger_kind": trigger_kind,
            "vector_kind": vector_kind,
            "embedding_provider": "local",
            "embedding_model": "all-MiniLM-L6-v2",
            "embedding_dims": 384,
            "embedding_metric": "cosine",
        },
    }


def _patch_search_provider(
    monkeypatch,
    canned_results: List[Dict[str, Any]],
):
    """Replace ProviderBridgeStore + resolver so search_similar returns canned hits."""
    from services import case_memory_service as cms

    class _FakeBridge:
        def __init__(self):
            pass

        async def search_similar(
            self, query_text: str, limit: int = 5, sender_key: Optional[str] = None
        ):
            return canned_results[:limit]

        async def search_similar_by_embedding(
            self,
            query_embedding: List[float],
            limit: int = 5,
            sender_key: Optional[str] = None,
        ):
            return canned_results[:limit]

    class _FakeResolver:
        def resolve(self, **kwargs):
            return None

    class _FakeRegistry:
        def get_chromadb_fallback(self, persist_directory):
            return object()  # any non-None placeholder; bridge is faked

    # The service constructs ProviderBridgeStore directly; replace it.
    import agent.memory.providers.bridge as bridge_module
    import agent.memory.providers.resolver as resolver_module
    import agent.memory.providers.registry as registry_module

    monkeypatch.setattr(bridge_module, "ProviderBridgeStore", lambda **kwargs: _FakeBridge())
    monkeypatch.setattr(resolver_module, "VectorStoreResolver", _FakeResolver)
    monkeypatch.setattr(registry_module, "VectorStoreRegistry", _FakeRegistry)


def test_search_returns_own_tenant_only(db_session, monkeypatch):
    seeded_a = seed_world(db_session, tenant_id="tenant-A", agent_id=200, contact_id=300, continuous_agent_id=400)
    seeded_b = seed_world(db_session, tenant_id="tenant-B", agent_id=210, contact_id=310, continuous_agent_id=410)
    _seed_case(db_session, tenant_id="tenant-A", agent_id=200, case_id=1, trigger_kind="jira", problem="Tenant A case")
    _seed_case(db_session, tenant_id="tenant-B", agent_id=210, case_id=2, trigger_kind="jira", problem="Tenant B case")
    db_session.commit()

    canned = [
        _make_search_record(tenant_id="tenant-A", agent_id=200, case_id=1, trigger_kind="jira", distance=0.05),
        _make_search_record(tenant_id="tenant-B", agent_id=210, case_id=2, trigger_kind="jira", distance=0.03),
    ]
    _patch_search_provider(monkeypatch, canned)

    from services.case_memory_service import search_similar_cases

    results = search_similar_cases(
        db_session,
        tenant_id="tenant-A",
        agent_id=200,
        query="incident",
        scope="agent",
        k=5,
        min_similarity=0.5,
        vector="problem",
    )

    assert len(results) == 1
    assert results[0]["case_id"] == 1
    assert all(r["case_id"] != 2 for r in results)


def test_scope_trigger_kind_filters_other_kinds(db_session, monkeypatch):
    seed_world(db_session, tenant_id="tenant-C", agent_id=220, contact_id=320, continuous_agent_id=420)
    _seed_case(db_session, tenant_id="tenant-C", agent_id=220, case_id=11, trigger_kind="jira", problem="jira case")
    _seed_case(db_session, tenant_id="tenant-C", agent_id=220, case_id=12, trigger_kind="github", problem="github case")
    db_session.commit()

    canned = [
        _make_search_record(tenant_id="tenant-C", agent_id=220, case_id=11, trigger_kind="jira", distance=0.05),
        _make_search_record(tenant_id="tenant-C", agent_id=220, case_id=12, trigger_kind="github", distance=0.03),
    ]
    _patch_search_provider(monkeypatch, canned)

    from services.case_memory_service import search_similar_cases

    results = search_similar_cases(
        db_session,
        tenant_id="tenant-C",
        agent_id=220,
        query="incident",
        scope="trigger_kind",
        trigger_kind="jira",
        k=5,
        min_similarity=0.5,
    )

    case_ids = [r["case_id"] for r in results]
    assert 11 in case_ids
    assert 12 not in case_ids


def test_scope_agent_includes_cross_trigger(db_session, monkeypatch):
    seed_world(db_session, tenant_id="tenant-D", agent_id=230, contact_id=330, continuous_agent_id=430)
    _seed_case(db_session, tenant_id="tenant-D", agent_id=230, case_id=21, trigger_kind="jira", problem="jira case")
    _seed_case(db_session, tenant_id="tenant-D", agent_id=230, case_id=22, trigger_kind="github", problem="github case")
    db_session.commit()

    canned = [
        _make_search_record(tenant_id="tenant-D", agent_id=230, case_id=21, trigger_kind="jira", distance=0.05),
        _make_search_record(tenant_id="tenant-D", agent_id=230, case_id=22, trigger_kind="github", distance=0.03),
    ]
    _patch_search_provider(monkeypatch, canned)

    from services.case_memory_service import search_similar_cases

    results = search_similar_cases(
        db_session,
        tenant_id="tenant-D",
        agent_id=230,
        query="incident",
        scope="agent",
        k=5,
        min_similarity=0.5,
    )

    case_ids = {r["case_id"] for r in results}
    assert {21, 22}.issubset(case_ids)
