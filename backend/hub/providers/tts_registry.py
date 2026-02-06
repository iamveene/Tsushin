"""
TTS Provider Registry
Central registry for managing available TTS providers.
"""

from typing import Dict, Type, Optional, List, Any
import logging
from sqlalchemy.orm import Session

from .tts_provider import TTSProvider, ProviderStatus


logger = logging.getLogger(__name__)


class TTSProviderRegistry:
    """
    Registry for all available TTS providers.
    Handles provider discovery, instantiation, and lifecycle management.

    Providers are registered at startup and can be retrieved by name.
    This enables dynamic provider selection per agent.
    """

    _providers: Dict[str, Type[TTSProvider]] = {}
    _provider_configs: Dict[str, Dict[str, Any]] = {}  # Store provider-specific config
    _initialized = False

    @classmethod
    def register_provider(
        cls,
        name: str,
        provider_class: Type[TTSProvider],
        config: Optional[Dict[str, Any]] = None
    ):
        """
        Register a new TTS provider.

        Args:
            name: Provider identifier (e.g., "openai", "kokoro", "elevenlabs")
            provider_class: Provider class that implements TTSProvider
            config: Optional provider-specific configuration

        Example:
            TTSProviderRegistry.register_provider(
                "kokoro",
                KokoroTTSProvider,
                {"requires_api_key": False, "is_free": True}
            )
        """
        if not issubclass(provider_class, TTSProvider):
            raise ValueError(
                f"Provider class {provider_class.__name__} must inherit from TTSProvider"
            )

        cls._providers[name] = provider_class
        cls._provider_configs[name] = config or {}
        logger.info(f"Registered TTS provider: {name} ({provider_class.__name__})")

    @classmethod
    def get_provider(
        cls,
        provider_name: str,
        db: Optional[Session] = None,
        token_tracker=None
    ) -> Optional[TTSProvider]:
        """
        Get an instance of the specified provider.

        Args:
            provider_name: Provider identifier (e.g., "openai", "kokoro")
            db: Database session (for API key lookup)
            token_tracker: TokenTracker instance for usage tracking

        Returns:
            Instantiated provider or None if not found

        Example:
            provider = TTSProviderRegistry.get_provider("kokoro", db, token_tracker)
            if provider:
                response = await provider.synthesize(request)
        """
        # Check if provider is registered
        provider_class = cls._providers.get(provider_name)
        if not provider_class:
            logger.warning(f"TTS provider '{provider_name}' not registered")
            return None

        # Instantiate provider
        try:
            provider = provider_class(db=db, token_tracker=token_tracker)
            logger.debug(f"Instantiated TTS provider: {provider_name}")
            return provider
        except Exception as e:
            logger.error(f"Failed to instantiate TTS provider '{provider_name}': {e}")
            return None

    @classmethod
    async def get_provider_status(
        cls,
        provider_name: str,
        db: Optional[Session] = None
    ) -> ProviderStatus:
        """
        Get health status for a specific provider.

        Args:
            provider_name: Provider identifier
            db: Database session

        Returns:
            ProviderStatus with health information
        """
        if provider_name not in cls._providers:
            return ProviderStatus(
                provider=provider_name,
                status="not_registered",
                message=f"Provider '{provider_name}' is not registered",
                available=False
            )

        provider = cls.get_provider(provider_name, db)
        if not provider:
            return ProviderStatus(
                provider=provider_name,
                status="not_configured",
                message=f"Provider '{provider_name}' is not configured",
                available=False
            )

        return await provider.health_check()

    @classmethod
    def list_providers(cls, db: Optional[Session] = None, include_health: bool = False) -> List[Dict]:
        """
        List all registered TTS providers with metadata.

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
                "is_free": config.get("is_free", False),
                "status": config.get("status", "available"),  # "available", "coming_soon"
                "pricing": pricing,
                "voice_count": provider_info.get("voice_count", 0),
                "default_voice": provider_info.get("default_voice", "default"),
                "supported_formats": provider_info.get("supported_formats", []),
                "supported_languages": provider_info.get("supported_languages", []),
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
        Initialize and register all available TTS providers.

        This method should be called at application startup to register
        all TTS providers. It imports and registers providers from
        the providers package.

        Note: This uses lazy imports to avoid circular dependencies.
        """
        if cls._initialized:
            logger.debug("TTS providers already initialized")
            return

        # Register OpenAI TTS provider
        try:
            from .openai_tts_provider import OpenAITTSProvider
            cls.register_provider(
                "openai",
                OpenAITTSProvider,
                {
                    "requires_api_key": True,
                    "is_free": False,
                    "status": "available",
                    "description": "Premium quality TTS from OpenAI"
                }
            )
        except ImportError as e:
            logger.warning(f"Could not import OpenAITTSProvider: {e}")

        # Register Kokoro TTS provider
        try:
            from .kokoro_tts_provider import KokoroTTSProvider
            cls.register_provider(
                "kokoro",
                KokoroTTSProvider,
                {
                    "requires_api_key": False,
                    "is_free": True,
                    "status": "available",
                    "description": "Free open-source TTS with PTBR support"
                }
            )
        except ImportError as e:
            logger.warning(f"Could not import KokoroTTSProvider: {e}")

        # Register ElevenLabs placeholder (coming soon)
        try:
            from .elevenlabs_tts_provider import ElevenLabsTTSProvider
            cls.register_provider(
                "elevenlabs",
                ElevenLabsTTSProvider,
                {
                    "requires_api_key": True,
                    "is_free": False,
                    "status": "coming_soon",
                    "description": "Premium voice AI synthesis (coming soon)"
                }
            )
        except ImportError as e:
            logger.debug(f"ElevenLabs provider not available: {e}")

        cls._initialized = True
        logger.info(f"Initialized {len(cls._providers)} TTS provider(s)")

    @classmethod
    def reset(cls):
        """
        Reset the registry (mainly for testing).
        Clears all registered providers.
        """
        cls._providers.clear()
        cls._provider_configs.clear()
        cls._initialized = False
        logger.debug("TTS provider registry reset")
