"""Per-trigger Memory Recap builder.

v0.7.x — per-tenant gate via ``Tenant.case_memory_recap_enabled``
(DB-backed, settable from the tenant settings UI). Defaults to TRUE on
every tenant; flipping it False globally disables recap injection for
that tenant without touching individual ``TriggerRecapConfig`` rows.
The case-memory indexer (write side) is unaffected.

Public API:
  ``build_memory_recap(db, *, tenant_id, agent_id, trigger_kind,
                       trigger_instance_id, payload_doc) -> Optional[dict]``

For a given trigger fire, the dispatcher looks up the
``TriggerRecapConfig`` row keyed on ``(tenant_id, trigger_kind,
trigger_instance_id)``. If recap is globally enabled, the row exists,
and ``config.enabled`` is True, the service:

  1. Expands ``query_template`` (Jinja2 ``SandboxedEnvironment``)
     against ``payload_doc`` — which is already redacted by
     ``TriggerDispatchService._write_payload_ref``. Missing variables
     resolve to empty strings (``Undefined``, NOT ``StrictUndefined``)
     so a partial template still renders something useful.

  2. Calls ``case_memory_service.search_similar_cases`` with the
     configured ``scope`` / ``k`` / ``min_similarity`` /
     ``vector_kind`` / ``trigger_kind`` / ``include_failed``.

  3. Renders ``format_template`` (also sandboxed) with the result list
     and a small set of helper variables (``cases``, ``count``,
     ``query``, ``trigger_kind``). When zero cases matched, the
     template still renders the empty-state block so the agent's first
     turn explicitly *sees* "no past cases" instead of silently being
     left without context (which invites hallucination).

  4. Truncates to ``max_recap_chars`` and returns:

         {
             "rendered_text": <str>,
             "cases_used": <int>,
             "config_snapshot": {
                 "scope": ..., "k": ..., "min_similarity": ...,
                 "vector_kind": ..., "inject_position": ...,
                 "query_template_hash": <sha256[:24]>,
             },
         }

Failure semantics:
  - Every error path swallows + logs at WARNING and returns ``None``.
  - The search call runs on a 1-thread ``ThreadPoolExecutor`` with a
    2.0s ``result(timeout=...)`` — so a slow embedder or vector store
    cannot stall trigger dispatch.
  - Broken Jinja2 templates → ``None`` (no exception bubbles).
  - Disabled config / missing config / global flag off → ``None``.

The original trigger run is NEVER aborted by recap construction — the
caller wraps this in its own try/except and treats ``None`` as
"no recap, dispatch normally".
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import logging
from typing import Any, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Default Jinja2 format template — used when ``format_template`` is empty
# on the config row. Kept identical to the migration default so a row
# inserted via ``server_default`` and a row inserted via the API both
# render the same way.
_DEFAULT_FORMAT_TEMPLATE = (
    "## Past Cases ({{ count }} match{% if count != 1 %}es{% endif %})\n"
    "{% for c in cases %}\n"
    "- **[{{ c.outcome_label or 'unknown' }}]** sim={{ '%.3f'|format(c.similarity) }} | "
    "{{ (c.problem_summary or '')[:300] }}\n"
    "  Action: {{ (c.action_summary or '')[:300] }}\n"
    "{% endfor %}"
)

_EMPTY_STATE_TEMPLATE = (
    "## Past Cases (0 matches)\n"
    "No past cases found above similarity threshold "
    "({{ '%.2f'|format(min_similarity) }})."
)

# 10s wall clock — covers embedder cold-start (model load ~3-5s on first call)
# plus the actual search. After the embedder is hot the real cost is <200ms;
# the budget exists to bound dispatch latency on a bad day, not for happy path.
_SEARCH_TIMEOUT_S = 10.0


def _render_template(template_text: str, context: dict) -> str:
    """Render a Jinja2 template in a sandboxed environment.

    Raises ``jinja2.TemplateError`` (or subclass) on syntax/runtime
    error so the caller can swallow + log.
    """
    from jinja2 import Undefined
    from jinja2.sandbox import SandboxedEnvironment

    env = SandboxedEnvironment(
        autoescape=False,
        undefined=Undefined,  # missing keys → empty string, NOT raise.
        trim_blocks=False,
        lstrip_blocks=False,
    )
    return env.from_string(template_text).render(**context)


def _hash_query_template(template_text: str) -> str:
    return hashlib.sha256(
        (template_text or "").encode("utf-8", errors="replace")
    ).hexdigest()[:24]


def _build_query(query_template: str, payload_doc: dict) -> str:
    """Expand the operator-supplied query template against the payload.

    Returns the trimmed string — caller decides what to do when empty.
    """
    if not query_template:
        return ""
    # The payload doc shape is what _write_payload_ref produced:
    #   {trigger_type, instance_id, event_type, dedupe_key, ...,
    #    payload: { ... }}
    # We expose the full doc AND flatten ``payload`` to top-level keys so
    # operators can write ``{{summary}}`` instead of ``{{payload.summary}}``
    # for the simple case (Jira/Email payloads have ``summary`` /
    # ``subject`` at the top of ``payload``).
    inner = payload_doc.get("payload") if isinstance(payload_doc, dict) else None
    context: dict[str, Any] = {}
    if isinstance(inner, dict):
        for key, value in inner.items():
            context[str(key)] = value
    if isinstance(payload_doc, dict):
        context.update(
            {
                "payload": inner,
                "doc": payload_doc,
                "trigger_type": payload_doc.get("trigger_type"),
                "instance_id": payload_doc.get("instance_id"),
                "event_type": payload_doc.get("event_type"),
                "dedupe_key": payload_doc.get("dedupe_key"),
            }
        )
    rendered = _render_template(query_template, context)
    return (rendered or "").strip()


def _backend_supports_cross_thread_session(db: Session) -> bool:
    """Return True when the session's engine can be safely used across threads.

    Postgres connections are thread-safe so the recap timeout wrapper can
    move ``search_similar_cases`` onto a worker thread. SQLite — used by
    in-memory test fixtures — is single-threaded by default, which would
    raise ``ProgrammingError: SQLite objects created in a thread can only
    be used in that same thread`` if the session were touched off-thread.

    On SQLite we therefore skip the threadpool wrapper and run inline.
    The wall-clock budget is still enforced in production (Postgres) and
    the loss of timeout protection in tests is acceptable because the
    in-memory test embedder is synchronous and instant.
    """
    try:
        bind = db.get_bind()
        backend = bind.dialect.name
        return backend != "sqlite"
    except Exception:  # noqa: BLE001
        # If we can't introspect the bind, default to inline (safer).
        return False


def _run_search_with_timeout(
    db: Session,
    *,
    tenant_id: str,
    agent_id: int,
    query: str,
    scope: str,
    k: int,
    min_similarity: float,
    vector: str,
    trigger_kind: str,
    include_failed: bool,
    timeout_s: float = _SEARCH_TIMEOUT_S,
) -> list[dict]:
    """Run ``search_similar_cases`` with a hard wall-clock timeout.

    Returns ``[]`` on timeout or any exception. Never raises.

    The threadpool wrapper is skipped on SQLite (in-memory test fixtures
    are single-threaded) — see ``_backend_supports_cross_thread_session``.
    """
    from services.case_memory_service import search_similar_cases

    def _do_search() -> list[dict]:
        return search_similar_cases(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            query=query,
            scope=scope,
            k=k,
            min_similarity=min_similarity,
            vector=vector,
            trigger_kind=trigger_kind,
            include_failed=include_failed,
        )

    if not _backend_supports_cross_thread_session(db):
        try:
            return _do_search() or []
        except Exception:  # noqa: BLE001 — never raise from recap
            logger.warning(
                "trigger_recap: search_similar_cases failed inline "
                "(tenant=%s agent=%s trigger_kind=%s); recap will be empty",
                tenant_id,
                agent_id,
                trigger_kind,
                exc_info=True,
            )
            return []

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_do_search)
            return future.result(timeout=timeout_s) or []
    except concurrent.futures.TimeoutError:
        logger.warning(
            "trigger_recap: search_similar_cases timed out after %.1fs "
            "(tenant=%s agent=%s trigger_kind=%s)",
            timeout_s,
            tenant_id,
            agent_id,
            trigger_kind,
        )
        return []
    except Exception:  # noqa: BLE001 — last-resort guard
        logger.warning(
            "trigger_recap: search_similar_cases failed (tenant=%s agent=%s "
            "trigger_kind=%s); recap will be empty",
            tenant_id,
            agent_id,
            trigger_kind,
            exc_info=True,
        )
        return []


def build_memory_recap(
    db: Session,
    *,
    tenant_id: str,
    agent_id: int,
    trigger_kind: str,
    trigger_instance_id: int,
    payload_doc: dict,
) -> Optional[dict]:
    """Build the per-trigger memory recap. Returns ``None`` on any failure.

    See module docstring for the contract. Callers MUST treat ``None``
    as "no recap, dispatch normally" — recap is a best-effort
    enrichment and never blocks the trigger run.
    """
    # 1) Per-tenant gate. ``tenant.case_memory_recap_enabled`` is a SaaS
    # setting (DB column, default TRUE) toggled via the tenant settings
    # UI. When False, recap injection is skipped for this tenant regardless
    # of per-trigger config. The indexer (write-side) is unaffected.
    try:
        from config.feature_flags import case_memory_recap_enabled

        if not case_memory_recap_enabled(tenant_id=tenant_id, db=db):
            return None
    except Exception:  # noqa: BLE001 — gate-eval failures must not break dispatch
        logger.warning(
            "trigger_recap: case_memory_recap_enabled() lookup failed; "
            "treating as off to be safe",
            exc_info=True,
        )
        return None

    # 2) Load config row.
    try:
        from models import TriggerRecapConfig

        config = (
            db.query(TriggerRecapConfig)
            .filter(
                TriggerRecapConfig.tenant_id == tenant_id,
                TriggerRecapConfig.trigger_kind == trigger_kind,
                TriggerRecapConfig.trigger_instance_id == trigger_instance_id,
            )
            .first()
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "trigger_recap: failed to load TriggerRecapConfig "
            "(tenant=%s kind=%s instance=%s)",
            tenant_id,
            trigger_kind,
            trigger_instance_id,
            exc_info=True,
        )
        return None

    if config is None:
        return None
    if not bool(getattr(config, "enabled", False)):
        return None

    # Snapshot config primitives BEFORE any work — we want to embed the
    # values that drove the run into the returned dict, not whatever the
    # row's mutable state ends up at later.
    scope = (config.scope or "trigger_instance").strip()
    k = max(1, int(config.k or 3))
    min_similarity = float(config.min_similarity if config.min_similarity is not None else 0.35)
    vector_kind = (config.vector_kind or "problem").strip()
    include_failed = bool(config.include_failed)
    inject_position = (config.inject_position or "prepend_user_msg").strip()
    max_recap_chars = max(1, int(config.max_recap_chars or 1500))
    query_template = config.query_template or ""
    format_template = config.format_template or _DEFAULT_FORMAT_TEMPLATE

    # 3) Render the query template.
    try:
        query = _build_query(query_template, payload_doc or {})
    except Exception:  # noqa: BLE001 — covers jinja2.TemplateError + anything weird
        logger.warning(
            "trigger_recap: query_template render failed "
            "(tenant=%s kind=%s instance=%s); skipping recap",
            tenant_id,
            trigger_kind,
            trigger_instance_id,
            exc_info=True,
        )
        return None

    # 4) Search (with hard timeout + total exception swallow).
    cases: list[dict] = []
    if query:
        cases = _run_search_with_timeout(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            query=query,
            scope=scope,
            k=k,
            min_similarity=min_similarity,
            vector=vector_kind,
            trigger_kind=trigger_kind,
            include_failed=include_failed,
        )

    # 5) Render the format template (or the empty-state template).
    cases_count = len(cases)
    try:
        if cases_count == 0:
            rendered = _render_template(
                _EMPTY_STATE_TEMPLATE,
                {
                    "min_similarity": min_similarity,
                    "query": query,
                    "trigger_kind": trigger_kind,
                },
            )
        else:
            rendered = _render_template(
                format_template or _DEFAULT_FORMAT_TEMPLATE,
                {
                    "cases": cases,
                    "count": cases_count,
                    "query": query,
                    "trigger_kind": trigger_kind,
                    "min_similarity": min_similarity,
                },
            )
    except Exception:  # noqa: BLE001 — covers jinja2.TemplateError
        logger.warning(
            "trigger_recap: format_template render failed "
            "(tenant=%s kind=%s instance=%s); skipping recap",
            tenant_id,
            trigger_kind,
            trigger_instance_id,
            exc_info=True,
        )
        return None

    # 6) Truncate hard to the configured budget.
    rendered_text = (rendered or "").strip()
    if len(rendered_text) > max_recap_chars:
        rendered_text = rendered_text[:max_recap_chars]

    if not rendered_text:
        # Defensive: never return an empty rendered_text — the contract
        # is that callers receive either ``None`` (disabled / failed) or
        # a non-empty string. Empty string would silently mask an
        # infrastructure bug as "no past cases".
        logger.warning(
            "trigger_recap: rendered text was empty after truncation "
            "(tenant=%s kind=%s instance=%s); returning None",
            tenant_id,
            trigger_kind,
            trigger_instance_id,
        )
        return None

    config_snapshot = {
        "scope": scope,
        "k": k,
        "min_similarity": min_similarity,
        "vector_kind": vector_kind,
        "inject_position": inject_position,
        "query_template_hash": _hash_query_template(query_template),
    }

    logger.info(
        "trigger_recap: built recap tenant=%s kind=%s instance=%s agent=%s "
        "cases=%d chars=%d scope=%s",
        tenant_id,
        trigger_kind,
        trigger_instance_id,
        agent_id,
        cases_count,
        len(rendered_text),
        scope,
    )

    return {
        "rendered_text": rendered_text,
        "cases_used": cases_count,
        "config_snapshot": config_snapshot,
    }
