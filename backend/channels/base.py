"""
Channel Abstraction Layer — Base Adapter Contract
v0.6.0 Item 32

All messaging channels (WhatsApp, Telegram, Slack, Discord, Playground)
implement this contract. Follows the same ABC pattern as agent.skills.base.BaseSkill.
"""

from abc import ABC, abstractmethod
from typing import ClassVar, Optional

from channels.types import SendResult, HealthResult


class ChannelAdapter(ABC):
    """Base contract for all messaging channel adapters.

    Each adapter wraps channel-specific transport logic (MCP, Bot API, SDK)
    behind a unified interface. Adapters are instantiated per-router (not global)
    because each router serves a specific tenant/instance context.

    Class Variables:
        channel_type: Identifier string (e.g., "whatsapp", "telegram", "slack")
        delivery_mode: "push" (webhook/request-response) or "pull" (polling/websocket)
        supports_threads: Whether the channel natively supports threaded replies
        supports_reactions: Whether the channel supports message reactions
        supports_rich_formatting: Whether the channel supports rich text (HTML, blocks, embeds)
        supports_media: Whether the channel supports media attachments
        text_chunk_limit: Max characters per message before chunking is needed
    """

    channel_type: ClassVar[str] = ""
    delivery_mode: ClassVar[str] = "pull"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = True
    text_chunk_limit: ClassVar[int] = 4096

    @abstractmethod
    async def start(self) -> None:
        """Initialize the channel connection (WebSocket, polling loop, etc.).
        No-op for channels managed externally (e.g., WhatsApp MCP containers).
        """

    @abstractmethod
    async def stop(self) -> None:
        """Graceful shutdown of the channel connection."""

    @abstractmethod
    async def send_message(
        self,
        to: str,
        text: str,
        *,
        media_path: Optional[str] = None,
        **kwargs
    ) -> SendResult:
        """Send an outbound message through this channel.

        Args:
            to: Recipient identifier (phone number, chat ID, channel ID, etc.)
            text: Message text content
            media_path: Optional path to media file to attach
            **kwargs: Channel-specific parameters (agent_id, thread_id, etc.)

        Returns:
            SendResult with success status and optional message ID
        """

    @abstractmethod
    async def health_check(self) -> HealthResult:
        """Check the channel connection health.

        Returns:
            HealthResult with health status and optional diagnostics
        """

    def validate_recipient(self, recipient: str) -> bool:
        """Validate that a recipient identifier is appropriate for this channel.

        Override in subclasses for channel-specific validation (phone format,
        numeric ID, etc.). Default: allow all.

        Args:
            recipient: Recipient identifier to validate

        Returns:
            True if valid for this channel
        """
        return True
