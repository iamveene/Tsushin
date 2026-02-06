"""
MCP Health Monitor Service
Automatically monitors MCP container health and triggers recovery when needed.

This service runs in the background and:
1. Periodically checks health of all active MCP instances
2. Detects unstable connections (high reconnect attempts, keepalive failures)
3. Automatically restarts containers when health degrades
4. Pauses watchers during recovery to prevent message processing failures
5. Resumes watchers once health is restored

Root cause addressed: WhatsApp "Keepalive timed out" errors that cause message delivery failures.
"""

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Callable
from sqlalchemy.orm import Session

from models import WhatsAppMCPInstance

logger = logging.getLogger(__name__)


class MCPHealthMonitorService:
    """Background service that monitors MCP container health and triggers auto-recovery."""

    # Health check configuration
    CHECK_INTERVAL_SECONDS = 30  # How often to check health
    MAX_RECONNECT_ATTEMPTS = 5   # Trigger recovery after this many reconnect attempts
    MAX_INACTIVITY_SECONDS = 180 # 3 minutes without activity triggers warning
    RECOVERY_COOLDOWN_SECONDS = 300  # 5 minutes between recovery attempts for same instance
    MAX_CONSECUTIVE_FAILURES = 3  # Restart after this many consecutive health check failures

    def __init__(
        self,
        get_db_session: Callable[[], Session],
        container_manager,
        watcher_manager=None,
        on_recovery_triggered: Optional[Callable[[int, str], None]] = None
    ):
        """
        Initialize health monitor.

        Args:
            get_db_session: Factory function to get database session
            container_manager: MCPContainerManager instance for container operations
            watcher_manager: Optional WatcherManager for pause/resume during recovery
            on_recovery_triggered: Optional callback when recovery is triggered (instance_id, reason)
        """
        self.get_db_session = get_db_session
        self.container_manager = container_manager
        self.watcher_manager = watcher_manager
        self.on_recovery_triggered = on_recovery_triggered

        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Track recovery state per instance
        self._last_recovery: Dict[int, datetime] = {}
        self._consecutive_failures: Dict[int, int] = {}
        self._instance_health_cache: Dict[int, Dict[str, Any]] = {}

    async def start(self):
        """Start the health monitoring background task."""
        if self._running:
            logger.warning("MCPHealthMonitorService is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("🏥 MCPHealthMonitorService started - monitoring MCP container health")

    async def stop(self):
        """Stop the health monitoring background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("🏥 MCPHealthMonitorService stopped")

    async def _monitor_loop(self):
        """Main monitoring loop - runs continuously in background."""
        while self._running:
            try:
                await self._check_all_instances()
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}", exc_info=True)

            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    async def _check_all_instances(self):
        """Check health of all active MCP instances."""
        db = self.get_db_session()
        try:
            # Get all active instances (running or starting)
            instances = db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.status.in_(["running", "starting", "authenticated"])
            ).all()

            for instance in instances:
                await self._check_instance_health(instance, db)

        finally:
            db.close()

    async def _check_instance_health(self, instance: WhatsAppMCPInstance, db: Session):
        """
        Check health of a single MCP instance and trigger recovery if needed.

        Args:
            instance: MCP instance to check
            db: Database session
        """
        instance_id = instance.id

        try:
            # Get health status from container manager
            health = self.container_manager.health_check(instance)
            self._instance_health_cache[instance_id] = health

            # Log health for debugging
            logger.debug(
                f"Health check instance {instance_id}: "
                f"status={health.get('status')}, "
                f"connected={health.get('connected')}, "
                f"reconnect_attempts={health.get('reconnect_attempts', 0)}"
            )

            # Check for conditions that require recovery
            needs_recovery = False
            recovery_reason = ""

            # Condition 1: High reconnection attempts (connection instability)
            reconnect_attempts = health.get('reconnect_attempts', 0)
            if reconnect_attempts >= self.MAX_RECONNECT_ATTEMPTS:
                needs_recovery = True
                recovery_reason = f"High reconnection attempts ({reconnect_attempts})"

            # Condition 2: Container unhealthy or degraded
            status = health.get('status', 'unknown')
            if status in ['unhealthy', 'error', 'unavailable']:
                self._consecutive_failures[instance_id] = self._consecutive_failures.get(instance_id, 0) + 1
                if self._consecutive_failures[instance_id] >= self.MAX_CONSECUTIVE_FAILURES:
                    needs_recovery = True
                    recovery_reason = f"Consecutive health failures ({self._consecutive_failures[instance_id]})"
            else:
                # Reset failure counter on successful health check
                self._consecutive_failures[instance_id] = 0

            # Condition 3: Is reconnecting for too long
            if health.get('is_reconnecting', False) and reconnect_attempts > 2:
                needs_recovery = True
                recovery_reason = "Stuck in reconnecting state"

            # Condition 4: API not reachable but container running
            if health.get('container_state') == 'running' and not health.get('api_reachable', False):
                self._consecutive_failures[instance_id] = self._consecutive_failures.get(instance_id, 0) + 1
                if self._consecutive_failures[instance_id] >= self.MAX_CONSECUTIVE_FAILURES:
                    needs_recovery = True
                    recovery_reason = "API unreachable despite container running"

            # Condition 5: Needs re-authentication (log warning but don't auto-recover)
            if health.get('needs_reauth', False):
                logger.warning(
                    f"⚠️  MCP instance {instance_id} ({instance.phone_number}) needs re-authentication. "
                    f"Please scan QR code to restore connection."
                )

            # Trigger recovery if needed (with cooldown)
            if needs_recovery:
                await self._trigger_recovery(instance_id, recovery_reason, db)

        except Exception as e:
            logger.error(f"Error checking health for instance {instance_id}: {e}", exc_info=True)
            self._consecutive_failures[instance_id] = self._consecutive_failures.get(instance_id, 0) + 1

    async def _trigger_recovery(self, instance_id: int, reason: str, db: Session):
        """
        Trigger recovery for an MCP instance (restart container).

        Args:
            instance_id: MCP instance ID
            reason: Why recovery is being triggered
            db: Database session
        """
        # Check cooldown to prevent recovery loops
        last_recovery = self._last_recovery.get(instance_id)
        if last_recovery:
            time_since_recovery = (datetime.utcnow() - last_recovery).total_seconds()
            if time_since_recovery < self.RECOVERY_COOLDOWN_SECONDS:
                logger.debug(
                    f"Skipping recovery for instance {instance_id} - "
                    f"cooldown ({int(self.RECOVERY_COOLDOWN_SECONDS - time_since_recovery)}s remaining)"
                )
                return

        logger.warning(
            f"🔄 Triggering auto-recovery for MCP instance {instance_id}: {reason}"
        )

        try:
            # 1. Pause watcher if available (prevent message processing during restart)
            if self.watcher_manager:
                try:
                    await self.watcher_manager.pause_watcher_for_instance(instance_id)
                    logger.info(f"⏸  Paused watcher for instance {instance_id} during recovery")
                except Exception as e:
                    logger.warning(f"Could not pause watcher: {e}")

            # 2. Restart the container
            try:
                self.container_manager.restart_instance(instance_id, db)
                logger.info(f"✅ Container restarted for instance {instance_id}")
            except Exception as e:
                logger.error(f"Failed to restart container for instance {instance_id}: {e}")
                raise

            # 3. Wait for container to be healthy
            await self._wait_for_health(instance_id, db, timeout_seconds=60)

            # 4. Resume watcher
            if self.watcher_manager:
                try:
                    await self.watcher_manager.resume_watcher_for_instance(instance_id)
                    logger.info(f"▶️  Resumed watcher for instance {instance_id} after recovery")
                except Exception as e:
                    logger.warning(f"Could not resume watcher: {e}")

            # Update recovery tracking
            self._last_recovery[instance_id] = datetime.utcnow()
            self._consecutive_failures[instance_id] = 0

            # Call recovery callback if provided
            if self.on_recovery_triggered:
                try:
                    self.on_recovery_triggered(instance_id, reason)
                except Exception as e:
                    logger.error(f"Error in recovery callback: {e}")

            logger.info(f"✅ Auto-recovery completed for MCP instance {instance_id}")

        except Exception as e:
            logger.error(f"Auto-recovery failed for instance {instance_id}: {e}", exc_info=True)

            # Resume watcher even on failure to prevent being stuck
            if self.watcher_manager:
                try:
                    await self.watcher_manager.resume_watcher_for_instance(instance_id)
                except:
                    pass

    async def _wait_for_health(self, instance_id: int, db: Session, timeout_seconds: int = 60):
        """
        Wait for instance to become healthy after restart.

        Args:
            instance_id: MCP instance ID
            db: Database session
            timeout_seconds: Maximum time to wait
        """
        start = datetime.utcnow()
        check_interval = 5  # seconds

        while (datetime.utcnow() - start).total_seconds() < timeout_seconds:
            instance = db.query(WhatsAppMCPInstance).get(instance_id)
            if not instance:
                raise ValueError(f"Instance {instance_id} not found")

            health = self.container_manager.health_check(instance)

            if health.get('status') in ['healthy', 'authenticating']:
                logger.info(f"Instance {instance_id} is healthy after restart")
                return

            if health.get('api_reachable', False):
                logger.info(f"Instance {instance_id} API is reachable after restart")
                return

            await asyncio.sleep(check_interval)

        logger.warning(f"Instance {instance_id} did not become healthy within {timeout_seconds}s")

    def get_health_status(self, instance_id: int) -> Optional[Dict[str, Any]]:
        """Get cached health status for an instance."""
        return self._instance_health_cache.get(instance_id)

    def get_all_health_status(self) -> Dict[int, Dict[str, Any]]:
        """Get cached health status for all monitored instances."""
        return dict(self._instance_health_cache)

    def is_running(self) -> bool:
        """Check if the monitor is running."""
        return self._running
