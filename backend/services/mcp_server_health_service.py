"""
MCP Server Periodic Health Check Service (v0.6.0 G3-A)

Background asyncio service that periodically checks the health of all active
MCP server connections (Hub integrations) and records results in the
MCPServerHealth table.

Lifecycle:
- Started at app startup (after MCP auto-connect)
- Stopped at app shutdown
- Runs every CHECK_INTERVAL_SECONDS (180s = 3 min)

For each active MCPServerConfig:
- Connected: pings via transport.ping(), records latency
- Disconnected: attempts reconnection via MCPConnectionManager.get_or_connect()
- Degraded (cooldown active): skips until cooldown expires, then retries
"""

import asyncio
import logging
import time
from contextlib import contextmanager
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker, Session

logger = logging.getLogger(__name__)


class MCPServerHealthCheckService:
    """Background service that periodically health-checks all active MCP servers."""

    CHECK_INTERVAL_SECONDS = 180  # 3 minutes

    def __init__(self, engine):
        """
        Args:
            engine: SQLAlchemy engine for creating database sessions.
        """
        self._engine = engine
        self._session_factory = sessionmaker(bind=engine)
        self._running = False
        self._task: Optional[asyncio.Task] = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self):
        """Start the periodic health check loop."""
        if self._running:
            logger.warning("MCPServerHealthCheckService is already running")
            return
        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("MCP Server Health Check Service started (interval=%ds)", self.CHECK_INTERVAL_SECONDS)

    async def stop(self):
        """Stop the health check loop gracefully."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("MCP Server Health Check Service stopped")

    def is_running(self) -> bool:
        return self._running

    @contextmanager
    def _db_session_scope(self):
        """Provide a short-lived DB session for health check persistence."""
        db: Session = self._session_factory()
        try:
            yield db
        finally:
            try:
                db.rollback()
            except Exception:
                pass
            db.close()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def _monitor_loop(self):
        """Run health checks in a loop until stopped."""
        # Initial delay so the app can finish starting up fully
        await asyncio.sleep(15)
        while self._running:
            try:
                await self._check_all_servers()
            except Exception as e:
                logger.error("Health check cycle error: %s", e, exc_info=True)

            # BUG-665 instrumentation: lightweight probe of idle-in-transaction
            # sessions so we can watch pool hygiene over time.
            try:
                with self._db_session_scope() as db:
                    idle_count = db.execute(
                        text(
                            "SELECT count(*) FROM pg_stat_activity "
                            "WHERE state = 'idle in transaction'"
                        )
                    ).scalar()
                idle_count = int(idle_count or 0)
                logger.info(
                    "pg_stat_activity idle-in-transaction count: %d", idle_count
                )
                # Feed the Prometheus gauge if metrics are enabled.
                try:
                    import settings as _settings
                    if _settings.METRICS_ENABLED:
                        from services.metrics_service import (
                            TSN_DB_IDLE_IN_TRANSACTION,
                        )
                        TSN_DB_IDLE_IN_TRANSACTION.set(idle_count)
                except Exception:
                    pass
            except Exception as probe_err:
                # SQLite / permission-denied / any other backend that doesn't
                # expose pg_stat_activity — swallow so the monitor loop keeps
                # running.
                logger.debug(
                    "idle-in-transaction probe skipped: %s", probe_err
                )

            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    # ------------------------------------------------------------------
    # Bulk check
    # ------------------------------------------------------------------

    async def _check_all_servers(self):
        """Query all active MCP servers and check each one."""
        from models import MCPServerConfig

        with self._db_session_scope() as db:
            servers = (
                db.query(MCPServerConfig)
                .filter(MCPServerConfig.is_active == True)  # noqa: E712
                .all()
            )
            server_snapshots = [(server.id, server.server_name) for server in servers]

        if not server_snapshots:
            return

        checked = 0
        healthy = 0
        for server_id, server_name in server_snapshots:
            try:
                ok = await self._check_server(server_id, server_name)
                checked += 1
                if ok:
                    healthy += 1
            except Exception as e:
                logger.error(
                    "Health check failed for server %s (id=%d): %s",
                    server_name, server_id, e,
                )
                checked += 1

        logger.info(
            "MCP health check cycle complete: %d/%d healthy (%d checked)",
            healthy, len(server_snapshots), checked,
        )

    # ------------------------------------------------------------------
    # Single-server check
    # ------------------------------------------------------------------

    async def _check_server(self, server_id: int, server_name: str) -> bool:
        """Check a single MCP server. Returns True if healthy.

        Strategy:
        - Connected   -> ping, record result
        - Disconnected -> attempt reconnect, record result
        - Degraded (cooldown) -> skip (log only)
        """
        from hub.mcp.connection_manager import MCPConnectionManager
        manager = MCPConnectionManager.get_instance()

        status = manager.get_connection_status(server_id)

        if status == "degraded":
            # Server is in circuit-breaker cooldown; don't poke it.
            with self._db_session_scope() as db:
                self._record_health(db, server_id, check_type="ping", success=False,
                                    error_message="Server in degraded cooldown, skipped")
            logger.debug("Skipping degraded server %s (id=%d)", server_name, server_id)
            return False

        if status == "connected":
            return await self._ping_server(manager, server_id, server_name)

        # Disconnected — attempt reconnect
        return await self._reconnect_server(manager, server_id, server_name)

    async def _ping_server(
        self, manager, server_id: int, server_name: str
    ) -> bool:
        """Ping an already-connected server and record the result."""
        transport = manager._connections.get(server_id)
        if not transport:
            # Stale status — treat as disconnected
            return await self._reconnect_server(manager, server_id, server_name)

        t0 = time.monotonic()
        try:
            alive = await asyncio.wait_for(transport.ping(), timeout=15)
            latency_ms = int((time.monotonic() - t0) * 1000)

            if alive:
                with self._db_session_scope() as db:
                    manager.record_success(server_id)
                    self._record_health(db, server_id, check_type="ping",
                                        success=True, latency_ms=latency_ms)
                return True
            else:
                latency_ms = int((time.monotonic() - t0) * 1000)
                with self._db_session_scope() as db:
                    manager.record_failure(server_id, db, error="Ping returned False")
                    self._record_health(db, server_id, check_type="ping",
                                        success=False, latency_ms=latency_ms,
                                        error_message="Ping returned False")
                return False

        except asyncio.TimeoutError:
            latency_ms = int((time.monotonic() - t0) * 1000)
            with self._db_session_scope() as db:
                manager.record_failure(server_id, db, error="Ping timed out (15s)")
                self._record_health(db, server_id, check_type="ping",
                                    success=False, latency_ms=latency_ms,
                                    error_message="Ping timed out (15s)")
            logger.warning("Ping timed out for server %s (id=%d)", server_name, server_id)
            return False

        except Exception as e:
            latency_ms = int((time.monotonic() - t0) * 1000)
            error_msg = f"Ping error: {e}"
            with self._db_session_scope() as db:
                manager.record_failure(server_id, db, error=error_msg)
                self._record_health(db, server_id, check_type="ping",
                                    success=False, latency_ms=latency_ms,
                                    error_message=error_msg[:500])
            logger.warning("Ping failed for server %s (id=%d): %s", server_name, server_id, e)
            return False

    async def _reconnect_server(
        self, manager, server_id: int, server_name: str
    ) -> bool:
        """Attempt to reconnect a disconnected server and record the result.

        BUG-665: pre-validate the server row and extract any primitives we
        need into plain Python variables BEFORE the 30s-bounded network
        call, so our own DB session is released back to the pool and is not
        held "idle in transaction" across the await. The connection manager
        still needs a session for its own internal work (config lookup,
        container ensure, status commit), so we hand it a dedicated
        short-lived session that is scoped only around that call. The
        result is recorded through yet another fresh short-lived session.
        Mirrors the BUG-663 Ollama write-back pattern.
        """
        t0 = time.monotonic()

        # Step 1: pre-validate & extract primitives under a very short session.
        from models import MCPServerConfig
        try:
            with self._db_session_scope() as db:
                row = (
                    db.query(MCPServerConfig)
                    .filter(MCPServerConfig.id == server_id)
                    .first()
                )
                if row is None:
                    logger.warning(
                        "Reconnect skipped: MCP server %s (id=%d) not found",
                        server_name, server_id,
                    )
                    return False
                if not row.is_active:
                    logger.debug(
                        "Reconnect skipped: MCP server %s (id=%d) inactive",
                        server_name, server_id,
                    )
                    return False
                # Refresh the display name in case it changed.
                server_name = row.server_name or server_name
        except Exception as e:
            logger.warning(
                "Pre-validation failed for MCP server %s (id=%d): %s",
                server_name, server_id, e,
            )
            # Fall through — we still try the reconnect attempt below.

        # Step 2: perform the network call with a dedicated short-lived
        # session. `manager.get_or_connect` needs the session for its full
        # duration (DB read of MCPServerConfig → toolbox bootstrap for stdio
        # transports → DB write of `connection_status` post-connect), so the
        # pool slot IS held across the `await transport.connect()`.
        #
        # To bound the worst-case hold we shortened the timeout to 10s
        # (from 30s): a health-loop speculative reconnect that needs >10s
        # is almost certainly going to fail anyway, and the user-path
        # reconnect (which still uses `get_or_connect` directly) is
        # unaffected.
        #
        # TODO(follow-up): refactor `MCPConnectionManager.get_or_connect`
        # itself to split read → await → write into three sessions so the
        # pool slot is genuinely released across the blocking connect.
        try:
            with self._db_session_scope() as conn_db:
                await asyncio.wait_for(
                    manager.get_or_connect(server_id, conn_db), timeout=10
                )
            latency_ms = int((time.monotonic() - t0) * 1000)

            # Step 3: open a fresh short-lived session to record success.
            with self._db_session_scope() as db:
                self._record_health(db, server_id, check_type="reconnect",
                                    success=True, latency_ms=latency_ms)
            logger.info("Reconnected MCP server %s (id=%d) in %dms",
                        server_name, server_id, latency_ms)
            return True

        except asyncio.TimeoutError:
            latency_ms = int((time.monotonic() - t0) * 1000)
            error_msg = "Reconnect timed out (10s)"
            # Fresh short-lived session for the failure write-back.
            with self._db_session_scope() as db:
                manager.record_failure(server_id, db, error=error_msg)
                self._record_health(db, server_id, check_type="reconnect",
                                    success=False, latency_ms=latency_ms,
                                    error_message=error_msg)
            logger.warning("Reconnect timed out for server %s (id=%d)", server_name, server_id)
            return False

        except Exception as e:
            latency_ms = int((time.monotonic() - t0) * 1000)
            error_msg = f"Reconnect error: {e}"
            with self._db_session_scope() as db:
                manager.record_failure(server_id, db, error=error_msg)
                self._record_health(db, server_id, check_type="reconnect",
                                    success=False, latency_ms=latency_ms,
                                    error_message=error_msg[:500])
            logger.warning("Reconnect failed for server %s (id=%d): %s",
                           server_name, server_id, e)
            return False

    # ------------------------------------------------------------------
    # DB recording
    # ------------------------------------------------------------------

    def _record_health(
        self,
        db: Session,
        server_id: int,
        check_type: str,
        success: bool,
        latency_ms: Optional[int] = None,
        error_message: Optional[str] = None,
    ):
        """Insert a row into MCPServerHealth."""
        from models import MCPServerHealth
        try:
            entry = MCPServerHealth(
                server_id=server_id,
                check_type=check_type,
                success=success,
                latency_ms=latency_ms,
                error_message=error_message,
                checked_at=datetime.utcnow(),
            )
            db.add(entry)
            db.commit()
        except Exception as e:
            logger.error("Failed to record health for server %d: %s", server_id, e)
            try:
                db.rollback()
            except Exception:
                pass
