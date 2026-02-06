"""
Asana MCP Client - TRUE MCP Protocol Implementation

Uses official MCP Python SDK to connect to Asana MCP Server via SSE.
This is the CORRECT implementation following MCP specification.
"""

import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from mcp import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)


@dataclass
class MCPTool:
    """Represents an MCP tool schema."""
    name: str
    description: str
    input_schema: Dict


class AsanaMCPClient:
    """
    Official MCP client for Asana MCP Server.

    Uses MCP Python SDK to connect via SSE transport.
    Tokens from MCP OAuth work correctly with MCP protocol.
    """

    MCP_SERVER_URL = "https://mcp.asana.com/sse"

    def __init__(self, access_token: str):
        """
        Initialize MCP client.

        Args:
            access_token: OAuth access token from Asana MCP OAuth flow
        """
        self.access_token = access_token
        self._session: Optional[ClientSession] = None
        self._tools_cache: Optional[List[MCPTool]] = None

    async def __aenter__(self):
        """Async context manager entry - establishes SSE connection."""
        logger.info(f"Connecting to Asana MCP Server: {self.MCP_SERVER_URL}")

        # Create SSE client with OAuth token
        self._sse_context = sse_client(
            url=self.MCP_SERVER_URL,
            headers={"Authorization": f"Bearer {self.access_token}"}
        )
        self._streams = await self._sse_context.__aenter__()

        # Create client session
        self._session_context = ClientSession(*self._streams)
        self._session = await self._session_context.__aenter__()

        # Initialize the MCP session
        await self._session.initialize()
        logger.info("MCP session initialized successfully")

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit - closes SSE connection."""
        if self._session_context:
            await self._session_context.__aexit__(exc_type, exc_val, exc_tb)
        if self._sse_context:
            await self._sse_context.__aexit__(exc_type, exc_val, exc_tb)
        logger.info("MCP session closed")

    async def list_tools(self) -> List[MCPTool]:
        """
        List all available Asana MCP tools.

        Returns:
            List of MCPTool objects
        """
        if self._tools_cache:
            return self._tools_cache

        if not self._session:
            raise RuntimeError("MCP session not initialized. Use async with context manager.")

        # Call MCP list_tools
        response = await self._session.list_tools()

        tools = [
            MCPTool(
                name=tool.name,
                description=tool.description or "",
                input_schema=tool.inputSchema if hasattr(tool, 'inputSchema') else {}
            )
            for tool in response.tools
        ]

        self._tools_cache = tools
        logger.info(f"Discovered {len(tools)} Asana MCP tools")
        return tools

    async def call_tool(self, tool_name: str, arguments: Dict) -> Any:
        """
        Execute an Asana MCP tool.

        Args:
            tool_name: Name of the tool to execute
            arguments: Tool arguments

        Returns:
            Tool execution result
        """
        if not self._session:
            raise RuntimeError("MCP session not initialized. Use async with context manager.")

        logger.info(f"Calling MCP tool: {tool_name} with args: {arguments}")

        # Call tool via MCP protocol
        result = await self._session.call_tool(tool_name, arguments)

        logger.info(f"Tool {tool_name} executed successfully")
        return result

    async def get_tool_by_name(self, name: str) -> Optional[MCPTool]:
        """Find tool by name."""
        tools = await self.list_tools()
        return next((t for t in tools if t.name == name), None)

    async def search_tools(self, query: str) -> List[MCPTool]:
        """Search tools by name or description."""
        tools = await self.list_tools()
        query_lower = query.lower()

        return [
            t for t in tools
            if query_lower in t.name.lower() or query_lower in t.description.lower()
        ]
