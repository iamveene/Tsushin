"""
v0.6.0 Item 37: Temporal Memory Decay

Add decay configuration fields to Agent model, and last_accessed_at tracking
to SemanticKnowledge and SharedMemory for time-based relevance scoring.

Revision ID: 0017
Revises: 0016
"""
from alembic import op
import sqlalchemy as sa

revision = '0017'
down_revision = '0016'
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = inspector.get_table_names()

    # --- Agent table: decay configuration ---
    if 'agent' in tables:
        cols = [c['name'] for c in inspector.get_columns('agent')]

        if 'memory_decay_enabled' not in cols:
            op.add_column('agent',
                          sa.Column('memory_decay_enabled', sa.Boolean(), server_default='false', nullable=True))
        if 'memory_decay_lambda' not in cols:
            op.add_column('agent',
                          sa.Column('memory_decay_lambda', sa.Float(), server_default='0.01', nullable=True))
        if 'memory_decay_archive_threshold' not in cols:
            op.add_column('agent',
                          sa.Column('memory_decay_archive_threshold', sa.Float(), server_default='0.05', nullable=True))
        if 'memory_decay_mmr_lambda' not in cols:
            op.add_column('agent',
                          sa.Column('memory_decay_mmr_lambda', sa.Float(), server_default='0.5', nullable=True))

    # --- SemanticKnowledge table: last_accessed_at ---
    if 'semantic_knowledge' in tables:
        cols = [c['name'] for c in inspector.get_columns('semantic_knowledge')]

        if 'last_accessed_at' not in cols:
            op.add_column('semantic_knowledge',
                          sa.Column('last_accessed_at', sa.DateTime(), nullable=True))
            # Backfill with updated_at (fallback to created_at, then NOW())
            op.execute("UPDATE semantic_knowledge SET last_accessed_at = COALESCE(updated_at, learned_at, NOW()) WHERE last_accessed_at IS NULL")

    # --- SharedMemory table: last_accessed_at ---
    if 'shared_memory' in tables:
        cols = [c['name'] for c in inspector.get_columns('shared_memory')]

        if 'last_accessed_at' not in cols:
            op.add_column('shared_memory',
                          sa.Column('last_accessed_at', sa.DateTime(), nullable=True))
            # Backfill with updated_at (fallback to created_at, then NOW())
            op.execute("UPDATE shared_memory SET last_accessed_at = COALESCE(updated_at, created_at, NOW()) WHERE last_accessed_at IS NULL")


def downgrade():
    op.drop_column('agent', 'memory_decay_mmr_lambda')
    op.drop_column('agent', 'memory_decay_archive_threshold')
    op.drop_column('agent', 'memory_decay_lambda')
    op.drop_column('agent', 'memory_decay_enabled')
    op.drop_column('semantic_knowledge', 'last_accessed_at')
    op.drop_column('shared_memory', 'last_accessed_at')
