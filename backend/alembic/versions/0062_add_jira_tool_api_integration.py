"""Add Jira Tool API integration rows.

Revision ID: 0062
Revises: 0061
Create Date: 2026-04-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0062"
down_revision: Union[str, None] = "0061"
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


def _foreign_keys(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk.get("name")}


def _backfill_jira_integrations() -> None:
    if not _has_table("jira_channel_instance") or not _has_table("jira_integration"):
        return
    if not _has_column("jira_channel_instance", "jira_integration_id"):
        return

    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            """
            SELECT id, tenant_id, integration_name, site_url, project_key,
                   auth_email, api_token_encrypted, api_token_preview,
                   is_active, health_status, health_status_reason,
                   last_health_check, created_at, updated_at
            FROM jira_channel_instance
            WHERE jira_integration_id IS NULL
            ORDER BY id ASC
            """
        )
    ).mappings().all()

    for row in rows:
        display_name = row["integration_name"] or f"Jira trigger #{row['id']}"
        hub_id = bind.execute(
            sa.text(
                """
                INSERT INTO hub_integration
                    (type, name, display_name, is_active, tenant_id,
                     created_at, updated_at, last_health_check,
                     health_status, health_status_reason)
                VALUES
                    ('jira', :name, :display_name, :is_active, :tenant_id,
                     COALESCE(:created_at, CURRENT_TIMESTAMP), :updated_at,
                     :last_health_check, :health_status, :health_status_reason)
                RETURNING id
                """
            ),
            {
                "name": display_name,
                "display_name": display_name,
                "is_active": row["is_active"],
                "tenant_id": row["tenant_id"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "last_health_check": row["last_health_check"],
                "health_status": row["health_status"] or "unknown",
                "health_status_reason": row["health_status_reason"],
            },
        ).scalar_one()
        bind.execute(
            sa.text(
                """
                INSERT INTO jira_integration
                    (id, site_url, project_key, auth_email,
                     api_token_encrypted, api_token_preview)
                VALUES
                    (:id, :site_url, :project_key, :auth_email,
                     :api_token_encrypted, :api_token_preview)
                """
            ),
            {
                "id": hub_id,
                "site_url": row["site_url"],
                "project_key": row["project_key"],
                "auth_email": row["auth_email"],
                "api_token_encrypted": row["api_token_encrypted"],
                "api_token_preview": row["api_token_preview"],
            },
        )
        bind.execute(
            sa.text(
                """
                UPDATE jira_channel_instance
                SET jira_integration_id = :jira_integration_id
                WHERE id = :trigger_id
                """
            ),
            {"jira_integration_id": hub_id, "trigger_id": row["id"]},
        )


def upgrade() -> None:
    if not _has_table("jira_integration"):
        op.create_table(
            "jira_integration",
            sa.Column("id", sa.Integer(), sa.ForeignKey("hub_integration.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("site_url", sa.String(length=500), nullable=False),
            sa.Column("project_key", sa.String(length=64), nullable=True),
            sa.Column("auth_email", sa.String(length=255), nullable=True),
            sa.Column("api_token_encrypted", sa.Text(), nullable=True),
            sa.Column("api_token_preview", sa.String(length=32), nullable=True),
        )
    if "idx_jira_integration_site_url" not in _indexes("jira_integration"):
        op.create_index("idx_jira_integration_site_url", "jira_integration", ["site_url"])
    if "idx_jira_integration_auth_email" not in _indexes("jira_integration"):
        op.create_index("idx_jira_integration_auth_email", "jira_integration", ["auth_email"])

    if _has_table("jira_channel_instance") and not _has_column("jira_channel_instance", "jira_integration_id"):
        with op.batch_alter_table("jira_channel_instance") as batch_op:
            batch_op.add_column(sa.Column("jira_integration_id", sa.Integer(), nullable=True))
            batch_op.create_foreign_key(
                "fk_jira_channel_instance_jira_integration_id",
                "jira_integration",
                ["jira_integration_id"],
                ["id"],
                ondelete="SET NULL",
            )
    if _has_table("jira_channel_instance") and "idx_jira_channel_instance_jira_integration_id" not in _indexes("jira_channel_instance"):
        op.create_index(
            "idx_jira_channel_instance_jira_integration_id",
            "jira_channel_instance",
            ["jira_integration_id"],
        )

    _backfill_jira_integrations()


def downgrade() -> None:
    if _has_table("jira_channel_instance"):
        indexes = _indexes("jira_channel_instance")
        if "idx_jira_channel_instance_jira_integration_id" in indexes:
            op.drop_index("idx_jira_channel_instance_jira_integration_id", table_name="jira_channel_instance")
        if _has_column("jira_channel_instance", "jira_integration_id"):
            with op.batch_alter_table("jira_channel_instance") as batch_op:
                if "fk_jira_channel_instance_jira_integration_id" in _foreign_keys("jira_channel_instance"):
                    batch_op.drop_constraint("fk_jira_channel_instance_jira_integration_id", type_="foreignkey")
                batch_op.drop_column("jira_integration_id")

    if _has_table("jira_integration"):
        for index_name in ("idx_jira_integration_auth_email", "idx_jira_integration_site_url"):
            if index_name in _indexes("jira_integration"):
                op.drop_index(index_name, table_name="jira_integration")
        op.drop_table("jira_integration")

    if _has_table("hub_integration"):
        op.execute("DELETE FROM hub_integration WHERE type = 'jira'")
