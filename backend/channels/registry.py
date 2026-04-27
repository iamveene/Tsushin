"""Entry-point registry for Channel and Trigger instances."""

import logging
from typing import Dict, List, Optional

from channels.base import Channel, EntryPoint
from channels.trigger import Trigger

logger = logging.getLogger(__name__)


class ChannelRegistry:
    """Discovers and manages entry-point instances per router context."""

    def __init__(self) -> None:
        self._adapters: Dict[str, EntryPoint] = {}

    def register(self, channel_type: str, adapter: EntryPoint) -> None:
        """Register a channel or trigger instance.

        Args:
            channel_type: Channel identifier (e.g., "whatsapp", "telegram")
            adapter: Adapter instance for this channel
        """
        self._adapters[channel_type] = adapter
        logger.debug(f"Channel adapter registered: {channel_type}")

    def get_adapter(self, channel_type: str) -> Optional[EntryPoint]:
        """Retrieve entry point by channel type string.

        Args:
            channel_type: Channel identifier

        Returns:
            EntryPoint instance or None if not registered
        """
        return self._adapters.get(channel_type)

    def list_channels(self) -> List[str]:
        """List registered conversational channels."""
        return [
            channel_type
            for channel_type, adapter in self._adapters.items()
            if isinstance(adapter, Channel)
        ]

    def list_triggers(self) -> List[str]:
        """List registered trigger entry points."""
        return [
            channel_type
            for channel_type, adapter in self._adapters.items()
            if isinstance(adapter, Trigger)
        ]

    def has_channel(self, channel_type: str) -> bool:
        """Check if a channel is registered."""
        return channel_type in self.list_channels()
