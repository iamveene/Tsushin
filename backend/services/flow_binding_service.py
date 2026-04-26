"""Flow ↔ Trigger binding service helpers (v0.7.0 Triggers↔Flows Unification).

Wave 3 of the unification. ``flow_trigger_binding`` is the boundary edge
between a trigger (channel instance) and a Flow. This module owns the
small set of read-side helpers that ``trigger_dispatch_service`` uses
to fan a wake event out to bound flows, plus the cleanup hook that
trigger DELETE handlers call (because the binding's
``trigger_instance_id`` is a *semantic* FK across five per-kind tables
and cannot be expressed as a SQL CASCADE).

All read paths are gated by ``flows_trigger_binding_enabled()``;
mutation paths are not gated (binding rows can always be created /
updated / deleted, just won't be acted on by the dispatcher until the
env var flips).

Wave 4 will add ``ensure_system_managed_flow_for_trigger`` here for
the Phase A auto-Flow generation on trigger create.
"""

from __future__ import annotations

import logging
from typing import Iterable, Optional

from sqlalchemy.orm import Session

from models import FlowTriggerBinding

logger = logging.getLogger(__name__)


def list_active_bindings_for_trigger(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
) -> list[FlowTriggerBinding]:
    """Return all ``flow_trigger_binding`` rows for a trigger that should
    fire on a wake event (``is_active=True``).

    Tenant-scoped. The binding row's tenant_id is denormalized from the
    flow's tenant_id and protected by a SQLite trigger (see migration
    0066) — but we still apply the tenant filter belt-and-suspenders.
    """
    return (
        db.query(FlowTriggerBinding)
        .filter(
            FlowTriggerBinding.tenant_id == tenant_id,
            FlowTriggerBinding.trigger_kind == trigger_kind,
            FlowTriggerBinding.trigger_instance_id == trigger_instance_id,
            FlowTriggerBinding.is_active.is_(True),
        )
        .all()
    )


def has_active_suppress_default_binding(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
) -> bool:
    """True iff this (tenant, kind, instance) has at least one active
    binding with ``suppress_default_agent=True``.

    Used by the dispatcher to decide whether to enqueue ContinuousRuns
    for the legacy default-agent path. When True, the bound Flow takes
    over fully and the legacy ContinuousAgent is silenced.
    """
    return (
        db.query(FlowTriggerBinding.id)
        .filter(
            FlowTriggerBinding.tenant_id == tenant_id,
            FlowTriggerBinding.trigger_kind == trigger_kind,
            FlowTriggerBinding.trigger_instance_id == trigger_instance_id,
            FlowTriggerBinding.is_active.is_(True),
            FlowTriggerBinding.suppress_default_agent.is_(True),
        )
        .first()
        is not None
    )


def list_bindings_for_flow(
    db: Session,
    *,
    tenant_id: str,
    flow_definition_id: int,
) -> list[FlowTriggerBinding]:
    """All bindings (active and inactive) for a given flow.

    Used by the trigger detail "Wired Flows" UX in Wave 4 to render the
    list of triggers a flow listens to.
    """
    return (
        db.query(FlowTriggerBinding)
        .filter(
            FlowTriggerBinding.tenant_id == tenant_id,
            FlowTriggerBinding.flow_definition_id == flow_definition_id,
        )
        .all()
    )


def delete_bindings_for_trigger(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
    delete_system_managed_flows: bool = True,
) -> int:
    """Hard-delete every binding row for a (tenant, kind, instance).

    Called by the per-kind trigger DELETE handlers (jira / email /
    github / schedule / webhook) because ``trigger_instance_id`` is a
    semantic FK and cannot CASCADE on its own.

    When ``delete_system_managed_flows=True`` (the default), any
    auto-generated Flow that was attached to one of those bindings via
    ``is_system_managed=True`` also gets deleted — Phase A's
    invariant is "the auto-flow's lifetime equals the trigger's
    lifetime". User-authored bindings that happen to point at the same
    flow_definition_id are left alone.

    Returns the count of binding rows removed.
    """
    bindings = (
        db.query(FlowTriggerBinding)
        .filter(
            FlowTriggerBinding.tenant_id == tenant_id,
            FlowTriggerBinding.trigger_kind == trigger_kind,
            FlowTriggerBinding.trigger_instance_id == trigger_instance_id,
        )
        .all()
    )
    if not bindings:
        return 0

    system_managed_flow_ids: set[int] = set()
    for binding in bindings:
        if delete_system_managed_flows and binding.is_system_managed:
            system_managed_flow_ids.add(binding.flow_definition_id)
        db.delete(binding)

    if system_managed_flow_ids:
        from models import FlowDefinition  # local import — avoid widening top-level cycle
        for flow_id in system_managed_flow_ids:
            # Defensive: only delete if no OTHER non-system-managed binding still
            # references this flow.
            remaining = (
                db.query(FlowTriggerBinding.id)
                .filter(
                    FlowTriggerBinding.flow_definition_id == flow_id,
                    FlowTriggerBinding.is_system_managed.is_(False),
                )
                .first()
            )
            if remaining is None:
                flow = db.query(FlowDefinition).filter(FlowDefinition.id == flow_id).first()
                if flow is not None and flow.is_system_owned:
                    logger.info(
                        "Removing system-managed FlowDefinition %s after trigger %s/%s deletion",
                        flow_id,
                        trigger_kind,
                        trigger_instance_id,
                    )
                    db.delete(flow)

    return len(bindings)


def find_source_node_id(
    db: Session,
    *,
    flow_definition_id: int,
) -> Optional[int]:
    """Look up the FlowNode.id of the (one) source step in a flow.

    Used when persisting a binding to record ``source_node_id`` even
    if the caller didn't supply it. None when the flow has no source
    step.
    """
    from models import FlowNode  # local import to avoid module-load cycles
    src = (
        db.query(FlowNode)
        .filter(
            FlowNode.flow_definition_id == flow_definition_id,
            FlowNode.type.in_(("source", "Source")),
        )
        .first()
    )
    return src.id if src is not None else None
