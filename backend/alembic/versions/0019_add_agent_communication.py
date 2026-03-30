"""
v0.6.0 Item 15: Add Agent-to-Agent Communication tables.

Creates three tables for inter-agent communication:
- agent_communication_permission: Controls which agents can communicate
- agent_communication_session: Tracks complete inter-agent exchanges
- agent_communication_message: Individual messages within sessions

Revision ID: 0019
Revises: 0018
"""
from alembic import op
import sqlalchemy as sa

revision = '0019'
down_revision = '0018'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # --- agent_communication_permission table ---
    if 'agent_communication_permission' not in existing_tables:
        op.create_table(
            'agent_communication_permission',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.String(50), nullable=False),
            sa.Column('source_agent_id', sa.Integer(), sa.ForeignKey('agent.id', ondelete='CASCADE'), nullable=False),
            sa.Column('target_agent_id', sa.Integer(), sa.ForeignKey('agent.id', ondelete='CASCADE'), nullable=False),
            sa.Column('is_enabled', sa.Boolean(), server_default='true'),
            sa.Column('max_depth', sa.Integer(), server_default='3'),
            sa.Column('rate_limit_rpm', sa.Integer(), server_default='30'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('source_agent_id', 'target_agent_id', name='uq_agent_comm_perm_pair'),
        )
        op.create_index('ix_agent_comm_perm_tenant', 'agent_communication_permission', ['tenant_id'])
        op.create_index('ix_agent_comm_perm_source', 'agent_communication_permission', ['source_agent_id'])
        op.create_index('ix_agent_comm_perm_target', 'agent_communication_permission', ['target_agent_id'])

    # --- agent_communication_session table ---
    if 'agent_communication_session' not in existing_tables:
        op.create_table(
            'agent_communication_session',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.String(50), nullable=False),
            sa.Column('initiator_agent_id', sa.Integer(), sa.ForeignKey('agent.id', ondelete='CASCADE'), nullable=False),
            sa.Column('target_agent_id', sa.Integer(), sa.ForeignKey('agent.id', ondelete='CASCADE'), nullable=False),
            sa.Column('original_sender_key', sa.String(255), nullable=True),
            sa.Column('original_message_preview', sa.String(200), nullable=True),
            sa.Column('session_type', sa.String(20), server_default='sync'),
            sa.Column('status', sa.String(20), server_default='pending'),
            sa.Column('depth', sa.Integer(), server_default='0'),
            sa.Column('max_depth', sa.Integer(), server_default='3'),
            sa.Column('timeout_seconds', sa.Integer(), server_default='30'),
            sa.Column('total_messages', sa.Integer(), server_default='0'),
            sa.Column('error_text', sa.Text(), nullable=True),
            sa.Column('parent_session_id', sa.Integer(), sa.ForeignKey('agent_communication_session.id', ondelete='SET NULL'), nullable=True),
            sa.Column('started_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('completed_at', sa.DateTime(), nullable=True),
        )
        op.create_index('ix_agent_comm_session_tenant', 'agent_communication_session', ['tenant_id'])
        op.create_index('ix_agent_comm_session_tenant_status', 'agent_communication_session', ['tenant_id', 'status'])
        op.create_index('ix_agent_comm_session_initiator', 'agent_communication_session', ['initiator_agent_id', 'started_at'])
        op.create_index('ix_agent_comm_session_target', 'agent_communication_session', ['target_agent_id'])

    # --- agent_communication_message table ---
    if 'agent_communication_message' not in existing_tables:
        op.create_table(
            'agent_communication_message',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('session_id', sa.Integer(), sa.ForeignKey('agent_communication_session.id', ondelete='CASCADE'), nullable=False),
            sa.Column('from_agent_id', sa.Integer(), sa.ForeignKey('agent.id', ondelete='CASCADE'), nullable=False),
            sa.Column('to_agent_id', sa.Integer(), sa.ForeignKey('agent.id', ondelete='CASCADE'), nullable=False),
            sa.Column('direction', sa.String(10), nullable=False),
            sa.Column('message_content', sa.Text(), nullable=False),
            sa.Column('message_preview', sa.String(500), nullable=True),
            sa.Column('context_transferred', sa.JSON(), nullable=True),
            sa.Column('model_used', sa.String(100), nullable=True),
            sa.Column('token_usage_json', sa.JSON(), nullable=True),
            sa.Column('execution_time_ms', sa.Integer(), nullable=True),
            sa.Column('sentinel_analyzed', sa.Boolean(), server_default='false'),
            sa.Column('sentinel_result', sa.JSON(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
        )
        op.create_index('ix_agent_comm_msg_session', 'agent_communication_message', ['session_id', 'created_at'])


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()
    for table in ('agent_communication_message', 'agent_communication_session', 'agent_communication_permission'):
        if table in existing_tables:
            op.drop_table(table)
