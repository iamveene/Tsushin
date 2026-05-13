"""Resolve immutable physical vector indexes for a vector store instance."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models import VectorStoreIndex, VectorStoreInstance


_DEFAULT_PROVIDER = "local"
_DEFAULT_MODEL = "all-MiniLM-L6-v2"
_DEFAULT_DIMS = 384
_DEFAULT_METRIC = "cosine"


@dataclass(frozen=True)
class VectorStoreContract:
    embedding_provider: str
    embedding_model: str
    embedding_dims: int
    embedding_metric: str
    embedding_provider_instance_id: Optional[int] = None
    embedding_task_document: Optional[str] = None
    embedding_task_query: Optional[str] = None

    def canonical_dict(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "embedding_provider": self.embedding_provider,
            "embedding_model": self.embedding_model,
            "embedding_dims": self.embedding_dims,
            "embedding_metric": self.embedding_metric,
        }
        if self.embedding_provider_instance_id is not None:
            data["embedding_provider_instance_id"] = self.embedding_provider_instance_id
        if self.embedding_task_document:
            data["embedding_task_document"] = self.embedding_task_document
        if self.embedding_task_query:
            data["embedding_task_query"] = self.embedding_task_query
        return data

    @property
    def contract_hash(self) -> str:
        payload = json.dumps(self.canonical_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


class VectorStoreIndexResolver:
    """Tenant-scoped resolver for reusable physical vector indexes."""

    def __init__(self, db: Optional[Session] = None):
        self.db = db

    @classmethod
    def normalize_contract(cls, contract: Optional[Dict[str, Any]] = None) -> VectorStoreContract:
        if isinstance(contract, VectorStoreContract):
            return contract
        if hasattr(contract, "canonical_dict"):
            raw = contract.canonical_dict()
        else:
            raw = dict(contract or {})

        provider = raw.get("embedding_provider", raw.get("provider", _DEFAULT_PROVIDER))
        model = raw.get("embedding_model", raw.get("model", _DEFAULT_MODEL))
        dims = raw.get("embedding_dims", raw.get("dimensions", raw.get("dims", _DEFAULT_DIMS)))
        metric = raw.get("embedding_metric", raw.get("metric", _DEFAULT_METRIC))

        try:
            dims_int = int(dims)
        except (TypeError, ValueError) as exc:
            raise ValueError("embedding_dims must be an integer") from exc
        if dims_int <= 0:
            raise ValueError("embedding_dims must be greater than zero")

        provider_instance_id = raw.get("embedding_provider_instance_id")
        if provider_instance_id in ("", None):
            provider_instance_id = None
        elif provider_instance_id is not None:
            try:
                provider_instance_id = int(provider_instance_id)
            except (TypeError, ValueError) as exc:
                raise ValueError("embedding_provider_instance_id must be an integer") from exc

        return VectorStoreContract(
            embedding_provider=str(provider or _DEFAULT_PROVIDER).strip().lower(),
            embedding_model=str(model or _DEFAULT_MODEL).strip(),
            embedding_dims=dims_int,
            embedding_metric=str(metric or _DEFAULT_METRIC).strip().lower(),
            embedding_provider_instance_id=provider_instance_id,
            embedding_task_document=cls._optional_str(raw.get("embedding_task_document")),
            embedding_task_query=cls._optional_str(raw.get("embedding_task_query")),
        )

    @classmethod
    def resolve_or_create(
        cls,
        db: Session,
        *,
        tenant_id: str,
        vector_store_instance_id: Optional[int],
        purpose: str,
        owner_type: str,
        owner_id: int = 0,
        contract: Optional[Dict[str, Any]] = None,
        physical_collection_name: Optional[str] = None,
        physical_index_name: Optional[str] = None,
        physical_namespace: Optional[str] = None,
        create: bool = True,
    ) -> Optional[VectorStoreIndex]:
        instance = (
            cls._get_instance(db, tenant_id, vector_store_instance_id)
            if vector_store_instance_id is not None
            else SimpleNamespace(vendor="chromadb")
        )
        normalized = cls.normalize_contract(contract)
        purpose_slug = cls._validate_component("purpose", purpose, 32)
        owner_type_slug = cls._validate_component("owner_type", owner_type, 32)
        owner_id_int = cls._coerce_owner_id(owner_id)

        existing = cls._query_existing(
            db,
            tenant_id=tenant_id,
            vector_store_instance_id=vector_store_instance_id,
            purpose=purpose_slug,
            owner_type=owner_type_slug,
            owner_id=owner_id_int,
            contract_hash=normalized.contract_hash,
        ).first()
        if existing:
            return existing

        if not create:
            return None

        physical = cls._resolve_physical_names(
            instance=instance,
            tenant_id=tenant_id,
            purpose=purpose_slug,
            owner_type=owner_type_slug,
            owner_id=owner_id_int,
            contract_hash=normalized.contract_hash,
            physical_collection_name=physical_collection_name,
            physical_index_name=physical_index_name,
            physical_namespace=physical_namespace,
        )

        index = VectorStoreIndex(
            tenant_id=tenant_id,
            vector_store_instance_id=vector_store_instance_id,
            purpose=purpose_slug,
            owner_type=owner_type_slug,
            owner_id=owner_id_int,
            embedding_provider_instance_id=normalized.embedding_provider_instance_id,
            embedding_provider=normalized.embedding_provider,
            embedding_model=normalized.embedding_model,
            embedding_dims=normalized.embedding_dims,
            embedding_metric=normalized.embedding_metric,
            embedding_task_document=normalized.embedding_task_document,
            embedding_task_query=normalized.embedding_task_query,
            physical_collection_name=physical["collection_name"],
            physical_index_name=physical["index_name"],
            physical_namespace=physical["namespace"],
            contract_hash=normalized.contract_hash,
            is_active=True,
        )

        db.add(index)
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return cls._query_existing(
                db,
                tenant_id=tenant_id,
                vector_store_instance_id=vector_store_instance_id,
                purpose=purpose_slug,
                owner_type=owner_type_slug,
                owner_id=owner_id_int,
                contract_hash=normalized.contract_hash,
            ).first()

        db.refresh(index)
        return index

    @classmethod
    def to_dict(cls, index: VectorStoreIndex) -> Dict[str, Any]:
        contract = {
            "embedding_provider_instance_id": index.embedding_provider_instance_id,
            "embedding_provider": index.embedding_provider,
            "embedding_model": index.embedding_model,
            "embedding_dims": index.embedding_dims,
            "embedding_metric": index.embedding_metric,
            "embedding_task_document": index.embedding_task_document,
            "embedding_task_query": index.embedding_task_query,
        }
        contract = {key: value for key, value in contract.items() if value is not None}
        return {
            "id": index.id,
            "tenant_id": index.tenant_id,
            "vector_store_instance_id": index.vector_store_instance_id,
            "purpose": index.purpose,
            "owner_type": index.owner_type,
            "owner_id": index.owner_id,
            "contract_hash": index.contract_hash,
            "contract": contract,
            "embedding_provider_instance_id": index.embedding_provider_instance_id,
            "embedding_provider": index.embedding_provider,
            "embedding_model": index.embedding_model,
            "embedding_dims": index.embedding_dims,
            "embedding_metric": index.embedding_metric,
            "embedding_task_document": index.embedding_task_document,
            "embedding_task_query": index.embedding_task_query,
            "physical_collection_name": index.physical_collection_name,
            "physical_index_name": index.physical_index_name,
            "physical_namespace": index.physical_namespace,
            "is_active": index.is_active,
            "created_at": index.created_at.isoformat() if index.created_at else None,
            "updated_at": index.updated_at.isoformat() if index.updated_at else None,
        }

    @classmethod
    def to_response(cls, index: VectorStoreIndex) -> Dict[str, Any]:
        return cls.to_dict(index)

    @classmethod
    def _get_instance(
        cls,
        db: Session,
        tenant_id: str,
        vector_store_instance_id: Optional[int],
    ) -> VectorStoreInstance:
        instance = db.query(VectorStoreInstance).filter(
            VectorStoreInstance.id == vector_store_instance_id,
            VectorStoreInstance.tenant_id == tenant_id,
            VectorStoreInstance.is_active == True,
        ).first()
        if not instance:
            raise ValueError("Vector store instance not found")
        return instance

    @classmethod
    def _query_existing(
        cls,
        db: Session,
        *,
        tenant_id: str,
        vector_store_instance_id: Optional[int],
        purpose: str,
        owner_type: str,
        owner_id: int,
        contract_hash: str,
    ):
        return db.query(VectorStoreIndex).filter(
            VectorStoreIndex.tenant_id == tenant_id,
            VectorStoreIndex.vector_store_instance_id == vector_store_instance_id,
            VectorStoreIndex.purpose == purpose,
            VectorStoreIndex.owner_type == owner_type,
            VectorStoreIndex.owner_id == owner_id,
            VectorStoreIndex.contract_hash == contract_hash,
            VectorStoreIndex.is_active == True,
        )

    @classmethod
    def _resolve_physical_names(
        cls,
        *,
        instance: VectorStoreInstance,
        tenant_id: str,
        purpose: str,
        owner_type: str,
        owner_id: int,
        contract_hash: str,
        physical_collection_name: Optional[str],
        physical_index_name: Optional[str],
        physical_namespace: Optional[str],
    ) -> Dict[str, str]:
        base = cls._physical_base(tenant_id, purpose, owner_type, owner_id, contract_hash)
        vendor = str(instance.vendor or "").lower()

        collection_name = cls._optional_str(physical_collection_name)
        index_name = cls._optional_str(physical_index_name)
        namespace = cls._optional_str(physical_namespace)

        if not collection_name:
            collection_name = base
        if namespace is None:
            namespace = base
        if not index_name:
            index_name = cls._default_index_name(vendor, base)

        return {
            "collection_name": collection_name,
            "index_name": index_name,
            "namespace": namespace,
        }

    @classmethod
    def _physical_base(
        cls,
        tenant_id: str,
        purpose: str,
        owner_type: str,
        owner_id: int,
        contract_hash: str,
    ) -> str:
        tenant_hash = hashlib.sha256(str(tenant_id).encode("utf-8")).hexdigest()[:8]
        owner_hash = hashlib.sha256(f"{owner_type}:{owner_id}".encode("utf-8")).hexdigest()[:8]
        purpose_part = cls._slug(purpose, 24)
        owner_part = cls._slug(owner_type, 16)
        return f"tsn_t{tenant_hash}_{purpose_part}_{owner_part}_{owner_hash}_{contract_hash[:12]}"

    @classmethod
    def _default_index_name(cls, vendor: str, base: str) -> str:
        if vendor == "pinecone":
            return base.replace("_", "-")[:45].rstrip("-") or "tsushin-index"
        if vendor == "mongodb":
            return f"{base}_idx"[:255]
        return base

    @staticmethod
    def _coerce_owner_id(owner_id: Any) -> int:
        if owner_id in ("", None):
            return 0
        try:
            owner_id_int = int(owner_id)
        except (TypeError, ValueError) as exc:
            raise ValueError("owner_id must be an integer") from exc
        if owner_id_int < 0:
            raise ValueError("owner_id must be non-negative")
        return owner_id_int

    @classmethod
    def _validate_component(cls, name: str, value: Any, max_length: int) -> str:
        text = cls._slug(value, max_length)
        if not text:
            raise ValueError(f"{name} is required")
        return text

    @staticmethod
    def _slug(value: Any, max_length: int) -> str:
        text = str(value or "").strip().lower()
        text = re.sub(r"[^a-z0-9_:-]+", "_", text)
        text = re.sub(r"_+", "_", text).strip("_:-")
        return text[:max_length]

    @staticmethod
    def _optional_str(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text or None


VectorIndexContract = VectorStoreContract
