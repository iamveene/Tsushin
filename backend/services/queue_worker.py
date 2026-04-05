"""
Queue Worker for Async Message Processing

Background asyncio worker that polls the message_queue table and dispatches
processing to the appropriate channel handler. Manages one task per
(tenant_id, agent_id) pair for sequential processing.
"""

import asyncio
import logging
import traceback
from datetime import datetime
from typing import Dict, Tuple, Optional
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.engine import Engine

logger = logging.getLogger(__name__)


class QueueWorker:
    """
    Asyncio-based worker for processing queued messages.

    - Polls for pending items every 500ms
    - Manages one processing task per (tenant_id, agent_id) pair
    - For playground: calls PlaygroundService.send_message() and pushes results via WebSocket
    - For api: calls PlaygroundService.send_message() and persists result for polling (no WebSocket)
    - For WhatsApp/Telegram: calls AgentRouter.route_message()
    - On failure: retries up to max_retries, then dead-letters
    - On startup: resets stale processing items
    """

    def __init__(self, engine: Engine, poll_interval_ms: int = 500):
        self.engine = engine
        self.poll_interval = poll_interval_ms / 1000.0  # Convert to seconds
        self._running = False
        self._poll_task: Optional[asyncio.Task] = None
        # Active processing tasks per (tenant_id, agent_id)
        self._active_tasks: Dict[Tuple[str, int], asyncio.Task] = {}
        self.SessionLocal = sessionmaker(bind=engine)

    async def start(self):
        """Start the queue worker."""
        if self._running:
            logger.warning("QueueWorker already running")
            return

        self._running = True

        # Reset stale processing items on startup
        try:
            db = self.SessionLocal()
            try:
                from services.message_queue_service import MessageQueueService
                service = MessageQueueService(db)
                stale_count = service.reset_stale(threshold_seconds=300)
                if stale_count > 0:
                    logger.info(f"QueueWorker reset {stale_count} stale processing items on startup")
            finally:
                db.close()
        except Exception as e:
            logger.error(f"Error resetting stale items on startup: {e}")

        # Start the polling loop
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(f"QueueWorker started (poll interval: {self.poll_interval}s)")

    async def stop(self):
        """Stop the queue worker gracefully."""
        if not self._running:
            return

        logger.info("Stopping QueueWorker...")
        self._running = False

        # Cancel the poll task
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass

        # Wait for active tasks to finish (with timeout)
        if self._active_tasks:
            logger.info(f"Waiting for {len(self._active_tasks)} active tasks to finish...")
            tasks = list(self._active_tasks.values())
            done, pending = await asyncio.wait(tasks, timeout=10)
            for task in pending:
                task.cancel()

        self._active_tasks.clear()
        logger.info("QueueWorker stopped")

    async def _poll_loop(self):
        """Main polling loop - checks for pending items and dispatches processing."""
        while self._running:
            try:
                await self._poll_and_dispatch()
            except Exception as e:
                logger.error(f"Error in queue worker poll loop: {e}", exc_info=True)

            # Sleep between polls
            await asyncio.sleep(self.poll_interval)

    async def _poll_and_dispatch(self):
        """Poll for pending items and dispatch processing tasks.

        V060-HLT-003: Before spawning a processing task for a (tenant, agent)
        pair, peek at the next pending item's channel/instance and consult
        ChannelHealthService.is_circuit_open(). If the circuit is still OPEN
        we DO NOT claim/dispatch — we leave the item pending and poll again
        next tick. This prevents the infinite re-queue loop where router.py's
        CB gate re-enqueued every drained item while CB stayed OPEN.
        """
        db = self.SessionLocal()
        try:
            from services.message_queue_service import MessageQueueService
            service = MessageQueueService(db)

            # Also periodically reset stale items
            service.reset_stale(threshold_seconds=300)

            # Get all (tenant_id, agent_id) pairs with pending items
            pending_agents = service.get_pending_agents()

            for tenant_id, agent_id in pending_agents:
                task_key = (tenant_id, agent_id)

                # Skip if there's already an active task for this agent
                if task_key in self._active_tasks:
                    task = self._active_tasks[task_key]
                    if not task.done():
                        continue
                    else:
                        # Clean up completed task
                        del self._active_tasks[task_key]

                # V060-HLT-003: Peek at the next pending item for this agent
                # and check its channel CB. Defer dispatch if OPEN.
                if self._should_defer_for_circuit_breaker(db, tenant_id, agent_id):
                    continue

                # Create a new processing task for this agent
                task = asyncio.create_task(
                    self._process_agent_queue(tenant_id, agent_id)
                )
                self._active_tasks[task_key] = task

        finally:
            db.close()

    def _should_defer_for_circuit_breaker(self, db: Session, tenant_id: str, agent_id: int) -> bool:
        """V060-HLT-003: Return True when the next pending item's channel CB
        is OPEN — in that case we skip dispatch this tick and let the item
        remain queued. Returns False on any lookup failure (fail-open so
        legitimate traffic isn't held hostage by a bug in this gate)."""
        try:
            from models import MessageQueue, WhatsAppMCPInstance, TelegramBotInstance, Agent
            from services.channel_health_service import ChannelHealthService

            chs = ChannelHealthService.get_instance()
            if chs is None:
                return False

            # Peek at the highest-priority oldest pending item for this pair.
            item = (
                db.query(MessageQueue)
                .filter(
                    MessageQueue.tenant_id == tenant_id,
                    MessageQueue.agent_id == agent_id,
                    MessageQueue.status == "pending",
                )
                .order_by(MessageQueue.priority.desc(), MessageQueue.id.asc())
                .first()
            )
            if not item:
                return False

            channel = item.channel
            # Playground/api channels are in-process — no external CB applies.
            if channel not in ("whatsapp", "telegram"):
                return False

            # Resolve the instance_id for the CB key.
            instance_id: Optional[int] = None
            payload = item.payload or {}
            if channel == "whatsapp":
                instance_id = payload.get("mcp_instance_id")
                if not instance_id:
                    # Fall back to the agent's linked MCP instance
                    agent = db.query(Agent).filter(Agent.id == agent_id).first()
                    if agent:
                        linked = (
                            db.query(WhatsAppMCPInstance)
                            .filter(WhatsAppMCPInstance.tenant_id == tenant_id)
                            .first()
                        )
                        if linked:
                            instance_id = linked.id
            elif channel == "telegram":
                instance_id = payload.get("instance_id") or payload.get("telegram_instance_id")

            if not instance_id:
                return False  # Can't identify instance → don't block dispatch

            if chs.is_circuit_open(channel, instance_id):
                logger.info(
                    f"[V060-HLT-003] Deferring dispatch: CB OPEN for {channel}/{instance_id} "
                    f"(tenant={tenant_id}, agent={agent_id}, pending_item={item.id})"
                )
                return True
            return False
        except Exception as e:
            logger.debug(f"_should_defer_for_circuit_breaker: lookup failed, not deferring: {e}")
            return False

    async def _process_agent_queue(self, tenant_id: str, agent_id: int):
        """
        Process all pending items for a specific (tenant_id, agent_id) pair sequentially.
        """
        while self._running:
            db = self.SessionLocal()
            try:
                from services.message_queue_service import MessageQueueService
                service = MessageQueueService(db)

                # Claim next item
                item = service.claim_next(tenant_id, agent_id)
                if not item:
                    break  # No more pending items for this agent

                queue_id = item.id
                channel = item.channel
                payload = item.payload

                logger.info(
                    f"Processing queue item {queue_id} "
                    f"(channel={channel}, tenant={tenant_id}, agent={agent_id})"
                )

                # Send WebSocket notification that processing has started
                try:
                    await self._notify_processing_started(queue_id, channel, payload)
                except Exception as e:
                    logger.warning(f"Failed to send processing_started WebSocket notification: {e}")

                try:
                    result = None
                    if channel == "playground":
                        result = await self._process_playground_message(db, item)
                    elif channel == "whatsapp":
                        await self._process_whatsapp_message(db, item)
                    elif channel == "telegram":
                        await self._process_telegram_message(db, item)
                    elif channel == "api":
                        result = await self._process_api_message(db, item)
                    elif channel == "slack":
                        # V060-CHN-002
                        await self._process_slack_message(db, item)
                    elif channel == "discord":
                        # V060-CHN-002
                        await self._process_discord_message(db, item)
                    else:
                        raise ValueError(f"Unknown channel: {channel}")

                    # Mark as completed, persisting result for poll retrieval
                    service.mark_completed(queue_id, result=result)

                except Exception as e:
                    error_msg = f"{type(e).__name__}: {str(e)}\n{traceback.format_exc()}"
                    logger.error(f"Error processing queue item {queue_id}: {error_msg}")
                    service.mark_failed(queue_id, str(e))

            except Exception as e:
                logger.error(f"Error in agent queue processing loop: {e}", exc_info=True)
                break
            finally:
                db.close()

    async def _notify_processing_started(self, queue_id: int, channel: str, payload: dict):
        """Send WebSocket notification that a queued message is being processed."""
        if channel == "playground":
            user_id = payload.get("user_id")
            if user_id:
                from websocket_manager import manager as ws_manager
                await ws_manager.send_to_user(user_id, {
                    "type": "queue_processing_started",
                    "queue_id": queue_id,
                })

    async def _process_playground_message(self, db: Session, item):
        """Process a playground message from the queue. Returns result dict."""
        from services.playground_service import PlaygroundService

        payload = item.payload
        user_id = payload.get("user_id")
        message = payload.get("message", "")
        thread_id = payload.get("thread_id")
        media_type = payload.get("media_type")

        service = PlaygroundService(db)
        result = await service.send_message(
            user_id=user_id,
            agent_id=item.agent_id,
            message_text=message,
            thread_id=thread_id,
            media_type=media_type,
        )

        result_payload = {
            "status": result.get("status"),
            "message": result.get("message"),
            "agent_name": result.get("agent_name"),
            "timestamp": result.get("timestamp"),
            "thread_renamed": result.get("thread_renamed"),
            "new_thread_title": result.get("new_thread_title"),
            "kb_used": result.get("kb_used"),
        }

        # Send result via WebSocket to the user
        if user_id:
            from websocket_manager import manager as ws_manager
            await ws_manager.send_to_user(user_id, {
                "type": "queue_message_completed",
                "queue_id": item.id,
                "result": result_payload,
            })

        if result.get("status") == "error":
            raise Exception(result.get("error", "Unknown playground error"))

        return result_payload

    async def _process_whatsapp_message(self, db: Session, item):
        """Process a WhatsApp message from the queue."""
        from models import Config, WhatsAppMCPInstance
        from agent.router import AgentRouter
        from agent.contact_service_cached import CachedContactService
        import json as json_lib

        payload = item.payload
        message = payload.get("message", {})

        # Get config
        config = db.query(Config).first()
        if not config:
            raise Exception("No config found for WhatsApp processing")

        contact_mappings = json_lib.loads(config.contact_mappings) if config.contact_mappings else {}

        config_dict = {
            "model_provider": config.model_provider,
            "model_name": config.model_name,
            "system_prompt": config.system_prompt,
            "memory_size": config.memory_size,
            "contact_mappings": contact_mappings,
            "maintenance_mode": config.maintenance_mode,
            "maintenance_message": config.maintenance_message,
            "context_message_count": config.context_message_count,
            "context_char_limit": config.context_char_limit,
            "enable_semantic_search": getattr(config, "enable_semantic_search", False),
            "semantic_search_results": getattr(config, "semantic_search_results", 5),
            "semantic_similarity_threshold": getattr(config, "semantic_similarity_threshold", 0.3),
        }

        # Find MCP instance for this agent
        mcp_instance_id = payload.get("mcp_instance_id")

        agent_router = AgentRouter(
            db, config_dict, mcp_reader=None, mcp_instance_id=mcp_instance_id,
            tenant_id=item.tenant_id,  # V060-CHN-006
        )
        await agent_router.route_message(message, "queue")

    async def _process_telegram_message(self, db: Session, item):
        """Process a Telegram message from the queue."""
        from models import Config, Agent, TelegramBotInstance
        from agent.router import AgentRouter
        import json as json_lib

        payload = item.payload
        message = payload.get("update", {})
        instance_id = payload.get("instance_id")

        # Get config
        config = db.query(Config).first()
        if not config:
            raise Exception("No config found for Telegram processing")

        contact_mappings = json_lib.loads(config.contact_mappings) if config.contact_mappings else {}

        config_dict = {
            "model_provider": config.model_provider,
            "model_name": config.model_name,
            "system_prompt": config.system_prompt,
            "memory_size": config.memory_size,
            "contact_mappings": contact_mappings,
            "maintenance_mode": config.maintenance_mode,
            "maintenance_message": config.maintenance_message,
            "context_message_count": config.context_message_count,
            "context_char_limit": config.context_char_limit,
            "enable_semantic_search": getattr(config, "enable_semantic_search", False),
            "semantic_search_results": getattr(config, "semantic_search_results", 5),
            "semantic_similarity_threshold": getattr(config, "semantic_similarity_threshold", 0.3),
        }

        agent_router = AgentRouter(
            db, config_dict, mcp_reader=None, telegram_instance_id=instance_id,
            tenant_id=item.tenant_id,  # V060-CHN-006
        )
        await agent_router.route_message(message, "queue")

    async def _process_slack_message(self, db: Session, item):
        """V060-CHN-002: Process a queued inbound Slack event through AgentRouter."""
        from models import Config
        from agent.router import AgentRouter
        import json as json_lib

        payload = item.payload or {}
        event = payload.get("event", {})
        slack_integration_id = payload.get("slack_integration_id")

        config = db.query(Config).first()
        if not config:
            raise Exception("No config found for Slack processing")

        contact_mappings = json_lib.loads(config.contact_mappings) if config.contact_mappings else {}
        config_dict = {
            "model_provider": config.model_provider,
            "model_name": config.model_name,
            "system_prompt": config.system_prompt,
            "memory_size": config.memory_size,
            "contact_mappings": contact_mappings,
            "maintenance_mode": config.maintenance_mode,
            "maintenance_message": config.maintenance_message,
            "context_message_count": config.context_message_count,
            "context_char_limit": config.context_char_limit,
            "enable_semantic_search": getattr(config, "enable_semantic_search", False),
            "semantic_search_results": getattr(config, "semantic_search_results", 5),
            "semantic_similarity_threshold": getattr(config, "semantic_similarity_threshold", 0.3),
        }

        # Normalize Slack event into router message envelope
        message = {
            "channel": "slack",
            "sender": f"{payload.get('team_id', '')}:{event.get('user', '')}",
            "sender_name": event.get("user", ""),
            "body": event.get("text", ""),
            "to": event.get("channel"),  # Slack channel ID to reply to
            "thread_ts": event.get("thread_ts") or event.get("ts"),
            "tenant_id": item.tenant_id,
            "agent_id": item.agent_id,
            "slack_integration_id": slack_integration_id,
        }

        agent_router = AgentRouter(
            db, config_dict, mcp_reader=None,
            tenant_id=item.tenant_id,
            slack_integration_id=slack_integration_id,
        )
        await agent_router.route_message(message, "queue")

    async def _process_discord_message(self, db: Session, item):
        """V060-CHN-002: Process a queued inbound Discord interaction through AgentRouter."""
        from models import Config
        from agent.router import AgentRouter
        import json as json_lib

        payload = item.payload or {}
        interaction = payload.get("interaction", {})
        discord_integration_id = payload.get("discord_integration_id")

        config = db.query(Config).first()
        if not config:
            raise Exception("No config found for Discord processing")

        contact_mappings = json_lib.loads(config.contact_mappings) if config.contact_mappings else {}
        config_dict = {
            "model_provider": config.model_provider,
            "model_name": config.model_name,
            "system_prompt": config.system_prompt,
            "memory_size": config.memory_size,
            "contact_mappings": contact_mappings,
            "maintenance_mode": config.maintenance_mode,
            "maintenance_message": config.maintenance_message,
            "context_message_count": config.context_message_count,
            "context_char_limit": config.context_char_limit,
            "enable_semantic_search": getattr(config, "enable_semantic_search", False),
            "semantic_search_results": getattr(config, "semantic_search_results", 5),
            "semantic_similarity_threshold": getattr(config, "semantic_similarity_threshold", 0.3),
        }

        user = (interaction.get("member") or {}).get("user") or interaction.get("user") or {}
        data = interaction.get("data") or {}
        # Pull slash-command text or options
        command_text = data.get("name", "") or ""
        for opt in data.get("options") or []:
            if opt.get("type") == 3 and opt.get("value"):  # STRING option
                command_text += f" {opt.get('value')}"

        message = {
            "channel": "discord",
            "sender": f"discord:{user.get('id', '')}",
            "sender_name": user.get("username", ""),
            "body": command_text.strip(),
            "to": interaction.get("channel_id"),
            "tenant_id": item.tenant_id,
            "agent_id": item.agent_id,
            "discord_integration_id": discord_integration_id,
        }

        agent_router = AgentRouter(
            db, config_dict, mcp_reader=None,
            tenant_id=item.tenant_id,
            discord_integration_id=discord_integration_id,
        )
        await agent_router.route_message(message, "queue")

    async def _process_api_message(self, db: Session, item):
        """
        Process an API channel message from the queue. Returns result dict.
        Similar to playground processing but does NOT send WebSocket notifications.
        The result is persisted in the queue item payload for polling.
        """
        from services.playground_service import PlaygroundService
        from services.playground_thread_service import PlaygroundThreadService

        payload = item.payload
        user_id = payload.get("user_id", 0)
        message = payload.get("message", "")
        thread_id = payload.get("thread_id")

        # Auto-create thread if not specified
        if not thread_id:
            thread_service = PlaygroundThreadService(db)
            thread_data = await thread_service.create_thread(
                tenant_id=item.tenant_id,
                user_id=user_id,
                agent_id=item.agent_id,
                title=message[:50] + "..." if len(message) > 50 else message,
            )
            thread_obj = thread_data.get("thread", {})
            thread_id = thread_obj.get("id") if thread_obj else None

        service = PlaygroundService(db)
        result = await service.send_message(
            user_id=user_id,
            agent_id=item.agent_id,
            message_text=message,
            thread_id=thread_id,
            tenant_id=item.tenant_id,
        )

        if result.get("status") == "error":
            raise Exception(result.get("error", "Unknown API processing error"))

        return {
            "status": result.get("status", "success"),
            "message": result.get("message") or result.get("answer"),
            "agent_name": result.get("agent_name"),
            "thread_id": thread_id,
            "timestamp": result.get("timestamp"),
            "kb_used": result.get("kb_used"),
        }

    @property
    def is_running(self) -> bool:
        """Check if worker is currently running."""
        return self._running


# Global worker instance (singleton)
_worker_instance: Optional[QueueWorker] = None


def get_queue_worker() -> Optional[QueueWorker]:
    """Get the global queue worker instance."""
    return _worker_instance


async def start_queue_worker(engine: Engine, poll_interval_ms: int = 500):
    """Start the global queue worker."""
    global _worker_instance
    if _worker_instance and _worker_instance.is_running:
        logger.warning("QueueWorker already running")
        return _worker_instance

    _worker_instance = QueueWorker(engine, poll_interval_ms=poll_interval_ms)
    await _worker_instance.start()
    return _worker_instance


async def stop_queue_worker():
    """Stop the global queue worker."""
    global _worker_instance
    if _worker_instance:
        await _worker_instance.stop()
        _worker_instance = None
