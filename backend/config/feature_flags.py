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


def case_memory_enabled(tenant_id: str | None = None, db=None) -> bool:
    """v0.7.x — per-tenant case-memory gate. Reads ``tenant.case_memory_enabled``.

    SaaS configuration: settable via the tenant settings UI, NOT env vars.
    Default True (the column itself defaults TRUE in alembic 0077 so any
    new tenant gets the feature out of the box).

    Returns ``True`` when:
      - ``tenant_id`` / ``db`` is omitted (defensive default — no DB
        lookup performed), OR
      - the row's ``case_memory_enabled`` column is True.
    """
    if tenant_id is None or db is None:
        return True
    try:
        from models_rbac import Tenant

        row = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if row is None:
            return True
        return bool(getattr(row, "case_memory_enabled", True))
    except Exception:
        # Defensive — never block dispatch on a flag-lookup failure.
        return True


def case_memory_recap_enabled(tenant_id: str | None = None, db=None) -> bool:
    """v0.7.x — per-tenant recap injection gate.

    SaaS configuration: settable via the tenant settings UI. Default True.
    When False, ``trigger_recap_service.build_memory_recap`` returns
    ``None`` for this tenant regardless of per-trigger config. The
    case-memory indexer (write-side) is unaffected.
    """
    if tenant_id is None or db is None:
        return True
    try:
        from models_rbac import Tenant

        row = db.query(Tenant).filter(Tenant.id == tenant_id).first()
        if row is None:
            return True
        return bool(getattr(row, "case_memory_recap_enabled", True))
    except Exception:
        return True


__all__ = [
    "flows_trigger_binding_enabled",
    "flows_auto_generation_enabled",
    "flows_backfill_suppress_legacy",
    "case_memory_enabled",
    "case_memory_recap_enabled",
]
