"""
Public webhook ingestion endpoint (v0.6.0).

POST /api/webhooks/{webhook_id}/inbound
  Unauthenticated at the bearer/JWT layer — authenticated via HMAC-SHA256
  signature over the raw body (X-Tsushin-Signature) + timestamp replay
  protection (X-Tsushin-Timestamp). Optional per-webhook IP allowlist and
  per-webhook rate limit.

On success: enqueues a message into message_queue with channel='webhook'
and returns 202 with the queue_id and poll URL. The QueueWorker's
_process_webhook_message dispatcher routes the message through AgentRouter
→ LLM → (optional) callback POST via WebhookChannelAdapter.
"""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json as _json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request
from sqlalchemy.orm import Session

from db import get_db
from fastapi import Depends
from middleware.rate_limiter import api_rate_limiter
from models import Agent, WebhookIntegration
from services.message_queue_service import MessageQueueService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["webhook-inbound"])

# Replay-protection window: ±5 minutes
_TIMESTAMP_SKEW_SECONDS = 300


def _generic_403():
    # Return identical 403 for all auth failures (no detail leak)
    raise HTTPException(status_code=403, detail="Forbidden")


def _decrypt_secret(db: Session, integration: WebhookIntegration) -> Optional[str]:
    try:
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_webhook_encryption_key

        master_key = get_webhook_encryption_key(db)
        if not master_key:
            logger.error("Webhook encryption key unavailable")
            return None
        return TokenEncryption(master_key.encode()).decrypt(
            integration.api_secret_encrypted, integration.tenant_id
        )
    except Exception as e:
        logger.error(f"Failed to decrypt webhook secret: {type(e).__name__}")
        return None


def _client_ip(request: Request) -> str:
    # Use request.client.host which is already set correctly by ProxyHeadersMiddleware
    # for trusted proxies. Reading X-Forwarded-For directly bypasses trust verification.
    return request.client.host if request.client else ""


def _ip_in_allowlist(client_ip: str, allowlist_json: str) -> bool:
    try:
        cidrs = _json.loads(allowlist_json)
        if not isinstance(cidrs, list) or not cidrs:
            return True  # empty/malformed list = allow all
        ip = ipaddress.ip_address(client_ip)
        for cidr in cidrs:
            try:
                if ip in ipaddress.ip_network(str(cidr), strict=False):
                    return True
            except ValueError:
                continue
        return False
    except Exception:
        # Fail closed on allowlist parse errors
        return False


# BUG-593: queued responses are semantically 202 Accepted, not 200. The
# contract/docs already said 202; the route was silently emitting 200.
@router.post("/api/webhooks/{slug}/inbound", status_code=202)
async def receive_webhook(
    slug: str,
    request: Request,
    x_tsushin_signature: Optional[str] = Header(None, alias="X-Tsushin-Signature"),
    x_tsushin_timestamp: Optional[str] = Header(None, alias="X-Tsushin-Timestamp"),
    db: Session = Depends(get_db),
):
    """Receive an HMAC-signed external webhook event and enqueue it for agent processing.

    v0.7.1: path param is now a human-readable slug. Numeric-only slugs are
    treated as a backward-compat fallback to the legacy ``/api/webhooks/{id}``
    shape so every existing integration keeps working.

    Request requirements:
      • X-Tsushin-Signature: "sha256=<hex>" where hex = HMAC-SHA256(secret, timestamp + "." + raw_body)
      • X-Tsushin-Timestamp: unix seconds (±5 min from server time)
      • Content-Type: application/json
      • Body: JSON object with at minimum {"message": "…"} (or {"message_text": "…"})
        Optional fields: sender_id, sender_name, source_id, timestamp
    """
    integration: Optional[WebhookIntegration] = (
        db.query(WebhookIntegration).filter_by(slug=slug).first()
    )
    if integration is None and slug.isdigit():
        # Backward compatibility: legacy numeric-id URLs
        integration = db.query(WebhookIntegration).filter_by(id=int(slug)).first()
    if integration is None or not integration.is_active or integration.status == "paused":
        _generic_403()

    webhook_id = integration.id

    # Honor emergency stop at the ingress (avoid eating queue/LLM resources).
    # v0.7.3: Check BOTH the global kill switch and the integration's tenant flag.
    try:
        from models import Config as ConfigModel
        _config = db.query(ConfigModel).first()
        if _config and getattr(_config, 'emergency_stop', False):
            logger.warning(f"[EMERGENCY STOP:global] Rejecting webhook {webhook_id} inbound — GLOBAL emergency stop active")
            raise HTTPException(status_code=503, detail="Service temporarily unavailable")
        if integration.tenant_id:
            from models_rbac import Tenant as TenantModel
            _tenant = db.query(TenantModel).filter(TenantModel.id == integration.tenant_id).first()
            if _tenant and getattr(_tenant, 'emergency_stop', False):
                logger.warning(f"[EMERGENCY STOP:tenant] Rejecting webhook {webhook_id} inbound — tenant {integration.tenant_id} emergency stop active")
                raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    except HTTPException:
        raise
    except Exception:
        pass

    # --- Layer 1: IP allowlist (optional, defense-in-depth) ---
    if integration.ip_allowlist_json:
        client_ip = _client_ip(request)
        if client_ip and not _ip_in_allowlist(client_ip, integration.ip_allowlist_json):
            logger.warning(
                f"Webhook {webhook_id}: rejected IP {client_ip} (not in allowlist)"
            )
            _generic_403()

    # --- Layer 2: per-webhook rate limit ---
    rpm = integration.rate_limit_rpm or 30
    if not api_rate_limiter.allow(f"webhook:{webhook_id}", rpm, 60):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")

    # --- Layer 3: payload size cap ---
    max_bytes = integration.max_payload_bytes or 1_048_576
    raw_body = await request.body()
    if len(raw_body) > max_bytes:
        raise HTTPException(status_code=413, detail="Payload too large")

    # --- Layer 4: timestamp replay protection ---
    if not x_tsushin_timestamp:
        _generic_403()
    try:
        ts_int = int(x_tsushin_timestamp)
    except (ValueError, TypeError):
        _generic_403()
    now = int(time.time())
    if abs(now - ts_int) > _TIMESTAMP_SKEW_SECONDS:
        logger.warning(f"Webhook {webhook_id}: stale timestamp (skew={now - ts_int}s)")
        _generic_403()

    # --- Layer 5: HMAC-SHA256 signature ---
    if not x_tsushin_signature:
        _generic_403()
    secret = _decrypt_secret(db, integration)
    if not secret:
        raise HTTPException(status_code=500, detail="Server configuration error")

    signed_input = f"{x_tsushin_timestamp}.".encode("utf-8") + raw_body
    expected = hmac.new(secret.encode("utf-8"), signed_input, hashlib.sha256).hexdigest()
    # Accept "sha256=<hex>" or bare hex
    provided = x_tsushin_signature.strip()
    if provided.startswith("sha256="):
        provided = provided[len("sha256="):]
    if not hmac.compare_digest(provided, expected):
        logger.warning(f"Webhook {webhook_id}: HMAC signature mismatch")
        _generic_403()

    # --- Layer 6: parse body ---
    try:
        body = _json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, _json.JSONDecodeError):
        raise HTTPException(status_code=400, detail="Invalid JSON body")
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    message_text = (
        body.get("message_text")
        or body.get("message")
        or body.get("text")
        or ""
    )
    if not isinstance(message_text, str) or not message_text.strip():
        raise HTTPException(status_code=400, detail="message text required")

    sender_id = str(body.get("sender_id") or body.get("user_id") or "webhook")
    sender_name = str(body.get("sender_name") or body.get("user_name") or "Webhook")
    source_id = str(body.get("source_id") or f"whk_{webhook_id}_{int(time.time()*1000)}")

    # --- Layer 7: resolve bound agent ---
    agent = (
        db.query(Agent)
        .filter(
            Agent.webhook_integration_id == webhook_id,
            Agent.tenant_id == integration.tenant_id,
            Agent.is_active == True,  # noqa: E712
        )
        .first()
    )
    if agent is None:
        logger.warning(f"Webhook {webhook_id}: no bound agent for tenant {integration.tenant_id}")
        raise HTTPException(status_code=404, detail="No agent bound to this webhook")

    # --- Layer 8: enqueue ---
    payload = {
        "webhook_id": webhook_id,
        "message_text": message_text.strip()[:8192],  # hard cap text length
        "sender_id": sender_id[:128],
        "sender_name": sender_name[:128],
        "source_id": source_id[:128],
        "timestamp": ts_int,
        "raw_event": body,
    }
    mqs = MessageQueueService(db)
    item = mqs.enqueue(
        channel="webhook",
        tenant_id=integration.tenant_id,
        agent_id=agent.id,
        sender_key=f"webhook_{webhook_id}_{sender_id}"[:255],
        payload=payload,
        priority=0,
    )

    return {
        "status": "queued",
        "queue_id": item.id,
        "poll_url": f"/api/v1/queue/{item.id}",
    }
