"""Add browser session profile storage to browser automation integrations.

Revision ID: 0090
Revises: 0089
Create Date: 2026-05-06
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0090"
down_revision: Union[str, None] = "0089"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    cols = _columns("browser_automation_integration")
    if not cols:
        return

    if "session_profile_name" not in cols:
        op.add_column("browser_automation_integration", sa.Column("session_profile_name", sa.String(length=120), nullable=True))
    if "storage_state_encrypted" not in cols:
        op.add_column("browser_automation_integration", sa.Column("storage_state_encrypted", sa.Text(), nullable=True))
    if "storage_state_imported_at" not in cols:
        op.add_column("browser_automation_integration", sa.Column("storage_state_imported_at", sa.DateTime(), nullable=True))
    if "storage_state_summary_json" not in cols:
        op.add_column("browser_automation_integration", sa.Column("storage_state_summary_json", sa.Text(), nullable=True))

    if "idx_browser_automation_tenant_profile" not in _indexes("browser_automation_integration"):
        op.create_index(
            "idx_browser_automation_tenant_profile",
            "browser_automation_integration",
            ["session_profile_name"],
        )


def downgrade() -> None:
    cols = _columns("browser_automation_integration")
    if not cols:
        return

    if "idx_browser_automation_tenant_profile" in _indexes("browser_automation_integration"):
        op.drop_index("idx_browser_automation_tenant_profile", table_name="browser_automation_integration")
    for column in (
        "storage_state_summary_json",
        "storage_state_imported_at",
        "storage_state_encrypted",
        "session_profile_name",
    ):
        if column in _columns("browser_automation_integration"):
            op.drop_column("browser_automation_integration", column)
