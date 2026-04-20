"""
Tavily Search Provider

Wraps the Tavily Search API (https://api.tavily.com/search) so it plugs into the
same SearchProvider contract that backs Brave / SerpAPI / SearXNG. Registered
via SearchProviderRegistry at startup (search_registry.py).

API docs: https://docs.tavily.com/docs/rest-api/api-reference
"""

import time
import logging
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

logger = logging.getLogger(__name__)


class TavilySearchProvider(SearchProvider):
    """Tavily Search API provider — AI-optimized web search with a concise
    answer string alongside the ranked result list.

    Configured via Hub > Tool APIs > Tavily (api_key service = 'tavily')."""

    BASE_URL = "https://api.tavily.com/search"

    def __init__(self, db: Optional[Session] = None, token_tracker=None, tenant_id: str = None):
        super().__init__(db=db, token_tracker=token_tracker, tenant_id=tenant_id)
        self._api_key: Optional[str] = None
        self._load_api_key()

    def _load_api_key(self) -> None:
        if self.db:
            self._api_key = get_api_key("tavily", self.db, tenant_id=self.tenant_id)
            if self._api_key:
                self.logger.info(
                    f"✓ Loaded Tavily API key from database (tenant: {self.tenant_id or 'system'})"
                )
        if not self._api_key:
            self.logger.warning(
                f"Tavily API key not configured (tenant: {self.tenant_id}). "
                "Configure via Hub > Tool APIs > Tavily."
            )

    def get_provider_name(self) -> str:
        return "tavily"

    def get_display_name(self) -> str:
        return "Tavily"

    async def search(self, request: SearchRequest) -> SearchResponse:
        start_time = time.time()

        if not self._api_key:
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error="Search API key not configured. Configure Tavily in Hub > Tool APIs.",
            )

        if not request.query or not request.query.strip():
            return SearchResponse(
                success=False,
                query=request.query or "",
                provider=self.provider_name,
                error="Search query cannot be empty",
            )

        payload: Dict[str, Any] = {
            "api_key": self._api_key,
            "query": request.query.strip(),
            "search_depth": "basic",
            "max_results": max(1, min(request.count, self.get_max_results())),
            "include_answer": True,
            "include_images": False,
        }

        try:
            response = requests.post(
                self.BASE_URL,
                json=payload,
                timeout=15,
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )

            if response.status_code != 200:
                self.logger.error(f"Tavily error response ({response.status_code}): {response.text[:500]}")
            response.raise_for_status()

            data = response.json()
            raw_results = data.get("results", [])[: request.count]
            results: List[SearchResult] = []
            for i, item in enumerate(raw_results):
                results.append(
                    SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        description=item.get("content", "") or item.get("snippet", ""),
                        position=i + 1,
                        published_date=item.get("published_date"),
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
                total_results=len(raw_results),
                request_time_ms=elapsed_ms,
                metadata={
                    "answer": data.get("answer"),
                    "response_time": data.get("response_time"),
                    "language": request.language,
                    "country": request.country,
                },
            )

        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code if e.response is not None else None
            if status_code == 401:
                error_msg = "Invalid Tavily API key"
            elif status_code == 429:
                error_msg = "Tavily rate limit exceeded. Please try again later."
            else:
                error_msg = f"Tavily API error: {status_code}"
            self.logger.error(f"Tavily HTTP error: {error_msg}")
            return SearchResponse(
                success=False, query=request.query, provider=self.provider_name, error=error_msg
            )
        except requests.exceptions.Timeout:
            self.logger.error("Tavily request timed out")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error="Tavily request timed out",
            )
        except requests.exceptions.RequestException as e:
            self.logger.error(f"Tavily request failed: {e}")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=f"Failed to reach Tavily: {str(e)}",
            )
        except ValueError as e:
            self.logger.error(f"Tavily returned invalid JSON: {e}")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=f"Tavily returned invalid JSON: {str(e)}",
            )
        except Exception as e:
            self.logger.error(f"Unexpected error in Tavily Search: {e}", exc_info=True)
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=f"Unexpected error: {str(e)}",
            )

    async def health_check(self) -> SearchProviderStatus:
        if not self._api_key:
            return SearchProviderStatus(
                provider=self.provider_name,
                status="not_configured",
                message="API key not configured",
                available=False,
            )
        try:
            start_time = time.time()
            r = requests.post(
                self.BASE_URL,
                json={
                    "api_key": self._api_key,
                    "query": "health",
                    "search_depth": "basic",
                    "max_results": 1,
                    "include_answer": False,
                },
                timeout=5,
            )
            latency_ms = int((time.time() - start_time) * 1000)

            if r.status_code == 200:
                return SearchProviderStatus(
                    provider=self.provider_name,
                    status="healthy",
                    message="Tavily API is operational",
                    available=True,
                    latency_ms=latency_ms,
                )
            if r.status_code == 401:
                return SearchProviderStatus(
                    provider=self.provider_name,
                    status="not_configured",
                    message="Invalid API key",
                    available=False,
                )
            if r.status_code == 429:
                return SearchProviderStatus(
                    provider=self.provider_name,
                    status="degraded",
                    message="Rate limited",
                    available=True,
                    latency_ms=latency_ms,
                )
            return SearchProviderStatus(
                provider=self.provider_name,
                status="degraded",
                message=f"API returned status {r.status_code}",
                available=False,
            )
        except requests.exceptions.Timeout:
            return SearchProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message="API request timed out",
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
        return ["en", "pt", "es", "fr", "de", "it", "nl", "pl", "ru", "ja", "zh", "ko"]

    def get_supported_countries(self) -> List[str]:
        return ["US", "BR", "GB", "CA", "AU", "DE", "FR", "ES", "IT", "JP"]

    def get_max_results(self) -> int:
        return 10

    def get_pricing_info(self) -> Dict[str, Any]:
        return {
            "cost_per_1k_requests": None,
            "currency": "USD",
            "is_free": False,
            "free_tier_requests": 1000,
            "description": "Free tier: 1,000 API calls/month. Paid plans for higher volume.",
        }
