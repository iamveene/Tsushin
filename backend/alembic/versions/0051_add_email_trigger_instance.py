"""Add email_channel_instance table for persisted Email triggers.

Revision ID: 0051
Revises: 0048
Create Date: 2026-04-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0051"
down_revision: Union[str, None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _indexes(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "email_channel_instance" not in inspector.get_table_names():
        op.create_table(
            "email_channel_instance",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("integration_name", sa.String(length=100), nullable=False),
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="gmail"),
            sa.Column(
                "gmail_integration_id",
                sa.Integer(),
                sa.ForeignKey("gmail_integration.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("search_query", sa.String(length=500), nullable=True),
            sa.Column("poll_interval_seconds", sa.Integer(), nullable=False, server_default="60"),
            sa.Column(
                "default_agent_id",
                sa.Integer(),
                sa.ForeignKey("agent.id", ondelete="SET NULL"),
                nullable=True,
            ),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="active"),
            sa.Column("health_status", sa.String(length=20), nullable=False, server_default="unknown"),
            sa.Column("health_status_reason", sa.String(length=500), nullable=True),
            sa.Column("last_health_check", sa.DateTime(), nullable=True),
            sa.Column("last_activity_at", sa.DateTime(), nullable=True),
            sa.Column("last_cursor", sa.String(length=255), nullable=True),
            sa.Column("created_by", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
        )

    if "ix_email_channel_instance_tenant" not in _indexes("email_channel_instance"):
        op.create_index(
            "ix_email_channel_instance_tenant",
            "email_channel_instance",
            ["tenant_id"],
        )
    if "ix_email_channel_instance_status" not in _indexes("email_channel_instance"):
        op.create_index(
            "ix_email_channel_instance_status",
            "email_channel_instance",
            ["status"],
        )
    if "ix_email_channel_instance_gmail_integration_id" not in _indexes("email_channel_instance"):
        op.create_index(
            "ix_email_channel_instance_gmail_integration_id",
            "email_channel_instance",
            ["gmail_integration_id"],
        )
    if "ix_email_channel_instance_default_agent_id" not in _indexes("email_channel_instance"):
        op.create_index(
            "ix_email_channel_instance_default_agent_id",
            "email_channel_instance",
            ["default_agent_id"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "email_channel_instance" not in inspector.get_table_names():
        return

    for index_name in (
        "ix_email_channel_instance_default_agent_id",
        "ix_email_channel_instance_gmail_integration_id",
        "ix_email_channel_instance_status",
        "ix_email_channel_instance_tenant",
    ):
        if index_name in _indexes("email_channel_instance"):
            op.drop_index(index_name, table_name="email_channel_instance")
    op.drop_table("email_channel_instance")
