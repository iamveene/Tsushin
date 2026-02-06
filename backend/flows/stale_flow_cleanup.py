"""
Phase 19: Stale Flow Run Cleanup Service
Automatically detects and cleans up flow runs stuck in "running" state.

This service addresses BUG-FLOWS-002 by:
1. Periodically scanning for FlowRun records in "running" status
2. Marking runs exceeding the stale threshold as "timeout"
3. Cleaning up associated FlowNodeRun records
4. Cleaning up orphaned ConversationThread records (flow type only)
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional, Dict, Any, List
from sqlalchemy.orm import Session

from models import FlowRun, FlowNodeRun, ConversationThread

logger = logging.getLogger(__name__)


class StaleFlowCleanupService:
    """Background service that detects and cleans up stale flow runs."""

    # Configuration defaults
    DEFAULT_STALE_THRESHOLD_SECONDS = 7200      # 2 hours
    DEFAULT_CHECK_INTERVAL_SECONDS = 300        # 5 minutes
    DEFAULT_CONVERSATION_STALE_SECONDS = 3600   # 1 hour for orphaned threads

    def __init__(
        self,
        get_db_session: Callable[[], Session],
        stale_threshold_seconds: int = None,
        check_interval_seconds: int = None,
        conversation_stale_seconds: int = None,
        on_cleanup_triggered: Optional[Callable[[int, str], None]] = None
    ):
        """
        Initialize stale flow cleanup service.

        Args:
            get_db_session: Factory function to get database session
            stale_threshold_seconds: Time after which running flows are considered stale
            check_interval_seconds: How often to check for stale flows
            conversation_stale_seconds: Time after which active conversation threads are stale
            on_cleanup_triggered: Optional callback (flow_run_id, reason)
        """
        self.get_db_session = get_db_session
        self.stale_threshold = stale_threshold_seconds or self.DEFAULT_STALE_THRESHOLD_SECONDS
        self.check_interval = check_interval_seconds or self.DEFAULT_CHECK_INTERVAL_SECONDS
        self.conversation_stale = conversation_stale_seconds or self.DEFAULT_CONVERSATION_STALE_SECONDS
        self.on_cleanup_triggered = on_cleanup_triggered

        self._running = False
        self._task: Optional[asyncio.Task] = None
        self._cleanup_stats: Dict[str, Any] = {
            "flows_cleaned": 0,
            "steps_cleaned": 0,
            "threads_cleaned": 0,
            "last_check": None
        }

    async def start(self):
        """Start the cleanup background task."""
        if self._running:
            logger.warning("StaleFlowCleanupService is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._cleanup_loop())
        logger.info(
            f"StaleFlowCleanupService started - "
            f"stale threshold: {self.stale_threshold}s, "
            f"check interval: {self.check_interval}s"
        )

    async def stop(self):
        """Stop the cleanup background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("StaleFlowCleanupService stopped")

    async def _cleanup_loop(self):
        """Main cleanup loop - runs continuously in background."""
        while self._running:
            try:
                await self._run_cleanup()
                self._cleanup_stats["last_check"] = datetime.utcnow().isoformat() + "Z"
            except Exception as e:
                logger.error(f"Error in stale flow cleanup loop: {e}", exc_info=True)

            await asyncio.sleep(self.check_interval)

    async def _run_cleanup(self):
        """Execute one cleanup cycle."""
        db = self.get_db_session()
        try:
            # 1. Clean up stale FlowRun records
            stale_flows = await self._cleanup_stale_flow_runs(db)

            # 2. Clean up orphaned FlowNodeRun records (running with no parent running)
            stale_steps = await self._cleanup_stale_step_runs(db)

            # 3. Clean up orphaned ConversationThread records
            stale_threads = await self._cleanup_stale_conversation_threads(db)

            # Log summary if any cleanup happened
            total = stale_flows + stale_steps + stale_threads
            if total > 0:
                logger.info(
                    f"Stale cleanup completed: "
                    f"{stale_flows} flows, {stale_steps} steps, {stale_threads} threads"
                )
        finally:
            db.close()

    async def _cleanup_stale_flow_runs(self, db: Session) -> int:
        """
        Find and mark stale flow runs as timeout.

        Returns:
            Number of flow runs cleaned up
        """
        cutoff_time = datetime.utcnow() - timedelta(seconds=self.stale_threshold)

        # Query for stale running flows
        stale_runs = db.query(FlowRun).filter(
            FlowRun.status == "running",
            FlowRun.started_at < cutoff_time
        ).all()

        cleaned = 0
        for flow_run in stale_runs:
            try:
                elapsed = (datetime.utcnow() - flow_run.started_at).total_seconds()

                logger.warning(
                    f"Cleaning up stale flow run {flow_run.id} "
                    f"(flow_def={flow_run.flow_definition_id}, "
                    f"tenant={flow_run.tenant_id}, "
                    f"running for {elapsed:.0f}s)"
                )

                # Update FlowRun status
                flow_run.status = "timeout"
                flow_run.completed_at = datetime.utcnow()
                flow_run.error_text = (
                    f"Flow run timed out after {elapsed:.0f}s "
                    f"(threshold: {self.stale_threshold}s). "
                    f"Cleaned up by StaleFlowCleanupService."
                )

                # Also mark any running steps as timeout
                running_steps = db.query(FlowNodeRun).filter(
                    FlowNodeRun.flow_run_id == flow_run.id,
                    FlowNodeRun.status == "running"
                ).all()

                for step_run in running_steps:
                    step_run.status = "timeout"
                    step_run.completed_at = datetime.utcnow()
                    step_run.error_text = "Step timed out due to flow run cleanup"

                db.commit()
                cleaned += 1
                self._cleanup_stats["flows_cleaned"] += 1
                self._cleanup_stats["steps_cleaned"] += len(running_steps)

                # Trigger callback if provided
                if self.on_cleanup_triggered:
                    self.on_cleanup_triggered(
                        flow_run.id,
                        f"Stale timeout after {elapsed:.0f}s"
                    )

            except Exception as e:
                logger.error(f"Error cleaning up flow run {flow_run.id}: {e}")
                db.rollback()

        return cleaned

    async def _cleanup_stale_step_runs(self, db: Session) -> int:
        """
        Find and mark orphaned step runs (running but flow completed/failed).

        Returns:
            Number of step runs cleaned up
        """
        # Find step runs that are "running" but their flow_run is not "running"
        orphaned_steps = db.query(FlowNodeRun).join(FlowRun).filter(
            FlowNodeRun.status == "running",
            FlowRun.status.notin_(["running", "pending"])
        ).all()

        cleaned = 0
        for step_run in orphaned_steps:
            try:
                logger.warning(
                    f"Cleaning up orphaned step run {step_run.id} "
                    f"(flow_run={step_run.flow_run_id}, flow_status={step_run.run.status})"
                )

                step_run.status = "failed"
                step_run.completed_at = datetime.utcnow()
                step_run.error_text = (
                    f"Step orphaned - flow run {step_run.flow_run_id} "
                    f"already has status '{step_run.run.status}'"
                )

                db.commit()
                cleaned += 1
                self._cleanup_stats["steps_cleaned"] += 1

            except Exception as e:
                logger.error(f"Error cleaning up step run {step_run.id}: {e}")
                db.rollback()

        return cleaned

    async def _cleanup_stale_conversation_threads(self, db: Session) -> int:
        """
        Find and mark stale conversation threads (active for too long).
        Only cleans up FLOW threads, not PLAYGROUND threads.

        Returns:
            Number of threads cleaned up
        """
        cutoff_time = datetime.utcnow() - timedelta(seconds=self.conversation_stale)

        # Find stale active threads (only flow type)
        stale_threads = db.query(ConversationThread).filter(
            ConversationThread.status == "active",
            ConversationThread.thread_type == "flow",  # Only flow threads
            ConversationThread.last_activity_at < cutoff_time
        ).all()

        cleaned = 0
        for thread in stale_threads:
            try:
                elapsed = (datetime.utcnow() - thread.last_activity_at).total_seconds()

                logger.warning(
                    f"Cleaning up stale conversation thread {thread.id} "
                    f"(recipient={thread.recipient}, "
                    f"step_run={thread.flow_step_run_id}, "
                    f"inactive for {elapsed:.0f}s)"
                )

                thread.status = "timeout"
                thread.completed_at = datetime.utcnow()

                db.commit()
                cleaned += 1
                self._cleanup_stats["threads_cleaned"] += 1

            except Exception as e:
                logger.error(f"Error cleaning up thread {thread.id}: {e}")
                db.rollback()

        return cleaned

    def get_stats(self) -> Dict[str, Any]:
        """Get cleanup statistics."""
        return {
            **self._cleanup_stats,
            "stale_threshold_seconds": self.stale_threshold,
            "check_interval_seconds": self.check_interval,
            "conversation_stale_seconds": self.conversation_stale,
            "running": self._running
        }


# Global instance (singleton pattern)
_cleanup_service: Optional[StaleFlowCleanupService] = None


def get_stale_flow_cleanup_service(
    get_db_session: Callable[[], Session],
    **kwargs
) -> StaleFlowCleanupService:
    """Get or create the global stale flow cleanup service."""
    global _cleanup_service

    if _cleanup_service is None:
        _cleanup_service = StaleFlowCleanupService(get_db_session, **kwargs)

    return _cleanup_service


async def start_stale_flow_cleanup(
    get_db_session: Callable[[], Session],
    stale_threshold_seconds: int = None,
    check_interval_seconds: int = None,
    conversation_stale_seconds: int = None
):
    """Start the global stale flow cleanup service."""
    service = get_stale_flow_cleanup_service(
        get_db_session,
        stale_threshold_seconds=stale_threshold_seconds,
        check_interval_seconds=check_interval_seconds,
        conversation_stale_seconds=conversation_stale_seconds
    )
    await service.start()


async def stop_stale_flow_cleanup():
    """Stop the global stale flow cleanup service."""
    if _cleanup_service:
        await _cleanup_service.stop()
