"""v0.6.0 Remote Access: Cloudflare Tunnel config table + tenant entitlement.

Adds the system-wide remote_access_config table (single row), the
remote_access_encryption_key column on the config table, and the
remote_access_enabled column on the tenant table.

Revision ID: 0031
Revises: 0030
"""
from alembic import op
import sqlalchemy as sa

from models import get_remote_access_proxy_target_url


revision = '0031'
down_revision = '0030'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    default_target_url = get_remote_access_proxy_target_url()

    # 1. remote_access_config table
    existing_tables = set(inspector.get_table_names())
    if 'remote_access_config' not in existing_tables:
        op.create_table(
            'remote_access_config',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('enabled', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('mode', sa.String(length=20), nullable=False, server_default='quick'),
            sa.Column('autostart', sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column('protocol', sa.String(length=10), nullable=False, server_default='auto'),
            sa.Column('tunnel_token_encrypted', sa.Text(), nullable=True),
            sa.Column('tunnel_hostname', sa.String(length=255), nullable=True),
            sa.Column('tunnel_dns_target', sa.String(length=255), nullable=True),
            sa.Column('target_url', sa.String(length=255), nullable=False, server_default=sa.text(f"'{default_target_url}'")),
            sa.Column('last_started_at', sa.DateTime(), nullable=True),
            sa.Column('last_stopped_at', sa.DateTime(), nullable=True),
            sa.Column('last_error', sa.Text(), nullable=True),
            sa.Column('updated_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )
        # Seed the single config row
        op.execute(
            "INSERT INTO remote_access_config (id, enabled, mode, autostart, protocol, target_url) "
            f"VALUES (1, false, 'quick', false, 'auto', '{default_target_url}')"
        )

    # 2. config.remote_access_encryption_key
    config_columns = {c['name'] for c in inspector.get_columns('config')}
    if 'remote_access_encryption_key' not in config_columns:
        op.add_column(
            'config',
            sa.Column('remote_access_encryption_key', sa.String(length=500), nullable=True),
        )

    # 3. tenant.remote_access_enabled + index
    tenant_columns = {c['name'] for c in inspector.get_columns('tenant')}
    if 'remote_access_enabled' not in tenant_columns:
        op.add_column(
            'tenant',
            sa.Column(
                'remote_access_enabled',
                sa.Boolean(),
                nullable=False,
                server_default=sa.false(),
            ),
        )
        existing_indexes = {idx['name'] for idx in inspector.get_indexes('tenant')}
        if 'ix_tenant_remote_access_enabled' not in existing_indexes:
            op.create_index(
                'ix_tenant_remote_access_enabled',
                'tenant',
                ['remote_access_enabled'],
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    tenant_indexes = {idx['name'] for idx in inspector.get_indexes('tenant')}
    if 'ix_tenant_remote_access_enabled' in tenant_indexes:
        op.drop_index('ix_tenant_remote_access_enabled', table_name='tenant')

    tenant_columns = {c['name'] for c in inspector.get_columns('tenant')}
    if 'remote_access_enabled' in tenant_columns:
        op.drop_column('tenant', 'remote_access_enabled')

    config_columns = {c['name'] for c in inspector.get_columns('config')}
    if 'remote_access_encryption_key' in config_columns:
        op.drop_column('config', 'remote_access_encryption_key')

    existing_tables = set(inspector.get_table_names())
    if 'remote_access_config' in existing_tables:
        op.drop_table('remote_access_config')
