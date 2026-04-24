"""Add managed action config to continuous subscriptions.

Revision ID: 0060
Revises: 0055
Create Date: 2026-04-24
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0060"
down_revision: Union[str, None] = "0055"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_column(table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return False
    return any(col["name"] == column_name for col in inspector.get_columns(table_name))


def upgrade() -> None:
    if not _has_column("continuous_subscription", "action_config"):
        op.add_column("continuous_subscription", sa.Column("action_config", sa.JSON(), nullable=True))


def downgrade() -> None:
    if _has_column("continuous_subscription", "action_config"):
        op.drop_column("continuous_subscription", "action_config")
