"""Case Memory service — write + retrieval orchestration.

Phase 3 of the v0.7.0 Trigger Case Memory MVP. Default-off behind
``TSN_CASE_MEMORY_ENABLED`` (see ``config/feature_flags.py``).

Responsibilities:
  - ``index_case`` — idempotent terminal-run indexer:
      * load WakeEvent + Agent + (ContinuousRun | FlowRun) tenant-scoped;
      * read the redacted ``payload_ref`` written by
        ``TriggerDispatchService._write_payload_ref``;
      * build problem/action/outcome text (best-effort, with fallback to
        problem-only when summarization is unavailable);
      * resolve the embedding contract; embed each text with the shared
        ``EmbeddingService``; validate dims;
      * write up to 3 vectors via the existing ``ProviderBridgeStore``
        with deterministic IDs ``case_{origin}_{run_id}_{kind}`` and
        rich metadata;
      * insert/update the ``CaseMemory`` row with status + summary state.
  - ``search_similar_cases`` — read-side helper: embed the query, hit the
    bridge, post-filter by tenant + scope (agent | trigger_kind | tenant)
    and ``vector_kind``, hydrate from ``CaseMemory``, update
    ``last_recalled_at`` on hits.

Failure semantics:
  - Embedding-dimension mismatch → mark case ``index_status='failed'``
    (or insert a failed row), raise to the queue worker which marks the
    queue item failed *with no retry* (see ``queue_router._dispatch_case_index``).
  - Vector-store outage → mark ``partial`` (problem vector landed) or
    ``failed`` (problem vector did not land); never raise from
    ``index_case``.
  - Broken payload_ref / missing run / cross-tenant attempt → mark
    ``failed`` and return; original trigger run is untouched.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, List, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# --- Constants ---------------------------------------------------------------

OUTCOME_LABELS = ("resolved", "failed", "skipped", "escalated", "unknown")
INDEX_STATUSES = ("pending", "indexed", "partial", "failed", "skipped")
SUMMARY_STATUSES = ("generated", "fallback", "unavailable")
VECTOR_KINDS = ("problem", "action", "outcome")

# Mirror of TriggerDispatchService._SENSITIVE_KEY_PARTS (kept local to avoid
# importing a private helper from a peer service).
_SENSITIVE_KEY_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "signature",
    "token",
)

# Body preview budgets — kept tight so the problem vector embeds the trigger
# subject more than a long body, and so we don't accidentally feed PII
# fragments through the embedder when redaction misses a key.
_MAX_PROBLEM_BODY_CHARS = 2048
_MAX_ACTION_CHARS = 1024
_MAX_OUTCOME_CHARS = 1024


# --- Helpers -----------------------------------------------------------------


def _is_sensitive_key(key: str) -> bool:
    lowered = (key or "").lower()
    return any(part in lowered for part in _SENSITIVE_KEY_PARTS)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, child in value.items():
            if _is_sensitive_key(str(key)):
                out[str(key)] = "[REDACTED]"
            else:
                out[str(key)] = _redact(child)
        return out
    if isinstance(value, (list, tuple)):
        return [_redact(item) for item in value]
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def _read_payload_ref(payload_ref: Optional[str]) -> Optional[dict]:
    """Read the redacted payload JSON written by ``_write_payload_ref``.

    Mirrors the relative-path handling in ``queue_router._read_wake_payload``
    so this works on the host (``backend_root = .../tsushin/backend``)
    and in the container (``backend_root = /app``).
    """
    if not payload_ref:
        return None
    try:
        backend_root = Path(__file__).resolve().parents[1]
        candidate = Path(payload_ref)
        if not candidate.is_absolute():
            parts = candidate.parts
            if parts and parts[0] == "backend":
                candidate = backend_root.joinpath(*parts[1:])
            else:
                candidate = backend_root / candidate
        if not candidate.exists():
            return None
        document = json.loads(candidate.read_text(encoding="utf-8"))
        if isinstance(document, dict):
            return document
    except Exception:
        logger.exception("case_memory: failed to read payload_ref %s", payload_ref)
    return None


def _truncate(text: Optional[str], limit: int) -> str:
    if not text:
        return ""
    if len(text) <= limit:
        return text
    return text[:limit] + "…"


def _stringify_payload_body(payload_doc: dict) -> str:
    """Render the payload body as a redacted, length-bounded preview."""
    body = payload_doc.get("payload", payload_doc)
    body = _redact(body)
    try:
        rendered = json.dumps(body, indent=2, ensure_ascii=False, sort_keys=True, default=str)
    except (TypeError, ValueError):
        rendered = repr(body)
    return _truncate(rendered, _MAX_PROBLEM_BODY_CHARS)


def build_problem_text(wake_event: Any, payload_doc: Optional[dict]) -> str:
    """Build the ``problem`` vector text for a case.

    Concatenates the trigger subject/title (best-effort: payload subject /
    summary / event_type) with a length-bounded redacted body preview.
    Falls back to ``event_type:dedupe_key`` when the payload is missing
    so the case is still indexable (just with a thinner signal).
    """
    payload_doc = payload_doc or {}
    body = payload_doc.get("payload") if isinstance(payload_doc.get("payload"), dict) else payload_doc

    subject = ""
    if isinstance(body, dict):
        for key in ("subject", "title", "summary", "name"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                subject = value.strip()
                break

    event_type = (
        payload_doc.get("event_type")
        or getattr(wake_event, "event_type", None)
        or "trigger"
    )
    channel_type = (
        payload_doc.get("trigger_type")
        or getattr(wake_event, "channel_type", None)
        or "trigger"
    )

    header = f"[{channel_type}:{event_type}] {subject}".strip()
    body_preview = _stringify_payload_body(payload_doc) if payload_doc else ""

    if not header.strip("[]: ") and not body_preview:
        # Last-resort fallback so the embedding gets *something*.
        dedupe = getattr(wake_event, "dedupe_key", None) or ""
        return f"{event_type}:{dedupe}".strip(":")

    if body_preview:
        return f"{header}\n\n{body_preview}".strip()
    return header.strip()


def derive_outcome_label(
    *,
    origin_kind: str,
    run_status: Optional[str],
    run_outcome_state: Optional[dict] = None,
) -> str:
    """Map a run's terminal status onto a case ``outcome_label``."""
    status = (run_status or "").lower()
    if origin_kind == "continuous_run":
        if status == "succeeded":
            return "resolved"
        if status == "failed":
            return "failed"
        if status == "cancelled":
            return "skipped"
        if status in ("paused_budget", "skipped"):
            return "skipped"
        return "unknown"
    if origin_kind == "flow_run":
        if status == "completed":
            return "resolved"
        if status == "completed_with_errors":
            return "escalated"
        if status == "failed":
            return "failed"
        if status == "cancelled":
            return "skipped"
        return "unknown"
    return "unknown"


def build_action_text(run_obj: Any) -> str:
    """Best-effort short summary of what the run did.

    For ContinuousRun: read ``outcome_state.answer``.
    For FlowRun: parse ``final_report_json`` and stringify a top-level
    summary if present.
    Returns ``""`` on any failure — caller marks ``summary_status='fallback'``.
    """
    try:
        # ContinuousRun shape
        outcome_state = getattr(run_obj, "outcome_state", None)
        if isinstance(outcome_state, dict):
            answer = outcome_state.get("answer")
            if isinstance(answer, str) and answer.strip():
                return _truncate(answer.strip(), _MAX_ACTION_CHARS)

        # FlowRun shape
        final_report = getattr(run_obj, "final_report_json", None)
        if isinstance(final_report, str) and final_report.strip():
            try:
                doc = json.loads(final_report)
                if isinstance(doc, dict):
                    for key in ("summary", "answer", "result", "report"):
                        value = doc.get(key)
                        if isinstance(value, str) and value.strip():
                            return _truncate(value.strip(), _MAX_ACTION_CHARS)
                    return _truncate(json.dumps(doc, ensure_ascii=False, default=str), _MAX_ACTION_CHARS)
            except Exception:
                return _truncate(final_report.strip(), _MAX_ACTION_CHARS)
    except Exception:
        logger.exception("case_memory: build_action_text failed")
    return ""


def build_outcome_text(run_obj: Any, *, outcome_label: str) -> str:
    """Short narrative describing the disposition.

    Composes ``outcome_label`` with a truncated tail of the run's status
    text or error_text. Best-effort; returns ``""`` on failure.
    """
    parts: List[str] = [f"outcome={outcome_label}"]
    try:
        status = getattr(run_obj, "status", None)
        if isinstance(status, str) and status:
            parts.append(f"status={status}")

        # ContinuousRun.outcome_state.error
        outcome_state = getattr(run_obj, "outcome_state", None)
        if isinstance(outcome_state, dict):
            err = outcome_state.get("error")
            if isinstance(err, str) and err.strip():
                parts.append(f"error={_truncate(err.strip(), 256)}")

        # FlowRun.error_text
        error_text = getattr(run_obj, "error_text", None)
        if isinstance(error_text, str) and error_text.strip():
            parts.append(f"error={_truncate(error_text.strip(), 256)}")
    except Exception:
        logger.exception("case_memory: build_outcome_text failed")

    return _truncate(" | ".join(parts), _MAX_OUTCOME_CHARS)


# --- Indexer -----------------------------------------------------------------


@dataclass
class _RunBundle:
    run_obj: Any
    origin_kind: str
    occurred_at: Optional[datetime]
    trigger_kind: Optional[str]
    subject_digest: Optional[str]


def _load_run(
    db: Session,
    *,
    tenant_id: str,
    origin_kind: str,
    run_id: int,
) -> Optional[Any]:
    from models import ContinuousRun, FlowRun

    if origin_kind == "continuous_run":
        return (
            db.query(ContinuousRun)
            .filter(
                ContinuousRun.id == run_id,
                ContinuousRun.tenant_id == tenant_id,
            )
            .first()
        )
    if origin_kind == "flow_run":
        return (
            db.query(FlowRun)
            .filter(
                FlowRun.id == run_id,
                FlowRun.tenant_id == tenant_id,
            )
            .first()
        )
    return None


def _existing_case(
    db: Session, *, tenant_id: str, origin_kind: str, run_id: int
) -> Optional[Any]:
    from models import CaseMemory

    if origin_kind == "continuous_run":
        return (
            db.query(CaseMemory)
            .filter(
                CaseMemory.tenant_id == tenant_id,
                CaseMemory.continuous_run_id == run_id,
            )
            .first()
        )
    if origin_kind == "flow_run":
        return (
            db.query(CaseMemory)
            .filter(
                CaseMemory.tenant_id == tenant_id,
                CaseMemory.flow_run_id == run_id,
            )
            .first()
        )
    return None


def _run_status(run_obj: Any) -> Optional[str]:
    return getattr(run_obj, "status", None)


def _embed_texts(
    texts: List[str],
    contract: Optional[Any] = None,
    credentials: Optional[dict] = None,
) -> List[List[float]]:
    """Run the resolved embedder over a small batch.

    When ``contract`` is supplied with ``provider="gemini"``, dispatches
    to the Gemini provider with task hint ``RETRIEVAL_DOCUMENT``.
    Otherwise falls back to the shared local SentenceTransformer
    (MiniLM/384) — i.e. preserves the v0.7.0 MVP behaviour for any
    caller that doesn't pass a contract.
    """
    from agent.memory.embedding_service import get_shared_embedding_service

    embedder = get_shared_embedding_service(contract=contract, credentials=credentials)
    task = getattr(contract, "task_document", None) or "RETRIEVAL_DOCUMENT"
    return embedder.embed_batch_chunked(
        texts, batch_size=8, force_gc=False, task_type=task
    )


def _resolve_credentials_for_contract(
    db: Session, *, tenant_id: str, contract: Any
) -> Optional[dict]:
    """Decrypt the VectorStoreInstance credentials when the contract
    actually needs them (Gemini today; future remote providers tomorrow).

    Returns ``None`` for the local provider so the embedding service can
    skip the credential lookup entirely.
    """
    if contract is None:
        return None
    provider = (getattr(contract, "provider", None) or "").lower()
    if provider in ("local", ""):
        return None
    instance_id = getattr(contract, "vector_store_instance_id", None)
    if instance_id is None:
        return None

    try:
        from services.vector_store_instance_service import VectorStoreInstanceService

        instance = VectorStoreInstanceService.get_instance(instance_id, tenant_id, db)
        if instance is None:
            return None
        return VectorStoreInstanceService.resolve_credentials(instance, db)
    except Exception:  # noqa: BLE001 — never break indexing on credential lookup
        logger.exception(
            "case_memory: failed to resolve credentials for instance=%s tenant=%s",
            instance_id,
            tenant_id,
        )
        return None


async def _write_vectors_via_bridge(
    db: Session,
    *,
    tenant_id: str,
    agent: Any,
    case_id: int,
    wake_event_id: Optional[int],
    origin_kind: str,
    run_id: int,
    trigger_kind: Optional[str],
    contract,
    vectors: List[tuple[str, str, List[float]]],
) -> List[str]:
    """Write up to 3 case vectors via the resolved ``ProviderBridgeStore``.

    Returns the list of ``vector_kind`` values that were successfully
    written. Never raises — vector-store outages bubble back to the
    caller as a partial/failed status, not as an exception.
    """

    from agent.memory.embedding_service import get_shared_embedding_service
    from agent.memory.providers.bridge import ProviderBridgeStore
    from agent.memory.providers.resolver import VectorStoreResolver

    backend_root = Path(__file__).resolve().parents[1]
    persist_directory = str(backend_root / "data" / "memory" / f"agent_{getattr(agent, 'id', 0)}")

    embedder = get_shared_embedding_service()

    # Resolve the agent's vector store; falls back to ChromaDB local path.
    resolver = VectorStoreResolver()
    resolved = resolver.resolve(
        agent_id=agent.id,
        db=db,
        persist_directory=persist_directory,
        vector_store_instance_id=getattr(agent, "vector_store_instance_id", None),
        vector_store_mode=getattr(agent, "vector_store_mode", "override") or "override",
        tenant_id=tenant_id,
    )

    if resolved is None:
        # Local ChromaDB default — instantiate a CachedVectorStore-style
        # provider. For MVP we lean on the bridge with a local
        # ChromaDB backend via the registry's chromadb fallback.
        from agent.memory.providers.registry import VectorStoreRegistry

        registry = VectorStoreRegistry()
        try:
            provider = registry.get_chromadb_fallback(persist_directory)
        except Exception:
            logger.exception(
                "case_memory: failed to obtain ChromaDB fallback for tenant=%s agent=%s",
                tenant_id,
                agent.id,
            )
            return []
    else:
        provider = resolved

    bridge = ProviderBridgeStore(provider=provider, embedding_service=embedder)

    written: List[str] = []
    for vector_kind, text, embedding in vectors:
        message_id = f"case_{origin_kind}_{run_id}_{vector_kind}"
        sender_key = f"case:{origin_kind}:{run_id}"
        metadata = {
            "tenant_id": tenant_id,
            "agent_id": agent.id,
            "case_id": case_id,
            "wake_event_id": wake_event_id,
            "vector_store_instance_id": contract.vector_store_instance_id,
            "origin_kind": origin_kind,
            "trigger_kind": trigger_kind,
            "vector_kind": vector_kind,
            "embedding_provider": contract.provider,
            "embedding_model": contract.model,
            "embedding_dims": contract.dimensions,
            "embedding_metric": contract.metric,
        }
        try:
            # The bridge's add_message re-embeds via its own embedding_service;
            # we already validated dimensions, so let it pass the precomputed
            # embedding through where possible. The default bridge.add_message
            # does a re-embed though — for the MVP we accept that small
            # overhead so we can reuse the existing path. Tests inject a fake
            # provider that records what was passed.
            await bridge.add_message(
                message_id=message_id,
                sender_key=sender_key,
                text=text,
                metadata=metadata,
            )
            written.append(vector_kind)
        except Exception:
            logger.exception(
                "case_memory: vector-store write failed (case=%s vector=%s)",
                case_id,
                vector_kind,
            )
    return written


def index_case(
    db: Session,
    *,
    tenant_id: str,
    agent_id: int,
    origin_kind: str,
    run_id: int,
    wake_event_id: Optional[int],
    write_vectors_async: bool = True,
) -> Optional[Any]:
    """Idempotently produce a ``CaseMemory`` row for a terminal trigger run.

    See module docstring for failure semantics.

    Returns the ``CaseMemory`` row (existing or new). Returns ``None``
    when the wake event / agent / run cannot be loaded under the given
    tenant — in that case nothing is written.
    """
    from models import Agent, CaseMemory, WakeEvent
    from services.case_embedding_resolver import (
        EmbeddingDimensionMismatch,
        resolve_for_agent,
        validate_vector,
    )

    if origin_kind not in ("continuous_run", "flow_run"):
        logger.warning("case_memory: unsupported origin_kind=%s", origin_kind)
        return None

    # 1) Idempotency.
    existing = _existing_case(
        db, tenant_id=tenant_id, origin_kind=origin_kind, run_id=run_id
    )
    if existing is not None:
        logger.info(
            "case_memory: case already exists for %s id=%s — no-op",
            origin_kind,
            run_id,
        )
        return existing

    # 2) Load run + agent + wake_event tenant-scoped.
    run_obj = _load_run(db, tenant_id=tenant_id, origin_kind=origin_kind, run_id=run_id)
    if run_obj is None:
        logger.warning(
            "case_memory: %s id=%s not found under tenant=%s — skipping",
            origin_kind,
            run_id,
            tenant_id,
        )
        return None

    agent = (
        db.query(Agent)
        .filter(Agent.id == agent_id, Agent.tenant_id == tenant_id)
        .first()
    )
    if agent is None:
        logger.warning(
            "case_memory: agent id=%s not found under tenant=%s — skipping",
            agent_id,
            tenant_id,
        )
        return None

    wake_event = None
    if wake_event_id is not None:
        wake_event = (
            db.query(WakeEvent)
            .filter(
                WakeEvent.id == wake_event_id,
                WakeEvent.tenant_id == tenant_id,
            )
            .first()
        )

    trigger_kind = getattr(wake_event, "channel_type", None) if wake_event is not None else None
    occurred_at = (
        getattr(wake_event, "occurred_at", None)
        if wake_event is not None
        else getattr(run_obj, "started_at", None)
    )
    subject_digest = getattr(wake_event, "dedupe_key", None) if wake_event is not None else None

    # 3) Read redacted payload + build texts.
    payload_doc = (
        _read_payload_ref(getattr(wake_event, "payload_ref", None))
        if wake_event is not None
        else None
    )
    problem_text = build_problem_text(wake_event, payload_doc) if wake_event is not None else (
        f"{origin_kind}:{run_id}"
    )

    outcome_label = derive_outcome_label(
        origin_kind=origin_kind,
        run_status=_run_status(run_obj),
        run_outcome_state=getattr(run_obj, "outcome_state", None),
    )
    action_text = build_action_text(run_obj)
    outcome_text = build_outcome_text(run_obj, outcome_label=outcome_label)

    # 4) Resolve contract + (optionally) credentials.
    contract = resolve_for_agent(db, tenant_id=tenant_id, agent_id=agent_id)
    credentials = _resolve_credentials_for_contract(
        db, tenant_id=tenant_id, contract=contract
    )

    # Decide which vectors to attempt. Problem is mandatory; action /
    # outcome are best-effort and degrade to fallback when empty.
    vector_targets: List[tuple[str, str]] = [("problem", problem_text)]
    summary_status = "generated"
    if action_text:
        vector_targets.append(("action", action_text))
    else:
        summary_status = "fallback"
    if outcome_text:
        vector_targets.append(("outcome", outcome_text))
    elif summary_status != "fallback":
        summary_status = "fallback"

    # 5) Embed + dim-validate.
    texts_only = [t for _, t in vector_targets]
    try:
        embeddings = _embed_texts(texts_only, contract=contract, credentials=credentials)
    except Exception:
        logger.exception(
            "case_memory: embedding failed (tenant=%s agent=%s origin=%s run=%s)",
            tenant_id,
            agent_id,
            origin_kind,
            run_id,
        )
        embeddings = []

    if not embeddings or len(embeddings) != len(texts_only):
        # No embeddings → write a failed case row so the operator can see why.
        case = CaseMemory(
            tenant_id=tenant_id,
            agent_id=agent_id,
            wake_event_id=wake_event_id,
            continuous_run_id=run_id if origin_kind == "continuous_run" else None,
            flow_run_id=run_id if origin_kind == "flow_run" else None,
            origin_kind=origin_kind,
            trigger_kind=trigger_kind,
            subject_digest=subject_digest,
            problem_summary=problem_text,
            action_summary=action_text or None,
            outcome_summary=outcome_text or None,
            outcome_label=outcome_label,
            vector_store_instance_id=contract.vector_store_instance_id,
            embedding_provider=contract.provider,
            embedding_model=contract.model,
            embedding_dims=contract.dimensions,
            embedding_metric=contract.metric,
            embedding_task=contract.task,
            vector_refs_json=[],
            index_status="failed",
            summary_status="unavailable",
            occurred_at=occurred_at,
            indexed_at=datetime.utcnow(),
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        return case

    # Validate dims for every vector — this is the "embedding contract" check.
    try:
        for (kind, _text), emb in zip(vector_targets, embeddings):
            validate_vector(
                contract,
                emb,
                tenant_id=tenant_id,
                agent_id=agent_id,
                vector_kind=kind,
            )
    except EmbeddingDimensionMismatch as exc:
        logger.error(
            "case_memory: %s — original run is untouched (tenant=%s agent=%s origin=%s run=%s)",
            exc,
            tenant_id,
            agent_id,
            origin_kind,
            run_id,
        )
        case = CaseMemory(
            tenant_id=tenant_id,
            agent_id=agent_id,
            wake_event_id=wake_event_id,
            continuous_run_id=run_id if origin_kind == "continuous_run" else None,
            flow_run_id=run_id if origin_kind == "flow_run" else None,
            origin_kind=origin_kind,
            trigger_kind=trigger_kind,
            subject_digest=subject_digest,
            problem_summary=problem_text,
            action_summary=action_text or None,
            outcome_summary=outcome_text or None,
            outcome_label=outcome_label,
            vector_store_instance_id=contract.vector_store_instance_id,
            embedding_provider=contract.provider,
            embedding_model=contract.model,
            embedding_dims=contract.dimensions,
            embedding_metric=contract.metric,
            embedding_task=contract.task,
            vector_refs_json=[],
            index_status="failed",
            summary_status=summary_status,
            occurred_at=occurred_at,
            indexed_at=datetime.utcnow(),
        )
        db.add(case)
        db.commit()
        db.refresh(case)
        # Re-raise so the queue worker can mark the queue item failed
        # without retrying. The case row is already persisted.
        raise

    # 6) Insert pending CaseMemory row first to obtain an id.
    case = CaseMemory(
        tenant_id=tenant_id,
        agent_id=agent_id,
        wake_event_id=wake_event_id,
        continuous_run_id=run_id if origin_kind == "continuous_run" else None,
        flow_run_id=run_id if origin_kind == "flow_run" else None,
        origin_kind=origin_kind,
        trigger_kind=trigger_kind,
        subject_digest=subject_digest,
        problem_summary=problem_text,
        action_summary=action_text or None,
        outcome_summary=outcome_text or None,
        outcome_label=outcome_label,
        vector_store_instance_id=contract.vector_store_instance_id,
        embedding_provider=contract.provider,
        embedding_model=contract.model,
        embedding_dims=contract.dimensions,
        embedding_metric=contract.metric,
        embedding_task=contract.task,
        vector_refs_json=[],
        index_status="pending",
        summary_status=summary_status,
        occurred_at=occurred_at,
    )
    db.add(case)
    db.flush()  # populate case.id

    # 7) Write vectors via the bridge (best-effort).
    vectors_payload = [
        (kind, text, emb)
        for (kind, text), emb in zip(vector_targets, embeddings)
    ]

    written: List[str] = []
    if write_vectors_async:
        try:
            import asyncio

            written = asyncio.run(
                _write_vectors_via_bridge(
                    db,
                    tenant_id=tenant_id,
                    agent=agent,
                    case_id=case.id,
                    wake_event_id=wake_event_id,
                    origin_kind=origin_kind,
                    run_id=run_id,
                    trigger_kind=trigger_kind,
                    contract=contract,
                    vectors=vectors_payload,
                )
            )
        except RuntimeError as exc:
            # Already inside an event loop — schedule synchronously via a fresh
            # loop is unsafe; fall back to a thread-bound runner.
            if "asyncio.run() cannot be called" in str(exc) or "running event loop" in str(exc):
                import asyncio
                import concurrent.futures

                def _run() -> List[str]:
                    return asyncio.run(
                        _write_vectors_via_bridge(
                            db,
                            tenant_id=tenant_id,
                            agent=agent,
                            case_id=case.id,
                            wake_event_id=wake_event_id,
                            origin_kind=origin_kind,
                            run_id=run_id,
                            trigger_kind=trigger_kind,
                            contract=contract,
                            vectors=vectors_payload,
                        )
                    )

                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                    written = executor.submit(_run).result()
            else:
                logger.exception("case_memory: bridge write failed")
                written = []
        except Exception:
            logger.exception("case_memory: bridge write failed")
            written = []

    # 8) Finalize row state.
    vector_refs = [
        {
            "kind": kind,
            "vector_id": f"case_{origin_kind}_{run_id}_{kind}",
        }
        for kind in written
    ]
    case.vector_refs_json = vector_refs

    if "problem" in written and len(written) == len(vector_targets):
        case.index_status = "indexed"
    elif "problem" in written:
        case.index_status = "partial"
    else:
        case.index_status = "failed"

    case.indexed_at = datetime.utcnow()

    db.add(case)
    db.commit()
    db.refresh(case)
    return case


# --- Search ------------------------------------------------------------------


def _distance_to_similarity(distance: Optional[float], metric: str) -> float:
    """Map a vector-store distance to a similarity in ``[0, 1]``.

    Matches the convention used elsewhere in the codebase
    (``agent/memory/semantic_memory.py``): ``sim = 1 / (1 + distance)``,
    which is monotonic, bounded, and works for both bounded cosine
    distances and unbounded squared-L2 distances. The local ChromaDB
    fallback uses L2² by default, so a hard ``1 - d`` mapping would
    collapse near-matches to ``sim=0`` (and was the cause of the
    initial smoke regression).
    """
    if distance is None:
        return 0.0
    try:
        d = float(distance)
    except (TypeError, ValueError):
        return 0.0
    if d < 0:
        d = 0.0
    return 1.0 / (1.0 + d)


def search_similar_cases(
    db: Session,
    *,
    tenant_id: str,
    agent_id: Optional[int],
    query: str,
    scope: str = "agent",
    k: int = 3,
    # 0.35 default matches the empirical distance distribution of the local
    # MiniLM/L2 ChromaDB collection (un-normalized 384-dim vectors yield
    # distances ~1.0-2.0 for related text → sim ~0.33-0.5 via 1/(1+d)).
    # The earlier 0.65 default was cosine-scale and silently rejected every
    # real recall hit when the resolver fell back to the local store.
    min_similarity: float = 0.35,
    vector: str = "problem",
    trigger_kind: Optional[str] = None,
    include_failed: bool = True,
) -> List[dict]:
    """Embed ``query``, hit the vector store, hydrate from ``CaseMemory``.

    See module docstring for scope/filter semantics.

    .. note::
       ``scope="tenant"`` resolves the vector store against a single
       representative agent (the one passed via ``agent_id``, or the
       lowest-id agent in the tenant if ``agent_id`` is ``None``).
       If different agents in the tenant use different
       ``VectorStoreInstance`` rows, tenant-scope search may miss cases
       stored against a non-representative agent's instance. The
       ``/api/case-memory/search`` route requires ``agent_id`` whenever
       ``scope="tenant"`` is used so callers must pick a representative
       agent. Service callers should be aware of this caveat as well.
    """
    from models import Agent, CaseMemory
    from agent.memory.embedding_service import get_shared_embedding_service
    from agent.memory.providers.bridge import ProviderBridgeStore
    from agent.memory.providers.registry import VectorStoreRegistry
    from agent.memory.providers.resolver import VectorStoreResolver
    from services.case_embedding_resolver import resolve_for_agent

    if not query or not query.strip():
        return []

    if scope not in ("agent", "trigger_kind", "tenant"):
        scope = "agent"

    # Choose a representative agent for resolving the vector store. For
    # tenant-scope searches without an agent_id, just pick the first
    # active agent in the tenant — the bridge's collection is shared.
    agent = None
    if agent_id is not None:
        agent = (
            db.query(Agent)
            .filter(Agent.id == agent_id, Agent.tenant_id == tenant_id)
            .first()
        )
    if agent is None:
        agent = (
            db.query(Agent)
            .filter(Agent.tenant_id == tenant_id)
            .order_by(Agent.id.asc())
            .first()
        )
    if agent is None:
        return []

    backend_root = Path(__file__).resolve().parents[1]
    persist_directory = str(backend_root / "data" / "memory" / f"agent_{agent.id}")

    # Resolve the embedding contract for the search side, then pre-embed
    # the query with the right task hint (RETRIEVAL_QUERY for Gemini,
    # ignored for local). Without this step, Gemini-configured tenants
    # would silently fall back to local 384-dim embeddings here while
    # writing 1536-dim Gemini vectors — guaranteeing zero recall.
    contract = resolve_for_agent(db, tenant_id=tenant_id, agent_id=agent.id)
    credentials = _resolve_credentials_for_contract(
        db, tenant_id=tenant_id, contract=contract
    )
    try:
        embedder = get_shared_embedding_service(
            contract=contract, credentials=credentials
        )
    except Exception:
        logger.exception(
            "case_memory: failed to resolve contract-aware embedder for "
            "tenant=%s agent=%s — falling back to local default",
            tenant_id,
            agent.id,
        )
        embedder = get_shared_embedding_service()

    try:
        query_embedding = embedder.embed_text(
            query, task_type=contract.task_query
        )
    except TypeError:
        # Some legacy stand-ins (test fakes) don't accept task_type.
        query_embedding = embedder.embed_text(query)
    except Exception:
        logger.exception(
            "case_memory: query embedding failed (tenant=%s agent=%s)",
            tenant_id,
            agent.id,
        )
        return []

    if not query_embedding:
        return []

    resolver = VectorStoreResolver()
    resolved = resolver.resolve(
        agent_id=agent.id,
        db=db,
        persist_directory=persist_directory,
        vector_store_instance_id=getattr(agent, "vector_store_instance_id", None),
        vector_store_mode=getattr(agent, "vector_store_mode", "override") or "override",
        tenant_id=tenant_id,
    )

    if resolved is None:
        registry = VectorStoreRegistry()
        try:
            provider = registry.get_chromadb_fallback(persist_directory)
        except Exception:
            return []
    else:
        provider = resolved

    bridge = ProviderBridgeStore(provider=provider, embedding_service=embedder)

    over_fetch = max(k * 4, k + 4)
    # Decide BEFORE creating the coroutine whether we can use asyncio.run
    # directly or need a thread. Creating the coroutine first and letting
    # asyncio.run raise RuntimeError leaves a dangling coroutine that emits
    # "coroutine was never awaited" — which surfaced as the live-Playground
    # recall regression on 2026-04-29 (skill invoked, returned 0 cases).
    import asyncio
    try:
        asyncio.get_running_loop()
        loop_is_running = True
    except RuntimeError:
        loop_is_running = False

    def _make_coro():
        # Use the embedding-aware path so we don't double-embed the
        # query under the bridge's own embedding_service.
        return bridge.search_similar_by_embedding(
            query_embedding=query_embedding,
            limit=over_fetch,
            sender_key=None,
        )

    try:
        if loop_is_running:
            # Caller is inside an active event loop (e.g. FastAPI websocket
            # handler driving the agent runtime). asyncio.run requires a
            # fresh loop — run in a worker thread so we don't conflict.
            import concurrent.futures

            def _runner():
                return asyncio.run(_make_coro())

            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                results = executor.submit(_runner).result()
        else:
            # No running loop in this thread — asyncio.run is safe.
            results = asyncio.run(_make_coro())
    except Exception:
        logger.exception("case_memory: search failed")
        return []

    # Filter + hydrate.
    out: List[dict] = []
    seen_case_ids: set[int] = set()
    for record in results or []:
        meta = record.get("metadata") or {}
        if not isinstance(meta, dict):
            continue
        if meta.get("tenant_id") != tenant_id:
            continue
        if vector not in (None, "any"):
            if meta.get("vector_kind") != vector:
                continue
        if scope == "agent":
            if agent_id is not None and meta.get("agent_id") != agent_id:
                continue
        elif scope == "trigger_kind":
            if agent_id is not None and meta.get("agent_id") != agent_id:
                continue
            if trigger_kind and meta.get("trigger_kind") != trigger_kind:
                continue
        # scope == "tenant": no extra filter beyond tenant_id

        case_id = meta.get("case_id")
        if not isinstance(case_id, int) or case_id in seen_case_ids:
            continue
        seen_case_ids.add(case_id)

        case = (
            db.query(CaseMemory)
            .filter(CaseMemory.id == case_id, CaseMemory.tenant_id == tenant_id)
            .first()
        )
        if case is None:
            continue
        if not include_failed and case.index_status == "failed":
            continue

        similarity = _distance_to_similarity(
            record.get("distance"),
            meta.get("embedding_metric") or "cosine",
        )
        if similarity < min_similarity:
            continue

        out.append(
            {
                "case_id": case.id,
                "occurred_at_iso": case.occurred_at.isoformat() if case.occurred_at else None,
                "similarity": similarity,
                "problem_summary": case.problem_summary,
                "action_summary": case.action_summary,
                "outcome_summary": case.outcome_summary,
                "outcome_label": case.outcome_label,
                "origin_kind": case.origin_kind,
                "trigger_kind": case.trigger_kind,
                "wake_event_id": case.wake_event_id,
                "continuous_run_id": case.continuous_run_id,
                "flow_run_id": case.flow_run_id,
                "_case_obj": case,
            }
        )

    out.sort(key=lambda r: r["similarity"], reverse=True)
    out = out[:k]

    # Update last_recalled_at in one shot (avoid per-row commit churn).
    if out:
        try:
            now = datetime.utcnow()
            for hit in out:
                case = hit.pop("_case_obj", None)
                if case is not None:
                    case.last_recalled_at = now
            db.commit()
        except Exception:
            logger.exception("case_memory: failed to update last_recalled_at")
            db.rollback()
    else:
        for hit in out:
            hit.pop("_case_obj", None)

    return out
