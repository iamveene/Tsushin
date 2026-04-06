"""
BUG-LOG-010: Add unique constraint on flow_node_run.idempotency_key.

The ORM model already declares `unique=True` on the column, but databases
created before this declaration may lack the DB-level constraint.  This
migration ensures the constraint exists regardless of creation history,
closing the TOCTOU race on the idempotency check.

Revision ID: 0026
Revises: 0025
"""
from alembic import op
import sqlalchemy as sa

revision = '0026'
down_revision = '0025'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'flow_node_run' not in inspector.get_table_names():
        # Fresh install — table will be created by ORM metadata with the
        # unique constraint already present.
        return

    # Check if the unique constraint already exists
    existing_indexes = {idx['name'] for idx in inspector.get_indexes('flow_node_run')}
    unique_constraints = {
        uc['name']
        for uc in inspector.get_unique_constraints('flow_node_run')
    }

    # The constraint may appear as either a unique index or a unique constraint
    # depending on the DB backend.  Check both.
    target_name = 'uq_flow_node_run_idempotency_key'
    if target_name in existing_indexes or target_name in unique_constraints:
        return  # Already exists

    # Also check for SQLAlchemy auto-generated names (e.g., from Column(unique=True))
    for uc in inspector.get_unique_constraints('flow_node_run'):
        if uc.get('column_names') == ['idempotency_key']:
            return  # Already has a unique constraint on idempotency_key

    # Check if there are duplicate idempotency_key values that would block
    # the constraint creation.  Clean them up by keeping only the latest row.
    dup_count = bind.execute(sa.text(
        "SELECT COUNT(*) FROM ("
        "  SELECT idempotency_key FROM flow_node_run"
        "  WHERE idempotency_key IS NOT NULL"
        "  GROUP BY idempotency_key HAVING COUNT(*) > 1"
        ") dups"
    )).scalar() or 0

    if dup_count > 0:
        print(f"[0026] Cleaning {dup_count} duplicate idempotency_key group(s) — keeping latest row per key")
        # Keep only the row with the highest id for each duplicate key
        op.execute(
            """
            DELETE FROM flow_node_run
            WHERE id NOT IN (
                SELECT MAX(id) FROM flow_node_run
                WHERE idempotency_key IS NOT NULL
                GROUP BY idempotency_key
            )
            AND idempotency_key IS NOT NULL
            AND idempotency_key IN (
                SELECT idempotency_key FROM flow_node_run
                WHERE idempotency_key IS NOT NULL
                GROUP BY idempotency_key HAVING COUNT(*) > 1
            )
            """
        )

    op.create_unique_constraint(
        target_name,
        'flow_node_run',
        ['idempotency_key'],
    )


def downgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if 'flow_node_run' not in inspector.get_table_names():
        return

    unique_constraints = {
        uc['name']
        for uc in inspector.get_unique_constraints('flow_node_run')
    }
    target_name = 'uq_flow_node_run_idempotency_key'
    if target_name in unique_constraints:
        op.drop_constraint(target_name, 'flow_node_run', type_='unique')
