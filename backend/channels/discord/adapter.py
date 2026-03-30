"""
Discord Channel Adapter
v0.6.0 Item 34

Wraps Discord REST API for messaging through Discord servers (guilds).
Follows the same ChannelAdapter contract as WhatsApp, Telegram, and Slack adapters.

Uses Discord REST API directly for outbound messages (no gateway connection needed
for sending). Gateway/WebSocket is only required for inbound event handling, which
is managed externally.
"""

import logging
import os
from typing import ClassVar, Optional

from channels.base import ChannelAdapter
from channels.types import SendResult, HealthResult

DISCORD_API_BASE = "https://discord.com/api/v10"


class DiscordChannelAdapter(ChannelAdapter):
    """Discord channel via Bot REST API."""

    channel_type: ClassVar[str] = "discord"
    delivery_mode: ClassVar[str] = "push"     # Gateway events or webhook
    supports_threads: ClassVar[bool] = True
    supports_reactions: ClassVar[bool] = True
    supports_rich_formatting: ClassVar[bool] = True   # Markdown + Embeds
    supports_media: ClassVar[bool] = True
    text_chunk_limit: ClassVar[int] = 2000    # Discord message character limit

    def __init__(self, bot_token: str, logger: logging.Logger):
        """
        Args:
            bot_token: Decrypted Discord bot token
            logger: Logger instance
        """
        self.bot_token = bot_token
        self.logger = logger
        self._http = None

    @property
    def http(self):
        """Lazy-init aiohttp session for Discord REST API calls."""
        if self._http is None:
            import aiohttp
            self._http = aiohttp.ClientSession(headers={
                "Authorization": f"Bot {self.bot_token}",
                "Content-Type": "application/json",
                "User-Agent": "TsushinBot (https://github.com/tsushin, 0.6.0)"
            })
        return self._http

    async def start(self) -> None:
        """No-op -- Discord Gateway lifecycle managed externally."""
        pass

    async def stop(self) -> None:
        """Close HTTP session if open."""
        if self._http is not None:
            await self._http.close()
            self._http = None

    async def send_message(
        self,
        to: str,
        text: str,
        *,
        media_path: Optional[str] = None,
        **kwargs
    ) -> SendResult:
        """Send message to a Discord channel via REST API.

        Args:
            to: Discord channel ID (snowflake)
            text: Message text
            media_path: Optional file to upload
            **kwargs: thread_id for threaded replies
        """
        if not self.validate_recipient(to):
            return SendResult(
                success=False,
                error=f"Invalid Discord channel ID: {to}"
            )

        url = f"{DISCORD_API_BASE}/channels/{to}/messages"

        try:
            import aiohttp

            if media_path:
                # Multipart upload for file attachments
                form = aiohttp.FormData()
                form.add_field("payload_json", '{"content": ' + repr(text or '') + '}',
                               content_type="application/json")
                form.add_field(
                    "files[0]",
                    open(media_path, "rb"),
                    filename=os.path.basename(media_path)
                )
                # Need separate headers without Content-Type for multipart
                headers = {
                    "Authorization": f"Bot {self.bot_token}",
                    "User-Agent": "TsushinBot (https://github.com/tsushin, 0.6.0)"
                }
                async with self.http.post(url, data=form, headers=headers) as resp:
                    data = await resp.json()
                    success = 200 <= resp.status < 300
                    return SendResult(
                        success=success,
                        message_id=data.get("id") if success else None,
                        error=data.get("message") if not success else None,
                        raw=data
                    )
            else:
                payload = {"content": text}

                # Thread support: reply in a thread
                thread_id = kwargs.get("thread_id")
                if thread_id:
                    payload["message_reference"] = {"message_id": thread_id}

                async with self.http.post(url, json=payload) as resp:
                    data = await resp.json()
                    success = 200 <= resp.status < 300
                    return SendResult(
                        success=success,
                        message_id=data.get("id") if success else None,
                        error=data.get("message") if not success else None,
                        raw=data
                    )
        except Exception as e:
            self.logger.error(f"Discord send error: {e}", exc_info=True)
            return SendResult(success=False, error=str(e))

    async def health_check(self) -> HealthResult:
        """Check bot connection via /users/@me endpoint."""
        try:
            url = f"{DISCORD_API_BASE}/users/@me"
            async with self.http.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    bot_name = data.get("username", "unknown")
                    discriminator = data.get("discriminator", "0")
                    display = f"{bot_name}#{discriminator}" if discriminator != "0" else bot_name
                    return HealthResult(
                        healthy=True,
                        status="connected",
                        detail=f"Bot: @{display}"
                    )
                return HealthResult(
                    healthy=False,
                    status="error",
                    detail=f"HTTP {resp.status}"
                )
        except Exception as e:
            return HealthResult(healthy=False, status="error", detail=str(e))

    def validate_recipient(self, recipient: str) -> bool:
        """Validate Discord channel ID (snowflake: 17-20 digit integer)."""
        if not recipient:
            return False
        return recipient.isdigit() and 17 <= len(recipient) <= 20
