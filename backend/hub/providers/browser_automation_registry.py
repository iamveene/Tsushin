"""
Browser Automation Provider Registry

Phase 14.5: Browser Automation Skill - Provider Registry

Central registry for managing browser automation providers (Playwright, MCP Browser, etc.).
Follows the same pattern as FlightProviderRegistry for consistency.
"""

from typing import Dict, Type, Optional, List, Any
import logging
from sqlalchemy.orm import Session

from .browser_automation_provider import (
    BrowserAutomationProvider,
    BrowserConfig,
    BrowserAutomationError
)

logger = logging.getLogger(__name__)


class BrowserAutomationRegistry:
    """
    Registry for all available browser automation providers.
    Handles provider discovery, instantiation, and lifecycle management.

    Providers are registered at startup and can be retrieved by name.
    This enables dynamic provider selection per agent configuration.

    Supported providers:
    - playwright: Container-based browser automation (default)
    - mcp_browser: Host browser control via MCP (Phase 8)

    Usage:
        # Initialize at startup
        BrowserAutomationRegistry.initialize_providers()

        # Get provider instance
        provider = BrowserAutomationRegistry.get_provider("playwright", db, tenant_id)
        if provider:
            await provider.initialize()
            try:
                result = await provider.navigate("https://example.com")
            finally:
                await provider.cleanup()
    """

    _providers: Dict[str, Type[BrowserAutomationProvider]] = {}
    _provider_configs: Dict[str, Dict[str, Any]] = {}  # Metadata per provider
    _initialized = False

    @classmethod
    def register_provider(
        cls,
        name: str,
        provider_class: Type[BrowserAutomationProvider],
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Register a new browser automation provider.

        Args:
            name: Provider identifier (e.g., "playwright", "mcp_browser")
            provider_class: Provider class that implements BrowserAutomationProvider
            config: Optional provider metadata (requires_api_key, status, etc.)

        Example:
            BrowserAutomationRegistry.register_provider(
                "playwright",
                PlaywrightProvider,
                {"requires_api_key": False, "is_free": True, "status": "available"}
            )
        """
        if not issubclass(provider_class, BrowserAutomationProvider):
            raise ValueError(
                f"Provider class {provider_class.__name__} must inherit from BrowserAutomationProvider"
            )

        cls._providers[name] = provider_class
        cls._provider_configs[name] = config or {
            "requires_api_key": False,
            "is_free": True,
            "status": "available",
            "description": provider_class.provider_name
        }
        logger.info(f"Registered browser automation provider: {name} ({provider_class.__name__})")

    @classmethod
    def get_provider(
        cls,
        provider_name: str,
        db: Optional[Session] = None,
        tenant_id: Optional[str] = None,
        config_override: Optional[BrowserConfig] = None
    ) -> Optional[BrowserAutomationProvider]:
        """
        Get an instance of the specified provider.

        For container-mode providers (playwright), loads configuration from database
        if available, otherwise uses defaults.

        Args:
            provider_name: Provider identifier (e.g., "playwright")
            db: Database session (optional for default config)
            tenant_id: Optional tenant ID for multi-tenancy
            config_override: Optional config to use instead of database lookup

        Returns:
            Instantiated provider or None if not found/not available

        Example:
            provider = BrowserAutomationRegistry.get_provider("playwright", db)
            if provider:
                await provider.initialize()
                result = await provider.navigate("https://example.com")
        """
        # Check if provider is registered
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            logger.warning(f"Browser automation provider '{provider_name}' not registered")
            return None

        # Check provider status
        provider_meta = cls._provider_configs.get(provider_name, {})
        if provider_meta.get("status") == "coming_soon":
            logger.warning(f"Provider '{provider_name}' is coming soon, not yet available")
            return None

        # Use override config if provided
        if config_override:
            try:
                provider = provider_class(config_override)
                logger.debug(f"Instantiated browser provider: {provider_name} (override config)")
                return provider
            except Exception as e:
                logger.error(f"Failed to instantiate provider '{provider_name}': {e}")
                return None

        # Try to load integration from database
        config = None
        if db:
            try:
                # Lazy import to avoid circular dependencies
                from models import HubIntegration

                query = db.query(HubIntegration).filter(
                    HubIntegration.type == "browser_automation",
                    HubIntegration.is_active == True
                )

                # Filter by tenant if provided
                if tenant_id:
                    query = query.filter(HubIntegration.tenant_id == tenant_id)
                else:
                    # Fall back to system-wide integration
                    query = query.filter(
                        (HubIntegration.tenant_id == tenant_id) |
                        (HubIntegration.tenant_id == "_system") |
                        (HubIntegration.tenant_id == None)
                    )

                integration = query.first()

                if integration:
                    # Check if this integration uses the requested provider type
                    if hasattr(integration, 'provider_type'):
                        if integration.provider_type != provider_name:
                            logger.debug(
                                f"Integration found but for different provider "
                                f"({integration.provider_type}), using defaults"
                            )
                            integration = None

                    if integration:
                        config = BrowserConfig.from_integration(integration)
                        logger.debug(f"Loaded config from integration for tenant: {tenant_id}")

            except Exception as e:
                logger.warning(f"Could not load integration from database: {e}")
                # Continue with default config

        # Fall back to default config
        if not config:
            config = BrowserConfig(provider_type=provider_name)
            logger.debug(f"Using default config for provider: {provider_name}")

        # Instantiate provider
        try:
            provider = provider_class(config)
            logger.debug(f"Instantiated browser provider: {provider_name}")
            return provider
        except Exception as e:
            logger.error(f"Failed to instantiate provider '{provider_name}': {e}")
            return None

    @classmethod
    def list_available_providers(
        cls,
        db: Optional[Session] = None,
        include_coming_soon: bool = False
    ) -> List[Dict[str, Any]]:
        """
        List all registered providers with metadata.

        Args:
            db: Optional database session to check configuration status
            include_coming_soon: Include providers marked as "coming_soon"

        Returns:
            List of provider info dicts with:
            - id: Provider identifier
            - name: Human-readable name
            - class: Provider class name
            - status: "available" or "coming_soon"
            - requires_api_key: Whether provider needs API key
            - is_free: Whether provider is free to use
            - configured: Whether integration exists (if db provided)

        Example:
            providers = BrowserAutomationRegistry.list_available_providers(db)
        """
        providers_list = []

        for name, provider_class in cls._providers.items():
            meta = cls._provider_configs.get(name, {})

            # Skip coming_soon unless requested
            if meta.get("status") == "coming_soon" and not include_coming_soon:
                continue

            provider_info = {
                "id": name,
                "name": provider_class.provider_name,
                "class": provider_class.__name__,
                "status": meta.get("status", "available"),
                "requires_api_key": meta.get("requires_api_key", False),
                "is_free": meta.get("is_free", True),
                "description": meta.get("description", ""),
                "actions": provider_class.get_provider_info().get("actions", [])
            }

            # Check if configured (if database session provided)
            if db:
                try:
                    from models import HubIntegration

                    integration = db.query(HubIntegration).filter(
                        HubIntegration.type == "browser_automation",
                        HubIntegration.is_active == True
                    ).first()

                    provider_info["configured"] = integration is not None

                    if integration:
                        provider_info["health_status"] = integration.health_status

                except Exception:
                    provider_info["configured"] = False

            providers_list.append(provider_info)

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
    def is_provider_available(cls, provider_name: str) -> bool:
        """
        Check if a provider is registered and available (not coming_soon).

        Args:
            provider_name: Provider identifier

        Returns:
            True if provider is registered and available
        """
        if provider_name not in cls._providers:
            return False

        meta = cls._provider_configs.get(provider_name, {})
        return meta.get("status") != "coming_soon"

    @classmethod
    def get_registered_providers(cls) -> List[str]:
        """
        Get list of all registered provider names.

        Returns:
            List of provider identifiers
        """
        return list(cls._providers.keys())

    @classmethod
    def get_default_provider(cls) -> str:
        """
        Get the default provider name.

        Returns:
            Default provider identifier ("playwright")
        """
        return "playwright"

    @classmethod
    def initialize_providers(cls):
        """
        Initialize and register all available browser automation providers.

        This method should be called at application startup to register
        all providers. It uses lazy imports to avoid circular dependencies.
        """
        if cls._initialized:
            logger.debug("Browser automation providers already initialized")
            return

        # Register Playwright provider (container mode)
        try:
            from .playwright_provider import PlaywrightProvider
            cls.register_provider(
                "playwright",
                PlaywrightProvider,
                {
                    "requires_api_key": False,
                    "is_free": True,
                    "status": "available",
                    "description": "Container-based browser automation using Playwright",
                    "mode": "container"
                }
            )
        except ImportError as e:
            logger.warning(f"Could not import PlaywrightProvider: {e}")

        # NOTE: MCP Browser provider (host mode) - Phase 8 - DISABLED
        # The host browser mode via MCP Bridge was not properly implemented.
        # It returned mock data instead of controlling the real browser.
        # This feature is disabled until a better solution is found.
        # See: .private/BROWSER_AUTOMATION_COMPLETE_PLAN.md for details
        #
        # try:
        #     from .mcp_browser_provider import MCPBrowserProvider
        #     cls.register_provider(
        #         "mcp_browser",
        #         MCPBrowserProvider,
        #         {
        #             "requires_api_key": False,
        #             "is_free": True,
        #             "status": "available",
        #             "description": "Host browser control via MCP (authenticated sessions)",
        #             "mode": "host"
        #         }
        #     )
        # except ImportError as e:
        #     logger.warning(f"Could not import MCPBrowserProvider: {e}")

        cls._initialized = True
        logger.info(f"Initialized {len(cls._providers)} browser automation provider(s)")

    @classmethod
    def reset(cls):
        """
        Reset the registry (mainly for testing).
        Clears all registered providers.
        """
        cls._providers.clear()
        cls._provider_configs.clear()
        cls._initialized = False
        logger.debug("Browser automation provider registry reset")
