"""Backfill tenant.plan_id from the legacy tenant.plan string column.

Tenants created before plan_seeding was wired into init_database have
plan_id = NULL even though subscription_plan rows now exist.  This
migration resolves the FK for all such tenants.

Revision ID: 0033
Revises: 0032
"""
revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None

from alembic import op


def upgrade():
    op.execute("""
        UPDATE tenant t
        SET plan_id = sp.id
        FROM subscription_plan sp
        WHERE sp.name = t.plan
          AND t.plan_id IS NULL
    """)


def downgrade():
    pass
