"""
v0.7.0 Phase 0 queue router.

Centralizes the new MessageQueue.message_type discriminator while preserving
the existing channel handlers in QueueWorker. Phase 0 intentionally keeps
trigger/continuous rows resolved to an agent before enqueueing.
"""

from __future__ import annotations

from typing import Any


class QueueRouter:
    """Dispatch queue items by message_type, then by existing channel handlers."""

    async def dispatch(self, worker: Any, db: Any, item: Any) -> Any:
        message_type = getattr(item, "message_type", None) or "inbound_message"
        if message_type == "inbound_message":
            return await self._dispatch_inbound_message(worker, db, item)
        if message_type == "trigger_event":
            return await self._dispatch_trigger_event(worker, db, item)
        if message_type == "continuous_task":
            return await self._dispatch_continuous_task(worker, db, item)
        raise ValueError(f"Unknown message_type: {message_type}")

    async def _dispatch_inbound_message(self, worker: Any, db: Any, item: Any) -> Any:
        channel = item.channel
        if channel == "playground":
            return await worker._process_playground_message(db, item)
        if channel == "whatsapp":
            await worker._process_whatsapp_message(db, item)
            return None
        if channel == "telegram":
            await worker._process_telegram_message(db, item)
            return None
        if channel == "webhook":
            return await worker._process_webhook_message(db, item)
        if channel == "api":
            return await worker._process_api_message(db, item)
        if channel == "slack":
            await worker._process_slack_message(db, item)
            return None
        if channel == "discord":
            await worker._process_discord_message(db, item)
            return None
        raise ValueError(f"Unknown channel: {channel}")

    async def _dispatch_trigger_event(self, worker: Any, db: Any, item: Any) -> Any:
        # Phase 0 has no Trigger base yet; webhook keeps its current path.
        if item.channel == "webhook":
            return await worker._process_webhook_message(db, item)
        raise NotImplementedError(
            f"trigger_event routing for channel '{item.channel}' lands after the Channel/Trigger split"
        )

    async def _dispatch_continuous_task(self, worker: Any, db: Any, item: Any) -> Any:
        raise NotImplementedError("continuous_task routing lands with the continuous-agent control plane")


queue_router = QueueRouter()
