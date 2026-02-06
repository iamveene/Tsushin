"""
Search Provider Registry
Central registry for managing available Search providers.
"""

from typing import Dict, Type, Optional, List, Any
import logging
from sqlalchemy.orm import Session

from .search_provider import SearchProvider, SearchProviderStatus


logger = logging.getLogger(__name__)


class SearchProviderRegistry:
    """
    Registry for all available Search providers.
    Handles provider discovery, instantiation, and lifecycle management.

    Providers are registered at startup and can be retrieved by name.
    This enables dynamic provider selection per agent.
    """

    _providers: Dict[str, Type[SearchProvider]] = {}
    _provider_configs: Dict[str, Dict[str, Any]] = {}  # Store provider-specific config
    _initialized = False

    @classmethod
    def register_provider(
        cls,
        name: str,
        provider_class: Type[SearchProvider],
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Register a new Search provider.

        Args:
            name: Provider identifier (e.g., "brave", "google", "bing")
            provider_class: Provider class that implements SearchProvider
            config: Optional provider-specific configuration

        Example:
            SearchProviderRegistry.register_provider(
                "brave",
                BraveSearchProvider,
                {"requires_api_key": True, "is_default": True}
            )
        """
        if not issubclass(provider_class, SearchProvider):
            raise ValueError(
                f"Provider class {provider_class.__name__} must inherit from SearchProvider"
            )

        cls._providers[name] = provider_class
        cls._provider_configs[name] = config or {}
        logger.info(f"Registered Search provider: {name} ({provider_class.__name__})")

    @classmethod
    def get_provider(
        cls,
        provider_name: str,
        db: Optional[Session] = None,
        token_tracker=None,
        tenant_id: str = None
    ) -> Optional[SearchProvider]:
        """
        Get an instance of the specified provider.

        Args:
            provider_name: Provider identifier (e.g., "brave", "google")
            db: Database session (for API key lookup)
            token_tracker: TokenTracker instance for usage tracking
            tenant_id: Tenant ID for multi-tenant API key isolation

        Returns:
            Instantiated provider or None if not found

        Example:
            provider = SearchProviderRegistry.get_provider("brave", db, token_tracker, tenant_id)
            if provider:
                response = await provider.search(request)
        """
        # Check if provider is registered
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            logger.warning(f"Search provider '{provider_name}' not registered")
            return None

        # Instantiate provider
        try:
            provider = provider_class(db=db, token_tracker=token_tracker, tenant_id=tenant_id)
            logger.debug(f"Instantiated Search provider: {provider_name} (tenant: {tenant_id})")
            return provider
        except Exception as e:
            logger.error(f"Failed to instantiate Search provider '{provider_name}': {e}")
            return None

    @classmethod
    async def get_provider_status(
        cls,
        provider_name: str,
        db: Optional[Session] = None
    ) -> SearchProviderStatus:
        """
        Get health status for a specific provider.

        Args:
            provider_name: Provider identifier
            db: Database session

        Returns:
            SearchProviderStatus with health information
        """
        if provider_name not in cls._providers:
            return SearchProviderStatus(
                provider=provider_name,
                status="not_registered",
                message=f"Provider '{provider_name}' is not registered",
                available=False
            )

        provider = cls.get_provider(provider_name, db)
        if not provider:
            return SearchProviderStatus(
                provider=provider_name,
                status="not_configured",
                message=f"Provider '{provider_name}' is not configured",
                available=False
            )

        return await provider.health_check()

    @classmethod
    def list_providers(cls, db: Optional[Session] = None, include_health: bool = False) -> List[Dict]:
        """
        List all registered Search providers with metadata.

        Args:
            db: Optional database session for configuration status
            include_health: Whether to include health status (slower, requires async)

        Returns:
            List of provider info dicts
        """
        providers_list = []

        for name, provider_class in cls._providers.items():
            config = cls._provider_configs.get(name, {})

            # Create temporary provider instance for metadata
            try:
                temp_provider = provider_class(db=db, token_tracker=None)
                provider_info = temp_provider.get_provider_info()
                pricing = temp_provider.get_pricing_info()
            except Exception as e:
                logger.warning(f"Could not get info for provider {name}: {e}")
                provider_info = {"name": name, "display_name": name.title()}
                pricing = {}

            provider_data = {
                "id": name,
                "name": provider_info.get("display_name", name.title()),
                "class": provider_class.__name__,
                "supported": True,
                "requires_api_key": config.get("requires_api_key", True),
                "is_default": config.get("is_default", False),
                "status": config.get("status", "available"),  # "available", "coming_soon"
                "pricing": pricing,
                "max_results": provider_info.get("max_results", 20),
                "supported_languages": provider_info.get("supported_languages", []),
                "supported_countries": provider_info.get("supported_countries", []),
            }

            providers_list.append(provider_data)

        return providers_list

    @classmethod
    def is_provider_registered(cls, provider_name: str) -> bool:
        """
        Check if a provider is registered.

        Args:
            provider_name: Provider identifier

        Returns:
            True if provider is registered, False otherwise
        """
        return provider_name in cls._providers

    @classmethod
    def get_registered_providers(cls) -> List[str]:
        """
        Get list of all registered provider names.

        Returns:
            List of provider identifiers
        """
        return list(cls._providers.keys())

    @classmethod
    def get_available_providers(cls) -> List[str]:
        """
        Get list of available (not coming_soon) provider names.

        Returns:
            List of available provider identifiers
        """
        return [
            name for name, config in cls._provider_configs.items()
            if config.get("status", "available") == "available"
        ]

    @classmethod
    def get_default_provider(cls) -> Optional[str]:
        """
        Get the default provider name.

        Returns:
            Default provider identifier or None
        """
        for name, config in cls._provider_configs.items():
            if config.get("is_default", False):
                return name

        # Fallback to first available provider
        available = cls.get_available_providers()
        return available[0] if available else None

    @classmethod
    def get_provider_config(cls, provider_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific provider.

        Args:
            provider_name: Provider identifier

        Returns:
            Provider configuration dict
        """
        return cls._provider_configs.get(provider_name, {})

    @classmethod
    def initialize_providers(cls):
        """
        Initialize and register all available Search providers.

        This method should be called at application startup to register
        all Search providers. It imports and registers providers from
        the providers package.

        Note: This uses lazy imports to avoid circular dependencies.
        """
        if cls._initialized:
            logger.debug("Search providers already initialized")
            return

        # Register Brave Search provider (default)
        try:
            from .brave_search_provider import BraveSearchProvider
            cls.register_provider(
                "brave",
                BraveSearchProvider,
                {
                    "requires_api_key": True,
                    "is_default": True,
                    "status": "available",
                    "description": "Fast and privacy-focused web search"
                }
            )
        except ImportError as e:
            logger.warning(f"Could not import BraveSearchProvider: {e}")

        # Register Google Search provider (via SerpAPI)
        try:
            from .serpapi_search_provider import SerpApiSearchProvider
            cls.register_provider(
                "google",
                SerpApiSearchProvider,
                {
                    "requires_api_key": True,
                    "is_default": False,
                    "status": "available",
                    "description": "Google Search via SerpAPI"
                }
            )
        except ImportError as e:
            logger.warning(f"Could not import SerpApiSearchProvider: {e}")

        cls._initialized = True
        logger.info(f"Initialized {len(cls._providers)} Search provider(s)")

    @classmethod
    def reset(cls):
        """
        Reset the registry (mainly for testing).
        Clears all registered providers.
        """
        cls._providers.clear()
        cls._provider_configs.clear()
        cls._initialized = False
        logger.debug("Search provider registry reset")
