"""
Add system_ai_provider_instance_id to config table.

Allows the System AI Configuration to point to an existing ProviderInstance
instead of maintaining its own duplicated provider/model selection.

Revision ID: 0027
Revises: 0026
"""
from alembic import op
import sqlalchemy as sa

revision = '0027'
down_revision = '0026'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('config')]

    if 'system_ai_provider_instance_id' not in columns:
        op.add_column(
            'config',
            sa.Column(
                'system_ai_provider_instance_id',
                sa.Integer(),
                sa.ForeignKey('provider_instance.id', ondelete='SET NULL'),
                nullable=True,
            ),
        )


def downgrade() -> None:
    op.drop_column('config', 'system_ai_provider_instance_id')
