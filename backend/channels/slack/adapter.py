"""
Slack Channel Adapter
v0.6.0 Item 33

Wraps slack-bolt/slack-sdk for messaging through Slack workspaces.
Follows the same ChannelAdapter contract as WhatsApp and Telegram adapters.
"""

import asyncio
import logging
from typing import ClassVar, Optional

from channels.base import Channel
from channels.types import SendResult, HealthResult


class SlackChannelAdapter(Channel):
    """Slack channel via Bot API (Socket Mode or HTTP Events API)."""

    channel_type: ClassVar[str] = "slack"
    delivery_mode: ClassVar[str] = "push"     # Socket Mode or Events API
    supports_threads: ClassVar[bool] = True
    supports_reactions: ClassVar[bool] = True
    supports_rich_formatting: ClassVar[bool] = True   # Block Kit
    supports_media: ClassVar[bool] = True
    text_chunk_limit: ClassVar[int] = 4000    # Slack limit ~4000 for text blocks

    def __init__(self, bot_token: str, logger: logging.Logger):
        """
        Args:
            bot_token: Decrypted Slack bot token (xoxb-...)
            logger: Logger instance
        """
        self.bot_token = bot_token
        self.logger = logger
        self._client = None

    @property
    def client(self):
        """Lazy-initialize Slack WebClient to avoid import at module load."""
        if self._client is None:
            from slack_sdk import WebClient
            self._client = WebClient(token=self.bot_token)
        return self._client

    async def start(self) -> None:
        """No-op -- Slack Socket Mode lifecycle managed externally."""
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
        """Send message to a Slack channel or DM.

        Args:
            to: Slack channel ID (C...) or user ID (U...) for DM
            text: Message text
            media_path: Optional file to upload
            **kwargs: thread_ts for threaded replies
        """
        if not self.validate_recipient(to):
            return SendResult(
                success=False,
                error=f"Invalid Slack recipient: {to}"
            )

        thread_ts = kwargs.get("thread_ts")

        try:
            loop = asyncio.get_running_loop()
            if media_path:
                import os
                response = await loop.run_in_executor(
                    None,
                    lambda: self.client.files_upload_v2(
                        channel=to,
                        file=media_path,
                        initial_comment=text,
                        thread_ts=thread_ts,
                        filename=os.path.basename(media_path)
                    )
                )
                return SendResult(
                    success=response.get("ok", False),
                    message_id=response.get("file", {}).get("id"),
                    raw=response.data if hasattr(response, 'data') else None
                )

            response = await loop.run_in_executor(
                None,
                lambda: self.client.chat_postMessage(
                    channel=to,
                    text=text,
                    thread_ts=thread_ts
                )
            )
            return SendResult(
                success=response.get("ok", False),
                message_id=response.get("ts"),
                raw=response.data if hasattr(response, 'data') else None
            )
        except Exception as e:
            self.logger.error(f"Slack send error: {e}", exc_info=True)
            return SendResult(success=False, error=str(e))

    async def health_check(self) -> HealthResult:
        """Check Slack Bot API connection via auth.test."""
        try:
            loop = asyncio.get_running_loop()
            response = await loop.run_in_executor(None, self.client.auth_test)
            if response.get("ok"):
                return HealthResult(
                    healthy=True,
                    status="connected",
                    detail=f"Bot: @{response.get('user', 'unknown')} in {response.get('team', 'unknown')}"
                )
            return HealthResult(healthy=False, status="error", detail=response.get("error", "unknown"))
        except Exception as e:
            return HealthResult(healthy=False, status="error", detail=str(e))

    def validate_recipient(self, recipient: str) -> bool:
        """Validate Slack recipient (channel ID starts with C/G/D or user ID starts with U/W)."""
        if not recipient:
            return False
        return recipient[0] in ('C', 'G', 'D', 'U', 'W')
