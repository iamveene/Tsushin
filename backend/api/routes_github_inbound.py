"""Signed GitHub webhook ingestion for GitHub triggers."""

from __future__ import annotations

import json
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response
from sqlalchemy.orm import Session

from channels.github.trigger import (
    build_dispatch_payload,
    decrypt_webhook_secret,
    github_filters_match,
    occurred_at_for_payload,
    sender_key_for_payload,
    verify_github_signature,
)
from db import get_db
from models import GitHubChannelInstance
from services.trigger_dispatch_service import TriggerDispatchInput, TriggerDispatchService


logger = logging.getLogger(__name__)
router = APIRouter(tags=["github-inbound"])


def _generic_403() -> None:
    raise HTTPException(status_code=403, detail="Forbidden")


def _result_status(result) -> Optional[str]:
    status = getattr(result, "status", None)
    if status is None:
        return None
    return str(getattr(status, "value", status))


def _load_public_instance(db: Session, trigger_id: int) -> GitHubChannelInstance:
    instance = db.query(GitHubChannelInstance).filter(GitHubChannelInstance.id == trigger_id).first()
    if instance is None or not instance.is_active or (instance.status or "active") != "active":
        _generic_403()
    return instance


@router.post("/api/triggers/github/{trigger_id}/inbound", status_code=202)
async def receive_github_webhook(
    trigger_id: int,
    request: Request,
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
    x_github_delivery: Optional[str] = Header(None, alias="X-GitHub-Delivery"),
    db: Session = Depends(get_db),
):
    """Receive a signed GitHub webhook delivery and dispatch a wake event."""
    instance = _load_public_instance(db, trigger_id)
    if not instance.webhook_secret_encrypted:
        logger.error("GitHub trigger %s has no webhook secret configured", trigger_id)
        _generic_403()

    raw_body = await request.body()
    try:
        secret = decrypt_webhook_secret(db, instance.tenant_id, instance.webhook_secret_encrypted)
    except Exception as exc:
        logger.error("Failed to decrypt GitHub webhook secret: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Server configuration error") from exc

    if not verify_github_signature(raw_body, x_hub_signature_256, secret):
        logger.warning("GitHub trigger %s rejected delivery with invalid signature", trigger_id)
        _generic_403()

    event_type = (x_github_event or "").strip().lower()
    if not event_type:
        raise HTTPException(status_code=400, detail="X-GitHub-Event header required")
    delivery_id = (x_github_delivery or "").strip()
    if not delivery_id:
        raise HTTPException(status_code=400, detail="X-GitHub-Delivery header required")

    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    matched, filter_reason = github_filters_match(instance, event_type, payload)
    if not matched:
        logger.info(
            "GitHub trigger %s ignored delivery %s: %s",
            trigger_id,
            delivery_id,
            filter_reason,
        )
        return Response(status_code=204)

    dispatch_payload = build_dispatch_payload(
        instance_id=instance.id,
        delivery_id=delivery_id,
        event_type=event_type,
        payload=payload,
    )
    result = TriggerDispatchService(db).dispatch(
        TriggerDispatchInput(
            trigger_type="github",
            instance_id=instance.id,
            event_type=f"github.{event_type}",
            dedupe_key=delivery_id,
            payload=dispatch_payload,
            occurred_at=occurred_at_for_payload(payload),
            importance="normal",
            sender_key=sender_key_for_payload(instance.id, payload),
            source_id=delivery_id,
        )
    )

    instance.last_delivery_id = delivery_id
    instance.last_activity_at = occurred_at_for_payload(payload)
    db.commit()

    status = _result_status(result)
    if status == "duplicate":
        return {
            "status": "duplicate",
            "delivery_id": delivery_id,
            "reason": getattr(result, "reason", None),
        }
    if status == "dispatched":
        return {
            "status": "accepted",
            "delivery_id": delivery_id,
            "wake_event_id": getattr(result, "wake_event_id", None),
            "continuous_run_ids": getattr(result, "continuous_run_ids", []),
        }
    if status == "filtered":
        return {
            "status": "filtered",
            "delivery_id": delivery_id,
            "reason": getattr(result, "reason", None),
        }
    return {
        "status": status or "unknown",
        "delivery_id": delivery_id,
        "reason": getattr(result, "reason", None),
    }
