"""Add Sentinel profile override to Agent Teams.

Revision ID: 0085
Revises: 0084
Create Date: 2026-05-05

Adds an optional team-level Sentinel profile reference used by the Team
Builder API and runtime Sentinel analysis.
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0085"
down_revision: Union[str, None] = "0084"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _inspector() -> sa.Inspector:
    return sa.inspect(op.get_bind())


def _has_table(table_name: str) -> bool:
    return table_name in _inspector().get_table_names()


def _has_column(table_name: str, column_name: str) -> bool:
    if not _has_table(table_name):
        return False
    return any(col["name"] == column_name for col in _inspector().get_columns(table_name))


def _index_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {idx["name"] for idx in _inspector().get_indexes(table_name)}


def _fk_names(table_name: str) -> set[str]:
    if not _has_table(table_name):
        return set()
    return {fk["name"] for fk in _inspector().get_foreign_keys(table_name) if fk.get("name")}


def _add_column_if_missing(table_name: str, column: sa.Column) -> None:
    if _has_table(table_name) and not _has_column(table_name, column.name):
        op.add_column(table_name, column)


def _drop_column_if_exists(table_name: str, column_name: str) -> None:
    if _has_table(table_name) and _has_column(table_name, column_name):
        op.drop_column(table_name, column_name)


def _create_index_if_missing(name: str, table_name: str, columns: list[str]) -> None:
    if _has_table(table_name) and name not in _index_names(table_name):
        op.create_index(name, table_name, columns)


def _drop_index_if_exists(name: str, table_name: str) -> None:
    if _has_table(table_name) and name in _index_names(table_name):
        op.drop_index(name, table_name=table_name)


def _create_fk_if_missing(
    name: str,
    source_table: str,
    referent_table: str,
    local_cols: list[str],
    remote_cols: list[str],
    *,
    ondelete: str | None = None,
) -> None:
    if _has_table(source_table) and _has_table(referent_table) and name not in _fk_names(source_table):
        op.create_foreign_key(
            name,
            source_table,
            referent_table,
            local_cols,
            remote_cols,
            ondelete=ondelete,
        )


def _drop_fk_if_exists(name: str, table_name: str) -> None:
    if _has_table(table_name) and name in _fk_names(table_name):
        op.drop_constraint(name, table_name, type_="foreignkey")


def upgrade() -> None:
    if not _has_table("agent_team"):
        return

    _add_column_if_missing("agent_team", sa.Column("sentinel_profile_id", sa.Integer(), nullable=True))
    _create_index_if_missing("ix_agent_team_sentinel_profile_id", "agent_team", ["sentinel_profile_id"])
    _create_fk_if_missing(
        "fk_agent_team_sentinel_profile",
        "agent_team",
        "sentinel_profile",
        ["sentinel_profile_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    if not _has_table("agent_team"):
        return

    _drop_fk_if_exists("fk_agent_team_sentinel_profile", "agent_team")
    _drop_index_if_exists("ix_agent_team_sentinel_profile_id", "agent_team")
    _drop_column_if_exists("agent_team", "sentinel_profile_id")
