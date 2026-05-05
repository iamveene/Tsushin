"""KB custom embedding and vector profile snapshots.

Revision ID: 0079
Revises: 0078
Create Date: 2026-05-02
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0079"
down_revision: Union[str, None] = "0078"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def _create_index_if_missing(inspector, table_name: str, index_name: str, columns: list[str]) -> None:
    if not _has_table(inspector, table_name):
        return
    existing = {idx["name"] for idx in inspector.get_indexes(table_name)}
    if index_name not in existing:
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "agent_knowledge_config"):
        op.create_table(
            "agent_knowledge_config",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("agent_id", sa.Integer(), nullable=False),
            sa.Column("embedding_provider_instance_id", sa.Integer(), nullable=True),
            sa.Column("embedding_provider", sa.String(length=30), nullable=False, server_default="local"),
            sa.Column("embedding_model", sa.String(length=100), nullable=False, server_default="all-MiniLM-L6-v2"),
            sa.Column("embedding_dims", sa.Integer(), nullable=False, server_default="384"),
            sa.Column("embedding_metric", sa.String(length=20), nullable=False, server_default="cosine"),
            sa.Column("vector_store_instance_id", sa.Integer(), nullable=True),
            sa.Column("vector_collection_name", sa.String(length=255), nullable=True),
            sa.Column("vector_namespace", sa.String(length=255), nullable=True),
            sa.Column("chunk_strategy", sa.String(length=30), nullable=False, server_default="fixed_text"),
            sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="800"),
            sa.Column("chunk_overlap", sa.Integer(), nullable=False, server_default="100"),
            sa.Column("parser", sa.String(length=30), nullable=False, server_default="auto"),
            sa.Column("search_top_k", sa.Integer(), nullable=False, server_default="5"),
            sa.Column("similarity_threshold", sa.Float(), nullable=False, server_default="0.3"),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.Column("updated_at", sa.DateTime(), nullable=True),
            sa.ForeignKeyConstraint(
                ["embedding_provider_instance_id"],
                ["provider_instance.id"],
                ondelete="SET NULL",
            ),
            sa.ForeignKeyConstraint(
                ["vector_store_instance_id"],
                ["vector_store_instance.id"],
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint("tenant_id", "agent_id", name="uq_agent_knowledge_config_tenant_agent"),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(
        inspector,
        "agent_knowledge_config",
        "idx_agent_knowledge_config_tenant_agent",
        ["tenant_id", "agent_id"],
    )
    _create_index_if_missing(
        inspector,
        "agent_knowledge_config",
        "ix_agent_knowledge_config_tenant_id",
        ["tenant_id"],
    )
    _create_index_if_missing(
        inspector,
        "agent_knowledge_config",
        "ix_agent_knowledge_config_agent_id",
        ["agent_id"],
    )

    snapshot_columns = [
        ("tenant_id", sa.Column("tenant_id", sa.String(length=50), nullable=True)),
        ("embedding_provider_instance_id", sa.Column("embedding_provider_instance_id", sa.Integer(), nullable=True)),
        ("embedding_provider", sa.Column("embedding_provider", sa.String(length=30), nullable=True)),
        ("embedding_model", sa.Column("embedding_model", sa.String(length=100), nullable=True)),
        ("embedding_dims", sa.Column("embedding_dims", sa.Integer(), nullable=True)),
        ("embedding_metric", sa.Column("embedding_metric", sa.String(length=20), nullable=True)),
        ("vector_store_instance_id", sa.Column("vector_store_instance_id", sa.Integer(), nullable=True)),
        ("vector_collection_name", sa.Column("vector_collection_name", sa.String(length=255), nullable=True)),
        ("vector_namespace", sa.Column("vector_namespace", sa.String(length=255), nullable=True)),
        ("chunk_strategy", sa.Column("chunk_strategy", sa.String(length=30), nullable=True)),
        ("chunk_size", sa.Column("chunk_size", sa.Integer(), nullable=True)),
        ("chunk_overlap", sa.Column("chunk_overlap", sa.Integer(), nullable=True)),
        ("parser", sa.Column("parser", sa.String(length=30), nullable=True)),
        ("index_version", sa.Column("index_version", sa.Integer(), nullable=False, server_default="1")),
    ]

    for column_name, column in snapshot_columns:
        if not _has_column(inspector, "agent_knowledge", column_name):
            op.add_column("agent_knowledge", column)

    bind.execute(
        sa.text(
            """
            UPDATE agent_knowledge
            SET tenant_id = (
                SELECT agent.tenant_id
                FROM agent
                WHERE agent.id = agent_knowledge.agent_id
            )
            WHERE tenant_id IS NULL
            """
        )
    )

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "agent_knowledge", "ix_agent_knowledge_tenant_id", ["tenant_id"])
    _create_index_if_missing(
        inspector,
        "agent_knowledge",
        "idx_agent_knowledge_tenant_agent",
        ["tenant_id", "agent_id"],
    )
    _create_index_if_missing(
        inspector,
        "agent_knowledge",
        "idx_agent_knowledge_vector_profile",
        ["agent_id", "embedding_provider", "embedding_model", "embedding_dims"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if _has_table(inspector, "agent_knowledge_config"):
        op.drop_table("agent_knowledge_config")

    for index_name in (
        "idx_agent_knowledge_vector_profile",
        "idx_agent_knowledge_tenant_agent",
        "ix_agent_knowledge_tenant_id",
    ):
        inspector = sa.inspect(bind)
        if _has_table(inspector, "agent_knowledge") and index_name in {
            idx["name"] for idx in inspector.get_indexes("agent_knowledge")
        }:
            op.drop_index(index_name, table_name="agent_knowledge")

    for column_name in (
        "index_version",
        "parser",
        "chunk_overlap",
        "chunk_size",
        "chunk_strategy",
        "vector_namespace",
        "vector_collection_name",
        "vector_store_instance_id",
        "embedding_metric",
        "embedding_dims",
        "embedding_model",
        "embedding_provider",
        "embedding_provider_instance_id",
        "tenant_id",
    ):
        inspector = sa.inspect(bind)
        if _has_column(inspector, "agent_knowledge", column_name):
            op.drop_column("agent_knowledge", column_name)
