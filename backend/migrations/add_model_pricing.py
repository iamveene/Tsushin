"""
Database Migration: Add Model Pricing Table
Phase: Cost Tracking

Creates:
- model_pricing: Configurable model pricing for cost estimation in debug panel

The model_pricing table allows tenants to customize pricing per model
or use system defaults for accurate cost tracking.
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def table_exists(cursor, table_name: str) -> bool:
    """Check if a table exists in the database."""
    cursor.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?",
        (table_name,)
    )
    return cursor.fetchone() is not None


def upgrade(db_path: str):
    """Run the migration."""
    logger.info(f"Running model pricing migration on {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Create model_pricing table
        if not table_exists(cursor, 'model_pricing'):
            logger.info("Creating model_pricing table...")
            cursor.execute("""
                CREATE TABLE model_pricing (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    model_provider VARCHAR(20) NOT NULL,
                    model_name VARCHAR(100) NOT NULL,
                    input_cost_per_million REAL NOT NULL DEFAULT 0.0,
                    output_cost_per_million REAL NOT NULL DEFAULT 0.0,
                    cached_input_cost_per_million REAL,
                    display_name VARCHAR(100),
                    tenant_id VARCHAR(50),
                    is_active BOOLEAN DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

            # Create unique constraint and indexes
            cursor.execute("""
                CREATE UNIQUE INDEX uix_model_pricing_tenant_model
                ON model_pricing(tenant_id, model_provider, model_name)
            """)
            cursor.execute("""
                CREATE INDEX idx_model_pricing_model
                ON model_pricing(model_provider, model_name)
            """)
            cursor.execute("""
                CREATE INDEX idx_model_pricing_tenant
                ON model_pricing(tenant_id)
            """)

            logger.info("✓ Created model_pricing table")

            # Note: We don't seed default pricing because the system already has
            # hardcoded defaults in MODEL_PRICING that serve as fallback.
            # Custom pricing is optional and tenant-specific.

        else:
            logger.info("✓ model_pricing table already exists")

        conn.commit()
        logger.info("✓ Model pricing migration completed successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


def downgrade(db_path: str):
    """Reverse the migration."""
    logger.info(f"Rolling back model pricing migration on {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        cursor.execute("DROP TABLE IF EXISTS model_pricing")
        conn.commit()
        logger.info("✓ Rollback completed - model_pricing table dropped")

    except Exception as e:
        conn.rollback()
        logger.error(f"Rollback failed: {e}")
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: python add_model_pricing.py <db_path> [--downgrade]")
        sys.exit(1)

    db_path = sys.argv[1]

    if len(sys.argv) > 2 and sys.argv[2] == '--downgrade':
        downgrade(db_path)
    else:
        upgrade(db_path)
