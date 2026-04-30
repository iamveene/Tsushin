"""v0.7.0 Trigger Case Memory MVP — admin/debug API tests.

Calls the route handlers directly with a stub TenantContext, the same
pattern used by ``test_routes_email_triggers.py``. The auth + permission
dependencies (``require_permission("agents.read")``) are verified at
runtime when the FastAPI app mounts the router; this suite focuses on
behavior + tenant isolation.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

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


def _make_ctx(tenant_id: str):
    """Build a minimal TenantContext-like object with filter_by_tenant."""

    class _Ctx:
        def __init__(self, tid: str):
            self.tenant_id = tid
            self.is_global_admin = False

        def filter_by_tenant(self, query, column, include_shared: bool = False):
            return query.filter(column == self.tenant_id)

    return _Ctx(tenant_id)


def _seed_case_row(
    db,
    *,
    tenant_id: str,
    agent_id: int,
    case_id: int,
    trigger_kind: str = "jira",
    origin_kind: str = "continuous_run",
):
    from models import CaseMemory

    case = CaseMemory(
        id=case_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        wake_event_id=None,
        continuous_run_id=case_id * 100 if origin_kind == "continuous_run" else None,
        flow_run_id=case_id * 100 if origin_kind == "flow_run" else None,
        origin_kind=origin_kind,
        trigger_kind=trigger_kind,
        subject_digest=f"digest-{case_id}",
        problem_summary=f"problem {case_id}",
        action_summary=f"action {case_id}",
        outcome_summary=f"outcome {case_id}",
        outcome_label="resolved",
        embedding_provider="local",
        embedding_model="all-MiniLM-L6-v2",
        embedding_dims=384,
        embedding_metric="cosine",
        index_status="indexed",
        summary_status="generated",
        occurred_at=datetime.utcnow(),
        indexed_at=datetime.utcnow(),
    )
    db.add(case)
    db.flush()
    return case


def test_list_filters_by_tenant(db_session):
    seed_world(db_session, tenant_id="tenant-A", agent_id=200, contact_id=300, continuous_agent_id=400)
    seed_world(db_session, tenant_id="tenant-B", agent_id=210, contact_id=310, continuous_agent_id=410)
    _seed_case_row(db_session, tenant_id="tenant-A", agent_id=200, case_id=1)
    _seed_case_row(db_session, tenant_id="tenant-A", agent_id=200, case_id=2)
    _seed_case_row(db_session, tenant_id="tenant-B", agent_id=210, case_id=3)
    db_session.commit()

    from api.routes_case_memory import list_case_memory

    page = list_case_memory(
        agent_id=None,
        trigger_kind=None,
        origin_kind=None,
        limit=50,
        offset=0,
        ctx=_make_ctx("tenant-A"),
        _=SimpleNamespace(),
        db=db_session,
    )

    assert page.total == 2
    case_ids = sorted(item.id for item in page.items)
    assert case_ids == [1, 2]


def test_get_404_other_tenant(db_session):
    seed_world(db_session, tenant_id="tenant-A", agent_id=200, contact_id=300, continuous_agent_id=400)
    seed_world(db_session, tenant_id="tenant-B", agent_id=210, contact_id=310, continuous_agent_id=410)
    _seed_case_row(db_session, tenant_id="tenant-A", agent_id=200, case_id=1)
    db_session.commit()

    from api.routes_case_memory import get_case_memory

    # Same-tenant fetch works.
    row = get_case_memory(
        case_id=1,
        ctx=_make_ctx("tenant-A"),
        _=SimpleNamespace(),
        db=db_session,
    )
    assert row.id == 1

    # Cross-tenant fetch raises 404.
    with pytest.raises(HTTPException) as excinfo:
        get_case_memory(
            case_id=1,
            ctx=_make_ctx("tenant-B"),
            _=SimpleNamespace(),
            db=db_session,
        )
    assert excinfo.value.status_code == 404


def test_search_returns_results_for_own_tenant(db_session, monkeypatch):
    seed_world(db_session, tenant_id="tenant-S", agent_id=220, contact_id=320, continuous_agent_id=420)
    case = _seed_case_row(db_session, tenant_id="tenant-S", agent_id=220, case_id=11, trigger_kind="jira")
    db_session.commit()

    # Stub the search service to return a canned hit.
    canned_hit = {
        "case_id": case.id,
        "occurred_at_iso": case.occurred_at.isoformat() if case.occurred_at else None,
        "similarity": 0.9,
        "problem_summary": case.problem_summary,
        "action_summary": case.action_summary,
        "outcome_summary": case.outcome_summary,
        "outcome_label": case.outcome_label,
        "origin_kind": case.origin_kind,
        "trigger_kind": case.trigger_kind,
        "wake_event_id": case.wake_event_id,
        "continuous_run_id": case.continuous_run_id,
        "flow_run_id": case.flow_run_id,
    }

    from services import case_memory_service as cms

    def fake_search(*args, **kwargs):
        return [canned_hit]

    monkeypatch.setattr(cms, "search_similar_cases", fake_search)

    from api.routes_case_memory import CaseMemorySearchRequest, search_case_memory

    body = CaseMemorySearchRequest(
        query="firewall outage",
        scope="agent",
        k=3,
        min_similarity=0.5,
        vector="problem",
        agent_id=220,
    )
    resp = search_case_memory(
        body=body,
        ctx=_make_ctx("tenant-S"),
        _=SimpleNamespace(),
        db=db_session,
    )
    assert len(resp.items) == 1
    assert resp.items[0].case_id == case.id
    assert resp.scope == "agent"


def test_search_excludes_other_tenant(db_session, monkeypatch):
    seed_world(db_session, tenant_id="tenant-X", agent_id=230, contact_id=330, continuous_agent_id=430)
    seed_world(db_session, tenant_id="tenant-Y", agent_id=240, contact_id=340, continuous_agent_id=440)
    _seed_case_row(db_session, tenant_id="tenant-Y", agent_id=240, case_id=22, trigger_kind="jira")
    db_session.commit()

    from services import case_memory_service as cms

    captured = {}

    def fake_search(*args, **kwargs):
        # Tests the route passed the right tenant to the service.
        captured.update(kwargs)
        # Tenant-X has no cases → return empty.
        return [] if kwargs.get("tenant_id") == "tenant-X" else [{
            "case_id": 22, "similarity": 0.9, "problem_summary": "p",
            "action_summary": "a", "outcome_summary": "o", "outcome_label": "resolved",
            "origin_kind": "continuous_run", "trigger_kind": "jira", "wake_event_id": None,
            "continuous_run_id": 2200, "flow_run_id": None, "occurred_at_iso": None,
        }]

    monkeypatch.setattr(cms, "search_similar_cases", fake_search)

    from api.routes_case_memory import CaseMemorySearchRequest, search_case_memory

    resp = search_case_memory(
        body=CaseMemorySearchRequest(
            query="incident", scope="tenant", k=3, agent_id=230
        ),
        ctx=_make_ctx("tenant-X"),
        _=SimpleNamespace(),
        db=db_session,
    )
    assert resp.items == []
    assert captured["tenant_id"] == "tenant-X"


def test_search_validates_agent_belongs_to_tenant(db_session):
    seed_world(db_session, tenant_id="tenant-A", agent_id=200, contact_id=300, continuous_agent_id=400)
    seed_world(db_session, tenant_id="tenant-B", agent_id=210, contact_id=310, continuous_agent_id=410)
    db_session.commit()

    from api.routes_case_memory import CaseMemorySearchRequest, search_case_memory

    # Tenant-A user trying to search using Tenant-B's agent_id → 404.
    with pytest.raises(HTTPException) as excinfo:
        search_case_memory(
            body=CaseMemorySearchRequest(
                query="incident", scope="agent", k=3, agent_id=210
            ),
            ctx=_make_ctx("tenant-A"),
            _=SimpleNamespace(),
            db=db_session,
        )
    assert excinfo.value.status_code == 404


def test_search_scope_tenant_requires_agent_id(db_session):
    seed_world(db_session, tenant_id="tenant-A", agent_id=260, contact_id=360, continuous_agent_id=460)
    db_session.commit()

    from api.routes_case_memory import CaseMemorySearchRequest, search_case_memory

    # scope="tenant" with no agent_id is rejected by the v0.7.0 MVP API:
    # the underlying vector store is resolved per agent, so a representative
    # agent_id must be supplied.
    with pytest.raises(HTTPException) as excinfo:
        search_case_memory(
            body=CaseMemorySearchRequest(query="incident", scope="tenant", k=3),
            ctx=_make_ctx("tenant-A"),
            _=SimpleNamespace(),
            db=db_session,
        )
    assert excinfo.value.status_code == 400
    assert "scope='tenant' requires agent_id" in excinfo.value.detail
