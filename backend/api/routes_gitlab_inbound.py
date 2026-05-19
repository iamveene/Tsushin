"""Token-gated GitLab webhook ingestion for GitLab triggers."""

from __future__ import annotations

import json
import logging
import hashlib
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from channels.gitlab.trigger import (
    build_dispatch_payload,
    decrypt_webhook_secret,
    gitlab_filters_match,
    occurred_at_for_payload,
    sender_key_for_payload,
    verify_gitlab_token,
)
from channels.repository.events import canonical_event
from db import get_db
from models import GitLabChannelInstance
from services.trigger_dispatch_service import TriggerDispatchInput, TriggerDispatchService


logger = logging.getLogger(__name__)
router = APIRouter(tags=["gitlab-inbound"])


def _generic_403() -> None:
    raise HTTPException(status_code=403, detail="Forbidden")


def _status_value(result) -> Optional[str]:
    status = getattr(result, "status", None)
    if status is None:
        return None
    return str(getattr(status, "value", status))


def _load_public_instance(db: Session, trigger_id: int) -> GitLabChannelInstance:
    instance = db.query(GitLabChannelInstance).filter(GitLabChannelInstance.id == trigger_id).first()
    if instance is None or not instance.is_active or (instance.status or "active") != "active":
        _generic_403()
    return instance


@router.post("/api/triggers/gitlab/{trigger_id}/inbound", status_code=202)
async def receive_gitlab_webhook(
    trigger_id: int,
    request: Request,
    x_gitlab_token: Optional[str] = Header(None, alias="X-Gitlab-Token"),
    x_gitlab_event: Optional[str] = Header(None, alias="X-Gitlab-Event"),
    x_gitlab_event_uuid: Optional[str] = Header(None, alias="X-Gitlab-Event-UUID"),
    db: Session = Depends(get_db),
):
    instance = _load_public_instance(db, trigger_id)
    if not instance.webhook_secret_encrypted:
        logger.error("GitLab trigger %s has no webhook secret configured", trigger_id)
        _generic_403()

    try:
        secret = decrypt_webhook_secret(db, instance.tenant_id, instance.webhook_secret_encrypted)
    except Exception as exc:
        logger.error("Failed to decrypt GitLab webhook secret: %s", type(exc).__name__)
        raise HTTPException(status_code=500, detail="Server configuration error") from exc

    if not verify_gitlab_token(x_gitlab_token, secret):
        logger.warning("GitLab trigger %s rejected delivery with invalid token", trigger_id)
        _generic_403()

    event_type = (x_gitlab_event or "").strip()
    if not event_type:
        raise HTTPException(status_code=400, detail="X-Gitlab-Event header required")

    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8")) if raw_body else {}
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")

    delivery_id = (x_gitlab_event_uuid or "").strip()
    if not delivery_id:
        delivery_hash = hashlib.sha256(raw_body or json.dumps(payload, sort_keys=True).encode("utf-8")).hexdigest()
        delivery_id = f"gitlab-{trigger_id}-{delivery_hash}"

    matched, filter_reason = gitlab_filters_match(instance, event_type, payload)
    if not matched:
        return {"status": "filtered", "delivery_id": delivery_id, "reason": filter_reason}

    dispatch_payload = build_dispatch_payload(
        instance_id=instance.id,
        delivery_id=delivery_id,
        event_type=event_type,
        payload=payload,
    )
    occurred_at = occurred_at_for_payload(payload)
    result = TriggerDispatchService(db).dispatch(
        TriggerDispatchInput(
            trigger_type="gitlab",
            instance_id=instance.id,
            event_type=canonical_event("gitlab", event_type),
            dedupe_key=delivery_id,
            payload=dispatch_payload,
            occurred_at=occurred_at,
            importance="normal",
            sender_key=sender_key_for_payload(instance.id, payload),
            source_id=delivery_id,
        )
    )

    instance.last_delivery_id = delivery_id
    instance.last_activity_at = occurred_at
    db.commit()

    status = _status_value(result)
    if status == "duplicate":
        return {"status": "duplicate", "delivery_id": delivery_id, "reason": getattr(result, "reason", None)}
    if status == "dispatched":
        return {
            "status": "accepted",
            "delivery_id": delivery_id,
            "wake_event_id": getattr(result, "wake_event_id", None),
            "continuous_run_ids": getattr(result, "continuous_run_ids", []),
            "team_run_ids": getattr(result, "team_run_ids", []),
        }
    if status == "filtered":
        return {"status": "filtered", "delivery_id": delivery_id, "reason": getattr(result, "reason", None)}
    return {"status": status or "unknown", "delivery_id": delivery_id, "reason": getattr(result, "reason", None)}
