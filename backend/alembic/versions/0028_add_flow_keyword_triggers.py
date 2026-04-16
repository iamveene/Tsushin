"""
Add trigger_keywords to flow_definition for keyword-based flow execution (BUG-336).

Adds a JSON column that stores a list of keywords/commands that trigger the flow
when matched in an incoming message (playground or channel).
Also extends the execution_method constraint to allow 'keyword' value.

Revision ID: 0028
Revises: 0027
"""
from alembic import op
import sqlalchemy as sa

revision = '0028'
down_revision = '0027'
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('flow_definition')]

    if 'trigger_keywords' not in columns:
        op.add_column(
            'flow_definition',
            sa.Column(
                'trigger_keywords',
                sa.JSON(),
                nullable=True,
                server_default='[]',
                comment='List of keywords/commands that trigger this flow (execution_method=keyword)'
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = [c['name'] for c in inspector.get_columns('flow_definition')]

    if 'trigger_keywords' in columns:
        op.drop_column('flow_definition', 'trigger_keywords')
