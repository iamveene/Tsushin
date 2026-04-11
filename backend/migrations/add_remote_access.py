"""v0.6.0 Remote Access migration (SQLite-only non-Alembic fallback).

Mirrors alembic/versions/0031_add_remote_access.py for environments that
do not run Alembic (legacy SQLite installs). Idempotent.
"""

import logging
from sqlalchemy import text, inspect

from models import get_remote_access_proxy_target_url

logger = logging.getLogger(__name__)


def upgrade_from_engine(engine):
    """Add remote_access_config table + remote_access_encryption_key
    column + tenant.remote_access_enabled column. Safe to call repeatedly."""
    try:
        if getattr(getattr(engine, "dialect", None), "name", None) != "sqlite":
            logger.info("Remote Access migration skipped for non-SQLite engine")
            return

        inspector = inspect(engine)
        default_target_url = get_remote_access_proxy_target_url()
        default_target_url_sql = default_target_url.replace("'", "''")

        with engine.begin() as conn:
            # 1. remote_access_config table
            if "remote_access_config" not in inspector.get_table_names():
                conn.execute(text("""
                    CREATE TABLE remote_access_config (
                        id INTEGER PRIMARY KEY,
                        enabled BOOLEAN NOT NULL DEFAULT 0,
                        mode VARCHAR(20) NOT NULL DEFAULT 'quick',
                        autostart BOOLEAN NOT NULL DEFAULT 0,
                        protocol VARCHAR(10) NOT NULL DEFAULT 'auto',
                        tunnel_token_encrypted TEXT,
                        tunnel_hostname VARCHAR(255),
                        tunnel_dns_target VARCHAR(255),
                        target_url VARCHAR(255) NOT NULL DEFAULT '%s',
                        last_started_at DATETIME,
                        last_stopped_at DATETIME,
                        last_error TEXT,
                        updated_by INTEGER REFERENCES user(id),
                        updated_at DATETIME
                    )
                """ % default_target_url_sql))
                conn.execute(
                    text(
                        "INSERT INTO remote_access_config "
                        "(id, enabled, mode, autostart, protocol, target_url) "
                        "VALUES (1, 0, 'quick', 0, 'auto', :default_target_url)"
                    ),
                    {"default_target_url": default_target_url},
                )
                logger.info("Created remote_access_config table + seeded row")
            else:
                # Ensure the seed row exists even if the table was created elsewhere
                result = conn.execute(text("SELECT COUNT(*) FROM remote_access_config WHERE id = 1"))
                if result.scalar() == 0:
                    conn.execute(
                        text(
                            "INSERT INTO remote_access_config "
                            "(id, enabled, mode, autostart, protocol, target_url) "
                            "VALUES (1, 0, 'quick', 0, 'auto', :default_target_url)"
                        ),
                        {"default_target_url": default_target_url},
                    )
                    logger.info("Seeded remote_access_config default row")

            # 2. config.remote_access_encryption_key
            if "config" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("config")}
                if "remote_access_encryption_key" not in cols:
                    conn.execute(text(
                        "ALTER TABLE config ADD COLUMN remote_access_encryption_key VARCHAR(500)"
                    ))
                    logger.info("Added config.remote_access_encryption_key column")

            # 3. tenant.remote_access_enabled
            if "tenant" in inspector.get_table_names():
                cols = {c["name"] for c in inspector.get_columns("tenant")}
                if "remote_access_enabled" not in cols:
                    conn.execute(text(
                        "ALTER TABLE tenant ADD COLUMN remote_access_enabled BOOLEAN NOT NULL DEFAULT 0"
                    ))
                    conn.execute(text(
                        "CREATE INDEX IF NOT EXISTS ix_tenant_remote_access_enabled "
                        "ON tenant(remote_access_enabled)"
                    ))
                    logger.info("Added tenant.remote_access_enabled column + index")

        logger.info("Remote Access migration completed")

    except Exception as e:
        logger.warning(f"Remote Access migration: {e}")
