"""v0.7.0 KB custom embedding contract, chunking, and coexistence tests."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._case_memory_test_helpers import install_test_stubs  # noqa: E402

install_test_stubs()


class _PositiveSentenceTransformer:
    def __init__(self, *_args, **_kwargs):
        pass

    def encode(self, texts, **_kwargs):
        try:
            import numpy as np
        except Exception:  # pragma: no cover
            np = None
        if isinstance(texts, str):
            return np.ones(384, dtype=float) if np is not None else [1.0] * 384
        return (
            np.ones((len(texts), 384), dtype=float)
            if np is not None
            else [[1.0] * 384 for _ in texts]
        )

    def get_sentence_embedding_dimension(self):
        return 384


sys.modules["sentence_transformers"].SentenceTransformer = _PositiveSentenceTransformer


def test_embedding_catalog_accepts_release_070_providers():
    from agent.memory.embedding_catalog import validate_embedding_contract

    assert validate_embedding_contract(
        provider="local",
        model="all-MiniLM-L6-v2",
        dimensions=384,
    )["dimensions"] == 384
    assert validate_embedding_contract(
        provider="openai",
        model="text-embedding-3-small",
        dimensions=512,
    )["model"] == "text-embedding-3-small"
    assert validate_embedding_contract(
        provider="gemini",
        model="gemini-embedding-2",
        dimensions=3072,
    )["dimensions"] == 3072
    assert validate_embedding_contract(
        provider="ollama",
        model="nomic-embed-text",
        dimensions=768,
    )["provider"] == "ollama"


def test_embedding_catalog_rejects_dimension_mismatches():
    from agent.memory.embedding_catalog import validate_embedding_contract

    with pytest.raises(ValueError, match="Invalid embedding dimensions"):
        validate_embedding_contract(
            provider="local",
            model="all-MiniLM-L6-v2",
            dimensions=768,
        )

    with pytest.raises(ValueError, match="Invalid embedding dimensions"):
        validate_embedding_contract(
            provider="openai",
            model="text-embedding-3-small",
            dimensions=3072,
        )

    with pytest.raises(ValueError, match="Ollama embedding dimensions must be detected"):
        validate_embedding_contract(
            provider="ollama",
            model="nomic-embed-text",
            dimensions=None,
            allow_ollama_dynamic=False,
        )


def test_document_processor_chunks_json_by_structure(tmp_path):
    from agent.knowledge.document_processor import DocumentProcessor

    path = tmp_path / "kb.json"
    path.write_text(
        '{"product":{"name":"Tsushin","limits":{"kb":50}},"roles":["admin","agent"]}',
        encoding="utf-8",
    )

    chunks = DocumentProcessor(chunk_size=120, chunk_strategy="json_structure").process_document(
        str(path),
        "json",
        chunk_strategy="json_structure",
    )

    paths = {chunk.get("json_path") for chunk in chunks}
    assert "$.product.name" in paths
    assert "$.product.limits.kb" in paths
    assert all(chunk["chunk_strategy"] == "json_structure" for chunk in chunks)


def test_document_processor_chunks_csv_by_bounded_row_groups(tmp_path):
    from agent.knowledge.document_processor import DocumentProcessor

    path = tmp_path / "kb.csv"
    path.write_text(
        "id,name,status\n1,Alpha,active\n2,Beta,pending\n3,Gamma,closed\n",
        encoding="utf-8",
    )

    chunks = DocumentProcessor(chunk_size=70, chunk_strategy="csv_rows").process_document(
        str(path),
        "csv",
        chunk_strategy="csv_rows",
    )

    assert chunks
    assert all(chunk["chunk_strategy"] == "csv_rows" for chunk in chunks)
    assert chunks[0]["row_start"] == 1
    assert "Headers: id, name, status" in chunks[0]["content"]


def _make_kb_db():
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from models import (
        Agent,
        AgentKnowledge,
        AgentKnowledgeConfig,
        Base,
        Contact,
        ProviderInstance,
        VectorStoreIndex,
        VectorStoreInstance,
    )
    from models_rbac import Tenant, User

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Tenant.__table__,
            User.__table__,
            Contact.__table__,
            Agent.__table__,
            ProviderInstance.__table__,
            VectorStoreInstance.__table__,
            VectorStoreIndex.__table__,
            AgentKnowledgeConfig.__table__,
            AgentKnowledge.__table__,
        ],
    )
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()


def test_kb_config_snapshots_isolate_builtin_and_external_vector_profiles():
    from agent.knowledge.knowledge_service import KnowledgeService
    from models import Agent, Contact, ProviderInstance, VectorStoreInstance
    from models_rbac import Tenant, User

    db = _make_kb_db()
    try:
        db.add(Tenant(id="tenant-kb", name="Tenant KB", slug="tenant-kb"))
        db.add(User(id=1, tenant_id="tenant-kb", email="kb@example.com", password_hash="x"))
        db.add(Contact(id=10, tenant_id="tenant-kb", friendly_name="Agent", role="agent"))
        db.add(
            Agent(
                id=20,
                tenant_id="tenant-kb",
                contact_id=10,
                system_prompt="prompt",
                response_template="{response}",
                is_active=True,
            )
        )
        db.add(
            VectorStoreInstance(
                id=30,
                tenant_id="tenant-kb",
                vendor="qdrant",
                instance_name="Qdrant KB",
                base_url="http://qdrant.test",
                extra_config={"embedding_dims": 384},
                is_active=True,
            )
        )
        db.add(
            ProviderInstance(
                id=40,
                tenant_id="tenant-kb",
                vendor="openai",
                instance_name="OpenAI",
                available_models=["text-embedding-3-small"],
                is_active=True,
            )
        )
        db.commit()

        service = KnowledgeService.__new__(KnowledgeService)
        service.db = db

        default_config = service.get_knowledge_config(20, "tenant-kb")
        default_profile = service._profile_from_config(default_config, tenant_id="tenant-kb", agent_id=20)
        assert default_profile.vector_store_instance_id is None
        assert default_profile.vector_collection_name.endswith("_20_384")

        qdrant_config = service.update_knowledge_config(
            20,
            "tenant-kb",
            {
                "embedding_provider": "local",
                "embedding_model": "all-MiniLM-L6-v2",
                "embedding_dims": 384,
                "vector_store_instance_id": 30,
                "chunk_strategy": "fixed_text",
            },
        )
        qdrant_profile = service._profile_from_config(qdrant_config, tenant_id="tenant-kb", agent_id=20)
        assert qdrant_profile.vector_store_instance_id == 30
        assert qdrant_profile.vector_collection_name.endswith("_20_384")

        openai_config = service.update_knowledge_config(
            20,
            "tenant-kb",
            {
                "embedding_provider": "openai",
                "embedding_provider_instance_id": 40,
                "embedding_model": "text-embedding-3-small",
                "embedding_dims": 512,
                "vector_store_instance_id": 30,
                "chunk_strategy": "fixed_text",
            },
        )
        openai_profile = service._profile_from_config(openai_config, tenant_id="tenant-kb", agent_id=20)
        assert openai_profile.vector_collection_name.endswith("_20_512")
        assert openai_profile.vector_collection_name != qdrant_profile.vector_collection_name
    finally:
        db.close()
