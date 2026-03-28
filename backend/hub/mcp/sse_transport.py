"""SSE transport for MCP servers -- generalized from AsanaMCPClient."""
import asyncio
import logging
from typing import Any, Optional
from contextlib import AsyncExitStack
from hub.mcp.transport_base import MCPTransport

logger = logging.getLogger(__name__)


class SSETransport(MCPTransport):
    """SSE-based MCP transport using mcp SDK.

    Generalizes the pattern from AsanaMCPClient (hub/asana/asana_mcp_client.py)
    to work with any SSE-based MCP server.
    """

    def __init__(self, server_config):
        super().__init__(server_config)
        self._streams = None
        self._exit_stack = None

    async def connect(self) -> Any:
        """Establish SSE connection to the MCP server.

        Returns:
            ClientSession object.

        Raises:
            Exception: If connection fails.
        """
        try:
            from mcp.client.sse import sse_client
            from mcp import ClientSession

            headers = self._build_auth_headers()

            # Create SSE connection via async exit stack
            self._exit_stack = AsyncExitStack()
            await self._exit_stack.__aenter__()

            self._streams = await self._exit_stack.enter_async_context(
                sse_client(self.server_config.server_url, headers=headers)
            )
            self._session = await self._exit_stack.enter_async_context(
                ClientSession(*self._streams)
            )
            await self._session.initialize()
            self._connected = True
            logger.info(f"Connected to MCP server: {self.server_config.server_name}")
            return self._session

        except Exception as e:
            self._connected = False
            logger.error(f"Failed to connect to MCP server {self.server_config.server_name}: {e}")
            raise

    async def disconnect(self) -> None:
        """Close SSE connection and clean up resources."""
        if self._exit_stack:
            try:
                await self._exit_stack.__aexit__(None, None, None)
            except Exception:
                pass
        self._connected = False
        self._session = None
        self._streams = None
        self._exit_stack = None

    async def ping(self) -> bool:
        """Send a ping to the MCP server to check liveness."""
        if not self._session:
            return False
        try:
            await self._session.send_ping()
            return True
        except Exception:
            return False

    async def list_tools(self) -> list:
        """Discover available tools from the MCP server."""
        if not self._session:
            raise RuntimeError("Not connected")
        result = await self._session.list_tools()
        return result.tools if hasattr(result, 'tools') else []

    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Execute a tool call on the MCP server."""
        if not self._session:
            raise RuntimeError("Not connected")
        result = await self._session.call_tool(tool_name, arguments)
        return result

    def _build_auth_headers(self) -> dict:
        """Build authentication headers based on server config."""
        headers = {}
        auth_type = self.server_config.auth_type

        if auth_type in ('bearer', 'api_key') and self.server_config.auth_token_encrypted:
            from hub.mcp.utils import decrypt_auth_token
            token = decrypt_auth_token(self.server_config)

            if auth_type == 'bearer':
                headers["Authorization"] = f"Bearer {token}"
            elif auth_type == 'api_key':
                header_name = self.server_config.auth_header_name or "X-API-Key"
                headers[header_name] = token

        elif auth_type == 'header' and self.server_config.auth_token_encrypted:
            from hub.mcp.utils import decrypt_auth_token
            token = decrypt_auth_token(self.server_config)
            header_name = self.server_config.auth_header_name or "Authorization"
            headers[header_name] = token

        return headers
