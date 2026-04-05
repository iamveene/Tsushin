"""
Encryption Key Service

Provides centralized access to encryption keys with database-first, environment fallback,
and auto-generation pattern. This enables SaaS-ready configuration where encryption keys
are automatically generated on first use and can be managed via UI.

Phase 7.10: SaaS-Ready Configuration
Phase 7.11: Auto-generation of encryption keys for seamless first-time setup
SEC-006: Envelope encryption — Fernet keys wrapped with TSN_MASTER_KEY before DB storage
"""

import os
import logging
from typing import Optional
from sqlalchemy.orm import Session
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Master key helpers (SEC-006: envelope encryption)
# ---------------------------------------------------------------------------

def _get_master_key() -> Optional[bytes]:
    """
    Returns the master key used to wrap/unwrap Fernet encryption keys stored in DB.

    Reads TSN_MASTER_KEY from environment. Accepts either:
      - A 44-character base64url Fernet key (direct use)
      - A 32-byte value encoded as base64url (decoded then re-encoded as Fernet key)

    Returns None if TSN_MASTER_KEY is not set or invalid, which activates
    legacy plaintext mode (backward-compatible with existing deployments).

    To generate a valid key:
        python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    """
    import base64

    raw = os.environ.get("TSN_MASTER_KEY", "").strip()
    if raw:
        # Option 1: already a 44-char Fernet key (base64url-encoded 32-byte value)
        if len(raw) == 44:
            try:
                Fernet(raw.encode())  # validate it's a proper Fernet key
                return raw.encode()
            except Exception:
                pass

        # Option 2: a base64url string that decodes to exactly 32 bytes
        try:
            key_bytes = base64.urlsafe_b64decode(raw.encode())
            if len(key_bytes) == 32:
                fernet_key = base64.urlsafe_b64encode(key_bytes)
                Fernet(fernet_key)  # validate
                return fernet_key
        except Exception:
            pass

        logger.warning(
            "TSN_MASTER_KEY is set but invalid (must be a 44-char Fernet key or "
            "a base64url-encoded 32-byte value). Falling back to plaintext mode."
        )
        return None

    logger.warning(
        "TSN_MASTER_KEY is not set — Fernet encryption keys are stored in plaintext in the DB. "
        "Set TSN_MASTER_KEY to a 44-char Fernet key for envelope encryption (SEC-006). "
        "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
    )
    return None


def _wrap_key(raw_key: str) -> str:
    """
    Wrap a Fernet key with the master key for DB storage (SEC-006).

    If no master key is configured, returns the key unchanged (legacy/plaintext mode).
    """
    master_key = _get_master_key()
    if master_key is None:
        return raw_key  # legacy: store plaintext
    f = Fernet(master_key)
    return f.encrypt(raw_key.encode()).decode()


def _unwrap_key(stored_key: str) -> str:
    """
    Unwrap a stored Fernet key using the master key (SEC-006).

    Handles both wrapped (envelope-encrypted) and legacy plaintext keys gracefully.
    If the master key is not set, returns the stored key as-is (legacy mode).
    If decryption fails (e.g. key was stored before TSN_MASTER_KEY was introduced),
    falls back to returning the stored value and logs a warning.
    """
    master_key = _get_master_key()
    if master_key is None:
        return stored_key  # legacy mode: treat as plaintext
    try:
        f = Fernet(master_key)
        return f.decrypt(stored_key.encode()).decode()
    except Exception:
        # Fallback: key may be stored in legacy plaintext format (pre-SEC-006)
        logger.warning(
            "Could not decrypt wrapped key with TSN_MASTER_KEY — treating as plaintext. "
            "Run migration wrap_encryption_keys.py to wrap existing keys."
        )
        return stored_key


# ---------------------------------------------------------------------------
# Validation and generation helpers
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# DB read/write helpers
# ---------------------------------------------------------------------------

def _save_encryption_key_to_db(key_type: str, key: str, db: Session) -> bool:
    """
    Save encryption key to Config table.

    The key is wrapped with TSN_MASTER_KEY before storing (envelope encryption, SEC-006).
    In legacy mode (TSN_MASTER_KEY not set), the key is stored as plaintext.

    Args:
        key_type: Type of key ('google', 'asana', 'telegram', 'amadeus', 'api_key', 'slack', or 'discord')
        key: The plaintext encryption key to save
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

        # Wrap the key before storing (SEC-006)
        wrapped = _wrap_key(key)

        if key_type == 'google':
            config.google_encryption_key = wrapped
        elif key_type == 'asana':
            config.asana_encryption_key = wrapped
        elif key_type == 'telegram':
            config.telegram_encryption_key = wrapped
        elif key_type == 'amadeus':
            config.amadeus_encryption_key = wrapped
        elif key_type == 'api_key':
            config.api_key_encryption_key = wrapped
        elif key_type == 'slack':
            config.slack_encryption_key = wrapped
        elif key_type == 'discord':
            config.discord_encryption_key = wrapped
        elif key_type == 'webhook':
            config.webhook_encryption_key = wrapped
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

    Keys stored in the DB are unwrapped using TSN_MASTER_KEY before being returned
    (envelope encryption, SEC-006). Keys from environment variables are returned as-is
    (they are never wrapped).

    This enables seamless first-time setup for SaaS deployments where each tenant
    gets a unique encryption key automatically generated on first use.

    Args:
        key_type: Type of encryption key ('google', 'asana', 'telegram', 'amadeus', 'api_key', 'slack', or 'discord')
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
        'slack': 'SLACK_ENCRYPTION_KEY',
        'discord': 'DISCORD_ENCRYPTION_KEY',
        'webhook': 'WEBHOOK_ENCRYPTION_KEY',
    }

    # Step 1: Check database (Config table)
    try:
        from models import Config
        config = db.query(Config).first()

        if config:
            stored_key = None
            if key_type == 'google':
                stored_key = config.google_encryption_key
            elif key_type == 'asana':
                stored_key = config.asana_encryption_key
            elif key_type == 'telegram':
                stored_key = config.telegram_encryption_key
            elif key_type == 'amadeus':
                stored_key = config.amadeus_encryption_key
            elif key_type == 'api_key':
                stored_key = config.api_key_encryption_key
            elif key_type == 'slack':
                stored_key = config.slack_encryption_key
            elif key_type == 'discord':
                stored_key = config.discord_encryption_key
            elif key_type == 'webhook':
                stored_key = config.webhook_encryption_key

            if stored_key:
                # Unwrap the stored key (SEC-006 envelope decryption)
                db_key = _unwrap_key(stored_key)
                if _is_valid_fernet_key(db_key):
                    logger.debug(f"Using database encryption key for {key_type}")
                    return db_key
                else:
                    # Key exists but is invalid after unwrapping - log warning
                    logger.warning(
                        f"Invalid {key_type} encryption key in database (not a valid Fernet key after unwrap). "
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


def get_slack_encryption_key(db: Session) -> Optional[str]:
    """
    Get Slack encryption key (for Slack bot/app tokens).

    v0.6.0 Item 33: Dedicated encryption key for Slack integration tokens.

    Automatically generates a new key if none exists (SaaS-ready).

    Args:
        db: Database session

    Returns:
        Slack encryption key (never None in normal operation)
    """
    return get_encryption_key('slack', db, auto_generate=True)


def get_discord_encryption_key(db: Session) -> Optional[str]:
    """
    Get Discord encryption key (for Discord bot tokens).

    v0.6.0 Item 34: Dedicated encryption key for Discord integration tokens.

    Automatically generates a new key if none exists (SaaS-ready).

    Args:
        db: Database session

    Returns:
        Discord encryption key (never None in normal operation)
    """
    return get_encryption_key('discord', db, auto_generate=True)


def get_webhook_encryption_key(db: Session) -> Optional[str]:
    """
    Get Webhook encryption key (for webhook HMAC secrets).

    v0.6.0: Dedicated encryption key for WebhookIntegration.api_secret_encrypted.

    Automatically generates a new key if none exists (SaaS-ready).

    Args:
        db: Database session

    Returns:
        Webhook encryption key (never None in normal operation)
    """
    return get_encryption_key('webhook', db, auto_generate=True)
