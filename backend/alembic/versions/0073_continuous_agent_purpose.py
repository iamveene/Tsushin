"""continuous_agent: add purpose + action_kind (v0.7.0-fix Phase 6)

User direction: "We create a continuous agent, select the option and
then what? what happens? Theres no option to customize define the purpose
and whatnot." This migration plumbs the missing fields. Both columns are
nullable to keep existing rows valid; the API layer enforces purpose as
required for new creates.

Revision ID: 0073
Revises: 0072
Create Date: 2026-04-28
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0073"
down_revision: Union[str, None] = "0072"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "continuous_agent" not in inspector.get_table_names():
        return

    cols = {c["name"] for c in inspector.get_columns("continuous_agent")}
    if "purpose" not in cols:
        op.add_column("continuous_agent", sa.Column("purpose", sa.Text(), nullable=True))
    if "action_kind" not in cols:
        op.add_column("continuous_agent", sa.Column("action_kind", sa.String(length=32), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "continuous_agent" not in inspector.get_table_names():
        return
    cols = {c["name"] for c in inspector.get_columns("continuous_agent")}
    if "action_kind" in cols:
        op.drop_column("continuous_agent", "action_kind")
    if "purpose" in cols:
        op.drop_column("continuous_agent", "purpose")
