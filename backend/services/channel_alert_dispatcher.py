"""
Channel Alert Dispatcher - Item 38
Sends alerts when circuit breaker transitions occur (e.g., channel goes OPEN).
Supports webhook and email notification methods with cooldown to prevent spam.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, Callable, Dict, Any, Tuple

import httpx

logger = logging.getLogger(__name__)


class ChannelAlertDispatcher:
    """
    Dispatches alerts based on tenant alert configuration.
    Respects per-instance cooldown to prevent alert fatigue.
    """

    # Default cooldown: 5 minutes between alerts for the same instance
    DEFAULT_COOLDOWN_SECONDS = 300

    def __init__(self, get_db_session: Callable):
        self.get_db_session = get_db_session
        self._last_alert: Dict[Tuple[str, int], datetime] = {}

    async def dispatch(
        self,
        tenant_id: str,
        channel_type: str,
        instance_id: int,
        event_type: str,
        detail: str,
    ):
        """
        Send alert based on ChannelAlertConfig. Respects cooldown.

        Args:
            tenant_id: Tenant ID
            channel_type: Channel type (whatsapp, telegram, slack, discord)
            instance_id: Channel instance ID
            event_type: Event type (e.g., closed_to_open)
            detail: Detail message about the event
        """
        # Load alert config from DB first (need cooldown_seconds for check)
        config = self._load_alert_config(tenant_id)
        if not config or not config.get("enabled", False):
            logger.debug(f"Alerts disabled for tenant {tenant_id}")
            return

        # Check cooldown using per-tenant config (falls back to default)
        cooldown = config.get("cooldown_seconds", self.DEFAULT_COOLDOWN_SECONDS)
        key = (channel_type, instance_id)
        last = self._last_alert.get(key)
        if last:
            elapsed = (datetime.utcnow() - last).total_seconds()
            if elapsed < cooldown:
                logger.debug(
                    f"Alert cooldown active for {channel_type}/{instance_id} - "
                    f"{int(cooldown - elapsed)}s remaining"
                )
                return

        # Record alert time
        self._last_alert[key] = datetime.utcnow()

        # Build payload
        payload = {
            "tenant_id": tenant_id,
            "channel_type": channel_type,
            "instance_id": instance_id,
            "event_type": event_type,
            "detail": detail,
            "timestamp": datetime.utcnow().isoformat() + "Z",
        }

        # Send webhook
        webhook_url = config.get("webhook_url")
        if webhook_url:
            try:
                await self._send_webhook(webhook_url, payload)
            except Exception as e:
                logger.warning(f"Webhook alert failed for {channel_type}/{instance_id}: {e}")

        # Send email (placeholder)
        email_recipients = config.get("email_recipients")
        if email_recipients:
            try:
                subject = f"[Tsushin] Channel Alert: {channel_type}/{instance_id} - {event_type}"
                body = (
                    f"Channel health alert\n\n"
                    f"Channel: {channel_type}\n"
                    f"Instance: {instance_id}\n"
                    f"Event: {event_type}\n"
                    f"Detail: {detail}\n"
                    f"Timestamp: {payload['timestamp']}\n"
                )
                await self._send_email(email_recipients, subject, body)
            except Exception as e:
                logger.warning(f"Email alert failed for {channel_type}/{instance_id}: {e}")

    def _load_alert_config(self, tenant_id: str) -> Optional[Dict[str, Any]]:
        """Load alert configuration from DB for the given tenant."""
        db = self.get_db_session()
        try:
            try:
                from models import ChannelAlertConfig
                config = db.query(ChannelAlertConfig).filter(
                    ChannelAlertConfig.tenant_id == tenant_id,
                ).first()
                if config:
                    return {
                        "enabled": config.is_enabled,
                        "webhook_url": config.webhook_url,
                        "email_recipients": config.email_recipients,
                        "cooldown_seconds": config.cooldown_seconds or self.DEFAULT_COOLDOWN_SECONDS,
                    }
            except ImportError:
                logger.debug("ChannelAlertConfig model not yet available")
            except Exception as e:
                logger.debug(f"Could not load alert config: {e}")
            return None
        finally:
            db.close()

    async def _send_webhook(self, url: str, payload: Dict[str, Any]):
        """POST JSON via httpx."""
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code >= 400:
                logger.warning(f"Webhook returned {resp.status_code}: {resp.text[:200]}")
            else:
                logger.info(f"Webhook alert sent successfully to {url}")

    async def _send_email(self, recipients: list, subject: str, body: str):
        """Basic email notification (log for now, integrate with EmailService later)."""
        # Placeholder: log the email intent; actual email integration can be added later
        logger.info(
            f"Email alert (not yet integrated): to={recipients}, subject={subject}"
        )
