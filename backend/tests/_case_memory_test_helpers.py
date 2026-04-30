"""Shared helpers for the v0.7.0 Trigger Case Memory MVP test suite.

Stubs out the optional dependencies (``docker``, ``argon2``,
``sentence_transformers``, ``chromadb``) the same way other v0.7.0
tests do, builds an in-memory SQLite engine with the explicit table
list the case-memory codepath touches, and provides seed helpers and
fake-embedder utilities that replace the heavy SentenceTransformer
during indexer tests.
"""

from __future__ import annotations

import os
import sys
import types
from datetime import datetime
from typing import Any, Dict, List, Optional


def install_test_stubs() -> None:
    """Idempotently install module stubs other v0.7.0 tests rely on."""

    # docker
    docker_stub = types.ModuleType("docker")
    docker_stub.errors = types.SimpleNamespace(
        NotFound=Exception, DockerException=Exception
    )
    docker_stub.DockerClient = object
    sys.modules.setdefault("docker", docker_stub)

    # argon2
    argon2_stub = types.ModuleType("argon2")

    class _PasswordHasher:
        def hash(self, value):  # noqa: ANN001
            return value

        def verify(self, hashed, plain):  # noqa: ANN001
            return hashed == plain

    argon2_stub.PasswordHasher = _PasswordHasher
    argon2_exceptions_stub = types.ModuleType("argon2.exceptions")
    argon2_exceptions_stub.VerifyMismatchError = ValueError
    argon2_exceptions_stub.InvalidHashError = ValueError
    sys.modules.setdefault("argon2", argon2_stub)
    sys.modules.setdefault("argon2.exceptions", argon2_exceptions_stub)

    # json_repair
    json_repair_stub = types.ModuleType("json_repair")
    json_repair_stub.repair_json = lambda value: value
    sys.modules.setdefault("json_repair", json_repair_stub)

    # sentence_transformers (only matters as a guard import; the case
    # tests inject a fake embedding service via monkeypatch and bypass
    # the real model entirely). The recall tests (Wave 1-B) exercise
    # ``EmbeddingService._embed_text_sync`` which calls ``.tolist()`` on
    # the encode result, so we return numpy arrays here even though the
    # original v0.7.0 stub returned plain lists.
    if "sentence_transformers" not in sys.modules:
        try:
            import numpy as _np  # noqa: WPS433 — local import for stub
        except Exception:  # pragma: no cover — numpy is a hard dep elsewhere
            _np = None

        st_stub = types.ModuleType("sentence_transformers")

        class _SentenceTransformer:
            def __init__(self, *_args, **_kwargs):
                pass

            def encode(self, texts, **_kwargs):
                if isinstance(texts, str):
                    if _np is not None:
                        return _np.zeros(384, dtype=float)
                    return [0.0] * 384
                if _np is not None:
                    return _np.zeros((len(texts), 384), dtype=float)
                return [[0.0] * 384 for _ in texts]

            def get_sentence_embedding_dimension(self):
                return 384

        st_stub.SentenceTransformer = _SentenceTransformer
        sys.modules["sentence_transformers"] = st_stub

    # chromadb — keep it minimal but importable.
    if "chromadb" not in sys.modules:
        chromadb_stub = types.ModuleType("chromadb")

        class _Collection:
            def count(self):
                return 0

            def query(self, *_args, **_kwargs):
                return {
                    "ids": [[]],
                    "distances": [[]],
                    "documents": [[]],
                    "metadatas": [[]],
                }

            def upsert(self, *_args, **_kwargs):
                return None

        class _PersistentClient:
            def __init__(self, *_args, **_kwargs):
                pass

            def get_or_create_collection(self, *_args, **_kwargs):
                return _Collection()

        chromadb_stub.PersistentClient = _PersistentClient

        chromadb_config_stub = types.ModuleType("chromadb.config")

        class _Settings:
            def __init__(self, *_args, **_kwargs):
                pass

        chromadb_config_stub.Settings = _Settings

        sys.modules["chromadb"] = chromadb_stub
        sys.modules["chromadb.config"] = chromadb_config_stub


def make_db_session():
    """Build an in-memory SQLite session with all tables case-memory touches."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    install_test_stubs()
    BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if BACKEND_ROOT not in sys.path:
        sys.path.insert(0, BACKEND_ROOT)

    from models import (
        Agent,
        Base,
        BudgetPolicy,
        CaseMemory,
        Contact,
        ContinuousAgent,
        ContinuousRun,
        ContinuousSubscription,
        DeliveryPolicy,
        FlowDefinition,
        FlowNode,
        FlowNodeRun,
        FlowRun,
        FlowTriggerBinding,
        MessageQueue,
        SentinelProfile,
        VectorStoreInstance,
        WakeEvent,
    )
    from models_rbac import Tenant, User

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            Contact.__table__,
            Agent.__table__,
            SentinelProfile.__table__,
            DeliveryPolicy.__table__,
            BudgetPolicy.__table__,
            ContinuousAgent.__table__,
            ContinuousSubscription.__table__,
            WakeEvent.__table__,
            ContinuousRun.__table__,
            MessageQueue.__table__,
            VectorStoreInstance.__table__,
            FlowDefinition.__table__,
            FlowNode.__table__,
            FlowRun.__table__,
            FlowNodeRun.__table__,
            FlowTriggerBinding.__table__,
            CaseMemory.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def seed_world(
    db,
    *,
    tenant_id: str = "tenant-x",
    agent_id: int = 100,
    contact_id: int = 200,
    continuous_agent_id: int = 300,
):
    """Minimal seeded world: tenant + user + contact + agent + continuous_agent."""
    from models import Agent, Contact, ContinuousAgent
    from models_rbac import Tenant, User

    db.add(Tenant(id=tenant_id, name=tenant_id.title(), slug=tenant_id))
    db.add(
        User(
            id=hash(tenant_id) & 0x7FFFFFFF,
            tenant_id=tenant_id,
            email=f"{tenant_id}@example.com",
            password_hash="x",
            is_active=True,
        )
    )
    db.add(
        Contact(
            id=contact_id,
            tenant_id=tenant_id,
            friendly_name=f"{tenant_id} Agent",
            role="agent",
        )
    )
    db.add(
        Agent(
            id=agent_id,
            tenant_id=tenant_id,
            contact_id=contact_id,
            system_prompt="prompt",
            model_provider="gemini",
            model_name="gemini-2.5-pro",
            response_template="{response}",
            is_active=True,
        )
    )
    db.flush()
    ca = ContinuousAgent(
        id=continuous_agent_id,
        tenant_id=tenant_id,
        agent_id=agent_id,
        name=f"{tenant_id} continuous",
        execution_mode="hybrid",
        status="active",
    )
    db.add(ca)
    db.flush()
    return {
        "tenant_id": tenant_id,
        "agent_id": agent_id,
        "continuous_agent_id": continuous_agent_id,
    }


def seed_wake_event(
    db,
    *,
    tenant_id: str,
    continuous_agent_id: Optional[int] = None,
    channel_type: str = "jira",
    event_type: str = "issue.created",
    dedupe_key: Optional[str] = None,
    payload_ref: Optional[str] = None,
    importance: str = "normal",
    instance_id: int = 1,
):
    from models import WakeEvent

    we = WakeEvent(
        tenant_id=tenant_id,
        continuous_agent_id=continuous_agent_id,
        continuous_subscription_id=None,
        channel_type=channel_type,
        channel_instance_id=instance_id,
        event_type=event_type,
        occurred_at=datetime.utcnow(),
        dedupe_key=dedupe_key or f"{channel_type}-{datetime.utcnow().isoformat()}",
        importance=importance,
        payload_ref=payload_ref,
        status="pending",
    )
    db.add(we)
    db.flush()
    return we


def seed_continuous_run(
    db,
    *,
    tenant_id: str,
    continuous_agent_id: int,
    wake_event_id: int,
    status: str = "succeeded",
    outcome_state: Optional[Dict[str, Any]] = None,
):
    from models import ContinuousRun

    run = ContinuousRun(
        tenant_id=tenant_id,
        continuous_agent_id=continuous_agent_id,
        wake_event_ids=[wake_event_id],
        execution_mode="hybrid",
        status=status,
        run_type="continuous",
        outcome_state=outcome_state or {"answer": "Resolved by following standard runbook."},
        started_at=datetime.utcnow(),
        finished_at=datetime.utcnow(),
    )
    db.add(run)
    db.flush()
    return run


def seed_flow_run(
    db,
    *,
    tenant_id: str,
    flow_definition_id: int = 1,
    trigger_event_id: Optional[int] = None,
    status: str = "completed",
):
    from models import FlowDefinition, FlowRun

    if (
        db.query(FlowDefinition)
        .filter(FlowDefinition.id == flow_definition_id)
        .first()
        is None
    ):
        db.add(
            FlowDefinition(
                id=flow_definition_id,
                tenant_id=tenant_id,
                name=f"flow-{flow_definition_id}",
                description="test flow",
                version=1,
                is_active=True,
            )
        )
        db.flush()

    fr = FlowRun(
        flow_definition_id=flow_definition_id,
        tenant_id=tenant_id,
        status=status,
        initiator="trigger",
        trigger_type="triggered",
        trigger_event_id=trigger_event_id,
        final_report_json='{"summary": "done"}',
        started_at=datetime.utcnow(),
        completed_at=datetime.utcnow(),
    )
    db.add(fr)
    db.flush()
    return fr


class FakeEmbedder:
    """Replacement for ``EmbeddingService`` used by case_memory_service.

    Returns deterministic vectors of a configurable dimension so the
    tests can exercise the dim-validation path without spinning up
    sentence-transformers.
    """

    def __init__(self, dimension: int = 384):
        self.dimension = dimension
        self.calls: List[List[str]] = []

    def __call__(
        self,
        texts: List[str],
        contract: Optional[Any] = None,
        credentials: Optional[Dict[str, Any]] = None,
    ) -> List[List[float]]:
        # Accept (and ignore) the contract/credentials kwargs added in
        # v0.7.x Wave 1-B so the same fake works for both the old and
        # new ``_embed_texts`` signatures.
        self.calls.append(list(texts))
        # Deterministic non-zero vector per text (length-only matters).
        return [[0.001 * (i + 1)] * self.dimension for i in range(len(texts))]


class RecordingProvider:
    """In-memory stand-in for ``ProviderBridgeStore`` used during indexer tests.

    Records every ``add_message`` call so tests can assert vector kinds
    + metadata, and ``search_similar`` returns canned hits keyed on the
    most recent ``case_id`` write so recall tests can simulate matches
    without a real vector store.
    """

    def __init__(self):
        self.writes: List[Dict[str, Any]] = []
        self.search_results: List[Dict[str, Any]] = []

    @property
    def embedding_service(self):  # bridge contract
        return None

    async def add_message(
        self,
        message_id: str,
        sender_key: str,
        text: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.writes.append(
            {
                "message_id": message_id,
                "sender_key": sender_key,
                "text": text,
                "metadata": dict(metadata or {}),
            }
        )

    async def add_batch(self, records):  # noqa: ANN001
        for r in records:
            await self.add_message(
                message_id=r.get("message_id", ""),
                sender_key=r.get("sender_key", ""),
                text=r.get("text", ""),
                metadata=r.get("metadata"),
            )

    async def search_similar(
        self,
        query_text: str,
        limit: int = 5,
        sender_key: Optional[str] = None,
    ):
        return self.search_results[:limit]
