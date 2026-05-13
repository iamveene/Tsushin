"""Add immutable vector store indexes.

Revision ID: 0080
Revises: 0079
Create Date: 2026-05-03
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0080"
down_revision: Union[str, None] = "0079"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(inspector, table_name: str) -> bool:
    return table_name in inspector.get_table_names()


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return column_name in {col["name"] for col in inspector.get_columns(table_name)}


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return index_name in {idx["name"] for idx in inspector.get_indexes(table_name)}


def _has_foreign_key(inspector, table_name: str, constraint_name: str) -> bool:
    if not _has_table(inspector, table_name):
        return False
    return constraint_name in {fk["name"] for fk in inspector.get_foreign_keys(table_name)}


def _add_column_if_missing(inspector, table_name: str, column_name: str, column) -> None:
    if _has_table(inspector, table_name) and not _has_column(inspector, table_name, column_name):
        op.add_column(table_name, column)


def _create_index_if_missing(inspector, table_name: str, index_name: str, columns: list[str]) -> None:
    if not _has_index(inspector, table_name, index_name):
        op.create_index(index_name, table_name, columns)


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not _has_table(inspector, "vector_store_index"):
        op.create_table(
            "vector_store_index",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("vector_store_instance_id", sa.Integer(), nullable=True),
            sa.Column("purpose", sa.String(length=32), nullable=False),
            sa.Column("owner_type", sa.String(length=32), nullable=False),
            sa.Column("owner_id", sa.Integer(), nullable=False),
            sa.Column("embedding_provider_instance_id", sa.Integer(), nullable=True),
            sa.Column("embedding_provider", sa.String(length=30), nullable=False),
            sa.Column("embedding_model", sa.String(length=128), nullable=False),
            sa.Column("embedding_dims", sa.Integer(), nullable=False),
            sa.Column("embedding_metric", sa.String(length=24), nullable=False, server_default="cosine"),
            sa.Column("embedding_task_document", sa.String(length=64), nullable=True),
            sa.Column("embedding_task_query", sa.String(length=64), nullable=True),
            sa.Column("physical_collection_name", sa.String(length=255), nullable=False),
            sa.Column("physical_namespace", sa.String(length=255), nullable=False),
            sa.Column("physical_index_name", sa.String(length=255), nullable=True),
            sa.Column("contract_hash", sa.String(length=24), nullable=False),
            sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
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
            sa.UniqueConstraint(
                "tenant_id",
                "vector_store_instance_id",
                "purpose",
                "owner_type",
                "owner_id",
                "contract_hash",
                name="uq_vector_store_index_contract_owner",
            ),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "vector_store_index", "ix_vector_store_index_tenant_id", ["tenant_id"])
    _create_index_if_missing(
        inspector,
        "vector_store_index",
        "ix_vector_store_index_vector_store_instance_id",
        ["vector_store_instance_id"],
    )
    _create_index_if_missing(
        inspector,
        "vector_store_index",
        "ix_vector_store_index_purpose",
        ["purpose"],
    )
    _create_index_if_missing(
        inspector,
        "vector_store_index",
        "idx_vector_store_index_lookup",
        ["tenant_id", "purpose", "owner_type", "owner_id", "embedding_dims"],
    )

    inspector = sa.inspect(bind)
    _add_column_if_missing(
        inspector,
        "agent_knowledge_config",
        "vector_store_index_id",
        sa.Column("vector_store_index_id", sa.Integer(), nullable=True),
    )
    _add_column_if_missing(
        inspector,
        "agent_knowledge",
        "vector_store_index_id",
        sa.Column("vector_store_index_id", sa.Integer(), nullable=True),
    )
    inspector = sa.inspect(bind)
    if (
        _has_table(inspector, "agent_knowledge_config")
        and _has_table(inspector, "vector_store_index")
        and not _has_foreign_key(
            inspector,
            "agent_knowledge_config",
            "fk_agent_knowledge_config_vector_store_index_id",
        )
    ):
        op.create_foreign_key(
            "fk_agent_knowledge_config_vector_store_index_id",
            "agent_knowledge_config",
            "vector_store_index",
            ["vector_store_index_id"],
            ["id"],
            ondelete="SET NULL",
        )

    if not _has_table(inspector, "project_knowledge_config"):
        op.create_table(
            "project_knowledge_config",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("tenant_id", sa.String(length=50), nullable=False),
            sa.Column("project_id", sa.Integer(), nullable=False),
            sa.Column("embedding_provider_instance_id", sa.Integer(), nullable=True),
            sa.Column("embedding_provider", sa.String(length=30), nullable=False, server_default="local"),
            sa.Column("embedding_model", sa.String(length=100), nullable=False, server_default="all-MiniLM-L6-v2"),
            sa.Column("embedding_dims", sa.Integer(), nullable=False, server_default="384"),
            sa.Column("embedding_metric", sa.String(length=20), nullable=False, server_default="cosine"),
            sa.Column("vector_store_instance_id", sa.Integer(), nullable=True),
            sa.Column("vector_store_index_id", sa.Integer(), nullable=True),
            sa.Column("vector_collection_name", sa.String(length=255), nullable=True),
            sa.Column("vector_namespace", sa.String(length=255), nullable=True),
            sa.Column("chunk_strategy", sa.String(length=30), nullable=False, server_default="fixed_text"),
            sa.Column("chunk_size", sa.Integer(), nullable=False, server_default="500"),
            sa.Column("chunk_overlap", sa.Integer(), nullable=False, server_default="50"),
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
            sa.ForeignKeyConstraint(
                ["vector_store_index_id"],
                ["vector_store_index.id"],
                ondelete="SET NULL",
            ),
            sa.UniqueConstraint(
                "tenant_id",
                "project_id",
                name="uq_project_knowledge_config_tenant_project",
            ),
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(
        inspector,
        "project_knowledge_config",
        "ix_project_knowledge_config_tenant_id",
        ["tenant_id"],
    )
    _create_index_if_missing(
        inspector,
        "project_knowledge_config",
        "ix_project_knowledge_config_project_id",
        ["project_id"],
    )
    _create_index_if_missing(
        inspector,
        "project_knowledge_config",
        "idx_project_knowledge_config_tenant_project",
        ["tenant_id", "project_id"],
    )

    project_snapshot_columns = [
        ("tenant_id", sa.Column("tenant_id", sa.String(length=50), nullable=True)),
        ("embedding_provider_instance_id", sa.Column("embedding_provider_instance_id", sa.Integer(), nullable=True)),
        ("embedding_provider", sa.Column("embedding_provider", sa.String(length=30), nullable=True)),
        ("embedding_model", sa.Column("embedding_model", sa.String(length=100), nullable=True)),
        ("embedding_dims", sa.Column("embedding_dims", sa.Integer(), nullable=True)),
        ("embedding_metric", sa.Column("embedding_metric", sa.String(length=20), nullable=True)),
        ("vector_store_instance_id", sa.Column("vector_store_instance_id", sa.Integer(), nullable=True)),
        ("vector_store_index_id", sa.Column("vector_store_index_id", sa.Integer(), nullable=True)),
        ("vector_collection_name", sa.Column("vector_collection_name", sa.String(length=255), nullable=True)),
        ("vector_namespace", sa.Column("vector_namespace", sa.String(length=255), nullable=True)),
        ("chunk_strategy", sa.Column("chunk_strategy", sa.String(length=30), nullable=True)),
        ("chunk_size", sa.Column("chunk_size", sa.Integer(), nullable=True)),
        ("chunk_overlap", sa.Column("chunk_overlap", sa.Integer(), nullable=True)),
        ("parser", sa.Column("parser", sa.String(length=30), nullable=True)),
        ("index_version", sa.Column("index_version", sa.Integer(), nullable=False, server_default="1")),
    ]

    inspector = sa.inspect(bind)
    for column_name, column in project_snapshot_columns:
        _add_column_if_missing(inspector, "project_knowledge", column_name, column)
        inspector = sa.inspect(bind)

    if _has_table(inspector, "project_knowledge") and _has_table(inspector, "project"):
        bind.execute(
            sa.text(
                """
                UPDATE project_knowledge
                SET tenant_id = (
                    SELECT project.tenant_id
                    FROM project
                    WHERE project.id = project_knowledge.project_id
                )
                WHERE tenant_id IS NULL
                """
            )
        )

    inspector = sa.inspect(bind)
    _create_index_if_missing(inspector, "project_knowledge", "ix_project_knowledge_tenant_id", ["tenant_id"])
    _create_index_if_missing(
        inspector,
        "project_knowledge",
        "idx_project_knowledge_tenant_project",
        ["tenant_id", "project_id"],
    )
    _create_index_if_missing(
        inspector,
        "project_knowledge",
        "idx_project_knowledge_vector_profile",
        ["project_id", "embedding_provider", "embedding_model", "embedding_dims"],
    )
    _create_index_if_missing(
        inspector,
        "project_knowledge",
        "idx_project_knowledge_vector_store_index",
        ["vector_store_index_id"],
    )

    case_memory_columns = [
        ("vector_store_index_id", sa.Column("vector_store_index_id", sa.Integer(), nullable=True)),
        ("embedding_provider_instance_id", sa.Column("embedding_provider_instance_id", sa.Integer(), nullable=True)),
    ]
    for column_name, column in case_memory_columns:
        _add_column_if_missing(inspector, "case_memory", column_name, column)
        inspector = sa.inspect(bind)

    if (
        _has_table(inspector, "case_memory")
        and _has_table(inspector, "vector_store_index")
        and not _has_foreign_key(
            inspector,
            "case_memory",
            "fk_case_memory_vector_store_index_id",
        )
    ):
        op.create_foreign_key(
            "fk_case_memory_vector_store_index_id",
            "case_memory",
            "vector_store_index",
            ["vector_store_index_id"],
            ["id"],
            ondelete="SET NULL",
        )

    _create_index_if_missing(
        inspector,
        "case_memory",
        "idx_case_memory_vector_store_index",
        ["vector_store_index_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    for table_name, constraint_name in (
        ("case_memory", "fk_case_memory_vector_store_index_id"),
        ("agent_knowledge_config", "fk_agent_knowledge_config_vector_store_index_id"),
    ):
        inspector = sa.inspect(bind)
        if _has_foreign_key(inspector, table_name, constraint_name):
            op.drop_constraint(constraint_name, table_name, type_="foreignkey")

    for table_name, index_name in (
        ("case_memory", "idx_case_memory_vector_store_index"),
        ("project_knowledge", "idx_project_knowledge_vector_store_index"),
        ("project_knowledge", "idx_project_knowledge_vector_profile"),
        ("project_knowledge", "idx_project_knowledge_tenant_project"),
        ("project_knowledge", "ix_project_knowledge_tenant_id"),
    ):
        inspector = sa.inspect(bind)
        if _has_index(inspector, table_name, index_name):
            op.drop_index(index_name, table_name=table_name)

    for column_name in ("embedding_provider_instance_id", "vector_store_index_id"):
        inspector = sa.inspect(bind)
        if _has_column(inspector, "case_memory", column_name):
            op.drop_column("case_memory", column_name)

    for column_name in (
        "index_version",
        "parser",
        "chunk_overlap",
        "chunk_size",
        "chunk_strategy",
        "vector_namespace",
        "vector_collection_name",
        "vector_store_index_id",
        "vector_store_instance_id",
        "embedding_metric",
        "embedding_dims",
        "embedding_model",
        "embedding_provider",
        "embedding_provider_instance_id",
        "tenant_id",
    ):
        inspector = sa.inspect(bind)
        if _has_column(inspector, "project_knowledge", column_name):
            op.drop_column("project_knowledge", column_name)

    if _has_table(inspector, "project_knowledge_config"):
        op.drop_table("project_knowledge_config")

    for table_name, column_name in (
        ("agent_knowledge", "vector_store_index_id"),
        ("agent_knowledge_config", "vector_store_index_id"),
    ):
        inspector = sa.inspect(bind)
        if _has_column(inspector, table_name, column_name):
            op.drop_column(table_name, column_name)

    if _has_table(inspector, "vector_store_index"):
        op.drop_table("vector_store_index")
