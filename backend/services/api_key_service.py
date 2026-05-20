"""
Legacy API key helpers.

The `api_key` table is retained only as a migration/audit source. Runtime
credential resolution must use typed configuration models such as
ProviderInstance, TTSInstance, SearchProviderIntegration, GoogleFlightsIntegration
or AmadeusIntegration. Any runtime call into get_api_key()/store_api_key() is a
bug and should fail closed.
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


def get_api_key(service: str, db: Session, tenant_id: Optional[str] = None) -> Optional[str]:
    raise RuntimeError(
        "Legacy api_key runtime resolver is retired. "
        "Use ProviderInstance or a typed integration model instead."
    )


def has_api_key(service: str, db: Session, tenant_id: Optional[str] = None) -> bool:
    """Legacy runtime availability checks are retired."""
    return False


def store_api_key(service: str, api_key: str, tenant_id: Optional[str], db: Session) -> ApiKey:
    raise RuntimeError(
        "Legacy api_key writes are retired. "
        "Create ProviderInstance or typed integration rows instead."
    )
