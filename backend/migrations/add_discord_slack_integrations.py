"""
Phase 23: Discord & Slack Channel Integration Migration
BUG-311, BUG-312, BUG-313 Fixes

Adds missing columns to existing discord_integration and slack_integration tables:
- discord_integration.public_key (BUG-311/313: per-integration Ed25519 key)
- slack_integration.app_id (BUG-312: for url_verification handshake resolution)
"""

import logging
from sqlalchemy import text, inspect

logger = logging.getLogger(__name__)


def upgrade_from_engine(engine):
    """Add missing columns to existing Discord/Slack integration tables."""
    try:
        inspector = inspect(engine)

        with engine.begin() as conn:
            # Add public_key to discord_integration if missing
            if "discord_integration" in inspector.get_table_names():
                discord_cols = [c["name"] for c in inspector.get_columns("discord_integration")]
                if "public_key" not in discord_cols:
                    conn.execute(text("ALTER TABLE discord_integration ADD COLUMN public_key VARCHAR(128)"))
                    logger.info("Added discord_integration.public_key column")

            # Add app_id to slack_integration if missing
            if "slack_integration" in inspector.get_table_names():
                slack_cols = [c["name"] for c in inspector.get_columns("slack_integration")]
                if "app_id" not in slack_cols:
                    conn.execute(text("ALTER TABLE slack_integration ADD COLUMN app_id VARCHAR(50)"))
                    conn.execute(text("CREATE INDEX IF NOT EXISTS idx_slack_app_id ON slack_integration(app_id)"))
                    logger.info("Added slack_integration.app_id column")

        logger.info("Discord/Slack integration migration completed")

    except Exception as e:
        logger.warning(f"Discord/Slack migration: {e}")
