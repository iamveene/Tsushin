"""Add message_queue table for async message processing.

Supports playground, WhatsApp, and Telegram channels with
priority queuing, retry logic, and dead-letter handling.

Revision ID: 0003
Revises: 0002
Create Date: 2026-03-27
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create message_queue table with all columns and indexes."""
    # Skip if table already exists (created by 0001 via metadata.create_all)
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'message_queue' in inspector.get_table_names():
        return

    op.create_table(
        'message_queue',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('tenant_id', sa.String(50), nullable=False),
        sa.Column('channel', sa.String(20), nullable=False),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('agent_id', sa.Integer(), sa.ForeignKey('agent.id'), nullable=False),
        sa.Column('sender_key', sa.String(255), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('priority', sa.Integer(), server_default='0'),
        sa.Column('retry_count', sa.Integer(), server_default='0'),
        sa.Column('max_retries', sa.Integer(), server_default='3'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('queued_at', sa.DateTime(), server_default=sa.func.now()),
        sa.Column('processing_started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )

    # Single-column indexes
    op.create_index('ix_mq_tenant_id', 'message_queue', ['tenant_id'])
    op.create_index('ix_mq_channel', 'message_queue', ['channel'])
    op.create_index('ix_mq_status', 'message_queue', ['status'])
    op.create_index('ix_mq_agent_id', 'message_queue', ['agent_id'])
    op.create_index('ix_mq_queued_at', 'message_queue', ['queued_at'])

    # Composite indexes for common query patterns
    op.create_index('ix_mq_tenant_agent_status', 'message_queue', ['tenant_id', 'agent_id', 'status'])
    op.create_index('ix_mq_pending_priority', 'message_queue', ['status', 'priority', 'queued_at'])


def downgrade() -> None:
    """Drop message_queue table."""
    op.drop_table('message_queue')
