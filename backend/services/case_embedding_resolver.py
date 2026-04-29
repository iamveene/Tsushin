"""Case Memory — embedding-contract resolver.

Resolves the embedding contract (provider / model / dimensions / metric /
optional task) used to write a case's vectors. The contract is pinned on
the ``CaseMemory`` row and on every vector's metadata so a tenant that
later switches their default ``VectorStoreInstance`` to a different
model cannot retroactively invalidate older cases.

Default: ``local / all-MiniLM-L6-v2 / 384 / cosine`` (the existing local
SentenceTransformer path used by ``EmbeddingService``).

When the tenant has a default ``VectorStoreInstance`` with
``extra_config.embedding_dims`` set, the contract is read from
``extra_config`` (model / dims / metric / task), and
``vector_store_instance_id`` is stamped on the case row.

This module is intentionally tiny — heavier orchestration belongs in
``case_memory_service.py``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Optional

logger = logging.getLogger(__name__)


_DEFAULT_PROVIDER = "local"
_DEFAULT_MODEL = "all-MiniLM-L6-v2"
_DEFAULT_DIMS = 384
_DEFAULT_METRIC = "cosine"


class EmbeddingDimensionMismatch(Exception):
    """Raised when a generated embedding does not match the resolved contract.

    The case-index job catches this, marks the offending ``CaseMemory``
    row ``index_status='failed'``, and returns without retrying — the
    original trigger run is unaffected. See
    ``case_memory_service.index_case``.
    """

    def __init__(
        self,
        *,
        expected: int,
        actual: int,
        tenant_id: Optional[str] = None,
        agent_id: Optional[int] = None,
        vector_store_instance_id: Optional[int] = None,
        vector_kind: Optional[str] = None,
    ) -> None:
        self.expected = expected
        self.actual = actual
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.vector_store_instance_id = vector_store_instance_id
        self.vector_kind = vector_kind
        super().__init__(
            f"Embedding dimension mismatch: expected {expected}, got {actual} "
            f"(tenant={tenant_id}, agent={agent_id}, instance={vector_store_instance_id}, "
            f"vector_kind={vector_kind})"
        )


@dataclass(frozen=True)
class EmbeddingContract:
    """Snapshot of the embedding contract used to write a case's vectors."""

    provider: str
    model: str
    dimensions: int
    metric: str
    task: Optional[str] = None
    vector_store_instance_id: Optional[int] = None


def resolve_for_agent(
    db,
    *,
    tenant_id: str,
    agent_id: int,
) -> EmbeddingContract:
    """Resolve the embedding contract for a given (tenant, agent).

    Strategy:
      1. Look up the tenant's default ``VectorStoreInstance`` via
         ``vector_store_instance_service.get_default_instance``.
      2. If found, read ``extra_config`` for ``embedding_dims`` /
         ``embedding_model`` / ``metric`` / ``embedding_task``. Stamp the
         instance id on the contract.
      3. Else fall back to the local default
         (``local / all-MiniLM-L6-v2 / 384 / cosine``).

    The agent_id is currently unused (no per-agent override yet), but is
    accepted so a future iteration can inspect the agent's bound
    instance without API changes.
    """

    instance = None
    try:
        from services.vector_store_instance_service import VectorStoreInstanceService

        instance = VectorStoreInstanceService.get_default_instance(tenant_id, db)
    except Exception:  # noqa: BLE001 — defensive; never block the indexer here
        logger.exception(
            "case_embedding_resolver: failed to look up default VectorStoreInstance "
            "(tenant=%s, agent=%s); falling back to local default",
            tenant_id,
            agent_id,
        )
        instance = None

    if instance is None:
        return EmbeddingContract(
            provider=_DEFAULT_PROVIDER,
            model=_DEFAULT_MODEL,
            dimensions=_DEFAULT_DIMS,
            metric=_DEFAULT_METRIC,
            task=None,
            vector_store_instance_id=None,
        )

    extra = getattr(instance, "extra_config", None) or {}
    if not isinstance(extra, dict):
        extra = {}

    # If the instance is the local ChromaDB default with no embedding_dims
    # set, we still treat it as the local 384 contract so the indexer
    # writes through the bridge cleanly.
    dims = extra.get("embedding_dims")
    if dims is None:
        return EmbeddingContract(
            provider=_DEFAULT_PROVIDER,
            model=extra.get("embedding_model", _DEFAULT_MODEL),
            dimensions=_DEFAULT_DIMS,
            metric=extra.get("metric", _DEFAULT_METRIC),
            task=extra.get("embedding_task"),
            vector_store_instance_id=getattr(instance, "id", None),
        )

    try:
        dims_int = int(dims)
    except (TypeError, ValueError):
        logger.warning(
            "case_embedding_resolver: extra_config.embedding_dims=%r is not an int "
            "for tenant=%s instance=%s; falling back to %d",
            dims,
            tenant_id,
            getattr(instance, "id", None),
            _DEFAULT_DIMS,
        )
        dims_int = _DEFAULT_DIMS

    return EmbeddingContract(
        provider=str(getattr(instance, "vendor", None) or _DEFAULT_PROVIDER),
        model=str(extra.get("embedding_model") or _DEFAULT_MODEL),
        dimensions=dims_int,
        metric=str(extra.get("metric") or _DEFAULT_METRIC),
        task=extra.get("embedding_task"),
        vector_store_instance_id=getattr(instance, "id", None),
    )


def validate_vector(
    contract: EmbeddingContract,
    vector: Iterable[float],
    *,
    tenant_id: Optional[str] = None,
    agent_id: Optional[int] = None,
    vector_kind: Optional[str] = None,
) -> None:
    """Raise ``EmbeddingDimensionMismatch`` if ``len(vector) != dimensions``.

    The contract is the source of truth. We check explicit length to
    catch silent provider misconfiguration (e.g. a tenant flipped
    ``extra_config.embedding_dims`` from 384 → 768 after data already
    existed in a 384-dim collection).
    """

    actual = len(list(vector)) if not hasattr(vector, "__len__") else len(vector)  # type: ignore[arg-type]
    if actual != contract.dimensions:
        raise EmbeddingDimensionMismatch(
            expected=contract.dimensions,
            actual=actual,
            tenant_id=tenant_id,
            agent_id=agent_id,
            vector_store_instance_id=contract.vector_store_instance_id,
            vector_kind=vector_kind,
        )


def reject_post_data_dims_mutation(
    db,
    *,
    tenant_id: str,
    instance_id: int,
    new_dims: int,
) -> None:
    """Defensive guard: reject mutating ``embedding_dims`` after cases exist.

    The vector_store_instance_service.update_instance method does not
    currently enforce immutability of ``extra_config.embedding_dims``
    after vectors have been written — that's a separate, out-of-scope
    hardening pass. This helper lets case-memory tests assert we *would*
    refuse the change at the case-memory layer, and lets a future
    op-tooling surface call it before mutating the instance.

    Raises:
        RuntimeError: when ``CaseMemory`` rows exist for this instance with
        a different ``embedding_dims``.
    """
    from models import CaseMemory

    existing = (
        db.query(CaseMemory)
        .filter(
            CaseMemory.tenant_id == tenant_id,
            CaseMemory.vector_store_instance_id == instance_id,
        )
        .first()
    )
    if existing is None:
        return
    if existing.embedding_dims is None or existing.embedding_dims == new_dims:
        return
    raise RuntimeError(
        "Refusing to change VectorStoreInstance embedding_dims from "
        f"{existing.embedding_dims} → {new_dims} for tenant={tenant_id} "
        f"instance={instance_id} — CaseMemory rows already exist with the "
        "old contract. Create a new instance and reindex instead."
    )
