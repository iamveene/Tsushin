"""Add financial utility bill storage.

Revision ID: 0087
Revises: 0086
Create Date: 2026-05-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0087"
down_revision: Union[str, None] = "0086"
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
    if not _has_table("financial_utility_bill"):
        op.create_table(
            "financial_utility_bill",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("automation_key", sa.String(length=100), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("unit_id", sa.String(length=100), nullable=False),
            sa.Column("asset", sa.String(length=255), nullable=True),
            sa.Column("address", sa.Text(), nullable=True),
            sa.Column("reference_month", sa.String(length=7), nullable=False),
            sa.Column("due_date", sa.String(length=10), nullable=True),
            sa.Column("amount_cents", sa.BigInteger(), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=False, server_default="BRL"),
            sa.Column("status", sa.String(length=100), nullable=True),
            sa.Column("barcode_encrypted", sa.Text(), nullable=True),
            sa.Column("barcode_preview", sa.String(length=64), nullable=True),
            sa.Column("raw_payload_json", sa.Text(), nullable=True),
            sa.Column("last_flow_run_id", sa.Integer(), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "tenant_id",
                "provider",
                "unit_id",
                "reference_month",
                name="uq_financial_utility_bill_dedupe",
            ),
        )

    existing = _indexes("financial_utility_bill")
    if "ix_financial_utility_bill_tenant_id" not in existing:
        op.create_index("ix_financial_utility_bill_tenant_id", "financial_utility_bill", ["tenant_id"])
    if "ix_financial_utility_bill_automation_key" not in existing:
        op.create_index("ix_financial_utility_bill_automation_key", "financial_utility_bill", ["automation_key"])
    if "idx_financial_utility_bill_tenant_provider" not in existing:
        op.create_index("idx_financial_utility_bill_tenant_provider", "financial_utility_bill", ["tenant_id", "provider"])
    if "idx_financial_utility_bill_due_date" not in existing:
        op.create_index("idx_financial_utility_bill_due_date", "financial_utility_bill", ["tenant_id", "due_date"])


def downgrade() -> None:
    if _has_table("financial_utility_bill"):
        for index_name in (
            "idx_financial_utility_bill_due_date",
            "idx_financial_utility_bill_tenant_provider",
            "ix_financial_utility_bill_automation_key",
            "ix_financial_utility_bill_tenant_id",
        ):
            if index_name in _indexes("financial_utility_bill"):
                op.drop_index(index_name, table_name="financial_utility_bill")
        op.drop_table("financial_utility_bill")
