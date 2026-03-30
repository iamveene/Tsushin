"""
Telegram Channel Adapter
v0.6.0 Item 32

Wraps the existing TelegramSender behind the ChannelAdapter contract.
No behavioral changes — delegates to the same transport object.
"""

import logging
from typing import ClassVar, Optional

from channels.base import ChannelAdapter
from channels.types import SendResult, HealthResult


class TelegramChannelAdapter(ChannelAdapter):
    """Telegram channel via Bot API."""

    channel_type: ClassVar[str] = "telegram"
    delivery_mode: ClassVar[str] = "pull"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = True
    supports_media: ClassVar[bool] = True
    text_chunk_limit: ClassVar[int] = 4096

    def __init__(self, telegram_sender, logger: logging.Logger):
        """
        Args:
            telegram_sender: TelegramSender instance with bot token
            logger: Logger instance
        """
        self.telegram_sender = telegram_sender
        self.logger = logger

    async def start(self) -> None:
        """No-op — Telegram watcher lifecycle is managed externally."""
        pass

    async def stop(self) -> None:
        """No-op — Telegram watcher lifecycle is managed externally."""
        pass

    async def send_message(
        self,
        to: str,
        text: str,
        *,
        media_path: Optional[str] = None,
        **kwargs
    ) -> SendResult:
        """Send message via Telegram Bot API.

        Args:
            to: Telegram chat ID (numeric string)
            text: Message text
            media_path: Optional photo/media file path
        """
        if not self.validate_recipient(to):
            return SendResult(
                success=False,
                error=f"Invalid Telegram recipient: {to}"
            )

        try:
            chat_id = int(to)

            if media_path:
                self.logger.info(f"Sending photo to Telegram chat {chat_id}: {media_path}")
                success = await self.telegram_sender.send_photo(
                    chat_id=chat_id,
                    photo_path=media_path,
                    caption=text or None
                )
            else:
                success = await self.telegram_sender.send_message(
                    chat_id=chat_id,
                    message=text
                )

            return SendResult(success=success)
        except Exception as e:
            self.logger.error(f"Telegram send error: {e}", exc_info=True)
            return SendResult(success=False, error=str(e))

    async def health_check(self) -> HealthResult:
        """Check Telegram Bot API connection."""
        try:
            me = await self.telegram_sender.client.get_me()
            if me:
                return HealthResult(
                    healthy=True,
                    status="connected",
                    detail=f"Bot: @{me.get('username', 'unknown')}"
                )
            return HealthResult(healthy=False, status="error", detail="get_me returned None")
        except Exception as e:
            return HealthResult(healthy=False, status="error", detail=str(e))

    def validate_recipient(self, recipient: str) -> bool:
        """Validate Telegram recipient (must be numeric chat ID)."""
        normalized = recipient.split('@')[0].lstrip('+')
        if not normalized.isdigit():
            self.logger.error(
                f"BLOCKED: Invalid Telegram recipient '{recipient}' (must be numeric chat ID)"
            )
            return False
        return True
