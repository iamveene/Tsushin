"""Add database-level safety net for trigger deletion cascade (BUG-QA070-WC-001).

The application layer (per-kind trigger DELETE handlers in routes_*_triggers.py)
already orchestrates cascade cleanup via flow_binding_service.delete_bindings_for_trigger().
However, ``flow_trigger_binding.trigger_instance_id`` is a polymorphic FK (kind+id pair)
so PostgreSQL cannot natively cascade. If a row is removed by any other path
(direct SQL DELETE, restore-from-backup, manual maintenance), the system-managed
auto-flow + nodes + binding row are orphaned.

This migration adds per-trigger-table BEFORE DELETE triggers that mirror the
service layer cascade: when a trigger row is deleted at the DB layer, the trigger
function removes any FlowTriggerBinding rows pointing at it, and the system-owned
FlowDefinitions those bindings reference (with all child flow_node + flow_run rows
cascading via existing ON DELETE CASCADE on flow_definition_id).

Revision ID: 0081
Revises: 0080
Create Date: 2026-05-03
"""
from typing import Sequence, Union

from alembic import op


revision: str = "0081"
down_revision: Union[str, None] = "0080"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Map: trigger table -> trigger_kind label used in flow_trigger_binding.trigger_kind
TRIGGER_TABLES = {
    "webhook_integration": "webhook",
    "email_channel_instance": "email",
    "jira_channel_instance": "jira",
    "github_channel_instance": "github",
}


def upgrade() -> None:
    # Shared trigger function: deletes bindings for a (kind, id) pair, then any
    # system-owned flow that no other non-system-managed binding references.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION fn_cascade_trigger_delete(
            p_tenant_id varchar,
            p_kind varchar,
            p_instance_id integer
        ) RETURNS void
        LANGUAGE plpgsql
        AS $$
        DECLARE
            v_flow_id integer;
        BEGIN
            -- Collect system-managed flow IDs for this (kind, id) before deleting bindings.
            FOR v_flow_id IN
                SELECT flow_definition_id
                FROM flow_trigger_binding
                WHERE tenant_id = p_tenant_id
                  AND trigger_kind = p_kind
                  AND trigger_instance_id = p_instance_id
                  AND is_system_managed = TRUE
            LOOP
                -- Only delete the flow if no OTHER non-system-managed binding still references it.
                IF NOT EXISTS (
                    SELECT 1
                    FROM flow_trigger_binding
                    WHERE flow_definition_id = v_flow_id
                      AND is_system_managed = FALSE
                ) THEN
                    DELETE FROM flow_definition
                    WHERE id = v_flow_id
                      AND is_system_owned = TRUE;
                END IF;
            END LOOP;

            -- Now drop all bindings for this (kind, id). Bindings whose flow was just
            -- deleted will be removed via the flow_definition_id ON DELETE CASCADE; we
            -- still need to remove non-system-managed bindings.
            DELETE FROM flow_trigger_binding
            WHERE tenant_id = p_tenant_id
              AND trigger_kind = p_kind
              AND trigger_instance_id = p_instance_id;
        END;
        $$;
        """
    )

    # One BEFORE DELETE trigger per trigger table.
    for table, kind in TRIGGER_TABLES.items():
        op.execute(
            f"""
            CREATE OR REPLACE FUNCTION fn_{table}_cascade_delete()
            RETURNS trigger
            LANGUAGE plpgsql
            AS $$
            BEGIN
                PERFORM fn_cascade_trigger_delete(OLD.tenant_id, '{kind}', OLD.id);
                RETURN OLD;
            END;
            $$;
            """
        )
        op.execute(
            f"""
            DROP TRIGGER IF EXISTS trg_{table}_cascade_delete ON {table};
            CREATE TRIGGER trg_{table}_cascade_delete
            BEFORE DELETE ON {table}
            FOR EACH ROW
            EXECUTE FUNCTION fn_{table}_cascade_delete();
            """
        )


def downgrade() -> None:
    for table in TRIGGER_TABLES:
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_cascade_delete ON {table};")
        op.execute(f"DROP FUNCTION IF EXISTS fn_{table}_cascade_delete();")
    op.execute("DROP FUNCTION IF EXISTS fn_cascade_trigger_delete(varchar, varchar, integer);")
