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
``extra_config`` (provider / model / dims / metric / task hints), and
``vector_store_instance_id`` is stamped on the case row.

This module is intentionally tiny — heavier orchestration belongs in
``case_memory_service.py``.

v0.7.x Wave 1-B (this revision):
  - Fixed a load-bearing bug where ``provider`` was being read from
    ``instance.vendor`` (the *vector store* vendor — ``qdrant`` /
    ``mongodb`` / ``pinecone``) instead of from
    ``extra_config.embedding_provider`` (the *embedding* provider —
    ``local`` / ``gemini``). With the old code, every Gemini-configured
    instance silently fell back to ``provider="qdrant"`` and the
    Gemini client was never invoked.
  - Added ``task_document`` / ``task_query`` to ``EmbeddingContract`` so
    the Gemini provider can pass the right task hint per direction.
  - Added ``validate_extra_config_embedding`` for input validation and
    ``reject_post_data_contract_mutation`` (renamed from
    ``reject_post_data_dims_mutation``) for the immutability guard.
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

# Provider-specific dimensionality constraints.
_GEMINI_VALID_DIMS = {768, 1536, 3072}
_LOCAL_VALID_DIMS = {384}


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
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        self.expected = expected
        self.actual = actual
        self.tenant_id = tenant_id
        self.agent_id = agent_id
        self.vector_store_instance_id = vector_store_instance_id
        self.vector_kind = vector_kind
        self.provider = provider
        self.model = model
        super().__init__(
            f"Embedding dimension mismatch: expected {expected}, got {actual} "
            f"(tenant={tenant_id}, agent={agent_id}, instance={vector_store_instance_id}, "
            f"vector_kind={vector_kind}, provider={provider}, model={model})"
        )


@dataclass(frozen=True)
class EmbeddingContract:
    """Snapshot of the embedding contract used to write a case's vectors.

    ``task`` is kept for backward compatibility with rows already
    persisted under the v0.7.0 MVP. New code should prefer
    ``task_document`` (write-side hint) and ``task_query`` (query-side
    hint), which Gemini honours and local providers ignore.
    """

    provider: str
    model: str
    dimensions: int
    metric: str
    task: Optional[str] = None
    task_document: str = "RETRIEVAL_DOCUMENT"
    task_query: str = "RETRIEVAL_QUERY"
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
        from models import Agent, VectorStoreInstance

        # 1. Prefer the agent's per-agent binding (Agent.vector_store_instance_id).
        if agent_id is not None:
            agent_row = db.query(Agent).filter(
                Agent.id == agent_id,
                Agent.tenant_id == tenant_id,
            ).first()
            bound_id = getattr(agent_row, "vector_store_instance_id", None) if agent_row else None
            if bound_id:
                instance = db.query(VectorStoreInstance).filter(
                    VectorStoreInstance.id == bound_id,
                    VectorStoreInstance.tenant_id == tenant_id,
                ).first()

        # 2. Else fall back to the tenant's default instance.
        if instance is None:
            instance = VectorStoreInstanceService.get_default_instance(tenant_id, db)
    except Exception:  # noqa: BLE001 — defensive; never block the indexer here
        logger.exception(
            "case_embedding_resolver: failed to look up VectorStoreInstance "
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

    task_document = str(extra.get("embedding_task_document") or "RETRIEVAL_DOCUMENT")
    task_query = str(extra.get("embedding_task_query") or "RETRIEVAL_QUERY")
    legacy_task = extra.get("embedding_task")

    # If the instance is the local ChromaDB default with no embedding_dims
    # set, we still treat it as the local 384 contract so the indexer
    # writes through the bridge cleanly.
    dims = extra.get("embedding_dims")
    if dims is None:
        return EmbeddingContract(
            provider=str(extra.get("embedding_provider") or _DEFAULT_PROVIDER),
            model=extra.get("embedding_model", _DEFAULT_MODEL),
            dimensions=_DEFAULT_DIMS,
            metric=extra.get("metric", _DEFAULT_METRIC),
            task=legacy_task,
            task_document=task_document,
            task_query=task_query,
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

    # v0.7.x Wave 1-B fix: read provider from extra_config.embedding_provider
    # rather than instance.vendor — the latter is the *vector store* vendor
    # (qdrant / mongodb / pinecone), not the *embedding* provider.
    return EmbeddingContract(
        provider=str(extra.get("embedding_provider") or _DEFAULT_PROVIDER),
        model=str(extra.get("embedding_model") or _DEFAULT_MODEL),
        dimensions=dims_int,
        metric=str(extra.get("metric") or _DEFAULT_METRIC),
        task=legacy_task,
        task_document=task_document,
        task_query=task_query,
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
            provider=contract.provider,
            model=contract.model,
        )


def validate_extra_config_embedding(extra: Optional[dict]) -> None:
    """Validate that ``extra_config`` declares a coherent embedding contract.

    Called by ``vector_store_instance_service.update_instance`` (and the
    create path, by extension via the wizard) so an operator can't save
    ``provider=gemini, dims=384`` or ``provider=local, dims=1536``.

    Validates:
      - ``embedding_provider`` (when set) is in ``{local, gemini}``.
      - ``embedding_dims`` (when set) is an int.
      - The (provider, dims) pair is one of the allowed combinations.

    Raises ``ValueError`` with a clear message on every failure mode so
    the API route can convert it to a 400.
    """
    if not isinstance(extra, dict):
        return

    provider = extra.get("embedding_provider")
    dims = extra.get("embedding_dims")

    if provider is None and dims is None:
        return

    if provider is not None:
        provider_norm = str(provider).lower()
        if provider_norm not in ("local", "gemini"):
            raise ValueError(
                f"Invalid embedding_provider {provider!r}: must be 'local' or 'gemini'"
            )
    else:
        provider_norm = "local"

    if dims is None:
        return

    try:
        dims_int = int(dims)
    except (TypeError, ValueError):
        raise ValueError(
            f"Invalid embedding_dims {dims!r}: must be an integer"
        )

    if provider_norm == "gemini":
        if dims_int not in _GEMINI_VALID_DIMS:
            raise ValueError(
                "Invalid embedding_dims for Gemini: must be one of "
                f"{sorted(_GEMINI_VALID_DIMS)}, got {dims_int}"
            )
    elif provider_norm == "local":
        if dims_int not in _LOCAL_VALID_DIMS:
            raise ValueError(
                "Invalid embedding_dims for local SentenceTransformer: must be "
                f"{sorted(_LOCAL_VALID_DIMS)[0]}, got {dims_int}"
            )


def reject_post_data_contract_mutation(
    db,
    *,
    tenant_id: str,
    instance_id: int,
    new_extra_config: Optional[dict] = None,
    new_dims: Optional[int] = None,
) -> None:
    """Defensive guard: reject mutating the embedding contract after cases exist.

    Once at least one ``CaseMemory`` row has been written against an
    instance, the embedding contract (provider / model / dims) is
    immutable for that instance. Changing any of them would mean
    queries computed under the new contract would search a vector
    space populated under a different one — silently broken recall.

    Two calling conventions are supported:
      - **Preferred (v0.7.x):** pass ``new_extra_config={...}`` —
        provider, model, and dims are all compared.
      - **Legacy (v0.7.0):** pass ``new_dims=int`` — only dims is
        compared. Kept for the small number of test/dev callers from
        the MVP that haven't migrated yet.

    Raises ``ValueError`` (4xx-friendly) when the change would
    invalidate existing data. Raising ``ValueError`` rather than
    ``RuntimeError`` lets the FastAPI route handler convert this to a
    400 via its existing ``except ValueError`` clause.
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

    # Legacy single-dim path. Preserves the original "Refusing to change"
    # phrasing for back-compat with v0.7.0 tests/scripts that match on it.
    if new_extra_config is None and new_dims is not None:
        if existing.embedding_dims is None or existing.embedding_dims == new_dims:
            return
        raise ValueError(
            "Refusing to change VectorStoreInstance embedding_dims from "
            f"{existing.embedding_dims} → {new_dims} for tenant={tenant_id} "
            f"instance={instance_id} — CaseMemory rows already exist with the "
            "old contract. Create a new instance and reindex instead."
        )

    if not isinstance(new_extra_config, dict):
        return

    new_provider = new_extra_config.get("embedding_provider")
    new_model = new_extra_config.get("embedding_model")
    new_dims_val = new_extra_config.get("embedding_dims")

    mismatches = []
    if new_provider is not None and existing.embedding_provider is not None and (
        str(existing.embedding_provider) != str(new_provider)
    ):
        mismatches.append(
            f"embedding_provider {existing.embedding_provider!r} → {new_provider!r}"
        )
    if new_model is not None and existing.embedding_model is not None and (
        str(existing.embedding_model) != str(new_model)
    ):
        mismatches.append(
            f"embedding_model {existing.embedding_model!r} → {new_model!r}"
        )
    if new_dims_val is not None and existing.embedding_dims is not None:
        try:
            new_dims_int = int(new_dims_val)
        except (TypeError, ValueError):
            new_dims_int = None
        if new_dims_int is not None and existing.embedding_dims != new_dims_int:
            mismatches.append(
                f"embedding_dims {existing.embedding_dims} → {new_dims_int}"
            )

    if not mismatches:
        return

    raise ValueError(
        "Refusing to mutate VectorStoreInstance embedding contract for "
        f"tenant={tenant_id} instance={instance_id} — existing cases prevent: "
        + "; ".join(mismatches)
        + ". Create a new instance and reindex instead."
    )


# DEPRECATED: kept as a thin alias so legacy callers keep working. New
# code should call ``reject_post_data_contract_mutation`` directly.
def reject_post_data_dims_mutation(
    db,
    *,
    tenant_id: str,
    instance_id: int,
    new_dims: int,
) -> None:
    """Deprecated alias for ``reject_post_data_contract_mutation``.

    Preserved so a v0.7.0 dev_tests caller continues to work. Internal
    behaviour now raises ``ValueError`` (was ``RuntimeError``) for
    consistency with the new function. Tests that asserted
    ``pytest.raises(RuntimeError)`` against this name should be migrated
    to the new function name.
    """
    try:
        reject_post_data_contract_mutation(
            db,
            tenant_id=tenant_id,
            instance_id=instance_id,
            new_dims=new_dims,
        )
    except ValueError as exc:
        # Preserve the original RuntimeError contract for legacy callers.
        raise RuntimeError(str(exc)) from exc
