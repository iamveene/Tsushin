"""
ASR Provider Registry.
"""

from typing import Dict, Type, Optional
import logging

from sqlalchemy.orm import Session

from .asr_provider import ASRProvider

logger = logging.getLogger(__name__)


class ASRProviderRegistry:
    _providers: Dict[str, Type[ASRProvider]] = {}
    _initialized = False

    @classmethod
    def register_provider(cls, name: str, provider_class: Type[ASRProvider]) -> None:
        cls._providers[name] = provider_class
        logger.info("Registered ASR provider: %s (%s)", name, provider_class.__name__)

    @classmethod
    def initialize_providers(cls) -> None:
        if cls._initialized:
            return
        from .openai_asr_provider import OpenAIASRProvider
        from .openai_whisper_asr_provider import OpenAIWhisperASRProvider
        from .whisper_asr_provider import WhisperASRProvider

        cls.register_provider("openai", OpenAIASRProvider)
        cls.register_provider("speaches", WhisperASRProvider)
        cls.register_provider("openai_whisper", OpenAIWhisperASRProvider)
        cls._initialized = True

    @classmethod
    def get_provider_class(cls, provider_name: str) -> Optional[Type[ASRProvider]]:
        if not cls._initialized:
            cls.initialize_providers()
        return cls._providers.get(provider_name)

    @classmethod
    def get_openai_provider(
        cls,
        db: Optional[Session] = None,
        token_tracker=None,
        tenant_id: Optional[str] = None,
        api_key: Optional[str] = None,
    ) -> ASRProvider:
        provider_class = cls.get_provider_class("openai")
        return provider_class(db=db, token_tracker=token_tracker, tenant_id=tenant_id, api_key=api_key)

    @classmethod
    def get_instance_provider(
        cls,
        instance,
        db: Session,
        token_tracker=None,
        tenant_id: Optional[str] = None,
    ) -> ASRProvider:
        provider_class = cls.get_provider_class(instance.vendor)
        if not provider_class:
            raise ValueError(f"ASR provider '{instance.vendor}' not registered")
        return provider_class(instance=instance, db=db, token_tracker=token_tracker, tenant_id=tenant_id)
