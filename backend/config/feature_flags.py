"""Feature flag helpers for the Triggers↔Flows Unification (release/0.7.0).

The repo has no centralized feature-flag system today (no GrowthBook,
LaunchDarkly, or in-house gate). For 0.7.0 we use environment variables
read at request time. Defaults are OFF so code can land progressively
in ``release/0.7.0`` while behavior stays identical until the operator
flips a flag (per-tenant in a future iteration; currently global).

Used by:
  - ``trigger_dispatch_service`` — Wave 3 dispatch fork.
  - ``flow_binding_service`` and the 5 trigger create endpoints —
    Wave 4 auto-generation + notification write-through.
  - ``0069_backfill_managed_notifications`` — Wave 5 backfill migration.
"""

from __future__ import annotations

import os


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def flows_trigger_binding_enabled() -> bool:
    """Wave 3 — dispatch reads flow_trigger_binding and enqueues FlowRuns.

    When False (default), TriggerDispatchService behaves exactly as it
    did in 0.6.x: produces ContinuousRuns only, never FlowRuns.
    """
    return _bool_env("TSN_FLOWS_TRIGGER_BINDING_ENABLED", default=False)


def flows_auto_generation_enabled() -> bool:
    """Wave 4 — new triggers auto-create a system-managed FlowDefinition.

    When False (default), the 5 trigger CREATE endpoints behave exactly
    as they did in 0.6.x: no Flow + binding rows are created. The
    Notification toggle write-through also remains routed to the legacy
    ContinuousAgent path.
    """
    return _bool_env("TSN_FLOWS_AUTO_GENERATION_ENABLED", default=False)


def flows_backfill_suppress_legacy() -> bool:
    """Wave 5 — flip suppress_default_agent=true on backfilled bindings.

    When False (default), backfilled bindings let the legacy
    ContinuousAgent path keep firing (parallel-run safety). When True,
    the legacy path is suppressed for every backfilled (tenant,
    channel_kind, instance_id) and the Flow is the sole producer of
    the WhatsApp notification.
    """
    return _bool_env("TSN_FLOWS_BACKFILL_SUPPRESS_LEGACY", default=False)


def case_memory_enabled() -> bool:
    """v0.7.0 — Trigger Case Memory MVP gate.

    When False (default), no ``case_index`` queue items are enqueued by
    the queue router after terminal ContinuousRuns or trigger-origin
    FlowRuns; no ``CaseMemory`` rows are written; the
    ``find_similar_past_cases`` skill is not registered; and the
    ``/api/case-memory/*`` admin/debug endpoints return ``503``. Existing
    trigger runtime behavior is unchanged.

    When True, the indexer hook fires after each terminal trigger-driven
    run and writes a compact ``CaseMemory`` row + up to 3 vectors
    (problem/action/outcome) into the tenant's resolved vector store
    using the embedding contract pinned on each row.
    """
    return _bool_env("TSN_CASE_MEMORY_ENABLED", default=False)


__all__ = [
    "flows_trigger_binding_enabled",
    "flows_auto_generation_enabled",
    "flows_backfill_suppress_legacy",
    "case_memory_enabled",
]
