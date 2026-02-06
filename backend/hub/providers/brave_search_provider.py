"""
Brave Search Provider
Implementation of SearchProvider for Brave Search API.

Brave Search is a privacy-focused search engine with a powerful API.
- Free tier: 2,000 queries/month
- Paid tier: $0.009 per 1,000 queries
"""

import os
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
    SearchProviderStatus
)
from services.api_key_service import get_api_key


logger = logging.getLogger(__name__)


class BraveSearchProvider(SearchProvider):
    """
    Brave Search API provider.

    Fast, privacy-focused web search with good international support.
    Configured via Studio → API Keys → brave_search.

    API Documentation: https://api.search.brave.com/
    """

    BASE_URL = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, db: Optional[Session] = None, token_tracker=None, tenant_id: str = None):
        """
        Initialize Brave Search provider.

        Args:
            db: Database session for API key lookup
            token_tracker: TokenTracker instance for usage tracking
            tenant_id: Tenant ID for multi-tenant API key isolation
        """
        super().__init__(db=db, token_tracker=token_tracker, tenant_id=tenant_id)
        self._api_key: Optional[str] = None
        self._load_api_key()

    def _load_api_key(self):
        """Load API key from database only (configured via Hub → API Keys)."""
        if self.db:
            self._api_key = get_api_key('brave_search', self.db, tenant_id=self.tenant_id)
            if self._api_key:
                self.logger.info(f"✓ Loaded Brave API key from database (tenant: {self.tenant_id or 'system'})")

        if not self._api_key:
            self.logger.warning(f"Brave Search API key not configured (tenant: {self.tenant_id}). Configure via Hub → API Keys.")

    def get_provider_name(self) -> str:
        return "brave"

    def get_display_name(self) -> str:
        return "Brave Search"

    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Perform web search using Brave Search API.

        Args:
            request: Standardized search request

        Returns:
            SearchResponse with results or error
        """
        start_time = time.time()

        if not self._api_key:
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error="Search API key not configured. Configure Brave Search in Hub → Tool APIs."
            )

        try:
            headers = {
                "Accept": "application/json",
                "Accept-Encoding": "gzip",
                "X-Subscription-Token": self._api_key
            }

            params = {
                "q": request.query,
                "count": min(request.count, self.get_max_results()),
                "offset": request.offset
            }

            # Add language/country preferences if specified
            if request.language and request.language != "en":
                params["search_lang"] = request.language

            if request.country and request.country != "US":
                params["country"] = request.country

            if request.safe_search:
                params["safesearch"] = "moderate"

            self.logger.info(f"Brave Search request: params={params}")

            response = requests.get(
                self.BASE_URL,
                headers=headers,
                params=params,
                timeout=10
            )

            self.logger.info(f"Brave Search response status: {response.status_code}")

            if response.status_code != 200:
                self.logger.error(f"Brave Search error response: {response.text}")

            response.raise_for_status()

            data = response.json()

            # Parse results
            results = []
            if "web" in data and "results" in data["web"]:
                for i, item in enumerate(data["web"]["results"][:request.count]):
                    results.append(SearchResult(
                        title=item.get("title", ""),
                        url=item.get("url", ""),
                        description=item.get("description", ""),
                        position=i + 1,
                        favicon_url=item.get("profile", {}).get("img") if item.get("profile") else None,
                        site_name=item.get("profile", {}).get("name") if item.get("profile") else None
                    ))

            elapsed_ms = int((time.time() - start_time) * 1000)

            # Track usage
            self._track_usage(
                query_length=len(request.query),
                result_count=len(results),
                agent_id=request.agent_id,
                sender_key=request.sender_key,
                message_id=request.message_id
            )

            return SearchResponse(
                success=True,
                query=request.query,
                results=results,
                provider=self.provider_name,
                result_count=len(results),
                total_results=data.get("web", {}).get("total"),
                request_time_ms=elapsed_ms,
                metadata={
                    "language": request.language,
                    "country": request.country
                }
            )

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                error_msg = "Invalid API key"
            elif e.response.status_code == 429:
                error_msg = "Rate limit exceeded. Please try again later."
            else:
                error_msg = f"Search API error: {e.response.status_code}"

            self.logger.error(f"Brave Search HTTP error: {error_msg}")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=error_msg
            )

        except requests.exceptions.Timeout:
            self.logger.error("Brave Search request timed out")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error="Search request timed out"
            )

        except requests.exceptions.RequestException as e:
            self.logger.error(f"Brave Search request failed: {e}")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=f"Failed to perform search: {str(e)}"
            )

        except Exception as e:
            self.logger.error(f"Unexpected error in Brave Search: {e}", exc_info=True)
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=f"Unexpected error: {str(e)}"
            )

    async def health_check(self) -> SearchProviderStatus:
        """
        Check Brave Search API availability.

        Returns:
            SearchProviderStatus with health information
        """
        if not self._api_key:
            return SearchProviderStatus(
                provider=self.provider_name,
                status="not_configured",
                message="API key not configured",
                available=False
            )

        try:
            # Perform a minimal search to test the API
            start_time = time.time()

            headers = {
                "Accept": "application/json",
                "X-Subscription-Token": self._api_key
            }

            response = requests.get(
                self.BASE_URL,
                headers=headers,
                params={"q": "test", "count": 1},
                timeout=5
            )

            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                return SearchProviderStatus(
                    provider=self.provider_name,
                    status="healthy",
                    message="Brave Search API is operational",
                    available=True,
                    latency_ms=latency_ms
                )
            elif response.status_code == 401:
                return SearchProviderStatus(
                    provider=self.provider_name,
                    status="not_configured",
                    message="Invalid API key",
                    available=False
                )
            elif response.status_code == 429:
                return SearchProviderStatus(
                    provider=self.provider_name,
                    status="degraded",
                    message="Rate limited",
                    available=True,
                    latency_ms=latency_ms
                )
            else:
                return SearchProviderStatus(
                    provider=self.provider_name,
                    status="degraded",
                    message=f"API returned status {response.status_code}",
                    available=False
                )

        except requests.exceptions.Timeout:
            return SearchProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message="API request timed out",
                available=False
            )
        except Exception as e:
            return SearchProviderStatus(
                provider=self.provider_name,
                status="unavailable",
                message=str(e),
                available=False
            )

    def get_supported_languages(self) -> List[str]:
        """Brave Search supports many languages."""
        return [
            "en", "pt", "es", "fr", "de", "it", "nl", "pl", "ru",
            "ja", "zh", "ko", "ar", "tr", "id", "vi", "th"
        ]

    def get_supported_countries(self) -> List[str]:
        """Brave Search supports global searches."""
        return [
            "US", "BR", "GB", "CA", "AU", "DE", "FR", "ES", "IT",
            "JP", "CN", "KR", "IN", "RU", "MX", "AR", "PT"
        ]

    def get_max_results(self) -> int:
        """Brave Search allows up to 20 results per request."""
        return 20

    def get_pricing_info(self) -> Dict[str, Any]:
        """Brave Search pricing information."""
        return {
            "cost_per_1k_requests": 0.009,
            "currency": "USD",
            "is_free": False,
            "free_tier_requests": 2000,  # per month
            "description": "Free tier: 2,000 queries/month. Paid: $0.009/1,000 queries"
        }
