"""
BUG-367: Add api_client_id to conversation_thread for API v1 client isolation.

API clients were all sharing threads because they used user_id=0. This column
allows per-client thread scoping.

Revision ID: 0029
Revises: 0028
"""
from alembic import op
import sqlalchemy as sa

revision = '0029'
down_revision = '0028'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('conversation_thread')]

    if 'api_client_id' not in columns:
        op.add_column(
            'conversation_thread',
            sa.Column(
                'api_client_id',
                sa.String(100),
                nullable=True,
                index=True,
                comment='BUG-367: API v1 client ID for thread isolation'
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('conversation_thread')]

    if 'api_client_id' in columns:
        op.drop_column('conversation_thread', 'api_client_id')
