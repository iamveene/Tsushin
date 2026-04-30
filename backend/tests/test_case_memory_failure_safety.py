"""v0.7.0 Trigger Case Memory MVP — failure-safety guarantees.

Broken payload_ref, summary failure, and vector-store failure must NOT
fail the original trigger run. Partial indexing is recorded as
``partial`` (problem vector landed) or ``failed`` (problem did not land).
"""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._case_memory_test_helpers import (  # noqa: E402
    FakeEmbedder,
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


def test_broken_payload_ref_marks_failed_run_untouched(db_session, monkeypatch):
    """payload_ref that doesn't exist on disk → still indexes (with thinner signal)."""
    from services import case_memory_service as cms

    monkeypatch.setattr(cms, "_embed_texts", FakeEmbedder(dimension=384))

    async def fake_write(
        db, *, tenant_id, agent, case_id, wake_event_id, origin_kind,
        run_id, trigger_kind, contract, vectors, **_kwargs,
    ):
        return [kind for kind, _, _ in vectors]

    monkeypatch.setattr(cms, "_write_vectors_via_bridge", fake_write)

    seeded = seed_world(db_session)
    wake = seed_wake_event(
        db_session,
        tenant_id=seeded["tenant_id"],
        continuous_agent_id=seeded["continuous_agent_id"],
        payload_ref="/nonexistent/path/that/never/existed.json",
    )
    run = seed_continuous_run(
        db_session,
        tenant_id=seeded["tenant_id"],
        continuous_agent_id=seeded["continuous_agent_id"],
        wake_event_id=wake.id,
        status="succeeded",
    )
    original_status = run.status
    original_finished_at = run.finished_at
    db_session.commit()

    case = cms.index_case(
        db_session,
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        origin_kind="continuous_run",
        run_id=run.id,
        wake_event_id=wake.id,
    )
    assert case is not None
    # Even with a broken payload_ref, the indexer falls back to event_type:dedupe_key
    # for the problem text and indexes successfully.
    assert case.problem_summary
    assert case.index_status in ("indexed", "partial")

    # Run state untouched.
    db_session.refresh(run)
    assert run.status == original_status
    assert run.finished_at == original_finished_at


def test_action_summary_failure_falls_back_to_problem_only(db_session, monkeypatch):
    """When action_summary text is empty, summary_status='fallback' and only problem vector lands."""
    from services import case_memory_service as cms

    monkeypatch.setattr(cms, "_embed_texts", FakeEmbedder(dimension=384))

    async def fake_write(
        db, *, tenant_id, agent, case_id, wake_event_id, origin_kind,
        run_id, trigger_kind, contract, vectors, **_kwargs,
    ):
        return [kind for kind, _, _ in vectors]

    monkeypatch.setattr(cms, "_write_vectors_via_bridge", fake_write)

    seeded = seed_world(db_session, tenant_id="tenant-fallback", agent_id=170, contact_id=270, continuous_agent_id=370)
    wake = seed_wake_event(
        db_session,
        tenant_id=seeded["tenant_id"],
        continuous_agent_id=seeded["continuous_agent_id"],
    )
    # outcome_state without an "answer" — build_action_text returns "".
    run = seed_continuous_run(
        db_session,
        tenant_id=seeded["tenant_id"],
        continuous_agent_id=seeded["continuous_agent_id"],
        wake_event_id=wake.id,
        status="succeeded",
        outcome_state={"tokens": {"prompt": 1, "completion": 2}},
    )
    db_session.commit()

    case = cms.index_case(
        db_session,
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        origin_kind="continuous_run",
        run_id=run.id,
        wake_event_id=wake.id,
    )
    assert case.summary_status == "fallback"
    kinds = {ref["kind"] for ref in (case.vector_refs_json or [])}
    # Problem must always be there. Action falls back (no text), outcome may
    # still write because we synthesize outcome text from the label + status.
    assert "problem" in kinds
    assert "action" not in kinds


def test_vector_store_failure_marks_failed_or_partial(db_session, monkeypatch):
    """Bridge write throws → case marked failed; run untouched."""
    from services import case_memory_service as cms

    monkeypatch.setattr(cms, "_embed_texts", FakeEmbedder(dimension=384))

    async def failing_write(
        db, *, tenant_id, agent, case_id, wake_event_id, origin_kind,
        run_id, trigger_kind, contract, vectors, **_kwargs,
    ):
        # Simulate vector store outage — return empty written list.
        return []

    monkeypatch.setattr(cms, "_write_vectors_via_bridge", failing_write)

    seeded = seed_world(db_session, tenant_id="tenant-vsfail", agent_id=180, contact_id=280, continuous_agent_id=380)
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
    original_status = run.status
    db_session.commit()

    case = cms.index_case(
        db_session,
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        origin_kind="continuous_run",
        run_id=run.id,
        wake_event_id=wake.id,
    )
    # No vectors landed → index_status='failed'.
    assert case.index_status == "failed"
    # Original run untouched.
    db_session.refresh(run)
    assert run.status == original_status
