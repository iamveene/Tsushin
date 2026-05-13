"""Add flow_run.trigger_event_id for WakeEvent correlation.

Revision ID: 0067
Revises: 0066
Create Date: 2026-04-26

Wave 1 of the Triggers↔Flows Unification (release/0.7.0).

Adds ``flow_run.trigger_event_id`` (FK to ``wake_event.id``, nullable,
ON DELETE SET NULL) so a FlowRun can be traced back to the trigger
event that woke it. Adds a partial unique index on
``(trigger_event_id, flow_definition_id)`` to prevent retry-driven
duplicate FlowRuns when a MessageQueue item is redelivered.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0067"
down_revision: Union[str, None] = "0066"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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
    if not _has_column("flow_run", "trigger_event_id"):
        # SQLite has no inline ALTER TABLE ADD CONSTRAINT support, but
        # the column itself is added cleanly. The FK is declared in the
        # ORM model; SQLite enforces FK constraints lazily, which is
        # acceptable here since the constraint is for audit/correlation
        # rather than referential integrity (ON DELETE SET NULL means
        # we tolerate the parent row going away).
        op.add_column(
            "flow_run",
            sa.Column(
                "trigger_event_id",
                sa.Integer(),
                sa.ForeignKey("wake_event.id", ondelete="SET NULL"),
                nullable=True,
            ),
        )

    indexes = _indexes("flow_run")
    if "ix_flow_run_trigger_event" not in indexes:
        op.create_index(
            "ix_flow_run_trigger_event",
            "flow_run",
            ["trigger_event_id"],
        )

    # Prevents duplicate FlowRuns when the QueueRouter retries delivery
    # of a flow_run_triggered MessageQueue item. NULL trigger_event_id
    # rows (manual / API / scheduled flow runs) are exempt from the
    # uniqueness constraint via the partial WHERE clause.
    if "uq_flow_run_per_event_per_flow" not in indexes:
        bind = op.get_bind()
        if bind.dialect.name == "sqlite":
            # SQLite supports partial indexes
            op.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_flow_run_per_event_per_flow "
                "ON flow_run (trigger_event_id, flow_definition_id) "
                "WHERE trigger_event_id IS NOT NULL"
            )
        else:
            # PostgreSQL also supports partial indexes
            op.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_flow_run_per_event_per_flow "
                "ON flow_run (trigger_event_id, flow_definition_id) "
                "WHERE trigger_event_id IS NOT NULL"
            )


def downgrade() -> None:
    indexes = _indexes("flow_run")
    if "uq_flow_run_per_event_per_flow" in indexes:
        op.drop_index("uq_flow_run_per_event_per_flow", table_name="flow_run")
    if "ix_flow_run_trigger_event" in indexes:
        op.drop_index("ix_flow_run_trigger_event", table_name="flow_run")

    if _has_column("flow_run", "trigger_event_id"):
        # SQLite ALTER TABLE DROP COLUMN is supported on 3.35+ (the
        # versions we ship). Use batch-mode for portability.
        with op.batch_alter_table("flow_run") as batch_op:
            batch_op.drop_column("trigger_event_id")
