"""
Telegram Message Sender
Phase 10.1.1

Similar to mcp_sender.py but for Telegram.
"""

import logging
import asyncio
from typing import Optional, Dict, Any
from telegram_integration.client import TelegramClient

logger = logging.getLogger(__name__)


class TelegramSender:
    """Send messages via Telegram Bot API."""

    def __init__(self, token: str):
        self.client = TelegramClient(token)

    async def send_message(
        self,
        chat_id: int,
        message: str,
        reply_markup: Optional[Dict] = None,
        reply_to: Optional[int] = None
    ) -> bool:
        """
        Send a text message.

        Args:
            chat_id: Telegram chat ID
            message: Text content
            reply_markup: Optional inline keyboard
            reply_to: Optional message ID to reply to
        """
        # Convert dict to InlineKeyboardMarkup if provided
        keyboard = None
        if reply_markup and "inline_keyboard" in reply_markup:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup
            buttons = []
            for row in reply_markup["inline_keyboard"]:
                button_row = []
                for btn in row:
                    button_row.append(InlineKeyboardButton(
                        text=btn.get("text", ""),
                        callback_data=btn.get("callback_data"),
                        url=btn.get("url")
                    ))
                buttons.append(button_row)
            keyboard = InlineKeyboardMarkup(buttons)

        return await self.client.send_message(
            chat_id=chat_id,
            text=message,
            reply_markup=keyboard,
            reply_to_message_id=reply_to
        )

    async def send_audio(
        self,
        chat_id: int,
        audio_path: str,
        caption: Optional[str] = None
    ) -> bool:
        """Send audio/voice message."""
        return await self.client.send_voice(
            chat_id=chat_id,
            voice=audio_path,
            caption=caption
        )
