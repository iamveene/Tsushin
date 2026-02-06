"""
Migration: Add Google Integration Tables

Adds tables for:
- google_oauth_credentials: Per-tenant Google OAuth app credentials (BYOT)
- gmail_integration: Gmail read-only access for agents
- calendar_integration: Google Calendar integration for scheduling
- agent_skill_integration: Per-agent skill-to-integration mapping

Also adds display_name column to hub_integration for user-friendly naming.

Run with: python -m migrations.add_google_integrations
"""

import os
import sys
import logging
from datetime import datetime

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import (
    create_engine,
    text,
    inspect,
)
from sqlalchemy.orm import sessionmaker
from db import get_engine

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def get_db_path():
    """Get database path from environment or default."""
    return os.getenv("INTERNAL_DB_PATH", "./data/agent.db")


def column_exists(inspector, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    try:
        columns = [col['name'] for col in inspector.get_columns(table_name)]
        return column_name in columns
    except Exception:
        return False


def table_exists(inspector, table_name: str) -> bool:
    """Check if a table exists."""
    return table_name in inspector.get_table_names()


def run_migration():
    """Run the migration to add Google integration tables."""
    db_path = get_db_path()
    logger.info(f"Running Google integrations migration on: {db_path}")

    engine = get_engine(db_path)
    inspector = inspect(engine)

    with engine.connect() as conn:
        # ============================================
        # 1. Add display_name to hub_integration
        # ============================================
        if not column_exists(inspector, 'hub_integration', 'display_name'):
            logger.info("Adding display_name column to hub_integration...")
            conn.execute(text("""
                ALTER TABLE hub_integration
                ADD COLUMN display_name VARCHAR(200)
            """))
            logger.info("✓ Added display_name column")
        else:
            logger.info("✓ display_name column already exists")

        # ============================================
        # 2. Create google_oauth_credentials table
        # ============================================
        if not table_exists(inspector, 'google_oauth_credentials'):
            logger.info("Creating google_oauth_credentials table...")
            conn.execute(text("""
                CREATE TABLE google_oauth_credentials (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id VARCHAR(50) NOT NULL UNIQUE,
                    client_id VARCHAR(200) NOT NULL,
                    client_secret_encrypted TEXT NOT NULL,
                    redirect_uri VARCHAR(500),
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    created_by INTEGER,
                    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
                    FOREIGN KEY (created_by) REFERENCES user(id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX idx_google_oauth_tenant ON google_oauth_credentials(tenant_id)
            """))
            logger.info("✓ Created google_oauth_credentials table")
        else:
            logger.info("✓ google_oauth_credentials table already exists")

        # ============================================
        # 3. Create gmail_integration table
        # ============================================
        if not table_exists(inspector, 'gmail_integration'):
            logger.info("Creating gmail_integration table...")
            conn.execute(text("""
                CREATE TABLE gmail_integration (
                    id INTEGER PRIMARY KEY,
                    email_address VARCHAR(255) NOT NULL,
                    authorized_at DATETIME NOT NULL,
                    google_user_id VARCHAR(100),
                    FOREIGN KEY (id) REFERENCES hub_integration(id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX idx_gmail_email ON gmail_integration(email_address)
            """))
            logger.info("✓ Created gmail_integration table")
        else:
            logger.info("✓ gmail_integration table already exists")

        # ============================================
        # 4. Create calendar_integration table
        # ============================================
        if not table_exists(inspector, 'calendar_integration'):
            logger.info("Creating calendar_integration table...")
            conn.execute(text("""
                CREATE TABLE calendar_integration (
                    id INTEGER PRIMARY KEY,
                    email_address VARCHAR(255) NOT NULL,
                    default_calendar_id VARCHAR(255) DEFAULT 'primary',
                    timezone VARCHAR(50) DEFAULT 'America/Sao_Paulo',
                    authorized_at DATETIME NOT NULL,
                    google_user_id VARCHAR(100),
                    FOREIGN KEY (id) REFERENCES hub_integration(id)
                )
            """))
            conn.execute(text("""
                CREATE INDEX idx_calendar_email ON calendar_integration(email_address)
            """))
            logger.info("✓ Created calendar_integration table")
        else:
            logger.info("✓ calendar_integration table already exists")

        # ============================================
        # 5. Create agent_skill_integration table
        # ============================================
        if not table_exists(inspector, 'agent_skill_integration'):
            logger.info("Creating agent_skill_integration table...")
            conn.execute(text("""
                CREATE TABLE agent_skill_integration (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id INTEGER NOT NULL,
                    skill_type VARCHAR(50) NOT NULL,
                    integration_id INTEGER,
                    scheduler_provider VARCHAR(50),
                    config JSON,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (agent_id) REFERENCES agent(id),
                    FOREIGN KEY (integration_id) REFERENCES hub_integration(id)
                )
            """))
            conn.execute(text("""
                CREATE UNIQUE INDEX idx_agent_skill_integration ON agent_skill_integration(agent_id, skill_type)
            """))
            conn.execute(text("""
                CREATE INDEX idx_skill_integration_type ON agent_skill_integration(skill_type)
            """))
            logger.info("✓ Created agent_skill_integration table")
        else:
            logger.info("✓ agent_skill_integration table already exists")

        # Commit all changes
        conn.commit()

    logger.info("=" * 50)
    logger.info("Migration completed successfully!")
    logger.info("=" * 50)


def rollback_migration():
    """Rollback the migration (for development/testing)."""
    db_path = get_db_path()
    logger.warning(f"Rolling back Google integrations migration on: {db_path}")

    engine = get_engine(db_path)
    inspector = inspect(engine)

    with engine.connect() as conn:
        # Drop tables in reverse order (respecting foreign keys)
        tables_to_drop = [
            'agent_skill_integration',
            'calendar_integration',
            'gmail_integration',
            'google_oauth_credentials',
        ]

        for table in tables_to_drop:
            if table_exists(inspector, table):
                logger.info(f"Dropping table: {table}")
                conn.execute(text(f"DROP TABLE {table}"))
                logger.info(f"✓ Dropped {table}")

        # Note: display_name column removal requires table recreation in SQLite
        # We'll leave it in place as it's harmless

        conn.commit()

    logger.info("Rollback completed!")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Google Integrations Migration")
    parser.add_argument('--rollback', action='store_true', help="Rollback the migration")
    args = parser.parse_args()

    if args.rollback:
        rollback_migration()
    else:
        run_migration()
