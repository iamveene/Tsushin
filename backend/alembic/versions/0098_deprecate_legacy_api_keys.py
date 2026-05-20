"""deprecate legacy api_key credential runtime

Revision ID: 0098
Revises: 0097
Create Date: 2026-05-20
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0098"
down_revision: Union[str, None] = "0097"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _tables() -> set[str]:
    return set(sa.inspect(op.get_bind()).get_table_names())


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {idx["name"] for idx in inspector.get_indexes(table_name)}


def upgrade() -> None:
    tables = _tables()

    if "search_provider_integration" not in tables:
        op.create_table(
            "search_provider_integration",
            sa.Column(
                "id",
                sa.Integer(),
                sa.ForeignKey("hub_integration.id", ondelete="CASCADE"),
                primary_key=True,
            ),
            sa.Column("provider_id", sa.String(length=40), nullable=False),
            sa.Column("api_key_encrypted", sa.Text(), nullable=False),
            sa.Column("api_key_preview", sa.String(length=32), nullable=True),
            sa.Column("default_country", sa.String(length=5), nullable=True, server_default="US"),
            sa.Column("default_language", sa.String(length=10), nullable=True, server_default="en"),
        )

    if "idx_search_provider_integration_provider" not in _indexes("search_provider_integration"):
        op.create_index(
            "idx_search_provider_integration_provider",
            "search_provider_integration",
            ["provider_id"],
        )

    tts_columns = _columns("tts_instance")
    if "api_key_encrypted" not in tts_columns:
        op.add_column("tts_instance", sa.Column("api_key_encrypted", sa.Text(), nullable=True))
    if "api_key_preview" not in tts_columns:
        op.add_column("tts_instance", sa.Column("api_key_preview", sa.String(length=32), nullable=True))


def downgrade() -> None:
    tts_columns = _columns("tts_instance")
    if "api_key_preview" in tts_columns:
        op.drop_column("tts_instance", "api_key_preview")
    if "api_key_encrypted" in tts_columns:
        op.drop_column("tts_instance", "api_key_encrypted")

    if "search_provider_integration" in _tables():
        op.drop_index("idx_search_provider_integration_provider", table_name="search_provider_integration")
        op.drop_table("search_provider_integration")
