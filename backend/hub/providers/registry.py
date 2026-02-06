"""
Flight Provider Registry
Central registry for managing available flight search providers.
"""

from typing import Dict, Type, Optional, List
import logging
from sqlalchemy.orm import Session

from .flight_search_provider import FlightSearchProvider
from models import HubIntegration, ApiKey, GoogleFlightsIntegration
from hub.security import TokenEncryption
from services.encryption_key_service import get_api_key_encryption_key
from services.api_key_service import get_api_key as get_decrypted_api_key


logger = logging.getLogger(__name__)


class FlightProviderRegistry:
    """
    Registry for all available flight search providers.
    Handles provider discovery, instantiation, and lifecycle management.

    Providers are registered at startup and can be retrieved by name.
    This enables dynamic provider selection per agent.
    """

    _providers: Dict[str, Type[FlightSearchProvider]] = {}
    _initialized = False

    @classmethod
    def register_provider(
        cls,
        name: str,
        provider_class: Type[FlightSearchProvider]
    ):
        """
        Register a new provider.

        This method is used to add flight search providers to the registry.
        Can be used for plugins/extensions to add custom providers.

        Args:
            name: Provider identifier (e.g., "amadeus", "skyscanner")
            provider_class: Provider class that implements FlightSearchProvider

        Example:
            FlightProviderRegistry.register_provider(
                "amadeus",
                AmadeusFlightProvider
            )
        """
        if not issubclass(provider_class, FlightSearchProvider):
            raise ValueError(
                f"Provider class {provider_class.__name__} must inherit from FlightSearchProvider"
            )

        cls._providers[name] = provider_class
        logger.info(f"Registered flight provider: {name} ({provider_class.__name__})")

    @classmethod
    def get_provider(
        cls,
        provider_name: str,
        db: Session,
        tenant_id: Optional[str] = None
    ) -> Optional[FlightSearchProvider]:
        """
        Get an instance of the specified provider.

        Loads the provider's Hub integration from database and instantiates
        the provider class with the integration credentials.

        Args:
            provider_name: Provider identifier (e.g., "amadeus")
            db: Database session
            tenant_id: Optional tenant ID for multi-tenancy

        Returns:
            Instantiated provider or None if not found/configured

        Example:
            provider = FlightProviderRegistry.get_provider("amadeus", db)
            if provider:
                response = await provider.search_flights(request)
        """
        # Check if provider is registered
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            logger.warning(f"Provider '{provider_name}' not registered")
            return None

        # Load integration from database
        query = db.query(HubIntegration).filter(
            HubIntegration.type == provider_name,
            HubIntegration.is_active == True
        )

        # Filter by tenant if provided
        if tenant_id:
            query = query.filter(HubIntegration.tenant_id == tenant_id)

        integration = query.first()

        if not integration and provider_name == "google_flights":
            integration = cls._sync_google_flights_integration(db, tenant_id)

        if not integration:
            logger.warning(
                f"No active integration found for provider '{provider_name}'"
                + (f" (tenant: {tenant_id})" if tenant_id else "")
            )
            return None

        # Instantiate provider
        try:
            provider = provider_class(integration, db)
            logger.debug(f"Instantiated provider: {provider_name}")
            return provider
        except Exception as e:
            logger.error(f"Failed to instantiate provider '{provider_name}': {e}")
            return None

    @classmethod
    def _sync_google_flights_integration(
        cls,
        db: Session,
        tenant_id: Optional[str]
    ) -> Optional[GoogleFlightsIntegration]:
        """
        Ensure Google Flights integration exists when API key is present.
        """
        key_query = db.query(ApiKey).filter(
            ApiKey.service == "google_flights",
            ApiKey.is_active == True
        )

        if tenant_id:
            api_key = key_query.filter(ApiKey.tenant_id == tenant_id).first()
            if not api_key:
                api_key = key_query.filter(ApiKey.tenant_id == None).first()
        else:
            api_key = key_query.filter(ApiKey.tenant_id == None).first()
            if not api_key:
                api_key = key_query.first()

        if not api_key:
            return None

        # CRIT-004 fix: Get decrypted API key from api_key_service (not api_key.api_key which may be NULL)
        # Then re-encrypt with dedicated encryption key (not JWT_SECRET_KEY)
        decrypted_key = get_decrypted_api_key('google_flights', db, tenant_id=api_key.tenant_id)
        if not decrypted_key:
            logger.warning("Could not get decrypted API key for GoogleFlightsIntegration sync")
            return None

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            logger.error("Failed to get encryption key for GoogleFlightsIntegration sync")
            return None

        encryptor = TokenEncryption(encryption_key.encode())
        # Use consistent identifier with ApiKey table
        identifier = f"apikey_google_flights_{api_key.tenant_id or 'system'}"
        encrypted_key = encryptor.encrypt(decrypted_key, identifier)

        integration = GoogleFlightsIntegration(
            name="Google Flights (SerpApi)",
            display_name="Google Flights",
            is_active=api_key.is_active,
            tenant_id=api_key.tenant_id,
            api_key_encrypted=encrypted_key,
            default_currency="USD",
            default_language="en"
        )
        db.add(integration)
        db.commit()
        db.refresh(integration)
        logger.info(
            "Created Google Flights integration from ApiKey"
            + (f" (tenant: {api_key.tenant_id})" if api_key.tenant_id else " (system)")
        )
        return integration

    @classmethod
    def list_available_providers(cls, db: Optional[Session] = None) -> List[Dict]:
        """
        List all registered providers with metadata.

        Args:
            db: Optional database session to check configuration status

        Returns:
            List of provider info dicts with:
            - id: Provider identifier
            - name: Human-readable name
            - class: Provider class name
            - supported: Always True (all registered providers are supported)
            - configured: Whether provider has active integration (if db provided)

        Example:
            providers = FlightProviderRegistry.list_available_providers(db)
            # [
            #     {
            #         "id": "amadeus",
            #         "name": "Amadeus",
            #         "class": "AmadeusFlightProvider",
            #         "supported": True,
            #         "configured": True
            #     }
            # ]
        """
        providers_list = []

        for name, provider_class in cls._providers.items():
            provider_info = {
                "id": name,
                "name": name.replace("_", " ").title(),
                "class": provider_class.__name__,
                "supported": True
            }

            # Check if configured (if database session provided)
            if db:
                integration = db.query(HubIntegration).filter(
                    HubIntegration.type == name,
                    HubIntegration.is_active == True
                ).first()
                provider_info["configured"] = integration is not None

                if integration:
                    provider_info["health_status"] = integration.health_status

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
    def get_registered_providers(cls) -> List[str]:
        """
        Get list of all registered provider names.

        Returns:
            List of provider identifiers
        """
        return list(cls._providers.keys())

    @classmethod
    def initialize_providers(cls):
        """
        Initialize and register all available providers.

        This method should be called at application startup to register
        all flight search providers. It imports and registers providers
        from the providers package.

        Note: This uses lazy imports to avoid circular dependencies.
        """
        if cls._initialized:
            logger.debug("Providers already initialized")
            return

        try:
            # Import and register Amadeus provider
            from .amadeus_provider import AmadeusFlightProvider
            cls.register_provider("amadeus", AmadeusFlightProvider)
        except ImportError as e:
            logger.warning(f"Could not import AmadeusFlightProvider: {e}")

        try:
            # Import and register Google Flights provider
            from .google_flights_provider import GoogleFlightsProvider
            cls.register_provider("google_flights", GoogleFlightsProvider)
        except ImportError as e:
            logger.warning(f"Could not import GoogleFlightsProvider: {e}")


        # Future providers can be added here:
        # try:
        #     from .skyscanner_provider import SkyscannerFlightProvider
        #     cls.register_provider("skyscanner", SkyscannerFlightProvider)
        # except ImportError:
        #     pass

        # try:
        #     from .google_flights_provider import GoogleFlightsProvider
        #     cls.register_provider("google_flights", GoogleFlightsProvider)
        # except ImportError:
        #     pass

        cls._initialized = True
        logger.info(f"Initialized {len(cls._providers)} flight provider(s)")

    @classmethod
    def reset(cls):
        """
        Reset the registry (mainly for testing).
        Clears all registered providers.
        """
        cls._providers.clear()
        cls._initialized = False
        logger.debug("Provider registry reset")
