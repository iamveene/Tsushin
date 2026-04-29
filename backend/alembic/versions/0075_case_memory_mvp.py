"""Trigger Case Memory MVP — schema (table + check-constraint extension).

Revision ID: 0075
Revises: 0074
Create Date: 2026-04-29

Adds the ``case_memory`` table that stores compact post-execution case
records produced by terminal ContinuousRuns and trigger-origin FlowRuns,
plus three vector references (problem/action/outcome) written to the
existing vector-store path. Default-off behind ``TSN_CASE_MEMORY_ENABLED``.

Also extends the ``ck_message_queue_message_type`` CHECK constraint to
permit the new ``'case_index'`` discriminator that the queue router
dispatches to the case indexer worker. Postgres-only branch — SQLite
inline CHECKs are not used here so test fixtures (in-memory SQLite) are
unaffected.

The table carries the embedding contract resolved at write time
(``embedding_provider``, ``embedding_model``, ``embedding_dims``,
``embedding_metric``, optional ``embedding_task``) so a tenant that
later switches its default ``VectorStoreInstance`` to a higher-dim model
(e.g. Gemini at 768/1536/3072) can do so without retroactively breaking
prior cases — the ``embedding_dims`` here is the contract that produced
the existing ``vector_refs_json`` entries.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0075"
down_revision: Union[str, None] = "0074"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_TYPES = (
    "inbound_message",
    "trigger_event",
    "continuous_task",
    "flow_run_triggered",
)
_NEW_TYPES = (*_OLD_TYPES, "case_index")


def _constraint_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE table_name = :tbl AND constraint_name = :name "
                "AND constraint_type = 'CHECK'"
            ),
            {"tbl": table, "name": name},
        ).first()
    )


def upgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # ---------------------------------------------------------------
    # 1) Create the case_memory table.
    # ---------------------------------------------------------------
    op.create_table(
        "case_memory",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "tenant_id",
            sa.String(length=50),
            sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.Integer(),
            sa.ForeignKey("agent.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "wake_event_id",
            sa.Integer(),
            sa.ForeignKey("wake_event.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "continuous_run_id",
            sa.Integer(),
            sa.ForeignKey("continuous_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "flow_run_id",
            sa.Integer(),
            sa.ForeignKey("flow_run.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("origin_kind", sa.String(length=24), nullable=False),
        sa.Column("trigger_kind", sa.String(length=32), nullable=True),
        sa.Column("subject_digest", sa.String(length=128), nullable=True),
        sa.Column("problem_summary", sa.Text(), nullable=True),
        sa.Column("action_summary", sa.Text(), nullable=True),
        sa.Column("outcome_summary", sa.Text(), nullable=True),
        sa.Column("outcome_label", sa.String(length=24), nullable=False, server_default="unknown"),
        sa.Column(
            "vector_store_instance_id",
            sa.Integer(),
            sa.ForeignKey("vector_store_instance.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("embedding_provider", sa.String(length=32), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("embedding_dims", sa.Integer(), nullable=True),
        sa.Column("embedding_metric", sa.String(length=24), nullable=True),
        sa.Column("embedding_task", sa.String(length=64), nullable=True),
        sa.Column("vector_refs_json", sa.JSON(), nullable=True),
        sa.Column("index_status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("summary_status", sa.String(length=16), nullable=False, server_default="generated"),
        sa.Column("occurred_at", sa.DateTime(), nullable=True),
        sa.Column("indexed_at", sa.DateTime(), nullable=True),
        sa.Column("last_recalled_at", sa.DateTime(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )

    op.create_index(
        "ix_case_memory_tenant_id",
        "case_memory",
        ["tenant_id"],
    )
    op.create_index(
        "ix_case_memory_agent_id",
        "case_memory",
        ["agent_id"],
    )
    op.create_index(
        "ix_case_memory_wake_event_id",
        "case_memory",
        ["wake_event_id"],
    )
    op.create_index(
        "ix_case_memory_tenant_agent_occurred",
        "case_memory",
        ["tenant_id", "agent_id", "occurred_at"],
    )

    # Partial unique indexes — Postgres supports postgresql_where; for SQLite
    # the partial WHERE is silently ignored at runtime by alembic, so we
    # branch and emit a non-unique helper index on the dev/test SQLite path
    # (uniqueness is still enforced in app code via the idempotency guard
    # in case_memory_service.index_case).
    if dialect == "postgresql":
        op.create_index(
            "uq_case_memory_continuous_run",
            "case_memory",
            ["continuous_run_id"],
            unique=True,
            postgresql_where=sa.text("continuous_run_id IS NOT NULL"),
        )
        op.create_index(
            "uq_case_memory_flow_run",
            "case_memory",
            ["flow_run_id"],
            unique=True,
            postgresql_where=sa.text("flow_run_id IS NOT NULL"),
        )
    else:
        op.create_index(
            "ix_case_memory_continuous_run",
            "case_memory",
            ["continuous_run_id"],
        )
        op.create_index(
            "ix_case_memory_flow_run",
            "case_memory",
            ["flow_run_id"],
        )

    # ---------------------------------------------------------------
    # 2) Extend ck_message_queue_message_type CHECK to allow case_index.
    #    Postgres-only — SQLite check constraints are inline and the test
    #    in-memory schema is built from models.py without those CHECKs.
    # ---------------------------------------------------------------
    if dialect != "postgresql":
        return

    if _constraint_exists("message_queue", "ck_message_queue_message_type"):
        op.drop_constraint(
            "ck_message_queue_message_type",
            "message_queue",
            type_="check",
        )
    types_csv = ", ".join(f"'{t}'" for t in _NEW_TYPES)
    op.create_check_constraint(
        "ck_message_queue_message_type",
        "message_queue",
        f"message_type IN ({types_csv})",
    )


def downgrade() -> None:
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1) Restore the previous CHECK constraint (drop case_index).
    if dialect == "postgresql":
        if _constraint_exists("message_queue", "ck_message_queue_message_type"):
            op.drop_constraint(
                "ck_message_queue_message_type",
                "message_queue",
                type_="check",
            )
        types_csv = ", ".join(f"'{t}'" for t in _OLD_TYPES)
        op.create_check_constraint(
            "ck_message_queue_message_type",
            "message_queue",
            f"message_type IN ({types_csv})",
        )

    # 2) Drop indexes + table.
    if dialect == "postgresql":
        op.drop_index("uq_case_memory_flow_run", table_name="case_memory")
        op.drop_index("uq_case_memory_continuous_run", table_name="case_memory")
    else:
        op.drop_index("ix_case_memory_flow_run", table_name="case_memory")
        op.drop_index("ix_case_memory_continuous_run", table_name="case_memory")
    op.drop_index("ix_case_memory_tenant_agent_occurred", table_name="case_memory")
    op.drop_index("ix_case_memory_wake_event_id", table_name="case_memory")
    op.drop_index("ix_case_memory_agent_id", table_name="case_memory")
    op.drop_index("ix_case_memory_tenant_id", table_name="case_memory")

    op.drop_table("case_memory")
