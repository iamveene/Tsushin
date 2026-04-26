"""Allow ``flow_run_triggered`` in message_queue.message_type CHECK constraint.

Revision ID: 0070
Revises: 0069
Create Date: 2026-04-26

Wave 4/5 release-finishing fix. The Wave 3 dispatch fork
(``trigger_dispatch_service._enqueue_bound_flows``) writes
``MessageQueue`` rows with ``message_type='flow_run_triggered'`` so the
QueueRouter's ``_dispatch_flow_run_triggered`` handler can pick them
up. But the CHECK constraint introduced in 0045 only allows
``('inbound_message', 'trigger_event', 'continuous_task')`` — every
bound-flow fan-out attempt 23001's with::

    psycopg2.errors.CheckViolation: new row for relation
    "message_queue" violates check constraint
    "ck_message_queue_message_type"

The dispatch wrapped the failure in a try/except so it never aborted
dispatch, but the fan-out path was silently broken. Caught by the
release-finishing dispatch E2E test (after fixing the agent_id NOT NULL
violation).

This migration drops the old constraint and re-adds it with
``flow_run_triggered`` included.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0070"
down_revision: Union[str, None] = "0069"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_OLD_TYPES = ('inbound_message', 'trigger_event', 'continuous_task')
_NEW_TYPES = (*_OLD_TYPES, 'flow_run_triggered')


def _constraint_exists(table: str, name: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return False
    return bool(
        bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.table_constraints "
                "WHERE table_name = :tbl AND constraint_name = :name AND constraint_type = 'CHECK'"
            ),
            {"tbl": table, "name": name},
        ).first()
    )


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return  # SQLite check constraints are inline; safe to skip.

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
    if bind.dialect.name != "postgresql":
        return

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
