"""Add channel event routing rules.

Revision numbering note: Track A2 owns slot 0050 and keeps the chain linear by
revising 0047, even though 0047 itself revises the integrated release head
0059.

Revision ID: 0050
Revises: 0047
Create Date: 2026-04-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB


revision: str = "0050"
down_revision: Union[str, None] = "0047"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def _drop_index_if_exists(name: str, table_name: str) -> None:
    if table_name in _tables() and name in _indexes(table_name):
        op.drop_index(name, table_name=table_name)


def upgrade() -> None:
    if "channel_event_rule" not in _tables():
        op.create_table(
            "channel_event_rule",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("channel_instance_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=64), nullable=True),
            sa.Column("criteria", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("priority", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("agent_id", sa.Integer(), sa.ForeignKey("agent.id", ondelete="CASCADE"), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "tenant_id",
                "channel_type",
                "channel_instance_id",
                "priority",
                name="uq_channel_event_rule_priority",
            ),
        )
    if "ix_channel_event_rule_instance" not in _indexes("channel_event_rule"):
        op.create_index(
            "ix_channel_event_rule_instance",
            "channel_event_rule",
            ["tenant_id", "channel_type", "channel_instance_id", "is_active"],
        )
    if "ix_channel_event_rule_agent" not in _indexes("channel_event_rule"):
        op.create_index("ix_channel_event_rule_agent", "channel_event_rule", ["agent_id"])


def downgrade() -> None:
    _drop_index_if_exists("ix_channel_event_rule_agent", "channel_event_rule")
    _drop_index_if_exists("ix_channel_event_rule_instance", "channel_event_rule")
    if "channel_event_rule" in _tables():
        op.drop_table("channel_event_rule")
