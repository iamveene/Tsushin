"""Add tenant-managed Password Vault secret overrides.

Revision ID: 0089
Revises: 0088
Create Date: 2026-05-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0089"
down_revision: Union[str, None] = "0088"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table_name: str) -> bool:
    return table_name in sa.inspect(op.get_bind()).get_table_names()


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    if not _has_table("password_vault_secret_override"):
        op.create_table(
            "password_vault_secret_override",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column(
                "integration_id",
                sa.Integer(),
                sa.ForeignKey("password_vault_integration.id", ondelete="CASCADE"),
                nullable=False,
            ),
            sa.Column("vault", sa.String(length=200), nullable=True),
            sa.Column("item_ref", sa.String(length=300), nullable=False),
            sa.Column("field_name", sa.String(length=200), nullable=False),
            sa.Column("field_type", sa.String(length=32), nullable=False, server_default="CONCEALED"),
            sa.Column("value_encrypted", sa.Text(), nullable=False),
            sa.Column("value_preview", sa.String(length=32), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "tenant_id",
                "integration_id",
                "vault",
                "item_ref",
                "field_name",
                name="uq_password_vault_secret_override_field",
            ),
        )

    if "idx_password_vault_secret_override_lookup" not in _indexes("password_vault_secret_override"):
        op.create_index(
            "idx_password_vault_secret_override_lookup",
            "password_vault_secret_override",
            ["tenant_id", "integration_id", "item_ref", "field_name"],
        )
    if "ix_password_vault_secret_override_tenant_id" not in _indexes("password_vault_secret_override"):
        op.create_index(
            "ix_password_vault_secret_override_tenant_id",
            "password_vault_secret_override",
            ["tenant_id"],
        )
    if "ix_password_vault_secret_override_integration_id" not in _indexes("password_vault_secret_override"):
        op.create_index(
            "ix_password_vault_secret_override_integration_id",
            "password_vault_secret_override",
            ["integration_id"],
        )


def downgrade() -> None:
    if not _has_table("password_vault_secret_override"):
        return
    for index_name in (
        "ix_password_vault_secret_override_integration_id",
        "ix_password_vault_secret_override_tenant_id",
        "idx_password_vault_secret_override_lookup",
    ):
        if index_name in _indexes("password_vault_secret_override"):
            op.drop_index(index_name, table_name="password_vault_secret_override")
    op.drop_table("password_vault_secret_override")
