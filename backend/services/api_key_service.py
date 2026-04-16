"""
Phase 4.6: API Key Service
Phase SEC-001: Added encryption at rest for API keys (CRIT-003 fix).

Centralized service for loading API keys from database.
Configure via Settings → Integrations or Hub → API Keys UI (encrypted at rest).

Priority order:
1. Tenant-specific database key (if tenant_id provided)
2. System-wide database key (tenant_id = NULL)

No env var fallback — all keys must be stored in the database.
"""

from typing import Optional
from sqlalchemy.orm import Session
from models import ApiKey
import logging

logger = logging.getLogger(__name__)

# No env var fallback — all API keys must be configured via UI/DB.
# This ensures DB misconfigurations surface immediately instead of being
# masked by stale env vars.


def _decrypt_api_key(api_key_record: ApiKey, db: Session) -> Optional[str]:
    """
    Decrypt an API key from its encrypted form.
    Falls back to plaintext for backward compatibility during migration.

    Args:
        api_key_record: The ApiKey database record
        db: Database session (needed for encryption key retrieval)

    Returns:
        Decrypted API key string or None if decryption fails
    """
    # Try encrypted field first (new format)
    if api_key_record.api_key_encrypted:
        try:
            from hub.security import TokenEncryption
            from services.encryption_key_service import get_api_key_encryption_key

            # MED-001 security fix: Use dedicated API key encryption key
            encryption_key = get_api_key_encryption_key(db)
            if encryption_key:
                encryptor = TokenEncryption(encryption_key.encode())
                # Use service + tenant as identifier for key derivation
                identifier = f"apikey_{api_key_record.service}_{api_key_record.tenant_id or 'system'}"
                decrypted = encryptor.decrypt(api_key_record.api_key_encrypted, identifier)
                return decrypted
            else:
                logger.error("Failed to get encryption key for API key decryption")
        except Exception as e:
            logger.error(f"Failed to decrypt API key for {api_key_record.service}: {e}")
            # Don't fall back to plaintext if decryption explicitly fails
            # This prevents security bypass if encryption key is wrong
            return None

    # Fall back to plaintext (legacy/migration compatibility)
    if api_key_record.api_key:
        logger.warning(f"Using plaintext API key for {api_key_record.service} - please run migration to encrypt")
        return api_key_record.api_key

    return None


def _encrypt_api_key(plaintext_key: str, service: str, tenant_id: Optional[str], db: Session) -> Optional[str]:
    """
    Encrypt an API key for storage.

    Args:
        plaintext_key: The plaintext API key to encrypt
        service: Service name (used in key derivation)
        tenant_id: Tenant ID (used in key derivation)
        db: Database session (needed for encryption key retrieval)

    Returns:
        Encrypted API key string or None if encryption fails
    """
    try:
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        # MED-001 security fix: Use dedicated API key encryption key
        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            logger.error("Failed to get encryption key for API key encryption")
            return None

        encryptor = TokenEncryption(encryption_key.encode())
        # Use service + tenant as identifier for key derivation
        identifier = f"apikey_{service}_{tenant_id or 'system'}"
        encrypted = encryptor.encrypt(plaintext_key, identifier)
        return encrypted
    except Exception as e:
        logger.error(f"Failed to encrypt API key for {service}: {e}")
        return None


def _decrypt_provider_instance_key(encrypted_key: str, tenant_id: str, db: Session) -> Optional[str]:
    """Decrypt a provider instance API key."""
    try:
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            return None
        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"provider_instance_{tenant_id}"
        return encryptor.decrypt(encrypted_key, identifier)
    except Exception as e:
        logger.error(f"Failed to decrypt provider instance key: {e}")
        return None


def get_api_key(service: str, db: Session, tenant_id: Optional[str] = None) -> Optional[str]:
    """
    Get API key for a service.

    Priority order:
    1. Tenant-specific service API key (if tenant_id provided)
    2. System-wide service API key (tenant_id = NULL)
    3. Provider instance key (default instance for matching vendor)

    Args:
        service: Service name ('anthropic', 'openai', 'gemini', 'openrouter', 'brave_search', 'amadeus', 'serpapi')
        db: Database session
        tenant_id: Optional tenant ID for multi-tenant key isolation

    Returns:
        API key string or None if not found
        Note: For 'amadeus', returns 'key:secret' concatenated with colon
    """
    if not db:
        logger.error(f"❌ get_api_key called with db=None for service={service}")
        return None

    # Step 1: Check tenant-specific database key
    if tenant_id:
        try:
            tenant_key = db.query(ApiKey).filter(
                ApiKey.service == service,
                ApiKey.tenant_id == tenant_id,
                ApiKey.is_active == True
            ).first()

            if tenant_key:
                logger.info(f" Using tenant-specific API key for {service} (tenant: {tenant_id})")
                return _decrypt_api_key(tenant_key, db)
        except Exception as e:
            logger.warning(f"Failed to load tenant-specific API key for {service}: {e}")

    # Step 2: Check system-wide database key (tenant_id = NULL)
    try:
        system_key = db.query(ApiKey).filter(
            ApiKey.service == service,
            ApiKey.tenant_id.is_(None),
            ApiKey.is_active == True
        ).first()

        if system_key:
            logger.info(f" Using system-wide API key for {service}")
            return _decrypt_api_key(system_key, db)
    except Exception as e:
        logger.warning(f"Failed to load system-wide API key from database for {service}: {e}")

    # Step 3: Fall back to provider instance key (reuse LLM provider key for TTS etc.)
    if tenant_id:
        try:
            from models import ProviderInstance
            instance = db.query(ProviderInstance).filter(
                ProviderInstance.vendor == service,
                ProviderInstance.tenant_id == tenant_id,
                ProviderInstance.is_active == True,
                ProviderInstance.is_default == True,
                ProviderInstance.api_key_encrypted.isnot(None)
            ).first()

            if instance:
                key = _decrypt_provider_instance_key(
                    instance.api_key_encrypted, tenant_id, db
                )
                if key:
                    logger.info(f" Using provider instance key for {service} (instance: {instance.instance_name})")
                    return key
        except Exception as e:
            logger.warning(f"Failed to load provider instance key for {service}: {e}")

    logger.warning(f"No API key found for {service}. Configure via Hub → AI Providers or Service API Keys.")
    return None


def has_api_key(service: str, db: Session) -> bool:
    """
    Check if an API key exists for a service.

    Args:
        service: Service name
        db: Database session

    Returns:
        True if key exists, False otherwise
    """
    return get_api_key(service, db) is not None


def store_api_key(service: str, api_key: str, tenant_id: Optional[str], db: Session) -> ApiKey:
    """
    Store or update an API key in the database (encrypted).
    Used by setup wizard to configure initial API keys.

    Args:
        service: Service name ('gemini', 'openai', 'anthropic', etc.)
        api_key: The API key value (plaintext - will be encrypted)
        tenant_id: Tenant ID (None for system-wide keys)
        db: Database session

    Returns:
        The created or updated ApiKey object
    """
    # Encrypt the API key
    encrypted_key = _encrypt_api_key(api_key, service, tenant_id, db)
    if not encrypted_key:
        raise ValueError(f"Failed to encrypt API key for {service}")

    # Check if key already exists
    existing_key = db.query(ApiKey).filter(
        ApiKey.service == service,
        ApiKey.tenant_id == tenant_id if tenant_id else ApiKey.tenant_id.is_(None)
    ).first()

    if existing_key:
        # Update existing key - store encrypted, clear plaintext
        existing_key.api_key_encrypted = encrypted_key
        existing_key.api_key = None  # Clear plaintext
        existing_key.is_active = True
        db.commit()
        logger.info(f"Updated API key for {service} (tenant: {tenant_id or 'system-wide'}) [encrypted]")
        return existing_key
    else:
        # Create new key - store encrypted only
        new_key = ApiKey(
            service=service,
            api_key=None,  # No plaintext
            api_key_encrypted=encrypted_key,
            tenant_id=tenant_id,
            is_active=True
        )
        db.add(new_key)
        db.commit()
        logger.info(f"Created API key for {service} (tenant: {tenant_id or 'system-wide'}) [encrypted]")
        return new_key
