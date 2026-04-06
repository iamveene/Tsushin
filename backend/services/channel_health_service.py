"""
Channel Health Service - Item 38
Background service that monitors health of all channel instances (WhatsApp, Telegram,
Slack, Discord) and manages circuit breaker state for each.

Integrates with:
- MCPContainerManager for WhatsApp health checks
- Telegram Bot API (getMe) for Telegram health checks
- SlackChannelAdapter for Slack health checks
- DiscordChannelAdapter for Discord health checks
- WatcherActivityService for real-time WebSocket updates
- ChannelAlertDispatcher for alert notifications
- Prometheus metrics for observability
"""

import asyncio
import logging
import time
from datetime import datetime
from typing import Optional, Dict, Any, Callable, List, Tuple

import httpx
from sqlalchemy.orm import Session

from models import WhatsAppMCPInstance, TelegramBotInstance
from services.circuit_breaker import CircuitBreaker, CircuitBreakerConfig, CircuitBreakerState
import settings

logger = logging.getLogger(__name__)

# Prometheus metrics (imported only when enabled)
if settings.METRICS_ENABLED:
    from services.metrics_service import (
        TSN_CIRCUIT_BREAKER_TRANSITIONS_TOTAL,
        TSN_CIRCUIT_BREAKER_STATE,
        TSN_CHANNEL_HEALTH_CHECK_DURATION,
        TSN_CHANNEL_HEALTH_CHECK_FAILURES_TOTAL,
    )

# Map circuit breaker state to gauge value for Prometheus
_STATE_GAUGE_MAP = {
    CircuitBreakerState.CLOSED: 0,
    CircuitBreakerState.OPEN: 1,
    CircuitBreakerState.HALF_OPEN: 2,
}


class ChannelHealthService:
    """
    Background service that periodically probes all channel instances and
    manages circuit breaker state transitions.
    """

    CHECK_INTERVAL_SECONDS = settings.CHANNEL_HEALTH_CHECK_INTERVAL

    # Module-level singleton for access from non-request contexts (e.g., AgentRouter)
    _instance: Optional['ChannelHealthService'] = None

    @classmethod
    def get_instance(cls) -> Optional['ChannelHealthService']:
        """Return the singleton instance, or None if not yet initialized."""
        return cls._instance

    def __init__(
        self,
        get_db_session: Callable[[], Session],
        container_manager=None,
        watcher_activity_service=None,
        alert_dispatcher=None,
    ):
        """
        Args:
            get_db_session: Factory function that returns a new DB session
            container_manager: MCPContainerManager for WhatsApp health checks
            watcher_activity_service: WatcherActivityService for WebSocket events
            alert_dispatcher: ChannelAlertDispatcher for alert notifications
        """
        self.get_db_session = get_db_session
        self.container_manager = container_manager
        self.watcher_activity_service = watcher_activity_service
        self.alert_dispatcher = alert_dispatcher

        self._circuit_breakers: Dict[Tuple[str, int], CircuitBreaker] = {}
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Default CB config from settings
        self._default_config = CircuitBreakerConfig(
            failure_threshold=settings.CHANNEL_CB_FAILURE_THRESHOLD,
            recovery_timeout_seconds=settings.CHANNEL_CB_RECOVERY_TIMEOUT,
        )

        # Register singleton so AgentRouter can access without app.state
        ChannelHealthService._instance = self

    async def start(self):
        """Start the health monitoring background task."""
        if not settings.CHANNEL_HEALTH_ENABLED:
            logger.info("Channel Health Monitor disabled via TSN_CHANNEL_HEALTH_ENABLED")
            return
        if self._running:
            logger.warning("ChannelHealthService is already running")
            return

        self._running = True
        self._task = asyncio.create_task(self._monitor_loop())
        logger.info("ChannelHealthService started - monitoring channel health every %ds", self.CHECK_INTERVAL_SECONDS)

    async def stop(self):
        """Stop the health monitoring background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("ChannelHealthService stopped")

    async def _monitor_loop(self):
        """Main loop: check all active instances."""
        while self._running:
            try:
                await self._check_all_instances()
            except Exception as e:
                logger.error(f"Error in channel health monitor loop: {e}", exc_info=True)

            await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)

    async def _check_all_instances(self):
        """Query DB for active WhatsApp, Telegram, Slack, and Discord instances, probe each."""
        db = self.get_db_session()
        try:
            # WhatsApp instances
            wa_instances = db.query(WhatsAppMCPInstance).filter(
                WhatsAppMCPInstance.status.in_(["running", "starting", "authenticated"])
            ).all()
            for inst in wa_instances:
                try:
                    await self._check_whatsapp_instance(inst, db)
                except Exception as e:
                    logger.error(f"Error checking WhatsApp instance {inst.id}: {e}", exc_info=True)

            # Telegram instances
            tg_instances = db.query(TelegramBotInstance).filter(
                TelegramBotInstance.status.in_(["active"])
            ).all()
            for inst in tg_instances:
                try:
                    await self._check_telegram_instance(inst, db)
                except Exception as e:
                    logger.error(f"Error checking Telegram instance {inst.id}: {e}", exc_info=True)

            # Slack instances
            try:
                from models import SlackIntegration
                slack_instances = db.query(SlackIntegration).filter(
                    SlackIntegration.is_active == True,
                    SlackIntegration.status.in_(["connected"])
                ).all()
                for inst in slack_instances:
                    try:
                        await self._check_slack_instance(inst, db)
                    except Exception as e:
                        logger.error(f"Error checking Slack instance {inst.id}: {e}", exc_info=True)
            except Exception as e:
                logger.debug(f"Slack integration not available: {e}")

            # Discord instances
            try:
                from models import DiscordIntegration
                discord_instances = db.query(DiscordIntegration).filter(
                    DiscordIntegration.is_active == True,
                    DiscordIntegration.status.in_(["connected"])
                ).all()
                for inst in discord_instances:
                    try:
                        await self._check_discord_instance(inst, db)
                    except Exception as e:
                        logger.error(f"Error checking Discord instance {inst.id}: {e}", exc_info=True)
            except Exception as e:
                logger.debug(f"Discord integration not available: {e}")

        finally:
            db.close()

    async def _check_whatsapp_instance(self, instance: WhatsAppMCPInstance, db: Session):
        """Delegate to container_manager.health_check(), map to success/failure."""
        if not self.container_manager:
            return

        channel_type = "whatsapp"
        cb = self._get_or_create_cb(channel_type, instance.id)

        if not cb.should_probe():
            return
        cb.try_recover()

        start_time = time.monotonic()
        try:
            health = self.container_manager.health_check(instance)
            latency_ms = (time.monotonic() - start_time) * 1000

            if settings.METRICS_ENABLED:
                TSN_CHANNEL_HEALTH_CHECK_DURATION.labels(channel_type=channel_type).observe(latency_ms / 1000)

            status = health.get('status', 'unknown')
            connected = health.get('connected', False)

            # Map: healthy/degraded with connected=True -> success, everything else -> failure
            if status in ('healthy', 'degraded') and connected:
                health_status = "healthy"
                detail = f"status={status}, connected={connected}"
                transition = cb.record_success()
            else:
                health_status = "unhealthy"
                reason = f"status={status}, connected={connected}"
                detail = reason
                transition = cb.record_failure(reason)

                if settings.METRICS_ENABLED:
                    TSN_CHANNEL_HEALTH_CHECK_FAILURES_TOTAL.labels(
                        channel_type=channel_type, reason=status
                    ).inc()

            if transition:
                await self._handle_transition(
                    cb, channel_type, instance.id, instance.tenant_id,
                    transition[0], transition[1], detail, health_status, latency_ms, db
                )

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(f"WhatsApp health check failed for instance {instance.id}: {e}")
            transition = cb.record_failure(str(e))
            if settings.METRICS_ENABLED:
                TSN_CHANNEL_HEALTH_CHECK_FAILURES_TOTAL.labels(
                    channel_type=channel_type, reason="exception"
                ).inc()
            if transition:
                await self._handle_transition(
                    cb, channel_type, instance.id, instance.tenant_id,
                    transition[0], transition[1], str(e), "unhealthy", latency_ms, db
                )

    async def _check_telegram_instance(self, instance: TelegramBotInstance, db: Session):
        """Check Telegram bot health via Bot API getMe()."""
        channel_type = "telegram"
        cb = self._get_or_create_cb(channel_type, instance.id)

        if not cb.should_probe():
            return
        cb.try_recover()

        start_time = time.monotonic()
        try:
            # Decrypt bot token
            token = self._decrypt_telegram_token(instance, db)
            if not token:
                transition = cb.record_failure("token_decryption_failed")
                if transition:
                    await self._handle_transition(
                        cb, channel_type, instance.id, instance.tenant_id,
                        transition[0], transition[1], "Token decryption failed",
                        "unhealthy", 0, db
                    )
                return

            # Call Telegram API
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
                latency_ms = (time.monotonic() - start_time) * 1000

                if settings.METRICS_ENABLED:
                    TSN_CHANNEL_HEALTH_CHECK_DURATION.labels(channel_type=channel_type).observe(latency_ms / 1000)

                if resp.status_code == 200:
                    data = resp.json()
                    if data.get("ok"):
                        health_status = "healthy"
                        bot_username = data.get("result", {}).get("username", "unknown")
                        detail = f"Bot: @{bot_username}"
                        transition = cb.record_success()
                    else:
                        health_status = "unhealthy"
                        detail = data.get("description", "Unknown Telegram API error")
                        transition = cb.record_failure(detail)
                else:
                    health_status = "unhealthy"
                    detail = f"HTTP {resp.status_code}"
                    transition = cb.record_failure(detail)

                    if settings.METRICS_ENABLED:
                        TSN_CHANNEL_HEALTH_CHECK_FAILURES_TOTAL.labels(
                            channel_type=channel_type, reason=f"http_{resp.status_code}"
                        ).inc()

                if transition:
                    await self._handle_transition(
                        cb, channel_type, instance.id, instance.tenant_id,
                        transition[0], transition[1], detail, health_status, latency_ms, db
                    )

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(f"Telegram health check failed for instance {instance.id}: {e}")
            transition = cb.record_failure(str(e))
            if settings.METRICS_ENABLED:
                TSN_CHANNEL_HEALTH_CHECK_FAILURES_TOTAL.labels(
                    channel_type=channel_type, reason="exception"
                ).inc()
            if transition:
                await self._handle_transition(
                    cb, channel_type, instance.id, instance.tenant_id,
                    transition[0], transition[1], str(e), "unhealthy", latency_ms, db
                )

    async def _check_slack_instance(self, instance, db: Session):
        """Check Slack bot health via auth.test API."""
        channel_type = "slack"
        cb = self._get_or_create_cb(channel_type, instance.id)

        if not cb.should_probe():
            return
        cb.try_recover()

        start_time = time.monotonic()
        try:
            # Decrypt token
            token = self._decrypt_slack_token(instance, db)
            if not token:
                transition = cb.record_failure("token_decryption_failed")
                if transition:
                    await self._handle_transition(
                        cb, channel_type, instance.id, instance.tenant_id,
                        transition[0], transition[1], "Token decryption failed",
                        "unhealthy", 0, db
                    )
                return

            # Use the Slack adapter's health check
            from channels.slack.adapter import SlackChannelAdapter
            adapter = SlackChannelAdapter(bot_token=token, logger=logger)
            result = await adapter.health_check()
            latency_ms = (time.monotonic() - start_time) * 1000

            if settings.METRICS_ENABLED:
                TSN_CHANNEL_HEALTH_CHECK_DURATION.labels(channel_type=channel_type).observe(latency_ms / 1000)

            if result.healthy:
                health_status = "healthy"
                detail = result.detail or "connected"
                transition = cb.record_success()
            else:
                health_status = "unhealthy"
                detail = result.detail or result.status
                transition = cb.record_failure(detail)
                if settings.METRICS_ENABLED:
                    TSN_CHANNEL_HEALTH_CHECK_FAILURES_TOTAL.labels(
                        channel_type=channel_type, reason=result.status
                    ).inc()

            if transition:
                await self._handle_transition(
                    cb, channel_type, instance.id, instance.tenant_id,
                    transition[0], transition[1], detail, health_status, latency_ms, db
                )

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(f"Slack health check failed for instance {instance.id}: {e}")
            transition = cb.record_failure(str(e))
            if settings.METRICS_ENABLED:
                TSN_CHANNEL_HEALTH_CHECK_FAILURES_TOTAL.labels(
                    channel_type=channel_type, reason="exception"
                ).inc()
            if transition:
                await self._handle_transition(
                    cb, channel_type, instance.id, instance.tenant_id,
                    transition[0], transition[1], str(e), "unhealthy", latency_ms, db
                )

    async def _check_discord_instance(self, instance, db: Session):
        """Check Discord bot health via /users/@me endpoint."""
        channel_type = "discord"
        cb = self._get_or_create_cb(channel_type, instance.id)

        if not cb.should_probe():
            return
        cb.try_recover()

        start_time = time.monotonic()
        try:
            # Decrypt token
            token = self._decrypt_discord_token(instance, db)
            if not token:
                transition = cb.record_failure("token_decryption_failed")
                if transition:
                    await self._handle_transition(
                        cb, channel_type, instance.id, instance.tenant_id,
                        transition[0], transition[1], "Token decryption failed",
                        "unhealthy", 0, db
                    )
                return

            # Use the Discord adapter's health check
            from channels.discord.adapter import DiscordChannelAdapter
            adapter = DiscordChannelAdapter(bot_token=token, logger=logger)
            try:
                result = await adapter.health_check()
                latency_ms = (time.monotonic() - start_time) * 1000

                if settings.METRICS_ENABLED:
                    TSN_CHANNEL_HEALTH_CHECK_DURATION.labels(channel_type=channel_type).observe(latency_ms / 1000)

                if result.healthy:
                    health_status = "healthy"
                    detail = result.detail or "connected"
                    transition = cb.record_success()
                else:
                    health_status = "unhealthy"
                    detail = result.detail or result.status
                    transition = cb.record_failure(detail)
                    if settings.METRICS_ENABLED:
                        TSN_CHANNEL_HEALTH_CHECK_FAILURES_TOTAL.labels(
                            channel_type=channel_type, reason=result.status
                        ).inc()

                if transition:
                    await self._handle_transition(
                        cb, channel_type, instance.id, instance.tenant_id,
                        transition[0], transition[1], detail, health_status, latency_ms, db
                    )
            finally:
                await adapter.stop()  # Close aiohttp session

        except Exception as e:
            latency_ms = (time.monotonic() - start_time) * 1000
            logger.warning(f"Discord health check failed for instance {instance.id}: {e}")
            transition = cb.record_failure(str(e))
            if settings.METRICS_ENABLED:
                TSN_CHANNEL_HEALTH_CHECK_FAILURES_TOTAL.labels(
                    channel_type=channel_type, reason="exception"
                ).inc()
            if transition:
                await self._handle_transition(
                    cb, channel_type, instance.id, instance.tenant_id,
                    transition[0], transition[1], str(e), "unhealthy", latency_ms, db
                )

    # =========================================================================
    # Token Decryption Helpers
    # =========================================================================

    def _decrypt_telegram_token(self, instance: TelegramBotInstance, db: Session) -> Optional[str]:
        """Decrypt Telegram bot token using per-workspace Fernet encryption."""
        try:
            from services.encryption_key_service import get_telegram_encryption_key
            from hub.security import TokenEncryption

            encryption_key = get_telegram_encryption_key(db)
            if not encryption_key:
                logger.error("Telegram encryption key not available")
                return None

            encryption = TokenEncryption(encryption_key.encode())
            return encryption.decrypt(instance.bot_token_encrypted, instance.tenant_id)
        except Exception as e:
            logger.error(f"Failed to decrypt Telegram token for instance {instance.id}: {e}")
            return None

    def _decrypt_slack_token(self, instance, db: Session) -> Optional[str]:
        """Decrypt Slack bot token using per-workspace Fernet encryption."""
        try:
            from services.encryption_key_service import get_slack_encryption_key
            from hub.security import TokenEncryption

            encryption_key = get_slack_encryption_key(db)
            if not encryption_key:
                logger.error("Slack encryption key not available")
                return None

            encryption = TokenEncryption(encryption_key.encode())
            return encryption.decrypt(instance.bot_token_encrypted, instance.tenant_id)
        except Exception as e:
            logger.error(f"Failed to decrypt Slack token for instance {instance.id}: {e}")
            return None

    def _decrypt_discord_token(self, instance, db: Session) -> Optional[str]:
        """Decrypt Discord bot token using per-workspace Fernet encryption."""
        try:
            from services.encryption_key_service import get_discord_encryption_key
            from hub.security import TokenEncryption

            encryption_key = get_discord_encryption_key(db)
            if not encryption_key:
                logger.error("Discord encryption key not available")
                return None

            encryption = TokenEncryption(encryption_key.encode())
            return encryption.decrypt(instance.bot_token_encrypted, instance.tenant_id)
        except Exception as e:
            logger.error(f"Failed to decrypt Discord token for instance {instance.id}: {e}")
            return None

    # =========================================================================
    # Circuit Breaker Management
    # =========================================================================

    def _get_or_create_cb(
        self, channel_type: str, instance_id: int,
        state_str: str = "closed", failure_count: int = 0,
        opened_at: Optional[datetime] = None
    ) -> CircuitBreaker:
        """Get or create a circuit breaker for a channel instance."""
        key = (channel_type, instance_id)
        if key not in self._circuit_breakers:
            self._circuit_breakers[key] = CircuitBreaker.from_db(
                state_str, failure_count, opened_at, self._default_config
            )
        return self._circuit_breakers[key]

    async def _handle_transition(
        self,
        cb: CircuitBreaker,
        channel_type: str,
        instance_id: int,
        tenant_id: str,
        old_state: CircuitBreakerState,
        new_state: CircuitBreakerState,
        detail: str,
        health_status: str,
        latency_ms: float,
        db: Session,
    ):
        """Persist state, write audit event, emit WebSocket, dispatch alert."""
        logger.info(
            f"Circuit breaker transition: {channel_type}/{instance_id} "
            f"{old_state.value} -> {new_state.value} ({detail})"
        )

        # 1. Record Prometheus metrics
        if settings.METRICS_ENABLED:
            TSN_CIRCUIT_BREAKER_TRANSITIONS_TOTAL.labels(
                channel_type=channel_type,
                from_state=old_state.value,
                to_state=new_state.value,
            ).inc()
            TSN_CIRCUIT_BREAKER_STATE.labels(
                channel_type=channel_type,
                instance_id=str(instance_id),
            ).set(_STATE_GAUGE_MAP.get(new_state, 0))

        # 2. Write ChannelHealthEvent record (use isolated session to avoid
        #    contaminating the caller's session on failure)
        audit_db = None
        try:
            from models import ChannelHealthEvent
            audit_db = self.get_db_session()
            event = ChannelHealthEvent(
                tenant_id=tenant_id,
                channel_type=channel_type,
                instance_id=instance_id,
                event_type=f"{old_state.value}_to_{new_state.value}",
                old_state=old_state.value,
                new_state=new_state.value,
                reason=detail,
                health_status=health_status,
                latency_ms=latency_ms,
            )
            audit_db.add(event)
            audit_db.commit()
        except ImportError:
            logger.debug("ChannelHealthEvent model not yet available - skipping DB write")
        except Exception as e:
            logger.warning(f"Failed to write ChannelHealthEvent: {e}")
            if audit_db:
                try:
                    audit_db.rollback()
                except Exception:
                    pass
        finally:
            if audit_db:
                try:
                    audit_db.close()
                except Exception:
                    pass

        # 3. Emit via WatcherActivityService (if available)
        if self.watcher_activity_service:
            try:
                await self.watcher_activity_service.emit_channel_health(
                    tenant_id=tenant_id,
                    channel_type=channel_type,
                    instance_id=instance_id,
                    circuit_state=new_state.value,
                    health_status=health_status,
                    latency_ms=latency_ms,
                    detail=detail,
                )
            except Exception as e:
                logger.warning(f"Failed to emit channel health WebSocket event: {e}")

        # 4. Dispatch alert (if available and circuit opened)
        if self.alert_dispatcher and new_state == CircuitBreakerState.OPEN:
            try:
                asyncio.create_task(self.alert_dispatcher.dispatch(
                    tenant_id=tenant_id,
                    channel_type=channel_type,
                    instance_id=instance_id,
                    event_type=f"{old_state.value}_to_{new_state.value}",
                    detail=detail,
                ))
            except Exception as e:
                logger.warning(f"Failed to dispatch channel alert: {e}")

    # =========================================================================
    # Public Query Methods
    # =========================================================================

    def get_all_health(self, tenant_id: str, db: Session) -> List[Dict[str, Any]]:
        """Get health for all instances of a tenant."""
        results = []

        # WhatsApp instances
        wa_instances = db.query(WhatsAppMCPInstance).filter(
            WhatsAppMCPInstance.tenant_id == tenant_id,
        ).all()
        for inst in wa_instances:
            cb = self._circuit_breakers.get(("whatsapp", inst.id))
            results.append({
                "channel_type": "whatsapp",
                "instance_id": inst.id,
                "instance_name": inst.phone_number,
                "status": inst.status,
                "circuit_breaker": cb.to_dict() if cb else CircuitBreaker().to_dict(),
            })

        # Telegram instances
        tg_instances = db.query(TelegramBotInstance).filter(
            TelegramBotInstance.tenant_id == tenant_id,
        ).all()
        for inst in tg_instances:
            cb = self._circuit_breakers.get(("telegram", inst.id))
            results.append({
                "channel_type": "telegram",
                "instance_id": inst.id,
                "instance_name": inst.bot_username,
                "status": inst.status,
                "circuit_breaker": cb.to_dict() if cb else CircuitBreaker().to_dict(),
            })

        # Slack instances
        try:
            from models import SlackIntegration
            slack_instances = db.query(SlackIntegration).filter(
                SlackIntegration.tenant_id == tenant_id,
            ).all()
            for inst in slack_instances:
                cb = self._circuit_breakers.get(("slack", inst.id))
                results.append({
                    "channel_type": "slack",
                    "instance_id": inst.id,
                    "instance_name": inst.workspace_name or inst.workspace_id,
                    "status": inst.status,
                    "circuit_breaker": cb.to_dict() if cb else CircuitBreaker().to_dict(),
                })
        except Exception:
            pass

        # Discord instances
        try:
            from models import DiscordIntegration
            discord_instances = db.query(DiscordIntegration).filter(
                DiscordIntegration.tenant_id == tenant_id,
            ).all()
            for inst in discord_instances:
                cb = self._circuit_breakers.get(("discord", inst.id))
                results.append({
                    "channel_type": "discord",
                    "instance_id": inst.id,
                    "instance_name": inst.application_id,
                    "status": inst.status,
                    "circuit_breaker": cb.to_dict() if cb else CircuitBreaker().to_dict(),
                })
        except Exception:
            pass

        return results

    def get_instance_health(self, channel_type: str, instance_id: int) -> Optional[Dict[str, Any]]:
        """Get health for specific instance."""
        key = (channel_type, instance_id)
        cb = self._circuit_breakers.get(key)
        if cb is None:
            return None
        return {
            "channel_type": channel_type,
            "instance_id": instance_id,
            "circuit_breaker": cb.to_dict(),
        }

    def is_circuit_open(self, channel_type: str, instance_id: int) -> bool:
        """Check if circuit breaker is in OPEN state."""
        key = (channel_type, instance_id)
        cb = self._circuit_breakers.get(key)
        if cb is None:
            return False
        return cb.state == CircuitBreakerState.OPEN

    def on_external_recovery(self, channel_type: str, instance_id: int):
        """Called when MCPHealthMonitorService or other external mechanism triggers recovery."""
        key = (channel_type, instance_id)
        cb = self._circuit_breakers.get(key)
        if cb is not None:
            cb.state = CircuitBreakerState.HALF_OPEN
            cb.success_count = 0
            logger.info(
                f"External recovery signal for {channel_type}/{instance_id} - "
                f"CB moved to HALF_OPEN"
            )

    async def manual_probe(self, channel_type: str, instance_id: int, tenant_id: str) -> Dict[str, Any]:
        """Execute a manual health probe for a specific instance. Returns probe result."""
        db = self.get_db_session()
        try:
            if channel_type == "whatsapp":
                instance = db.query(WhatsAppMCPInstance).filter(
                    WhatsAppMCPInstance.id == instance_id,
                    WhatsAppMCPInstance.tenant_id == tenant_id,
                ).first()
                if not instance:
                    return {"error": "Instance not found"}
                await self._check_whatsapp_instance(instance, db)

            elif channel_type == "telegram":
                instance = db.query(TelegramBotInstance).filter(
                    TelegramBotInstance.id == instance_id,
                    TelegramBotInstance.tenant_id == tenant_id,
                ).first()
                if not instance:
                    return {"error": "Instance not found"}
                await self._check_telegram_instance(instance, db)

            elif channel_type == "slack":
                from models import SlackIntegration
                instance = db.query(SlackIntegration).filter(
                    SlackIntegration.id == instance_id,
                    SlackIntegration.tenant_id == tenant_id,
                ).first()
                if not instance:
                    return {"error": "Instance not found"}
                await self._check_slack_instance(instance, db)

            elif channel_type == "discord":
                from models import DiscordIntegration
                instance = db.query(DiscordIntegration).filter(
                    DiscordIntegration.id == instance_id,
                    DiscordIntegration.tenant_id == tenant_id,
                ).first()
                if not instance:
                    return {"error": "Instance not found"}
                await self._check_discord_instance(instance, db)

            else:
                return {"error": f"Unknown channel type: {channel_type}"}

            # Return current CB state after probe
            cb = self._circuit_breakers.get((channel_type, instance_id))
            return {
                "channel_type": channel_type,
                "instance_id": instance_id,
                "circuit_breaker": cb.to_dict() if cb else CircuitBreaker().to_dict(),
                "probed": True,
            }
        finally:
            db.close()

    def reset_circuit_breaker(self, channel_type: str, instance_id: int) -> Dict[str, Any]:
        """Reset circuit breaker to CLOSED state (admin override)."""
        key = (channel_type, instance_id)
        cb = self._circuit_breakers.get(key)
        if cb is None:
            cb = CircuitBreaker(config=self._default_config)
            self._circuit_breakers[key] = cb
        else:
            cb.state = CircuitBreakerState.CLOSED
            cb._reset_counters()

        logger.info(f"Circuit breaker manually reset for {channel_type}/{instance_id}")

        if settings.METRICS_ENABLED:
            TSN_CIRCUIT_BREAKER_STATE.labels(
                channel_type=channel_type,
                instance_id=str(instance_id),
            ).set(0)

        return {
            "channel_type": channel_type,
            "instance_id": instance_id,
            "circuit_breaker": cb.to_dict(),
            "reset": True,
        }
