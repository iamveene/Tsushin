"""Add provider instance binding to Sentinel config and profiles.

Revision ID: 0094
Revises: 0093
Create Date: 2026-05-18
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0094"
down_revision: Union[str, None] = "0093"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_BINDINGS = (
    (
        "sentinel_config",
        "provider_instance_id",
        "fk_sentinel_config_provider_instance",
        "idx_sentinel_config_provider_instance_id",
    ),
    (
        "sentinel_profile",
        "provider_instance_id",
        "fk_sentinel_profile_provider_instance",
        "idx_sentinel_profile_provider_instance_id",
    ),
)


def _inspector():
    return sa.inspect(op.get_bind())


def _table_exists(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _column_exists(table_name: str, column_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(col["name"] == column_name for col in _inspector().get_columns(table_name))


def _fk_exists(table_name: str, fk_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(fk.get("name") == fk_name for fk in _inspector().get_foreign_keys(table_name))


def _index_exists(table_name: str, index_name: str) -> bool:
    if not _table_exists(table_name):
        return False
    return any(index.get("name") == index_name for index in _inspector().get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("provider_instance"):
        return

    for table_name, column_name, fk_name, index_name in _BINDINGS:
        if not _table_exists(table_name):
            continue
        if not _column_exists(table_name, column_name):
            op.add_column(table_name, sa.Column(column_name, sa.Integer(), nullable=True))
        if not _fk_exists(table_name, fk_name):
            op.create_foreign_key(
                fk_name,
                table_name,
                "provider_instance",
                [column_name],
                ["id"],
                ondelete="SET NULL",
            )
        if not _index_exists(table_name, index_name):
            op.create_index(index_name, table_name, [column_name])


def downgrade() -> None:
    for table_name, column_name, fk_name, index_name in reversed(_BINDINGS):
        if not _table_exists(table_name):
            continue
        if _index_exists(table_name, index_name):
            op.drop_index(index_name, table_name=table_name)
        if _fk_exists(table_name, fk_name):
            op.drop_constraint(fk_name, table_name, type_="foreignkey")
        if _column_exists(table_name, column_name):
            op.drop_column(table_name, column_name)
