"""
Add CDP browser mode column to browser_automation_integration

Revision ID: 0013
Revises: 0012
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'browser_automation_integration' not in inspector.get_table_names():
        return

    cols = [c['name'] for c in inspector.get_columns('browser_automation_integration')]

    if 'cdp_url' not in cols:
        op.add_column('browser_automation_integration',
                       sa.Column('cdp_url', sa.String(255), nullable=True,
                                 server_default='http://host.docker.internal:9222'))


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'browser_automation_integration' not in inspector.get_table_names():
        return

    cols = [c['name'] for c in inspector.get_columns('browser_automation_integration')]

    if 'cdp_url' in cols:
        op.drop_column('browser_automation_integration', 'cdp_url')
