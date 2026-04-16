"""MCP utility functions."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def decrypt_auth_token(server_config) -> str:
    """Decrypt MCP server auth token using the system encryption key service.

    Uses the same encryption pattern as provider instances (api_key encryption key
    with per-resource workspace identifier derivation).

    Args:
        server_config: MCPServerConfig model instance with auth_token_encrypted set.

    Returns:
        Decrypted plaintext auth token.

    Raises:
        ValueError: If decryption fails or no encryption key is available.
    """
    from hub.security import TokenEncryption
    from services.encryption_key_service import get_api_key_encryption_key

    # We need a DB session to retrieve the encryption key from Config table.
    # Import here to avoid circular imports.
    from db import get_global_engine
    from sqlalchemy.orm import sessionmaker

    engine = get_global_engine()
    if not engine:
        raise ValueError("Database engine not initialized")

    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()
    try:
        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            raise ValueError("No encryption key available for MCP server token decryption")

        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"mcp_server_{server_config.id}"
        return encryptor.decrypt(server_config.auth_token_encrypted, identifier)
    finally:
        db.close()


def encrypt_auth_token(plaintext_token: str, server_id: int, db) -> Optional[str]:
    """Encrypt an MCP server auth token for storage.

    Args:
        plaintext_token: The raw auth token to encrypt.
        server_id: ID of the MCPServerConfig record (used in workspace identifier).
        db: SQLAlchemy session.

    Returns:
        Encrypted token string, or None on failure.
    """
    try:
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        encryption_key = get_api_key_encryption_key(db)
        if not encryption_key:
            logger.error("Failed to get encryption key for MCP server token encryption")
            return None

        encryptor = TokenEncryption(encryption_key.encode())
        identifier = f"mcp_server_{server_id}"
        return encryptor.encrypt(plaintext_token, identifier)
    except Exception as e:
        logger.error(f"Failed to encrypt MCP server token: {e}")
        return None
