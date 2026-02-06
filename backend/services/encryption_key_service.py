"""
Encryption Key Service

Provides centralized access to encryption keys with database-first, environment fallback,
and auto-generation pattern. This enables SaaS-ready configuration where encryption keys
are automatically generated on first use and can be managed via UI.

Phase 7.10: SaaS-Ready Configuration
Phase 7.11: Auto-generation of encryption keys for seamless first-time setup
"""

import os
import logging
from typing import Optional
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def _is_valid_fernet_key(key: Optional[str]) -> bool:
    """
    Validate if a string is a valid Fernet key.

    Args:
        key: String to validate

    Returns:
        True if key is valid, False otherwise
    """
    if not key or not key.strip():
        return False

    try:
        Fernet(key.encode())
        return True
    except Exception:
        return False


def _generate_fernet_key() -> str:
    """
    Generate a new Fernet encryption key.

    Returns:
        Base64-encoded 32-byte Fernet key
    """
    return Fernet.generate_key().decode()


def _save_encryption_key_to_db(key_type: str, key: str, db: Session) -> bool:
    """
    Save encryption key to Config table.

    Args:
        key_type: Type of key ('google', 'asana', 'telegram', 'amadeus', or 'api_key')
        key: The encryption key to save
        db: Database session

    Returns:
        True if saved successfully, False otherwise
    """
    try:
        from models import Config
        config = db.query(Config).first()

        if not config:
            logger.warning(f"Config table is empty, cannot save {key_type} encryption key")
            return False

        if key_type == 'google':
            config.google_encryption_key = key
        elif key_type == 'asana':
            config.asana_encryption_key = key
        elif key_type == 'telegram':
            config.telegram_encryption_key = key
        elif key_type == 'amadeus':
            config.amadeus_encryption_key = key
        elif key_type == 'api_key':
            config.api_key_encryption_key = key
        else:
            logger.warning(f"Unknown key type: {key_type}")
            return False

        db.commit()
        logger.info(f"Auto-generated and saved {key_type} encryption key to database")
        return True

    except Exception as e:
        logger.error(f"Failed to save {key_type} encryption key to database: {e}")
        db.rollback()
        return False


def get_encryption_key(key_type: str, db: Session, auto_generate: bool = True) -> Optional[str]:
    """
    Get encryption key with priority: Database -> Environment -> Auto-generate.

    This enables seamless first-time setup for SaaS deployments where each tenant
    gets a unique encryption key automatically generated on first use.

    Args:
        key_type: Type of encryption key ('google', 'asana', 'telegram', 'amadeus', or 'api_key')
        db: Database session
        auto_generate: If True, generate and save a new key if none exists

    Returns:
        Encryption key string or None if not found and auto_generate is False

    Example:
        >>> encryption_key = get_encryption_key('google', db)
        >>> if encryption_key:
        ...     token_encryption = TokenEncryption(encryption_key.encode())
    """
    env_key_map = {
        'google': 'GOOGLE_ENCRYPTION_KEY',
        'asana': 'ASANA_ENCRYPTION_KEY',
        'telegram': 'TELEGRAM_ENCRYPTION_KEY',
        'amadeus': 'AMADEUS_ENCRYPTION_KEY',
        'api_key': 'API_KEY_ENCRYPTION_KEY',
    }

    # Step 1: Check database (Config table)
    try:
        from models import Config
        config = db.query(Config).first()

        if config:
            db_key = None
            if key_type == 'google':
                db_key = config.google_encryption_key
            elif key_type == 'asana':
                db_key = config.asana_encryption_key
            elif key_type == 'telegram':
                db_key = config.telegram_encryption_key
            elif key_type == 'amadeus':
                db_key = config.amadeus_encryption_key
            elif key_type == 'api_key':
                db_key = config.api_key_encryption_key

            if _is_valid_fernet_key(db_key):
                logger.debug(f"Using database encryption key for {key_type}")
                return db_key
            elif db_key:
                # Key exists but is invalid - log warning
                logger.warning(
                    f"Invalid {key_type} encryption key in database (not a valid Fernet key). "
                    "Will attempt fallback to environment variable or auto-generate."
                )
    except Exception as e:
        logger.warning(f"Failed to load encryption key from database for {key_type}: {e}")

    # Step 2: Fallback to environment variables
    env_var = env_key_map.get(key_type)
    if env_var:
        env_key = os.getenv(env_var)
        if _is_valid_fernet_key(env_key):
            logger.debug(f"Using environment variable encryption key for {key_type}")
            return env_key
        elif env_key:
            logger.warning(
                f"Invalid {key_type} encryption key in environment variable {env_var} "
                "(not a valid Fernet key)"
            )

    # Step 3: Auto-generate if enabled
    if auto_generate:
        logger.info(f"No valid {key_type} encryption key found. Auto-generating new key...")
        new_key = _generate_fernet_key()

        # Try to save to database for persistence
        if _save_encryption_key_to_db(key_type, new_key, db):
            logger.info(f"Successfully auto-generated and saved {key_type} encryption key")
            return new_key
        else:
            # Even if DB save fails, return the key for this session
            # (user will need to configure manually for persistence)
            logger.warning(
                f"Auto-generated {key_type} encryption key but failed to persist to database. "
                "Please configure manually in Settings > Security."
            )
            return new_key

    logger.warning(f"No encryption key found for {key_type}")
    return None


def get_google_encryption_key(db: Session) -> Optional[str]:
    """
    Get Google encryption key (for Gmail/Calendar OAuth tokens).

    Automatically generates a new key if none exists (SaaS-ready).

    Args:
        db: Database session

    Returns:
        Google encryption key (never None in normal operation)
    """
    return get_encryption_key('google', db, auto_generate=True)


def get_asana_encryption_key(db: Session) -> Optional[str]:
    """
    Get Asana encryption key (for Asana OAuth tokens only).

    Note: As of MED-001 security fix, this key is now exclusively for Asana.
    Telegram, Amadeus, and API keys now have their own dedicated keys.

    Automatically generates a new key if none exists (SaaS-ready).

    Args:
        db: Database session

    Returns:
        Asana encryption key (never None in normal operation)
    """
    return get_encryption_key('asana', db, auto_generate=True)


def get_telegram_encryption_key(db: Session) -> Optional[str]:
    """
    Get Telegram encryption key (for Telegram bot tokens).

    MED-001 Security Fix: Separated from shared asana_encryption_key to limit
    blast radius if one key is compromised.

    Automatically generates a new key if none exists (SaaS-ready).

    Args:
        db: Database session

    Returns:
        Telegram encryption key (never None in normal operation)
    """
    return get_encryption_key('telegram', db, auto_generate=True)


def get_amadeus_encryption_key(db: Session) -> Optional[str]:
    """
    Get Amadeus encryption key (for Amadeus API credentials).

    MED-001 Security Fix: Separated from shared asana_encryption_key to limit
    blast radius if one key is compromised.

    Automatically generates a new key if none exists (SaaS-ready).

    Args:
        db: Database session

    Returns:
        Amadeus encryption key (never None in normal operation)
    """
    return get_encryption_key('amadeus', db, auto_generate=True)


def get_api_key_encryption_key(db: Session) -> Optional[str]:
    """
    Get API Key encryption key (for LLM provider API keys).

    MED-001 Security Fix: Separated from shared asana_encryption_key to limit
    blast radius if one key is compromised.

    Automatically generates a new key if none exists (SaaS-ready).

    Args:
        db: Database session

    Returns:
        API Key encryption key (never None in normal operation)
    """
    return get_encryption_key('api_key', db, auto_generate=True)
