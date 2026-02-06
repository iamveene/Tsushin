"""
Search Provider - Abstract Base Class
Defines the interface that all Search providers must implement.

Provider-agnostic web search architecture enabling agents to use
different search services (Brave, Google, Bing) without code changes.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from datetime import datetime
import logging


@dataclass
class SearchResult:
    """
    Single search result from any provider.
    Provider-agnostic representation of a search result.
    """
    title: str                      # Result title
    url: str                        # Result URL
    description: str = ""           # Result snippet/description
    position: int = 0               # Position in results

    # Optional metadata
    favicon_url: Optional[str] = None
    published_date: Optional[str] = None
    site_name: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.position}. {self.title} - {self.url}"


@dataclass
class SearchRequest:
    """
    Standardized search request.
    Provider-agnostic representation of search parameters.
    """
    query: str                      # Search query (required)
    count: int = 5                  # Number of results to return
    offset: int = 0                 # Results offset for pagination
    language: str = "en"            # Language preference
    country: str = "US"             # Country preference
    safe_search: bool = True        # Enable safe search filtering

    # Optional tracking metadata
    agent_id: Optional[int] = None
    sender_key: Optional[str] = None
    message_id: Optional[str] = None

    def __post_init__(self):
        """Validate request parameters"""
        if not self.query or not self.query.strip():
            raise ValueError("Query cannot be empty")

        if len(self.query) > 2000:
            raise ValueError("Query exceeds maximum length of 2000 characters")

        if self.count < 1 or self.count > 50:
            raise ValueError("Count must be between 1 and 50")


@dataclass
class SearchResponse:
    """
    Standardized search response.
    Contains search results and metadata from any provider.
    """
    success: bool
    query: str = ""                 # Original query
    results: List[SearchResult] = field(default_factory=list)
    provider: str = ""              # Provider identifier (e.g., "brave", "google")
    error: Optional[str] = None

    # Results metadata
    total_results: Optional[int] = None
    result_count: int = 0

    # Performance tracking
    request_time_ms: Optional[int] = None

    metadata: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __str__(self) -> str:
        if self.success:
            return f"SearchResponse(provider={self.provider}, results={self.result_count})"
        return f"SearchResponse(error={self.error})"

    def format_results(self) -> str:
        """
        Format search results into human-readable string.

        Returns:
            Formatted string with search results
        """
        if not self.success:
            return f"❌ {self.error}"

        if not self.results:
            return f"🔍 No results found for: {self.query}"

        formatted = f"🔍 **Search Results for:** {self.query}\n\n"
        formatted += f"Found {self.result_count} results:\n\n"

        for i, result in enumerate(self.results, 1):
            formatted += f"**{i}. {result.title}**\n"
            formatted += f"🔗 {result.url}\n"
            if result.description:
                formatted += f"📝 {result.description}\n"
            formatted += "\n"

        return formatted


@dataclass
class SearchProviderStatus:
    """
    Search provider health status.
    """
    provider: str
    status: str                    # "healthy", "degraded", "unavailable", "not_configured"
    message: str
    available: bool = False
    latency_ms: Optional[int] = None
    details: Dict = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.utcnow)


class SearchProvider(ABC):
    """
    Abstract base class for Search providers.
    All Search providers (Brave, Google, Bing, etc.) must implement this interface.

    This enables provider-agnostic web search where agents can switch
    between different providers without code changes.
    """

    def __init__(self, db=None, token_tracker=None, tenant_id: str = None):
        """
        Initialize provider.

        Args:
            db: Database session (optional, for API key lookup)
            token_tracker: TokenTracker instance for usage tracking
            tenant_id: Tenant ID for multi-tenant API key isolation
        """
        self.db = db
        self.token_tracker = token_tracker
        self.tenant_id = tenant_id
        self.provider_name = self.get_provider_name()
        self.logger = logging.getLogger(f"{__name__}.{self.provider_name}")

    @abstractmethod
    def get_provider_name(self) -> str:
        """
        Return provider identifier.

        Returns:
            Provider name (e.g., 'brave', 'google', 'bing')
        """
        pass

    @abstractmethod
    def get_display_name(self) -> str:
        """
        Return human-readable provider name.

        Returns:
            Display name (e.g., 'Brave Search', 'Google Search')
        """
        pass

    @abstractmethod
    async def search(self, request: SearchRequest) -> SearchResponse:
        """
        Perform web search.

        Args:
            request: Standardized search request

        Returns:
            SearchResponse with results or error
        """
        pass

    @abstractmethod
    async def health_check(self) -> SearchProviderStatus:
        """
        Check provider service availability.

        Returns:
            SearchProviderStatus with health information
        """
        pass

    def get_supported_languages(self) -> List[str]:
        """
        Get list of supported language codes.

        Returns:
            List of language codes (e.g., ["en", "pt", "es"])
        """
        return ["en"]

    def get_supported_countries(self) -> List[str]:
        """
        Get list of supported country codes.

        Returns:
            List of country codes (e.g., ["US", "BR", "GB"])
        """
        return ["US"]

    def get_max_results(self) -> int:
        """
        Get maximum number of results supported.

        Returns:
            Maximum results count
        """
        return 20

    def get_pricing_info(self) -> Dict[str, Any]:
        """
        Get pricing information for this provider.

        Returns:
            Dict with pricing details
        """
        return {
            "cost_per_1k_requests": 0.0,
            "currency": "USD",
            "is_free": False,
            "free_tier_requests": 0
        }

    def get_provider_info(self) -> Dict[str, Any]:
        """
        Get provider information and capabilities.

        Returns:
            Provider info dict
        """
        return {
            "name": self.provider_name,
            "display_name": self.get_display_name(),
            "supported_languages": self.get_supported_languages(),
            "supported_countries": self.get_supported_countries(),
            "max_results": self.get_max_results(),
            "pricing": self.get_pricing_info()
        }

    def _track_usage(
        self,
        query_length: int,
        result_count: int,
        agent_id: Optional[int] = None,
        sender_key: Optional[str] = None,
        message_id: Optional[str] = None
    ):
        """
        Track search usage for analytics.

        Args:
            query_length: Number of characters in query
            result_count: Number of results returned
            agent_id, sender_key, message_id: Tracking metadata
        """
        if self.token_tracker:
            try:
                self.token_tracker.track_usage(
                    operation_type="web_search",
                    model_provider=self.provider_name,
                    model_name=f"{self.provider_name}_search",
                    prompt_tokens=query_length,
                    completion_tokens=result_count,
                    agent_id=agent_id,
                    skill_type="web_search",
                    sender_key=sender_key,
                    message_id=message_id,
                )
            except Exception as e:
                self.logger.warning(f"Failed to track search usage: {e}")
