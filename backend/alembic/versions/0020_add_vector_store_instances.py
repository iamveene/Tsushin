"""
v0.6.1 Item 1: Add Vector Store Instance table and Agent FK.

Creates:
- vector_store_instance: External vector database connection configs
- Adds vector_store_instance_id FK and vector_store_mode to agent table

Revision ID: 0020
Revises: 0019
"""
from alembic import op
import sqlalchemy as sa

revision = '0020'
down_revision = '0019'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    # --- vector_store_instance table ---
    if 'vector_store_instance' not in existing_tables:
        op.create_table(
            'vector_store_instance',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('tenant_id', sa.String(50), nullable=False),
            sa.Column('vendor', sa.String(20), nullable=False),
            sa.Column('instance_name', sa.String(100), nullable=False),
            sa.Column('description', sa.Text(), nullable=True),
            sa.Column('base_url', sa.String(500), nullable=True),
            sa.Column('credentials_encrypted', sa.Text(), nullable=True),
            sa.Column('extra_config', sa.JSON(), server_default='{}'),
            sa.Column('health_status', sa.String(20), server_default='unknown'),
            sa.Column('health_status_reason', sa.String(500), nullable=True),
            sa.Column('last_health_check', sa.DateTime(), nullable=True),
            sa.Column('is_default', sa.Boolean(), server_default='false'),
            sa.Column('is_active', sa.Boolean(), server_default='true'),
            sa.Column('created_at', sa.DateTime(), server_default=sa.func.now()),
            sa.Column('updated_at', sa.DateTime(), server_default=sa.func.now()),
            sa.UniqueConstraint('tenant_id', 'instance_name', name='uq_vector_store_instance_tenant_name'),
        )
        op.create_index('ix_vsi_tenant_id', 'vector_store_instance', ['tenant_id'])
        op.create_index('idx_vsi_tenant_vendor', 'vector_store_instance', ['tenant_id', 'vendor'])

    # --- Add columns to agent table ---
    if 'agent' in existing_tables:
        existing_columns = [col['name'] for col in inspector.get_columns('agent')]

        if 'vector_store_instance_id' not in existing_columns:
            op.add_column('agent', sa.Column(
                'vector_store_instance_id', sa.Integer(),
                sa.ForeignKey('vector_store_instance.id', ondelete='SET NULL'),
                nullable=True
            ))

        if 'vector_store_mode' not in existing_columns:
            op.add_column('agent', sa.Column(
                'vector_store_mode', sa.String(20),
                server_default='override', nullable=True
            ))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = inspector.get_table_names()

    if 'agent' in existing_tables:
        existing_columns = [col['name'] for col in inspector.get_columns('agent')]
        if 'vector_store_mode' in existing_columns:
            op.drop_column('agent', 'vector_store_mode')
        if 'vector_store_instance_id' in existing_columns:
            op.drop_column('agent', 'vector_store_instance_id')

    if 'vector_store_instance' in existing_tables:
        op.drop_table('vector_store_instance')
