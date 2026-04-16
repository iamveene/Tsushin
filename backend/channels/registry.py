"""
Channel Abstraction Layer — Channel Registry
v0.6.0 Item 32

Maps channel_type strings to ChannelAdapter instances.
Instantiated per-AgentRouter (not global) because each router serves
a specific tenant/instance context with its own transport objects.
"""

import logging
from typing import Dict, List, Optional

from channels.base import ChannelAdapter

logger = logging.getLogger(__name__)


class ChannelRegistry:
    """Discovers and manages channel adapter instances per router context."""

    def __init__(self) -> None:
        self._adapters: Dict[str, ChannelAdapter] = {}

    def register(self, channel_type: str, adapter: ChannelAdapter) -> None:
        """Register a channel adapter instance.

        Args:
            channel_type: Channel identifier (e.g., "whatsapp", "telegram")
            adapter: Adapter instance for this channel
        """
        self._adapters[channel_type] = adapter
        logger.debug(f"Channel adapter registered: {channel_type}")

    def get_adapter(self, channel_type: str) -> Optional[ChannelAdapter]:
        """Retrieve adapter by channel type string.

        Args:
            channel_type: Channel identifier

        Returns:
            ChannelAdapter instance or None if not registered
        """
        return self._adapters.get(channel_type)

    def list_channels(self) -> List[str]:
        """List all registered channel type strings."""
        return list(self._adapters.keys())

    def has_channel(self, channel_type: str) -> bool:
        """Check if a channel is registered."""
        return channel_type in self._adapters
