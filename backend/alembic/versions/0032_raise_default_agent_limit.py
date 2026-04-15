"""Raise default tenant agent limit from 5 to 10 for self-hosted installs.

Any tenant still on the old default of 5 gets bumped to 10.
New tenants are already created with max_agents=10 via auth_service.py.

Revision ID: 0032
Revises: 0031
"""
from alembic import op


def upgrade():
    op.execute(
        "UPDATE tenant SET max_agents = 10 WHERE max_agents = 5"
    )


def downgrade():
    # No rollback — lowering limits would break existing agents
    pass
