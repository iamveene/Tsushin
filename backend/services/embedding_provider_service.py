"""Embedding provider option and live-test service."""

from __future__ import annotations

import math
import time
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from agent.memory.embedding_catalog import (
    LOCAL_DIMS,
    LOCAL_MODEL,
    list_model_specs,
    provider_default_model,
    validate_embedding_contract,
)
from agent.memory.embedding_service import get_shared_embedding_service
from models import ProviderInstance
from services.provider_instance_service import (
    ProviderInstanceService,
    get_vendor_default_base_url,
)


EMBEDDING_CAPABLE_VENDORS = {"openai", "gemini", "ollama"}


def _model_names_from_instance(instance: ProviderInstance) -> List[str]:
    names: List[str] = []
    for candidate in (instance.available_models or []):
        if isinstance(candidate, str) and candidate.strip():
            names.append(candidate.strip().removeprefix("models/"))
    extra = instance.extra_config or {}
    if isinstance(extra, dict):
        for key in ("pulled_models", "embedding_models"):
            for candidate in extra.get(key) or []:
                if isinstance(candidate, str) and candidate.strip():
                    names.append(candidate.strip().removeprefix("models/"))
    return sorted(set(names))


class EmbeddingProviderService:
    """Lists and tests embedding-capable configured provider instances."""

    @staticmethod
    def list_options(tenant_id: str, db: Session) -> Dict[str, Any]:
        options: List[Dict[str, Any]] = [
            {
                "provider": "local",
                "provider_instance_id": None,
                "instance_name": "Built-in local embeddings",
                "vendor": "local",
                "configured": True,
                "health_status": "healthy",
                "base_url": None,
                "models": [spec.to_dict() for spec in list_model_specs("local")],
                "default_model": LOCAL_MODEL,
                "default_dimensions": LOCAL_DIMS,
                "test_status": "built_in",
            }
        ]

        instances = (
            db.query(ProviderInstance)
            .filter(
                ProviderInstance.tenant_id == tenant_id,
                ProviderInstance.is_active == True,
                ProviderInstance.vendor.in_(sorted(EMBEDDING_CAPABLE_VENDORS)),
            )
            .order_by(
                ProviderInstance.vendor,
                ProviderInstance.is_default.desc(),
                ProviderInstance.instance_name,
            )
            .all()
        )

        for instance in instances:
            vendor = (instance.vendor or "").lower()
            if vendor == "ollama":
                discovered = _model_names_from_instance(instance)
                if not discovered:
                    discovered = ["nomic-embed-text"]
                models = [
                    {
                        "provider": "ollama",
                        "model": model,
                        "label": model,
                        "supported_dimensions": [],
                        "default_dimensions": None,
                        "max_dimensions": None,
                        "requires_provider_instance": True,
                        "supports_dimensions_parameter": True,
                    }
                    for model in discovered
                ]
            else:
                static_specs = list_model_specs(vendor)
                discovered = set(_model_names_from_instance(instance))
                if discovered:
                    filtered = [spec for spec in static_specs if spec.model in discovered]
                    static_specs = filtered or static_specs
                models = [spec.to_dict() for spec in static_specs]

            default_model = (
                (models[0]["model"] if models else None)
                or provider_default_model(vendor)
            )
            default_dimensions = models[0].get("default_dimensions") if models else None

            options.append(
                {
                    "provider": vendor,
                    "provider_instance_id": instance.id,
                    "instance_name": instance.instance_name,
                    "vendor": vendor,
                    "configured": True,
                    "health_status": instance.health_status or "unknown",
                    "base_url": instance.base_url,
                    "models": models,
                    "default_model": default_model,
                    "default_dimensions": default_dimensions,
                    "test_status": instance.health_status or "unknown",
                }
            )

        return {
            "providers": options,
            "default": {
                "provider": "local",
                "provider_instance_id": None,
                "model": LOCAL_MODEL,
                "dimensions": LOCAL_DIMS,
            },
        }

    @staticmethod
    def resolve_provider_credentials(
        *,
        tenant_id: str,
        provider: str,
        provider_instance_id: Optional[int],
        db: Session,
    ) -> Dict[str, Any]:
        provider_norm = (provider or "local").lower()
        if provider_norm == "local":
            return {}

        if provider_instance_id is None:
            raise ValueError(f"{provider_norm} embeddings require a configured provider instance")

        instance = (
            db.query(ProviderInstance)
            .filter(
                ProviderInstance.id == provider_instance_id,
                ProviderInstance.tenant_id == tenant_id,
                ProviderInstance.is_active == True,
                ProviderInstance.vendor == provider_norm,
            )
            .first()
        )
        if not instance:
            raise ValueError(f"Provider instance {provider_instance_id} not found")

        api_key = ProviderInstanceService.resolve_api_key(instance, db)
        base_url = instance.base_url or get_vendor_default_base_url(provider_norm)
        credentials = {"base_url": base_url}
        if api_key:
            credentials["api_key"] = api_key
        return credentials

    @staticmethod
    async def test_embedding(
        *,
        tenant_id: str,
        provider: str,
        model: str,
        dimensions: Optional[int],
        provider_instance_id: Optional[int],
        db: Session,
        text: str = "hello world",
    ) -> Dict[str, Any]:
        started = time.monotonic()
        provider_norm = (provider or "local").lower()
        try:
            normalized = validate_embedding_contract(
                provider=provider_norm,
                model=model,
                dimensions=dimensions,
                allow_ollama_dynamic=True,
            )
            credentials = EmbeddingProviderService.resolve_provider_credentials(
                tenant_id=tenant_id,
                provider=normalized["provider"],
                provider_instance_id=provider_instance_id,
                db=db,
            )
            contract = SimpleNamespace(
                provider=normalized["provider"],
                model=normalized["model"],
                dimensions=normalized["dimensions"],
                metric=normalized.get("metric") or "cosine",
                base_url=credentials.get("base_url"),
            )
            embedder = get_shared_embedding_service(contract=contract, credentials=credentials)
            sample_text = text or "hello world"
            vector = await embedder.embed_text_async(sample_text, task_type="RETRIEVAL_DOCUMENT")
            batch = await embedder.embed_batch_chunked_async(
                [sample_text, "second embedding smoke test"],
                batch_size=2,
                task_type="RETRIEVAL_DOCUMENT",
            )

            actual_dims = len(vector)
            expected_dims = normalized["dimensions"]
            if expected_dims is None:
                expected_dims = actual_dims
            if actual_dims != int(expected_dims):
                raise ValueError(
                    f"Embedding dimension mismatch: expected {expected_dims}, got {actual_dims}"
                )
            if len(batch) != 2:
                raise ValueError(f"Embedding batch returned {len(batch)} vectors; expected 2")
            bad_batch = [len(item) for item in batch if len(item) != actual_dims]
            if bad_batch:
                raise ValueError("Embedding batch returned inconsistent dimensions")

            sample_norm = math.sqrt(sum(float(value) * float(value) for value in vector))
            return {
                "success": True,
                "provider": normalized["provider"],
                "provider_instance_id": provider_instance_id,
                "model": normalized["model"],
                "requested_dimensions": normalized["dimensions"],
                "actual_dimensions": actual_dims,
                "batch_count": len(batch),
                "sample_norm": sample_norm,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 - diagnostic endpoint returns inline errors
            return {
                "success": False,
                "provider": provider_norm,
                "provider_instance_id": provider_instance_id,
                "model": model,
                "requested_dimensions": dimensions,
                "actual_dimensions": 0,
                "batch_count": 0,
                "sample_norm": 0.0,
                "latency_ms": int((time.monotonic() - started) * 1000),
                "error": str(exc),
            }
