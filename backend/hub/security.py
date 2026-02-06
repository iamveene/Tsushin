"""
Security utilities for Hub integrations.

Provides:
- Token masking for logging
- OAuth state generation and validation
- Per-workspace key derivation
"""

import secrets
import logging
from typing import Optional, Dict, Any, Tuple
import json
from datetime import datetime, timedelta
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

logger = logging.getLogger(__name__)


def mask_token(token: str, prefix_len: int = 4, suffix_len: int = 4) -> str:
    """
    Mask token for safe logging.

    Args:
        token: Token to mask
        prefix_len: Number of characters to show at start
        suffix_len: Number of characters to show at end

    Returns:
        Masked token (e.g., "sk-ab...xyz")

    Examples:
        >>> mask_token("sk-abc123def456ghi789")
        "sk-a...9"
        >>> mask_token("very_short")
        "***"
    """
    if not token:
        return "***"

    if len(token) <= (prefix_len + suffix_len):
        return "***"

    return f"{token[:prefix_len]}...{token[-suffix_len:]}"


def generate_oauth_state() -> str:
    """
    Generate cryptographically secure OAuth state token.

    Returns:
        32-byte URL-safe random string

    Example:
        >>> state = generate_oauth_state()
        >>> len(state)
        43  # Base64-encoded 32 bytes
    """
    return secrets.token_urlsafe(32)


def derive_workspace_key(
    master_key: bytes,
    workspace_identifier: str,
    iterations: int = 100000
) -> bytes:
    """
    Derive encryption key for specific workspace using PBKDF2.

    This provides defense-in-depth: compromising one workspace's key
    doesn't expose tokens for other workspaces.

    Args:
        master_key: Master encryption key from environment
        workspace_identifier: Unique workspace identifier (e.g., workspace_gid)
        iterations: PBKDF2 iteration count (default: 100,000)

    Returns:
        32-byte derived key (URL-safe Base64 encoded for Fernet)

    Security:
        - Uses SHA256 for hashing
        - 100,000 iterations (OWASP recommendation for 2024)
        - Workspace identifier as salt (unique per workspace)

    Example:
        >>> master_key = Fernet.generate_key()
        >>> key1 = derive_workspace_key(master_key, "workspace_123")
        >>> key2 = derive_workspace_key(master_key, "workspace_456")
        >>> key1 != key2
        True
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=workspace_identifier.encode(),
        iterations=iterations,
    )
    derived = kdf.derive(master_key)
    return base64.urlsafe_b64encode(derived)


class TokenEncryption:
    """
    Token encryption/decryption with per-workspace key derivation.

    Usage:
        >>> encryption = TokenEncryption(master_key)
        >>> encrypted = encryption.encrypt("secret_token", "workspace_123")
        >>> decrypted = encryption.decrypt(encrypted, "workspace_123")
        >>> decrypted == "secret_token"
        True
    """

    def __init__(self, master_key: bytes):
        """
        Initialize token encryption.

        Args:
            master_key: Master encryption key (any bytes, will be used to derive
                        workspace-specific Fernet keys via PBKDF2)

        Raises:
            ValueError: If master_key is empty
        """
        if not master_key:
            raise ValueError("Master key cannot be empty")

        # Note: We no longer validate that master_key is a valid Fernet key
        # because derive_workspace_key() will derive a proper 32-byte key
        # from any bytes input using PBKDF2. This allows using JWT_SECRET_KEY
        # or any other secret as the master key.

        self.master_key = master_key

    def encrypt(self, token: str, workspace_identifier: str) -> str:
        """
        Encrypt token using workspace-specific key.

        Args:
            token: Token to encrypt
            workspace_identifier: Workspace identifier for key derivation

        Returns:
            Encrypted token (Base64-encoded)

        Raises:
            ValueError: If inputs are invalid
        """
        if not token:
            raise ValueError("Token cannot be empty")
        if not workspace_identifier:
            raise ValueError("Workspace identifier cannot be empty")

        workspace_key = derive_workspace_key(self.master_key, workspace_identifier)
        cipher = Fernet(workspace_key)
        encrypted = cipher.encrypt(token.encode())

        logger.debug(f"Encrypted token for workspace {workspace_identifier}: {mask_token(token)}")
        return encrypted.decode()

    def decrypt(self, encrypted_token: str, workspace_identifier: str) -> str:
        """
        Decrypt token using workspace-specific key.

        Args:
            encrypted_token: Encrypted token (Base64-encoded)
            workspace_identifier: Workspace identifier for key derivation

        Returns:
            Decrypted token

        Raises:
            ValueError: If inputs are invalid or decryption fails
        """
        if not encrypted_token:
            raise ValueError("Encrypted token cannot be empty")
        if not workspace_identifier:
            raise ValueError("Workspace identifier cannot be empty")

        try:
            workspace_key = derive_workspace_key(self.master_key, workspace_identifier)
            cipher = Fernet(workspace_key)
            decrypted = cipher.decrypt(encrypted_token.encode())

            logger.debug(f"Decrypted token for workspace {workspace_identifier}")
            return decrypted.decode()
        except Exception as e:
            logger.error(f"Token decryption failed for workspace {workspace_identifier}: {e}")
            raise ValueError("Token decryption failed (invalid key or corrupted data)")


class OAuthStateManager:
    """
    Manages OAuth state tokens for CSRF protection.

    Stores state tokens in database with expiration for validation.
    """

    def __init__(self, db_session):
        """
        Initialize OAuth state manager.

        Args:
            db_session: SQLAlchemy database session
        """
        self.db = db_session

    def generate_state(
        self,
        integration_type: str,
        expires_in_minutes: int = 10,
        redirect_url: Optional[str] = None,
        tenant_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Generate and store OAuth state token.

        Args:
            integration_type: Integration type (e.g., 'asana', 'slack', 'google_sso')
            expires_in_minutes: State expiration time (default: 10 minutes)
            redirect_url: Optional URL to redirect after OAuth callback
            tenant_id: Tenant ID that initiated the OAuth flow
            metadata: Optional additional metadata (tenant_slug, invitation_token, etc.)

        Returns:
            Generated state token

        Example:
            >>> manager = OAuthStateManager(db)
            >>> state = manager.generate_state('asana', redirect_url='/dashboard', tenant_id='tenant_123')
            >>> len(state)
            43

        HIGH-004 Enhancement:
            >>> state = manager.generate_state(
            ...     'google_sso',
            ...     tenant_id='t123',
            ...     metadata={'tenant_slug': 'acme', 'invitation_token': 'inv_abc'}
            ... )
        """
        from models import OAuthState

        state_token = generate_oauth_state()
        expires_at = datetime.utcnow() + timedelta(minutes=expires_in_minutes)

        # Serialize metadata to JSON if provided
        metadata_json = json.dumps(metadata) if metadata else None

        oauth_state = OAuthState(
            state_token=state_token,
            integration_type=integration_type,
            expires_at=expires_at,
            redirect_url=redirect_url,
            tenant_id=tenant_id,
            metadata_json=metadata_json,
        )

        self.db.add(oauth_state)
        self.db.commit()

        logger.info(f"Generated OAuth state for {integration_type} (tenant: {tenant_id}): {mask_token(state_token)}")
        return state_token

    def validate_state(
        self,
        state_token: str,
        integration_type: Optional[str] = None
    ) -> Optional[str]:
        """
        Validate OAuth state token and delete after use.

        Args:
            state_token: State token from OAuth callback
            integration_type: Expected integration type (None to accept any)

        Returns:
            redirect_url if state is valid, None otherwise

        Raises:
            ValueError: If state is invalid or expired

        Example:
            >>> manager = OAuthStateManager(db)
            >>> state = manager.generate_state('asana')
            >>> redirect_url = manager.validate_state(state, 'asana')
            >>> # Second call should fail (one-time use)
            >>> manager.validate_state(state, 'asana')
            ValueError: Invalid or expired state token
        """
        from models import OAuthState

        query = self.db.query(OAuthState).filter(
            OAuthState.state_token == state_token,
            OAuthState.expires_at > datetime.utcnow()
        )

        # Only filter by integration_type if provided
        if integration_type is not None:
            query = query.filter(OAuthState.integration_type == integration_type)

        oauth_state = query.first()

        if not oauth_state:
            logger.warning(f"Invalid or expired OAuth state: {mask_token(state_token)}")
            raise ValueError("Invalid or expired state token (CSRF protection)")

        redirect_url = oauth_state.redirect_url

        # Delete state after use (one-time token)
        self.db.delete(oauth_state)
        self.db.commit()

        logger.info(f"OAuth state validated for {integration_type}: {mask_token(state_token)}")
        return redirect_url

    def validate_state_extended(
        self,
        state_token: str,
        integration_type: Optional[str] = None
    ) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """
        Validate OAuth state token and return extended information including metadata.

        Security Fix HIGH-004: Supports GoogleSSOService database-backed state with metadata.

        Args:
            state_token: State token from OAuth callback
            integration_type: Expected integration type (None to accept any)

        Returns:
            Tuple of (redirect_url, tenant_id, metadata_dict)

        Raises:
            ValueError: If state is invalid or expired

        Example:
            >>> manager = OAuthStateManager(db)
            >>> state = manager.generate_state(
            ...     'google_sso',
            ...     tenant_id='t123',
            ...     redirect_url='/dashboard',
            ...     metadata={'tenant_slug': 'acme', 'invitation_token': 'inv_abc'}
            ... )
            >>> redirect_url, tenant_id, metadata = manager.validate_state_extended(state, 'google_sso')
            >>> metadata['tenant_slug']
            'acme'
        """
        from models import OAuthState

        query = self.db.query(OAuthState).filter(
            OAuthState.state_token == state_token,
            OAuthState.expires_at > datetime.utcnow()
        )

        # Only filter by integration_type if provided
        if integration_type is not None:
            query = query.filter(OAuthState.integration_type == integration_type)

        oauth_state = query.first()

        if not oauth_state:
            logger.warning(f"Invalid or expired OAuth state: {mask_token(state_token)}")
            raise ValueError("Invalid or expired state token (CSRF protection)")

        redirect_url = oauth_state.redirect_url
        tenant_id = oauth_state.tenant_id
        metadata = {}

        # Parse metadata JSON if present
        if oauth_state.metadata_json:
            try:
                metadata = json.loads(oauth_state.metadata_json)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse metadata for state: {mask_token(state_token)}")

        # Delete state after use (one-time token)
        self.db.delete(oauth_state)
        self.db.commit()

        logger.info(f"OAuth state validated (extended) for {integration_type}: {mask_token(state_token)}")
        return redirect_url, tenant_id, metadata

    def cleanup_expired_states(self) -> int:
        """
        Delete expired OAuth states from database.

        Should be called periodically (e.g., daily cron job).

        Returns:
            Number of deleted states

        Example:
            >>> manager = OAuthStateManager(db)
            >>> deleted_count = manager.cleanup_expired_states()
            >>> print(f"Deleted {deleted_count} expired states")
        """
        from models import OAuthState

        expired_states = self.db.query(OAuthState).filter(
            OAuthState.expires_at <= datetime.utcnow()
        ).all()

        count = len(expired_states)

        for state in expired_states:
            self.db.delete(state)

        self.db.commit()

        logger.info(f"Cleaned up {count} expired OAuth states")
        return count
