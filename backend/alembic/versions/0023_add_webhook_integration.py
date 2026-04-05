"""
v0.6.0: Add webhook_integration table and agent binding column.

Creates the webhook_integration table for managing per-tenant HTTP webhook
channel integrations (bidirectional HMAC-signed), and adds
webhook_integration_id to the agent table for binding an agent to a
specific webhook integration.

Revision ID: 0023
Revises: 0022
"""
from alembic import op
import sqlalchemy as sa

revision = '0023'
down_revision = '0022'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # --- webhook_integration table ---
    if 'webhook_integration' not in existing_tables:
        op.create_table(
            'webhook_integration',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.String(50), sa.ForeignKey('tenant.id'), nullable=False),
            sa.Column('integration_name', sa.String(100), nullable=False),
            # Inbound identity
            sa.Column('api_secret_encrypted', sa.Text(), nullable=False),
            sa.Column('api_secret_preview', sa.String(16), nullable=False),
            # Outbound callback
            sa.Column('callback_url', sa.String(500), nullable=True),
            sa.Column('callback_enabled', sa.Boolean(), server_default=sa.text('false')),
            # Defense layers
            sa.Column('ip_allowlist_json', sa.Text(), nullable=True),
            sa.Column('rate_limit_rpm', sa.Integer(), server_default='30'),
            sa.Column('max_payload_bytes', sa.Integer(), server_default='1048576'),
            # Status
            sa.Column('is_active', sa.Boolean(), server_default=sa.text('true')),
            sa.Column('status', sa.String(20), server_default='active'),
            sa.Column('health_status', sa.String(20), server_default='unknown'),
            sa.Column('last_health_check', sa.DateTime(), nullable=True),
            sa.Column('last_activity_at', sa.DateTime(), nullable=True),
            # Circuit breaker
            sa.Column('circuit_breaker_state', sa.String(20), server_default='closed'),
            sa.Column('circuit_breaker_opened_at', sa.DateTime(), nullable=True),
            sa.Column('circuit_breaker_failure_count', sa.Integer(), server_default='0'),
            sa.Column('error_message', sa.Text(), nullable=True),
            # Retry
            sa.Column('max_retry_attempts', sa.Integer(), server_default='3'),
            sa.Column('retry_timeout_seconds', sa.Integer(), server_default='300'),
            # Audit
            sa.Column('created_by', sa.Integer(), sa.ForeignKey('user.id'), nullable=False),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('idx_webhook_integration_tenant', 'webhook_integration', ['tenant_id'])
        op.create_index('idx_webhook_integration_status', 'webhook_integration', ['status'])

    # --- agent.webhook_integration_id ---
    if 'agent' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('agent')]
        if 'webhook_integration_id' not in cols:
            op.add_column(
                'agent',
                sa.Column(
                    'webhook_integration_id',
                    sa.Integer(),
                    sa.ForeignKey('webhook_integration.id', ondelete='SET NULL'),
                    nullable=True,
                ),
            )

    # --- config.webhook_encryption_key ---
    if 'config' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('config')]
        if 'webhook_encryption_key' not in cols:
            op.add_column(
                'config',
                sa.Column('webhook_encryption_key', sa.String(500), nullable=True),
            )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'agent' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('agent')]
        if 'webhook_integration_id' in cols:
            op.drop_column('agent', 'webhook_integration_id')

    if 'config' in existing_tables:
        cols = [c['name'] for c in inspector.get_columns('config')]
        if 'webhook_encryption_key' in cols:
            op.drop_column('config', 'webhook_encryption_key')

    if 'webhook_integration' in existing_tables:
        op.drop_index('idx_webhook_integration_status', table_name='webhook_integration')
        op.drop_index('idx_webhook_integration_tenant', table_name='webhook_integration')
        op.drop_table('webhook_integration')
