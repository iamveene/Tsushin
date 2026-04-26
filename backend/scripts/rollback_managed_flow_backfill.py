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
        # The DB FKs from flow_node/flow_run -> flow_definition do NOT
        # cascade in PostgreSQL (only the ORM relationship's
        # cascade='all, delete-orphan' covers it, and that path needs
        # the ORM session to load the parent first). Raw SQL delete
        # must explicitly remove child rows in the right order. Also
        # cover flow_node_run (children of flow_run) and any
        # conversation_thread.flow_step_run_id references that block
        # the cascade.
        # 1. Find run + node_run ids.
        run_ids_rows = db.execute(
            text(f"SELECT id FROM flow_run WHERE flow_definition_id IN ({ids_csv})")
        ).fetchall()
        run_ids = [r.id for r in run_ids_rows]
        node_run_ids: list[int] = []
        if run_ids:
            run_ids_csv = ",".join(str(r) for r in run_ids)
            node_run_ids = [
                r.id for r in db.execute(
                    text(f"SELECT id FROM flow_node_run WHERE flow_run_id IN ({run_ids_csv})")
                ).fetchall()
            ]
        # 2. Null out conversation_thread.flow_step_run_id (FK with no CASCADE).
        if node_run_ids:
            node_run_csv = ",".join(str(r) for r in node_run_ids)
            db.execute(
                text(
                    f"UPDATE conversation_thread SET flow_step_run_id = NULL "
                    f"WHERE flow_step_run_id IN ({node_run_csv})"
                )
            )
        # 3. Delete child tables in dependency order.
        node_run_count = (
            db.execute(text(f"DELETE FROM flow_node_run WHERE flow_run_id IN ({','.join(str(r) for r in run_ids)})")).rowcount
            if run_ids else 0
        )
        run_count = (
            db.execute(text(f"DELETE FROM flow_run WHERE flow_definition_id IN ({ids_csv})")).rowcount
        )
        binding_count = db.execute(
            text(f"DELETE FROM flow_trigger_binding WHERE flow_definition_id IN ({ids_csv})")
        ).rowcount
        node_count = db.execute(
            text(f"DELETE FROM flow_node WHERE flow_definition_id IN ({ids_csv})")
        ).rowcount
        # 4. Now the parent.
        flow_count = db.execute(
            text(f"DELETE FROM flow_definition WHERE id IN ({ids_csv})")
        ).rowcount
        db.commit()

        logger.info(
            "Rolled back: removed %d flow_definition + %d flow_node + %d flow_trigger_binding + %d flow_run + %d flow_node_run rows",
            flow_count, node_count, binding_count, run_count, node_run_count,
        )
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
