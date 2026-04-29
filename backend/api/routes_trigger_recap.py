"""Shared per-trigger Memory Recap CRUD + test-recap helpers.

v0.7.x — Wave 2-C.

Each trigger kind's route module (``routes_jira_triggers.py``,
``routes_email_triggers.py``, ``routes_github_triggers.py``,
``routes_webhook_instances.py``) exposes the four endpoints below
under its own URL prefix. The handlers in this module are the
behavioural source of truth — the per-kind route files are thin
adapters that:

  1. Validate the trigger row exists for the requesting tenant
     (via the existing per-kind ``_load_*`` helpers).
  2. Delegate to one of ``get_recap_config_for``,
     ``put_recap_config_for``, ``delete_recap_config_for``,
     ``run_test_recap_for``.

URL shape (per kind ``K`` in ``{jira, email, github, webhook}``):

  ``GET    /api/triggers/{K}/{trigger_id}/recap-config``
  ``PUT    /api/triggers/{K}/{trigger_id}/recap-config``
  ``DELETE /api/triggers/{K}/{trigger_id}/recap-config``
  ``POST   /api/triggers/{K}/{trigger_id}/test-recap``

Auth: read scope is ``hub.read`` and write scope is ``hub.write`` —
matches each per-kind file's existing convention so the recap surface
inherits the same RBAC story trigger CRUD already has.

Tenant isolation: enforced at trigger-row load time. The recap config
itself is keyed on ``(tenant_id, trigger_kind, trigger_instance_id)``
so a leak via the recap row alone is structurally impossible — the
trigger must already belong to the tenant for the route to reach
this module.

Cascade delete: ``delete_recap_config_for_trigger_instance`` is a
plain helper (no HTTP) that the per-kind DELETE handlers call inside
their existing transaction so the recap row goes away with the
trigger row.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Optional

from fastapi import HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic schemas — shared across all four trigger kinds.
# ---------------------------------------------------------------------------


class TriggerRecapConfigRead(BaseModel):
    id: int
    tenant_id: str
    trigger_kind: str
    trigger_instance_id: int
    enabled: bool
    query_template: str
    scope: str
    k: int
    min_similarity: float
    vector_kind: str
    include_failed: bool
    format_template: str
    inject_position: str
    max_recap_chars: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TriggerRecapConfigWrite(BaseModel):
    enabled: bool = False
    query_template: str = ""
    scope: str = Field("trigger_instance", pattern="^(agent|trigger_kind|trigger_instance)$")
    k: int = Field(3, ge=1, le=10)
    min_similarity: float = Field(0.35, ge=0.0, le=1.0)
    vector_kind: str = Field("problem", pattern="^(problem|action|outcome|any)$")
    include_failed: bool = True
    format_template: str = ""
    inject_position: str = Field(
        "prepend_user_msg", pattern="^(prepend_user_msg|system_addendum)$"
    )
    max_recap_chars: int = Field(1500, ge=200, le=8192)


class TriggerRecapTestRequest(BaseModel):
    """Optional bodies. If both are absent the helper falls back to the
    most recent ``WakeEvent`` for this trigger instance.
    """

    query: Optional[str] = None
    sample_payload: Optional[dict[str, Any]] = None


class TriggerRecapTestResponse(BaseModel):
    rendered_text: Optional[str] = None
    cases_used: int = 0
    config_snapshot: Optional[dict[str, Any]] = None
    used_sample: bool = False
    elapsed_ms: int = 0


# Map trigger_kind → channel_type literal stored on WakeEvent rows.
# Both the dispatch service and the trigger registry use these short
# names so the recap fallback can find the most recent event by joining
# on (channel_type, channel_instance_id).
_TRIGGER_KIND_TO_CHANNEL = {
    "jira": "jira",
    "email": "email",
    "github": "github",
    "webhook": "webhook",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _to_read(row) -> TriggerRecapConfigRead:
    return TriggerRecapConfigRead.model_validate(row)


def _resolve_default_agent_id(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
) -> Optional[int]:
    """Look up the trigger row's ``default_agent_id`` (best-effort).

    The recap service expects an ``agent_id`` so it can scope vector
    search. For test-recap we use the trigger's bound default agent.
    Returns ``None`` if the trigger has none — callers swallow that as
    "no recap possible".
    """
    from models import (
        EmailChannelInstance,
        GitHubChannelInstance,
        JiraChannelInstance,
        WebhookIntegration,
    )

    model_by_kind = {
        "jira": JiraChannelInstance,
        "email": EmailChannelInstance,
        "github": GitHubChannelInstance,
        "webhook": WebhookIntegration,
    }
    model = model_by_kind.get(trigger_kind)
    if model is None:
        return None
    row = (
        db.query(model)
        .filter(model.id == trigger_instance_id, model.tenant_id == tenant_id)
        .first()
    )
    if row is None:
        return None
    return getattr(row, "default_agent_id", None)


def _read_recent_wake_event_payload(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
) -> Optional[dict]:
    """Return the redacted payload JSON of the most recent matching wake event.

    Falls back to ``None`` if no event exists or the payload file is
    missing — caller treats this as "no sample available" and may
    return a 400 explaining the situation.
    """
    from models import WakeEvent
    from services.trigger_dispatch_service import TriggerDispatchService

    channel_type = _TRIGGER_KIND_TO_CHANNEL.get(trigger_kind)
    if not channel_type:
        return None

    event = (
        db.query(WakeEvent)
        .filter(
            WakeEvent.tenant_id == tenant_id,
            WakeEvent.channel_type == channel_type,
            WakeEvent.channel_instance_id == trigger_instance_id,
        )
        .order_by(WakeEvent.occurred_at.desc(), WakeEvent.id.desc())
        .first()
    )
    if event is None or not event.payload_ref:
        return None
    try:
        # Reuse the dispatcher's reader so any future redaction tweak is
        # applied uniformly. Instantiating the service is cheap (no
        # work happens in __init__ beyond storing references).
        svc = TriggerDispatchService(db)
        return svc._read_payload_ref(event.payload_ref)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 — diagnostic path, never raise
        logger.warning(
            "trigger_recap.test: failed to re-read payload_ref=%s for "
            "tenant=%s kind=%s instance=%s",
            event.payload_ref,
            tenant_id,
            trigger_kind,
            trigger_instance_id,
            exc_info=True,
        )
        return None


# ---------------------------------------------------------------------------
# CRUD handlers — called by per-kind routers after they validate the trigger
# row belongs to the tenant.
# ---------------------------------------------------------------------------


def get_recap_config_for(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
) -> TriggerRecapConfigRead:
    from models import TriggerRecapConfig

    row = (
        db.query(TriggerRecapConfig)
        .filter(
            TriggerRecapConfig.tenant_id == tenant_id,
            TriggerRecapConfig.trigger_kind == trigger_kind,
            TriggerRecapConfig.trigger_instance_id == trigger_instance_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Recap config not found")
    return _to_read(row)


def put_recap_config_for(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
    payload: TriggerRecapConfigWrite,
) -> TriggerRecapConfigRead:
    """Upsert the recap config for ``(tenant, kind, instance)``.

    Returns the persisted row. Existing rows update in place; the
    unique constraint on ``(tenant_id, trigger_kind, trigger_instance_id)``
    guarantees there is at most one.
    """
    from models import TriggerRecapConfig

    row = (
        db.query(TriggerRecapConfig)
        .filter(
            TriggerRecapConfig.tenant_id == tenant_id,
            TriggerRecapConfig.trigger_kind == trigger_kind,
            TriggerRecapConfig.trigger_instance_id == trigger_instance_id,
        )
        .first()
    )

    fields = payload.model_dump()
    if row is None:
        row = TriggerRecapConfig(
            tenant_id=tenant_id,
            trigger_kind=trigger_kind,
            trigger_instance_id=trigger_instance_id,
            **fields,
        )
        db.add(row)
    else:
        for key, value in fields.items():
            setattr(row, key, value)
        row.updated_at = datetime.utcnow()

    db.commit()
    db.refresh(row)
    return _to_read(row)


def delete_recap_config_for(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
) -> None:
    """DELETE /recap-config — 404 when no row exists."""
    from models import TriggerRecapConfig

    row = (
        db.query(TriggerRecapConfig)
        .filter(
            TriggerRecapConfig.tenant_id == tenant_id,
            TriggerRecapConfig.trigger_kind == trigger_kind,
            TriggerRecapConfig.trigger_instance_id == trigger_instance_id,
        )
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Recap config not found")
    db.delete(row)
    db.commit()


def delete_recap_config_for_trigger_instance(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
) -> None:
    """Cascade-delete helper — silent no-op when there's no row.

    Per-kind DELETE handlers call this inside their existing
    transaction. A missing config is not an error — most triggers
    won't have a recap configured.

    Fail-soft against missing table: in-memory SQLite test fixtures may
    not seed ``trigger_recap_config`` (the table was added in alembic
    0076 — older fixtures pre-date it). A missing-table OperationalError
    must not break the trigger DELETE path.
    """
    from sqlalchemy.exc import OperationalError, ProgrammingError

    from models import TriggerRecapConfig

    # Use a savepoint so a missing-table failure doesn't roll back the parent
    # transaction's prior work (the trigger DELETE itself + its other cascades).
    try:
        with db.begin_nested():
            db.query(TriggerRecapConfig).filter(
                TriggerRecapConfig.tenant_id == tenant_id,
                TriggerRecapConfig.trigger_kind == trigger_kind,
                TriggerRecapConfig.trigger_instance_id == trigger_instance_id,
            ).delete(synchronize_session=False)
    except (OperationalError, ProgrammingError):
        # Savepoint already rolled back; parent transaction is unaffected.
        pass


def run_test_recap_for(
    db: Session,
    *,
    tenant_id: str,
    trigger_kind: str,
    trigger_instance_id: int,
    body: TriggerRecapTestRequest,
) -> TriggerRecapTestResponse:
    """Run a preview of ``build_memory_recap`` for the saved trigger.

    Resolution order for the payload doc:
      1. ``body.sample_payload`` — wrapped under the ``payload`` key so
         operators can write ``{{summary}}`` instead of
         ``{{payload.summary}}``, matching the dispatch-time contract.
      2. ``body.query`` — turned into a synthetic payload
         ``{"payload": {"query": <str>, "summary": <str>}}`` so the
         recap service still has structured input.
      3. The most recent ``WakeEvent`` for this trigger.

    A missing recap config returns 404 (matches GET semantics —
    operators get an actionable error). Any internal failure inside
    ``build_memory_recap`` returns ``rendered_text=None`` with
    ``cases_used=0`` so the UI can render an empty preview without a
    500.
    """
    from models import TriggerRecapConfig
    from services.trigger_recap_service import build_memory_recap

    config_row = (
        db.query(TriggerRecapConfig)
        .filter(
            TriggerRecapConfig.tenant_id == tenant_id,
            TriggerRecapConfig.trigger_kind == trigger_kind,
            TriggerRecapConfig.trigger_instance_id == trigger_instance_id,
        )
        .first()
    )
    if config_row is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "Recap config not found — configure recap for this trigger "
                "before running a test preview."
            ),
        )

    used_sample = False
    payload_doc: Optional[dict] = None
    if body.sample_payload is not None:
        payload_doc = {
            "trigger_type": trigger_kind,
            "instance_id": trigger_instance_id,
            "event_type": "test",
            "dedupe_key": "test-recap-preview",
            "payload": body.sample_payload,
        }
        used_sample = True
    elif body.query is not None:
        payload_doc = {
            "trigger_type": trigger_kind,
            "instance_id": trigger_instance_id,
            "event_type": "test",
            "dedupe_key": "test-recap-preview",
            "payload": {"query": body.query, "summary": body.query},
        }
        used_sample = True
    else:
        payload_doc = _read_recent_wake_event_payload(
            db,
            tenant_id=tenant_id,
            trigger_kind=trigger_kind,
            trigger_instance_id=trigger_instance_id,
        )

    if payload_doc is None:
        # Diagnostic shape: signal to the UI that there's nothing to
        # preview against, but the config exists and is valid.
        return TriggerRecapTestResponse(
            rendered_text=None,
            cases_used=0,
            config_snapshot=None,
            used_sample=False,
            elapsed_ms=0,
        )

    agent_id = _resolve_default_agent_id(
        db,
        tenant_id=tenant_id,
        trigger_kind=trigger_kind,
        trigger_instance_id=trigger_instance_id,
    )
    if agent_id is None:
        # Without a bound agent the recap service can't resolve a
        # vector-store target. Surface the situation via an empty
        # preview rather than a 500 — operators understand this from
        # the test-recap UX (the trigger needs a default agent).
        return TriggerRecapTestResponse(
            rendered_text=None,
            cases_used=0,
            config_snapshot=None,
            used_sample=used_sample,
            elapsed_ms=0,
        )

    started = time.monotonic()
    try:
        recap = build_memory_recap(
            db,
            tenant_id=tenant_id,
            agent_id=agent_id,
            trigger_kind=trigger_kind,
            trigger_instance_id=trigger_instance_id,
            payload_doc=payload_doc,
        )
    except Exception:  # noqa: BLE001 — preview must never 500
        logger.warning(
            "trigger_recap.test: build_memory_recap raised "
            "(tenant=%s kind=%s instance=%s)",
            tenant_id,
            trigger_kind,
            trigger_instance_id,
            exc_info=True,
        )
        recap = None
    elapsed_ms = int((time.monotonic() - started) * 1000)

    if recap is None:
        return TriggerRecapTestResponse(
            rendered_text=None,
            cases_used=0,
            config_snapshot=None,
            used_sample=used_sample,
            elapsed_ms=elapsed_ms,
        )

    return TriggerRecapTestResponse(
        rendered_text=recap.get("rendered_text"),
        cases_used=int(recap.get("cases_used") or 0),
        config_snapshot=recap.get("config_snapshot"),
        used_sample=used_sample,
        elapsed_ms=elapsed_ms,
    )
