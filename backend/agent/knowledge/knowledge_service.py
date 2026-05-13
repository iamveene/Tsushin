"""
Phase 5.0: Knowledge Base - Knowledge Service
Manages agent knowledge base including document upload, processing, and retrieval.
"""

import logging
import asyncio
import hashlib
import json
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import List, Dict, Optional, Any, Tuple
from datetime import datetime
from sqlalchemy.orm import Session

from models import Agent, AgentKnowledge, AgentKnowledgeConfig, KnowledgeChunk, VectorStoreInstance
from agent.knowledge.document_processor import DocumentProcessor
from agent.memory.embedding_catalog import (
    LOCAL_DIMS,
    LOCAL_MODEL,
    normalize_embedding_provider,
    provider_default_model,
    validate_embedding_contract,
)
from agent.memory.embedding_service import get_shared_embedding_service
import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

_DOCUMENT_METADATA_SUFFIX = ".meta.json"
_MAX_DOCUMENT_NAME_LENGTH = 255
_MAX_DOCUMENT_TAGS = 12
_MAX_DOCUMENT_TAG_LENGTH = 48
_KB_INDEX_VERSION = 1
_DEFAULT_CHUNK_SIZE = 800
_DEFAULT_CHUNK_OVERLAP = 100
_DEFAULT_SEARCH_TOP_K = 5
_DEFAULT_SIMILARITY_THRESHOLD = 0.3
_VALID_CHUNK_STRATEGIES = {"fixed_text", "json_structure", "csv_rows"}
_VALID_PARSERS = {"auto", "txt", "csv", "json", "pdf", "docx"}


@dataclass(frozen=True)
class KnowledgeIndexProfile:
    tenant_id: Optional[str]
    agent_id: int
    embedding_provider_instance_id: Optional[int]
    embedding_provider: str
    embedding_model: str
    embedding_dims: int
    embedding_metric: str
    vector_store_instance_id: Optional[int]
    vector_store_index_id: Optional[int]
    vector_collection_name: str
    vector_namespace: str
    chunk_strategy: str
    chunk_size: int
    chunk_overlap: int
    parser: str
    index_version: int = _KB_INDEX_VERSION

    def grouping_key(self) -> Tuple[Any, ...]:
        return (
            self.tenant_id,
            self.agent_id,
            self.embedding_provider_instance_id,
            self.embedding_provider,
            self.embedding_model,
            self.embedding_dims,
            self.vector_store_instance_id,
            self.vector_store_index_id,
            self.vector_collection_name,
            self.vector_namespace,
        )


class KnowledgeMetadataError(RuntimeError):
    """Raised when a knowledge-document sidecar cannot be read or written safely."""


def sanitize_document_name(document_name: str) -> str:
    """Normalize a user-facing document name without changing the stored file path."""
    cleaned = (document_name or "").strip()
    cleaned = cleaned.replace("\x00", " ")
    cleaned = re.sub(r"[\\/]+", " ", cleaned)
    cleaned = re.sub(r"[\r\n\t]+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    cleaned = cleaned.lstrip(". ").strip()

    if not cleaned:
        raise ValueError("Document name cannot be empty")

    if len(cleaned) > _MAX_DOCUMENT_NAME_LENGTH:
        raise ValueError(
            f"Document name must be {_MAX_DOCUMENT_NAME_LENGTH} characters or fewer"
        )

    return cleaned


def normalize_document_tags(tags: Optional[List[str]]) -> List[str]:
    """Validate and normalize free-form document tags into a stable, deduplicated list."""
    if not tags:
        return []
    if not isinstance(tags, list):
        raise ValueError("Tags must be provided as a list")

    normalized: List[str] = []
    seen: set[str] = set()

    for raw_tag in tags:
        if not isinstance(raw_tag, str):
            raise ValueError("Each tag must be a string")
        tag = re.sub(r"\s+", " ", raw_tag.strip().lower())
        if not tag:
            continue
        if len(tag) > _MAX_DOCUMENT_TAG_LENGTH:
            raise ValueError(
                f"Each tag must be {_MAX_DOCUMENT_TAG_LENGTH} characters or fewer"
            )
        if tag in seen:
            continue
        seen.add(tag)
        normalized.append(tag)
        if len(normalized) > _MAX_DOCUMENT_TAGS:
            raise ValueError(f"You can assign up to {_MAX_DOCUMENT_TAGS} tags per document")

    return normalized


class KnowledgeService:
    """Service for managing agent knowledge base."""

    def __init__(self, db: Session):
        """
        Initialize knowledge service.

        Args:
            db: Database session
        """
        self.db = db
        self.processor = DocumentProcessor()
        self.embedding_service = get_shared_embedding_service()

        # Initialize ChromaDB client via process-wide factory (BUG-695).
        vector_dir = Path("./data/chroma/knowledge")
        vector_dir.mkdir(parents=True, exist_ok=True)
        from chroma_client_factory import get_chroma_client
        self.chroma_client = get_chroma_client(str(vector_dir))

        # Storage directory for uploaded files
        self.storage_dir = Path("./data/knowledge")
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def _tenant_hash(self, tenant_id: Optional[str]) -> str:
        raw = tenant_id or "system"
        return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]

    def _collection_base(self, tenant_id: Optional[str], agent_id: int, dims: int) -> str:
        return f"kb_{self._tenant_hash(tenant_id)}_{agent_id}_{dims}"

    def _legacy_collection_name(self, agent_id: int) -> str:
        return f"knowledge_agent_{agent_id}"

    def _default_profile(
        self,
        *,
        tenant_id: Optional[str],
        agent_id: int,
    ) -> KnowledgeIndexProfile:
        collection = self._collection_base(tenant_id, agent_id, LOCAL_DIMS)
        return KnowledgeIndexProfile(
            tenant_id=tenant_id,
            agent_id=agent_id,
            embedding_provider_instance_id=None,
            embedding_provider="local",
            embedding_model=LOCAL_MODEL,
            embedding_dims=LOCAL_DIMS,
            embedding_metric="cosine",
            vector_store_instance_id=None,
            vector_store_index_id=None,
            vector_collection_name=collection,
            vector_namespace=f"kb:{tenant_id or 'system'}:{agent_id}:{LOCAL_DIMS}",
            chunk_strategy="fixed_text",
            chunk_size=_DEFAULT_CHUNK_SIZE,
            chunk_overlap=_DEFAULT_CHUNK_OVERLAP,
            parser="auto",
        )

    def _profile_from_config(
        self,
        config: AgentKnowledgeConfig,
        *,
        tenant_id: str,
        agent_id: int,
    ) -> KnowledgeIndexProfile:
        provider = normalize_embedding_provider(config.embedding_provider)
        normalized = validate_embedding_contract(
            provider=provider,
            model=config.embedding_model or provider_default_model(provider),
            dimensions=config.embedding_dims,
            allow_ollama_dynamic=False,
        )
        dims = int(normalized["dimensions"])
        collection = config.vector_collection_name or self._collection_base(tenant_id, agent_id, dims)
        namespace = config.vector_namespace or f"kb:{tenant_id}:{agent_id}:{dims}"
        strategy = config.chunk_strategy if config.chunk_strategy in _VALID_CHUNK_STRATEGIES else "fixed_text"
        parser = config.parser if config.parser in _VALID_PARSERS else "auto"
        return KnowledgeIndexProfile(
            tenant_id=tenant_id,
            agent_id=agent_id,
            embedding_provider_instance_id=config.embedding_provider_instance_id,
            embedding_provider=str(normalized["provider"]),
            embedding_model=str(normalized["model"]),
            embedding_dims=dims,
            embedding_metric=str(config.embedding_metric or normalized.get("metric") or "cosine"),
            vector_store_instance_id=config.vector_store_instance_id,
            vector_store_index_id=getattr(config, "vector_store_index_id", None),
            vector_collection_name=collection,
            vector_namespace=namespace,
            chunk_strategy=strategy,
            chunk_size=int(config.chunk_size or _DEFAULT_CHUNK_SIZE),
            chunk_overlap=int(config.chunk_overlap or _DEFAULT_CHUNK_OVERLAP),
            parser=parser,
        )

    def _profile_from_knowledge(self, knowledge: AgentKnowledge) -> KnowledgeIndexProfile:
        tenant_id = getattr(knowledge, "tenant_id", None)
        dims = int(getattr(knowledge, "embedding_dims", None) or LOCAL_DIMS)
        provider = normalize_embedding_provider(getattr(knowledge, "embedding_provider", None))
        model = getattr(knowledge, "embedding_model", None) or (
            provider_default_model(provider) if provider != "ollama" else LOCAL_MODEL
        )
        collection = (
            getattr(knowledge, "vector_collection_name", None)
            or self._legacy_collection_name(knowledge.agent_id)
        )
        namespace = (
            getattr(knowledge, "vector_namespace", None)
            or f"kb:{tenant_id or 'system'}:{knowledge.agent_id}:{dims}"
        )
        return KnowledgeIndexProfile(
            tenant_id=tenant_id,
            agent_id=knowledge.agent_id,
            embedding_provider_instance_id=getattr(knowledge, "embedding_provider_instance_id", None),
            embedding_provider=provider,
            embedding_model=model,
            embedding_dims=dims,
            embedding_metric=getattr(knowledge, "embedding_metric", None) or "cosine",
            vector_store_instance_id=getattr(knowledge, "vector_store_instance_id", None),
            vector_store_index_id=getattr(knowledge, "vector_store_index_id", None),
            vector_collection_name=collection,
            vector_namespace=namespace,
            chunk_strategy=getattr(knowledge, "chunk_strategy", None) or "fixed_text",
            chunk_size=int(getattr(knowledge, "chunk_size", None) or _DEFAULT_CHUNK_SIZE),
            chunk_overlap=int(getattr(knowledge, "chunk_overlap", None) or _DEFAULT_CHUNK_OVERLAP),
            parser=getattr(knowledge, "parser", None) or "auto",
            index_version=int(getattr(knowledge, "index_version", None) or 0),
        )

    def _snapshot_profile(self, knowledge: AgentKnowledge, profile: KnowledgeIndexProfile) -> None:
        knowledge.tenant_id = profile.tenant_id
        knowledge.embedding_provider_instance_id = profile.embedding_provider_instance_id
        knowledge.embedding_provider = profile.embedding_provider
        knowledge.embedding_model = profile.embedding_model
        knowledge.embedding_dims = profile.embedding_dims
        knowledge.embedding_metric = profile.embedding_metric
        knowledge.vector_store_instance_id = profile.vector_store_instance_id
        knowledge.vector_store_index_id = profile.vector_store_index_id
        knowledge.vector_collection_name = profile.vector_collection_name
        knowledge.vector_namespace = profile.vector_namespace
        knowledge.chunk_strategy = profile.chunk_strategy
        knowledge.chunk_size = profile.chunk_size
        knowledge.chunk_overlap = profile.chunk_overlap
        knowledge.parser = profile.parser
        knowledge.index_version = profile.index_version

    def _resolve_agent_profile(self, agent_id: int) -> KnowledgeIndexProfile:
        try:
            agent = self.db.query(Agent).filter(Agent.id == agent_id).first()
        except Exception:
            return self._default_profile(tenant_id=None, agent_id=agent_id)
        tenant_id = getattr(agent, "tenant_id", None) if agent else None
        if not tenant_id:
            return self._default_profile(tenant_id=tenant_id, agent_id=agent_id)

        config = (
            self.db.query(AgentKnowledgeConfig)
            .filter(
                AgentKnowledgeConfig.tenant_id == tenant_id,
                AgentKnowledgeConfig.agent_id == agent_id,
            )
            .first()
        )
        if not config:
            profile = self._default_profile(tenant_id=tenant_id, agent_id=agent_id)
        else:
            profile = self._profile_from_config(config, tenant_id=tenant_id, agent_id=agent_id)

        if tenant_id:
            try:
                profile = self._profile_with_vector_index(
                    profile,
                    purpose="agent_kb",
                    owner_type="agent",
                    owner_id=agent_id,
                )
                if config:
                    config.vector_store_index_id = profile.vector_store_index_id
                    config.vector_collection_name = profile.vector_collection_name
                    config.vector_namespace = profile.vector_namespace
                    config.updated_at = datetime.utcnow()
                    self.db.flush()
            except Exception:
                logger.exception("Failed to resolve Agent KB vector index")
                raise
        return profile

    def _profile_with_vector_index(
        self,
        profile: KnowledgeIndexProfile,
        *,
        purpose: str,
        owner_type: str,
        owner_id: int,
    ) -> KnowledgeIndexProfile:
        if not profile.tenant_id:
            return profile
        from services.vector_store_index_resolver import VectorStoreIndexResolver

        index = VectorStoreIndexResolver.resolve_or_create(
            self.db,
            tenant_id=profile.tenant_id,
            vector_store_instance_id=profile.vector_store_instance_id,
            purpose=purpose,
            owner_type=owner_type,
            owner_id=owner_id,
            contract={
                "embedding_provider_instance_id": profile.embedding_provider_instance_id,
                "embedding_provider": profile.embedding_provider,
                "embedding_model": profile.embedding_model,
                "embedding_dims": profile.embedding_dims,
                "embedding_metric": profile.embedding_metric,
            },
        )
        return KnowledgeIndexProfile(
            tenant_id=profile.tenant_id,
            agent_id=profile.agent_id,
            embedding_provider_instance_id=profile.embedding_provider_instance_id,
            embedding_provider=profile.embedding_provider,
            embedding_model=profile.embedding_model,
            embedding_dims=profile.embedding_dims,
            embedding_metric=profile.embedding_metric,
            vector_store_instance_id=profile.vector_store_instance_id,
            vector_store_index_id=index.id,
            vector_collection_name=index.physical_collection_name,
            vector_namespace=index.physical_namespace,
            chunk_strategy=profile.chunk_strategy,
            chunk_size=profile.chunk_size,
            chunk_overlap=profile.chunk_overlap,
            parser=profile.parser,
            index_version=profile.index_version,
        )

    def get_knowledge_config(self, agent_id: int, tenant_id: str) -> AgentKnowledgeConfig:
        config = (
            self.db.query(AgentKnowledgeConfig)
            .filter(
                AgentKnowledgeConfig.tenant_id == tenant_id,
                AgentKnowledgeConfig.agent_id == agent_id,
            )
            .first()
        )
        if config:
            return config

        config = AgentKnowledgeConfig(
            tenant_id=tenant_id,
            agent_id=agent_id,
            embedding_provider="local",
            embedding_model=LOCAL_MODEL,
            embedding_dims=LOCAL_DIMS,
            embedding_metric="cosine",
            chunk_strategy="fixed_text",
            chunk_size=_DEFAULT_CHUNK_SIZE,
            chunk_overlap=_DEFAULT_CHUNK_OVERLAP,
            parser="auto",
            search_top_k=_DEFAULT_SEARCH_TOP_K,
            similarity_threshold=_DEFAULT_SIMILARITY_THRESHOLD,
        )
        self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def update_knowledge_config(
        self,
        agent_id: int,
        tenant_id: str,
        data: Dict[str, Any],
    ) -> AgentKnowledgeConfig:
        config = self.get_knowledge_config(agent_id, tenant_id)

        provider = normalize_embedding_provider(data.get("embedding_provider", config.embedding_provider))
        model = data.get("embedding_model", config.embedding_model) or provider_default_model(provider)
        dims = data.get("embedding_dims", config.embedding_dims)
        normalized = validate_embedding_contract(
            provider=provider,
            model=model,
            dimensions=dims,
            allow_ollama_dynamic=False,
        )

        provider_instance_id = data.get(
            "embedding_provider_instance_id",
            config.embedding_provider_instance_id,
        )
        if normalized["provider"] != "local":
            from models import ProviderInstance

            instance = (
                self.db.query(ProviderInstance)
                .filter(
                    ProviderInstance.id == provider_instance_id,
                    ProviderInstance.tenant_id == tenant_id,
                    ProviderInstance.vendor == normalized["provider"],
                    ProviderInstance.is_active == True,
                )
                .first()
            )
            if not instance:
                raise ValueError("A configured embedding provider instance is required")
        else:
            provider_instance_id = None

        vector_store_instance_id = data.get(
            "vector_store_instance_id",
            config.vector_store_instance_id,
        )
        if vector_store_instance_id is not None:
            instance = self.db.query(VectorStoreInstance).filter(
                VectorStoreInstance.id == vector_store_instance_id,
                VectorStoreInstance.tenant_id == tenant_id,
                VectorStoreInstance.is_active == True,
            ).first()
            if not instance:
                raise ValueError("Vector store instance not found")

        chunk_strategy = data.get("chunk_strategy", config.chunk_strategy or "fixed_text")
        if chunk_strategy not in _VALID_CHUNK_STRATEGIES:
            raise ValueError(
                f"Invalid chunk_strategy {chunk_strategy!r}: must be one of {sorted(_VALID_CHUNK_STRATEGIES)}"
            )
        chunk_size = int(data.get("chunk_size", config.chunk_size or _DEFAULT_CHUNK_SIZE))
        chunk_overlap = int(data.get("chunk_overlap", config.chunk_overlap or _DEFAULT_CHUNK_OVERLAP))
        if chunk_size < 200 or chunk_size > 8000:
            raise ValueError("chunk_size must be between 200 and 8000")
        if chunk_overlap < 0 or chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap must be non-negative and smaller than chunk_size")

        parser = data.get("parser", config.parser or "auto")
        if parser not in _VALID_PARSERS:
            raise ValueError(f"Invalid parser {parser!r}: must be one of {sorted(_VALID_PARSERS)}")

        config.embedding_provider_instance_id = provider_instance_id
        config.embedding_provider = normalized["provider"]
        config.embedding_model = normalized["model"]
        config.embedding_dims = int(normalized["dimensions"])
        config.embedding_metric = data.get("embedding_metric", config.embedding_metric or "cosine")
        config.vector_store_instance_id = vector_store_instance_id
        config.vector_store_index_id = None
        config.vector_collection_name = None
        config.vector_namespace = None
        config.chunk_strategy = chunk_strategy
        config.chunk_size = chunk_size
        config.chunk_overlap = chunk_overlap
        config.parser = parser
        config.search_top_k = int(data.get("search_top_k", config.search_top_k or _DEFAULT_SEARCH_TOP_K))
        config.similarity_threshold = float(
            data.get("similarity_threshold", config.similarity_threshold or _DEFAULT_SIMILARITY_THRESHOLD)
        )
        config.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(config)
        return config

    def _embedding_credentials(self, profile: KnowledgeIndexProfile) -> Dict[str, Any]:
        from services.embedding_provider_service import EmbeddingProviderService

        return EmbeddingProviderService.resolve_provider_credentials(
            tenant_id=profile.tenant_id or "",
            provider=profile.embedding_provider,
            provider_instance_id=profile.embedding_provider_instance_id,
            db=self.db,
        )

    def _embedding_provider(self, profile: KnowledgeIndexProfile):
        contract = SimpleNamespace(
            provider=profile.embedding_provider,
            model=profile.embedding_model,
            dimensions=profile.embedding_dims,
            metric=profile.embedding_metric,
            vector_store_instance_id=profile.vector_store_instance_id,
        )
        return get_shared_embedding_service(
            contract=contract,
            credentials=self._embedding_credentials(profile),
        )

    def _vector_id(self, knowledge_id: int, chunk_id: int) -> str:
        return f"knowledge_{knowledge_id}_chunk_{chunk_id}"

    def _sender_key(self, profile: KnowledgeIndexProfile) -> str:
        return f"kb:{profile.tenant_id or 'system'}:{profile.agent_id}"

    def _chroma_collection(self, profile: KnowledgeIndexProfile):
        return self.chroma_client.get_or_create_collection(
            name=profile.vector_collection_name,
            metadata={
                "description": f"Knowledge base for tenant {profile.tenant_id or 'system'} agent {profile.agent_id}",
                "purpose": "knowledge_base",
                "embedding_dimensions": profile.embedding_dims,
            },
        )

    def _uses_builtin_chroma(self, profile: KnowledgeIndexProfile) -> bool:
        if profile.vector_store_instance_id is None:
            return True
        instance = self.db.query(VectorStoreInstance).filter(
            VectorStoreInstance.id == profile.vector_store_instance_id,
            VectorStoreInstance.tenant_id == profile.tenant_id,
        ).first()
        if not instance:
            return True
        return (instance.vendor or "").lower() in {"chroma", "chromadb"}

    def _external_vector_provider(self, profile: KnowledgeIndexProfile):
        if profile.vector_store_instance_id is None:
            return None

        instance = self.db.query(VectorStoreInstance).filter(
            VectorStoreInstance.id == profile.vector_store_instance_id,
            VectorStoreInstance.tenant_id == profile.tenant_id,
            VectorStoreInstance.is_active == True,
        ).first()
        if not instance:
            return None

        vendor = (instance.vendor or "").lower()
        if vendor in {"chroma", "chromadb"}:
            return None

        from services.vector_store_instance_service import VectorStoreInstanceService
        from agent.memory.providers.base import ProviderConnectionError

        credentials = VectorStoreInstanceService.resolve_credentials(instance, self.db)
        extra = instance.extra_config or {}
        if not isinstance(extra, dict):
            extra = {}

        if vendor == "qdrant":
            from agent.memory.providers.qdrant_adapter import QdrantVectorAdapter

            if not instance.base_url:
                raise ProviderConnectionError("Qdrant requires a base URL")
            return QdrantVectorAdapter(
                url=instance.base_url,
                collection_name=profile.vector_collection_name,
                api_key=credentials.get("api_key"),
                embedding_dims=profile.embedding_dims,
            )
        if vendor == "mongodb":
            from agent.memory.providers.mongodb_adapter import MongoDBVectorAdapter

            connection_string = credentials.get("connection_string") or instance.base_url
            if not connection_string:
                raise ProviderConnectionError("MongoDB requires a connection string")
            return MongoDBVectorAdapter(
                connection_string=connection_string,
                database_name=extra.get("database_name", "tsushin"),
                collection_name=profile.vector_collection_name,
                index_name=extra.get("index_name", "vector_index"),
                embedding_dims=profile.embedding_dims,
                use_native_search=extra.get("use_native_search", True),
            )
        if vendor == "pinecone":
            from agent.memory.providers.pinecone_adapter import PineconeVectorAdapter

            api_key = credentials.get("api_key", "")
            if not api_key:
                raise ProviderConnectionError("Pinecone requires an API key")
            base_index = extra.get("index_name") or "tsushin"
            index_name = (
                profile.vector_collection_name.replace("_", "-")
                if str(profile.embedding_dims) not in str(base_index)
                else base_index
            )
            return PineconeVectorAdapter(
                api_key=api_key,
                index_name=index_name,
                namespace=profile.vector_namespace,
                environment=extra.get("environment", ""),
                embedding_dims=profile.embedding_dims,
            )

        return None

    def _vector_metadata(
        self,
        profile: KnowledgeIndexProfile,
        knowledge: AgentKnowledge,
        chunk: KnowledgeChunk,
        chunk_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        return {
            "purpose": "knowledge_base",
            "tenant_id": profile.tenant_id or "",
            "agent_id": profile.agent_id,
            "knowledge_id": knowledge.id,
            "document_id": knowledge.id,
            "chunk_id": chunk.id,
            "chunk_index": chunk.chunk_index,
            "document_name": knowledge.document_name,
            "embedding_provider": profile.embedding_provider,
            "embedding_model": profile.embedding_model,
            "embedding_dims": profile.embedding_dims,
            "chunk_strategy": profile.chunk_strategy,
            "parser": profile.parser,
            "content": chunk.content[:200],
            "json_path": chunk_data.get("json_path", ""),
            "row_start": chunk_data.get("row_start", 0),
            "row_end": chunk_data.get("row_end", 0),
        }

    async def _store_embeddings(
        self,
        profile: KnowledgeIndexProfile,
        knowledge: AgentKnowledge,
        chunks: List[KnowledgeChunk],
        chunk_payloads: List[Dict[str, Any]],
        embeddings: List[List[float]],
    ) -> None:
        records = []
        for chunk, payload, embedding in zip(chunks, chunk_payloads, embeddings):
            if len(embedding) != profile.embedding_dims:
                raise ValueError(
                    f"Embedding dimension mismatch: expected {profile.embedding_dims}, got {len(embedding)}"
                )
            metadata = self._vector_metadata(profile, knowledge, chunk, payload)
            records.append(
                {
                    "message_id": self._vector_id(knowledge.id, chunk.id),
                    "sender_key": self._sender_key(profile),
                    "text": chunk.content,
                    "embedding": embedding,
                    "metadata": metadata,
                }
            )

        provider = self._external_vector_provider(profile)
        if provider is not None:
            await provider.add_batch(records)
            return

        collection = self._chroma_collection(profile)
        collection.upsert(
            ids=[record["message_id"] for record in records],
            embeddings=[record["embedding"] for record in records],
            metadatas=[
                {
                    "sender_key": record["sender_key"],
                    "text": record["text"][:1000],
                    **record["metadata"],
                }
                for record in records
            ],
            documents=[record["text"] for record in records],
        )

    async def _delete_vectors_for_chunks(
        self,
        profile: KnowledgeIndexProfile,
        knowledge: AgentKnowledge,
        chunks: List[KnowledgeChunk],
    ) -> None:
        provider = self._external_vector_provider(profile)
        if provider is not None:
            for chunk in chunks:
                try:
                    await provider.delete_message(self._vector_id(knowledge.id, chunk.id))
                except Exception as exc:
                    logger.warning("Error deleting KB vector %s: %s", chunk.id, exc)
            return

        try:
            collection = self.chroma_client.get_collection(name=profile.vector_collection_name)
            ids = [self._vector_id(knowledge.id, chunk.id) for chunk in chunks]
            if ids:
                collection.delete(ids=ids)
        except Exception as exc:
            logger.warning("Error deleting KB vectors from Chroma: %s", exc)

    def _run_async_cleanup(self, coro) -> None:
        try:
            asyncio.run(coro)
        except RuntimeError:
            loop = asyncio.new_event_loop()
            try:
                loop.run_until_complete(coro)
            finally:
                loop.close()

    def _metadata_path(self, knowledge: AgentKnowledge) -> Path:
        return Path(f"{knowledge.file_path}{_DOCUMENT_METADATA_SUFFIX}")

    def _read_document_metadata(self, knowledge: AgentKnowledge) -> Dict[str, Any]:
        metadata_path = self._metadata_path(knowledge)
        if not metadata_path.exists():
            return {}

        try:
            with metadata_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except json.JSONDecodeError as exc:
            raise KnowledgeMetadataError(
                f"Knowledge metadata is unreadable for document {knowledge.id}"
            ) from exc
        except Exception as exc:
            raise KnowledgeMetadataError(
                f"Knowledge metadata could not be read for document {knowledge.id}"
            ) from exc

        if not isinstance(data, dict):
            raise KnowledgeMetadataError(
                f"Knowledge metadata is malformed for document {knowledge.id}"
            )

        tags = data.get("tags", [])
        if tags is not None and not isinstance(tags, list):
            raise KnowledgeMetadataError(
                f"Knowledge metadata tags are malformed for document {knowledge.id}"
            )

        return data

    def _write_document_metadata_atomically(self, knowledge: AgentKnowledge, metadata: Dict[str, Any]) -> None:
        metadata_path = self._metadata_path(knowledge)
        payload = dict(metadata or {})
        payload["tags"] = normalize_document_tags(payload.get("tags"))

        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        temp_path: Optional[Path] = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=str(metadata_path.parent),
                prefix=f".{metadata_path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=True, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(temp_path, metadata_path)
        except Exception as exc:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            raise KnowledgeMetadataError(
                f"Knowledge metadata could not be written for document {knowledge.id}"
            ) from exc

    def _capture_metadata_snapshot(self, knowledge: AgentKnowledge) -> Optional[bytes]:
        metadata_path = self._metadata_path(knowledge)
        if not metadata_path.exists():
            return None
        return metadata_path.read_bytes()

    def _restore_metadata_snapshot(self, knowledge: AgentKnowledge, snapshot: Optional[bytes]) -> None:
        metadata_path = self._metadata_path(knowledge)
        if snapshot is None:
            metadata_path.unlink(missing_ok=True)
            return

        temp_path: Optional[Path] = None
        try:
            metadata_path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                mode="wb",
                dir=str(metadata_path.parent),
                prefix=f".{metadata_path.name}.",
                suffix=".restore.tmp",
                delete=False,
            ) as handle:
                temp_path = Path(handle.name)
                handle.write(snapshot)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, metadata_path)
        except Exception as exc:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
            raise KnowledgeMetadataError(
                f"Knowledge metadata rollback failed for document {knowledge.id}"
            ) from exc

    def _remove_metadata_file(self, knowledge: AgentKnowledge) -> None:
        self._metadata_path(knowledge).unlink(missing_ok=True)

    def get_document_tags(self, knowledge: AgentKnowledge) -> List[str]:
        return normalize_document_tags(self._read_document_metadata(knowledge).get("tags"))

    def attach_document_metadata(self, knowledge: AgentKnowledge) -> AgentKnowledge:
        setattr(knowledge, "tags", self.get_document_tags(knowledge))
        return knowledge

    def update_document(
        self,
        knowledge_id: int,
        *,
        document_name: Optional[str] = None,
        tags: Optional[List[str]] = None,
    ) -> Optional[AgentKnowledge]:
        """Update the editable document metadata for an AgentKnowledge record."""
        knowledge = self.db.query(AgentKnowledge).get(knowledge_id)
        if not knowledge:
            return None

        changed = False
        metadata_changed = False

        if document_name is not None:
            cleaned_name = sanitize_document_name(document_name)
            if cleaned_name != knowledge.document_name:
                knowledge.document_name = cleaned_name
                changed = True

        metadata = self._read_document_metadata(knowledge)
        if tags is not None:
            normalized_tags = normalize_document_tags(tags)
            if normalized_tags != normalize_document_tags(metadata.get("tags")):
                metadata["tags"] = normalized_tags
                metadata_changed = True
                changed = True

        if changed:
            metadata_snapshot = self._capture_metadata_snapshot(knowledge)
            try:
                knowledge.updated_at = datetime.utcnow()
                self.db.flush()
                if metadata_changed:
                    self._write_document_metadata_atomically(knowledge, metadata)
                self.db.commit()
                self.db.refresh(knowledge)
            except Exception:
                self.db.rollback()
                if metadata_changed:
                    self._restore_metadata_snapshot(knowledge, metadata_snapshot)
                raise

        return self.attach_document_metadata(knowledge)

    def upload_document(
        self,
        agent_id: int,
        file_path: str,
        document_name: str,
        document_type: str
    ) -> AgentKnowledge:
        """
        Upload a document to the knowledge base.

        Args:
            agent_id: ID of the agent
            file_path: Path to the uploaded file
            document_name: Name of the document
            document_type: Type of document (txt, csv, json, pdf, docx)

        Returns:
            AgentKnowledge record
        """
        stored_path: Optional[Path] = None
        knowledge: Optional[AgentKnowledge] = None
        try:
            # Get file size
            file_size = os.path.getsize(file_path)
            profile = self._resolve_agent_profile(agent_id)

            # Copy file to storage directory
            agent_dir = self.storage_dir / f"agent_{agent_id}"
            agent_dir.mkdir(exist_ok=True)

            # Generate unique filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            file_ext = Path(file_path).suffix
            stored_filename = f"{timestamp}_{document_name}"
            if not stored_filename.endswith(file_ext):
                stored_filename += file_ext

            stored_path = agent_dir / stored_filename
            shutil.copy2(file_path, stored_path)

            # Create database record
            knowledge = AgentKnowledge(
                agent_id=agent_id,
                tenant_id=profile.tenant_id,
                document_name=document_name,
                document_type=document_type,
                file_path=str(stored_path),
                file_size_bytes=file_size,
                status="pending",
            )
            self._snapshot_profile(knowledge, profile)

            self.db.add(knowledge)
            self.db.flush()
            self._write_document_metadata_atomically(knowledge, {"tags": []})
            self.db.commit()
            self.db.refresh(knowledge)

            logger.info(f"Document uploaded: {document_name} (ID: {knowledge.id})")
            return knowledge

        except Exception as e:
            logger.error(f"Error uploading document: {e}")
            self.db.rollback()
            if knowledge is not None:
                try:
                    self._remove_metadata_file(knowledge)
                except Exception as cleanup_exc:
                    logger.warning(
                        "Error cleaning metadata after upload failure for knowledge_id=%s: %s",
                        getattr(knowledge, "id", None),
                        cleanup_exc,
                    )
            if stored_path is not None and stored_path.exists():
                try:
                    stored_path.unlink()
                except Exception as cleanup_exc:
                    logger.warning(
                        "Error cleaning stored file after upload failure for %s: %s",
                        stored_path,
                        cleanup_exc,
                    )
            raise

    async def process_document(self, knowledge_id: int) -> bool:
        """
        Process a document: extract text, create chunks, generate embeddings.

        Args:
            knowledge_id: ID of the AgentKnowledge record

        Returns:
            True if successful, False otherwise
        """
        knowledge = self.db.query(AgentKnowledge).get(knowledge_id)
        if not knowledge:
            logger.error(f"Knowledge record not found: {knowledge_id}")
            return False

        try:
            # Update status
            knowledge.status = "processing"
            self.db.commit()

            profile = self._profile_from_knowledge(knowledge)

            # Process document and create chunks using the snapshotted strategy.
            processor = DocumentProcessor(
                chunk_size=profile.chunk_size,
                chunk_overlap=profile.chunk_overlap,
                chunk_strategy=profile.chunk_strategy,
            )
            chunks = processor.process_document(
                knowledge.file_path,
                knowledge.document_type,
                chunk_strategy=profile.chunk_strategy,
            )

            if not chunks:
                raise ValueError("No chunks created from document")

            chunk_records: List[KnowledgeChunk] = []

            # Store chunks in database first so vector metadata can reference stable ids.
            for chunk_data in chunks:
                chunk = KnowledgeChunk(
                    knowledge_id=knowledge.id,
                    chunk_index=chunk_data["chunk_index"],
                    content=chunk_data["content"],
                    char_count=chunk_data["char_count"],
                    metadata_json={
                        "start_pos": chunk_data["start_pos"],
                        "end_pos": chunk_data["end_pos"],
                        "chunk_strategy": chunk_data.get("chunk_strategy", profile.chunk_strategy),
                        "json_path": chunk_data.get("json_path"),
                        "row_start": chunk_data.get("row_start"),
                        "row_end": chunk_data.get("row_end"),
                    },
                )
                self.db.add(chunk)
                self.db.flush()
                chunk_records.append(chunk)

            embedder = self._embedding_provider(profile)
            embeddings = await embedder.embed_batch_chunked_async(
                [chunk.content for chunk in chunk_records],
                batch_size=32,
                task_type="RETRIEVAL_DOCUMENT",
            )
            if len(embeddings) != len(chunk_records):
                raise ValueError(
                    f"Embedding provider returned {len(embeddings)} vectors for {len(chunk_records)} chunks"
                )
            await self._store_embeddings(profile, knowledge, chunk_records, chunks, embeddings)

            # Update knowledge record
            knowledge.num_chunks = len(chunks)
            knowledge.status = "completed"
            knowledge.processed_date = datetime.utcnow()
            self.db.commit()

            logger.info(f"Document processed successfully: {knowledge.document_name} ({len(chunks)} chunks)")
            return True

        except Exception as e:
            logger.error(f"Error processing document {knowledge_id}: {e}")
            knowledge.status = "failed"
            knowledge.error_message = str(e)
            self.db.commit()
            return False

    async def search_knowledge(
        self,
        agent_id: int,
        query: str,
        max_results: int = 5,
        similarity_threshold: float = 0.3
    ) -> List[Dict]:
        """
        Search agent's knowledge base using semantic similarity.

        Args:
            agent_id: ID of the agent
            query: Search query
            max_results: Maximum number of results to return
            similarity_threshold: Minimum similarity score (0.0-1.0)

        Returns:
            List of relevant chunks with metadata
        """
        try:
            knowledge_rows = (
                self.db.query(AgentKnowledge)
                .filter(
                    AgentKnowledge.agent_id == agent_id,
                    AgentKnowledge.status == "completed",
                )
                .all()
            )
            if not knowledge_rows:
                return []

            grouped: Dict[Tuple[Any, ...], KnowledgeIndexProfile] = {}
            for row in knowledge_rows:
                profile = self._profile_from_knowledge(row)
                grouped[profile.grouping_key()] = profile

            formatted_results: List[Dict[str, Any]] = []
            for profile in grouped.values():
                embedder = self._embedding_provider(profile)
                query_embedding = await embedder.embed_text_async(
                    query,
                    task_type="RETRIEVAL_QUERY",
                )
                if len(query_embedding) != profile.embedding_dims:
                    logger.warning(
                        "Skipping KB profile due to query embedding dimension mismatch: "
                        "expected=%s actual=%s profile=%s",
                        profile.embedding_dims,
                        len(query_embedding),
                        profile.grouping_key(),
                    )
                    continue

                provider = self._external_vector_provider(profile)
                records = []
                if provider is not None:
                    records = await provider.search_similar(
                        query_embedding,
                        limit=max_results,
                        sender_key=self._sender_key(profile),
                    )
                else:
                    try:
                        collection = self.chroma_client.get_collection(
                            name=profile.vector_collection_name
                        )
                    except Exception:
                        continue
                    if collection.count() == 0:
                        continue
                    raw = collection.query(
                        query_embeddings=[query_embedding],
                        n_results=max_results,
                    )
                    if raw.get("ids") and raw["ids"][0]:
                        from agent.memory.providers.base import VectorRecord

                        for index in range(len(raw["ids"][0])):
                            meta = raw["metadatas"][0][index] if raw.get("metadatas") else {}
                            records.append(
                                VectorRecord(
                                    message_id=raw["ids"][0][index],
                                    text=raw["documents"][0][index] if raw.get("documents") else "",
                                    distance=raw["distances"][0][index] if raw.get("distances") else 0.0,
                                    sender_key=meta.get("sender_key"),
                                    metadata=meta or {},
                                )
                            )

                for record in records:
                    metadata = record.metadata or {}
                    is_legacy_profile = (
                        profile.index_version == 0
                        or profile.vector_collection_name == self._legacy_collection_name(agent_id)
                    )
                    if not is_legacy_profile:
                        if metadata.get("purpose") != "knowledge_base":
                            continue
                        if str(metadata.get("tenant_id") or "") != str(profile.tenant_id or ""):
                            continue
                        if int(metadata.get("agent_id") or 0) != agent_id:
                            continue
                    similarity = 1.0 / (1.0 + float(record.distance or 0.0))
                    if similarity < similarity_threshold:
                        continue
                    chunk_id = metadata.get("chunk_id")
                    if not chunk_id:
                        continue
                    chunk = self.db.query(KnowledgeChunk).get(int(chunk_id))
                    if not chunk:
                        continue
                    knowledge = self.db.query(AgentKnowledge).get(chunk.knowledge_id)
                    if not knowledge or knowledge.agent_id != agent_id:
                        continue
                    formatted_results.append({
                        "chunk_id": chunk.id,
                        "knowledge_id": knowledge.id,
                        "document_name": knowledge.document_name,
                        "content": chunk.content,
                        "similarity": similarity,
                        "chunk_index": chunk.chunk_index,
                    })

            formatted_results.sort(key=lambda item: item["similarity"], reverse=True)
            formatted_results = formatted_results[:max_results]

            logger.info(f"Knowledge search for agent {agent_id}: {len(formatted_results)} results")
            return formatted_results

        except Exception as e:
            logger.error(f"Error searching knowledge base: {e}")
            return []

    def get_agent_knowledge(self, agent_id: int) -> List[AgentKnowledge]:
        """
        Get all knowledge documents for an agent.

        Args:
            agent_id: ID of the agent

        Returns:
            List of AgentKnowledge records
        """
        return self.db.query(AgentKnowledge).filter(
            AgentKnowledge.agent_id == agent_id
        ).order_by(AgentKnowledge.upload_date.desc()).all()

    def get_knowledge_by_id(self, knowledge_id: int) -> Optional[AgentKnowledge]:
        """
        Get a specific knowledge document.

        Args:
            knowledge_id: ID of the knowledge document

        Returns:
            AgentKnowledge record or None
        """
        return self.db.query(AgentKnowledge).get(knowledge_id)

    def get_knowledge_chunks(self, knowledge_id: int) -> List[KnowledgeChunk]:
        """
        Get all chunks for a knowledge document.

        Args:
            knowledge_id: ID of the knowledge document

        Returns:
            List of KnowledgeChunk records
        """
        return self.db.query(KnowledgeChunk).filter(
            KnowledgeChunk.knowledge_id == knowledge_id
        ).order_by(KnowledgeChunk.chunk_index).all()

    def delete_knowledge(self, knowledge_id: int) -> bool:
        """
        Delete a knowledge document and all its chunks.

        Args:
            knowledge_id: ID of the knowledge document

        Returns:
            True if successful, False otherwise
        """
        try:
            knowledge = self.db.query(AgentKnowledge).get(knowledge_id)
            if not knowledge:
                logger.error(f"Knowledge record not found: {knowledge_id}")
                return False

            # Delete chunks from vector store
            chunks = self.get_knowledge_chunks(knowledge_id)
            profile = self._profile_from_knowledge(knowledge)
            self._run_async_cleanup(self._delete_vectors_for_chunks(profile, knowledge, chunks))

            # Delete database records (chunks will cascade)
            self.db.delete(knowledge)
            self.db.commit()

            # Delete file
            try:
                file_path = Path(knowledge.file_path)
                if file_path.exists():
                    file_path.unlink()
            except Exception as e:
                logger.warning(f"Error deleting file {knowledge.file_path}: {e}")

            try:
                self._remove_metadata_file(knowledge)
            except Exception as e:
                logger.warning(f"Error deleting document metadata for knowledge {knowledge_id}: {e}")

            logger.info(f"Knowledge deleted: {knowledge.document_name} (ID: {knowledge_id})")
            return True

        except Exception as e:
            logger.error(f"Error deleting knowledge {knowledge_id}: {e}")
            self.db.rollback()
            return False

    def prepare_reprocess_document(self, knowledge_id: int) -> Optional[AgentKnowledge]:
        """Remove old chunks/vectors and snapshot the current agent KB config."""
        knowledge = self.db.query(AgentKnowledge).get(knowledge_id)
        if not knowledge:
            return None

        old_profile = self._profile_from_knowledge(knowledge)
        chunks = self.get_knowledge_chunks(knowledge_id)
        self._run_async_cleanup(self._delete_vectors_for_chunks(old_profile, knowledge, chunks))
        for chunk in chunks:
            self.db.delete(chunk)

        new_profile = self._resolve_agent_profile(knowledge.agent_id)
        self._snapshot_profile(knowledge, new_profile)
        knowledge.status = "pending"
        knowledge.num_chunks = 0
        knowledge.error_message = None
        knowledge.processed_date = None
        knowledge.updated_at = datetime.utcnow()
        self.db.commit()
        self.db.refresh(knowledge)
        return knowledge

    def get_knowledge_stats(self, agent_id: int) -> Dict:
        """
        Get statistics about agent's knowledge base.

        Args:
            agent_id: ID of the agent

        Returns:
            Dictionary with statistics
        """
        knowledge_list = self.get_agent_knowledge(agent_id)

        total_documents = len(knowledge_list)
        total_chunks = sum(k.num_chunks for k in knowledge_list)
        total_size_bytes = sum(k.file_size_bytes for k in knowledge_list)

        completed = sum(1 for k in knowledge_list if k.status == "completed")
        processing = sum(1 for k in knowledge_list if k.status == "processing")
        failed = sum(1 for k in knowledge_list if k.status == "failed")

        return {
            "total_documents": total_documents,
            "total_chunks": total_chunks,
            "total_size_bytes": total_size_bytes,
            "total_size_mb": round(total_size_bytes / (1024 * 1024), 2),
            "completed": completed,
            "processing": processing,
            "failed": failed
        }
