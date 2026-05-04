"""Shared embedding provider/model catalog for KB, case memory, and RAG paths."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional


LOCAL_PROVIDER = "local"
LOCAL_MODEL = "all-MiniLM-L6-v2"
LOCAL_DIMS = 384


@dataclass(frozen=True)
class EmbeddingModelSpec:
    provider: str
    model: str
    label: str
    supported_dimensions: List[int]
    default_dimensions: int
    max_dimensions: int
    requires_provider_instance: bool = True
    supports_dimensions_parameter: bool = True

    def to_dict(self) -> Dict:
        return {
            "provider": self.provider,
            "model": self.model,
            "label": self.label,
            "supported_dimensions": list(self.supported_dimensions),
            "default_dimensions": self.default_dimensions,
            "max_dimensions": self.max_dimensions,
            "requires_provider_instance": self.requires_provider_instance,
            "supports_dimensions_parameter": self.supports_dimensions_parameter,
        }


_LOCAL_SPECS: Dict[str, EmbeddingModelSpec] = {
    LOCAL_MODEL: EmbeddingModelSpec(
        provider=LOCAL_PROVIDER,
        model=LOCAL_MODEL,
        label="Local MiniLM",
        supported_dimensions=[LOCAL_DIMS],
        default_dimensions=LOCAL_DIMS,
        max_dimensions=LOCAL_DIMS,
        requires_provider_instance=False,
        supports_dimensions_parameter=False,
    )
}

_OPENAI_SPECS: Dict[str, EmbeddingModelSpec] = {
    "text-embedding-3-small": EmbeddingModelSpec(
        provider="openai",
        model="text-embedding-3-small",
        label="OpenAI text-embedding-3-small",
        supported_dimensions=[256, 512, 1024, 1536],
        default_dimensions=1536,
        max_dimensions=1536,
    ),
    "text-embedding-3-large": EmbeddingModelSpec(
        provider="openai",
        model="text-embedding-3-large",
        label="OpenAI text-embedding-3-large",
        supported_dimensions=[256, 512, 1024, 3072],
        default_dimensions=3072,
        max_dimensions=3072,
    ),
}

_GEMINI_SPECS: Dict[str, EmbeddingModelSpec] = {
    "gemini-embedding-2": EmbeddingModelSpec(
        provider="gemini",
        model="gemini-embedding-2",
        label="Gemini Embedding 2",
        supported_dimensions=[768, 1536, 3072],
        default_dimensions=1536,
        max_dimensions=3072,
    ),
    "gemini-embedding-001": EmbeddingModelSpec(
        provider="gemini",
        model="gemini-embedding-001",
        label="Gemini Embedding 001",
        supported_dimensions=[768, 1536, 3072],
        default_dimensions=1536,
        max_dimensions=3072,
    ),
}

_CATALOG: Dict[str, Dict[str, EmbeddingModelSpec]] = {
    LOCAL_PROVIDER: _LOCAL_SPECS,
    "openai": _OPENAI_SPECS,
    "gemini": _GEMINI_SPECS,
}

SUPPORTED_PROVIDERS = {"local", "openai", "gemini", "ollama"}


def normalize_embedding_provider(provider: Optional[str]) -> str:
    provider_norm = (provider or LOCAL_PROVIDER).strip().lower()
    if provider_norm in {"chromadb", "sentence-transformers", "sentence_transformers"}:
        return LOCAL_PROVIDER
    return provider_norm


def provider_default_model(provider: str) -> str:
    provider_norm = normalize_embedding_provider(provider)
    if provider_norm == LOCAL_PROVIDER:
        return LOCAL_MODEL
    if provider_norm == "openai":
        return "text-embedding-3-small"
    if provider_norm == "gemini":
        return "gemini-embedding-2"
    if provider_norm == "ollama":
        return ""
    raise ValueError(
        f"Unsupported embedding provider {provider!r}: must be one of {sorted(SUPPORTED_PROVIDERS)}"
    )


def get_model_spec(provider: str, model: Optional[str]) -> Optional[EmbeddingModelSpec]:
    provider_norm = normalize_embedding_provider(provider)
    if provider_norm == "ollama":
        return None
    model_name = (model or provider_default_model(provider_norm)).strip()
    return _CATALOG.get(provider_norm, {}).get(model_name)


def list_model_specs(provider: Optional[str] = None) -> List[EmbeddingModelSpec]:
    if provider is not None:
        provider_norm = normalize_embedding_provider(provider)
        return list(_CATALOG.get(provider_norm, {}).values())
    specs: List[EmbeddingModelSpec] = []
    for provider_specs in _CATALOG.values():
        specs.extend(provider_specs.values())
    return specs


def _format_supported(values: Iterable[int]) -> str:
    return ", ".join(str(v) for v in sorted(values))


def validate_embedding_contract(
    *,
    provider: Optional[str],
    model: Optional[str],
    dimensions: Optional[int],
    allow_ollama_dynamic: bool = True,
) -> Dict:
    """Normalize and validate an embedding contract.

    Ollama dimensions are model/runtime dependent. Static validation only
    verifies that a custom dimension is a positive integer; the live test
    endpoint pins and validates the actual returned vector length.
    """

    provider_norm = normalize_embedding_provider(provider)
    if provider_norm not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported embedding provider {provider!r}: must be one of {sorted(SUPPORTED_PROVIDERS)}"
        )

    if provider_norm == "ollama":
        model_name = (model or "").strip()
        if not model_name:
            raise ValueError("Ollama embedding model is required")
        dims_int = None
        if dimensions is not None:
            try:
                dims_int = int(dimensions)
            except (TypeError, ValueError) as exc:
                raise ValueError("Ollama embedding dimensions must be an integer") from exc
            if dims_int <= 0:
                raise ValueError("Ollama embedding dimensions must be positive")
        elif not allow_ollama_dynamic:
            raise ValueError("Ollama embedding dimensions must be detected by testing before save")
        return {
            "provider": provider_norm,
            "model": model_name,
            "dimensions": dims_int,
            "metric": "cosine",
            "supported_dimensions": [],
            "default_dimensions": dims_int,
            "max_dimensions": dims_int,
        }

    spec = get_model_spec(provider_norm, model)
    if spec is None:
        supported_models = ", ".join(s.model for s in list_model_specs(provider_norm))
        raise ValueError(
            f"Unsupported {provider_norm} embedding model {model!r}. "
            f"Supported models: {supported_models}"
        )

    dims_int = spec.default_dimensions if dimensions is None else int(dimensions)
    if dims_int not in spec.supported_dimensions:
        raise ValueError(
            f"Invalid embedding dimensions for {spec.model}: must be one of "
            f"{_format_supported(spec.supported_dimensions)}, got {dims_int}"
        )

    return {
        "provider": provider_norm,
        "model": spec.model,
        "dimensions": dims_int,
        "metric": "cosine",
        "supported_dimensions": list(spec.supported_dimensions),
        "default_dimensions": spec.default_dimensions,
        "max_dimensions": spec.max_dimensions,
    }
