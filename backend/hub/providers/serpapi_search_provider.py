"""
SerpAPI Google Search Provider
Implementation of SearchProvider for Google Search via SerpAPI.

SerpAPI provides access to Google Search results through a simple API.
- Pricing: https://serpapi.com/pricing
- Documentation: https://serpapi.com/search-api
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


class SerpApiSearchProvider(SearchProvider):
    """
    Google Search via SerpAPI provider.

    High-quality search results from Google Search.
    Configured via Studio → API Keys → serpapi.

    API Documentation: https://serpapi.com/search-api
    """

    BASE_URL = "https://serpapi.com/search"

    def __init__(self, db: Optional[Session] = None, token_tracker=None, tenant_id: str = None):
        """
        Initialize SerpAPI Search provider.

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
            # Try 'serpapi' from ApiKey table first
            self._api_key = get_api_key('serpapi', self.db, tenant_id=self.tenant_id)

            # Fallback: Try ApiKey table with 'google_flights' service (legacy)
            if not self._api_key:
                self._api_key = get_api_key('google_flights', self.db, tenant_id=self.tenant_id)

            # Fallback: Try GoogleFlightsIntegration table (encrypted key, legacy)
            if not self._api_key:
                try:
                    from models import GoogleFlightsIntegration
                    from hub.security import TokenEncryption
                    from services.encryption_key_service import get_api_key_encryption_key

                    gf_integration = self.db.query(GoogleFlightsIntegration).filter(
                        GoogleFlightsIntegration.is_active == True
                    ).first()

                    if gf_integration:
                        # CRIT-004 fix: Use dedicated API key encryption key (not JWT_SECRET_KEY)
                        encryption_key = get_api_key_encryption_key(self.db)
                        if encryption_key:
                            encryptor = TokenEncryption(encryption_key.encode())
                            # Use consistent identifier with ApiKey table
                            identifier = f"apikey_google_flights_{gf_integration.tenant_id or 'system'}"
                            self._api_key = encryptor.decrypt(gf_integration.api_key_encrypted, identifier)
                            self.logger.info("✓ Loaded SerpAPI key from GoogleFlightsIntegration (decrypted)")
                        else:
                            self.logger.warning("Could not get encryption key for GoogleFlightsIntegration decryption")
                except Exception as e:
                    self.logger.debug(f"Could not load from GoogleFlightsIntegration: {e}")

        if not self._api_key:
            self.logger.warning(f"SerpAPI API key not configured (tenant: {self.tenant_id}). Configure via Hub → API Keys.")

    def get_provider_name(self) -> str:
        return "google"

    def get_display_name(self) -> str:
        return "Google Search"

    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Perform web search using SerpAPI Google Search.

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
                error="SerpAPI key not configured. Configure SerpAPI (Google Services) in Hub → Tool APIs."
            )

        try:
            params = {
                "engine": "google",
                "api_key": self._api_key,
                "q": request.query,
                "num": min(request.count, self.get_max_results()),
                "start": request.offset,
                "hl": request.language,
                "gl": request.country.lower(),
            }

            # Safe search parameter
            if request.safe_search:
                params["safe"] = "active"

            response = requests.get(
                self.BASE_URL,
                params=params,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()

            # Check for API errors
            if "error" in data:
                return SearchResponse(
                    success=False,
                    query=request.query,
                    provider=self.provider_name,
                    error=f"SerpAPI error: {data['error']}"
                )

            # Parse results
            results = []
            organic_results = data.get("organic_results", [])

            for i, item in enumerate(organic_results[:request.count]):
                results.append(SearchResult(
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    description=item.get("snippet", ""),
                    position=i + 1,
                    site_name=item.get("displayed_link", "").split(" › ")[0] if item.get("displayed_link") else None
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
                total_results=data.get("search_information", {}).get("total_results"),
                request_time_ms=elapsed_ms,
                metadata={
                    "language": request.language,
                    "country": request.country,
                    "search_parameters": data.get("search_parameters", {})
                }
            )

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 401:
                error_msg = "Invalid API key"
            elif e.response.status_code == 429:
                error_msg = "Rate limit exceeded. Please try again later."
            else:
                error_msg = f"SerpAPI error: {e.response.status_code}"

            self.logger.error(f"SerpAPI HTTP error: {error_msg}")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=error_msg
            )

        except requests.exceptions.Timeout:
            self.logger.error("SerpAPI request timed out")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error="Search request timed out"
            )

        except requests.exceptions.RequestException as e:
            self.logger.error(f"SerpAPI request failed: {e}")
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=f"Failed to perform search: {str(e)}"
            )

        except Exception as e:
            self.logger.error(f"Unexpected error in SerpAPI Search: {e}", exc_info=True)
            return SearchResponse(
                success=False,
                query=request.query,
                provider=self.provider_name,
                error=f"Unexpected error: {str(e)}"
            )

    async def health_check(self) -> SearchProviderStatus:
        """
        Check SerpAPI availability.

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

            params = {
                "engine": "google",
                "api_key": self._api_key,
                "q": "test",
                "num": 1
            }

            response = requests.get(
                self.BASE_URL,
                params=params,
                timeout=5
            )

            latency_ms = int((time.time() - start_time) * 1000)

            if response.status_code == 200:
                data = response.json()
                if "error" in data:
                    return SearchProviderStatus(
                        provider=self.provider_name,
                        status="not_configured",
                        message=f"API error: {data['error']}",
                        available=False
                    )
                return SearchProviderStatus(
                    provider=self.provider_name,
                    status="healthy",
                    message="SerpAPI Google Search is operational",
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
        """SerpAPI supports all Google Search languages."""
        return [
            "en", "pt", "es", "fr", "de", "it", "nl", "pl", "ru",
            "ja", "zh", "ko", "ar", "tr", "id", "vi", "th", "hi"
        ]

    def get_supported_countries(self) -> List[str]:
        """SerpAPI supports all Google Search countries."""
        return [
            "US", "BR", "GB", "CA", "AU", "DE", "FR", "ES", "IT",
            "JP", "CN", "KR", "IN", "RU", "MX", "AR", "PT", "NL"
        ]

    def get_max_results(self) -> int:
        """SerpAPI allows up to 100 results per request."""
        return 100

    def get_pricing_info(self) -> Dict[str, Any]:
        """SerpAPI pricing information."""
        return {
            "cost_per_1k_requests": 5.0,  # $5 per 1000 searches (approximate)
            "currency": "USD",
            "is_free": False,
            "free_tier_requests": 100,  # 100 free searches per month
            "description": "Free: 100 searches/month. Paid: from $50/month for 5,000 searches"
        }
