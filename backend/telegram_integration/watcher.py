"""
Telegram Message Watcher
Phase 10.1.1

Polls Telegram for new messages and routes them to agents.
"""

import logging
import asyncio
from typing import Callable, Optional
from datetime import datetime
from sqlalchemy.orm import Session

from .client import TelegramClient
from models import TelegramBotInstance, MessageCache

logger = logging.getLogger(__name__)


class TelegramWatcher:
    """Watch for incoming Telegram messages via long polling."""

    def __init__(
        self,
        instance: TelegramBotInstance,
        token: str,
        on_message_callback: Callable,
        db_session: Session,
        poll_timeout: int = 30
    ):
        self.instance = instance
        self.client = TelegramClient(token)
        self.on_message_callback = on_message_callback
        self.db_session = db_session
        self.poll_timeout = poll_timeout
        self.running = False
        self.paused = False
        self.last_update_id = instance.last_update_id or 0
        self.processed_message_ids = set()

    async def start(self):
        """Start the polling loop."""
        self.running = True
        logger.info(f"Starting Telegram watcher for @{self.instance.bot_username}")

        # Validate token with retry (prevents permanent failure on transient network errors at startup)
        while self.running:
            try:
                bot_info = await self.client.get_me()
                logger.info(f"Connected as @{bot_info['username']}")
                break
            except Exception as e:
                logger.warning(f"Waiting for Telegram API... ({e})")
                await asyncio.sleep(5)  # Wait 5s before retrying

        # Main polling loop
        while self.running:
            if self.paused:
                await asyncio.sleep(1)
                continue

            try:
                await self._poll_messages()
            except Exception as e:
                logger.error(f"Error in polling loop: {e}", exc_info=True)
                await asyncio.sleep(5)

    async def _poll_messages(self):
        """Poll for new messages."""
        updates = await self.client.get_updates(
            offset=self.last_update_id + 1,
            timeout=self.poll_timeout
        )

        for update in updates:
            # Update offset
            self.last_update_id = update.update_id

            # Save offset to database
            self.instance.last_update_id = self.last_update_id
            self.db_session.commit()

            # Process message
            if update.message:
                await self._process_message(update)
            elif update.callback_query:
                await self._process_callback(update)

    async def _process_message(self, update):
        """Process incoming message."""
        message = update.message

        # Skip if already processed
        msg_id = f"tg_{message.message_id}_{message.chat.id}"
        if msg_id in self.processed_message_ids:
            return
        self.processed_message_ids.add(msg_id)

        # Check message cache for duplicates
        existing = self.db_session.query(MessageCache).filter_by(
            source_id=msg_id
        ).first()
        if existing:
            logger.debug(f"Skipping duplicate message: {msg_id}")
            return

        # Extract message content
        content = message.text or message.caption or ""

        # Handle voice messages - download and transcribe
        voice_file_id = None
        transcription = None
        if message.voice:
            voice_file_id = message.voice.file_id
            logger.info(f"Voice message detected: {voice_file_id}")

            # Download voice file
            try:
                import tempfile
                import os

                # Create temp directory for audio files
                temp_dir = tempfile.mkdtemp(prefix="telegram_voice_")
                voice_path = os.path.join(temp_dir, f"voice_{message.message_id}.ogg")

                # Download from Telegram
                success = await self.client.download_file(voice_file_id, voice_path)
                if success and os.path.exists(voice_path):
                    logger.info(f"Voice file downloaded: {voice_path}")

                    # Transcribe using audio_transcript skill
                    try:
                        from agent.skills.audio_transcript import AudioTranscriptSkill
                        transcript_skill = AudioTranscriptSkill()

                        # Transcribe (skill handles OGG format)
                        result = await transcript_skill.transcribe_audio(voice_path)
                        if result and result.get("text"):
                            transcription = result["text"]
                            logger.info(f"Voice transcribed: {transcription[:100]}")

                            # Add transcription to message content
                            if content:
                                content = f"{content}\n\n[Voice transcription: {transcription}]"
                            else:
                                content = f"[Voice message] {transcription}"
                        else:
                            logger.warning("Voice transcription returned no text")
                            content = content or "[Voice message - transcription failed]"
                    except Exception as transcribe_error:
                        logger.error(f"Failed to transcribe voice: {transcribe_error}", exc_info=True)
                        content = content or "[Voice message - transcription unavailable]"
                    finally:
                        # Clean up temp file
                        try:
                            if os.path.exists(voice_path):
                                os.unlink(voice_path)
                            os.rmdir(temp_dir)
                        except Exception as cleanup_error:
                            logger.warning(f"Failed to cleanup voice file: {cleanup_error}")
                else:
                    logger.warning(f"Failed to download voice file: {voice_file_id}")
                    content = content or "[Voice message - download failed]"

            except Exception as voice_error:
                logger.error(f"Error processing voice message: {voice_error}", exc_info=True)
                content = content or "[Voice message - processing error]"

        # Build internal message format
        internal_msg = {
            "id": msg_id,
            "chat_id": str(message.chat.id),
            "sender": str(message.from_user.id),
            "sender_name": message.from_user.first_name or message.from_user.username,
            "sender_username": message.from_user.username,
            "body": content,
            "timestamp": message.date.isoformat(),
            "is_group": message.chat.type in ["group", "supergroup"],
            "chat_name": message.chat.title or message.chat.first_name,
            "channel": "telegram",
            "telegram_id": str(message.from_user.id),
            "voice_file_id": voice_file_id,
            "reply_to_message_id": message.reply_to_message.message_id if message.reply_to_message else None,
            "_telegram_instance_id": self.instance.id  # For routing to correct agent
        }

        # Route to agent
        try:
            await self.on_message_callback(internal_msg, "telegram_message")
        except Exception as e:
            logger.error(f"Error processing message: {e}", exc_info=True)

    async def _process_callback(self, update):
        """Process callback query (button press)."""
        callback_query = update.callback_query

        if not callback_query:
            return

        logger.info(f"Callback query received: {callback_query.data}")

        try:
            # Answer callback query immediately (required by Telegram API)
            await self.client.bot.answer_callback_query(callback_query.id)

            # Build message context for callback
            internal_msg = {
                "id": f"tg_callback_{callback_query.id}",
                "chat_id": str(callback_query.message.chat.id),
                "sender": str(callback_query.from_user.id),
                "sender_name": callback_query.from_user.first_name or callback_query.from_user.username,
                "sender_username": callback_query.from_user.username,
                "body": callback_query.data,  # The callback data becomes the message body
                "timestamp": callback_query.message.date.isoformat(),
                "is_group": callback_query.message.chat.type in ["group", "supergroup"],
                "chat_name": callback_query.message.chat.title or callback_query.message.chat.first_name,
                "channel": "telegram",
                "telegram_id": str(callback_query.from_user.id),
                "is_callback_query": True,
                "_telegram_instance_id": self.instance.id
            }

            # Route callback as a regular message
            await self.on_message_callback(internal_msg, "telegram_callback")

        except Exception as e:
            logger.error(f"Error processing callback query: {e}", exc_info=True)

    def pause(self):
        """Pause message processing."""
        self.paused = True
        logger.info(f"Telegram watcher paused for @{self.instance.bot_username}")

    def resume(self):
        """Resume message processing."""
        self.paused = False
        logger.info(f"Telegram watcher resumed for @{self.instance.bot_username}")

    def stop(self):
        """Stop the polling loop."""
        self.running = False
        logger.info(f"Telegram watcher stopped for @{self.instance.bot_username}")
