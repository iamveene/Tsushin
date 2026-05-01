"""Flow ↔ Trigger binding service helpers (v0.7.0 Triggers↔Flows Unification).

Wave 3 of the unification added the read-side helpers that
``trigger_dispatch_service`` uses to fan a wake event out to bound
flows, plus the cleanup hook that trigger DELETE handlers call.

Wave 4 adds ``ensure_system_managed_flow_for_trigger`` — Phase A's
auto-Flow generator. When a new trigger is created (any of jira /
email / github / webhook), this function creates a
system-managed FlowDefinition with the canonical
Source → Gate → Conversation → Notification chain plus a
``flow_trigger_binding`` row, so every trigger arrives with its own
default flow already wired. Casual users still see the same
"Enable Notification" toggle on the trigger page; the toggle now
flips the auto-flow's Notification node ``enabled`` flag instead of
mutating the legacy ContinuousAgent / ContinuousSubscription pair.

All read paths are gated by ``flows_trigger_binding_enabled()``;
all auto-generation is gated by ``flows_auto_generation_enabled()``;
mutation paths on ``flow_trigger_binding`` rows are not gated.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, Iterable, Optional

from sqlalchemy.orm import Session

from models import FlowDefinition, FlowNode, FlowTriggerBinding

logger = logging.getLogger(__name__)


# ============================================================================
# Wave 4 — Auto-Flow generation (Phase A)
# ============================================================================


# Trigger kind → DB instance table → field that holds the human-readable name
# used to title the auto-generated flow.
_KIND_NAME_FIELDS: dict[str, str] = {
    "jira": "integration_name",
    "email": "integration_name",
    "github": "integration_name",
    "webhook": "integration_name",
}

# Default Conversation step objective per kind (one-line system prompt seed).
_KIND_DEFAULT_OBJECTIVE: dict[str, str] = {
    "jira": "Process the inbound Jira event and surface the actionable insight.",
    "email": "Process the inbound email and surface the actionable insight.",
    "github": "Process the inbound GitHub event and surface the actionable insight.",
    "webhook": "Process the inbound webhook payload and surface the actionable insight.",
}


def _trigger_instance_name(db: Session, *, trigger_kind: str, trigger_instance_id: int) -> str:
    """Look up the human-readable name for a trigger instance.

    Returns a fallback like ``"Jira #5"`` when the instance row can't be
    located (rare — should be impossible if called from an auto-generation
    path right after the create commits).
    """
    from models import (
        EmailChannelInstance,
        GitHubChannelInstance,
        JiraChannelInstance,
        WebhookIntegration,
    )

    table = {
        "jira": JiraChannelInstance,
        "email": EmailChannelInstance,
        "github": GitHubChannelInstance,
        "webhook": WebhookIntegration,
    }.get(trigger_kind)
    if table is None:
        return f"{trigger_kind.capitalize()} #{trigger_instance_id}"

    row = db.query(table).filter(table.id == trigger_instance_id).first()
    if row is None:
        return f"{trigger_kind.capitalize()} #{trigger_instance_id}"

    name_field = _KIND_NAME_FIELDS.get(trigger_kind, "name")
    name = getattr(row, name_field, None)
    return name or f"{trigger_kind.capitalize()} #{trigger_instance_id}"


def find_system_managed_flow_for_trigger(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
) -> Optional[FlowDefinition]:
    """Return the system-managed FlowDefinition for a trigger if one exists.

    Idempotency anchor for ``ensure_system_managed_flow_for_trigger`` and
    for the Wave 4 notification-toggle write-through (it locates the
    auto-flow whose Notification node it should mutate).
    """
    binding = (
        db.query(FlowTriggerBinding)
        .filter(
            FlowTriggerBinding.tenant_id == tenant_id,
            FlowTriggerBinding.trigger_kind == trigger_kind,
            FlowTriggerBinding.trigger_instance_id == trigger_instance_id,
            FlowTriggerBinding.is_system_managed.is_(True),
        )
        .first()
    )
    if binding is None:
        return None
    return db.query(FlowDefinition).filter(FlowDefinition.id == binding.flow_definition_id).first()


def sync_system_managed_flow_default_agent(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
    default_agent_id: Optional[int],
) -> bool:
    """Keep the generated trigger Flow aligned with the trigger's default agent.

    Trigger PATCH endpoints own ``default_agent_id``. The system-managed
    Flow mirrors that value both on the FlowDefinition and on its generated
    Conversation node, so a trigger edit changes the actual execution path.
    """
    flow = find_system_managed_flow_for_trigger(
        db,
        tenant_id=tenant_id,
        trigger_kind=trigger_kind,
        trigger_instance_id=trigger_instance_id,
    )
    if flow is None:
        return False

    changed = False
    if flow.default_agent_id != default_agent_id:
        flow.default_agent_id = default_agent_id
        changed = True

    conversation_nodes = (
        db.query(FlowNode)
        .filter(
            FlowNode.flow_definition_id == flow.id,
            FlowNode.type == "conversation",
        )
        .all()
    )
    for node in conversation_nodes:
        if node.agent_id != default_agent_id:
            node.agent_id = default_agent_id
            node.updated_at = datetime.utcnow()
            changed = True

    if changed:
        flow.updated_at = datetime.utcnow()
    return changed


def ensure_system_managed_flow_for_trigger(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
    default_agent_id: Optional[int] = None,
    notification_recipient: Optional[str] = None,
    notification_enabled: bool = False,
) -> tuple[FlowDefinition, FlowTriggerBinding, bool]:
    """v0.7.0 Wave 4 — Phase A auto-Flow generation.

    Idempotently creates (or re-uses) a system-managed FlowDefinition for
    a trigger. The flow has 4 nodes:

      1. ``source`` — config: ``{trigger_kind, trigger_instance_id}``.
      2. ``gate`` — config: ``{mode: "programmatic", rules: []}`` (pass-all;
         the trigger's own ``trigger_criteria`` is the canonical filter).
      3. ``conversation`` — ``agent_id=default_agent_id``, kind-specific
         objective string. Acts as the "default agent" entry point.
      4. ``notification`` — ``enabled=False`` initially; the casual-user
         "Enable Notification" toggle flips this and sets ``recipient_phone``.

    Returns ``(flow, binding, created)`` where ``created`` is True iff a
    new flow was just inserted (False on idempotent re-runs).

    Caller is responsible for committing the session — this function
    flushes between inserts so foreign keys resolve, but the final
    transaction commit is the caller's call (so trigger create + auto-flow
    create can land in a single transaction or get rolled back together).
    """
    existing = find_system_managed_flow_for_trigger(
        db,
        tenant_id=tenant_id,
        trigger_kind=trigger_kind,
        trigger_instance_id=trigger_instance_id,
    )
    if existing is not None:
        binding = (
            db.query(FlowTriggerBinding)
            .filter(
                FlowTriggerBinding.tenant_id == tenant_id,
                FlowTriggerBinding.trigger_kind == trigger_kind,
                FlowTriggerBinding.trigger_instance_id == trigger_instance_id,
                FlowTriggerBinding.is_system_managed.is_(True),
            )
            .first()
        )
        return existing, binding, False

    instance_name = _trigger_instance_name(
        db,
        trigger_kind=trigger_kind,
        trigger_instance_id=trigger_instance_id,
    )
    objective = _KIND_DEFAULT_OBJECTIVE.get(trigger_kind, "Process the inbound event.")

    flow = FlowDefinition(
        tenant_id=tenant_id,
        name=f"{trigger_kind.capitalize()}: {instance_name}",
        description=f"Auto-generated default flow for the {trigger_kind} trigger '{instance_name}'.",
        execution_method="triggered",
        default_agent_id=default_agent_id,
        flow_type="workflow",
        is_active=True,
        is_system_owned=True,
        editable_by_tenant=True,
        deletable_by_tenant=False,
        initiator_type="programmatic",
        initiator_metadata={"reason": "trigger_auto_generated"},
    )
    db.add(flow)
    db.flush()  # populate flow.id

    source_node = FlowNode(
        flow_definition_id=flow.id,
        type="source",
        position=1,
        name="Source",
        config_json=json.dumps({
            "trigger_kind": trigger_kind,
            "trigger_instance_id": trigger_instance_id,
        }),
    )
    db.add(source_node)
    db.flush()

    gate_node = FlowNode(
        flow_definition_id=flow.id,
        type="gate",
        position=2,
        name="Criteria gate",
        config_json=json.dumps({
            "mode": "programmatic",
            "rules": [],  # empty = pass-all; trigger-side criteria is canonical
            "logic": "all",
        }),
    )
    db.add(gate_node)

    conversation_node = FlowNode(
        flow_definition_id=flow.id,
        type="conversation",
        position=3,
        name="Default agent",
        agent_id=default_agent_id,
        conversation_objective=objective,
        on_failure="continue" if notification_enabled and notification_recipient else None,
        config_json=json.dumps({
            "objective": objective,
            "allow_multi_turn": False,
        }),
    )
    db.add(conversation_node)

    notification_node = FlowNode(
        flow_definition_id=flow.id,
        type="notification",
        position=4,
        name="Notification",
        config_json=json.dumps({
            "enabled": bool(notification_enabled and notification_recipient),
            "channel": "whatsapp",
            "recipient": notification_recipient,
        }),
    )
    db.add(notification_node)
    db.flush()

    binding = FlowTriggerBinding(
        tenant_id=tenant_id,
        flow_definition_id=flow.id,
        trigger_kind=trigger_kind,
        trigger_instance_id=trigger_instance_id,
        source_node_id=source_node.id,
        suppress_default_agent=False,  # parallel-run safety: legacy path stays alive until backfill flips it
        is_active=True,
        is_system_managed=True,
    )
    db.add(binding)
    db.flush()

    logger.info(
        "Auto-generated system-managed flow %s for %s/%s (binding=%s, default_agent=%s)",
        flow.id,
        trigger_kind,
        trigger_instance_id,
        binding.id,
        default_agent_id,
    )
    return flow, binding, True


def update_auto_flow_notification(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
    enabled: bool,
    recipient_phone: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    """v0.7.0 Wave 4 — write-through helper for the casual-user notification toggle.

    Locates the system-managed auto-flow for a trigger and flips its
    Notification node ``enabled`` + ``recipient``. Returns a dict
    describing the resulting node config, or None when no auto-flow
    exists (e.g. trigger pre-dates the auto-gen rollout — fallback to
    the legacy ContinuousAgent path).

    NOTE: the kwarg is named ``recipient_phone`` for backwards
    compatibility with the existing email/jira notification subscription
    endpoints, but it is written as ``recipient`` in the node config to
    match the key NotificationStepHandler reads at flow_engine.py:362.

    Mirrors the API contract of the existing
    the trigger creation wizard and Flow editor so notification delivery stays
    on the auto-flow path.
    """
    flow = find_system_managed_flow_for_trigger(
        db,
        tenant_id=tenant_id,
        trigger_kind=trigger_kind,
        trigger_instance_id=trigger_instance_id,
    )
    if flow is None:
        return None

    notification_node = (
        db.query(FlowNode)
        .filter(
            FlowNode.flow_definition_id == flow.id,
            FlowNode.type == "notification",
        )
        .order_by(FlowNode.position)
        .first()
    )
    if notification_node is None:
        # Auto-flow shape drift — fix it lazily by adding a notification node.
        next_position = (
            db.query(FlowNode.position)
            .filter(FlowNode.flow_definition_id == flow.id)
            .order_by(FlowNode.position.desc())
            .first()
        )
        notification_node = FlowNode(
            flow_definition_id=flow.id,
            type="notification",
            position=(next_position[0] if next_position else 3) + 1,
            name="Notification",
            config_json=json.dumps({"enabled": False, "channel": "whatsapp"}),
        )
        db.add(notification_node)
        db.flush()

    config: dict[str, Any]
    try:
        config = json.loads(notification_node.config_json) if notification_node.config_json else {}
    except json.JSONDecodeError:
        config = {}

    config["enabled"] = bool(enabled)
    config["channel"] = config.get("channel", "whatsapp")
    # Drop any legacy ``recipient_phone`` key from earlier versions so the
    # engine sees a single source of truth.
    config.pop("recipient_phone", None)
    if recipient_phone is not None:
        config["recipient"] = recipient_phone
    notification_node.config_json = json.dumps(config)
    notification_node.updated_at = datetime.utcnow()

    if enabled and config.get("recipient"):
        conversation_nodes = (
            db.query(FlowNode)
            .filter(
                FlowNode.flow_definition_id == flow.id,
                FlowNode.type == "conversation",
            )
            .all()
        )
        for node in conversation_nodes:
            if node.on_failure != "continue":
                node.on_failure = "continue"
                node.updated_at = datetime.utcnow()

    return {
        "flow_definition_id": flow.id,
        "notification_node_id": notification_node.id,
        "enabled": config["enabled"],
        "recipient": config.get("recipient"),
        "channel": config.get("channel"),
    }


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
    github / webhook) because ``trigger_instance_id`` is a
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


def delete_system_owned_continuous_artifacts_for_trigger(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
) -> int:
    """Remove system-owned ContinuousSubscription rows for a deleted trigger.

    The legacy Jira/Email notification and triage paths created system-owned
    ContinuousAgent/ContinuousSubscription artifacts keyed by
    ``(channel_type, channel_instance_id)``. Trigger deletion owns those rows
    even after the public notification endpoints are retired. User-owned
    subscriptions are deliberately left untouched.
    """
    from models import ContinuousAgent, ContinuousSubscription

    subscriptions = (
        db.query(ContinuousSubscription)
        .filter(
            ContinuousSubscription.tenant_id == tenant_id,
            ContinuousSubscription.channel_type == trigger_kind,
            ContinuousSubscription.channel_instance_id == trigger_instance_id,
            ContinuousSubscription.is_system_owned.is_(True),
        )
        .all()
    )
    if not subscriptions:
        return 0

    continuous_agent_ids = {sub.continuous_agent_id for sub in subscriptions}
    for subscription in subscriptions:
        db.delete(subscription)
    db.flush()

    for continuous_agent_id in continuous_agent_ids:
        remaining_subscription = (
            db.query(ContinuousSubscription.id)
            .filter(
                ContinuousSubscription.tenant_id == tenant_id,
                ContinuousSubscription.continuous_agent_id == continuous_agent_id,
            )
            .first()
        )
        if remaining_subscription is not None:
            continue
        continuous_agent = (
            db.query(ContinuousAgent)
            .filter(
                ContinuousAgent.id == continuous_agent_id,
                ContinuousAgent.tenant_id == tenant_id,
                ContinuousAgent.is_system_owned.is_(True),
            )
            .first()
        )
        if continuous_agent is not None:
            db.delete(continuous_agent)

    return len(subscriptions)


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
