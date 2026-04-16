"""
v0.6.0 Item 34: Add Discord integration table and agent binding column.

Creates the discord_integration table for managing Discord bot connections
per tenant, and adds discord_integration_id to the agents table.

Revision ID: 0016
Revises: 0015
"""
from alembic import op
import sqlalchemy as sa

revision = '0016'
down_revision = '0015'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # --- discord_integration table ---
    if 'discord_integration' not in existing_tables:
        op.create_table(
            'discord_integration',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.String(100), nullable=False),
            sa.Column('bot_token_encrypted', sa.Text(), nullable=False),
            sa.Column('application_id', sa.String(50), nullable=False),
            sa.Column('bot_user_id', sa.String(50), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
            sa.Column('status', sa.String(20), server_default='inactive'),
            sa.Column('dm_policy', sa.String(20), server_default='allowlist'),
            sa.Column('allowed_guilds', sa.JSON(), nullable=True),
            sa.Column('guild_channel_config', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_discord_integration_tenant', 'discord_integration', ['tenant_id'])
        op.create_index('idx_discord_integration_status', 'discord_integration', ['status'])

    # --- agents.discord_integration_id ---
    if 'agent' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('agent')]
        if 'discord_integration_id' not in cols:
            op.add_column('agent',
                          sa.Column('discord_integration_id', sa.Integer(), nullable=True))

    # --- config.discord_encryption_key ---
    if 'config' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('config')]
        if 'discord_encryption_key' not in cols:
            op.add_column('config',
                          sa.Column('discord_encryption_key', sa.String(500), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'agent' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('agent')]
        if 'discord_integration_id' in cols:
            op.drop_column('agent', 'discord_integration_id')

    if 'config' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('config')]
        if 'discord_encryption_key' in cols:
            op.drop_column('config', 'discord_encryption_key')

    if 'discord_integration' in existing_tables:
        op.drop_index('idx_discord_integration_status', table_name='discord_integration')
        op.drop_index('idx_discord_integration_tenant', table_name='discord_integration')
        op.drop_table('discord_integration')
