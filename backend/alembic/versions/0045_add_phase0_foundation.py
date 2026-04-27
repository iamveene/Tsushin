"""v0.7.0 Phase 0 foundation

Adds the queue discriminator, trigger-event dedupe ledger, and Sentinel
continuous-agent approval toggles.

Revision ID: 0045
Revises: 0044
Create Date: 2026-04-23
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


MESSAGE_TYPES = ("inbound_message", "trigger_event", "continuous_task")


def _columns(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if column.name not in _columns(table_name):
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if column_name in _columns(table_name):
        op.drop_column(table_name, column_name)


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if name not in _indexes(table_name):
        op.create_index(name, table_name, columns)


def _drop_index_if_exists(name: str, table_name: str) -> None:
    if name in _indexes(table_name):
        op.drop_index(name, table_name=table_name)


def _constraint_exists(table_name: str, constraint_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    checks = inspector.get_check_constraints(table_name) if table_name in inspector.get_table_names() else []
    uniques = inspector.get_unique_constraints(table_name) if table_name in inspector.get_table_names() else []
    return any(c.get("name") == constraint_name for c in checks + uniques)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "message_queue" in tables and "message_type" not in _columns("message_queue"):
        op.add_column(
            "message_queue",
            sa.Column(
                "message_type",
                sa.String(length=32),
                nullable=False,
                server_default="inbound_message",
            ),
        )
    if "message_queue" in tables:
        _create_index_if_missing(
            "ix_message_queue_message_type",
            "message_queue",
            ["message_type"],
        )
        if not _constraint_exists("message_queue", "ck_message_queue_message_type"):
            op.create_check_constraint(
                "ck_message_queue_message_type",
                "message_queue",
                sa.text(
                    "message_type IN ('inbound_message', 'trigger_event', 'continuous_task')"
                ),
            )

    if "channel_event_dedupe" not in tables:
        op.create_table(
            "channel_event_dedupe",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="RESTRICT"),
                nullable=False,
            ),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("instance_id", sa.Integer(), nullable=False),
            sa.Column("dedupe_key", sa.String(length=512), nullable=False),
            sa.Column("outcome", sa.String(length=32), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "tenant_id",
                "channel_type",
                "instance_id",
                "dedupe_key",
                name="uq_channel_event_dedupe",
            ),
        )
    _create_index_if_missing(
        "ix_channel_event_dedupe_tenant_created",
        "channel_event_dedupe",
        ["tenant_id", "created_at"],
    )
    _create_index_if_missing(
        "ix_channel_event_dedupe_instance",
        "channel_event_dedupe",
        ["tenant_id", "instance_id", "created_at"],
    )

    _add_column_if_missing(
        "sentinel_config",
        sa.Column(
            "detect_continuous_agent_action_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    _add_column_if_missing(
        "sentinel_config",
        sa.Column("continuous_agent_action_approval_prompt", sa.Text(), nullable=True),
    )
    _add_column_if_missing(
        "sentinel_agent_config",
        sa.Column("detect_continuous_agent_action_approval", sa.Boolean(), nullable=True),
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "sentinel_agent_config" in tables:
        _drop_column_if_exists("sentinel_agent_config", "detect_continuous_agent_action_approval")
    if "sentinel_config" in tables:
        _drop_column_if_exists("sentinel_config", "continuous_agent_action_approval_prompt")
        _drop_column_if_exists("sentinel_config", "detect_continuous_agent_action_approval")

    if "channel_event_dedupe" in tables:
        _drop_index_if_exists("ix_channel_event_dedupe_instance", "channel_event_dedupe")
        _drop_index_if_exists("ix_channel_event_dedupe_tenant_created", "channel_event_dedupe")
        op.drop_table("channel_event_dedupe")

    if "message_queue" in tables:
        if _constraint_exists("message_queue", "ck_message_queue_message_type"):
            op.drop_constraint("ck_message_queue_message_type", "message_queue", type_="check")
        _drop_index_if_exists("ix_message_queue_message_type", "message_queue")
        _drop_column_if_exists("message_queue", "message_type")
