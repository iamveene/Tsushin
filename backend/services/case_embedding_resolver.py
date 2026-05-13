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
    vector_store_index_id: Optional[int] = None
    embedding_provider_instance_id: Optional[int] = None


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
            vector_store_index_id=None,
            embedding_provider_instance_id=None,
        )

    extra = getattr(instance, "extra_config", None) or {}
    if not isinstance(extra, dict):
        extra = {}

    task_document = str(extra.get("embedding_task_document") or "RETRIEVAL_DOCUMENT")
    task_query = str(extra.get("embedding_task_query") or "RETRIEVAL_QUERY")
    legacy_task = extra.get("embedding_task")

    from agent.memory.embedding_catalog import (
        LOCAL_DIMS,
        LOCAL_MODEL,
        normalize_embedding_provider,
        provider_default_model,
        validate_embedding_contract,
    )

    provider_declared = extra.get("embedding_provider") is not None
    provider = normalize_embedding_provider(extra.get("embedding_provider") or _DEFAULT_PROVIDER)
    default_model = provider_default_model(provider) or LOCAL_MODEL

    # If the instance is the local ChromaDB default with no embedding_dims
    # set, we still treat it as the local 384 contract so the indexer
    # writes through the bridge cleanly. Non-local providers should have
    # dimensions pinned by the provider/vector-store test flow before data
    # is written.
    dims = extra.get("embedding_dims")
    if dims is None:
        if provider_declared and provider != _DEFAULT_PROVIDER:
            try:
                normalized = validate_embedding_contract(
                    provider=provider,
                    model=extra.get("embedding_model") or default_model,
                    dimensions=None,
                    allow_ollama_dynamic=False,
                )
                dims_value = int(normalized["dimensions"])
                model_value = str(normalized["model"])
            except Exception:
                logger.warning(
                    "case_embedding_resolver: non-local embedding provider %s has no "
                    "pinned dimensions for tenant=%s instance=%s; falling back to local",
                    provider,
                    tenant_id,
                    getattr(instance, "id", None),
                )
                provider = _DEFAULT_PROVIDER
                dims_value = _DEFAULT_DIMS
                model_value = _DEFAULT_MODEL
        else:
            dims_value = LOCAL_DIMS
            model_value = extra.get("embedding_model", LOCAL_MODEL)
        return EmbeddingContract(
            provider=provider,
            model=model_value,
            dimensions=dims_value,
            metric=extra.get("metric", _DEFAULT_METRIC),
            task=legacy_task,
            task_document=task_document,
            task_query=task_query,
            vector_store_instance_id=getattr(instance, "id", None),
            vector_store_index_id=_resolve_case_index_id(
                db,
                tenant_id=tenant_id,
                agent_id=agent_id,
                instance=instance,
                provider=provider,
                model=model_value,
                dimensions=dims_value,
                metric=extra.get("metric", _DEFAULT_METRIC),
                task_document=task_document,
                task_query=task_query,
                provider_instance_id=extra.get("embedding_provider_instance_id"),
            ),
            embedding_provider_instance_id=extra.get("embedding_provider_instance_id"),
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

    if provider_declared or provider != _DEFAULT_PROVIDER:
        normalized = validate_embedding_contract(
            provider=provider,
            model=str(extra.get("embedding_model") or default_model),
            dimensions=dims_int,
            allow_ollama_dynamic=False,
        )
    else:
        # Preserve legacy rows/tests that pinned only ``embedding_dims`` before
        # the provider-aware contract existed. New create/update paths still
        # validate local as fixed 384.
        normalized = {
            "provider": provider,
            "model": str(extra.get("embedding_model") or default_model),
            "dimensions": dims_int,
            "metric": _DEFAULT_METRIC,
        }

    # v0.7.x Wave 1-B fix: read provider from extra_config.embedding_provider
    # rather than instance.vendor — the latter is the *vector store* vendor
    # (qdrant / mongodb / pinecone), not the *embedding* provider.
    return EmbeddingContract(
        provider=str(normalized["provider"]),
        model=str(normalized["model"]),
        dimensions=int(normalized["dimensions"]),
        metric=str(extra.get("metric") or normalized.get("metric") or _DEFAULT_METRIC),
        task=legacy_task,
        task_document=task_document,
        task_query=task_query,
        vector_store_instance_id=getattr(instance, "id", None),
        vector_store_index_id=_resolve_case_index_id(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            instance=instance,
            provider=str(normalized["provider"]),
            model=str(normalized["model"]),
            dimensions=int(normalized["dimensions"]),
            metric=str(extra.get("metric") or normalized.get("metric") or _DEFAULT_METRIC),
            task_document=task_document,
            task_query=task_query,
            provider_instance_id=extra.get("embedding_provider_instance_id"),
        ),
        embedding_provider_instance_id=extra.get("embedding_provider_instance_id"),
    )


def _resolve_case_index_id(
    db,
    *,
    tenant_id: str,
    agent_id: int,
    instance,
    provider: str,
    model: str,
    dimensions: int,
    metric: str,
    task_document: str,
    task_query: str,
    provider_instance_id: Optional[int],
) -> Optional[int]:
    if instance is None or getattr(instance, "id", None) is None:
        return None
    try:
        from services.vector_store_index_resolver import VectorStoreIndexResolver

        index = VectorStoreIndexResolver.resolve_or_create(
            db,
            tenant_id=tenant_id,
            vector_store_instance_id=getattr(instance, "id", None),
            purpose="case_memory",
            owner_type="agent",
            owner_id=agent_id,
            contract={
                "embedding_provider_instance_id": provider_instance_id,
                "embedding_provider": provider,
                "embedding_model": model,
                "embedding_dims": dimensions,
                "embedding_metric": metric,
                "embedding_task_document": task_document,
                "embedding_task_query": task_query,
            },
        )
        return index.id
    except Exception:
        logger.exception(
            "case_embedding_resolver: failed to resolve VectorStoreIndex "
            "(tenant=%s, agent=%s, instance=%s)",
            tenant_id,
            agent_id,
            getattr(instance, "id", None),
        )
        return None


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
      - ``embedding_provider`` (when set) is in ``{local, openai, gemini, ollama}``.
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

    from agent.memory.embedding_catalog import (
        normalize_embedding_provider,
        provider_default_model,
        validate_embedding_contract,
    )

    provider_norm = normalize_embedding_provider(provider)
    model = extra.get("embedding_model") or provider_default_model(provider_norm)

    if provider_norm == "ollama" and dims is None:
        raise ValueError(
            "Ollama embedding_dims must be detected by /api/embedding-providers/test "
            "and pinned before saving"
        )

    validate_embedding_contract(
        provider=provider_norm,
        model=model,
        dimensions=dims,
        allow_ollama_dynamic=False,
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
