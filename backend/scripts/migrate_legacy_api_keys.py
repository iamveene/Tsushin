"""Migrate active legacy ApiKey rows into typed credential models.

Run inside the backend container:

    docker exec tsushin-backend python -m scripts.migrate_legacy_api_keys
"""

from __future__ import annotations

import logging
import os
import sys

from sqlalchemy.orm import sessionmaker


def main() -> int:
    sys.path.insert(0, "/app")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from db import get_engine, get_global_engine, set_global_engine
    from services.legacy_api_key_migration_service import migrate_active_legacy_api_keys

    db_url = os.getenv("DATABASE_URL", "postgresql://tsushin:tsushin@postgres:5432/tsushin")
    set_global_engine(get_engine(db_url))
    SessionLocal = sessionmaker(bind=get_global_engine())
    db = SessionLocal()
    try:
        stats = migrate_active_legacy_api_keys(db)
        print(stats)
        return 0
    except Exception as exc:
        db.rollback()
        print(f"Legacy ApiKey migration failed: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
