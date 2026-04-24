"""
Phase 6.4: Scheduler Worker

Background worker that polls for and executes scheduled events.
Runs as a daemon thread with graceful shutdown support.
"""

import logging
import asyncio
import threading
import time
from datetime import datetime
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy.engine import Engine

from db import get_session
from scheduler.scheduler_service import SchedulerService

logger = logging.getLogger(__name__)


class SchedulerWorker:
    """Background worker for executing scheduled events."""

    def __init__(self, engine: Engine, poll_interval_seconds: int = 60):
        """
        Initialize scheduler worker.

        Args:
            engine: SQLAlchemy engine for database access
            poll_interval_seconds: How often to check for due events (default: 60s)
        """
        self.engine = engine
        self.poll_interval = poll_interval_seconds
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    def start(self):
        """Start the background worker thread."""
        if self._running:
            logger.warning("SchedulerWorker already running")
            return

        self._stop_event.clear()
        self._running = True

        self._thread = threading.Thread(
            target=self._run_loop,
            name="SchedulerWorker",
            daemon=True
        )
        self._thread.start()

        logger.info(f"SchedulerWorker started (poll interval: {self.poll_interval}s)")

    def stop(self, timeout: int = 10):
        """
        Stop the background worker thread.

        Args:
            timeout: Maximum seconds to wait for graceful shutdown
        """
        if not self._running:
            logger.warning("SchedulerWorker not running")
            return

        logger.info("Stopping SchedulerWorker...")
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

            if self._thread.is_alive():
                logger.warning(f"SchedulerWorker did not stop within {timeout}s")
            else:
                logger.info("SchedulerWorker stopped successfully")

        self._running = False

    def is_running(self) -> bool:
        """Check if worker is currently running."""
        return self._running and self._thread and self._thread.is_alive()

    def _run_loop(self):
        """Main worker loop - polls and executes events."""
        logger.info("SchedulerWorker loop started")
        iteration = 0

        while not self._stop_event.is_set():
            iteration += 1
            logger.info(f"SchedulerWorker iteration {iteration} - polling...")

            try:
                self._poll_and_execute()
                logger.info(f"SchedulerWorker iteration {iteration} - poll completed")
            except Exception as e:
                logger.error(f"Error in scheduler worker loop (iteration {iteration}): {e}", exc_info=True)

            # Sleep with interruptible wait (check stop_event every second)
            logger.info(f"SchedulerWorker sleeping for {self.poll_interval}s...")
            for i in range(self.poll_interval):
                if self._stop_event.is_set():
                    logger.info("SchedulerWorker stop event detected")
                    break
                time.sleep(1)

        logger.info("SchedulerWorker loop ended")

    def _poll_and_execute(self):
        """Poll for due events and execute them."""
        db: Optional[Session] = None
        logger.info("_poll_and_execute started")

        try:
            logger.info("Getting database session...")
            with get_session(self.engine) as db:
                logger.info("Creating SchedulerService...")
                # Phase 0.6.0: Create TokenTracker for background worker cost monitoring
                from analytics.token_tracker import TokenTracker
                token_tracker = TokenTracker(db)
                # Untenanted service just for the cross-tenant due-events poll.
                # Per-event execution uses a freshly-constructed service scoped
                # to event.tenant_id so ContactService lookups are tenant-safe
                # (V060-CHN-006 follow-up).
                poll_service = SchedulerService(db, token_tracker=token_tracker)

                # Get events that are due for execution
                logger.info("Querying for due events...")
                due_events = poll_service.get_due_events()
                logger.info(f"Query returned {len(due_events) if due_events else 0} events")

                if not due_events:
                    logger.info("No events due for execution")
                else:
                    logger.info(f"Found {len(due_events)} event(s) due for execution")

                    # Execute each event with a tenant-scoped SchedulerService
                    for event in due_events:
                        try:
                            logger.info(f"Executing event {event.id} ({event.event_type})")
                            event_service = SchedulerService(
                                db,
                                token_tracker=token_tracker,
                                tenant_id=getattr(event, "tenant_id", None),
                            )
                            event_service.execute_event(event)
                            logger.info(f"Successfully executed event {event.id}")

                        except Exception as e:
                            logger.error(
                                f"Failed to execute event {event.id}: {e}",
                                exc_info=True
                            )
                            # Error is already logged to event.error_message by execute_event

                try:
                    from channels.schedule.trigger import ScheduleTrigger

                    schedule_results = ScheduleTrigger.poll_due(db)
                    logger.info(
                        "Schedule trigger poll completed with %s due trigger(s)",
                        len(schedule_results),
                    )
                except Exception as e:
                    logger.error(f"Failed to poll schedule triggers: {e}", exc_info=True)

                try:
                    from channels.email.trigger import EmailTrigger

                    email_results = asyncio.run(EmailTrigger.poll_active(db))
                    logger.info(
                        "Email trigger poll completed with %s active trigger(s)",
                        len(email_results),
                    )
                except Exception as e:
                    logger.error(f"Failed to poll email triggers: {e}", exc_info=True)

                try:
                    from channels.jira.trigger import JiraTrigger

                    jira_results = asyncio.run(JiraTrigger.poll_active(db))
                    logger.info(
                        "Jira trigger poll completed with %s active trigger(s)",
                        len(jira_results),
                    )
                except Exception as e:
                    logger.error(f"Failed to poll Jira triggers: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in poll_and_execute: {e}", exc_info=True)

    def force_poll(self):
        """
        Force an immediate poll (for testing/manual triggers).
        Does not interrupt the regular polling schedule.
        """
        if not self._running:
            logger.warning("Cannot force poll - worker not running")
            return

        logger.info("Forcing immediate poll...")

        try:
            self._poll_and_execute()
        except Exception as e:
            logger.error(f"Error in force_poll: {e}", exc_info=True)


# Global worker instance (singleton pattern)
_worker_instance: Optional[SchedulerWorker] = None


def get_scheduler_worker(engine: Engine, poll_interval_seconds: int = 60) -> SchedulerWorker:
    """
    Get or create the global scheduler worker instance.

    Args:
        engine: SQLAlchemy engine for database access
        poll_interval_seconds: Polling interval (only used on first creation)

    Returns:
        SchedulerWorker instance
    """
    global _worker_instance

    if _worker_instance is None:
        _worker_instance = SchedulerWorker(engine, poll_interval_seconds)

    return _worker_instance


def start_scheduler_worker(engine: Engine, poll_interval_seconds: int = 60):
    """Start the global scheduler worker."""
    worker = get_scheduler_worker(engine, poll_interval_seconds)
    worker.start()


def stop_scheduler_worker(timeout: int = 10):
    """Stop the global scheduler worker."""
    if _worker_instance:
        _worker_instance.stop(timeout)
