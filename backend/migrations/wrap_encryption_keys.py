"""
Migration: SEC-006 — Wrap plaintext Fernet encryption keys in DB with TSN_MASTER_KEY

This migration implements envelope encryption for all Fernet keys stored in the
Config table. When TSN_MASTER_KEY is configured, each plaintext Fernet key is
wrapped (encrypted) using the master key so that a DB read alone is insufficient
to decrypt tenant credentials.

Usage:
    # With a running PostgreSQL database:
    TSN_MASTER_KEY=<your-key> python backend/migrations/wrap_encryption_keys.py

    # Or inside the backend container:
    docker exec tsushin-backend python /app/migrations/wrap_encryption_keys.py

Requirements:
    - TSN_MASTER_KEY must be set in the environment (44-char Fernet key).
    - DATABASE_URL or DATABASE_PATH must resolve to the active database.

Safety:
    - Plaintext keys are detected by length: a raw Fernet key is exactly 44 chars.
    - Wrapped keys (produced by Fernet.encrypt) are always longer (128+ chars).
    - Already-wrapped keys are skipped to allow safe re-runs.
    - The migration is idempotent: running it multiple times is safe.
"""

import os
import sys
import base64
import logging

# ---------------------------------------------------------------------------
# Bootstrap: add parent dir to path so we can import app modules if present
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Key detection heuristic
# ---------------------------------------------------------------------------

def _looks_like_plaintext_fernet_key(value: str) -> bool:
    """
    Return True if value appears to be a plaintext (unwrapped) Fernet key.

    A raw Fernet key is exactly 44 characters and is a valid base64url string
    that decodes to 32 bytes. A Fernet-encrypted (wrapped) value is always
    longer (includes IV, ciphertext, HMAC — typically 128+ chars).
    """
    if not value or len(value) != 44:
        return False
    try:
        decoded = base64.urlsafe_b64decode(value.encode())
        return len(decoded) == 32
    except Exception:
        return False


def _get_master_key_or_exit() -> bytes:
    """Read TSN_MASTER_KEY from env, validate it, and return as bytes. Exit if invalid."""
    from cryptography.fernet import Fernet

    raw = os.environ.get("TSN_MASTER_KEY", "").strip()
    if not raw:
        logger.error(
            "TSN_MASTER_KEY is not set. Nothing to do.\n"
            "Set TSN_MASTER_KEY to a 44-char Fernet key and re-run to wrap existing keys.\n"
            "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
        sys.exit(0)  # Not an error — just nothing to do without the key

    # Validate
    key_bytes = raw.encode()
    try:
        Fernet(key_bytes)
        return key_bytes
    except Exception:
        pass

    # Try decoding as base64url → 32 bytes → re-encode as Fernet key
    try:
        decoded = base64.urlsafe_b64decode(key_bytes)
        if len(decoded) == 32:
            fernet_key = base64.urlsafe_b64encode(decoded)
            Fernet(fernet_key)
            return fernet_key
    except Exception:
        pass

    logger.error(
        "TSN_MASTER_KEY is set but invalid. "
        "It must be a 44-char Fernet key or a base64url-encoded 32-byte value."
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# PostgreSQL path (primary, via SQLAlchemy)
# ---------------------------------------------------------------------------

def _run_migration_postgres(database_url: str, master_key: bytes) -> None:
    """Wrap plaintext Fernet keys in PostgreSQL Config table."""
    from cryptography.fernet import Fernet
    import sqlalchemy as sa

    KEY_COLUMNS = [
        "google_encryption_key",
        "asana_encryption_key",
        "telegram_encryption_key",
        "amadeus_encryption_key",
        "api_key_encryption_key",
        "slack_encryption_key",
        "discord_encryption_key",
    ]

    engine = sa.create_engine(database_url)
    f = Fernet(master_key)

    with engine.connect() as conn:
        # Load first config row (single-tenant; multi-tenant would need a loop)
        result = conn.execute(sa.text("SELECT id, " + ", ".join(KEY_COLUMNS) + " FROM config LIMIT 1"))
        row = result.fetchone()

        if row is None:
            logger.warning("No row found in config table. Nothing to migrate.")
            return

        config_id = row[0]
        updates = {}

        for idx, col in enumerate(KEY_COLUMNS):
            value = row[idx + 1]
            if value is None:
                logger.info(f"  {col}: NULL — skipping")
                continue

            if _looks_like_plaintext_fernet_key(value):
                wrapped = f.encrypt(value.encode()).decode()
                updates[col] = wrapped
                logger.info(f"  {col}: wrapped (was plaintext)")
            else:
                logger.info(f"  {col}: already wrapped or non-standard length — skipping")

        if not updates:
            logger.info("All keys are already wrapped. Nothing to do.")
            return

        # Build UPDATE statement
        set_clause = ", ".join(f"{col} = :{col}" for col in updates)
        updates["config_id"] = config_id
        conn.execute(
            sa.text(f"UPDATE config SET {set_clause} WHERE id = :config_id"),
            updates,
        )
        conn.commit()
        logger.info(f"Wrapped {len(updates) - 1} key(s) in config row id={config_id}.")


# ---------------------------------------------------------------------------
# SQLite path (legacy / fallback)
# ---------------------------------------------------------------------------

def _run_migration_sqlite(db_path: str, master_key: bytes) -> None:
    """Wrap plaintext Fernet keys in SQLite Config table."""
    import sqlite3
    from cryptography.fernet import Fernet

    KEY_COLUMNS = [
        "google_encryption_key",
        "asana_encryption_key",
        "telegram_encryption_key",
        "amadeus_encryption_key",
        "api_key_encryption_key",
        "slack_encryption_key",
        "discord_encryption_key",
    ]

    f = Fernet(master_key)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Verify table exists
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='config'")
    if not cursor.fetchone():
        logger.error("config table does not exist. Cannot proceed.")
        conn.close()
        sys.exit(1)

    # Get available columns (some may not exist in older schemas)
    cursor.execute("PRAGMA table_info(config)")
    available = {r[1] for r in cursor.fetchall()}
    columns_to_check = [c for c in KEY_COLUMNS if c in available]

    cursor.execute("SELECT id, " + ", ".join(columns_to_check) + " FROM config LIMIT 1")
    row = cursor.fetchone()

    if row is None:
        logger.warning("No row found in config table. Nothing to migrate.")
        conn.close()
        return

    config_id = row[0]
    updates = {}

    for idx, col in enumerate(columns_to_check):
        value = row[idx + 1]
        if value is None:
            logger.info(f"  {col}: NULL — skipping")
            continue

        if _looks_like_plaintext_fernet_key(value):
            wrapped = f.encrypt(value.encode()).decode()
            updates[col] = wrapped
            logger.info(f"  {col}: wrapped (was plaintext)")
        else:
            logger.info(f"  {col}: already wrapped or non-standard length — skipping")

    if not updates:
        logger.info("All keys are already wrapped. Nothing to do.")
        conn.close()
        return

    set_clause = ", ".join(f"{col} = ?" for col in updates)
    values = list(updates.values()) + [config_id]
    cursor.execute(f"UPDATE config SET {set_clause} WHERE id = ?", values)
    conn.commit()
    conn.close()
    logger.info(f"Wrapped {len(updates)} key(s) in config row id={config_id}.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 60)
    print("SEC-006 Migration: Wrap Fernet encryption keys in DB")
    print("=" * 60)

    master_key = _get_master_key_or_exit()
    logger.info("TSN_MASTER_KEY loaded and validated.")

    # Prefer PostgreSQL (DATABASE_URL)
    database_url = os.environ.get("DATABASE_URL", "").strip()
    if database_url:
        logger.info(f"Using PostgreSQL: {database_url.split('@')[-1]}")  # hide credentials
        _run_migration_postgres(database_url, master_key)
    else:
        # Fall back to SQLite
        db_path = os.environ.get("DATABASE_PATH", "/app/data/agent.db")
        if not os.path.exists(db_path):
            db_path = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "data", "agent.db",
            )
        if not os.path.exists(db_path):
            logger.error(
                f"SQLite database not found at {db_path}. "
                "Set DATABASE_URL or DATABASE_PATH environment variable."
            )
            sys.exit(1)
        logger.info(f"Using SQLite: {db_path}")
        _run_migration_sqlite(db_path, master_key)

    print("\n✅ SEC-006 migration completed successfully!")
    print("\nNext steps:")
    print("  1. Restart the backend container to load the updated service code.")
    print("  2. Verify normal operation (login, integrations, API keys).")
    print("  3. Keep TSN_MASTER_KEY in a secure secrets manager / .env (never commit it).")


if __name__ == "__main__":
    main()
