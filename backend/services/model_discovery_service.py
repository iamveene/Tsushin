"""
Phase 21: Model Discovery Service

Auto-discovers available models from provider endpoints.
- OpenAI-compatible APIs (openai/groq/grok/openrouter/custom): GET {base_url}/models
- Ollama: GET {base_url}/api/tags
- Anthropic/Gemini: predefined model lists (no /models endpoint)

SSRF validation is applied before any outbound connection.
"""

import logging
import httpx
from typing import List
from sqlalchemy.orm import Session
from models import ProviderInstance

logger = logging.getLogger(__name__)

# Predefined model lists for vendors without /models endpoint
PREDEFINED_MODELS = {
    "gemini": ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"],
    "anthropic": ["claude-opus-4-6", "claude-sonnet-4-6", "claude-haiku-4-5", "claude-sonnet-4-20250514", "claude-3-5-sonnet-20241022", "claude-3-opus-20240229"],
}


class ModelDiscoveryService:

    @staticmethod
    async def discover_models(instance: ProviderInstance, db: Session) -> List[str]:
        """
        Auto-discover available models from provider endpoint.
        - openai/groq/grok/openrouter/custom: GET {base_url}/models -> data[].id
        - ollama: GET {base_url}/api/tags -> models[].name
        - anthropic/gemini: return predefined lists
        """
        vendor = instance.vendor

        # Predefined lists
        if vendor in PREDEFINED_MODELS:
            return PREDEFINED_MODELS[vendor]

        # Resolve base URL and API key
        from services.provider_instance_service import ProviderInstanceService, VENDOR_DEFAULT_BASE_URLS
        base_url = instance.base_url or VENDOR_DEFAULT_BASE_URLS.get(vendor)
        if not base_url:
            return []

        api_key = ProviderInstanceService.resolve_api_key(instance, db)

        # SSRF validate before connecting
        if instance.base_url:
            from utils.ssrf_validator import validate_url, validate_ollama_url, SSRFValidationError
            try:
                if vendor == "ollama":
                    validate_ollama_url(base_url)
                else:
                    validate_url(base_url)
            except SSRFValidationError as e:
                logger.warning(f"SSRF blocked model discovery for {base_url}: {e}")
                return []

        try:
            if vendor == "ollama":
                return await ModelDiscoveryService._discover_ollama(base_url, api_key)
            else:
                return await ModelDiscoveryService._discover_openai_compat(base_url, api_key)
        except Exception as e:
            logger.error(f"Model discovery failed for {instance.instance_name}: {e}")
            return []

    @staticmethod
    async def _discover_openai_compat(base_url: str, api_key: str = None) -> List[str]:
        """GET {base_url}/models -> data[].id"""
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            models = [m["id"] for m in data.get("data", []) if isinstance(m, dict) and "id" in m]
            return sorted(models)

    @staticmethod
    async def _discover_ollama(base_url: str, api_key: str = None) -> List[str]:
        """GET {base_url}/api/tags -> models[].name"""
        headers = {}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{base_url.rstrip('/')}/api/tags", headers=headers)
            resp.raise_for_status()
            data = resp.json()
            models = [m["name"] for m in data.get("models", []) if isinstance(m, dict) and "name" in m]
            return sorted(models)
