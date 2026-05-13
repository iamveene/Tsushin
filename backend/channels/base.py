"""Shared entry-point contracts for channels and triggers."""

from abc import ABC, abstractmethod
from typing import ClassVar, Optional

from channels.types import HealthResult, SendResult


class EntryPoint(ABC):
    """Shared lifecycle contract for all inbound entry points."""

    channel_type: ClassVar[str] = ""
    delivery_mode: ClassVar[str] = "pull"

    @abstractmethod
    async def start(self) -> None:
        """Initialize any transport or background polling."""

    @abstractmethod
    async def stop(self) -> None:
        """Gracefully stop the transport."""

    @abstractmethod
    async def health_check(self) -> HealthResult:
        """Return the current health snapshot for this entry point."""


class Channel(EntryPoint):
    """Bidirectional conversational surface."""

    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = True
    text_chunk_limit: ClassVar[int] = 4096

    @abstractmethod
    async def send_message(
        self,
        to: str,
        text: str,
        *,
        media_path: Optional[str] = None,
        **kwargs,
    ) -> SendResult:
        """Send an outbound conversational message."""

    def validate_recipient(self, recipient: str) -> bool:
        """Allow channel-specific recipient validation hooks."""
        return True


# v0.7.0 compatibility alias: callers can keep importing ChannelAdapter.
ChannelAdapter = Channel
