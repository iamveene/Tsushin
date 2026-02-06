"""
Asana OAuth 2.0 Handler

Handles OAuth authorization flow with CSRF protection and per-workspace encryption.
"""

import os
import logging
from typing import Dict, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode
import httpx
from sqlalchemy.orm import Session

from models import AsanaIntegration, HubIntegration, OAuthToken
from hub.security import TokenEncryption, OAuthStateManager, mask_token

logger = logging.getLogger(__name__)


class AsanaOAuthHandler:
    """
    Handles OAuth 2.0 flow for Asana MCP Server with Dynamic Client Registration.

    Asana MCP Server uses Dynamic Client Registration (DCR) instead of traditional
    OAuth app registration. This means:
    1. First use: Register client dynamically at /register endpoint
    2. Get client_id and client_secret in response
    3. Store credentials in database for future use
    4. Use stored credentials for all subsequent OAuth flows

    Security features:
    - Dynamic client registration (no manual app creation)
    - OAuth state validation (CSRF protection)
    - Per-workspace key derivation (PBKDF2HMAC)
    - Token masking in logs
    - Automatic token refresh with rotation
    """

    # MCP Server endpoints (from /.well-known/oauth-authorization-server)
    REGISTER_URL = "https://mcp.asana.com/register"
    AUTHORIZATION_URL = "https://mcp.asana.com/authorize"  # Correct MCP OAuth endpoint
    TOKEN_URL = "https://mcp.asana.com/token"  # MCP token endpoint
    REVOKE_URL = "https://mcp.asana.com/token"  # MCP revoke endpoint (same as token endpoint)
    WORKSPACES_URL = "https://app.asana.com/api/1.0/workspaces"  # Standard API for workspace list
    USER_URL = "https://app.asana.com/api/1.0/users/me"  # Standard API for user info

    def __init__(self, db: Session, encryption_key: str, redirect_uri: str, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        """
        Initialize OAuth handler.

        Args:
            db: Database session
            encryption_key: Master encryption key (Fernet key)
            redirect_uri: OAuth callback URL
            client_id: Optional - from dynamic registration or Config table
            client_secret: Optional - from dynamic registration or Config table
        """
        self.db = db
        self.encryption_key = encryption_key
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

        # Initialize security components
        self.token_encryption = TokenEncryption(encryption_key.encode())
        self.state_manager = OAuthStateManager(db)

    async def ensure_registered(self) -> tuple[str, str]:
        """
        Ensure client is registered with Asana MCP Server.

        Uses Dynamic Client Registration (DCR) to automatically register
        this Tsushin installation on first use.

        Returns:
            Tuple of (client_id, client_secret)

        Raises:
            Exception: If registration fails
        """
        # Check if already registered (credentials in database)
        if self.client_id and self.client_secret:
            logger.info("Using existing MCP client credentials from parameters")
            return self.client_id, self.client_secret

        # Check Config table for stored credentials
        from models import Config
        config = self.db.query(Config).first()

        if config and config.asana_mcp_registered and config.asana_mcp_client_id:
            logger.info("Using stored MCP client credentials from database")
            self.client_id = config.asana_mcp_client_id
            self.client_secret = config.asana_mcp_client_secret
            return self.client_id, self.client_secret

        # Need to register dynamically
        logger.info(f"Registering new MCP client with redirect URI: {self.redirect_uri}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.REGISTER_URL,
                headers={"Content-Type": "application/json"},
                json={"redirect_uris": [self.redirect_uri]}
            )
            response.raise_for_status()
            registration_data = response.json()

        self.client_id = registration_data["client_id"]
        self.client_secret = registration_data["client_secret"]

        logger.info(f"MCP client registered successfully: {mask_token(self.client_id)}")

        # Store in database for future use
        if not config:
            from models import Config
            config = Config(
                messages_db_path="",  # Will be set later
                asana_mcp_client_id=self.client_id,
                asana_mcp_client_secret=self.client_secret,
                asana_mcp_registered=True
            )
            self.db.add(config)
        else:
            config.asana_mcp_client_id = self.client_id
            config.asana_mcp_client_secret = self.client_secret
            config.asana_mcp_registered = True

        self.db.commit()
        logger.info("MCP client credentials stored in database")

        return self.client_id, self.client_secret

    async def generate_authorization_url(self, redirect_url: Optional[str] = None, workspace_name: Optional[str] = None) -> tuple[str, str]:
        """
        Generate OAuth authorization URL with CSRF state token.

        Automatically registers MCP client on first use (Dynamic Client Registration).

        Args:
            redirect_url: Optional URL to redirect after OAuth callback
            workspace_name: User-provided workspace name (for UI display)

        Returns:
            Tuple of (authorization_url, state_token)
        """
        # Ensure client is registered (auto-registers on first use)
        client_id, client_secret = await self.ensure_registered()

        # Store workspace_name in state redirect_url as query parameter
        # This allows us to retrieve it in the callback
        if workspace_name and redirect_url:
            from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
            parsed = urlparse(redirect_url)
            query_params = parse_qs(parsed.query)
            query_params['workspace_name'] = [workspace_name]
            new_query = urlencode(query_params, doseq=True)
            redirect_url = urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))
        elif workspace_name:
            redirect_url = f"{redirect_url or '/hub'}?workspace_name={workspace_name}"

        state_token = self.state_manager.generate_state(
            integration_type='asana',
            expires_in_minutes=10,
            redirect_url=redirect_url
        )

        params = {
            "client_id": client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": state_token,
            "scope": "default",  # Asana MCP uses "default" scope
        }

        auth_url = f"{self.AUTHORIZATION_URL}?{urlencode(params)}"
        logger.info(f"Generated MCP OAuth authorization URL with state: {mask_token(state_token)}")

        return auth_url, state_token

    async def handle_callback(self, code: str, state: str) -> Dict:
        """
        Handle OAuth callback with state validation and token exchange.

        Args:
            code: Authorization code from Asana
            state: State token for CSRF validation

        Returns:
            Dict with integration details

        Raises:
            ValueError: If state validation fails or token exchange fails
        """
        # Validate state token (CSRF protection)
        redirect_url = self.state_manager.validate_state(state, 'asana')
        logger.info("OAuth state validated successfully")

        # Extract workspace_name from redirect_url if present
        user_provided_workspace_name = None
        if redirect_url:
            from urllib.parse import urlparse, parse_qs
            parsed = urlparse(redirect_url)
            query_params = parse_qs(parsed.query)
            if 'workspace_name' in query_params:
                user_provided_workspace_name = query_params['workspace_name'][0]
                logger.info(f"User provided workspace name: {user_provided_workspace_name}")

        # Exchange code for tokens
        token_response = await self.exchange_code_for_token(code)
        access_token = token_response["access_token"]

        # Query Asana MCP for actual workspaces using the new access token
        from hub.asana.asana_mcp_client import AsanaMCPClient

        logger.info("Fetching workspaces from Asana MCP to get real workspace GID...")

        workspace_gid = None
        workspace_name = user_provided_workspace_name or "Default Workspace"
        user_gid = "unknown"
        all_workspaces = []

        try:
            async with AsanaMCPClient(access_token) as mcp_client:
                # Get user info (includes user GID and workspaces)
                try:
                    result = await mcp_client.call_tool('asana_get_user', {'user': 'me'})

                    # Parse CallToolResult - MCP returns wrapped response
                    import json
                    if hasattr(result, 'content') and result.content:
                        text_content = result.content[0].text
                        data = json.loads(text_content)
                        user_data = data.get('data', {})

                        user_gid = user_data.get('gid', 'unknown')
                        all_workspaces = user_data.get('workspaces', [])

                        logger.info(f"Retrieved user GID: {user_gid}")
                        logger.info(f"Found {len(all_workspaces)} workspaces")

                        # Match user-provided workspace name
                        if user_provided_workspace_name and all_workspaces:
                            for ws in all_workspaces:
                                if ws.get('name', '').lower() == user_provided_workspace_name.lower():
                                    workspace_gid = ws.get('gid')
                                    workspace_name = ws.get('name')
                                    logger.info(f"Matched workspace: {workspace_name} (GID: {workspace_gid})")
                                    break

                        # Fallback to first workspace
                        if not workspace_gid and all_workspaces:
                            workspace_gid = all_workspaces[0].get('gid')
                            workspace_name = all_workspaces[0].get('name')
                            logger.info(f"Using first workspace: {workspace_name} (GID: {workspace_gid})")
                    else:
                        logger.warning(f"Unexpected MCP result format: {type(result)}")

                except Exception as e:
                    logger.error(f"Error fetching user/workspaces: {e}", exc_info=True)
        except Exception as e:
            logger.error(f"Error connecting to Asana MCP: {e}", exc_info=True)

        # Fallback to placeholder if we couldn't get real workspace GID
        if not workspace_gid:
            workspace_gid = f"mcp_{user_gid}_{int(datetime.utcnow().timestamp())}"
            logger.warning(f"Could not retrieve real workspace GID, using placeholder: {workspace_gid}")

        logger.info(f"User {user_gid} authorized via MCP (workspace: {workspace_name}, GID: {workspace_gid})")

        # Check if integration already exists for this user
        # Note: workspace_gid might be placeholder at this point
        existing_integration = self.db.query(AsanaIntegration).filter(
            AsanaIntegration.authorized_by_user_gid == user_gid
        ).first()

        if existing_integration:
            # Update existing integration
            integration = existing_integration
            integration.workspace_name = workspace_name
            integration.workspace_gid = workspace_gid
            integration.authorized_at = datetime.utcnow()
            integration.is_active = True

            # Update base integration name
            base = self.db.query(HubIntegration).filter(HubIntegration.id == existing_integration.id).first()
            if base:
                base.name = f"Asana - {workspace_name}"
                base.health_status = "unknown"
                base.is_active = True

            logger.info(f"Updated existing integration for user {user_gid}")
        else:
            # Create new integration using polymorphic pattern
            # AsanaIntegration automatically creates base HubIntegration row
            integration_name = f"Asana - {workspace_name}"
            logger.info(f"DEBUG: Creating AsanaIntegration with name='{integration_name}' (workspace_name='{workspace_name}')")

            integration = AsanaIntegration(
                # Base HubIntegration fields
                type='asana',
                name=integration_name,
                is_active=True,
                health_status="unknown",
                # AsanaIntegration specific fields
                workspace_gid=workspace_gid,
                workspace_name=workspace_name,
                authorized_by_user_gid=user_gid,
                authorized_at=datetime.utcnow()
            )
            self.db.add(integration)
            logger.info(f"DEBUG: AsanaIntegration added to session")

        self.db.flush()  # Get integration ID
        logger.info(f"DEBUG: Integration flushed, id={integration.id}")

        # Store encrypted tokens
        await self.save_token(integration.id, workspace_gid, token_response)

        self.db.commit()

        logger.info(f"OAuth flow completed successfully for integration {integration.id}")

        return {
            "integration_id": integration.id,
            "workspace_gid": workspace_gid,
            "workspace_name": workspace_name,
            "user_gid": user_gid,
            "redirect_url": redirect_url,
            "all_workspaces": all_workspaces  # Retrieved from Asana MCP
        }

    async def exchange_code_for_token(self, code: str) -> Dict:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth callback

        Returns:
            Token response dict with access_token, refresh_token, expires_in
        """
        logger.info("Exchanging authorization code for token")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uri": self.redirect_uri,
                    "code": code,
                }
            )
            response.raise_for_status()
            token_data = response.json()

            logger.info(f"Token exchange successful: {mask_token(token_data.get('access_token', ''))}")
            return token_data

    async def refresh_access_token(self, refresh_token: str) -> Dict:
        """
        Refresh access token using refresh token.

        Args:
            refresh_token: Current refresh token

        Returns:
            New token response dict
        """
        logger.info(f"Refreshing access token: {mask_token(refresh_token)}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "refresh_token": refresh_token,
                }
            )
            response.raise_for_status()
            token_data = response.json()

            logger.info(f"Token refresh successful: {mask_token(token_data.get('access_token', ''))}")
            return token_data

    async def revoke_token(self, access_token: str) -> None:
        """Revoke access token."""
        logger.info(f"Revoking access token: {mask_token(access_token)}")

        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post(
                self.REVOKE_URL,
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "token": access_token,
                }
            )

        logger.info("Token revoked successfully")

    async def save_token(self, integration_id: int, workspace_gid: str, token_response: Dict) -> OAuthToken:
        """
        Save OAuth token to database with per-workspace encryption.

        Args:
            integration_id: Associated HubIntegration ID
            workspace_gid: Workspace GID for key derivation
            token_response: Token response from Asana API

        Returns:
            Created OAuthToken instance
        """
        access_token = token_response["access_token"]
        refresh_token = token_response["refresh_token"]
        expires_in = token_response.get("expires_in", 3600)  # Default 1 hour

        # Calculate expiration time
        expires_at = datetime.utcnow() + timedelta(seconds=expires_in)

        # Encrypt tokens with per-workspace key
        access_encrypted = self.token_encryption.encrypt(access_token, workspace_gid)
        refresh_encrypted = self.token_encryption.encrypt(refresh_token, workspace_gid)

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

    async def get_valid_token(self, integration_id: int, workspace_gid: str) -> Optional[str]:
        """
        Get valid access token for integration, refreshing if needed.

        Args:
            integration_id: HubIntegration ID
            workspace_gid: Workspace GID for key derivation

        Returns:
            Valid access token or None if refresh fails
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

            try:
                refresh_token = self.token_encryption.decrypt(token.refresh_token_encrypted, workspace_gid)
                new_token_response = await self.refresh_access_token(refresh_token)

                # Save new token
                new_token = await self.save_token(integration_id, workspace_gid, new_token_response)
                self.db.commit()

                return self.token_encryption.decrypt(new_token.access_token_encrypted, workspace_gid)
            except Exception as e:
                logger.error(f"Token refresh failed: {e}", exc_info=True)
                return None

        # Token still valid
        return self.token_encryption.decrypt(token.access_token_encrypted, workspace_gid)

    async def disconnect_integration(self, integration_id: int, workspace_gid: str) -> None:
        """
        Disconnect integration and revoke tokens.

        Args:
            integration_id: HubIntegration ID
            workspace_gid: Workspace GID
        """
        # Get token
        token = self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == integration_id
        ).first()

        if token:
            try:
                access_token = self.token_encryption.decrypt(token.access_token_encrypted, workspace_gid)
                await self.revoke_token(access_token)
            except Exception as e:
                logger.warning(f"Token revocation failed: {e}")

        # Delete tokens
        self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == integration_id
        ).delete()

        # Deactivate integration
        integration = self.db.query(HubIntegration).filter(
            HubIntegration.id == integration_id
        ).first()

        if integration:
            integration.is_active = False

        self.db.commit()
        logger.info(f"Integration {integration_id} disconnected successfully")
