"""
Add session persistence columns to browser_automation_integration

Phase 35a: Browser session persistence support

Revision ID: 0012
Revises: 0011
"""
from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    # Check if table exists (fresh install may not have it yet)
    if 'browser_automation_integration' not in inspector.get_table_names():
        return

    cols = [c['name'] for c in inspector.get_columns('browser_automation_integration')]

    if 'session_persistence' not in cols:
        op.add_column('browser_automation_integration',
                       sa.Column('session_persistence', sa.Boolean(), server_default='false'))

    if 'session_ttl_seconds' not in cols:
        op.add_column('browser_automation_integration',
                       sa.Column('session_ttl_seconds', sa.Integer(), server_default='300'))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'browser_automation_integration' not in inspector.get_table_names():
        return

    cols = [c['name'] for c in inspector.get_columns('browser_automation_integration')]

    if 'session_ttl_seconds' in cols:
        op.drop_column('browser_automation_integration', 'session_ttl_seconds')
    if 'session_persistence' in cols:
        op.drop_column('browser_automation_integration', 'session_persistence')
