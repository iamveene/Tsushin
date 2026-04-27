"""default_agent_id FKs on entry-point instances + user_channel_default_agent

Revision ID: 0046
Revises: 0045
Create Date: 2026-04-23
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


INSTANCE_TABLES = (
    "whatsapp_mcp_instance",
    "telegram_bot_instance",
    "slack_integration",
    "discord_integration",
    "webhook_integration",
)


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


def _foreign_keys(table_name: str) -> set[str]:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk.get("name")}


def _add_default_agent_fk(table_name: str) -> None:
    if "default_agent_id" not in _columns(table_name):
        op.add_column(table_name, sa.Column("default_agent_id", sa.Integer(), nullable=True))

    fk_name = f"fk_{table_name}_default_agent_id"
    if fk_name not in _foreign_keys(table_name):
        op.create_foreign_key(
            fk_name,
            table_name,
            "agent",
            ["default_agent_id"],
            ["id"],
            ondelete="SET NULL",
        )

    index_name = f"ix_{table_name}_default_agent_id"
    if index_name not in _indexes(table_name):
        op.create_index(index_name, table_name, ["default_agent_id"])


def _drop_default_agent_fk(table_name: str) -> None:
    fk_name = f"fk_{table_name}_default_agent_id"
    if fk_name in _foreign_keys(table_name):
        op.drop_constraint(fk_name, table_name, type_="foreignkey")

    index_name = f"ix_{table_name}_default_agent_id"
    if index_name in _indexes(table_name):
        op.drop_index(index_name, table_name=table_name)

    if "default_agent_id" in _columns(table_name):
        op.drop_column(table_name, "default_agent_id")


def upgrade() -> None:
    for table_name in INSTANCE_TABLES:
        _add_default_agent_fk(table_name)

    if "user_channel_default_agent" not in sa.inspect(op.get_bind()).get_table_names():
        op.create_table(
            "user_channel_default_agent",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "tenant_id",
                sa.String(length=50),
                sa.ForeignKey("tenant.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("channel_type", sa.String(length=32), nullable=False),
            sa.Column("user_identifier", sa.String(length=256), nullable=False),
            sa.Column(
                "agent_id",
                sa.Integer(),
                sa.ForeignKey("agent.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint(
                "tenant_id",
                "channel_type",
                "user_identifier",
                name="uq_user_channel_default_agent",
            ),
        )
        op.create_index(
            "ix_user_channel_default_agent_tenant_channel",
            "user_channel_default_agent",
            ["tenant_id", "channel_type"],
        )

    op.execute(
        """
        UPDATE whatsapp_mcp_instance AS wmi
        SET default_agent_id = (
            SELECT a.id
            FROM agent AS a
            WHERE a.whatsapp_integration_id = wmi.id
              AND a.tenant_id = wmi.tenant_id
            ORDER BY a.id ASC
            LIMIT 1
        )
        WHERE default_agent_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE telegram_bot_instance AS tbi
        SET default_agent_id = (
            SELECT a.id
            FROM agent AS a
            WHERE a.telegram_integration_id = tbi.id
              AND a.tenant_id = tbi.tenant_id
            ORDER BY a.id ASC
            LIMIT 1
        )
        WHERE default_agent_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE slack_integration AS si
        SET default_agent_id = (
            SELECT a.id
            FROM agent AS a
            WHERE a.slack_integration_id = si.id
              AND a.tenant_id = si.tenant_id
            ORDER BY a.id ASC
            LIMIT 1
        )
        WHERE default_agent_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE discord_integration AS di
        SET default_agent_id = (
            SELECT a.id
            FROM agent AS a
            WHERE a.discord_integration_id = di.id
              AND a.tenant_id = di.tenant_id
            ORDER BY a.id ASC
            LIMIT 1
        )
        WHERE default_agent_id IS NULL
        """
    )
    op.execute(
        """
        UPDATE webhook_integration AS wi
        SET default_agent_id = (
            SELECT a.id
            FROM agent AS a
            WHERE a.webhook_integration_id = wi.id
              AND a.tenant_id = wi.tenant_id
            ORDER BY a.id ASC
            LIMIT 1
        )
        WHERE default_agent_id IS NULL
        """
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if "user_channel_default_agent" in inspector.get_table_names():
        if "ix_user_channel_default_agent_tenant_channel" in _indexes("user_channel_default_agent"):
            op.drop_index(
                "ix_user_channel_default_agent_tenant_channel",
                table_name="user_channel_default_agent",
            )
        op.drop_table("user_channel_default_agent")

    for table_name in reversed(INSTANCE_TABLES):
        _drop_default_agent_fk(table_name)
