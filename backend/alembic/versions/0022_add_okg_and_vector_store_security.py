"""
v0.6.0 Items 3+4+5: OKG Memory audit log, Sentinel vector_store_poisoning
detection columns, and VectorStoreInstance security_config.

Revision ID: 0022
Revises: 0021
"""
from alembic import op
import sqlalchemy as sa

revision = '0022'
down_revision = '0021'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # --- 1. Create okg_memory_audit_log table (Item 3) ---
    if 'okg_memory_audit_log' not in existing_tables:
        op.create_table(
            'okg_memory_audit_log',
            sa.Column('id', sa.Integer(), primary_key=True),
            sa.Column('tenant_id', sa.String(50), nullable=False, index=True),
            sa.Column('agent_id', sa.Integer(), nullable=False),
            sa.Column('user_id', sa.String(200), nullable=False),
            sa.Column('action', sa.String(20), nullable=False),  # store|recall|forget|auto_capture
            sa.Column('doc_id', sa.String(32), nullable=True, index=True),
            sa.Column('memory_type', sa.String(20), nullable=True),  # fact|episodic|semantic|procedural|belief
            sa.Column('subject_entity', sa.String(200), nullable=True),
            sa.Column('relation', sa.String(100), nullable=True),
            sa.Column('confidence', sa.Float(), nullable=True),
            sa.Column('memguard_blocked', sa.Boolean(), server_default='false', nullable=False),
            sa.Column('memguard_reason', sa.String(500), nullable=True),
            sa.Column('source', sa.String(20), nullable=True),  # tool_call|auto_capture|import
            sa.Column('result_count', sa.Integer(), nullable=True),
            sa.Column('latency_ms', sa.Integer(), nullable=True),
            sa.Column('error', sa.Text(), nullable=True),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index('idx_okg_audit_tenant_agent', 'okg_memory_audit_log', ['tenant_id', 'agent_id'])
        op.create_index('idx_okg_audit_created', 'okg_memory_audit_log', ['created_at'])

    # --- 2. Add detect_vector_store_poisoning to sentinel_config (Item 5) ---
    sentinel_columns = {col['name'] for col in inspector.get_columns('sentinel_config')}

    if 'detect_vector_store_poisoning' not in sentinel_columns:
        op.add_column('sentinel_config', sa.Column(
            'detect_vector_store_poisoning', sa.Boolean(),
            server_default='true', nullable=False,
        ))

    if 'vector_store_poisoning_prompt' not in sentinel_columns:
        op.add_column('sentinel_config', sa.Column(
            'vector_store_poisoning_prompt', sa.Text(), nullable=True,
        ))

    # --- 3. Add vector store access controls to sentinel_agent_config (Item 5) ---
    agent_config_columns = {col['name'] for col in inspector.get_columns('sentinel_agent_config')}

    if 'vector_store_access_enabled' not in agent_config_columns:
        op.add_column('sentinel_agent_config', sa.Column(
            'vector_store_access_enabled', sa.Boolean(), nullable=True,
        ))

    if 'vector_store_allowed_configs' not in agent_config_columns:
        op.add_column('sentinel_agent_config', sa.Column(
            'vector_store_allowed_configs', sa.JSON(), nullable=True,
        ))

    # --- 4. Add security_config to vector_store_instance (Item 4) ---
    vsi_columns = {col['name'] for col in inspector.get_columns('vector_store_instance')}

    if 'security_config' not in vsi_columns:
        op.add_column('vector_store_instance', sa.Column(
            'security_config', sa.JSON(), server_default='{}', nullable=False,
        ))


def downgrade():
    # vector_store_instance
    op.drop_column('vector_store_instance', 'security_config')

    # sentinel_agent_config
    op.drop_column('sentinel_agent_config', 'vector_store_allowed_configs')
    op.drop_column('sentinel_agent_config', 'vector_store_access_enabled')

    # sentinel_config
    op.drop_column('sentinel_config', 'vector_store_poisoning_prompt')
    op.drop_column('sentinel_config', 'detect_vector_store_poisoning')

    # okg_memory_audit_log
    op.drop_index('idx_okg_audit_created', table_name='okg_memory_audit_log')
    op.drop_index('idx_okg_audit_tenant_agent', table_name='okg_memory_audit_log')
    op.drop_table('okg_memory_audit_log')
