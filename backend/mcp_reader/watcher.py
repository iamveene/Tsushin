import asyncio
import logging
from datetime import datetime, timedelta, timezone
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
        whatsapp_conversation_delay_seconds: float = 5.0,
        max_catchup_seconds: int = 300  # Max backlog window on startup (default 5 min)
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
        self.max_catchup_seconds = max_catchup_seconds
        self.whatsapp_conversation_delay_seconds = max(0.0, whatsapp_conversation_delay_seconds or 0.0)
        self._conversation_delay_buffers = {}
        self._conversation_delay_tasks = {}

    def _get_conversation_delay(self, msg: dict, trigger_type: str) -> float:
        """
        Return the effective debounce window for a message.

        WhatsApp DMs should feel responsive, so we cap the debounce there to a
        short window while keeping the configured aggregation behavior for
        groups/conversation-heavy channels.
        """
        if trigger_type != "conversation":
            return 0.0

        delay = self.whatsapp_conversation_delay_seconds
        if msg.get("channel") == "whatsapp" and not bool(msg.get("is_group", 0)):
            return min(delay, 1.0)

        return delay

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

                # Cap the catchup window to prevent replaying hours of backlog
                # after a container rebuild. Messages older than the window are
                # skipped — they were either already answered or are too stale.
                if self.max_catchup_seconds > 0:
                    catchup_floor = (datetime.now(timezone.utc) - timedelta(seconds=self.max_catchup_seconds))
                    catchup_floor_str = catchup_floor.strftime("%Y-%m-%d %H:%M:%S") + "+00:00"
                    if self.last_timestamp < catchup_floor_str:
                        self.logger.warning(
                            f"⏩ Catchup cap: last_ts={self.last_timestamp} is older than "
                            f"{self.max_catchup_seconds}s window. Advancing to {catchup_floor_str} "
                            f"to avoid replaying stale messages."
                        )
                        self.last_timestamp = catchup_floor_str

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
        """Poll for new messages and dispatch them with per-chat ordering.

        Cursor advancement is deferred until after dispatch so a crash or
        retry in the middle of an audio burst cannot silently lose messages:
        on the next poll, anything not yet successfully handled is still
        ``> last_timestamp`` and gets re-fetched. Within a single burst from
        one chat (the common case for back-to-back voice notes) messages are
        processed strictly in send order so transcripts come back in order.
        """
        # Bug Fix 2026-01-06: Skip processing if paused
        if self.paused:
            self.logger.debug("Watcher is paused - skipping message processing")
            return

        messages = self.reader.get_new_messages(self.last_timestamp)
        if not messages:
            return

        self.logger.info(f"Found {len(messages)} new messages since {self.last_timestamp}")

        conversation_messages: list[tuple[dict, str]] = []
        normal_messages: list[tuple[dict, str]] = []
        # All triggered (msg_id, ts) pairs — used post-dispatch to find the
        # earliest unprocessed message, so the cursor stops just before it.
        triggered: list[tuple[str, str]] = []
        # Highest timestamp encountered in this batch — the natural ceiling
        # for cursor advancement when nothing is left pending.
        seen_max_ts = self.last_timestamp

        for msg in messages:
            msg_id = msg.get("id")
            msg_ts = msg.get("timestamp", "")

            # Skip if already processed (in-memory check) — safe to advance.
            if msg_id in self.processed_message_ids:
                if msg_ts > seen_max_ts:
                    seen_max_ts = msg_ts
                continue

            # Skip if already in database message_cache (persistent check) —
            # this is what prevents replay after MCP container restarts wipe
            # the in-memory set.
            if self.db_session:
                try:
                    from models import MessageCache
                    # Force a fresh query by expunging all cached objects
                    self.db_session.expire_all()

                    existing = self.db_session.query(MessageCache).filter_by(source_id=msg_id).first()
                    if existing:
                        self.processed_message_ids.add(msg_id)
                        if msg_ts > seen_max_ts:
                            seen_max_ts = msg_ts
                        continue
                except Exception as e:
                    self.logger.error(f"Error checking message_cache for {msg_id}: {e}", exc_info=True)
                    # Recover session only from PendingRollbackError (poisoned by earlier failed flush)
                    from sqlalchemy.exc import InvalidRequestError
                    if isinstance(e, InvalidRequestError):
                        try:
                            self.db_session.rollback()
                            self.logger.info(f"[SESSION RECOVERY] Rolled back poisoned session after {msg_id}")
                        except Exception:
                            pass
                    # Don't advance the cursor past a message whose state we
                    # couldn't determine — leave it for the next poll.
                    self.logger.warning(f"[SAFETY SKIP] Skipping message {msg_id} due to cache check error")
                    continue

            trigger_type = self.filter.should_trigger(msg)
            if trigger_type:
                self.logger.info(
                    f"Message {msg_id} from {msg.get('sender','?')} matched filter: {trigger_type}"
                )
                if trigger_type == "conversation":
                    conversation_messages.append((msg, trigger_type))
                else:
                    normal_messages.append((msg, trigger_type))
                triggered.append((msg_id, msg_ts))
                if msg_ts > seen_max_ts:
                    seen_max_ts = msg_ts
            else:
                # Filter miss: no work to do — remember we've seen it so we
                # don't refetch on the next poll.
                self.processed_message_ids.add(msg_id)
                if msg_ts > seen_max_ts:
                    seen_max_ts = msg_ts

        # CRITICAL FIX 2026-01-18: Conversation messages are processed
        # SEQUENTIALLY to prevent race conditions where rapid messages
        # overwrite each other's history.
        if conversation_messages:
            self.logger.info(f"Processing {len(conversation_messages)} conversation messages SEQUENTIALLY")
            for msg, trigger_type in conversation_messages:
                msg_id = msg.get("id")
                try:
                    await self._handle_conversation_message(msg, trigger_type)
                    self.processed_message_ids.add(msg_id)
                    # Settling delay (mirrors prior behavior)
                    await asyncio.sleep(0.05)
                except Exception as e:
                    self.logger.error(f"Error processing conversation message {msg_id}: {e}", exc_info=True)
                    # Cursor advancement is deferred — failure stays retriable.

        # Normal messages: per-chat FIFO. Audios from the same chat must be
        # transcribed in send order, otherwise transcripts come back out of
        # order or ASR rate-limits when N concurrent calls land on the same
        # Whisper instance. Different chats still process in parallel.
        if normal_messages:
            by_chat: dict[str, list[tuple[dict, str]]] = {}
            for msg, trigger_type in normal_messages:
                key = f"{msg.get('channel', 'unknown')}:{msg.get('chat_id') or msg.get('sender')}"
                by_chat.setdefault(key, []).append((msg, trigger_type))
            for items in by_chat.values():
                items.sort(key=lambda mt: mt[0].get("timestamp", ""))

            self.logger.info(
                f"Processing {len(normal_messages)} normal messages across "
                f"{len(by_chat)} chat(s): sequential per chat, parallel across chats"
            )

            async def _drain_chat(items: list[tuple[dict, str]]) -> None:
                for msg, trigger_type in items:
                    msg_id = msg.get("id")
                    try:
                        await self._process_message_task(msg, trigger_type)
                        self.processed_message_ids.add(msg_id)
                        await asyncio.sleep(0.05)  # 50ms settling time
                    except Exception as e:
                        self.logger.error(
                            f"Error processing normal message {msg_id}: {e}",
                            exc_info=True,
                        )
                        # Stop draining this chat so later messages don't
                        # jump the queue while the earlier one is unresolved.
                        return

            await asyncio.gather(
                *[_drain_chat(items) for items in by_chat.values()],
                return_exceptions=True,
            )

        # Cursor advancement: land just before the earliest still-unprocessed
        # triggered message; if everything succeeded, advance to a second
        # before ``seen_max_ts``.
        #
        # Why the 1-second rollback: WhatsApp delivers ``timestamp`` at
        # second granularity, and the reader filters with ``timestamp >
        # last_timestamp``. If a burst lands 3-6 audios in the same second
        # and the watcher only sees the first one in a poll (the rest are
        # still being written by the MCP), advancing to that second would
        # silently skip the same-second siblings on the next poll. Rolling
        # back by 1s makes the next poll re-fetch any same-second tail;
        # ``processed_message_ids`` (in-memory) and the DB ``message_cache``
        # check filter the already-handled rows so no work is repeated.
        from datetime import datetime, timedelta

        def _rollback_one_second(ts: str) -> str:
            try:
                dt = datetime.fromisoformat(ts.replace("+00:00", ""))
                dt -= timedelta(seconds=1)
                return dt.strftime("%Y-%m-%d %H:%M:%S") + "+00:00"
            except Exception:
                return self.last_timestamp

        unprocessed_ts = [
            ts for (mid, ts) in triggered if mid not in self.processed_message_ids
        ]
        if unprocessed_ts:
            earliest = min(unprocessed_ts)
            try:
                dt = datetime.fromisoformat(earliest.replace("+00:00", ""))
                dt -= timedelta(microseconds=1)
                target = dt.strftime("%Y-%m-%d %H:%M:%S") + "+00:00"
            except Exception:
                target = self.last_timestamp
        else:
            target = _rollback_one_second(seen_max_ts)

        if target > self.last_timestamp:
            self.last_timestamp = target

    async def _process_message_task(self, msg: dict, trigger_type: str):
        """Process a single message (for concurrent execution)"""
        try:
            await self.on_message_callback(msg, trigger_type)
        except Exception as e:
            self.logger.error(f"Error in message callback for {msg['id']}: {e}", exc_info=True)
            raise  # Re-raise to be caught by gather()

    async def _handle_conversation_message(self, msg: dict, trigger_type: str):
        """Optionally debounce WhatsApp conversation messages before routing.

        Media-only messages (audio/image/video/document) bypass the debounce
        window: they carry an empty ``body`` and therefore would be dropped
        silently by the buffer's ``if not combined_body: return`` guard. Each
        media message also has its own downstream side effect (e.g. an audio
        gets transcribed and delivered) that must not be aggregated away.
        """
        if (msg.get("media_type") or "").strip():
            await self.on_message_callback(msg, trigger_type)
            return

        delay = self._get_conversation_delay(msg, trigger_type)
        if delay > 0:
            self._enqueue_conversation_message(msg, trigger_type, delay)
            return

        await self.on_message_callback(msg, trigger_type)

    def _enqueue_conversation_message(self, msg: dict, trigger_type: str, delay_seconds: float) -> None:
        """Buffer conversation messages and debounce processing."""
        key = f"{msg.get('channel', 'unknown')}:{msg.get('chat_id') or msg.get('sender')}"
        buffer = self._conversation_delay_buffers.setdefault(key, [])
        buffer.append(msg)

        existing_task = self._conversation_delay_tasks.get(key)
        if existing_task and not existing_task.done():
            existing_task.cancel()

        self._conversation_delay_tasks[key] = asyncio.create_task(
            self._flush_conversation_buffer(key, trigger_type, delay_seconds)
        )

    async def _flush_conversation_buffer(self, key: str, trigger_type: str, delay_seconds: float) -> None:
        """Send a single aggregated message after the debounce window."""
        try:
            await asyncio.sleep(delay_seconds)
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
