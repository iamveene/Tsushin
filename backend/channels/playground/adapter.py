"""
Playground Channel Adapter
v0.6.0 Item 32

Represents the web Playground channel in the registry. Playground responses
are returned synchronously via PlaygroundService, not pushed. This adapter
exists for protocol uniformity, health_check, and capability flags.
"""

import logging
from typing import ClassVar, Optional

from channels.base import Channel
from channels.types import SendResult, HealthResult


class PlaygroundChannelAdapter(Channel):
    """Web Playground channel (request/response via API + WebSocket streaming)."""

    channel_type: ClassVar[str] = "playground"
    delivery_mode: ClassVar[str] = "push"
    supports_threads: ClassVar[bool] = True
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = True
    supports_media: ClassVar[bool] = True
    text_chunk_limit: ClassVar[int] = 65536

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    async def start(self) -> None:
        """No-op — Playground is stateless request/response."""
        pass

    async def stop(self) -> None:
        """No-op."""
        pass

    async def send_message(
        self,
        to: str,
        text: str,
        *,
        media_path: Optional[str] = None,
        **kwargs
    ) -> SendResult:
        """Playground sends are handled via PlaygroundService return value.
        This is a no-op that returns success (response already delivered inline).
        """
        return SendResult(success=True, message_id=None)

    async def health_check(self) -> HealthResult:
        """Always healthy — no external connection required."""
        return HealthResult(healthy=True, status="connected")
