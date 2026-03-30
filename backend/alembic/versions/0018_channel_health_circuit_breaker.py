"""
v0.6.0 Item 38: Channel Health Monitor with Circuit Breakers

Creates channel_health_event and channel_alert_config tables.
Adds circuit breaker state columns to all channel instance models
(WhatsApp, Telegram, Slack, Discord).

Revision ID: 0018
Revises: 0017
"""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def _add_cb_columns(table_name, inspector):
    """Add circuit breaker columns to a channel instance table."""
    cols = [c['name'] for c in inspector.get_columns(table_name)]

    if 'circuit_breaker_state' not in cols:
        op.add_column(table_name,
                      sa.Column('circuit_breaker_state', sa.String(20), server_default='closed', nullable=True))
    if 'circuit_breaker_opened_at' not in cols:
        op.add_column(table_name,
                      sa.Column('circuit_breaker_opened_at', sa.DateTime(), nullable=True))
    if 'circuit_breaker_failure_count' not in cols:
        op.add_column(table_name,
                      sa.Column('circuit_breaker_failure_count', sa.Integer(), server_default='0', nullable=True))


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # --- Create channel_health_event table ---
    if 'channel_health_event' not in tables:
        op.create_table(
            'channel_health_event',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.String(50), nullable=False, index=True),
            sa.Column('channel_type', sa.String(20), nullable=False),
            sa.Column('instance_id', sa.Integer(), nullable=False, index=True),
            sa.Column('event_type', sa.String(50), nullable=True),
            sa.Column('old_state', sa.String(20), nullable=False),
            sa.Column('new_state', sa.String(20), nullable=False),
            sa.Column('reason', sa.Text(), nullable=True),
            sa.Column('health_status', sa.String(20), nullable=True),
            sa.Column('latency_ms', sa.Float(), nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True, index=True),
        )
        op.create_index('ix_health_event_tenant_channel', 'channel_health_event',
                        ['tenant_id', 'channel_type'])
        op.create_index('ix_health_event_instance_created', 'channel_health_event',
                        ['instance_id', 'created_at'])

    # --- Create channel_alert_config table ---
    if 'channel_alert_config' not in tables:
        op.create_table(
            'channel_alert_config',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.String(50), nullable=False, unique=True, index=True),
            sa.Column('webhook_url', sa.String(500), nullable=True),
            sa.Column('email_recipients', sa.JSON(), nullable=True),
            sa.Column('alert_on_open', sa.Boolean(), server_default='true', nullable=True),
            sa.Column('alert_on_recovery', sa.Boolean(), server_default='true', nullable=True),
            sa.Column('cooldown_seconds', sa.Integer(), server_default='300', nullable=True),
            sa.Column('is_enabled', sa.Boolean(), server_default='true', nullable=True),
            sa.Column('created_at', sa.DateTime(), nullable=True),
            sa.Column('updated_at', sa.DateTime(), nullable=True),
        )

    # --- Add circuit breaker columns to WhatsApp MCP instances ---
    if 'whatsapp_mcp_instance' in tables:
        _add_cb_columns('whatsapp_mcp_instance', inspector)

    # --- Add circuit breaker columns to Telegram bot instances ---
    if 'telegram_bot_instance' in tables:
        _add_cb_columns('telegram_bot_instance', inspector)

    # --- Add circuit breaker + health columns to Slack integrations ---
    if 'slack_integration' in tables:
        cols = [c['name'] for c in inspector.get_columns('slack_integration')]
        if 'health_status' not in cols:
            op.add_column('slack_integration',
                          sa.Column('health_status', sa.String(20), server_default='unknown', nullable=True))
        if 'last_health_check' not in cols:
            op.add_column('slack_integration',
                          sa.Column('last_health_check', sa.DateTime(), nullable=True))
        _add_cb_columns('slack_integration', inspector)

    # --- Add circuit breaker + health columns to Discord integrations ---
    if 'discord_integration' in tables:
        cols = [c['name'] for c in inspector.get_columns('discord_integration')]
        if 'health_status' not in cols:
            op.add_column('discord_integration',
                          sa.Column('health_status', sa.String(20), server_default='unknown', nullable=True))
        if 'last_health_check' not in cols:
            op.add_column('discord_integration',
                          sa.Column('last_health_check', sa.DateTime(), nullable=True))
        _add_cb_columns('discord_integration', inspector)


def downgrade():
    op.drop_table('channel_health_event')
    op.drop_table('channel_alert_config')

    for table in ['whatsapp_mcp_instance', 'telegram_bot_instance', 'slack_integration', 'discord_integration']:
        op.drop_column(table, 'circuit_breaker_state')
        op.drop_column(table, 'circuit_breaker_opened_at')
        op.drop_column(table, 'circuit_breaker_failure_count')

    for table in ['slack_integration', 'discord_integration']:
        op.drop_column(table, 'health_status')
        op.drop_column(table, 'last_health_check')
