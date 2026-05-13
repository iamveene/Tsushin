"""Shared LLM model catalog constants.

Keep vendor-specific model defaults here when more than one backend surface
needs the same identifiers. UI fallbacks should either fetch the backend
catalog or mirror these names deliberately.
"""

from __future__ import annotations

import re
from typing import Dict, Iterable, List, Mapping, Optional


DEEPSEEK_DEFAULT_BASE_URL = "https://api.deepseek.com"
DEEPSEEK_V4_FLASH = "deepseek-v4-flash"
DEEPSEEK_V4_PRO = "deepseek-v4-pro"
DEEPSEEK_DEFAULT_MODEL = DEEPSEEK_V4_FLASH

# Compatibility aliases documented by DeepSeek. Keep selectable so existing
# tenants do not lose explicit saved choices, but do not make them defaults.
DEEPSEEK_LEGACY_CHAT = "deepseek-chat"
DEEPSEEK_LEGACY_REASONER = "deepseek-reasoner"

DEEPSEEK_V4_MODELS = [DEEPSEEK_V4_FLASH, DEEPSEEK_V4_PRO]
DEEPSEEK_LEGACY_MODELS = [DEEPSEEK_LEGACY_CHAT, DEEPSEEK_LEGACY_REASONER]
DEEPSEEK_MODELS = [*DEEPSEEK_V4_MODELS, *DEEPSEEK_LEGACY_MODELS]

DEEPSEEK_MODEL_DISPLAY_NAMES = {
    DEEPSEEK_V4_FLASH: "DeepSeek V4 Flash",
    DEEPSEEK_V4_PRO: "DeepSeek V4 Pro",
    DEEPSEEK_LEGACY_CHAT: "DeepSeek Chat (legacy alias)",
    DEEPSEEK_LEGACY_REASONER: "DeepSeek Reasoner (legacy alias)",
}

DEEPSEEK_MODEL_PRICING = {
    DEEPSEEK_V4_FLASH: {"prompt": 0.14, "cached_input": 0.0028, "completion": 0.28},
    # Standard DeepSeek V4 Pro rate. Ignore temporary promotional discounts so
    # usage accounting remains stable after the discount window ends.
    DEEPSEEK_V4_PRO: {"prompt": 1.74, "cached_input": 0.0145, "completion": 3.48},
    DEEPSEEK_LEGACY_CHAT: {"prompt": 0.14, "cached_input": 0.0028, "completion": 0.28},
    DEEPSEEK_LEGACY_REASONER: {"prompt": 0.14, "cached_input": 0.0028, "completion": 0.28},
}

OPENAI_LATEST_MODELS = [
    "gpt-5.5",
    "gpt-5.5-pro",
    "gpt-5.4",
    "gpt-5.4-pro",
    "gpt-5.4-mini",
    "gpt-5.4-nano",
    "gpt-5.2",
    "gpt-5.2-pro",
    "gpt-5.2-chat-latest",
    "gpt-5.1",
    "gpt-5.1-chat-latest",
    "gpt-5",
    "gpt-5-mini",
    "gpt-5-nano",
    "gpt-4.1",
    "gpt-4.1-mini",
    "gpt-4o",
    "gpt-4o-mini",
]

ANTHROPIC_LATEST_MODELS = [
    "claude-opus-4-7",
    "claude-opus-4-7-latest",
    "claude-opus-4-6",
    "claude-opus-4-6-latest",
    "claude-sonnet-4-6",
    "claude-sonnet-4-6-latest",
    "claude-haiku-4-5",
    "claude-haiku-4-5-latest",
    "claude-sonnet-4-20250514",
    "claude-3-5-sonnet-20241022",
]

GROK_LATEST_MODELS = [
    "grok-4.3",
    "grok-4.3-latest",
    "grok-4.20-multi-agent-0309",
    "grok-4.20-0309-reasoning",
    "grok-4.20-0309-non-reasoning",
    "grok-4-1-fast-reasoning",
    "grok-4-1-fast-non-reasoning",
    "grok-3",
    "grok-3-mini",
]

# Groq catalog intentionally contains hosted/open models from GroqCloud only.
# Avoid third-party gateway IDs here; OpenRouter owns those.
GROQ_HOSTED_OPEN_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
]

GEMINI_LATEST_MODELS = [
    "gemini-3.1-pro-preview",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-2.5-pro",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash",
    "gemini-1.5-pro",
    "gemini-1.5-flash",
]

OPENROUTER_GATEWAY_MODELS = [
    "openai/gpt-5.5",
    "openai/gpt-5.5-pro",
    "openai/gpt-5.2",
    "openai/gpt-5.2-pro",
    "anthropic/claude-opus-4.7",
    "anthropic/claude-opus-4-7",
    "anthropic/claude-sonnet-4.6",
    "anthropic/claude-haiku-4.5",
    "x-ai/grok-4.3",
    "x-ai/grok-4.3-latest",
    "x-ai/grok-4.20-multi-agent-0309",
    "x-ai/grok-4.20-0309-reasoning",
    "x-ai/grok-4.20-0309-non-reasoning",
    "x-ai/grok-4-1-fast-reasoning",
    "x-ai/grok-4-1-fast-non-reasoning",
    "google/gemini-2.5-flash",
    "google/gemini-2.5-pro",
    "meta-llama/llama-3.1-8b-instruct:free",
    "deepseek/deepseek-r1:free",
]

VERTEX_AI_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash",
    "claude-opus-4-7",
    "claude-sonnet-4-6",
    "claude-haiku-4-5-latest",
]

LLM_PROVIDER_CATALOG: Dict[str, List[str]] = {
    "openai": OPENAI_LATEST_MODELS,
    "anthropic": ANTHROPIC_LATEST_MODELS,
    "gemini": GEMINI_LATEST_MODELS,
    "groq": GROQ_HOSTED_OPEN_MODELS,
    "grok": GROK_LATEST_MODELS,
    "deepseek": DEEPSEEK_MODELS,
    "openrouter": OPENROUTER_GATEWAY_MODELS,
    "vertex_ai": VERTEX_AI_MODELS,
}

LATEST_MODEL_PRICING: Dict[str, Dict[str, float]] = {
    # OpenAI, standard short-context rates per 1M tokens.
    "gpt-5.5": {"prompt": 5.0, "cached_input": 0.5, "completion": 30.0},
    "gpt-5.5-pro": {"prompt": 30.0, "completion": 180.0},
    "gpt-5.4": {"prompt": 2.5, "cached_input": 0.25, "completion": 15.0},
    "gpt-5.4-pro": {"prompt": 30.0, "completion": 180.0},
    "gpt-5.4-mini": {"prompt": 0.75, "cached_input": 0.075, "completion": 4.5},
    "gpt-5.4-nano": {"prompt": 0.20, "cached_input": 0.02, "completion": 1.25},
    "gpt-5.2": {"prompt": 1.75, "cached_input": 0.175, "completion": 14.0},
    "gpt-5.2-chat-latest": {"prompt": 1.75, "cached_input": 0.175, "completion": 14.0},
    "gpt-5.2-pro": {"prompt": 21.0, "completion": 168.0},
    "gpt-5.1": {"prompt": 1.25, "cached_input": 0.125, "completion": 10.0},
    "gpt-5.1-chat-latest": {"prompt": 1.25, "cached_input": 0.125, "completion": 10.0},

    # Anthropic.
    "claude-opus-4-7": {"prompt": 5.0, "cached_input": 0.5, "completion": 25.0},
    "claude-opus-4-7-latest": {"prompt": 5.0, "cached_input": 0.5, "completion": 25.0},

    # xAI.
    "grok-4.3": {"prompt": 1.25, "cached_input": 0.20, "completion": 2.50},
    "grok-4.3-latest": {"prompt": 1.25, "cached_input": 0.20, "completion": 2.50},
    "grok-4.20-multi-agent-0309": {"prompt": 1.25, "cached_input": 0.20, "completion": 2.50},
    "grok-4.20-0309-reasoning": {"prompt": 1.25, "cached_input": 0.20, "completion": 2.50},
    "grok-4.20-0309-non-reasoning": {"prompt": 1.25, "cached_input": 0.20, "completion": 2.50},
    "grok-4-1-fast-reasoning": {"prompt": 0.20, "cached_input": 0.05, "completion": 0.50},
    "grok-4-1-fast-non-reasoning": {"prompt": 0.20, "cached_input": 0.05, "completion": 0.50},

    # Groq hosted/open models.
    "llama-3.1-8b-instant": {"prompt": 0.05, "completion": 0.08},
    "llama-3.3-70b-versatile": {"prompt": 0.59, "completion": 0.79},
    "openai/gpt-oss-120b": {"prompt": 0.15, "cached_input": 0.075, "completion": 0.60},
    "openai/gpt-oss-20b": {"prompt": 0.075, "cached_input": 0.037, "completion": 0.30},

    # OpenRouter gateway IDs.
    "openai/gpt-5.5": {"prompt": 5.0, "cached_input": 0.5, "completion": 30.0},
    "openai/gpt-5.5-pro": {"prompt": 30.0, "completion": 180.0},
    "openai/gpt-5.2": {"prompt": 1.75, "cached_input": 0.175, "completion": 14.0},
    "openai/gpt-5.2-pro": {"prompt": 21.0, "completion": 168.0},
    "anthropic/claude-opus-4.7": {"prompt": 5.0, "cached_input": 0.5, "completion": 25.0},
    "anthropic/claude-opus-4-7": {"prompt": 5.0, "cached_input": 0.5, "completion": 25.0},
    "x-ai/grok-4.3": {"prompt": 1.25, "cached_input": 0.20, "completion": 2.50},
    "x-ai/grok-4.3-latest": {"prompt": 1.25, "cached_input": 0.20, "completion": 2.50},
    "x-ai/grok-4.20-multi-agent-0309": {"prompt": 1.25, "cached_input": 0.20, "completion": 2.50},
    "x-ai/grok-4.20-0309-reasoning": {"prompt": 1.25, "cached_input": 0.20, "completion": 2.50},
    "x-ai/grok-4.20-0309-non-reasoning": {"prompt": 1.25, "cached_input": 0.20, "completion": 2.50},
    "x-ai/grok-4-1-fast-reasoning": {"prompt": 0.20, "cached_input": 0.05, "completion": 0.50},
    "x-ai/grok-4-1-fast-non-reasoning": {"prompt": 0.20, "cached_input": 0.05, "completion": 0.50},
}

DEFAULT_PROVIDER_MODELS: Dict[str, str] = {
    "gemini": "gemini-2.5-flash",
    "openai": "gpt-5.5",
    "anthropic": "claude-opus-4-7",
    "groq": "openai/gpt-oss-120b",
    "grok": "grok-4.3",
    "deepseek": DEEPSEEK_DEFAULT_MODEL,
    "openrouter": "openai/gpt-5.5",
    "ollama": "llama3.2:latest",
}

SENTINEL_DEFAULT_MODELS: Dict[str, str] = {
    "gemini": "gemini-2.5-flash-lite",
    "openai": "gpt-5.5",
    "anthropic": "claude-opus-4-7",
    "groq": "openai/gpt-oss-20b",
    "grok": "grok-4.3",
    "deepseek": DEEPSEEK_DEFAULT_MODEL,
    "openrouter": "openai/gpt-5.5",
}

PROVIDER_TEST_MODELS: Dict[str, str] = {
    "groq": "openai/gpt-oss-20b",
    "grok": "grok-4.3",
    "openai": "gpt-5.5",
    "anthropic": "claude-opus-4-7",
    "gemini": "gemini-2.5-flash",
    "openrouter": "meta-llama/llama-3.1-8b-instruct:free",
    "deepseek": DEEPSEEK_DEFAULT_MODEL,
}

SENTINEL_PROVIDER_MODELS: Dict[str, List[str]] = {
    "gemini": [
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash",
        "gemini-2.5-pro",
        "gemini-2.0-flash",
    ],
    "anthropic": ANTHROPIC_LATEST_MODELS,
    "openai": OPENAI_LATEST_MODELS,
    "groq": GROQ_HOSTED_OPEN_MODELS,
    "grok": GROK_LATEST_MODELS,
    "deepseek": DEEPSEEK_MODELS,
    "openrouter": OPENROUTER_GATEWAY_MODELS,
    "ollama": [],
}


def get_provider_models(provider: str) -> List[str]:
    """Return a copy of the curated catalog for a provider."""
    return list(LLM_PROVIDER_CATALOG.get((provider or "").lower(), []))


def get_sentinel_models(provider: str) -> List[str]:
    """Return a copy of Sentinel-compatible model suggestions."""
    return list(SENTINEL_PROVIDER_MODELS.get((provider or "").lower(), []))


def infer_provider_from_model(model_name: str, provider_hint: Optional[str] = None) -> str:
    """Infer Tsushin's provider key from a model id without rejecting custom ids."""
    if provider_hint:
        return provider_hint.lower()

    model_lower = (model_name or "").lower()
    if not model_lower:
        return "unknown"

    if "/" in model_lower:
        if model_lower.startswith("openai/gpt-oss-"):
            return "groq"
        prefix = model_lower.split("/", 1)[0]
        provider_map: Mapping[str, str] = {
            "openai": "openai",
            "anthropic": "anthropic",
            "google": "gemini",
            "x-ai": "grok",
            "meta-llama": "openrouter",
            "deepseek": "openrouter",
            "qwen": "openrouter",
            "mistralai": "openrouter",
        }
        return provider_map.get(prefix, "openrouter")

    if model_lower.startswith(("gpt-", "whisper", "tts-", "o1", "o3", "o4")):
        return "openai"
    if model_lower.startswith("claude-"):
        return "anthropic"
    if model_lower.startswith("gemini"):
        return "gemini"
    if model_lower.startswith("grok-"):
        return "grok"
    if model_lower.startswith("deepseek"):
        return "deepseek"
    if ":" in model_lower or model_lower in {"llama", "gemma", "mistral"}:
        return "ollama"
    if re.match(r"^llama-\d", model_lower) or model_lower.startswith("openai/gpt-oss-"):
        return "groq"
    if model_lower in {"kokoro", "elevenlabs"}:
        return model_lower
    return "unknown"


def merge_deepseek_v4_models(existing: Iterable[str] | None) -> List[str]:
    """Prepend the direct DeepSeek catalog while preserving custom entries.

    Used for conservative backfills: new current models become visible first,
    but saved agent/System AI/Sentinel assignments are not rewritten.
    """
    existing_models = list(existing or [])
    if not existing_models:
        return list(DEEPSEEK_MODELS)

    merged: List[str] = []
    seen: set[str] = set()
    for model in [*DEEPSEEK_MODELS, *existing_models]:
        if not model or model in seen:
            continue
        seen.add(model)
        merged.append(model)
    return merged


def expand_deepseek_model_catalog(models: Iterable[str] | None = None) -> List[str]:
    """Return a selectable DeepSeek catalog with V4 first and aliases retained."""
    existing = []
    seen: set[str] = set()
    for model in models or []:
        if model and model not in seen:
            seen.add(model)
            existing.append(model)

    ordered: List[str] = []
    for model in [*DEEPSEEK_MODELS, *existing]:
        if model and model not in ordered:
            ordered.append(model)
    return ordered
