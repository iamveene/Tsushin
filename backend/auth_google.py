"""
Google SSO Authentication Service
Phase: User Management & SSO

Handles Google OAuth 2.0 authentication for user sign-in.
Supports both platform-wide and tenant-specific Google credentials (BYOT).

Flow:
1. User clicks "Sign in with Google"
2. Backend generates OAuth authorization URL
3. User authenticates with Google
4. Google redirects back with auth code
5. Backend exchanges code for tokens, gets user info
6. Link to existing user OR create new (if auto-provision enabled)
7. Issue JWT token
"""

import logging
import json
from typing import Optional, Tuple, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import urlencode

import httpx
from sqlalchemy.orm import Session

import settings
from models_rbac import User, Tenant, TenantSSOConfig, UserRole, Role
from models import GoogleOAuthCredentials
from auth_utils import create_access_token
from hub.security import TokenEncryption, OAuthStateManager

logger = logging.getLogger(__name__)


class GoogleSSOError(Exception):
    """Custom exception for Google SSO errors."""
    pass


class GoogleSSOService:
    """
    Service for handling Google SSO authentication.

    Supports:
    - Platform-wide Google credentials (default)
    - Tenant-specific credentials (BYOT)
    - Domain restrictions per tenant
    - Auto-provisioning of new users
    """

    # Google OAuth endpoints
    AUTHORIZATION_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

    # OAuth scopes for user authentication
    SCOPES = [
        "openid",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    # State token expiry (10 minutes)
    STATE_EXPIRY_MINUTES = 10

    # HIGH-004 FIX: Removed in-memory _state_store dictionary.
    # Now using database-backed OAuthStateManager for persistence across restarts
    # and multi-instance deployments.

    def __init__(self, db: Session, encryption_key: Optional[str] = None):
        """
        Initialize Google SSO service.

        Args:
            db: Database session
            encryption_key: Key for decrypting tenant secrets (optional)
        """
        self.db = db
        self.encryption_key = encryption_key
        # HIGH-004: Use database-backed state manager for persistence
        self.state_manager = OAuthStateManager(db)

    def get_tenant_sso_config(self, tenant_id: str) -> Optional[TenantSSOConfig]:
        """Get SSO config for a tenant."""
        return self.db.query(TenantSSOConfig).filter(
            TenantSSOConfig.tenant_id == tenant_id
        ).first()

    def is_sso_enabled_for_tenant(self, tenant_id: str) -> bool:
        """
        Check if Google SSO is enabled for a tenant.

        SSO is enabled if:
        1. Tenant has SSO explicitly enabled in TenantSSOConfig, OR
        2. Tenant has Google OAuth credentials configured, OR
        3. Platform-wide Google SSO is configured
        """
        # Check if SSO is explicitly enabled
        sso_config = self.get_tenant_sso_config(tenant_id)
        if sso_config and sso_config.google_sso_enabled:
            return True

        # Check if tenant has Google credentials configured (centralized)
        google_creds = self.get_google_credentials(tenant_id)
        if google_creds and google_creds.client_id:
            return True

        # Fall back to platform-wide config
        return bool(settings.GOOGLE_SSO_CLIENT_ID)

    def get_google_credentials(self, tenant_id: str) -> Optional[GoogleOAuthCredentials]:
        """Get centralized Google OAuth credentials for a tenant (from Hub config)."""
        return self.db.query(GoogleOAuthCredentials).filter(
            GoogleOAuthCredentials.tenant_id == tenant_id
        ).first()

    def get_oauth_credentials(self, tenant_id: Optional[str] = None) -> Tuple[str, str, str]:
        """
        Get OAuth credentials for authentication.

        Uses centralized GoogleOAuthCredentials (same as Hub integrations),
        falling back to platform-wide credentials.

        Args:
            tenant_id: Optional tenant ID

        Returns:
            Tuple of (client_id, client_secret, redirect_uri)

        Raises:
            GoogleSSOError: If no credentials are configured
        """
        # Try tenant-specific credentials first (from centralized GoogleOAuthCredentials)
        if tenant_id:
            google_creds = self.get_google_credentials(tenant_id)
            if google_creds and google_creds.client_id and google_creds.client_secret_encrypted:
                # Decrypt client secret
                client_secret = google_creds.client_secret_encrypted
                if self.encryption_key:
                    try:
                        # Encode key as bytes if it's a string
                        key = self.encryption_key.encode() if isinstance(self.encryption_key, str) else self.encryption_key
                        encryptor = TokenEncryption(key)
                        # decrypt() requires workspace_identifier (tenant_id)
                        client_secret = encryptor.decrypt(google_creds.client_secret_encrypted, tenant_id)
                    except Exception as e:
                        logger.warning(f"Failed to decrypt tenant secret: {e}")

                return (
                    google_creds.client_id,
                    client_secret,
                    settings.GOOGLE_SSO_REDIRECT_URI
                )

        # Fall back to platform-wide credentials
        if settings.GOOGLE_SSO_CLIENT_ID and settings.GOOGLE_SSO_CLIENT_SECRET:
            return (
                settings.GOOGLE_SSO_CLIENT_ID,
                settings.GOOGLE_SSO_CLIENT_SECRET,
                settings.GOOGLE_SSO_REDIRECT_URI
            )

        raise GoogleSSOError(
            "Google OAuth is not configured. Please configure Google credentials "
            "in Settings → Integrations, or contact your administrator."
        )

    def generate_authorization_url(
        self,
        tenant_slug: Optional[str] = None,
        redirect_after: str = "/",
        invitation_token: Optional[str] = None,
    ) -> str:
        """
        Generate Google OAuth authorization URL.

        Args:
            tenant_slug: Optional tenant slug for tenant-specific auth
            redirect_after: URL to redirect to after authentication
            invitation_token: Optional invitation token if accepting an invite

        Returns:
            Authorization URL to redirect user to
        """
        # Get tenant ID from slug if provided
        tenant_id = None
        if tenant_slug:
            tenant = self.db.query(Tenant).filter(
                Tenant.slug == tenant_slug,
                Tenant.deleted_at.is_(None)
            ).first()
            if tenant:
                tenant_id = tenant.id

        # If no tenant specified, find a tenant with SSO enabled and credentials configured
        if not tenant_id:
            # Find any tenant with SSO enabled and Google OAuth credentials
            sso_config = self.db.query(TenantSSOConfig).filter(
                TenantSSOConfig.google_sso_enabled == True
            ).first()

            if sso_config:
                # Check if this tenant has Google OAuth credentials
                creds = self.db.query(GoogleOAuthCredentials).filter(
                    GoogleOAuthCredentials.tenant_id == sso_config.tenant_id
                ).first()
                if creds and creds.client_id:
                    tenant_id = sso_config.tenant_id
                    # Also get tenant slug for state
                    tenant = self.db.query(Tenant).filter(
                        Tenant.id == tenant_id
                    ).first()
                    if tenant:
                        tenant_slug = tenant.slug

        # Get OAuth credentials
        client_id, _, redirect_uri = self.get_oauth_credentials(tenant_id)

        # HIGH-004 FIX: Generate state token using database-backed state manager
        # This ensures state persists across server restarts and works in multi-instance deployments
        metadata = {
            "tenant_slug": tenant_slug,
            "invitation_token": invitation_token,
        }
        state = self.state_manager.generate_state(
            integration_type="google_sso",
            expires_in_minutes=self.STATE_EXPIRY_MINUTES,
            redirect_url=redirect_after,
            tenant_id=tenant_id,
            metadata=metadata,
        )

        # Build authorization URL
        params = {
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.SCOPES),
            "state": state,
            "access_type": "offline",
            "prompt": "select_account",  # Always show account picker
        }

        # Add login_hint if we know the tenant domain
        if tenant_id:
            config = self.get_tenant_sso_config(tenant_id)
            if config and config.allowed_domains:
                try:
                    domains = json.loads(config.allowed_domains)
                    if domains and len(domains) == 1:
                        params["hd"] = domains[0]  # Hosted domain hint
                except json.JSONDecodeError:
                    pass

        auth_url = f"{self.AUTHORIZATION_URL}?{urlencode(params)}"
        logger.info(f"Generated Google SSO auth URL for tenant: {tenant_slug or 'platform'}")

        return auth_url

    def validate_state(self, state: str) -> Dict[str, Any]:
        """
        Validate and consume state token using database-backed storage.

        HIGH-004 FIX: Now uses OAuthStateManager for persistent state storage.
        State survives server restarts and works in multi-instance deployments.

        Args:
            state: State token from callback

        Returns:
            State data (tenant_id, tenant_slug, redirect_after, invitation_token)

        Raises:
            GoogleSSOError: If state is invalid or expired
        """
        try:
            redirect_url, tenant_id, metadata = self.state_manager.validate_state_extended(
                state_token=state,
                integration_type="google_sso"
            )

            # Reconstruct state data from database record for backward compatibility
            return {
                "tenant_id": tenant_id,
                "tenant_slug": metadata.get("tenant_slug"),
                "redirect_after": redirect_url,
                "invitation_token": metadata.get("invitation_token"),
            }
        except ValueError as e:
            raise GoogleSSOError(str(e))

    async def exchange_code_for_tokens(self, code: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Exchange authorization code for tokens.

        Args:
            code: Authorization code from Google
            tenant_id: Optional tenant ID for credentials

        Returns:
            Token response from Google
        """
        client_id, client_secret, redirect_uri = self.get_oauth_credentials(tenant_id)

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
            )

            if response.status_code != 200:
                logger.error(f"Token exchange failed: {response.text}")
                raise GoogleSSOError("Failed to exchange authorization code")

            return response.json()

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Get user information from Google.

        Args:
            access_token: Google access token

        Returns:
            User info dict with id, email, name, picture
        """
        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.USERINFO_URL,
                headers={"Authorization": f"Bearer {access_token}"},
            )

            if response.status_code != 200:
                logger.error(f"Failed to get user info: {response.text}")
                raise GoogleSSOError("Failed to get user information from Google")

            return response.json()

    def validate_email_domain(self, email: str, tenant_id: str) -> bool:
        """
        Validate that email domain is allowed for tenant.

        Args:
            email: User's email address
            tenant_id: Tenant ID

        Returns:
            True if domain is allowed, False otherwise
        """
        config = self.get_tenant_sso_config(tenant_id)
        if not config or not config.allowed_domains:
            return True  # No domain restriction

        try:
            allowed_domains = json.loads(config.allowed_domains)
            if not allowed_domains:
                return True

            email_domain = email.split("@")[1].lower()
            return email_domain in [d.lower() for d in allowed_domains]
        except (json.JSONDecodeError, IndexError):
            return True

    def find_or_create_user(
        self,
        google_id: str,
        email: str,
        full_name: Optional[str],
        avatar_url: Optional[str],
        tenant_id: Optional[str] = None,
        invitation_token: Optional[str] = None,
    ) -> Tuple[User, bool]:
        """
        Find existing user or create new one.

        Args:
            google_id: Google user ID
            email: User's email
            full_name: User's full name
            avatar_url: Profile picture URL
            tenant_id: Target tenant ID (if known)
            invitation_token: Optional invitation token

        Returns:
            Tuple of (User, was_created)

        Raises:
            GoogleSSOError: If user cannot be created/found
        """
        # Try to find by Google ID first
        user = self.db.query(User).filter(User.google_id == google_id).first()
        if user:
            # Update profile info
            user.avatar_url = avatar_url
            if full_name and not user.full_name:
                user.full_name = full_name
            user.last_login_at = datetime.utcnow()
            self.db.commit()
            return user, False

        # Try to find by email
        user = self.db.query(User).filter(User.email == email).first()
        if user:
            # Link Google account to existing user
            user.google_id = google_id
            user.auth_provider = "google"
            user.avatar_url = avatar_url
            user.email_verified = True
            user.last_login_at = datetime.utcnow()
            self.db.commit()
            logger.info(f"Linked Google account to existing user: {email}")
            return user, False

        # Handle invitation
        if invitation_token:
            from models_rbac import UserInvitation
            invitation = self.db.query(UserInvitation).filter(
                UserInvitation.invitation_token == invitation_token,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.expires_at > datetime.utcnow(),
            ).first()

            if invitation and invitation.email.lower() == email.lower():
                # Create user from invitation
                user = User(
                    tenant_id=invitation.tenant_id,
                    email=email,
                    password_hash=None,  # No password for SSO users
                    full_name=full_name,
                    is_global_admin=False,
                    is_active=True,
                    email_verified=True,
                    auth_provider="google",
                    google_id=google_id,
                    avatar_url=avatar_url,
                )
                self.db.add(user)
                self.db.flush()

                # Assign role from invitation
                user_role = UserRole(
                    user_id=user.id,
                    role_id=invitation.role_id,
                    tenant_id=invitation.tenant_id,
                    assigned_by=invitation.invited_by,
                )
                self.db.add(user_role)

                # Mark invitation as accepted
                invitation.accepted_at = datetime.utcnow()

                self.db.commit()
                logger.info(f"Created user from invitation via Google SSO: {email}")
                return user, True

        # Check for auto-provisioning
        if tenant_id:
            config = self.get_tenant_sso_config(tenant_id)
            if config and config.auto_provision_users:
                # Validate domain
                if not self.validate_email_domain(email, tenant_id):
                    raise GoogleSSOError(f"Email domain not allowed for this organization")

                # Check tenant limits
                tenant = self.db.query(Tenant).filter(Tenant.id == tenant_id).first()
                if tenant:
                    current_users = self.db.query(User).filter(
                        User.tenant_id == tenant_id,
                        User.deleted_at.is_(None)
                    ).count()

                    if tenant.max_users > 0 and current_users >= tenant.max_users:
                        raise GoogleSSOError("Organization has reached maximum user limit")

                # Create auto-provisioned user
                user = User(
                    tenant_id=tenant_id,
                    email=email,
                    password_hash=None,
                    full_name=full_name,
                    is_global_admin=False,
                    is_active=True,
                    email_verified=True,
                    auth_provider="google",
                    google_id=google_id,
                    avatar_url=avatar_url,
                )
                self.db.add(user)
                self.db.flush()

                # Assign default role
                role_id = config.default_role_id
                if not role_id:
                    # Fall back to "member" role
                    role = self.db.query(Role).filter(Role.name == "member").first()
                    role_id = role.id if role else None

                if role_id:
                    user_role = UserRole(
                        user_id=user.id,
                        role_id=role_id,
                        tenant_id=tenant_id,
                    )
                    self.db.add(user_role)

                self.db.commit()
                logger.info(f"Auto-provisioned user via Google SSO: {email}")
                return user, True

        raise GoogleSSOError(
            "No account found for this email. Please ask your administrator "
            "to send you an invitation, or contact support."
        )

    async def authenticate(
        self,
        code: str,
        state: str,
    ) -> Tuple[User, str, str]:
        """
        Complete Google SSO authentication.

        Args:
            code: Authorization code from Google
            state: State token from callback

        Returns:
            Tuple of (User, JWT token, redirect_url)
        """
        # Validate state
        state_data = self.validate_state(state)
        tenant_id = state_data.get("tenant_id")
        redirect_after = state_data.get("redirect_after", "/")
        invitation_token = state_data.get("invitation_token")

        # Exchange code for tokens
        tokens = await self.exchange_code_for_tokens(code, tenant_id)
        access_token = tokens.get("access_token")

        if not access_token:
            raise GoogleSSOError("No access token received from Google")

        # Get user info
        user_info = await self.get_user_info(access_token)

        google_id = user_info.get("id")
        email = user_info.get("email")
        full_name = user_info.get("name")
        avatar_url = user_info.get("picture")

        if not google_id or not email:
            raise GoogleSSOError("Could not get user information from Google")

        # Validate domain if tenant is specified
        if tenant_id and not self.validate_email_domain(email, tenant_id):
            raise GoogleSSOError(f"Email domain not allowed for this organization")

        # Find or create user
        user, was_created = self.find_or_create_user(
            google_id=google_id,
            email=email,
            full_name=full_name,
            avatar_url=avatar_url,
            tenant_id=tenant_id,
            invitation_token=invitation_token,
        )

        # Check if user is active
        if not user.is_active:
            raise GoogleSSOError("Your account has been deactivated")

        # Get user's role
        user_role = self.db.query(UserRole).filter(UserRole.user_id == user.id).first()
        role_name = None
        if user_role:
            role = self.db.query(Role).filter(Role.id == user_role.role_id).first()
            role_name = role.name if role else None

        # Generate JWT token
        token_data = {
            "sub": str(user.id),
            "email": user.email,
            "tenant_id": user.tenant_id,
            "is_global_admin": user.is_global_admin,
            "role": role_name,
            "auth_provider": "google",
        }
        jwt_token = create_access_token(token_data)

        logger.info(f"Google SSO authentication successful for: {email}")

        return user, jwt_token, redirect_after


def get_google_sso_service(db: Session, encryption_key: Optional[str] = None) -> GoogleSSOService:
    """
    Factory function to get Google SSO service.

    Args:
        db: Database session
        encryption_key: Optional encryption key for tenant secrets

    Returns:
        GoogleSSOService instance
    """
    return GoogleSSOService(db, encryption_key)
