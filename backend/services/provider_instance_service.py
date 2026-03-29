"""
Phase 21: Provider Instance Service

CRUD operations, API key encryption, and SSRF validation for provider instances.
Each tenant can configure multiple provider endpoints with independent API keys,
base URLs, and model availability.

Encryption pattern matches api_key_service.py (Fernet via TokenEncryption + encryption_key_service).
SSRF validation uses utils/ssrf_validator.py (DNS-resolution-based IP checking).
"""

import logging
from typing import Optional, List
from sqlalchemy.orm import Session
from models import ProviderInstance, ProviderConnectionAudit

logger = logging.getLogger(__name__)

# Default base URLs for vendors (None = SDK default)
VENDOR_DEFAULT_BASE_URLS = {
    "openai": None,
    "anthropic": None,
    "gemini": None,
    "groq": "https://api.groq.com/openai/v1",
    "grok": "https://api.x.ai/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "ollama": "http://host.docker.internal:11434",
}

SUPPORTED_VENDORS = list(VENDOR_DEFAULT_BASE_URLS.keys()) + ["custom"]


class ProviderInstanceService:

    @staticmethod
    def ensure_ollama_instance(tenant_id: str, db: Session) -> ProviderInstance:
        """Ensure a default Ollama provider instance exists for the tenant.

        If an active Ollama instance already exists, returns it.
        Otherwise, creates a new default instance using the Ollama base URL
        from the Config table (or the standard default).
        """
        existing = db.query(ProviderInstance).filter(
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.vendor == 'ollama',
            ProviderInstance.is_active == True,
        ).first()
        if existing:
            return existing

        # Derive base_url from Config table
        from models import Config
        config = db.query(Config).first()
        base_url = config.ollama_base_url if config and config.ollama_base_url else "http://host.docker.internal:11434"

        return ProviderInstanceService.create_instance(
            tenant_id=tenant_id,
            vendor='ollama',
            instance_name='Ollama (Local)',
            db=db,
            base_url=base_url,
            is_default=True,
        )

    @staticmethod
    def list_instances(tenant_id: str, db: Session, vendor: str = None, active_only: bool = True) -> List[ProviderInstance]:
        """List provider instances for a tenant, optionally filtered by vendor."""
        query = db.query(ProviderInstance).filter(ProviderInstance.tenant_id == tenant_id)
        if active_only:
            query = query.filter(ProviderInstance.is_active == True)
        if vendor:
            query = query.filter(ProviderInstance.vendor == vendor)
        return query.order_by(ProviderInstance.vendor, ProviderInstance.is_default.desc(), ProviderInstance.instance_name).all()

    @staticmethod
    def get_instance(instance_id: int, tenant_id: str, db: Session) -> Optional[ProviderInstance]:
        """Get single instance with tenant guard."""
        return db.query(ProviderInstance).filter(
            ProviderInstance.id == instance_id,
            ProviderInstance.tenant_id == tenant_id
        ).first()

    @staticmethod
    def get_default_instance(vendor: str, tenant_id: str, db: Session) -> Optional[ProviderInstance]:
        """Get default instance for a vendor+tenant."""
        return db.query(ProviderInstance).filter(
            ProviderInstance.vendor == vendor,
            ProviderInstance.tenant_id == tenant_id,
            ProviderInstance.is_default == True,
            ProviderInstance.is_active == True
        ).first()

    @staticmethod
    def create_instance(tenant_id: str, vendor: str, instance_name: str, db: Session,
                        base_url: str = None, api_key: str = None,
                        available_models: list = None, is_default: bool = False) -> ProviderInstance:
        """
        Create a new provider instance.
        - Validates base_url with SSRF validator if provided
        - Encrypts API key with Fernet (same pattern as api_key_service)
        - Enforces single default per (tenant_id, vendor)
        """
        # 1. Validate vendor
        if vendor not in SUPPORTED_VENDORS:
            raise ValueError(f"Unsupported vendor: {vendor}")

        # 2. SSRF validate base_url if provided
        if base_url:
            from utils.ssrf_validator import validate_url, validate_ollama_url, SSRFValidationError
            try:
                if vendor == "ollama":
                    validate_ollama_url(base_url)
                else:
                    validate_url(base_url)
            except SSRFValidationError as e:
                raise ValueError(f"URL validation failed: {e}")

        # 3. Encrypt API key
        api_key_encrypted = None
        if api_key:
            api_key_encrypted = ProviderInstanceService._encrypt_key(api_key, tenant_id, db)

        # 4. Enforce single default per (tenant_id, vendor)
        if is_default:
            db.query(ProviderInstance).filter(
                ProviderInstance.tenant_id == tenant_id,
                ProviderInstance.vendor == vendor,
                ProviderInstance.is_default == True
            ).update({"is_default": False})

        instance = ProviderInstance(
            tenant_id=tenant_id,
            vendor=vendor,
            instance_name=instance_name,
            base_url=base_url,
            api_key_encrypted=api_key_encrypted,
            available_models=available_models or [],
            is_default=is_default,
        )
        db.add(instance)
        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def update_instance(instance_id: int, tenant_id: str, db: Session, **kwargs) -> Optional[ProviderInstance]:
        """Update instance. Re-validates base_url. Blank api_key keeps existing."""
        instance = ProviderInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return None

        if "base_url" in kwargs and kwargs["base_url"]:
            from utils.ssrf_validator import validate_url, validate_ollama_url, SSRFValidationError
            try:
                if instance.vendor == "ollama":
                    validate_ollama_url(kwargs["base_url"])
                else:
                    validate_url(kwargs["base_url"])
            except SSRFValidationError as e:
                raise ValueError(f"URL validation failed: {e}")

        if "api_key" in kwargs:
            api_key = kwargs.pop("api_key")
            if api_key:  # Non-empty = update
                instance.api_key_encrypted = ProviderInstanceService._encrypt_key(api_key, tenant_id, db)
            # Empty/None = keep existing

        if kwargs.get("is_default"):
            db.query(ProviderInstance).filter(
                ProviderInstance.tenant_id == tenant_id,
                ProviderInstance.vendor == instance.vendor,
                ProviderInstance.id != instance_id,
                ProviderInstance.is_default == True
            ).update({"is_default": False})

        for key, value in kwargs.items():
            if value is not None and hasattr(instance, key):
                setattr(instance, key, value)

        db.commit()
        db.refresh(instance)
        return instance

    @staticmethod
    def delete_instance(instance_id: int, tenant_id: str, db: Session) -> bool:
        """Soft delete: set is_active=False. Clear provider_instance_id on affected agents."""
        instance = ProviderInstanceService.get_instance(instance_id, tenant_id, db)
        if not instance:
            return False

        from models import Agent
        db.query(Agent).filter(Agent.provider_instance_id == instance_id).update({"provider_instance_id": None})
        instance.is_active = False
        db.commit()
        return True

    @staticmethod
    def resolve_api_key(instance: ProviderInstance, db: Session) -> Optional[str]:
        """Decrypt instance key. Falls back to get_api_key() if no instance key."""
        if instance.api_key_encrypted:
            return ProviderInstanceService._decrypt_key(instance.api_key_encrypted, instance.tenant_id, db)
        # Fallback to legacy key resolution
        from services.api_key_service import get_api_key
        return get_api_key(instance.vendor, db, tenant_id=instance.tenant_id)

    @staticmethod
    def log_connection_audit(tenant_id: str, user_id: int, instance_id: int, action: str,
                             base_url: str, success: bool, db: Session,
                             resolved_ip: str = None, error_message: str = None):
        """Log a connection audit entry."""
        entry = ProviderConnectionAudit(
            tenant_id=tenant_id,
            user_id=user_id,
            provider_instance_id=instance_id,
            action=action,
            resolved_ip=resolved_ip,
            base_url=base_url,
            success=success,
            error_message=error_message,
        )
        db.add(entry)
        db.commit()

    @staticmethod
    def mask_api_key(encrypted_key: str, tenant_id: str, db: Session) -> str:
        """Return masked version of key for display: sk-...xyz"""
        if not encrypted_key:
            return ""
        try:
            decrypted = ProviderInstanceService._decrypt_key(encrypted_key, tenant_id, db)
            if len(decrypted) <= 8:
                return "***"
            return f"{decrypted[:3]}...{decrypted[-3:]}"
        except Exception:
            return "***"

    @staticmethod
    def _encrypt_key(api_key: str, tenant_id: str, db: Session) -> str:
        """
        Encrypt API key using Fernet with tenant-specific key derivation.
        Follows the same pattern as api_key_service._encrypt_api_key():
        1. Retrieve master encryption key via encryption_key_service
        2. Instantiate TokenEncryption with master key
        3. Derive workspace-specific key using identifier
        """
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            raise ValueError("Failed to get encryption key for provider instance API key encryption")

        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"provider_instance_{tenant_id}"
        return encryptor.encrypt(api_key, identifier)

    @staticmethod
    def _decrypt_key(encrypted_key: str, tenant_id: str, db: Session) -> str:
        """
        Decrypt API key using Fernet with tenant-specific key derivation.
        Mirrors _encrypt_key: retrieves master key, derives workspace key, decrypts.
        """
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            raise ValueError("Failed to get encryption key for provider instance API key decryption")

        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"provider_instance_{tenant_id}"
        return encryptor.decrypt(encrypted_key, identifier)
