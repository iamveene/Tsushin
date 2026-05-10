"""Make agent_team_member_a2a_snapshot composite FK ON DELETE SET NULL.

The composite FK ``fk_agent_team_a2a_snapshot_tenant_permission``
(``tenant_id, permission_id``) was created without an ``ondelete`` clause in
migration ``0083``. PostgreSQL defaults that to ``NO ACTION``, which blocks
``DELETE`` on the parent ``agent_communication_permission`` row whenever any
snapshot still references it — surfacing as a 500 in
``DELETE /api/agent-communication/permissions/{id}``.

The single-column ``permission_id`` FK on the same table already uses
``ON DELETE SET NULL``; aligning the composite FK keeps both behaviors
consistent and unblocks permission deletion when team-membership snapshots are
present.

Revision ID: 0093
Revises: 0092
Create Date: 2026-05-10
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0093"
down_revision: Union[str, None] = "0092"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_TABLE = "agent_team_member_a2a_snapshot"
_FK_NAME = "fk_agent_team_a2a_snapshot_tenant_permission"
_TARGET_TABLE = "agent_communication_permission"


def _table_exists(name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    return name in inspector.get_table_names()


def _fk_exists(table: str, name: str) -> bool:
    inspector = sa.inspect(op.get_bind())
    if table not in inspector.get_table_names():
        return False
    return any(fk.get("name") == name for fk in inspector.get_foreign_keys(table))


def upgrade() -> None:
    if not _table_exists(_TABLE):
        return
    if _fk_exists(_TABLE, _FK_NAME):
        op.drop_constraint(_FK_NAME, _TABLE, type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        _TABLE,
        _TARGET_TABLE,
        ["tenant_id", "permission_id"],
        ["tenant_id", "id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    if not _table_exists(_TABLE):
        return
    if _fk_exists(_TABLE, _FK_NAME):
        op.drop_constraint(_FK_NAME, _TABLE, type_="foreignkey")
    op.create_foreign_key(
        _FK_NAME,
        _TABLE,
        _TARGET_TABLE,
        ["tenant_id", "permission_id"],
        ["tenant_id", "id"],
    )
