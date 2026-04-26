"""Rollback the Wave 5 managed-notification backfill (v0.7.0).

Surgically deletes the system-managed FlowDefinition + flow_trigger_binding
rows that the ``0069_backfill_managed_notifications`` migration created
(identified by ``initiator_metadata.reason='wave5_backfill'``).

User-authored flows and bindings are NEVER touched. The original
``ContinuousAgent`` + ``ContinuousSubscription`` rows are also NEVER
touched (the backfill migration didn't delete them — it ran in
parallel-mode by default).

Run inside the backend container:

    docker exec tsushin-backend python -m scripts.rollback_managed_flow_backfill

Output is a count of flows + bindings removed. Re-running the script is
a no-op (no rows to find).

If you want to BOTH undo the backfill AND silence the legacy path,
unset ``TSN_FLOWS_BACKFILL_SUPPRESS_LEGACY`` before running this script
so the legacy ContinuousAgent + ContinuousSubscription resume firing
WhatsApp on their own.
"""

from __future__ import annotations

import logging
import os
import sys

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("rollback_managed_flow_backfill")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main() -> int:
    sys.path.insert(0, "/app")
    from db import get_engine, set_global_engine, get_global_engine
    db_url = os.getenv("DATABASE_URL", "postgresql://tsushin:tsushin@postgres:5432/tsushin")
    set_global_engine(get_engine(db_url))

    SessionLocal = sessionmaker(bind=get_global_engine())
    db = SessionLocal()

    try:
        # Find every flow with the wave5_backfill marker.
        rows = db.execute(
            text(
                "SELECT id FROM flow_definition "
                "WHERE is_system_owned = true "
                "  AND initiator_metadata::text LIKE '%wave5_backfill%'"
            )
        ).fetchall()
        flow_ids = [r.id for r in rows]
        if not flow_ids:
            logger.info("No backfilled flows found — nothing to roll back.")
            return 0

        ids_csv = ",".join(str(fid) for fid in flow_ids)
        # CASCADE handles flow_node + flow_trigger_binding via ORM relationships.
        # We also defensively delete from flow_trigger_binding first in case the
        # CASCADE isn't honored on this engine.
        binding_count = db.execute(
            text(f"DELETE FROM flow_trigger_binding WHERE flow_definition_id IN ({ids_csv})")
        ).rowcount
        flow_count = db.execute(
            text(f"DELETE FROM flow_definition WHERE id IN ({ids_csv})")
        ).rowcount
        db.commit()

        logger.info(
            "Rolled back: removed %d flow_definition rows and %d flow_trigger_binding rows",
            flow_count, binding_count,
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
