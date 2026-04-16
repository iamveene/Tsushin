"""
Add password_changed_at column to user table for JWT invalidation after password change.

BUG-134 FIX: Track when user last changed their password so existing JWTs
issued before the change can be rejected.

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'user' not in inspector.get_table_names():
        return

    cols = [c['name'] for c in inspector.get_columns('user')]

    if 'password_changed_at' not in cols:
        op.add_column('user',
                       sa.Column('password_changed_at', sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column('user', 'password_changed_at')
