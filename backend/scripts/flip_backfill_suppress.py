"""Flip ``suppress_default_agent=true`` on every backfilled system-managed binding.

Wave 5 release-finishing helper. The 0069 backfill migration creates
``flow_trigger_binding`` rows with ``suppress_default_agent=False`` for
parallel-run safety (legacy ContinuousAgent path keeps firing alongside
the new Flow path during the validation window). When operators are
ready to silence the legacy path on every backfilled binding, they run
this script.

Run inside the backend container:

    docker exec tsushin-backend python -m scripts.flip_backfill_suppress

Idempotent — already-suppressed rows are left alone. Output is the
count of rows flipped.

To roll back the suppression (re-enable the legacy path), run:

    docker exec tsushin-backend python -m scripts.flip_backfill_suppress --unset

Originally Wave 5 attempted to drive this via re-running migration 0069
with ``TSN_FLOWS_BACKFILL_SUPPRESS_LEGACY=true``, but alembic skips
already-applied revisions, so the migration body never re-fired and the
flip never landed. This script replaces that path.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys

from sqlalchemy import text
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger("flip_backfill_suppress")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Flip suppress_default_agent on backfilled bindings.")
    parser.add_argument(
        "--unset",
        action="store_true",
        help="Re-enable the legacy ContinuousAgent path (set suppress_default_agent=false).",
    )
    args = parser.parse_args(argv)

    sys.path.insert(0, "/app")
    from db import get_engine, set_global_engine, get_global_engine
    db_url = os.getenv("DATABASE_URL", "postgresql://tsushin:tsushin@postgres:5432/tsushin")
    set_global_engine(get_engine(db_url))

    SessionLocal = sessionmaker(bind=get_global_engine())
    db = SessionLocal()

    target_value = not args.unset
    target_clause = "false" if args.unset else "true"
    where_filter = "false" if not args.unset else "true"  # only flip rows that are currently the opposite

    sql = text(
        f"UPDATE flow_trigger_binding "
        f"SET suppress_default_agent = {target_clause}, updated_at = CURRENT_TIMESTAMP "
        f"WHERE is_system_managed = true AND suppress_default_agent = {where_filter}"
    )
    try:
        result = db.execute(sql)
        db.commit()
        rowcount = getattr(result, "rowcount", -1)
        action = "Re-enabled legacy path" if args.unset else "Suppressed legacy path"
        logger.info("%s on %s system-managed bindings", action, rowcount if rowcount >= 0 else "<unknown>")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
