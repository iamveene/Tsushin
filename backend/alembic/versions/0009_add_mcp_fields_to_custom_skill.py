"""Add mcp_server_id and mcp_tool_name to custom_skill table.

Links custom skills to MCP server tools, enabling MCP-backed
custom skill creation via the UI.

Revision ID: 0009
Revises: 0008
Create Date: 2026-03-28
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add MCP server reference columns to custom_skill (idempotent)."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    existing_columns = [col['name'] for col in inspector.get_columns('custom_skill')]

    if 'mcp_server_id' not in existing_columns:
        op.add_column(
            'custom_skill',
            sa.Column(
                'mcp_server_id',
                sa.Integer(),
                sa.ForeignKey('mcp_server_config.id', ondelete='SET NULL'),
                nullable=True,
            ),
        )

    if 'mcp_tool_name' not in existing_columns:
        op.add_column(
            'custom_skill',
            sa.Column('mcp_tool_name', sa.String(200), nullable=True),
        )


def downgrade() -> None:
    """Remove MCP server reference columns from custom_skill."""
    op.drop_column('custom_skill', 'mcp_tool_name')
    op.drop_column('custom_skill', 'mcp_server_id')
