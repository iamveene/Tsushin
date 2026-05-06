"""Add generic financial automation records.

Revision ID: 0088
Revises: 0087
Create Date: 2026-05-05
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0088"
down_revision: Union[str, None] = "0087"
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
    if not _has_table("financial_automation_record"):
        op.create_table(
            "financial_automation_record",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("record_type", sa.String(length=50), nullable=False),
            sa.Column("automation_key", sa.String(length=100), nullable=False),
            sa.Column("provider", sa.String(length=50), nullable=False),
            sa.Column("subject_key", sa.String(length=255), nullable=False),
            sa.Column("period_key", sa.String(length=64), nullable=False),
            sa.Column("external_id", sa.String(length=255), nullable=True),
            sa.Column("dedupe_key", sa.String(length=512), nullable=False),
            sa.Column("title", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=100), nullable=True),
            sa.Column("amount_cents", sa.BigInteger(), nullable=True),
            sa.Column("currency", sa.String(length=3), nullable=True),
            sa.Column("due_date", sa.String(length=10), nullable=True),
            sa.Column("occurred_on", sa.String(length=10), nullable=True),
            sa.Column("redacted_payload_json", sa.Text(), nullable=True),
            sa.Column("sensitive_payload_encrypted", sa.Text(), nullable=True),
            sa.Column("last_flow_run_id", sa.Integer(), nullable=True),
            sa.Column("last_seen_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint(
                "tenant_id",
                "dedupe_key",
                name="uq_financial_automation_record_dedupe",
            ),
        )

    existing = _indexes("financial_automation_record")
    if "ix_financial_automation_record_tenant_id" not in existing:
        op.create_index("ix_financial_automation_record_tenant_id", "financial_automation_record", ["tenant_id"])
    if "ix_financial_automation_record_record_type" not in existing:
        op.create_index("ix_financial_automation_record_record_type", "financial_automation_record", ["record_type"])
    if "ix_financial_automation_record_automation_key" not in existing:
        op.create_index("ix_financial_automation_record_automation_key", "financial_automation_record", ["automation_key"])
    if "ix_financial_automation_record_provider" not in existing:
        op.create_index("ix_financial_automation_record_provider", "financial_automation_record", ["provider"])
    if "idx_financial_automation_record_tenant_type" not in existing:
        op.create_index("idx_financial_automation_record_tenant_type", "financial_automation_record", ["tenant_id", "record_type"])
    if "idx_financial_automation_record_provider" not in existing:
        op.create_index("idx_financial_automation_record_provider", "financial_automation_record", ["tenant_id", "provider"])
    if "idx_financial_automation_record_period" not in existing:
        op.create_index("idx_financial_automation_record_period", "financial_automation_record", ["tenant_id", "period_key"])


def downgrade() -> None:
    if _has_table("financial_automation_record"):
        for index_name in (
            "idx_financial_automation_record_period",
            "idx_financial_automation_record_provider",
            "idx_financial_automation_record_tenant_type",
            "ix_financial_automation_record_provider",
            "ix_financial_automation_record_automation_key",
            "ix_financial_automation_record_record_type",
            "ix_financial_automation_record_tenant_id",
        ):
            if index_name in _indexes("financial_automation_record"):
                op.drop_index(index_name, table_name="financial_automation_record")
        op.drop_table("financial_automation_record")
