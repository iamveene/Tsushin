"""Add PostgreSQL full-text search table for conversation search.

Replaces SQLite FTS5 virtual table with a regular PostgreSQL table
that uses tsvector generated column and GIN index.

Revision ID: 0002
Revises: 0001
Create Date: 2026-03-26
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create conversation_search_fts table with tsvector + GIN index."""
    # Check if we're on PostgreSQL (skip on SQLite)
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    # Create the table
    op.create_table(
        'conversation_search_fts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('thread_id', sa.Integer(), nullable=True),
        sa.Column('message_id', sa.String(100), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False, server_default=''),
        sa.Column('timestamp', sa.String(50), nullable=True),
        sa.Column('tenant_id', sa.String(50), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=True),
        sa.Column('agent_id', sa.Integer(), nullable=True),
    )

    # Add generated tsvector column for full-text search
    op.execute("""
        ALTER TABLE conversation_search_fts
        ADD COLUMN content_tsv tsvector
        GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
    """)

    # Create GIN index for fast full-text search
    op.execute("""
        CREATE INDEX idx_conversation_search_fts_tsv
        ON conversation_search_fts USING gin(content_tsv)
    """)

    # Create indexes for common filter columns
    op.create_index('idx_fts_tenant_id', 'conversation_search_fts', ['tenant_id'])
    op.create_index('idx_fts_thread_id', 'conversation_search_fts', ['thread_id'])
    op.create_index('idx_fts_user_id', 'conversation_search_fts', ['user_id'])
    op.create_index('idx_fts_agent_id', 'conversation_search_fts', ['agent_id'])
    op.create_index('idx_fts_message_id', 'conversation_search_fts', ['message_id'], unique=True)


def downgrade() -> None:
    """Drop the conversation search FTS table."""
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        return

    op.drop_table('conversation_search_fts')
