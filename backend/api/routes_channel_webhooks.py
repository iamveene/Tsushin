"""
V060-CHN-002: Public inbound webhook endpoints for Slack and Discord.

Slack Events API and Discord Interactions are delivered by the provider via
unauthenticated HTTP POSTs. Authentication is achieved through cryptographic
signature verification (Slack: HMAC-SHA256, Discord: Ed25519) against the
per-integration signing secret / public key stored on the tenant's
SlackIntegration/DiscordIntegration row.

On a verified event, the payload is enqueued to message_queue with
channel='slack' or 'discord'; QueueWorker picks it up and invokes AgentRouter
with the correct tenant_id and integration_id (threaded through payload).

NOTE: these endpoints are mounted WITHOUT JWT auth — rejecting an unsigned or
stale request with 401/403 is the only access control.
"""

import hmac
import hashlib
import json
import logging
import time
from typing import Optional
from fastapi import APIRouter, Request, HTTPException, status
from sqlalchemy.orm import Session

from db import get_db
from fastapi import Depends
from models import SlackIntegration, DiscordIntegration, Agent
from hub.security import TokenEncryption
from services.encryption_key_service import get_slack_encryption_key, get_discord_encryption_key
from services.message_queue_service import MessageQueueService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["Channel Webhooks"])

# Slack requires response within 3s and rejects requests older than 5 minutes.
SLACK_TIMESTAMP_MAX_SKEW_SECONDS = 300


def _verify_slack_signature(signing_secret: str, timestamp: str, raw_body: bytes, provided_signature: str) -> bool:
    """Compute Slack's v0=HMAC-SHA256 signature and constant-time compare.

    Reference: https://api.slack.com/authentication/verifying-requests-from-slack
    """
    if not (signing_secret and timestamp and provided_signature and raw_body is not None):
        return False
    try:
        ts_int = int(timestamp)
    except (TypeError, ValueError):
        return False
    # Replay protection
    if abs(time.time() - ts_int) > SLACK_TIMESTAMP_MAX_SKEW_SECONDS:
        return False
    basestring = f"v0:{timestamp}:".encode("utf-8") + raw_body
    digest = hmac.new(signing_secret.encode("utf-8"), basestring, hashlib.sha256).hexdigest()
    expected = f"v0={digest}"
    return hmac.compare_digest(expected, provided_signature)


def _verify_discord_signature(public_key_hex: str, timestamp: str, raw_body: bytes, signature_hex: str) -> bool:
    """Verify Discord's Ed25519 signature.

    Reference: https://discord.com/developers/docs/interactions/receiving-and-responding
    """
    if not (public_key_hex and timestamp and raw_body is not None and signature_hex):
        return False
    try:
        from nacl.signing import VerifyKey
        from nacl.exceptions import BadSignatureError
    except ImportError:
        logger.error("[CHN-002] PyNaCl not installed — cannot verify Discord signature")
        return False
    try:
        verify_key = VerifyKey(bytes.fromhex(public_key_hex))
        verify_key.verify(timestamp.encode("utf-8") + raw_body, bytes.fromhex(signature_hex))
        return True
    except (BadSignatureError, ValueError, TypeError):
        return False


def _resolve_agent_for_slack(db: Session, integration: SlackIntegration) -> Optional[Agent]:
    """Pick the agent bound to this Slack integration (or tenant default)."""
    agent = db.query(Agent).filter(
        Agent.tenant_id == integration.tenant_id,
        Agent.slack_integration_id == integration.id,
        Agent.is_active == True,
    ).first()
    if agent:
        return agent
    # Fallback to tenant default
    return db.query(Agent).filter(
        Agent.tenant_id == integration.tenant_id,
        Agent.is_default == True,
        Agent.is_active == True,
    ).first()


def _resolve_agent_for_discord(db: Session, integration: DiscordIntegration) -> Optional[Agent]:
    agent = db.query(Agent).filter(
        Agent.tenant_id == integration.tenant_id,
        Agent.discord_integration_id == integration.id,
        Agent.is_active == True,
    ).first()
    if agent:
        return agent
    return db.query(Agent).filter(
        Agent.tenant_id == integration.tenant_id,
        Agent.is_default == True,
        Agent.is_active == True,
    ).first()


@router.post("/slack/events")
async def slack_events(request: Request, db: Session = Depends(get_db)):
    """V060-CHN-002: Receive Slack Events API POSTs with HMAC-SHA256 signature verification.

    Protocol notes:
    - 'url_verification' challenge is echoed back immediately on first setup.
    - All other events are acknowledged with 200 within 3s; heavy work is
      deferred to the queue worker.
    """
    raw_body = await request.body()
    ts = request.headers.get("X-Slack-Request-Timestamp", "")
    sig = request.headers.get("X-Slack-Signature", "")

    # Parse body to find team_id -> SlackIntegration -> signing_secret
    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

    team_id = body.get("team_id") or body.get("api_app_id")
    # For url_verification the body may not have team_id — fall through; signature still verifies
    integration: Optional[SlackIntegration] = None
    if team_id:
        integration = db.query(SlackIntegration).filter(
            SlackIntegration.workspace_id == team_id,
            SlackIntegration.is_active == True,
        ).first()

    if not integration:
        # Can't identify tenant — reject
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown Slack workspace")

    if not integration.signing_secret_encrypted:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Slack integration has no signing_secret configured (HTTP mode required)",
        )

    key = get_slack_encryption_key(db)
    if not key:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Slack encryption key missing")
    try:
        signing_secret = TokenEncryption(key.encode()).decrypt(
            integration.signing_secret_encrypted, integration.tenant_id
        )
    except Exception:
        logger.exception("[CHN-002] Failed to decrypt signing_secret")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Signing secret decrypt failed")

    if not _verify_slack_signature(signing_secret, ts, raw_body, sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Slack signature")

    # URL verification handshake
    if body.get("type") == "url_verification":
        return {"challenge": body.get("challenge", "")}

    # Only enqueue 'event_callback' messages we actually handle
    event = body.get("event") or {}
    event_type = event.get("type", "")
    if body.get("type") != "event_callback" or event_type not in ("message", "app_mention"):
        return {"ok": True, "ignored": True, "event_type": event_type}

    # Ignore bot-originated messages (including our own bot echoing)
    if event.get("bot_id") or event.get("subtype") == "bot_message":
        return {"ok": True, "ignored": True, "reason": "bot_message"}

    agent = _resolve_agent_for_slack(db, integration)
    if not agent:
        logger.warning(f"[CHN-002] No agent resolved for Slack integration {integration.id}")
        return {"ok": True, "ignored": True, "reason": "no_agent"}

    sender_id = event.get("user") or "unknown"
    sender_key = f"{integration.workspace_id}:{sender_id}"

    mqs = MessageQueueService(db)
    mqs.enqueue(
        channel="slack",
        tenant_id=integration.tenant_id,
        agent_id=agent.id,
        sender_key=sender_key,
        payload={
            "event": event,
            "team_id": integration.workspace_id,
            "slack_integration_id": integration.id,
            "event_id": body.get("event_id"),
            "event_time": body.get("event_time"),
        },
        priority=0,
    )
    logger.info(
        f"[CHN-002] Enqueued Slack {event_type} from {sender_key} for agent {agent.id} "
        f"(tenant={integration.tenant_id})"
    )
    return {"ok": True, "enqueued": True}


@router.post("/discord/interactions")
async def discord_interactions(request: Request, db: Session = Depends(get_db)):
    """V060-CHN-002: Receive Discord Interactions (slash commands/components) with
    Ed25519 signature verification.

    Note: plain Discord message ingestion requires a Gateway (WebSocket)
    connection — that is out of scope for this webhook. Interactions (slash
    commands, buttons, modals) are the supported inbound surface.
    """
    raw_body = await request.body()
    ts = request.headers.get("X-Signature-Timestamp", "")
    sig = request.headers.get("X-Signature-Ed25519", "")

    try:
        body = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid JSON body")

    application_id = body.get("application_id")
    if not application_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Missing application_id")

    integration = db.query(DiscordIntegration).filter(
        DiscordIntegration.application_id == str(application_id),
        DiscordIntegration.is_active == True,
    ).first()
    if not integration:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown Discord application")

    # Discord stores the public key on-integration via a future column; for now
    # require it to be provided via env or an extensible field. Until the
    # schema adds it explicitly we read from environment variable per tenant.
    # FIXME: promote to a DB column when DiscordIntegration is updated.
    import os as _os
    pubkey = _os.environ.get(f"DISCORD_PUBLIC_KEY_{integration.id}") or _os.environ.get("DISCORD_PUBLIC_KEY")
    if not pubkey:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Discord public key not configured for this integration",
        )

    if not _verify_discord_signature(pubkey, ts, raw_body, sig):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Discord signature")

    # Discord interaction type 1 is PING
    if body.get("type") == 1:
        return {"type": 1}

    # type 2 = APPLICATION_COMMAND (slash), 3 = MESSAGE_COMPONENT, 5 = MODAL_SUBMIT
    if body.get("type") not in (2, 3, 5):
        return {"ok": True, "ignored": True, "type": body.get("type")}

    agent = _resolve_agent_for_discord(db, integration)
    if not agent:
        logger.warning(f"[CHN-002] No agent resolved for Discord integration {integration.id}")
        # Discord requires type 4 response (channel message) within 3s; reply deferred
        return {"type": 4, "data": {"content": "No agent is configured to handle this interaction."}}

    user = (body.get("member") or {}).get("user") or body.get("user") or {}
    sender_id = user.get("id") or "unknown"
    sender_key = f"discord:{sender_id}"

    mqs = MessageQueueService(db)
    mqs.enqueue(
        channel="discord",
        tenant_id=integration.tenant_id,
        agent_id=agent.id,
        sender_key=sender_key,
        payload={
            "interaction": body,
            "discord_integration_id": integration.id,
        },
        priority=0,
    )
    logger.info(
        f"[CHN-002] Enqueued Discord interaction type={body.get('type')} from {sender_key} "
        f"for agent {agent.id} (tenant={integration.tenant_id})"
    )
    # Respond immediately with DEFERRED_CHANNEL_MESSAGE_WITH_SOURCE (type 5) so
    # Discord stops waiting; the queue worker's outbound adapter can follow up.
    return {"type": 5}
