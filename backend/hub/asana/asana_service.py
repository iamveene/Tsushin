"""
Asana Service - High-Level Integration API

Provides a simplified interface for Asana integration with the Hub system.
"""

import logging
import asyncio
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from cachetools import TTLCache

from models import AsanaIntegration, HubIntegration, Agent
from hub.base import HubIntegrationBase, IntegrationHealthStatus
from hub.asana.oauth_handler import AsanaOAuthHandler
from hub.asana.asana_mcp_client import AsanaMCPClient, MCPTool

logger = logging.getLogger(__name__)


class AsanaService(HubIntegrationBase):
    """
    High-level service for Asana integration.

    Provides:
    - OAuth flow management
    - Tool execution with caching
    - Health monitoring
    - Token management
    """

    def __init__(
        self,
        db: Session,
        integration_id: int,
        encryption_key: str,
        redirect_uri: str,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None
    ):
        """
        Initialize Asana service.

        Args:
            db: Database session
            integration_id: HubIntegration ID
            encryption_key: Master encryption key
            redirect_uri: OAuth callback URL
            client_id: Optional - from database or dynamic registration
            client_secret: Optional - from database or dynamic registration
        """
        super().__init__(db, integration_id)

        self.oauth_handler = AsanaOAuthHandler(
            db=db,
            encryption_key=encryption_key,
            redirect_uri=redirect_uri,
            client_id=client_id,
            client_secret=client_secret
        )

        # Result cache (5-minute TTL)
        self._result_cache = TTLCache(maxsize=100, ttl=300)

        # MCP client singleton (reused across all tool calls)
        self._mcp_client: Optional[AsanaMCPClient] = None
        self._mcp_lock = asyncio.Lock()
        self._current_access_token: Optional[str] = None

        # Get integration details
        self.integration = db.query(AsanaIntegration).filter(
            AsanaIntegration.id == integration_id
        ).first()

        if not self.integration:
            raise ValueError(f"Integration {integration_id} not found")

    async def _get_mcp_client(self) -> AsanaMCPClient:
        """
        Get or create MCP client singleton.

        Maintains a single MCP connection per integration to avoid
        TaskGroup errors from creating/destroying connections per tool call.

        Returns:
            AsanaMCPClient instance
        """
        async with self._mcp_lock:
            # Get valid access token
            access_token = await self.oauth_handler.get_valid_token(
                self.integration_id,
                self.integration.workspace_gid
            )

            if not access_token:
                raise ValueError("No valid access token available")

            # If token changed or no client exists, recreate connection
            if self._mcp_client is None or self._current_access_token != access_token:
                # Close old client if exists
                if self._mcp_client is not None:
                    try:
                        await self._mcp_client.__aexit__(None, None, None)
                    except Exception as e:
                        logger.warning(f"Error closing old MCP client: {e}")

                # Create new client and establish connection
                self._mcp_client = AsanaMCPClient(access_token)
                await self._mcp_client.__aenter__()
                self._current_access_token = access_token
                logger.info(f"Created new MCP client for integration {self.integration_id}")

            return self._mcp_client

    async def close(self):
        """
        Close MCP client connection and cleanup resources.

        Should be called when integration is disconnected or service is shutting down.
        """
        async with self._mcp_lock:
            if self._mcp_client is not None:
                try:
                    await self._mcp_client.__aexit__(None, None, None)
                    logger.info(f"Closed MCP client for integration {self.integration_id}")
                except Exception as e:
                    logger.error(f"Error closing MCP client: {e}", exc_info=True)
                finally:
                    self._mcp_client = None
                    self._current_access_token = None

    async def check_health(self) -> Dict[str, Any]:
        """
        Check health of Asana integration.

        Returns:
            Health status dict
        """
        try:
            # Get or create MCP client (reuses existing connection)
            client = await self._get_mcp_client()

            # Try to list tools (lightweight health check)
            tools = await client.list_tools()

            # Update health status
            self.integration.last_health_check = datetime.utcnow()
            self.integration.health_status = IntegrationHealthStatus.HEALTHY
            self.db.commit()

            return {
                "status": IntegrationHealthStatus.HEALTHY,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "details": {
                    "token_valid": True,
                    "workspace": self.integration.workspace_name,
                    "tools_available": len(tools)
                },
                "errors": []
            }

        except ValueError as e:
            # Token error
            self.integration.last_health_check = datetime.utcnow()
            self.integration.health_status = IntegrationHealthStatus.UNAVAILABLE
            self.db.commit()

            return {
                "status": IntegrationHealthStatus.UNAVAILABLE,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "details": {
                    "token_valid": False,
                    "error": str(e)
                },
                "errors": [str(e)]
            }

        except Exception as e:
            logger.error(f"Health check failed: {e}", exc_info=True)

            self.integration.last_health_check = datetime.utcnow()
            self.integration.health_status = IntegrationHealthStatus.DEGRADED
            self.db.commit()

            return {
                "status": IntegrationHealthStatus.DEGRADED,
                "last_check": datetime.utcnow().isoformat() + "Z",
                "details": {
                    "error": str(e)
                },
                "errors": [str(e)]
            }

    async def refresh_tokens(self) -> bool:
        """
        Refresh OAuth tokens if needed.

        Returns:
            True if tokens refreshed successfully or still valid
        """
        try:
            access_token = await self.oauth_handler.get_valid_token(
                self.integration_id,
                self.integration.workspace_gid
            )
            return access_token is not None
        except Exception as e:
            logger.error(f"Token refresh failed: {e}", exc_info=True)
            return False

    async def revoke_access(self) -> None:
        """Revoke OAuth access and delete tokens."""
        # Close MCP connection first
        await self.close()

        # Then revoke OAuth tokens
        await self.oauth_handler.disconnect_integration(
            self.integration_id,
            self.integration.workspace_gid
        )

    def get_metrics(self) -> Dict[str, Any]:
        """
        Get integration metrics.

        Returns:
            Metrics dict
        """
        # Get token expiration
        from models import OAuthToken
        token = self.db.query(OAuthToken).filter(
            OAuthToken.integration_id == self.integration_id
        ).order_by(OAuthToken.created_at.desc()).first()

        token_expires_in = 0
        if token:
            delta = token.expires_at - datetime.utcnow()
            token_expires_in = max(0, int(delta.total_seconds()))

        return {
            "integration_id": self.integration_id,
            "workspace_name": self.integration.workspace_name,
            "is_active": self.integration.is_active,
            "health_status": self.integration.health_status,
            "token_expires_in_seconds": token_expires_in,
            "cache_size": len(self._result_cache),
            "last_health_check": self.integration.last_health_check.isoformat() + "Z" if self.integration.last_health_check else None
        }

    def get_workspace_gid(self) -> str:
        """
        Get the workspace GID for this integration.

        Returns:
            Workspace GID
        """
        return self.integration.workspace_gid

    async def execute_tool(self, tool_name: str, arguments: Dict) -> Any:
        """
        Execute Asana tool with result caching.

        Args:
            tool_name: Tool name
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        # Generate cache key
        cache_key = f"{tool_name}:{json.dumps(arguments, sort_keys=True)}"

        # Check cache
        if cache_key in self._result_cache:
            logger.info(f"Cache hit for {tool_name}")
            return self._result_cache[cache_key]

        # Get or create MCP client (reuses existing connection)
        client = await self._get_mcp_client()

        # Execute tool
        result = await client.call_tool(tool_name, arguments)

        # Cache result
        self._result_cache[cache_key] = result

        return result

    async def list_tools(self) -> List[MCPTool]:
        """
        List available Asana tools.

        Returns:
            List of MCPTool objects
        """
        # Get or create MCP client (reuses existing connection)
        client = await self._get_mcp_client()
        return await client.list_tools()

    async def get_workspace_info(self) -> Dict:
        """
        Get workspace information.

        Returns:
            Workspace details
        """
        return {
            "workspace_gid": self.integration.workspace_gid,
            "workspace_name": self.integration.workspace_name,
            "authorized_by": self.integration.authorized_by_user_gid,
            "authorized_at": self.integration.authorized_at.isoformat() + "Z"
        }

    async def resolve_user_by_name(self, name: str) -> Optional[Dict[str, str]]:
        """
        Resolve an Asana user name to GID using MCP tools.

        Uses asana_typeahead_search for fast, relevant user matching.
        Falls back to asana_get_workspace_users if typeahead fails.

        Note: MCP OAuth tokens only work with MCP protocol, not REST API.

        Args:
            name: User name to search for (e.g., "John Smith", "John")

        Returns:
            Dict with 'gid' and 'name' if found, None otherwise

        Raises:
            ValueError: If access token is not available
            Exception: On API errors
        """
        # Get valid access token (auto-refreshes if needed)
        access_token = await self.oauth_handler.get_valid_token(
            self.integration_id,
            self.integration.workspace_gid
        )

        if not access_token:
            raise ValueError("No valid access token available")

        workspace_gid = self.integration.workspace_gid

        try:
            # Strategy 1: Use typeahead search (recommended by Asana MCP)
            logger.info(f"Searching for user '{name}' using typeahead search")

            from hub.asana.asana_mcp_client import AsanaMCPClient
            async with AsanaMCPClient(access_token) as mcp_client:
                # Try typeahead search first (faster, more relevant)
                try:
                    result = await mcp_client.call_tool('asana_typeahead_search', {
                        'workspace_gid': workspace_gid,
                        'resource_type': 'user',
                        'query': name
                    })

                    # Parse MCP response
                    import json
                    if hasattr(result, 'content') and result.content:
                        text_content = result.content[0].text
                        data = json.loads(text_content)
                        users = data.get('data', [])

                        if users:
                            # Return first match (most relevant by recency/usage)
                            user = users[0]
                            logger.info(f"Typeahead found: {user['name']} (GID: {user['gid']})")
                            return {
                                "gid": user["gid"],
                                "name": user["name"]
                            }
                        else:
                            logger.info(f"No typeahead results for '{name}', trying workspace users list")
                except Exception as e:
                    logger.warning(f"Typeahead search failed: {e}, falling back to workspace users")

                # Strategy 2: Fall back to listing all workspace users
                logger.info(f"Listing all workspace users to find '{name}'")
                result = await mcp_client.call_tool('asana_get_workspace_users', {
                    'workspace_gid': workspace_gid
                })

                # Parse MCP response
                import json
                if hasattr(result, 'content') and result.content:
                    text_content = result.content[0].text
                    data = json.loads(text_content)
                    users = data.get('data', [])

                    # Search for user by name (case-insensitive, partial match)
                    name_lower = name.lower().strip()

                    # Try exact match first
                    for user in users:
                        user_name = user.get("name", "").lower()
                        if user_name == name_lower:
                            logger.info(f"Found exact match: {user['name']} (GID: {user['gid']})")
                            return {
                                "gid": user["gid"],
                                "name": user["name"]
                            }

                    # Try partial match
                    for user in users:
                        user_name = user.get("name", "").lower()
                        if name_lower in user_name or user_name in name_lower:
                            logger.info(f"Found partial match: {user['name']} (GID: {user['gid']})")
                            return {
                                "gid": user["gid"],
                                "name": user["name"]
                            }

                    # No match found
                    logger.warning(f"No user found matching '{name}' in workspace")
                    return None

        except Exception as e:
            logger.error(f"Failed to resolve user '{name}': {e}", exc_info=True)
            raise


# Import json for cache key generation
import json
