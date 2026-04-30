"""v0.7.0 Trigger Case Memory MVP — embedding contract metadata + dim validation."""

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


def _patch_bridge(monkeypatch):
    """Make the bridge writer a no-op recorder so we exercise the row write path."""
    from services import case_memory_service as cms

    async def fake_write(
        db, *, tenant_id, agent, case_id, wake_event_id, origin_kind,
        run_id, trigger_kind, contract, vectors, **_kwargs,
    ):
        return [kind for kind, _, _ in vectors]

    monkeypatch.setattr(cms, "_write_vectors_via_bridge", fake_write)


def _seed_default_instance(db, tenant_id: str, *, instance_id: int, dims: int):
    from models import VectorStoreInstance

    instance = VectorStoreInstance(
        id=instance_id,
        tenant_id=tenant_id,
        vendor="qdrant",
        instance_name=f"primary-{tenant_id}",
        description="test",
        base_url="http://qdrant.example",
        credentials_encrypted=None,
        extra_config={"embedding_dims": dims, "embedding_model": "fake-embedder", "metric": "cosine"},
        is_default=True,
        is_active=True,
    )
    db.add(instance)
    db.flush()
    return instance


def test_default_local_384(db_session, monkeypatch):
    """No VectorStoreInstance configured → contract = local / MiniLM / 384 / cosine."""
    from services import case_memory_service as cms

    monkeypatch.setattr(cms, "_embed_texts", FakeEmbedder(dimension=384))
    _patch_bridge(monkeypatch)

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

    case = cms.index_case(
        db_session,
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        origin_kind="continuous_run",
        run_id=run.id,
        wake_event_id=wake.id,
    )
    assert case.embedding_provider == "local"
    assert case.embedding_model == "all-MiniLM-L6-v2"
    assert case.embedding_dims == 384
    assert case.embedding_metric == "cosine"
    assert case.vector_store_instance_id is None


def test_mocked_768_writes_to_matching_instance(db_session, monkeypatch):
    """A 768-dim default instance pinned via extra_config gets stamped on the case."""
    from services import case_memory_service as cms

    monkeypatch.setattr(cms, "_embed_texts", FakeEmbedder(dimension=768))
    _patch_bridge(monkeypatch)

    seeded = seed_world(db_session, tenant_id="tenant-768", agent_id=140, contact_id=240, continuous_agent_id=340)
    instance = _seed_default_instance(db_session, seeded["tenant_id"], instance_id=901, dims=768)
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

    case = cms.index_case(
        db_session,
        tenant_id=seeded["tenant_id"],
        agent_id=seeded["agent_id"],
        origin_kind="continuous_run",
        run_id=run.id,
        wake_event_id=wake.id,
    )
    # v0.7.x Wave 1-B fix: provider is now read from
    # ``extra_config.embedding_provider`` (not from instance.vendor).
    # The test's fixture omits ``embedding_provider``, so the contract
    # falls back to the default "local" — the previous "qdrant" answer
    # was the load-bearing bug this wave fixed.
    assert case.embedding_provider == "local"
    assert case.embedding_model == "fake-embedder"
    assert case.embedding_dims == 768
    assert case.vector_store_instance_id == instance.id
    assert case.index_status == "indexed"


def test_dimension_mismatch_marks_case_failed_run_untouched(db_session, monkeypatch):
    """Embedder returns 768-d vectors but contract says 384 → case marked failed; run untouched."""
    from services import case_memory_service as cms
    from services.case_embedding_resolver import EmbeddingDimensionMismatch

    # Tenant has a 384-dim default instance, but the (faked) embedder returns 768-dim vectors.
    monkeypatch.setattr(cms, "_embed_texts", FakeEmbedder(dimension=768))
    _patch_bridge(monkeypatch)

    seeded = seed_world(db_session, tenant_id="tenant-mismatch", agent_id=150, contact_id=250, continuous_agent_id=350)
    _seed_default_instance(db_session, seeded["tenant_id"], instance_id=902, dims=384)
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
        outcome_state={"answer": "ran the playbook"},
    )
    original_status = run.status
    original_finished_at = run.finished_at
    db_session.commit()

    with pytest.raises(EmbeddingDimensionMismatch):
        cms.index_case(
            db_session,
            tenant_id=seeded["tenant_id"],
            agent_id=seeded["agent_id"],
            origin_kind="continuous_run",
            run_id=run.id,
            wake_event_id=wake.id,
        )

    # CaseMemory row exists, marked failed.
    from models import CaseMemory

    rows = db_session.query(CaseMemory).all()
    assert len(rows) == 1
    assert rows[0].index_status == "failed"
    # Original run unchanged.
    db_session.refresh(run)
    assert run.status == original_status
    assert run.finished_at == original_finished_at


def test_changing_embedding_dims_after_data_rejected(db_session):
    """Defensive guard rejects mutating ``embedding_dims`` after CaseMemory rows exist."""
    from models import CaseMemory
    from services.case_embedding_resolver import reject_post_data_dims_mutation

    seeded = seed_world(db_session, tenant_id="tenant-immutable", agent_id=160, contact_id=260, continuous_agent_id=360)
    _seed_default_instance(db_session, seeded["tenant_id"], instance_id=903, dims=384)

    # Existing case stamped at 384.
    db_session.add(
        CaseMemory(
            tenant_id=seeded["tenant_id"],
            agent_id=seeded["agent_id"],
            origin_kind="continuous_run",
            continuous_run_id=999,
            outcome_label="resolved",
            embedding_provider="qdrant",
            embedding_model="fake",
            embedding_dims=384,
            embedding_metric="cosine",
            vector_store_instance_id=903,
            index_status="indexed",
            summary_status="generated",
        )
    )
    db_session.commit()

    with pytest.raises(RuntimeError, match="Refusing to change"):
        reject_post_data_dims_mutation(
            db_session,
            tenant_id=seeded["tenant_id"],
            instance_id=903,
            new_dims=1536,
        )

    # Same dims is a no-op.
    reject_post_data_dims_mutation(
        db_session,
        tenant_id=seeded["tenant_id"],
        instance_id=903,
        new_dims=384,
    )
