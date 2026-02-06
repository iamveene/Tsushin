"""
OAuth Token Refresh Worker

Background worker that proactively refreshes OAuth tokens before they expire.
Runs periodically to ensure tokens are always valid.
"""

import logging
import threading
import time
from datetime import datetime, timedelta
from typing import Optional
import os

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from db import get_session
from models import OAuthToken, HubIntegration

logger = logging.getLogger(__name__)


class OAuthTokenRefreshWorker:
    """Background worker for proactive OAuth token refresh."""

    def __init__(
        self,
        engine: Engine,
        poll_interval_minutes: int = 30,
        refresh_threshold_hours: int = 24
    ):
        self.engine = engine
        self.poll_interval = poll_interval_minutes * 60
        self.refresh_threshold = timedelta(hours=refresh_threshold_hours)
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._running = False

    def start(self) -> None:
        """Start the background worker thread."""
        if self._running:
            logger.warning("OAuthTokenRefreshWorker already running")
            return

        self._stop_event.clear()
        self._running = True
        self._thread = threading.Thread(
            target=self._run_loop,
            name="OAuthTokenRefreshWorker",
            daemon=True
        )
        self._thread.start()

        logger.info(
            "OAuthTokenRefreshWorker started "
            "(poll=%s min, threshold=%s h)",
            int(self.poll_interval / 60),
            int(self.refresh_threshold.total_seconds() / 3600)
        )

    def stop(self, timeout: int = 10) -> None:
        """Stop the background worker thread."""
        if not self._running:
            return

        logger.info("Stopping OAuthTokenRefreshWorker...")
        self._stop_event.set()

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

        self._running = False
        logger.info("OAuthTokenRefreshWorker stopped")

    def _run_loop(self) -> None:
        """Main worker loop - checks and refreshes tokens."""
        logger.info("OAuthTokenRefreshWorker loop started")
        iteration = 0

        while not self._stop_event.is_set():
            iteration += 1
            logger.info("OAuthTokenRefreshWorker iteration %s", iteration)

            try:
                self._check_and_refresh_tokens()
            except Exception as e:
                logger.error("Error in token refresh worker: %s", e, exc_info=True)

            for _ in range(self.poll_interval):
                if self._stop_event.is_set():
                    break
                time.sleep(1)

    def _check_and_refresh_tokens(self) -> None:
        """Check all tokens and refresh those expiring soon."""
        with get_session(self.engine) as db:
            now = datetime.utcnow()
            threshold = now + self.refresh_threshold

            expiring_tokens = db.query(OAuthToken).filter(
                OAuthToken.expires_at < threshold
            ).all()

            if not expiring_tokens:
                logger.info("No tokens need refresh")
                return

            logger.info(
                "Found %s token(s) expiring within %s hours",
                len(expiring_tokens),
                int(self.refresh_threshold.total_seconds() / 3600)
            )

            for token in expiring_tokens:
                try:
                    self._refresh_token(db, token)
                except Exception as e:
                    logger.error(
                        "Failed to refresh token for integration %s: %s",
                        token.integration_id,
                        e,
                        exc_info=True
                    )

    def _refresh_token(self, db: Session, token: OAuthToken) -> None:
        """Refresh a specific token."""
        integration = db.query(HubIntegration).filter(
            HubIntegration.id == token.integration_id
        ).first()

        if not integration or not integration.is_active:
            logger.info("Skipping inactive integration %s", token.integration_id)
            return

        integration_type = integration.type
        logger.info(
            "Refreshing %s token for integration %s (expires_at=%s)",
            integration_type,
            integration.id,
            token.expires_at
        )

        if integration_type == "gmail":
            self._refresh_gmail_token(db, integration.id)
        elif integration_type == "calendar":
            self._refresh_calendar_token(db, integration.id)
        else:
            logger.warning("Unknown integration type for token refresh: %s", integration_type)

    def _refresh_gmail_token(self, db: Session, integration_id: int) -> None:
        """Refresh Gmail integration token."""
        from hub.google.gmail_service import GmailService
        from services.encryption_key_service import get_google_encryption_key
        import asyncio

        service = GmailService(
            db=db,
            integration_id=integration_id,
            encryption_key=get_google_encryption_key(db)
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(service.refresh_tokens())
        finally:
            loop.close()

        if success:
            logger.info("✅ Gmail token refreshed for integration %s", integration_id)
        else:
            raise RuntimeError("Gmail token refresh returned False")

    def _refresh_calendar_token(self, db: Session, integration_id: int) -> None:
        """Refresh Calendar integration token."""
        from hub.google.calendar_service import CalendarService
        from services.encryption_key_service import get_google_encryption_key
        import asyncio

        service = CalendarService(
            db=db,
            integration_id=integration_id,
            encryption_key=get_google_encryption_key(db)
        )

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            success = loop.run_until_complete(service.refresh_tokens())
        finally:
            loop.close()

        if success:
            logger.info("✅ Calendar token refreshed for integration %s", integration_id)
        else:
            raise RuntimeError("Calendar token refresh returned False")


_worker_instance: Optional[OAuthTokenRefreshWorker] = None


def get_oauth_refresh_worker(
    engine: Engine,
    poll_interval_minutes: int = 30,
    refresh_threshold_hours: int = 24
) -> OAuthTokenRefreshWorker:
    """Get or create the global OAuth refresh worker instance."""
    global _worker_instance

    if _worker_instance is None:
        _worker_instance = OAuthTokenRefreshWorker(
            engine,
            poll_interval_minutes,
            refresh_threshold_hours
        )

    return _worker_instance


def start_oauth_refresh_worker(
    engine: Engine,
    poll_interval_minutes: int = 30,
    refresh_threshold_hours: int = 24
) -> None:
    """Start the global OAuth refresh worker."""
    worker = get_oauth_refresh_worker(
        engine,
        poll_interval_minutes,
        refresh_threshold_hours
    )
    worker.start()


def stop_oauth_refresh_worker(timeout: int = 10) -> None:
    """Stop the global OAuth refresh worker."""
    if _worker_instance:
        _worker_instance.stop(timeout)
