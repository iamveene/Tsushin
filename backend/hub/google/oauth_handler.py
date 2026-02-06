"""
Google OAuth 2.0 Handler

Handles OAuth authorization flow for Gmail and Google Calendar integrations.
Supports per-tenant credentials (BYOT - Bring Your Own Token) and multi-account
per tenant.

Features:
- Per-tenant Google Cloud OAuth credentials
- Multi-account support (multiple Gmail/Calendar per tenant)
- CSRF protection via state tokens
- Per-integration token encryption
- Automatic token refresh

Required Google Cloud Setup:
1. Create project in Google Cloud Console
2. Enable Gmail API and Google Calendar API
3. Configure OAuth consent screen
4. Create OAuth 2.0 credentials (Web application)
5. Add authorized redirect URI: {your_domain}/api/hub/google/oauth/callback
"""

import os
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode
import httpx
from sqlalchemy.orm import Session

import settings
from models import (
    HubIntegration,
    OAuthToken,
    GoogleOAuthCredentials,
    GmailIntegration,
    CalendarIntegration,
)
from hub.security import TokenEncryption, OAuthStateManager, mask_token

logger = logging.getLogger(__name__)


class GoogleOAuthHandler:
    """
    Handles OAuth 2.0 flow for Google APIs (Gmail, Calendar).

    Supports per-tenant OAuth credentials (BYOT model) where each tenant
    configures their own Google Cloud project credentials.

    Security features:
    - Per-tenant OAuth credentials (isolation)
    - OAuth state validation (CSRF protection)
    - Per-integration key derivation (PBKDF2HMAC)
    - Token masking in logs
    - Automatic token refresh with rotation

    Example:
        handler = GoogleOAuthHandler(db, encryption_key, "acme-corp")

        # Generate authorization URL
        url, state = await handler.generate_authorization_url(
            integration_type="calendar",
            scopes=["calendar.events"]
        )

        # Handle callback
        result = await handler.handle_callback(code, state)
    """

    # Google OAuth endpoints
    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    REVOKE_URL = "https://oauth2.googleapis.com/revoke"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    # Default scopes by integration type
    DEFAULT_SCOPES = {
        "gmail": [
            "https://www.googleapis.com/auth/gmail.readonly",  # Read-only access
            "https://www.googleapis.com/auth/userinfo.email",
        ],
        "calendar": [
            "https://www.googleapis.com/auth/calendar",  # Full calendar access
            "https://www.googleapis.com/auth/userinfo.email",
        ],
    }

    def __init__(
        self,
        db: Session,
        encryption_key: str,
        tenant_id: str,
        redirect_uri: Optional[str] = None
    ):
        """
        Initialize Google OAuth handler.

        Args:
            db: Database session
            encryption_key: Master encryption key (Fernet key)
            tenant_id: Tenant ID for credential lookup
            redirect_uri: OAuth callback URL (optional, uses env default)
        """
        self.db = db
        self.tenant_id = tenant_id
        self.encryption_key = encryption_key
        self.redirect_uri = redirect_uri or settings.GOOGLE_OAUTH_REDIRECT_URI

        # Initialize security components
        self.token_encryption = TokenEncryption(encryption_key.encode())
        self.state_manager = OAuthStateManager(db)

        # Cached credentials (loaded lazily)
        self._credentials: Optional[GoogleOAuthCredentials] = None

    def _get_credentials(self) -> GoogleOAuthCredentials:
        """
        Get OAuth credentials for this tenant.

        Returns:
            GoogleOAuthCredentials for the tenant

        Raises:
            ValueError: If credentials not configured for tenant
        """
        if self._credentials:
            return self._credentials

        self._credentials = self.db.query(GoogleOAuthCredentials).filter(
            GoogleOAuthCredentials.tenant_id == self.tenant_id
        ).first()

        if not self._credentials:
            raise ValueError(
                f"Google OAuth credentials not configured for tenant '{self.tenant_id}'. "
                "Please configure credentials in Hub settings."
            )

        return self._credentials

    def _decrypt_client_secret(self, credentials: GoogleOAuthCredentials) -> str:
        """Decrypt the client secret."""
        return self.token_encryption.decrypt(
            credentials.client_secret_encrypted,
            self.tenant_id  # Use tenant_id as context for key derivation
        )

    async def generate_authorization_url(
        self,
        integration_type: str,
        scopes: Optional[List[str]] = None,
        redirect_url: Optional[str] = None,
        display_name: Optional[str] = None,
        login_hint: Optional[str] = None
    ) -> tuple[str, str]:
        """
        Generate OAuth authorization URL with CSRF state token.

        Args:
            integration_type: "gmail" or "calendar"
            scopes: OAuth scopes (defaults to integration type defaults)
            redirect_url: URL to redirect after OAuth callback
            display_name: User-friendly name for this integration
            login_hint: Email hint for Google account selector

        Returns:
            Tuple of (authorization_url, state_token)

        Raises:
            ValueError: If credentials not configured
        """
        credentials = self._get_credentials()

        # Get scopes
        if scopes is None:
            scopes = self.DEFAULT_SCOPES.get(integration_type, [])

        # Build state with metadata
        state_metadata = {
            "integration_type": integration_type,
            "display_name": display_name,
        }

        # Encode metadata in redirect_url for retrieval in callback
        if redirect_url:
            from urllib.parse import urlparse, parse_qs, urlencode as url_encode, urlunparse
            parsed = urlparse(redirect_url)
            query_params = parse_qs(parsed.query)
            if display_name:
                query_params['display_name'] = [display_name]
            query_params['integration_type'] = [integration_type]
            new_query = url_encode(query_params, doseq=True)
            redirect_url = urlunparse((
                parsed.scheme, parsed.netloc, parsed.path,
                parsed.params, new_query, parsed.fragment
            ))

        # Generate state token with tenant_id for proper isolation
        state_token = self.state_manager.generate_state(
            integration_type=f'google_{integration_type}',
            expires_in_minutes=10,
            redirect_url=redirect_url,
            tenant_id=self.tenant_id
        )

        # Build authorization URL
        params = {
            "client_id": credentials.client_id,
            "redirect_uri": credentials.redirect_uri or self.redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state_token,
            "access_type": "offline",  # Request refresh token
            "prompt": "consent",  # Force consent to get refresh token
        }

        if login_hint:
            params["login_hint"] = login_hint

        auth_url = f"{self.AUTHORIZATION_URL}?{urlencode(params)}"

        logger.info(
            f"Generated Google OAuth URL for {integration_type} "
            f"(tenant: {self.tenant_id}, state: {mask_token(state_token)})"
        )

        return auth_url, state_token

    async def handle_callback(self, code: str, state: str) -> Dict:
        """
        Handle OAuth callback with state validation and token exchange.

        Args:
            code: Authorization code from Google
            state: State token for CSRF validation

        Returns:
            Dict with integration details:
            {
                "integration_id": int,
                "integration_type": str,
                "email": str,
                "display_name": str,
                "redirect_url": str | None
            }

        Raises:
            ValueError: If state validation fails or token exchange fails
        """
        # Validate state token (CSRF protection)
        # State was created with integration_type prefix like "google_calendar"
        redirect_url = self.state_manager.validate_state(state, None)  # Don't check type, it's encoded
        logger.info("Google OAuth state validated successfully")

        # Extract metadata from redirect_url
        integration_type = "calendar"  # default
        display_name = None

        if redirect_url:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(redirect_url)
            query_params = parse_qs(parsed.query)
            integration_type = query_params.get('integration_type', ['calendar'])[0]
            display_name = query_params.get('display_name', [None])[0]

        # Exchange code for tokens
        credentials = self._get_credentials()
        client_secret = self._decrypt_client_secret(credentials)

        token_response = await self._exchange_code_for_token(
            code,
            credentials.client_id,
            client_secret,
            credentials.redirect_uri or self.redirect_uri
        )

        access_token = token_response["access_token"]

        # Get user info (email)
        user_info = await self._get_user_info(access_token)
        email = user_info.get("email", "unknown@unknown.com")
        google_user_id = user_info.get("id")

        logger.info(f"Google OAuth: User {email} authorized for {integration_type}")

        # Create or update integration
        if integration_type == "gmail":
            integration = await self._create_gmail_integration(
                email, google_user_id, display_name
            )
        else:
            integration = await self._create_calendar_integration(
                email, google_user_id, display_name
            )

        # Save encrypted tokens
        await self._save_token(integration.id, email, token_response)

        self.db.commit()

        logger.info(f"Google OAuth completed: integration_id={integration.id}, type={integration_type}")

        return {
            "integration_id": integration.id,
            "integration_type": integration_type,
            "email": email,
            "display_name": display_name or f"{integration_type.title()} - {email}",
            "redirect_url": redirect_url,
        }

    async def _exchange_code_for_token(
        self,
        code: str,
        client_id: str,
        client_secret: str,
        redirect_uri: str
    ) -> Dict:
        """Exchange authorization code for access token."""
        logger.info("Exchanging Google authorization code for token")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "redirect_uri": redirect_uri,
                    "code": code,
                }
            )
            response.raise_for_status()
            token_data = response.json()

        logger.info(f"Token exchange successful: {mask_token(token_data.get('access_token', ''))}")
        return token_data

    async def _get_user_info(self, access_token: str) -> Dict:
        """Get user info from Google."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"}
            )
            response.raise_for_status()
            return response.json()

    async def _create_gmail_integration(
        self,
        email: str,
        google_user_id: Optional[str],
        display_name: Optional[str]
    ) -> GmailIntegration:
        """Create or update Gmail integration."""
        # Check for existing integration with same email for this tenant
        existing = self.db.query(GmailIntegration).join(HubIntegration).filter(
            GmailIntegration.email_address == email,
            HubIntegration.tenant_id == self.tenant_id,
            HubIntegration.type == 'gmail'
        ).first()

        if existing:
            # Update existing
            existing.authorized_at = datetime.utcnow()
            existing.google_user_id = google_user_id
            if display_name:
                existing.display_name = display_name

            # Update base integration
            base = self.db.query(HubIntegration).filter(
                HubIntegration.id == existing.id
            ).first()
            if base:
                base.is_active = True
                base.health_status = "unknown"
                if display_name:
                    base.display_name = display_name

            logger.info(f"Updated existing Gmail integration: {existing.id}")
            return existing

        # Create new integration
        integration = GmailIntegration(
            type='gmail',
            name=f"Gmail - {email}",
            display_name=display_name,
            tenant_id=self.tenant_id,
            is_active=True,
            health_status="unknown",
            email_address=email,
            google_user_id=google_user_id,
            authorized_at=datetime.utcnow(),
        )
        self.db.add(integration)
        self.db.flush()

        logger.info(f"Created Gmail integration: {integration.id}")
        return integration

    async def _create_calendar_integration(
        self,
        email: str,
        google_user_id: Optional[str],
        display_name: Optional[str]
    ) -> CalendarIntegration:
        """Create or update Calendar integration."""
        # Check for existing integration with same email for this tenant
        existing = self.db.query(CalendarIntegration).join(HubIntegration).filter(
            CalendarIntegration.email_address == email,
            HubIntegration.tenant_id == self.tenant_id,
            HubIntegration.type == 'calendar'
        ).first()

        if existing:
            # Update existing
            existing.authorized_at = datetime.utcnow()
            existing.google_user_id = google_user_id
            if display_name:
                existing.display_name = display_name

            # Update base integration
            base = self.db.query(HubIntegration).filter(
                HubIntegration.id == existing.id
            ).first()
            if base:
                base.is_active = True
                base.health_status = "unknown"
                if display_name:
                    base.display_name = display_name

            logger.info(f"Updated existing Calendar integration: {existing.id}")
            return existing

        # Create new integration
        integration = CalendarIntegration(
            type='calendar',
            name=f"Calendar - {email}",
            display_name=display_name,
            tenant_id=self.tenant_id,
            is_active=True,
            health_status="unknown",
            email_address=email,
            google_user_id=google_user_id,
            default_calendar_id='primary',
            timezone='America/Sao_Paulo',
            authorized_at=datetime.utcnow(),
        )
        self.db.add(integration)
        self.db.flush()

        logger.info(f"Created Calendar integration: {integration.id}")
        return integration

    async def _save_token(
        self,
        integration_id: int,
        email: str,
        token_response: Dict
    ) -> OAuthToken:
        """Save OAuth token to database with encryption."""
        access_token = token_response["access_token"]
        refresh_token = token_response.get("refresh_token", "")
        expires_in = token_response.get("expires_in", 3600)

        # Calculate expiration time
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Encrypt tokens with email as context
        access_encrypted = self.token_encryption.encrypt(access_token, email)
        refresh_encrypted = self.token_encryption.encrypt(refresh_token, email) if refresh_token else ""

        # Delete old tokens for this integration
        self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == integration_id
        ).delete()

        # Create new token record
        token = OAuthToken(
            integration_id=integration_id,
            access_token_encrypted=access_encrypted,
            refresh_token_encrypted=refresh_encrypted,
            expires_at=expires_at,
            scope=token_response.get("scope"),
            last_refreshed_at=datetime.utcnow()
        )

        self.db.add(token)
        self.db.flush()

        logger.info(f"Token saved for integration {integration_id}, expires at {expires_at}")
        return token

    async def refresh_access_token(
        self,
        integration_id: int,
        email: str
    ) -> Optional[str]:
        """
        Refresh access token for an integration.

        Args:
            integration_id: Integration ID
            email: Email for decryption context

        Returns:
            New access token or None if refresh fails
        """
        # Get token
        token = self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == integration_id
        ).order_by(OAuthToken.created_at.desc()).first()

        if not token:
            logger.warning(f"No token found for integration {integration_id}")
            return None

        try:
            refresh_token = self.token_encryption.decrypt(
                token.refresh_token_encrypted, email
            )

            if not refresh_token:
                logger.warning(f"No refresh token for integration {integration_id}")
                self._mark_integration_unavailable(
                    integration_id,
                    "missing_refresh_token"
                )
                return None

            credentials = self._get_credentials()
            client_secret = self._decrypt_client_secret(credentials)

            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.TOKEN_URL,
                    data={
                        "grant_type": "refresh_token",
                        "client_id": credentials.client_id,
                        "client_secret": client_secret,
                        "refresh_token": refresh_token,
                    }
                )
                if response.status_code >= 400:
                    error_payload = {}
                    try:
                        error_payload = response.json()
                    except Exception:
                        error_payload = {"error": response.text[:500]}

                    error_code = error_payload.get("error")
                    error_description = error_payload.get("error_description") or error_payload.get("error")

                    logger.error(
                        "Token refresh failed for integration %s: HTTP %s (%s)",
                        integration_id,
                        response.status_code,
                        error_description or "unknown_error"
                    )

                    if error_code in {"invalid_grant", "invalid_client", "unauthorized_client", "access_denied"}:
                        self._mark_integration_unavailable(
                            integration_id,
                            error_description or error_code
                        )

                    return None

                token_data = response.json()

            # Update token (Google doesn't always return new refresh token)
            if "refresh_token" not in token_data:
                token_data["refresh_token"] = refresh_token

            # Save updated token
            new_token = await self._save_token(integration_id, email, token_data)
            self.db.commit()

            logger.info(f"Token refreshed for integration {integration_id}")
            return self.token_encryption.decrypt(new_token.access_token_encrypted, email)

        except Exception as e:
            logger.error(f"Token refresh failed for integration {integration_id}: {e}", exc_info=True)
            return None

    def _mark_integration_unavailable(self, integration_id: int, reason: str) -> None:
        """Mark integration as unavailable when refresh is permanently invalid."""
        try:
            integration = self.db.query(HubIntegration).filter(
                HubIntegration.id == integration_id
            ).first()

            if not integration:
                logger.warning(
                    "Could not mark integration %s unavailable: not found",
                    integration_id
                )
                return

            integration.is_active = False
            integration.health_status = "unavailable"
            integration.last_health_check = datetime.utcnow()
            self.db.commit()

            logger.warning(
                "Marked integration %s unavailable: %s",
                integration_id,
                reason
            )
        except Exception as e:
            logger.error(
                "Failed to mark integration %s unavailable: %s",
                integration_id,
                e,
                exc_info=True
            )

    async def get_valid_token(
        self,
        integration_id: int,
        email: str
    ) -> Optional[str]:
        """
        Get valid access token for integration, refreshing if needed.

        Args:
            integration_id: Integration ID
            email: Email for decryption context

        Returns:
            Valid access token or None if unavailable
        """
        # Get latest token
        token = self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == integration_id
        ).order_by(OAuthToken.created_at.desc()).first()

        if not token:
            logger.warning(f"No token found for integration {integration_id}")
            return None

        # Check if expired (with 5-minute buffer)
        now = datetime.utcnow()
        buffer = timedelta(minutes=5)

        if token.expires_at < now + buffer:
            logger.info(f"Token expired or expiring soon, refreshing for integration {integration_id}")
            return await self.refresh_access_token(integration_id, email)

        # Token still valid
        return self.token_encryption.decrypt(token.access_token_encrypted, email)

    async def disconnect_integration(self, integration_id: int) -> None:
        """
        Disconnect integration and revoke tokens.

        Args:
            integration_id: Integration ID to disconnect
        """
        # Get integration details
        integration = self.db.query(HubIntegration).filter(
            HubIntegration.id == integration_id,
            HubIntegration.tenant_id == self.tenant_id
        ).first()

        if not integration:
            logger.warning(f"Integration {integration_id} not found for tenant {self.tenant_id}")
            return

        # Get email for token decryption
        email = None
        if integration.type == 'gmail':
            gmail = self.db.query(GmailIntegration).filter(
                GmailIntegration.id == integration_id
            ).first()
            email = gmail.email_address if gmail else None
        elif integration.type == 'calendar':
            calendar = self.db.query(CalendarIntegration).filter(
                CalendarIntegration.id == integration_id
            ).first()
            email = calendar.email_address if calendar else None

        # Get token and try to revoke
        token = self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == integration_id
        ).first()

        if token and email:
            try:
                access_token = self.token_encryption.decrypt(
                    token.access_token_encrypted, email
                )

                async with httpx.AsyncClient(timeout=30.0) as client:
                    await client.post(
                        self.REVOKE_URL,
                        params={"token": access_token}
                    )

                logger.info(f"Token revoked for integration {integration_id}")
            except Exception as e:
                logger.warning(f"Token revocation failed: {e}")

        # Delete tokens
        self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == integration_id
        ).delete()

        # Deactivate integration
        integration.is_active = False

        self.db.commit()
        logger.info(f"Integration {integration_id} disconnected successfully")


# Convenience function for getting handler
def get_google_oauth_handler(
    db: Session,
    tenant_id: str,
    encryption_key: Optional[str] = None
) -> GoogleOAuthHandler:
    """
    Get Google OAuth handler for a tenant.

    Args:
        db: Database session
        tenant_id: Tenant ID
        encryption_key: Encryption key (defaults to env var)

    Returns:
        GoogleOAuthHandler instance
    """
    if not encryption_key:
        from services.encryption_key_service import get_google_encryption_key
        encryption_key = get_google_encryption_key(db)
        if not encryption_key:
            raise ValueError("GOOGLE_ENCRYPTION_KEY not configured in database or environment")

    return GoogleOAuthHandler(db, encryption_key, tenant_id)
