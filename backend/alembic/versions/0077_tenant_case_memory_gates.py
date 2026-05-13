"""Add per-tenant case-memory gate columns (replaces TSN_CASE_MEMORY_ENABLED env var).

Revision ID: 0077
Revises: 0076
Create Date: 2026-04-29

v0.7.x — moves the case-memory feature gates out of environment variables
and into the tenant table so they can be toggled per-tenant via the UI
(SaaS configuration). Adds:

  - tenant.case_memory_enabled         BOOLEAN NOT NULL DEFAULT TRUE
  - tenant.case_memory_recap_enabled   BOOLEAN NOT NULL DEFAULT TRUE

Both default True so existing tenants get the feature out of the box. A
tenant admin can flip either off via the new tenant settings endpoint;
flipping case_memory_recap_enabled=false disables recap injection at
dispatch time globally for that tenant without touching individual
TriggerRecapConfig rows. flipping case_memory_enabled=false fully
disables the subsystem for the tenant.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0077"
down_revision: Union[str, None] = "0076"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(table: str, column: str) -> bool:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        result = bind.execute(
            sa.text(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name = :tbl AND column_name = :col"
            ),
            {"tbl": table, "col": column},
        ).first()
        return bool(result)
    # SQLite — pragma_table_info inspection.
    rows = bind.execute(sa.text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def upgrade() -> None:
    if not _column_exists("tenant", "case_memory_enabled"):
        op.add_column(
            "tenant",
            sa.Column(
                "case_memory_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
        )
    if not _column_exists("tenant", "case_memory_recap_enabled"):
        op.add_column(
            "tenant",
            sa.Column(
                "case_memory_recap_enabled",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("TRUE"),
            ),
        )


def downgrade() -> None:
    if _column_exists("tenant", "case_memory_recap_enabled"):
        op.drop_column("tenant", "case_memory_recap_enabled")
    if _column_exists("tenant", "case_memory_enabled"):
        op.drop_column("tenant", "case_memory_enabled")
