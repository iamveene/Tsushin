"""
v0.6.0: Add auto-provisioning columns to vector_store_instance and
default_vector_store_instance_id to config table.

Revision ID: 0021
Revises: 0020
"""
from alembic import op
import sqlalchemy as sa

revision = '0021'
down_revision = '0020'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # --- Add auto-provision columns to vector_store_instance ---
    existing_columns = {col['name'] for col in inspector.get_columns('vector_store_instance')}

    new_columns = [
        ('is_auto_provisioned', sa.Boolean(), {'server_default': 'false', 'nullable': False}),
        ('container_name', sa.String(200), {'nullable': True}),
        ('container_id', sa.String(80), {'nullable': True}),
        ('container_port', sa.Integer(), {'nullable': True}),
        ('container_status', sa.String(20), {'server_default': 'none', 'nullable': False}),
        ('container_image', sa.String(200), {'nullable': True}),
        ('volume_name', sa.String(150), {'nullable': True}),
        ('mem_limit', sa.String(20), {'nullable': True}),
        ('cpu_quota', sa.Integer(), {'nullable': True}),
    ]

    for col_name, col_type, kwargs in new_columns:
        if col_name not in existing_columns:
            op.add_column('vector_store_instance', sa.Column(col_name, col_type, **kwargs))

    # --- Add default_vector_store_instance_id to config ---
    config_columns = {col['name'] for col in inspector.get_columns('config')}

    if 'default_vector_store_instance_id' not in config_columns:
        op.add_column('config', sa.Column(
            'default_vector_store_instance_id',
            sa.Integer(),
            sa.ForeignKey('vector_store_instance.id', ondelete='SET NULL'),
            nullable=True,
        ))


def downgrade():
    op.drop_column('config', 'default_vector_store_instance_id')
    for col in ['is_auto_provisioned', 'container_name', 'container_id', 'container_port',
                'container_status', 'container_image', 'volume_name', 'mem_limit', 'cpu_quota']:
        op.drop_column('vector_store_instance', col)
