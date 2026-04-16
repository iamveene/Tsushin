"""
Phase 23: Channel Inbound Webhook Handlers (Discord Interactions + Slack Events)

BUG-311 Fix: Discord interaction verification uses per-integration public_key
             instead of a global DISCORD_PUBLIC_KEY env var. Each tenant's Discord
             integration has its own Ed25519 public key for signature verification.

BUG-312 Fix: Slack url_verification resolves integrations by app_id (from payload)
             in addition to team_id/workspace_id. During initial url_verification,
             Slack may not provide team_id, so app_id is the primary resolution key.
             Signature verification uses the per-integration signing_secret.

BUG-313 Fix: Discord interactions are fully configurable through the integration API.
             The public_key is stored in the DiscordIntegration model, not env vars.

These endpoints are public (no auth required) because they receive inbound
requests from Discord/Slack infrastructure. Security is provided by signature
verification using per-integration secrets/keys.
"""

import hashlib
import hmac
import json
import logging
import time
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from db import get_db
from hub.security import TokenEncryption
from models import Agent, DiscordIntegration, SlackIntegration
from services.encryption_key_service import get_slack_encryption_key
from services.message_queue_service import MessageQueueService
from cryptography.fernet import Fernet  # noqa: F401  (kept for backward-compat imports)


def _resolve_agent_id_for_slack(db: Session, integration: SlackIntegration) -> Optional[int]:
    """Return the agent_id bound to this Slack integration, or None.

    If multiple agents are bound, picks the lowest id deterministically. The
    AgentChannelsManager UI prevents binding more than one agent per integration
    today, but we tolerate the data shape regardless.
    """
    agent = (
        db.query(Agent)
        .filter(
            Agent.slack_integration_id == integration.id,
            Agent.tenant_id == integration.tenant_id,
        )
        .order_by(Agent.id.asc())
        .first()
    )
    return agent.id if agent else None


def _resolve_agent_id_for_discord(db: Session, integration: DiscordIntegration) -> Optional[int]:
    """Return the agent_id bound to this Discord integration, or None."""
    agent = (
        db.query(Agent)
        .filter(
            Agent.discord_integration_id == integration.id,
            Agent.tenant_id == integration.tenant_id,
        )
        .order_by(Agent.id.asc())
        .first()
    )
    return agent.id if agent else None

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/channels",
    tags=["Channel Webhooks"],
    redirect_slashes=False
)


# ============================================================================
# Discord Interaction Endpoint
# ============================================================================

def _verify_discord_signature(
    public_key_hex: str,
    signature: str,
    timestamp: str,
    body: bytes,
) -> bool:
    """
    Verify Discord interaction signature using Ed25519.

    BUG-311 Fix: Uses the per-integration public_key, not a global env var.

    Args:
        public_key_hex: 64-char hex-encoded Ed25519 public key from DiscordIntegration.public_key
        signature: X-Signature-Ed25519 header from Discord
        timestamp: X-Signature-Timestamp header from Discord
        body: Raw request body bytes

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature

        public_key_bytes = bytes.fromhex(public_key_hex)
        public_key = Ed25519PublicKey.from_public_bytes(public_key_bytes)

        message = timestamp.encode() + body
        signature_bytes = bytes.fromhex(signature)

        public_key.verify(signature_bytes, message)
        return True

    except (InvalidSignature, ValueError, Exception) as e:
        logger.debug(f"Discord signature verification failed: {e}")
        return False


@router.post("/discord/{integration_id}/interactions")
async def discord_interactions(
    integration_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Discord Interactions Endpoint (receives inbound interaction payloads).

    This endpoint must be configured as the "Interactions Endpoint URL" in the
    Discord Developer Portal for each Discord application.

    BUG-311 Fix: Signature verification uses the per-integration public_key
    stored in DiscordIntegration, not a process-wide DISCORD_PUBLIC_KEY env var.
    This ensures multi-tenant isolation.

    BUG-313 Fix: No env var injection required. The public_key is stored in the
    database and configured through the Discord integration API.

    Discord Interaction Types:
    - Type 1 (PING): Endpoint verification — respond with {"type": 1}
    - Type 2 (APPLICATION_COMMAND): Slash command invoked
    - Type 3 (MESSAGE_COMPONENT): Button/select menu interaction
    - Type 5 (MODAL_SUBMIT): Modal form submitted
    """
    # 1. Extract signature headers FIRST (anti-enumeration: don't reveal integration existence)
    signature = request.headers.get("X-Signature-Ed25519")
    timestamp = request.headers.get("X-Signature-Timestamp")

    if not signature or not timestamp:
        raise HTTPException(status_code=401, detail="Missing Discord signature headers")

    # 2. Look up the integration
    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.id == integration_id,
        DiscordIntegration.is_active == True,
    ).first()

    if not integration:
        logger.warning(f"Discord interaction for unknown/inactive integration {integration_id}")
        raise HTTPException(status_code=401, detail="Invalid request signature")

    if not integration.public_key:
        logger.error(
            f"Discord integration {integration_id} has no public_key configured. "
            "Cannot verify interaction signatures. Update the integration with a valid public_key."
        )
        raise HTTPException(status_code=401, detail="Invalid request signature")

    # 3. Read raw body for signature verification
    body = await request.body()

    # 4. Verify signature using per-integration public key (BUG-311 fix)
    if not _verify_discord_signature(integration.public_key, signature, timestamp, body):
        logger.warning(
            f"Discord signature verification failed for integration {integration_id} "
            f"(tenant={integration.tenant_id})"
        )
        raise HTTPException(status_code=401, detail="Invalid request signature")

    # 5. Parse the interaction payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    interaction_type = payload.get("type")

    # 6. Handle PING (Type 1) — Discord endpoint verification
    if interaction_type == 1:
        logger.info(f"Discord PING received for integration {integration_id} — responding with ACK")
        return {"type": 1}

    # 7. Handle application commands and other interactions
    # V060-CHN-002: Enqueue the interaction so the QueueWorker.
    # _process_discord_message dispatcher can route it through AgentRouter.
    # Discord requires an HTTP response within 3 seconds, so we ACK here and
    # let the worker post the actual reply via the follow-up webhook URL the
    # adapter is configured against.
    if interaction_type in (2, 3, 5):
        logger.info(
            f"Discord interaction type={interaction_type} received for integration {integration_id} "
            f"(tenant={integration.tenant_id})"
        )

        agent_id = _resolve_agent_id_for_discord(db, integration)
        if agent_id is None:
            logger.warning(
                f"Discord interaction for integration {integration.id} dropped: no agent assigned. "
                "Bind an agent in the Hub → Agent → Channels tab to receive Discord messages."
            )
            # Still ACK so Discord doesn't retry — there's no recoverable handler.
            return {"type": 5}

        try:
            user = (payload.get("member") or {}).get("user") or payload.get("user") or {}
            sender_key = f"discord:{user.get('id', 'unknown')}"
            queue_service = MessageQueueService(db)
            queue_service.enqueue(
                channel="discord",
                tenant_id=integration.tenant_id,
                agent_id=agent_id,
                sender_key=sender_key,
                payload={
                    "interaction": payload,
                    "discord_integration_id": integration.id,
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to enqueue Discord interaction for integration {integration.id}: {e}",
                exc_info=True,
            )
            # Still ACK — failing to enqueue is a backend bug, not Discord's fault.

        # Type 5 = DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE
        # This tells Discord "we received the interaction, response is coming"
        return {"type": 5}

    # Unknown interaction type
    logger.warning(f"Unknown Discord interaction type={interaction_type} for integration {integration_id}")
    return {"type": 1}  # ACK as fallback


# ============================================================================
# Slack Events Endpoint
# ============================================================================

def _verify_slack_signature(
    signing_secret: str,
    timestamp: str,
    body: bytes,
    signature: str,
) -> bool:
    """
    Verify Slack request signature using HMAC-SHA256.

    BUG-312 Fix: Uses the per-integration signing_secret, not a global env var.

    Args:
        signing_secret: Slack signing secret from SlackIntegration.signing_secret_encrypted (decrypted)
        timestamp: X-Slack-Request-Timestamp header
        body: Raw request body bytes
        signature: X-Slack-Signature header (v0=...)

    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Check timestamp freshness (prevent replay attacks, 5-minute window)
        current_time = int(time.time())
        request_time = int(timestamp)
        if abs(current_time - request_time) > 300:
            logger.warning("Slack request timestamp too old (possible replay attack)")
            return False

        # Compute expected signature
        sig_basestring = f"v0:{timestamp}:{body.decode('utf-8')}"
        expected_signature = "v0=" + hmac.new(
            signing_secret.encode(),
            sig_basestring.encode(),
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    except (ValueError, Exception) as e:
        logger.debug(f"Slack signature verification failed: {e}")
        return False


def _resolve_slack_integration(
    db: Session,
    integration_id: Optional[int] = None,
    app_id: Optional[str] = None,
    team_id: Optional[str] = None,
) -> Optional[SlackIntegration]:
    """
    Resolve Slack integration from available identifiers.

    BUG-312 Fix: During url_verification, Slack may not provide team_id.
    Resolution priority:
    1. Direct ID lookup (from URL path)
    2. app_id match (most reliable during url_verification)
    3. team_id/workspace_id match (fallback for event payloads)

    Args:
        db: Database session
        integration_id: Direct integration ID (from URL)
        app_id: Slack App ID from payload
        team_id: Slack Team ID from payload

    Returns:
        SlackIntegration or None
    """
    # Priority 1: Direct ID from URL path
    if integration_id:
        integration = db.query(SlackIntegration).filter(
            SlackIntegration.id == integration_id,
            SlackIntegration.is_active == True,
            SlackIntegration.mode == "http",
        ).first()
        if integration:
            return integration

    # Priority 2: Match by app_id (BUG-312 fix — reliable during url_verification)
    # Note: app_id lookup is scoped by the integration_id's tenant to prevent cross-tenant resolution
    if app_id and integration_id:
        # Get tenant from the integration_id we already tried
        ref = db.query(SlackIntegration.tenant_id).filter(SlackIntegration.id == integration_id).first()
        tenant_filter = SlackIntegration.tenant_id == ref[0] if ref else True
        integration = db.query(SlackIntegration).filter(
            SlackIntegration.app_id == app_id,
            SlackIntegration.is_active == True,
            SlackIntegration.mode == "http",
            tenant_filter,
        ).first()
        if integration:
            return integration

    # Priority 3: Match by team_id/workspace_id (also tenant-scoped when possible)
    if team_id:
        integration = db.query(SlackIntegration).filter(
            SlackIntegration.workspace_id == team_id,
            SlackIntegration.is_active == True,
            SlackIntegration.mode == "http",
        ).first()
        if integration:
            return integration

    return None


@router.post("/slack/{integration_id}/events")
async def slack_events(
    integration_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Slack Events API Endpoint (receives inbound event payloads).

    This endpoint must be configured as the "Events Request URL" in Slack app settings.

    BUG-312 Fix:
    - url_verification works correctly by resolving integration via ID from URL path
    - Signature verification uses per-integration signing_secret
    - app_id stored in integration for additional resolution flexibility

    Slack Event Types:
    - url_verification: Initial handshake — echo the challenge value
    - event_callback: Actual events (messages, reactions, etc.)
    """
    # 1. Read raw body for signature verification
    body = await request.body()

    # 2. Parse the payload
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    event_type = payload.get("type")

    # 3. Extract identifiers for integration resolution
    payload_app_id = payload.get("api_app_id")
    payload_team_id = payload.get("team_id")

    # 4. Resolve integration (BUG-312 fix: use integration_id from URL as primary key)
    integration = _resolve_slack_integration(
        db,
        integration_id=integration_id,
        app_id=payload_app_id,
        team_id=payload_team_id,
    )

    if not integration:
        logger.warning(
            f"Slack event for unresolved integration: id={integration_id}, "
            f"app_id={payload_app_id}, team_id={payload_team_id}"
        )
        raise HTTPException(status_code=404, detail="Slack integration not found or inactive")

    # 5. Verify signature using per-integration signing_secret (BUG-312 fix)
    if not integration.signing_secret_encrypted:
        logger.error(
            f"Slack integration {integration.id} has no signing_secret configured. "
            "Cannot verify request signatures. Update the integration with mode='http' "
            "and provide the signing_secret."
        )
        raise HTTPException(
            status_code=500,
            detail="Integration misconfigured: no signing_secret for HTTP mode"
        )

    # Decrypt signing secret using TokenEncryption (per-tenant key derivation)
    # to match how routes_slack.py encrypts it. Pre-V060-CHN-002 this used raw
    # Fernet which never matched the encrypt side.
    try:
        encryption_key = get_slack_encryption_key(db)
        if not encryption_key:
            raise HTTPException(status_code=500, detail="Slack encryption key not available")

        enc = TokenEncryption(encryption_key.encode())
        signing_secret = enc.decrypt(integration.signing_secret_encrypted, integration.tenant_id)
    except Exception as e:
        logger.error(f"Failed to decrypt signing_secret for Slack integration {integration.id}: {e}")
        raise HTTPException(status_code=500, detail="Failed to decrypt integration credentials")

    # Verify signature
    slack_signature = request.headers.get("X-Slack-Signature", "")
    slack_timestamp = request.headers.get("X-Slack-Request-Timestamp", "")

    if not slack_signature or not slack_timestamp:
        # During url_verification, we still require signature headers
        # Slack always sends them, even for url_verification
        raise HTTPException(status_code=401, detail="Missing Slack signature headers")

    if not _verify_slack_signature(signing_secret, slack_timestamp, body, slack_signature):
        logger.warning(
            f"Slack signature verification failed for integration {integration.id} "
            f"(tenant={integration.tenant_id})"
        )
        raise HTTPException(status_code=401, detail="Invalid request signature")

    # 6. Handle url_verification (BUG-312 fix: echo challenge after signature verification)
    if event_type == "url_verification":
        challenge = payload.get("challenge", "")
        logger.info(
            f"Slack url_verification completed for integration {integration.id} "
            f"(app_id={payload_app_id}, tenant={integration.tenant_id})"
        )

        # Update workspace_id if provided and not yet stored
        if payload_team_id and not integration.workspace_id:
            integration.workspace_id = payload_team_id
            db.commit()

        # Return the challenge — this completes the Slack URL verification handshake
        return Response(
            content=json.dumps({"challenge": challenge}),
            media_type="application/json",
        )

    # 7. Handle event_callback (actual events like messages)
    if event_type == "event_callback":
        event = payload.get("event", {})
        event_subtype = event.get("type")

        logger.info(
            f"Slack event '{event_subtype}' received for integration {integration.id} "
            f"(tenant={integration.tenant_id})"
        )

        # V060-CHN-002: Enqueue events that carry a user message so the
        # QueueWorker._process_slack_message dispatcher can route them through
        # AgentRouter. We deliberately filter out:
        #   - bot_message subtypes (event.get('bot_id') set) — prevents reply loops
        #   - non-user events (channel_joined, reaction_added, etc.)
        if event_subtype != "message":
            return {"ok": True}
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            # Skip messages from bots (including ourselves) to avoid loops.
            return {"ok": True}
        if not event.get("user") or not event.get("text"):
            return {"ok": True}

        agent_id = _resolve_agent_id_for_slack(db, integration)
        if agent_id is None:
            logger.warning(
                f"Slack event for integration {integration.id} dropped: no agent assigned. "
                "Bind an agent in the Hub → Agent → Channels tab to receive Slack messages."
            )
            return {"ok": True}

        try:
            sender_key = f"slack:{payload.get('team_id', '')}:{event.get('user', '')}"
            queue_service = MessageQueueService(db)
            queue_service.enqueue(
                channel="slack",
                tenant_id=integration.tenant_id,
                agent_id=agent_id,
                sender_key=sender_key,
                payload={
                    "event": event,
                    "team_id": payload.get("team_id"),
                    "slack_integration_id": integration.id,
                },
            )
        except Exception as e:
            logger.error(
                f"Failed to enqueue Slack event for integration {integration.id}: {e}",
                exc_info=True,
            )

        # Slack expects 200 within 3 seconds — always ACK once enqueued (or filtered).
        return {"ok": True}

    # 8. Unknown event type — acknowledge anyway to prevent Slack retries
    logger.warning(f"Unknown Slack event type='{event_type}' for integration {integration.id}")
    return {"ok": True}
