"""
v0.6.0 Item 33: Add Slack integration table and agent binding column.

Creates the slack_integration table for managing Slack workspace connections
per tenant, and adds slack_integration_id to the agents table.

Revision ID: 0015
Revises: 0014
"""
from alembic import op
import sqlalchemy as sa

revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # --- slack_integration table ---
    if 'slack_integration' not in existing_tables:
        op.create_table(
            'slack_integration',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.String(100), nullable=False),
            sa.Column('workspace_id', sa.String(50), nullable=False),
            sa.Column('workspace_name', sa.String(200), nullable=True),
            sa.Column('bot_token_encrypted', sa.Text(), nullable=False),
            sa.Column('app_token_encrypted', sa.Text(), nullable=True),
            sa.Column('signing_secret_encrypted', sa.Text(), nullable=True),
            sa.Column('mode', sa.String(20), server_default='socket'),
            sa.Column('bot_user_id', sa.String(50), nullable=True),
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
            sa.Column('status', sa.String(20), server_default='inactive'),
            sa.Column('dm_policy', sa.String(20), server_default='allowlist'),
            sa.Column('allowed_channels', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )
        op.create_index('idx_slack_integration_tenant', 'slack_integration', ['tenant_id'])
        op.create_index('idx_slack_integration_status', 'slack_integration', ['status'])

    # --- agents.slack_integration_id ---
    if 'agent' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('agent')]
        if 'slack_integration_id' not in cols:
            op.add_column('agent',
                          sa.Column('slack_integration_id', sa.Integer(), nullable=True))

    # --- config.slack_encryption_key ---
    if 'config' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('config')]
        if 'slack_encryption_key' not in cols:
            op.add_column('config',
                          sa.Column('slack_encryption_key', sa.String(500), nullable=True))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'agent' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('agent')]
        if 'slack_integration_id' in cols:
            op.drop_column('agent', 'slack_integration_id')

    if 'config' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('config')]
        if 'slack_encryption_key' in cols:
            op.drop_column('config', 'slack_encryption_key')

    if 'slack_integration' in existing_tables:
        op.drop_index('idx_slack_integration_status', table_name='slack_integration')
        op.drop_index('idx_slack_integration_tenant', table_name='slack_integration')
        op.drop_table('slack_integration')
