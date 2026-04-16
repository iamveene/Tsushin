#!/usr/bin/env python3
"""
SQLite to PostgreSQL Data Migration Script for Tsushin.

Reads all data from the SQLite database and copies it to PostgreSQL.
The SQLite database is opened in READ-ONLY mode to prevent any modifications.

Usage:
    python scripts/migrate_sqlite_to_pg.py \
        --sqlite-url "sqlite:////app/data/agent.db" \
        --pg-url "postgresql://tsushin:password@postgres:5432/tsushin" \
        [--batch-size 500] \
        [--dry-run]
"""

import argparse
import sys
import os
import time
import logging

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import create_engine, text, inspect
from sqlalchemy.orm import sessionmaker
from models import Base
import models_rbac  # noqa: F401

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# Tables to skip during migration
SKIP_TABLES = {
    'conversation_search_fts',          # FTS5 virtual table — rebuilt on PG via Alembic
    'conversation_search_fts_content',  # FTS5 internal table
    'conversation_search_fts_docsize',  # FTS5 internal table
    'conversation_search_fts_data',     # FTS5 internal table
    'conversation_search_fts_idx',      # FTS5 internal table
    'conversation_search_fts_config',   # FTS5 internal table
    'sqlite_sequence',                  # SQLite internal table
    'alembic_version',                  # Alembic version tracking (PG has its own)
}


def get_table_order():
    """Get tables in dependency order (parents before children).

    Manual priority for tables with circular FKs (tenant <-> user).
    These must be inserted first to satisfy FK constraints.
    """
    # Priority tables that must come first due to circular dependencies
    priority = [
        'subscription_plan', 'tenant', 'user', 'role', 'permission',
        'role_permission', 'user_role',
    ]
    sorted_tables = [t.name for t in Base.metadata.sorted_tables]
    # Move priority tables to front, maintain relative order for the rest
    remaining = [t for t in sorted_tables if t not in priority]
    return priority + remaining


def count_rows(engine, table_name):
    """Count rows in a table."""
    with engine.connect() as conn:
        result = conn.execute(text(f'SELECT COUNT(*) FROM "{table_name}"'))
        return result.scalar()


def migrate_table(sqlite_engine, pg_engine, table_name, batch_size=500, dry_run=False):
    """Migrate a single table from SQLite to PostgreSQL."""
    try:
        row_count = count_rows(sqlite_engine, table_name)
    except Exception as e:
        logger.warning(f"  Skipping {table_name}: {e}")
        return 0

    if row_count == 0:
        logger.info(f"  {table_name}: 0 rows (skipped)")
        return 0

    logger.info(f"  {table_name}: {row_count} rows")

    if dry_run:
        return row_count

    # Read column names — use intersection of SQLite and PG columns
    # (SQLite may have legacy columns removed from the ORM)
    sqlite_inspector = inspect(sqlite_engine)
    pg_inspector = inspect(pg_engine)

    sqlite_cols = {col['name'] for col in sqlite_inspector.get_columns(table_name)}
    try:
        pg_cols_info = {col['name']: col for col in pg_inspector.get_columns(table_name)}
    except Exception:
        logger.warning(f"  Table {table_name} does not exist in PG, skipping")
        return 0

    # Only migrate columns that exist in both SQLite and PG
    columns = [c for c in sqlite_cols if c in pg_cols_info]
    if not columns:
        logger.warning(f"  No matching columns for {table_name}, skipping")
        return 0

    dropped_cols = sqlite_cols - set(columns)
    if dropped_cols:
        logger.info(f"    Dropping legacy columns not in PG: {dropped_cols}")

    # Identify boolean columns in PG (SQLite stores as 0/1, PG needs TRUE/FALSE)
    pg_bool_cols = {name for name, info in pg_cols_info.items()
                    if str(info.get('type', '')).upper() == 'BOOLEAN'}

    col_list = ', '.join(f'"{c}"' for c in columns)

    migrated = 0
    with sqlite_engine.connect() as src_conn:
        # Read in batches
        offset = 0
        while offset < row_count:
            rows = src_conn.execute(
                text(f'SELECT {col_list} FROM "{table_name}" LIMIT :limit OFFSET :offset'),
                {"limit": batch_size, "offset": offset}
            ).fetchall()

            if not rows:
                break

            # Insert into PostgreSQL
            with pg_engine.connect() as dest_conn:
                trans = dest_conn.begin()
                try:
                    # Disable FK checks during insert
                    dest_conn.execute(text("SET session_replication_role = replica"))

                    placeholders = ', '.join(f':{c}' for c in columns)
                    insert_sql = text(
                        f'INSERT INTO "{table_name}" ({col_list}) VALUES ({placeholders})'
                    )

                    skipped = 0
                    first_error = None
                    for row in rows:
                        row_dict = dict(zip(columns, row))
                        # Convert SQLite integer booleans (0/1) to Python booleans for PG
                        for col in pg_bool_cols:
                            if col in row_dict and isinstance(row_dict[col], int):
                                row_dict[col] = bool(row_dict[col])
                        try:
                            nested = dest_conn.begin_nested()  # SAVEPOINT
                            dest_conn.execute(insert_sql, row_dict)
                            nested.commit()
                        except Exception as e:
                            nested.rollback()
                            skipped += 1
                            if first_error is None:
                                first_error = str(e)[:200]

                    if skipped > 0:
                        logger.warning(f"    Skipped {skipped}/{len(rows)} rows in {table_name}")
                        if first_error:
                            logger.warning(f"    First error: {first_error}")

                    trans.commit()
                finally:
                    # Always restore FK checks
                    try:
                        dest_conn.execute(text("SET session_replication_role = DEFAULT"))
                    except Exception:
                        pass

            migrated += len(rows) - skipped
            offset += batch_size

            if offset % (batch_size * 10) == 0 and offset < row_count:
                logger.info(f"    Progress: {migrated}/{row_count}")

    # Reset sequence to max(id) + 1 for tables with auto-increment
    try:
        with pg_engine.begin() as conn:
            # Check if table has an 'id' column with a sequence
            result = conn.execute(text(f"""
                SELECT pg_get_serial_sequence('"{table_name}"', 'id')
            """)).scalar()
            if result:
                conn.execute(text(f"""
                    SELECT setval('{result}', COALESCE((SELECT MAX(id) FROM "{table_name}"), 0) + 1, false)
                """))
    except Exception:
        pass  # Table may not have an 'id' column or sequence

    return migrated


def main():
    parser = argparse.ArgumentParser(description="Migrate Tsushin data from SQLite to PostgreSQL")
    parser.add_argument("--sqlite-url", required=True, help="SQLite connection URL")
    parser.add_argument("--pg-url", required=True, help="PostgreSQL connection URL")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per batch (default: 500)")
    parser.add_argument("--dry-run", action="store_true", help="Count rows only, don't migrate")
    args = parser.parse_args()

    # Open SQLite in read-only mode
    sqlite_url = args.sqlite_url
    if "?" not in sqlite_url:
        sqlite_url += "?mode=ro"

    logger.info("=" * 60)
    logger.info("Tsushin SQLite → PostgreSQL Data Migration")
    logger.info("=" * 60)
    logger.info(f"Source: {args.sqlite_url}")
    logger.info(f"Target: {args.pg_url.split('@')[0]}@****")
    logger.info(f"Batch size: {args.batch_size}")
    logger.info(f"Dry run: {args.dry_run}")
    logger.info("")

    sqlite_engine = create_engine(
        sqlite_url,
        connect_args={"check_same_thread": False},
    )

    pg_engine = create_engine(args.pg_url)

    # Get tables in dependency order
    table_order = get_table_order()

    # Also check for tables in SQLite that aren't in the ORM (e.g., legacy tables)
    sqlite_inspector = inspect(sqlite_engine)
    sqlite_tables = set(sqlite_inspector.get_table_names())
    orm_tables = set(table_order)

    # Tables in SQLite but not in ORM (might need manual handling)
    extra_tables = sqlite_tables - orm_tables - SKIP_TABLES
    if extra_tables:
        logger.warning(f"Tables in SQLite not in ORM (will attempt migration): {extra_tables}")

    start_time = time.time()
    total_migrated = 0
    table_stats = {}

    logger.info("Migrating tables in dependency order...")
    logger.info("-" * 40)

    for table_name in table_order:
        if table_name in SKIP_TABLES:
            continue
        if table_name not in sqlite_tables:
            logger.debug(f"  {table_name}: not in SQLite (new table)")
            continue

        count = migrate_table(sqlite_engine, pg_engine, table_name, args.batch_size, args.dry_run)
        table_stats[table_name] = count
        total_migrated += count

    # Migrate extra tables (not in ORM)
    for table_name in sorted(extra_tables):
        if table_name in SKIP_TABLES:
            continue
        logger.info(f"  [extra] {table_name}")
        count = migrate_table(sqlite_engine, pg_engine, table_name, args.batch_size, args.dry_run)
        table_stats[table_name] = count
        total_migrated += count

    elapsed = time.time() - start_time

    logger.info("")
    logger.info("=" * 60)
    logger.info("Migration Summary")
    logger.info("=" * 60)
    logger.info(f"Tables processed: {len(table_stats)}")
    logger.info(f"Total rows: {total_migrated}")
    logger.info(f"Time elapsed: {elapsed:.1f}s")
    if args.dry_run:
        logger.info("MODE: DRY RUN (no data was written)")
    logger.info("")

    # Show top tables by row count
    sorted_stats = sorted(table_stats.items(), key=lambda x: x[1], reverse=True)
    logger.info("Top tables by row count:")
    for table_name, count in sorted_stats[:15]:
        if count > 0:
            logger.info(f"  {table_name}: {count:,}")

    sqlite_engine.dispose()
    pg_engine.dispose()

    logger.info("\nDone.")


if __name__ == "__main__":
    main()
