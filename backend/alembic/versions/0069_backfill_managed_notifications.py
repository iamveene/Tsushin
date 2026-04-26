"""Backfill existing system-owned ContinuousAgent notify_only rows into Flows.

Revision ID: 0069
Revises: 0068
Create Date: 2026-04-26

Wave 5 of the Triggers↔Flows Unification (release/0.7.0).

Reads every ``ContinuousAgent`` row with ``execution_mode='notify_only'``
AND ``is_system_owned=True`` (the auto-created Jira/Email Managed
Notifications) joined with its ``ContinuousSubscription``, and creates
an equivalent system-managed FlowDefinition (4 nodes — Source → Gate →
Conversation → Notification) plus a ``flow_trigger_binding`` row. The
``recipient_phone`` from the subscription's ``action_config`` JSON is
carried into the Notification node's ``config_json``.

Idempotent: skips any (tenant, kind, instance) that already has a
system-managed binding. Safe to re-run.

**Gating** — the migration is **DDL-trivial** (no schema changes); the
DML body only runs when ``TSN_FLOWS_BACKFILL_ENABLED=true`` is set in
the operator's environment at the moment ``alembic upgrade`` executes.
This lets the migration revision land on production hosts without
performing the data migration until a DBA explicitly opts in. Re-running
``alembic upgrade head`` with the env var on later picks up where the
previous run left off (idempotent INSERTs).

**Suppress-default-agent semantics** — backfilled bindings ship with
``suppress_default_agent=False`` initially so the legacy ContinuousAgent
path keeps firing alongside the new Flow path (parallel-run safety,
detect duplicate WhatsApp via watcher dedupe). When the operator sets
``TSN_FLOWS_BACKFILL_SUPPRESS_LEGACY=true`` and re-runs the upgrade,
the migration flips ``suppress_default_agent=True`` on every backfilled
binding, cutting the legacy path off — at that point the Flow is the
sole producer of the WhatsApp notification.

**Rollback** — see ``backend/scripts/rollback_managed_flow_backfill.py``
for the data-only undo (deletes only the system-managed flows + bindings
this migration created, leaves the original ContinuousAgent rows
untouched).
"""

from __future__ import annotations

import json
import logging
import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0069"
down_revision: Union[str, None] = "0068"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def _kind_default_objective(kind: str) -> str:
    return {
        "jira": "Process the inbound Jira event and surface the actionable insight.",
        "email": "Process the inbound email and surface the actionable insight.",
        "github": "Process the inbound GitHub event and surface the actionable insight.",
        "schedule": "Process the scheduled fire and execute its routine.",
        "webhook": "Process the inbound webhook payload and surface the actionable insight.",
    }.get(kind, "Process the inbound event.")


def upgrade() -> None:
    backfill_enabled = _bool_env("TSN_FLOWS_BACKFILL_ENABLED", default=False)
    suppress_legacy = _bool_env("TSN_FLOWS_BACKFILL_SUPPRESS_LEGACY", default=False)

    if not backfill_enabled and not suppress_legacy:
        # No-op revision when both flags are off — landing the migration in
        # production without performing the data migration. Re-run with
        # TSN_FLOWS_BACKFILL_ENABLED=true to backfill, or
        # TSN_FLOWS_BACKFILL_SUPPRESS_LEGACY=true to flip suppression on
        # already-backfilled bindings.
        logger.info(
            "Skipping 0069 backfill body — neither TSN_FLOWS_BACKFILL_ENABLED nor "
            "TSN_FLOWS_BACKFILL_SUPPRESS_LEGACY is set. Migration revision applied as no-op."
        )
        return

    bind = op.get_bind()

    if suppress_legacy and not backfill_enabled:
        # Pure-suppress pass: only flip the suppress flag on already-backfilled
        # rows, don't try to create new flows.
        result = bind.execute(
            sa.text(
                "UPDATE flow_trigger_binding "
                "SET suppress_default_agent = true, updated_at = CURRENT_TIMESTAMP "
                "WHERE is_system_managed = true AND suppress_default_agent = false"
            )
        )
        rowcount = getattr(result, "rowcount", -1)
        logger.info(
            "0069 suppress-legacy pass: flipped suppress_default_agent on %s system-managed bindings",
            rowcount if rowcount >= 0 else "<unknown>",
        )
        return

    # Backfill pass.
    rows = bind.execute(
        sa.text(
            """
            SELECT
              ca.id        AS continuous_agent_id,
              ca.tenant_id AS tenant_id,
              ca.agent_id  AS agent_id,
              cs.id        AS subscription_id,
              cs.channel_type AS channel_type,
              cs.channel_instance_id AS channel_instance_id,
              cs.action_config AS action_config
            FROM continuous_agent ca
            JOIN continuous_subscription cs ON cs.continuous_agent_id = ca.id
            WHERE ca.execution_mode = 'notify_only'
              AND ca.is_system_owned = true
              AND cs.is_system_owned = true
              AND cs.status = 'active'
            """
        )
    ).fetchall()

    created = 0
    skipped = 0
    failed = 0

    for row in rows:
        try:
            tenant_id = row.tenant_id
            kind = row.channel_type
            instance_id = row.channel_instance_id
            agent_id = row.agent_id
            action_config = row.action_config or {}
            if isinstance(action_config, str):
                try:
                    action_config = json.loads(action_config)
                except (TypeError, ValueError):
                    action_config = {}
            recipient_phone = action_config.get("recipient_phone") if isinstance(action_config, dict) else None

            # Idempotency: skip if a system-managed binding already exists.
            existing = bind.execute(
                sa.text(
                    "SELECT id FROM flow_trigger_binding "
                    "WHERE tenant_id = :t AND trigger_kind = :k AND trigger_instance_id = :i "
                    "  AND is_system_managed = true LIMIT 1"
                ),
                {"t": tenant_id, "k": kind, "i": instance_id},
            ).first()
            if existing is not None:
                # Optionally flip suppress on the existing row when the operator
                # passes both flags in the same upgrade.
                if suppress_legacy:
                    bind.execute(
                        sa.text(
                            "UPDATE flow_trigger_binding "
                            "SET suppress_default_agent = true, updated_at = CURRENT_TIMESTAMP "
                            "WHERE id = :id AND suppress_default_agent = false"
                        ),
                        {"id": existing.id},
                    )
                skipped += 1
                continue

            # Look up the integration name for the auto-flow title.
            kind_to_table_field = {
                "jira": ("jira_channel_instance", "integration_name"),
                "email": ("email_channel_instance", "integration_name"),
                "github": ("github_channel_instance", "integration_name"),
                "schedule": ("schedule_channel_instance", "name"),
                "webhook": ("webhook_integration", "integration_name"),
            }
            table_info = kind_to_table_field.get(kind)
            integration_name = f"{kind.capitalize()} #{instance_id}"
            if table_info is not None:
                tbl, field = table_info
                name_row = bind.execute(
                    sa.text(f"SELECT {field} FROM {tbl} WHERE id = :i"),
                    {"i": instance_id},
                ).first()
                if name_row is not None and getattr(name_row, field, None):
                    integration_name = getattr(name_row, field)

            # Insert the flow_definition row.
            flow_result = bind.execute(
                sa.text(
                    """
                    INSERT INTO flow_definition
                      (tenant_id, name, description, execution_method, default_agent_id,
                       initiator_type, initiator_metadata, flow_type,
                       is_active, is_system_owned, editable_by_tenant, deletable_by_tenant,
                       version, execution_count, created_at, updated_at)
                    VALUES
                      (:tenant_id, :name, :description, 'triggered', :default_agent_id,
                       'programmatic', :initiator_metadata, 'workflow',
                       true, true, true, false,
                       1, 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    RETURNING id
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "name": f"{kind.capitalize()}: {integration_name}",
                    "description": f"Backfilled from system-owned notify_only ContinuousAgent #{row.continuous_agent_id}.",
                    "default_agent_id": agent_id,
                    "initiator_metadata": json.dumps({
                        "reason": "wave5_backfill",
                        "source_continuous_agent_id": row.continuous_agent_id,
                        "source_subscription_id": row.subscription_id,
                    }),
                },
            )
            flow_id = flow_result.scalar()

            objective = _kind_default_objective(kind)

            # Insert the 4 step rows. ``config_json`` is text in the model.
            # Note: flow_node has many optional columns; we only set the ones
            # the runtime needs.
            bind.execute(
                sa.text(
                    """
                    INSERT INTO flow_node
                      (flow_definition_id, type, position, name, config_json,
                       timeout_seconds, retry_on_failure, max_retries, retry_delay_seconds,
                       allow_multi_turn, max_turns, created_at, updated_at)
                    VALUES
                      (:flow_id, 'source', 1, 'Source', :cfg,
                       300, false, 0, 1,
                       false, 20, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "flow_id": flow_id,
                    "cfg": json.dumps({"trigger_kind": kind, "trigger_instance_id": instance_id}),
                },
            )
            # Capture source_node_id for the binding via a follow-up SELECT.
            source_node_id = bind.execute(
                sa.text(
                    "SELECT id FROM flow_node WHERE flow_definition_id = :f AND type = 'source' "
                    "ORDER BY position LIMIT 1"
                ),
                {"f": flow_id},
            ).scalar()

            bind.execute(
                sa.text(
                    """
                    INSERT INTO flow_node
                      (flow_definition_id, type, position, name, config_json,
                       timeout_seconds, retry_on_failure, max_retries, retry_delay_seconds,
                       allow_multi_turn, max_turns, created_at, updated_at)
                    VALUES
                      (:flow_id, 'gate', 2, 'Criteria gate', :cfg,
                       300, false, 0, 1,
                       false, 20, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "flow_id": flow_id,
                    "cfg": json.dumps({"mode": "programmatic", "rules": [], "logic": "all"}),
                },
            )
            bind.execute(
                sa.text(
                    """
                    INSERT INTO flow_node
                      (flow_definition_id, type, position, name, config_json, agent_id,
                       conversation_objective, allow_multi_turn, max_turns,
                       timeout_seconds, retry_on_failure, max_retries, retry_delay_seconds,
                       created_at, updated_at)
                    VALUES
                      (:flow_id, 'conversation', 3, 'Default agent', :cfg, :agent_id,
                       :objective, false, 20,
                       300, false, 0, 1,
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "flow_id": flow_id,
                    "cfg": json.dumps({"objective": objective, "allow_multi_turn": False}),
                    "agent_id": agent_id,
                    "objective": objective,
                },
            )
            bind.execute(
                sa.text(
                    """
                    INSERT INTO flow_node
                      (flow_definition_id, type, position, name, config_json,
                       timeout_seconds, retry_on_failure, max_retries, retry_delay_seconds,
                       allow_multi_turn, max_turns, created_at, updated_at)
                    VALUES
                      (:flow_id, 'notification', 4, 'Notification', :cfg,
                       300, false, 0, 1,
                       false, 20, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "flow_id": flow_id,
                    "cfg": json.dumps({
                        "enabled": bool(recipient_phone),
                        "channel": "whatsapp",
                        "recipient_phone": recipient_phone,
                    }),
                },
            )

            bind.execute(
                sa.text(
                    """
                    INSERT INTO flow_trigger_binding
                      (tenant_id, flow_definition_id, trigger_kind, trigger_instance_id,
                       source_node_id, suppress_default_agent, is_active, is_system_managed,
                       created_at, updated_at)
                    VALUES
                      (:tenant_id, :flow_id, :kind, :instance_id,
                       :source_node_id, :suppress, true, true,
                       CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """
                ),
                {
                    "tenant_id": tenant_id,
                    "flow_id": flow_id,
                    "kind": kind,
                    "instance_id": instance_id,
                    "source_node_id": source_node_id,
                    "suppress": suppress_legacy,  # respects the operator's choice
                },
            )
            created += 1
        except Exception as exc:  # pragma: no cover — log and keep going
            logger.exception("0069 backfill failed for ContinuousAgent #%s: %s", row.continuous_agent_id, exc)
            failed += 1

    logger.info(
        "0069 backfill complete: created=%d skipped=%d failed=%d (suppress_legacy=%s)",
        created, skipped, failed, suppress_legacy,
    )


def downgrade() -> None:
    # Data-only undo — only delete what THIS migration created
    # (system-managed flows + bindings whose initiator_metadata.reason
    # is 'wave5_backfill'). User-authored flows and bindings are
    # untouched. The original ContinuousAgent + ContinuousSubscription
    # rows are also untouched (this migration never deleted them).
    bind = op.get_bind()

    flow_ids = [
        r.id for r in bind.execute(
            sa.text(
                "SELECT id FROM flow_definition "
                "WHERE is_system_owned = true "
                "  AND initiator_metadata::text LIKE '%wave5_backfill%'"
            )
        ).fetchall()
    ]
    if flow_ids:
        ids_csv = ",".join(str(fid) for fid in flow_ids)
        # Bindings → flow_node (CASCADE on flow_definition delete via the
        # ORM relationship's cascade='all, delete-orphan'). flow_trigger_binding
        # also CASCADEs on flow_definition_id. So a single delete on the
        # flow_definition rows is enough.
        bind.execute(sa.text(f"DELETE FROM flow_definition WHERE id IN ({ids_csv})"))
        logger.info("0069 downgrade: deleted %d system-managed backfill flows", len(flow_ids))
