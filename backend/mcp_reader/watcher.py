import asyncio
import logging
from typing import Callable, Union
from .sqlite_reader import MCPDatabaseReader
from .api_reader import MCPAPIReader
from .filters import MessageFilter

class MCPWatcher:
    def __init__(
        self,
        db_path: str = None,
        message_filter: MessageFilter = None,
        on_message_callback: Callable = None,
        poll_interval_ms: int = 3000,
        contact_mappings: dict = None,
        db_session = None,  # SQLAlchemy session for checking message_cache
        starting_timestamp: str = None,  # Optional: skip messages older than this (prevents replay on new instances)
        reader: Union[MCPDatabaseReader, MCPAPIReader] = None,  # Optional: pass reader directly
        whatsapp_conversation_delay_seconds: float = 5.0
    ):
        # Use provided reader or create SQLite reader from db_path
        if reader is not None:
            self.reader = reader
        elif db_path is not None:
            self.reader = MCPDatabaseReader(db_path, contact_mappings=contact_mappings)
        else:
            raise ValueError("Either reader or db_path must be provided")

        self.filter = message_filter
        self.on_message_callback = on_message_callback
        self.poll_interval = poll_interval_ms / 1000.0
        self.last_timestamp = "1970-01-01 00:00:00"
        self.starting_timestamp = starting_timestamp  # Minimum timestamp to process (for new instances)
        self.running = False
        self.paused = False  # Bug Fix 2026-01-06: Add pause capability
        self.logger = logging.getLogger(__name__)
        self.processed_message_ids = set()  # Track processed message IDs to prevent duplicates
        self.db_session = db_session  # For checking message_cache
        self.whatsapp_conversation_delay_seconds = max(0.0, whatsapp_conversation_delay_seconds or 0.0)
        self._conversation_delay_buffers = {}
        self._conversation_delay_tasks = {}

    async def start(self):
        """Start the polling loop"""
        self.running = True

        # Initial timestamp retrieval with infinite retry
        # This prevents the watcher from starting if the DB is locked/unavailable,
        # avoiding the default to 1970 and subsequent message flood.
        while self.running:
            try:
                db_timestamp = self.reader.get_latest_timestamp()

                # If starting_timestamp is provided (new instance), use it to prevent message replay
                # This ensures we only process messages received AFTER the instance was created
                if self.starting_timestamp:
                    # Use the later of: db_timestamp or starting_timestamp
                    if self.starting_timestamp > db_timestamp:
                        self.last_timestamp = self.starting_timestamp
                        self.logger.info(f"🆕 NEW INSTANCE: Starting from instance creation time {self.starting_timestamp} (skipping older messages)")
                    else:
                        self.last_timestamp = db_timestamp
                        self.logger.info(f"Starting MCP watcher from DB timestamp {self.last_timestamp}")
                else:
                    self.last_timestamp = db_timestamp
                    self.logger.info(f"Starting MCP watcher from timestamp {self.last_timestamp}")
                break
            except Exception as e:
                self.logger.warning(f"Waiting for MCP database... ({e})")
                await asyncio.sleep(5)  # Wait 5s before retrying

        # Main polling loop
        print(f"🔄 Watcher polling loop started (interval={self.poll_interval}s, last_ts={self.last_timestamp})")
        poll_count = 0
        while self.running:
            try:
                poll_count += 1
                if poll_count <= 3 or poll_count % 100 == 0:
                    self.logger.debug(f"Poll #{poll_count} (last_ts={self.last_timestamp})")
                await self._poll_messages()
                await asyncio.sleep(self.poll_interval)
            except Exception as e:
                self.logger.error(f"Error in polling loop: {e}", exc_info=True)
                await asyncio.sleep(self.poll_interval)

    async def _poll_messages(self):
        """Poll for new messages and process them concurrently (Phase 6.11.1)"""
        # Bug Fix 2026-01-06: Skip processing if paused
        if self.paused:
            self.logger.debug("Watcher is paused - skipping message processing")
            return

        messages = self.reader.get_new_messages(self.last_timestamp)

        if messages:
            self.logger.info(f"Found {len(messages)} new messages since {self.last_timestamp}")

            # Collect messages to process
            # CRITICAL FIX 2026-01-18: Separate conversation and normal messages
            # Conversation messages must be processed SEQUENTIALLY to prevent race conditions
            conversation_messages = []
            normal_tasks = []

            for msg in messages:
                # Skip if already processed (in-memory check)
                if msg['id'] in self.processed_message_ids:
                    continue

                # Skip if already in database message_cache (persistent check)
                # CRITICAL: This prevents message replay after MCP container restarts
                if self.db_session:
                    try:
                        from models import MessageCache
                        # Force a fresh query by expunging all cached objects
                        self.db_session.expire_all()

                        existing = self.db_session.query(MessageCache).filter_by(source_id=msg['id']).first()
                        if existing:
                            self.processed_message_ids.add(msg['id'])
                            if msg["timestamp"] >= self.last_timestamp:
                                from datetime import datetime, timedelta
                                try:
                                    ts = datetime.fromisoformat(msg["timestamp"].replace("+00:00", ""))
                                    ts += timedelta(microseconds=1)
                                    self.last_timestamp = ts.strftime("%Y-%m-%d %H:%M:%S") + "+00:00"
                                except:
                                    pass
                            continue
                    except Exception as e:
                        self.logger.error(f"Error checking message_cache for {msg['id']}: {e}", exc_info=True)
                        self.logger.warning(f"[SAFETY SKIP] Skipping message {msg['id']} due to cache check error")
                        continue

                # Check if message should trigger
                trigger_type = self.filter.should_trigger(msg)
                if trigger_type:
                    self.logger.info(f"Message {msg['id']} from {msg.get('sender','?')} matched filter: {trigger_type}")
                    # Separate conversation messages from normal messages
                    if trigger_type == "conversation":
                        conversation_messages.append((msg, trigger_type))
                    else:
                        # Add to task list for concurrent processing
                        normal_tasks.append(self._process_message_task(msg, trigger_type))

                # Mark message as processed
                self.processed_message_ids.add(msg['id'])

                # Update last timestamp
                if msg["timestamp"] > self.last_timestamp:
                    self.last_timestamp = msg["timestamp"]

            # CRITICAL FIX 2026-01-18: Process conversation messages SEQUENTIALLY first
            # This prevents race conditions where rapid messages overwrite each other's history
            if conversation_messages:
                self.logger.info(f"Processing {len(conversation_messages)} conversation messages SEQUENTIALLY")
                for msg, trigger_type in conversation_messages:
                    try:
                        await self._handle_conversation_message(msg, trigger_type)
                        # Small settling delay to ensure DB state is consistent before next message
                        # This prevents history overwrites when messages arrive rapidly
                        await asyncio.sleep(0.05)  # 50ms settling time
                    except Exception as e:
                        self.logger.error(f"Error processing conversation message {msg['id']}: {e}", exc_info=True)

            # Process normal messages concurrently (no race condition risk)
            if normal_tasks:
                self.logger.info(f"Processing {len(normal_tasks)} normal messages concurrently")
                results = await asyncio.gather(*normal_tasks, return_exceptions=True)

                # Log any errors
                for i, result in enumerate(results):
                    if isinstance(result, Exception):
                        self.logger.error(f"Error processing message: {result}", exc_info=result)

    async def _process_message_task(self, msg: dict, trigger_type: str):
        """Process a single message (for concurrent execution)"""
        try:
            await self.on_message_callback(msg, trigger_type)
        except Exception as e:
            self.logger.error(f"Error in message callback for {msg['id']}: {e}", exc_info=True)
            raise  # Re-raise to be caught by gather()

    async def _handle_conversation_message(self, msg: dict, trigger_type: str):
        """Optionally debounce WhatsApp conversation messages before routing."""
        if msg.get("channel") == "whatsapp" and self.whatsapp_conversation_delay_seconds > 0:
            self._enqueue_conversation_message(msg, trigger_type)
            return

        await self.on_message_callback(msg, trigger_type)

    def _enqueue_conversation_message(self, msg: dict, trigger_type: str) -> None:
        """Buffer conversation messages and debounce processing."""
        key = f"{msg.get('channel', 'unknown')}:{msg.get('chat_id') or msg.get('sender')}"
        buffer = self._conversation_delay_buffers.setdefault(key, [])
        buffer.append(msg)

        existing_task = self._conversation_delay_tasks.get(key)
        if existing_task and not existing_task.done():
            existing_task.cancel()

        self._conversation_delay_tasks[key] = asyncio.create_task(
            self._flush_conversation_buffer(key, trigger_type)
        )

    async def _flush_conversation_buffer(self, key: str, trigger_type: str) -> None:
        """Send a single aggregated message after the debounce window."""
        try:
            await asyncio.sleep(self.whatsapp_conversation_delay_seconds)
            buffered = self._conversation_delay_buffers.pop(key, [])
            if not buffered:
                return

            buffered.sort(key=lambda item: item.get("timestamp", ""))
            combined_body = "\n".join(
                msg.get("body", "").strip() for msg in buffered if msg.get("body")
            ).strip()
            if not combined_body:
                return

            last_msg = buffered[-1]
            aggregated = dict(last_msg)
            aggregated["body"] = combined_body
            aggregated["aggregated_message_ids"] = [msg.get("id") for msg in buffered]

            await self.on_message_callback(aggregated, trigger_type)
        except asyncio.CancelledError:
            return
        except Exception as e:
            self.logger.error(f"Error flushing conversation buffer {key}: {e}", exc_info=True)

    def reload_filter(self, new_filter: MessageFilter):
        """
        Reload filter configuration without restarting watcher.
        This allows filter updates to take effect immediately.

        Args:
            new_filter: New MessageFilter instance with updated configuration
        """
        self.filter = new_filter
        self.logger.info("Filter configuration reloaded - new filters are now active")

    def pause(self):
        """Pause message processing (Bug Fix 2026-01-06)"""
        self.paused = True
        self.logger.info("Watcher paused - message processing suspended")

    def resume(self):
        """Resume message processing (Bug Fix 2026-01-06)"""
        self.paused = False
        self.logger.info("Watcher resumed - message processing active")

    def is_paused(self) -> bool:
        """Check if watcher is paused"""
        return self.paused

    def stop(self):
        """Stop the polling loop"""
        self.running = False
        for task in self._conversation_delay_tasks.values():
            if not task.done():
                task.cancel()
        self.logger.info("Stopping MCP watcher")
