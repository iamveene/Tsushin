"""
Telegram Bot API Client
Phase 10.1.1

Wrapper around python-telegram-bot for Tsushin integration.
"""

import logging
import asyncio
from typing import Optional, List, Dict, Any
from telegram import Bot, Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


class TelegramClient:
    """Async Telegram Bot API client."""

    def __init__(self, token: str):
        self.token = token
        self.bot = Bot(token=token)
        self._bot_info = None

    async def get_me(self) -> Dict[str, Any]:
        """Validate token and get bot info."""
        try:
            user = await self.bot.get_me()
            self._bot_info = {
                "id": user.id,
                "username": user.username,
                "first_name": user.first_name,
                "can_join_groups": user.can_join_groups,
                "can_read_all_group_messages": user.can_read_all_group_messages,
            }
            return self._bot_info
        except TelegramError as e:
            logger.error(f"Failed to get bot info: {e}")
            raise

    async def get_updates(
        self,
        offset: int = 0,
        limit: int = 100,
        timeout: int = 30
    ) -> List[Update]:
        """Long polling for updates."""
        try:
            updates = await self.bot.get_updates(
                offset=offset,
                limit=limit,
                timeout=timeout,
                allowed_updates=["message", "callback_query"]
            )
            return updates
        except TelegramError as e:
            logger.error(f"Failed to get updates: {e}")
            return []

    async def send_message(
        self,
        chat_id: int,
        text: str,
        parse_mode: str = "HTML",
        reply_markup: Optional[InlineKeyboardMarkup] = None,
        reply_to_message_id: Optional[int] = None
    ) -> bool:
        """Send text message."""
        try:
            await self.bot.send_message(
                chat_id=chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=reply_markup,
                reply_to_message_id=reply_to_message_id
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to send message: {e}")
            return False

    async def send_photo(
        self,
        chat_id: int,
        photo: str,  # File path or URL
        caption: Optional[str] = None,
        parse_mode: str = "HTML"
    ) -> bool:
        """Send photo."""
        try:
            await self.bot.send_photo(
                chat_id=chat_id,
                photo=photo,
                caption=caption,
                parse_mode=parse_mode
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to send photo: {e}")
            return False

    async def send_document(
        self,
        chat_id: int,
        document: str,
        caption: Optional[str] = None
    ) -> bool:
        """Send document."""
        try:
            await self.bot.send_document(
                chat_id=chat_id,
                document=document,
                caption=caption
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to send document: {e}")
            return False

    async def send_voice(
        self,
        chat_id: int,
        voice: str,
        caption: Optional[str] = None
    ) -> bool:
        """Send voice message."""
        try:
            await self.bot.send_voice(
                chat_id=chat_id,
                voice=voice,
                caption=caption
            )
            return True
        except TelegramError as e:
            logger.error(f"Failed to send voice: {e}")
            return False

    async def download_file(self, file_id: str, destination: str) -> bool:
        """Download file from Telegram."""
        try:
            file = await self.bot.get_file(file_id)
            await file.download_to_drive(destination)
            return True
        except TelegramError as e:
            logger.error(f"Failed to download file: {e}")
            return False
