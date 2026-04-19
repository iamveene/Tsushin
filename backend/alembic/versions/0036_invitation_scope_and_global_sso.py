"""Invitation scope extensions + GlobalSSOConfig singleton

Two related schema changes that unblock the tenant+global invitation flow
and platform-wide Google SSO (see backend/api/routes_admin_invitations.py
and backend/api/routes_admin_sso.py):

1. ``user_invitation`` — extend to support both tenant-scoped invites and
   global-admin invites:
     - ``tenant_id`` and ``role_id`` become nullable (required only for
       tenant-scoped invites).
     - New column ``is_global_admin BOOLEAN NOT NULL DEFAULT false``.
     - New column ``auth_provider VARCHAR(16) NOT NULL DEFAULT 'local'``
       (``'local'`` or ``'google'``).
     - The old hard ``uq_tenant_email`` unique index is replaced by a
       PostgreSQL *partial* unique index that only covers pending invites
       (``WHERE accepted_at IS NULL``). This allows re-inviting an email
       after an old invite is accepted/cancelled, and keeps a distinct
       global-invite vs tenant-invite slot per email.
     - Two CHECK constraints enforce the shape invariants
       (``ck_invitation_scope`` and ``ck_invitation_auth_provider``).

2. ``global_sso_config`` — new singleton table for platform-wide Google SSO.
   Seeded with one empty row on upgrade so the CRUD endpoints never need
   upsert logic.

All ALTER/ADD paths are guarded with ``Inspector`` so re-running against a
DB that already has the columns is a no-op. This matches the idempotent
pattern used in migration ``0035_add_missing_provider_whatsapp_columns.py``.

Revision ID: 0036
Revises: 0035
Create Date: 2026-04-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0036'
down_revision: Union[str, None] = '0035'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_constraint(inspector, table: str, constraint_name: str) -> bool:
    try:
        for ck in inspector.get_check_constraints(table):
            if ck.get('name') == constraint_name:
                return True
    except NotImplementedError:
        # Some dialects don't support get_check_constraints — fall through.
        pass
    return False


def _has_index(inspector, table: str, index_name: str) -> bool:
    try:
        for ix in inspector.get_indexes(table):
            if ix.get('name') == index_name:
                return True
    except Exception:
        pass
    return False


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # ------------------------------------------------------------------
    # 1. user_invitation extensions
    # ------------------------------------------------------------------
    if inspector.has_table('user_invitation'):
        existing_cols = {c['name'] for c in inspector.get_columns('user_invitation')}

        # tenant_id / role_id → nullable (idempotent — alter is cheap if already nullable).
        op.alter_column('user_invitation', 'tenant_id',
                        existing_type=sa.String(length=50), nullable=True)
        op.alter_column('user_invitation', 'role_id',
                        existing_type=sa.Integer(), nullable=True)

        if 'is_global_admin' not in existing_cols:
            op.add_column(
                'user_invitation',
                sa.Column('is_global_admin', sa.Boolean(), server_default=sa.false(), nullable=False),
            )

        if 'auth_provider' not in existing_cols:
            op.add_column(
                'user_invitation',
                sa.Column('auth_provider', sa.String(length=16), server_default='local', nullable=False),
            )

        # Drop the old non-partial unique index.
        if _has_index(inspector, 'user_invitation', 'uq_tenant_email'):
            op.drop_index('uq_tenant_email', table_name='user_invitation')

        # Partial unique index — only enforce uniqueness on pending invites.
        if not _has_index(inspector, 'user_invitation', 'uq_invitation_tenant_email_pending'):
            op.execute(
                "CREATE UNIQUE INDEX uq_invitation_tenant_email_pending "
                "ON user_invitation (tenant_id, email) WHERE accepted_at IS NULL"
            )

        # CHECK constraints
        if not _has_constraint(inspector, 'user_invitation', 'ck_invitation_scope'):
            op.create_check_constraint(
                'ck_invitation_scope',
                'user_invitation',
                "(is_global_admin = TRUE AND tenant_id IS NULL AND role_id IS NULL) OR "
                "(is_global_admin = FALSE AND tenant_id IS NOT NULL AND role_id IS NOT NULL)",
            )
        if not _has_constraint(inspector, 'user_invitation', 'ck_invitation_auth_provider'):
            op.create_check_constraint(
                'ck_invitation_auth_provider',
                'user_invitation',
                "auth_provider IN ('local', 'google')",
            )

    # ------------------------------------------------------------------
    # 2. global_sso_config table + seed singleton row
    # ------------------------------------------------------------------
    if not inspector.has_table('global_sso_config'):
        op.create_table(
            'global_sso_config',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('google_sso_enabled', sa.Boolean(), server_default=sa.false(), nullable=True),
            sa.Column('google_client_id', sa.String(length=255), nullable=True),
            sa.Column('google_client_secret_encrypted', sa.Text(), nullable=True),
            sa.Column('allowed_domains', sa.Text(), nullable=True),
            sa.Column('auto_provision_users', sa.Boolean(), server_default=sa.false(), nullable=True),
            sa.Column('default_role_id', sa.Integer(), sa.ForeignKey('role.id'), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now(), nullable=True),
        )

    # Seed one singleton row (idempotent — only if empty).
    op.execute(
        "INSERT INTO global_sso_config (google_sso_enabled, auto_provision_users) "
        "SELECT FALSE, FALSE WHERE NOT EXISTS (SELECT 1 FROM global_sso_config)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Drop global_sso_config first (it has no dependents).
    if inspector.has_table('global_sso_config'):
        op.drop_table('global_sso_config')

    if inspector.has_table('user_invitation'):
        existing_cols = {c['name'] for c in inspector.get_columns('user_invitation')}

        # Drop CHECK constraints.
        if _has_constraint(inspector, 'user_invitation', 'ck_invitation_auth_provider'):
            op.drop_constraint('ck_invitation_auth_provider', 'user_invitation', type_='check')
        if _has_constraint(inspector, 'user_invitation', 'ck_invitation_scope'):
            op.drop_constraint('ck_invitation_scope', 'user_invitation', type_='check')

        # Drop partial unique index, restore old non-partial one.
        if _has_index(inspector, 'user_invitation', 'uq_invitation_tenant_email_pending'):
            op.execute("DROP INDEX IF EXISTS uq_invitation_tenant_email_pending")
        if not _has_index(inspector, 'user_invitation', 'uq_tenant_email'):
            op.create_index('uq_tenant_email', 'user_invitation', ['tenant_id', 'email'], unique=True)

        # Drop the new columns.
        if 'auth_provider' in existing_cols:
            op.drop_column('user_invitation', 'auth_provider')
        if 'is_global_admin' in existing_cols:
            op.drop_column('user_invitation', 'is_global_admin')

        # Restore NOT NULL on tenant_id / role_id. This will fail if any rows
        # have NULLs (i.e. global-admin invites exist) — callers should have
        # already dropped or migrated those rows before downgrade.
        op.alter_column('user_invitation', 'role_id',
                        existing_type=sa.Integer(), nullable=False)
        op.alter_column('user_invitation', 'tenant_id',
                        existing_type=sa.String(length=50), nullable=False)
