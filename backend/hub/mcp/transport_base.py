"""Abstract MCP transport base class."""
from abc import ABC, abstractmethod
from typing import Optional, Any
import logging

logger = logging.getLogger(__name__)


class MCPTransport(ABC):
    """Abstract transport for MCP server connections."""

    def __init__(self, server_config):
        self.server_config = server_config
        self._connected = False
        self._session = None

    @abstractmethod
    async def connect(self) -> Any:
        """Establish connection. Returns session object."""
        pass

    @abstractmethod
    async def disconnect(self) -> None:
        """Close connection."""
        pass

    def is_connected(self) -> bool:
        return self._connected

    @abstractmethod
    async def ping(self) -> bool:
        """Health check ping. Returns True if alive."""
        pass

    @abstractmethod
    async def list_tools(self) -> list:
        """Discover available tools."""
        pass

    @abstractmethod
    async def call_tool(self, tool_name: str, arguments: dict) -> Any:
        """Execute a tool call."""
        pass
