"""
Slack Socket Mode Manager (v0.6.0 V060-CHN-002).

Owns the lifecycle of all Slack Socket Mode workers in this backend process.
Mirrors TelegramWatcherManager so app.py and routes_slack.py have a familiar
control surface.

Responsibilities:
- start_all() at FastAPI startup → spin up workers for every active integration
  with mode='socket'.
- start_one(id) / stop_one(id) called from SlackIntegration CRUD endpoints when
  an integration is created, toggled, deleted, or has its app_token rotated.
- stop_all() at FastAPI shutdown.

Singleton pattern via app.state for reach from request handlers.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


class SlackSocketModeManager:
    """Manages Slack Socket Mode workers across all tenants in this process."""

    def __init__(self, db_session_factory) -> None:
        self._db_session_factory = db_session_factory
        self._workers: Dict[int, "SlackSocketModeWorker"] = {}

    async def start_all(self) -> None:
        """Spin up workers for every active mode='socket' integration."""
        from models import SlackIntegration  # noqa: WPS433

        db = self._db_session_factory()
        try:
            integrations = (
                db.query(SlackIntegration)
                .filter(
                    SlackIntegration.mode == "socket",
                    SlackIntegration.is_active == True,
                )
                .all()
            )
        finally:
            db.close()

        for integration in integrations:
            await self.start_one(integration.id)

        logger.info(
            "SlackSocketModeManager started %d worker(s)", len(self._workers)
        )

    async def start_one(self, integration_id: int) -> bool:
        """Start a worker for a specific integration. Idempotent."""
        if integration_id in self._workers:
            logger.debug("Slack Socket Mode worker already running for %s", integration_id)
            return True

        from models import SlackIntegration  # noqa: WPS433
        from hub.security import TokenEncryption  # noqa: WPS433
        from services.encryption_key_service import get_slack_encryption_key  # noqa: WPS433
        from channels.slack.socket_worker import SlackSocketModeWorker  # noqa: WPS433

        db = self._db_session_factory()
        try:
            integration = db.query(SlackIntegration).get(integration_id)
            if integration is None:
                logger.warning(
                    "Slack Socket Mode start_one: integration %s not found", integration_id
                )
                return False
            if integration.mode != "socket" or not integration.is_active:
                logger.info(
                    "Slack Socket Mode skipping integration %s (mode=%s, active=%s)",
                    integration_id, integration.mode, integration.is_active,
                )
                return False
            if not integration.bot_token_encrypted or not integration.app_token_encrypted:
                logger.warning(
                    "Slack Socket Mode integration %s missing tokens; cannot start worker",
                    integration_id,
                )
                return False

            key = get_slack_encryption_key(db)
            if not key:
                logger.error("Slack encryption key unavailable; cannot start Socket Mode worker")
                return False
            enc = TokenEncryption(key.encode())
            try:
                bot_token = enc.decrypt(integration.bot_token_encrypted, integration.tenant_id)
                app_token = enc.decrypt(integration.app_token_encrypted, integration.tenant_id)
            except Exception as e:
                logger.error(
                    "Slack Socket Mode token decrypt failed for integration %s: %s",
                    integration_id, e,
                )
                return False

            tenant_id = integration.tenant_id
        finally:
            db.close()

        worker = SlackSocketModeWorker(
            integration_id=integration_id,
            tenant_id=tenant_id,
            bot_token=bot_token,
            app_token=app_token,
            db_session_factory=self._db_session_factory,
        )

        ok = await worker.start()
        if ok:
            self._workers[integration_id] = worker
        return ok

    async def stop_one(self, integration_id: int) -> None:
        worker = self._workers.pop(integration_id, None)
        if worker is None:
            return
        await worker.stop()

    async def restart_one(self, integration_id: int) -> bool:
        await self.stop_one(integration_id)
        return await self.start_one(integration_id)

    async def stop_all(self) -> None:
        ids = list(self._workers.keys())
        for integration_id in ids:
            await self.stop_one(integration_id)
        logger.info("SlackSocketModeManager stopped all workers")

    def is_running(self, integration_id: int) -> bool:
        worker = self._workers.get(integration_id)
        return bool(worker and worker.connected)
