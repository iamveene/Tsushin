"""Webhook trigger implementation."""

import hashlib
import hmac
import json
import logging
import time
from typing import ClassVar, Optional

import httpx
from sqlalchemy.orm import Session

from channels.trigger import Trigger
from channels.types import HealthResult, SendResult, TriggerEvent
from utils.ssrf_validator import SSRFValidationError, validate_url


# Response-body cap for the callback POST (match slash-command pattern)
_MAX_RESPONSE_BYTES = 65536
_CALLBACK_TIMEOUT_SECONDS = 10.0


class WebhookTrigger(Trigger):
    """Webhook trigger with optional outbound callback delivery."""

    channel_type: ClassVar[str] = "webhook"
    delivery_mode: ClassVar[str] = "push"
    supports_threads: ClassVar[bool] = False
    supports_reactions: ClassVar[bool] = False
    supports_rich_formatting: ClassVar[bool] = False
    supports_media: ClassVar[bool] = False  # v1 text-only
    text_chunk_limit: ClassVar[int] = 16000  # customer system handles display

    def __init__(self, db_session: Session, webhook_integration_id: int, logger: logging.Logger):
        """
        Args:
            db_session: SQLAlchemy session (for resolving WebhookIntegration row)
            webhook_integration_id: ID of the WebhookIntegration this adapter serves
            logger: Logger instance
        """
        self.db = db_session
        self.webhook_integration_id = webhook_integration_id
        self.logger = logger

    async def start(self) -> None:
        """No-op — webhook transport is request-response, no persistent connection."""
        pass

    async def stop(self) -> None:
        """No-op — webhook transport is request-response, no persistent connection."""
        pass

    def _load_integration(self):
        """Load the WebhookIntegration row (fresh read, no caching)."""
        from models import WebhookIntegration
        return self.db.query(WebhookIntegration).filter_by(id=self.webhook_integration_id).first()

    def _decrypt_secret(self, encrypted: str, tenant_id: str) -> Optional[str]:
        """Decrypt api_secret_encrypted using webhook encryption key + per-tenant derivation."""
        try:
            from hub.security import TokenEncryption
            from services.encryption_key_service import get_webhook_encryption_key

            master_key = get_webhook_encryption_key(self.db)
            if not master_key:
                self.logger.error("Webhook encryption key unavailable")
                return None

            encryption = TokenEncryption(master_key.encode())
            return encryption.decrypt(encrypted, tenant_id)
        except Exception as e:
            self.logger.error(f"Failed to decrypt webhook secret: {e}")
            return None

    async def poll_or_receive(self) -> list[TriggerEvent]:
        """Webhook events are received via the public FastAPI route."""
        return []

    async def emit_wake_event(self, event: TriggerEvent) -> None:
        """Wake-event persistence lands with the continuous-agent control plane."""
        return None

    async def notify_external_system(self, result: dict) -> Optional[dict]:
        """POST agent output to the customer's callback_url with HMAC-SHA256."""
        integration = self._load_integration()
        if integration is None:
            return {"success": False, "error": "Webhook integration not found"}

        if not integration.callback_enabled or not integration.callback_url:
            self.logger.debug(
                f"Webhook {self.webhook_integration_id}: callback disabled, skipping outbound POST"
            )
            return {"success": True, "message_id": "webhook_inbound_only"}

        # SSRF safety gate on the callback URL (customer-controlled)
        try:
            validate_url(integration.callback_url)
        except SSRFValidationError as e:
            self.logger.error(
                f"Webhook {self.webhook_integration_id}: callback_url blocked by SSRF policy: {e}"
            )
            return {"success": False, "error": "callback_url blocked by SSRF policy"}

        secret = self._decrypt_secret(integration.api_secret_encrypted, integration.tenant_id)
        if not secret:
            return {"success": False, "error": "Could not decrypt webhook secret"}

        timestamp = str(int(time.time()))
        payload = {
            "event": "agent_response",
            "webhook_id": self.webhook_integration_id,
            "timestamp": int(timestamp),
            "text": result.get("text"),
            "agent_id": result.get("agent_id"),
            "sender_key": result.get("sender_key"),
            "source_id": result.get("source_id"),
            "metadata": result.get("metadata"),
        }
        body_bytes = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")

        signed_input = f"{timestamp}.".encode("utf-8") + body_bytes
        signature = hmac.new(secret.encode("utf-8"), signed_input, hashlib.sha256).hexdigest()

        headers = {
            "Content-Type": "application/json",
            "X-Tsushin-Signature": f"sha256={signature}",
            "X-Tsushin-Timestamp": timestamp,
            "X-Tsushin-Event": "agent_response",
            "X-Tsushin-Webhook-Id": str(self.webhook_integration_id),
            "User-Agent": "Tsushin-Webhook/1.0",
        }

        try:
            async with httpx.AsyncClient(
                timeout=_CALLBACK_TIMEOUT_SECONDS,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    integration.callback_url,
                    content=body_bytes,
                    headers=headers,
                )
            _ = response.text[:_MAX_RESPONSE_BYTES]

            if 200 <= response.status_code < 300:
                self.logger.info(
                    f"Webhook {self.webhook_integration_id} callback POST succeeded "
                    f"({response.status_code})"
                )
                return {
                    "success": True,
                    "message_id": f"whk_{self.webhook_integration_id}_{timestamp}",
                    "status_code": response.status_code,
                }
            self.logger.warning(
                f"Webhook {self.webhook_integration_id} callback POST failed: "
                f"HTTP {response.status_code}"
            )
            return {
                "success": False,
                "error": f"Callback returned HTTP {response.status_code}",
                "status_code": response.status_code,
            }
        except httpx.TimeoutException:
            self.logger.warning(f"Webhook {self.webhook_integration_id} callback POST timed out")
            return {"success": False, "error": "Callback timeout"}
        except httpx.HTTPError as e:
            self.logger.warning(
                f"Webhook {self.webhook_integration_id} callback POST transport error: {e}"
            )
            return {"success": False, "error": f"Transport error: {type(e).__name__}"}
        except Exception as e:
            self.logger.error(
                f"Webhook {self.webhook_integration_id} callback POST error: {e}",
                exc_info=True,
            )
            return {"success": False, "error": "Unexpected error"}

    async def health_check(self) -> HealthResult:
        """Return stored health snapshot — no live probe (avoid amplification)."""
        integration = self._load_integration()
        if integration is None:
            return HealthResult(healthy=False, status="error", detail="Integration not found")
        if not integration.is_active or integration.status == "paused":
            return HealthResult(healthy=False, status="paused", detail="Integration paused")
        if integration.circuit_breaker_state == "open":
            return HealthResult(
                healthy=False,
                status="circuit_open",
                detail=f"Circuit breaker opened (failures={integration.circuit_breaker_failure_count})",
            )
        healthy = integration.health_status == "healthy"
        return HealthResult(
            healthy=healthy,
            status=integration.health_status or "unknown",
            detail=integration.error_message,
        )

    def validate_recipient(self, recipient: str) -> bool:
        """Accept any recipient — actual callback URL is resolved from the integration row."""
        return True
