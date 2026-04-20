"""
SearXNG Search Provider
Implementation of SearchProvider for self-hosted SearXNG instances.

SearXNG is a free and open-source metasearch engine that can expose a JSON API.
This provider expects the configured value for service `searxng` to be the base
URL of a SearXNG instance (for example: http://localhost:8080).
"""

import logging
import time
from typing import Dict, List, Optional, Any

import requests
from sqlalchemy.orm import Session

from .search_provider import (
    SearchProvider,
    SearchRequest,
    SearchResponse,
    SearchResult,
    SearchProviderStatus,
)
from services.api_key_service import get_api_key
from utils.ssrf_validator import SSRFValidationError, validate_url


logger = logging.getLogger(__name__)


class SearXNGSearchProvider(SearchProvider):
    """
    SearXNG provider.

    Uses a self-hosted SearXNG instance configured via Hub -> Tool APIs.
    The stored secret for service `searxng` is treated as the instance base URL.
    """

    def __init__(self, db: Optional[Session] = None, token_tracker=None, tenant_id: str = None):
        super().__init__(db=db, token_tracker=token_tracker, tenant_id=tenant_id)
        self._base_url: Optional[str] = None
        self._load_base_url()

    def _load_base_url(self):
        """Load SearXNG base URL from the active SearxngInstance row for this tenant.

        v0.6.0-patch.6: resolver shifted from ApiKey('searxng') (legacy) to
        per-tenant SearxngInstance rows, which match the Kokoro/Ollama pattern
        and carry container lifecycle state. The old ApiKey path still exists
        for audit purposes but is marked inactive by migration 0043.
        """
        if not self.db or not self.tenant_id:
            self._base_url = None
            return

        configured_url: Optional[str] = None
        try:
            from services.searxng_instance_service import SearxngInstanceService
            inst = SearxngInstanceService.get_active_for_tenant(self.tenant_id, self.db)
            if inst and inst.base_url:
                configured_url = inst.base_url
        except Exception as e:
            self.logger.warning(f"Could not query SearxngInstance: {e}")

        # Legacy-install safety net: if the migration decrypt path couldn't
        # backfill a URL, fall back once to the old ApiKey so existing setups
        # keep working until the user re-runs the wizard.
        if not configured_url:
            try:
                configured_url = get_api_key("searxng", self.db, tenant_id=self.tenant_id)
            except Exception:
                configured_url = None

        if configured_url:
            try:
                self._base_url = validate_url(configured_url.rstrip("/"), allow_private=True).rstrip("/")
                self.logger.info(
                    f"Loaded SearXNG base URL from DB (tenant: {self.tenant_id or 'system'})"
                )
            except SSRFValidationError as e:
                self.logger.warning(f"SearXNG URL failed validation: {e}")
            except Exception as e:
                self.logger.warning(f"Could not normalize SearXNG URL: {e}")

        if not self._base_url:
            self.logger.warning(
                f"SearXNG base URL not configured (tenant: {self.tenant_id}). "
                "Configure via Hub -> Tool APIs > SearXNG."
            )

    def get_provider_name(self) -> str:
        return "searxng"

    def get_display_name(self) -> str:
        return "SearXNG"

    async def search(self, request: SearchRequest) -> SearchResponse:
        start_time = time.time()

        if not self._base_url:
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error="SearXNG base URL not configured. Configure SearXNG in Hub -> Tool APIs.",
            )

        try:
            params = {
                "q": request.query.strip(),
                "format": "json",
                "language": request.language,
                "safesearch": 1 if request.safe_search else 0,
                "pageno": max(1, (request.offset // max(1, request.count)) + 1),
            }

            response = requests.get(
                f"{self._base_url}/search",
                params=params,
                timeout=10,
                headers={"Accept": "application/json"},
            )
            response.raise_for_status()

            data = response.json()
            raw_results = data.get("results", [])[: request.count]
            results: List[SearchResult] = []

            for i, item in enumerate(raw_results):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        description=item.get("content", "") or item.get("description", ""),
                        position=i + 1,
                        favicon_url=item.get("thumbnail"),
                        published_date=item.get("publishedDate"),
                        site_name=item.get("parsed_url", [None, None])[1] if item.get("parsed_url") else None,
                    )
                )

            elapsed_ms = int((time.time() - start_time) * 1000)

            self._track_usage(
                query_length=len(request.query),
                result_count=len(results),
                agent_id=request.agent_id,
                sender_key=request.sender_key,
                message_id=request.message_id,
            )

            return SearchResponse(
                success=True,
                query=request.query,
                results=results,
                provider=self.provider_name,
                result_count=len(results),
                total_results=data.get("number_of_results"),
                request_time_ms=elapsed_ms,
                metadata={
                    "language": request.language,
                    "country": request.country,
                    "base_url": self._base_url,
                    "results_count_on_page": len(data.get("results", [])),
                },
            )

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None
            if status_code == 403:
                error_msg = (
                    "SearXNG JSON API is not available. Enable `json` in the instance "
                    "search formats or check access restrictions."
                )
            elif status_code == 429:
                error_msg = "SearXNG rate limit exceeded. Please try again later."
            else:
                error_msg = f"SearXNG returned status {status_code}"

            self.logger.error(f"SearXNG HTTP error: {error_msg}")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=error_msg,
            )
        except requests.exceptions.Timeout:
            self.logger.error("SearXNG request timed out")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error="SearXNG request timed out",
            )
        except requests.exceptions.RequestException as e:
            self.logger.error(f"SearXNG request failed: {e}")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=f"Failed to reach SearXNG: {str(e)}",
            )
        except ValueError as e:
            self.logger.error(f"SearXNG returned invalid JSON: {e}")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=f"SearXNG returned invalid JSON: {str(e)}",
            )
        except Exception as e:
            self.logger.error(f"Unexpected error in SearXNG Search: {e}", exc_info=True)
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=f"Unexpected error: {str(e)}",
            )

    async def health_check(self) -> SearchProviderStatus:
        if not self._base_url:
            return SearchProviderStatus(
                provider=self.provider_name,
                status="not_configured",
                message="Base URL not configured",
                available=False,
            )

        try:
            start_time = time.time()
            response = requests.get(
                f"{self._base_url}/search",
                params={"q": "test", "format": "json"},
                timeout=5,
                headers={"Accept": "application/json"},
            )
            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                return SearchProviderStatus(
                    provider=self.provider_name,
                    status="healthy",
                    message="SearXNG is operational",
                    available=True,
                    latency_ms=latency_ms,
                    details={"base_url": self._base_url},
                )
            if response.status_code == 403:
                return SearchProviderStatus(
                    provider=self.provider_name,
                    status="degraded",
                    message="SearXNG reachable, but JSON format is disabled",
                    available=False,
                    latency_ms=latency_ms,
                    details={"base_url": self._base_url},
                )
            return SearchProviderStatus(
                provider=self.provider_name,
                status="degraded",
                message=f"SearXNG returned status {response.status_code}",
                available=False,
                latency_ms=latency_ms,
                details={"base_url": self._base_url},
            )
        except requests.exceptions.Timeout:
            return SearchProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message="SearXNG request timed out",
                available=False,
            )
        except Exception as e:
            return SearchProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message=str(e),
                available=False,
            )

    def get_supported_languages(self) -> List[str]:
        return [
            "all", "en", "pt", "es", "fr", "de", "it", "nl", "pl", "ru",
            "ja", "zh", "ko", "ar", "tr", "id", "vi", "th", "hi",
        ]

    def get_supported_countries(self) -> List[str]:
        return [
            "US", "BR", "GB", "CA", "AU", "DE", "FR", "ES", "IT",
            "JP", "CN", "KR", "IN", "RU", "MX", "AR", "PT", "NL",
        ]

    def get_max_results(self) -> int:
        return 20

    def get_pricing_info(self) -> Dict[str, Any]:
        return {
            "cost_per_1k_requests": 0.0,
            "currency": "USD",
            "is_free": True,
            "free_tier_requests": 0,
            "description": "Self-hosted and open source. Configure your own SearXNG base URL.",
        }
