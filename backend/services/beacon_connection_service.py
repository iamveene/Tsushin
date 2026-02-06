"""
Beacon Connection Service (Phase 18.4)
Health Monitoring and Background Tasks for Shell Skill C2

Provides:
- Background health monitoring for beacon connections
- Stale connection cleanup
- Integration status updates
"""

import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from models import ShellIntegration
from websocket_manager import manager

logger = logging.getLogger(__name__)


class BeaconConnectionService:
    """
    Service for monitoring and managing beacon WebSocket connections.

    Runs as a background task to:
    - Detect stale connections (no heartbeat)
    - Update database health status
    - Clean up disconnected beacons
    """

    def __init__(self, engine=None):
        """
        Initialize the service.

        Args:
            engine: SQLAlchemy engine (optional, can be set later)
        """
        self._engine = engine
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Configuration
        self.check_interval = 10  # Seconds between health checks
        self.heartbeat_timeout = 30  # Seconds before marking beacon as stale
        self.cleanup_interval = 60  # Seconds between cleanup runs

        self._last_cleanup = datetime.utcnow()

    def set_engine(self, engine):
        """Set the database engine."""
        self._engine = engine

    def _get_db(self) -> Session:
        """Get a database session."""
        if not self._engine:
            raise RuntimeError("Database engine not configured")
        SessionLocal = sessionmaker(bind=self._engine)
        return SessionLocal()

    async def start(self):
        """Start the background health monitoring task."""
        if self._running:
            logger.warning("BeaconConnectionService already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("BeaconConnectionService started")

    async def stop(self):
        """Stop the background health monitoring task."""
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        logger.info("BeaconConnectionService stopped")

    async def _monitor_loop(self):
        """Main monitoring loop."""
        while self._running:
            try:
                await self._check_beacon_health()

                # Periodic cleanup
                if datetime.utcnow() - self._last_cleanup > timedelta(seconds=self.cleanup_interval):
                    await self._cleanup_stale_connections()
                    self._last_cleanup = datetime.utcnow()

            except Exception as e:
                logger.error(f"Error in beacon monitor loop: {e}")

            await asyncio.sleep(self.check_interval)

    async def _check_beacon_health(self):
        """
        Check health of all connected beacons.

        Marks beacons as offline if no heartbeat received within timeout.
        """
        stale_beacons = []

        for integration_id in list(manager.beacon_connections.keys()):
            last_heartbeat = manager.beacon_last_heartbeat.get(integration_id)

            if not last_heartbeat:
                stale_beacons.append(integration_id)
                continue

            if datetime.utcnow() - last_heartbeat > timedelta(seconds=self.heartbeat_timeout):
                stale_beacons.append(integration_id)

        # Handle stale beacons
        for integration_id in stale_beacons:
            logger.warning(f"Beacon {integration_id} is stale, disconnecting")
            await self._mark_beacon_offline(integration_id)

    async def _mark_beacon_offline(self, integration_id: int):
        """
        Mark a beacon as offline and clean up.

        Args:
            integration_id: ShellIntegration ID
        """
        # Disconnect from WebSocket
        await manager.disconnect_beacon(integration_id)

        # Update database
        db = self._get_db()
        try:
            integration = db.query(ShellIntegration).filter(
                ShellIntegration.id == integration_id
            ).first()

            if integration:
                integration.health_status = "offline"
                db.commit()
                logger.info(f"Marked beacon {integration_id} as offline in database")

        except Exception as e:
            logger.error(f"Error updating beacon status in database: {e}")
            db.rollback()
        finally:
            db.close()

    async def _cleanup_stale_connections(self):
        """
        Periodic cleanup of stale data.

        - Remove expired command results (based on retention)
        - Sync database status with actual connections
        """
        db = self._get_db()

        try:
            # Find integrations marked as online in DB but not connected
            online_in_db = db.query(ShellIntegration).filter(
                ShellIntegration.health_status == "healthy"
            ).all()

            for integration in online_in_db:
                if integration.id not in manager.beacon_connections:
                    # Check last_checkin
                    if integration.last_checkin:
                        # If last checkin was more than 3x poll_interval ago, mark offline
                        timeout = timedelta(seconds=integration.poll_interval * 3)
                        if datetime.utcnow() - integration.last_checkin > timeout:
                            integration.health_status = "offline"
                            logger.info(f"Synced beacon {integration.id} status to offline")

            db.commit()

        except Exception as e:
            logger.error(f"Error in stale connection cleanup: {e}")
            db.rollback()
        finally:
            db.close()

    def get_status(self) -> dict:
        """
        Get current service status.

        Returns:
            Dict with service status and beacon stats
        """
        return {
            "running": self._running,
            "check_interval": self.check_interval,
            "heartbeat_timeout": self.heartbeat_timeout,
            "beacon_stats": manager.get_beacon_stats()
        }


# Global service instance
beacon_service = BeaconConnectionService()


async def start_beacon_service(engine):
    """
    Start the beacon connection service.

    Called from app.py startup event.

    Args:
        engine: SQLAlchemy engine
    """
    beacon_service.set_engine(engine)
    await beacon_service.start()


async def stop_beacon_service():
    """
    Stop the beacon connection service.

    Called from app.py shutdown event.
    """
    await beacon_service.stop()
