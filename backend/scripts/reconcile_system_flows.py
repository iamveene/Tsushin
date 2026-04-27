"""Reconcile system-managed flows for triggers (v0.7.0 Wave 5).

Scans every existing trigger across the 5 kinds and ensures each has a
matching system-managed FlowDefinition + flow_trigger_binding row. Useful
when:

  - The Wave 4 auto-Flow generation gate (``TSN_FLOWS_AUTO_GENERATION_ENABLED``)
    was off when a tenant created a trigger, and the operator now wants
    to retroactively wire it.
  - A previous reconciliation crashed mid-run.
  - A binding row was manually deleted from the DB.

The script is idempotent — it skips any (tenant, kind, instance) that
already has a system-managed binding. Existing user-authored flows /
bindings are never touched.

Run inside the backend container:

    docker exec tsushin-backend python -m scripts.reconcile_system_flows

Reads the live DB via the global engine — does NOT need any env var
flipped. Output is a per-kind tally of {created, skipped, failed}.
"""

from __future__ import annotations

import logging
import sys
from typing import Iterable

from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("reconcile_system_flows")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


_KIND_INSTANCE_TABLE = {
    "jira": "JiraChannelInstance",
    "email": "EmailChannelInstance",
    "github": "GitHubChannelInstance",
    "schedule": "ScheduleChannelInstance",
    "webhook": "WebhookIntegration",
}


def _iter_trigger_rows(db, kind: str) -> Iterable[tuple[int, str, int | None]]:
    """Yield ``(instance_id, tenant_id, default_agent_id)`` for every row of a kind."""
    import models
    cls = getattr(models, _KIND_INSTANCE_TABLE[kind])
    for row in db.query(cls).all():
        yield row.id, row.tenant_id, getattr(row, "default_agent_id", None)


def main() -> int:
    sys.path.insert(0, "/app")  # backend is mounted at /app inside the container
    from db import get_global_engine, set_global_engine, get_engine
    import os
    db_url = os.getenv("DATABASE_URL", "postgresql://tsushin:tsushin@postgres:5432/tsushin")
    set_global_engine(get_engine(db_url))

    from services.flow_binding_service import (
        ensure_system_managed_flow_for_trigger,
        find_system_managed_flow_for_trigger,
    )

    SessionLocal = sessionmaker(bind=get_global_engine())
    db = SessionLocal()

    totals: dict[str, dict[str, int]] = {}
    try:
        for kind in _KIND_INSTANCE_TABLE.keys():
            tally = {"created": 0, "skipped": 0, "failed": 0}
            for instance_id, tenant_id, default_agent_id in _iter_trigger_rows(db, kind):
                if not tenant_id:
                    tally["skipped"] += 1
                    continue
                if find_system_managed_flow_for_trigger(
                    db,
                    tenant_id=tenant_id,
                    trigger_kind=kind,
                    trigger_instance_id=instance_id,
                ) is not None:
                    tally["skipped"] += 1
                    continue
                try:
                    flow, binding, created = ensure_system_managed_flow_for_trigger(
                        db,
                        tenant_id=tenant_id,
                        trigger_kind=kind,
                        trigger_instance_id=instance_id,
                        default_agent_id=default_agent_id,
                    )
                    db.commit()
                    if created:
                        tally["created"] += 1
                        logger.info(
                            "Reconciled %s/%s for tenant %s → flow=%s binding=%s",
                            kind, instance_id, tenant_id, flow.id, binding.id,
                        )
                except Exception as exc:
                    db.rollback()
                    tally["failed"] += 1
                    logger.exception("Failed to reconcile %s/%s: %s", kind, instance_id, exc)
            totals[kind] = tally
    finally:
        db.close()

    logger.info("=== Reconciliation summary ===")
    for kind, tally in totals.items():
        logger.info("%s: created=%d skipped=%d failed=%d", kind, **tally)
    return 0 if all(t["failed"] == 0 for t in totals.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
