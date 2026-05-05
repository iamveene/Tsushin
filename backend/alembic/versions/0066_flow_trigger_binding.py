"""Add flow_trigger_binding table.

Revision ID: 0066
Revises: 0065
Create Date: 2026-04-26

Wave 1 of the Triggers↔Flows Unification (release/0.7.0).

Creates ``flow_trigger_binding`` — the boundary edge between a trigger
(channel instance) and a Flow (program). One flow can listen to N
triggers (fan-in); one trigger can wake N flows (fan-out). Combined with
the new ``source`` step type and the dispatch fork landing in Wave 2-3,
this table is what lets ``trigger_dispatch_service`` enqueue FlowRuns
alongside ContinuousRuns.

Notes:
- ``trigger_instance_id`` is a *semantic* FK into one of the per-kind
  channel-instance tables (jira_trigger / email_trigger / github_trigger
  / schedule_trigger / webhook_integration). It is NOT a declared FK
  because there is no single target table. Trigger DELETE handlers must
  call ``flow_binding_service.delete_bindings_for_trigger`` to clean up.
- ``source_node_id`` is SET NULL on flow_node delete so a Source-step
  removal doesn't break the binding row; FlowEngine recreates it lazily.
- ``suppress_default_agent`` defaults to false (parallel-run safety with
  the legacy ContinuousAgent dispatch path).
- ``is_system_managed`` marks the auto-generated 1-flow-per-trigger row
  created by Phase A's auto-generation in Wave 4.

The whole feature is gated by env var ``TSN_FLOWS_TRIGGER_BINDING_ENABLED``
(default false in 0.7.0). The schema lands now so backend code can
reference the table; behavior stays identical until the env var flips.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0066"
down_revision: Union[str, None] = "0065"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_names() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _has_table(table_name: str) -> bool:
    return table_name in _table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _has_table("flow_trigger_binding"):
        op.create_table(
            "flow_trigger_binding",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column(
                "flow_definition_id",
                sa.Integer(),
                sa.ForeignKey("flow_definition.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("trigger_kind", sa.String(length=32), nullable=False),
            sa.Column("trigger_instance_id", sa.Integer(), nullable=False),
            sa.Column(
                "source_node_id",
                sa.Integer(),
                sa.ForeignKey("flow_node.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column(
                "suppress_default_agent",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "is_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.true(),
            ),
            sa.Column(
                "is_system_managed",
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(),
                nullable=False,
                server_default=sa.func.current_timestamp(),
            ),
            sa.UniqueConstraint(
                "flow_definition_id",
                "trigger_kind",
                "trigger_instance_id",
                name="uq_flow_trigger_binding_unique",
            ),
        )

    # Idempotent index creation
    indexes = _indexes("flow_trigger_binding")
    if "ix_flow_trigger_binding_lookup" not in indexes:
        op.create_index(
            "ix_flow_trigger_binding_lookup",
            "flow_trigger_binding",
            ["tenant_id", "trigger_kind", "trigger_instance_id", "is_active"],
        )
    if "ix_flow_trigger_binding_flow" not in indexes:
        op.create_index(
            "ix_flow_trigger_binding_flow",
            "flow_trigger_binding",
            ["flow_definition_id"],
        )

    # SQLite trigger to reject cross-tenant bindings (flow.tenant_id must
    # equal binding.tenant_id). Defense-in-depth: the API layer also checks.
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_ftb_tenant_check_insert
            BEFORE INSERT ON flow_trigger_binding
            FOR EACH ROW
            WHEN (
                SELECT tenant_id FROM flow_definition WHERE id = NEW.flow_definition_id
            ) IS NOT NULL
            AND (
                SELECT tenant_id FROM flow_definition WHERE id = NEW.flow_definition_id
            ) != NEW.tenant_id
            BEGIN
                SELECT RAISE(ABORT, 'flow_trigger_binding tenant_id must match flow_definition.tenant_id');
            END;
            """
        )
        op.execute(
            """
            CREATE TRIGGER IF NOT EXISTS trg_ftb_tenant_check_update
            BEFORE UPDATE OF tenant_id, flow_definition_id ON flow_trigger_binding
            FOR EACH ROW
            WHEN (
                SELECT tenant_id FROM flow_definition WHERE id = NEW.flow_definition_id
            ) IS NOT NULL
            AND (
                SELECT tenant_id FROM flow_definition WHERE id = NEW.flow_definition_id
            ) != NEW.tenant_id
            BEGIN
                SELECT RAISE(ABORT, 'flow_trigger_binding tenant_id must match flow_definition.tenant_id');
            END;
            """
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        op.execute("DROP TRIGGER IF EXISTS trg_ftb_tenant_check_insert")
        op.execute("DROP TRIGGER IF EXISTS trg_ftb_tenant_check_update")

    if _has_table("flow_trigger_binding"):
        for index_name in (
            "ix_flow_trigger_binding_flow",
            "ix_flow_trigger_binding_lookup",
        ):
            if index_name in _indexes("flow_trigger_binding"):
                op.drop_index(index_name, table_name="flow_trigger_binding")
        op.drop_table("flow_trigger_binding")
