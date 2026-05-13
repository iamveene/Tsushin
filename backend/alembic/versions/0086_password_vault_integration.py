"""Add Password Vault provider integration.

Revision ID: 0086
Revises: 0085
Create Date: 2026-05-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0086"
down_revision: Union[str, None] = "0085"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


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
    if not _has_table("password_vault_integration"):
        op.create_table(
            "password_vault_integration",
            sa.Column(
                "id",
                sa.Integer(),
                sa.ForeignKey("hub_integration.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("provider", sa.String(length=32), nullable=False, server_default="onepassword"),
            sa.Column("auth_method", sa.String(length=32), nullable=False, server_default="service_account"),
            sa.Column("token_encrypted", sa.Text(), nullable=True),
            sa.Column("token_preview", sa.String(length=32), nullable=True),
            sa.Column("account_url", sa.String(length=500), nullable=True),
            sa.Column("account_email", sa.String(length=255), nullable=True),
            sa.Column("default_vault", sa.String(length=200), nullable=True),
            sa.Column("default_vault_id", sa.String(length=128), nullable=True),
            sa.Column("allowed_items_json", sa.Text(), nullable=True),
            sa.Column("allowed_fields_json", sa.Text(), nullable=True),
            sa.Column("allow_secret_read", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("allow_totp_read", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("allow_metadata_read", sa.Boolean(), nullable=False, server_default=sa.true()),
        )
    else:
        for name, column in (
            ("provider", sa.Column("provider", sa.String(length=32), nullable=False, server_default="onepassword")),
            ("auth_method", sa.Column("auth_method", sa.String(length=32), nullable=False, server_default="service_account")),
            ("token_encrypted", sa.Column("token_encrypted", sa.Text(), nullable=True)),
            ("token_preview", sa.Column("token_preview", sa.String(length=32), nullable=True)),
            ("account_url", sa.Column("account_url", sa.String(length=500), nullable=True)),
            ("account_email", sa.Column("account_email", sa.String(length=255), nullable=True)),
            ("default_vault", sa.Column("default_vault", sa.String(length=200), nullable=True)),
            ("default_vault_id", sa.Column("default_vault_id", sa.String(length=128), nullable=True)),
            ("allowed_items_json", sa.Column("allowed_items_json", sa.Text(), nullable=True)),
            ("allowed_fields_json", sa.Column("allowed_fields_json", sa.Text(), nullable=True)),
            ("allow_secret_read", sa.Column("allow_secret_read", sa.Boolean(), nullable=False, server_default=sa.false())),
            ("allow_totp_read", sa.Column("allow_totp_read", sa.Boolean(), nullable=False, server_default=sa.false())),
            ("allow_metadata_read", sa.Column("allow_metadata_read", sa.Boolean(), nullable=False, server_default=sa.true())),
        ):
            if not _has_column("password_vault_integration", name):
                op.add_column("password_vault_integration", column)

    if "idx_password_vault_integration_provider" not in _indexes("password_vault_integration"):
        op.create_index("idx_password_vault_integration_provider", "password_vault_integration", ["provider"])
    if "idx_password_vault_integration_default_vault" not in _indexes("password_vault_integration"):
        op.create_index("idx_password_vault_integration_default_vault", "password_vault_integration", ["default_vault"])


def downgrade() -> None:
    if _has_table("password_vault_integration"):
        for index_name in (
            "idx_password_vault_integration_default_vault",
            "idx_password_vault_integration_provider",
        ):
            if index_name in _indexes("password_vault_integration"):
                op.drop_index(index_name, table_name="password_vault_integration")
        op.drop_table("password_vault_integration")
    if _has_table("hub_integration"):
        op.execute("DELETE FROM hub_integration WHERE type = 'password_vault'")
