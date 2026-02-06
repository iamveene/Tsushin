"""
Telegram Watcher Manager
Phase 10.1.1

Manages multiple Telegram bot polling instances.
"""

import logging
import asyncio
from typing import Dict, Optional
from sqlalchemy.orm import Session

from models import TelegramBotInstance
from telegram_integration.watcher import TelegramWatcher
from services.telegram_bot_service import TelegramBotService

logger = logging.getLogger(__name__)


class TelegramWatcherManager:
    """Manages Telegram watcher instances for all active bots."""

    def __init__(self, db_session_factory, message_callback):
        self.db_session_factory = db_session_factory
        self.message_callback = message_callback
        self.watchers: Dict[int, TelegramWatcher] = {}
        self.tasks: Dict[int, asyncio.Task] = {}

    async def start_all(self):
        """Start watchers for all active Telegram instances."""
        db = self.db_session_factory()
        try:
            instances = db.query(TelegramBotInstance).filter(
                TelegramBotInstance.status == "active"
            ).all()

            for instance in instances:
                await self.start_watcher(instance.id, db)

            logger.info(f"Started {len(instances)} Telegram watchers")
        finally:
            db.close()

    async def start_watcher(self, instance_id: int, db: Session = None):
        """Start watcher for a specific instance."""
        close_db = False
        if db is None:
            db = self.db_session_factory()
            close_db = True

        try:
            instance = db.query(TelegramBotInstance).get(instance_id)
            if not instance:
                logger.error(f"Instance {instance_id} not found")
                return False

            if instance_id in self.watchers:
                logger.info(f"Watcher already running for instance {instance_id}")
                return True

            # Decrypt token
            service = TelegramBotService(db)
            token = service._decrypt_token(instance.bot_token_encrypted, instance.tenant_id)

            # Create watcher
            watcher = TelegramWatcher(
                instance=instance,
                token=token,
                on_message_callback=self.message_callback,
                db_session=db
            )

            # Start polling task
            task = asyncio.create_task(watcher.start())

            self.watchers[instance_id] = watcher
            self.tasks[instance_id] = task

            logger.info(f"Started Telegram watcher for @{instance.bot_username}")
            return True

        except Exception as e:
            logger.error(f"Failed to start watcher for instance {instance_id}: {e}")
            return False
        finally:
            if close_db:
                db.close()

    async def stop_watcher(self, instance_id: int):
        """Stop watcher for a specific instance."""
        if instance_id not in self.watchers:
            return False

        watcher = self.watchers[instance_id]
        watcher.stop()

        if instance_id in self.tasks:
            self.tasks[instance_id].cancel()
            del self.tasks[instance_id]

        del self.watchers[instance_id]

        logger.info(f"Stopped Telegram watcher for instance {instance_id}")
        return True

    async def stop_all(self):
        """Stop all watchers."""
        for instance_id in list(self.watchers.keys()):
            await self.stop_watcher(instance_id)
