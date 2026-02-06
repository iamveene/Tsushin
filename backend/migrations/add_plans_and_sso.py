"""
Database Migration: Add Plans and SSO Tables
Phase: User Management & SSO

Creates:
- subscription_plan: Database-driven subscription plans
- tenant_sso_config: Per-tenant SSO configuration
- Adds auth_provider, google_id, avatar_url to user table
- Adds plan_id to tenant table

Also seeds default subscription plans.
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


def column_exists(cursor, table_name: str, column_name: str) -> bool:
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def upgrade(db_path: str):
    """Run the migration."""
    logger.info(f"Running plans and SSO migration on {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Create subscription_plan table
        if not table_exists(cursor, 'subscription_plan'):
            logger.info("Creating subscription_plan table...")
            cursor.execute("""
                CREATE TABLE subscription_plan (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name VARCHAR(50) NOT NULL UNIQUE,
                    display_name VARCHAR(100) NOT NULL,
                    description TEXT,
                    price_monthly INTEGER DEFAULT 0,
                    price_yearly INTEGER DEFAULT 0,
                    max_users INTEGER DEFAULT 1,
                    max_agents INTEGER DEFAULT 1,
                    max_monthly_requests INTEGER DEFAULT 1000,
                    max_knowledge_docs INTEGER DEFAULT 10,
                    max_flows INTEGER DEFAULT 5,
                    max_mcp_instances INTEGER DEFAULT 1,
                    features_json TEXT,
                    is_active BOOLEAN DEFAULT 1,
                    is_public BOOLEAN DEFAULT 1,
                    sort_order INTEGER DEFAULT 0,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            cursor.execute("CREATE INDEX idx_subscription_plan_name ON subscription_plan(name)")
            cursor.execute("CREATE INDEX idx_subscription_plan_active ON subscription_plan(is_active)")
            logger.info("✓ Created subscription_plan table")

            # Seed default plans
            seed_default_plans(cursor)
        else:
            logger.info("✓ subscription_plan table already exists")

        # 2. Create tenant_sso_config table
        if not table_exists(cursor, 'tenant_sso_config'):
            logger.info("Creating tenant_sso_config table...")
            cursor.execute("""
                CREATE TABLE tenant_sso_config (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id VARCHAR(50) NOT NULL UNIQUE,
                    google_sso_enabled BOOLEAN DEFAULT 0,
                    google_client_id VARCHAR(255),
                    google_client_secret_encrypted TEXT,
                    allowed_domains TEXT,
                    auto_provision_users BOOLEAN DEFAULT 0,
                    default_role_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
                    FOREIGN KEY (default_role_id) REFERENCES role(id)
                )
            """)
            cursor.execute("CREATE INDEX idx_tenant_sso_tenant ON tenant_sso_config(tenant_id)")
            logger.info("✓ Created tenant_sso_config table")
        else:
            logger.info("✓ tenant_sso_config table already exists")

        # 3. Add SSO columns to user table
        if table_exists(cursor, 'user'):
            if not column_exists(cursor, 'user', 'auth_provider'):
                logger.info("Adding auth_provider column to user table...")
                cursor.execute("ALTER TABLE user ADD COLUMN auth_provider VARCHAR(20) DEFAULT 'local'")
                cursor.execute("CREATE INDEX idx_user_auth_provider ON user(auth_provider)")
                logger.info("✓ Added auth_provider column")

            if not column_exists(cursor, 'user', 'google_id'):
                logger.info("Adding google_id column to user table...")
                cursor.execute("ALTER TABLE user ADD COLUMN google_id VARCHAR(255)")
                cursor.execute("CREATE UNIQUE INDEX idx_user_google_id ON user(google_id)")
                logger.info("✓ Added google_id column")

            if not column_exists(cursor, 'user', 'avatar_url'):
                logger.info("Adding avatar_url column to user table...")
                cursor.execute("ALTER TABLE user ADD COLUMN avatar_url VARCHAR(500)")
                logger.info("✓ Added avatar_url column")

            # Make password_hash nullable for SSO users
            # SQLite doesn't support ALTER COLUMN, so we skip this for existing tables
            logger.info("Note: password_hash nullable change requires table recreation (skipped)")

        # 4. Add plan_id column to tenant table
        if table_exists(cursor, 'tenant'):
            if not column_exists(cursor, 'tenant', 'plan_id'):
                logger.info("Adding plan_id column to tenant table...")
                cursor.execute("ALTER TABLE tenant ADD COLUMN plan_id INTEGER REFERENCES subscription_plan(id)")
                cursor.execute("CREATE INDEX idx_tenant_plan_id ON tenant(plan_id)")
                logger.info("✓ Added plan_id column")

                # Migrate existing plan strings to plan_id
                migrate_tenant_plans(cursor)

        conn.commit()
        logger.info("✓ Plans and SSO migration completed successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()


def seed_default_plans(cursor):
    """Seed default subscription plans."""
    import json

    logger.info("Seeding default subscription plans...")

    plans = [
        {
            'name': 'free',
            'display_name': 'Free',
            'description': 'Perfect for getting started with basic automation needs.',
            'price_monthly': 0,
            'price_yearly': 0,
            'max_users': 1,
            'max_agents': 1,
            'max_monthly_requests': 100,
            'max_knowledge_docs': 5,
            'max_flows': 2,
            'max_mcp_instances': 1,
            'features_json': json.dumps(['basic_support', 'playground']),
            'is_active': 1,
            'is_public': 1,
            'sort_order': 0
        },
        {
            'name': 'pro',
            'display_name': 'Pro',
            'description': 'For professionals who need more power and flexibility.',
            'price_monthly': 2900,  # $29.00
            'price_yearly': 29000,  # $290.00 (2 months free)
            'max_users': 5,
            'max_agents': 10,
            'max_monthly_requests': 10000,
            'max_knowledge_docs': 50,
            'max_flows': 20,
            'max_mcp_instances': 3,
            'features_json': json.dumps(['priority_support', 'playground', 'custom_tools', 'api_access']),
            'is_active': 1,
            'is_public': 1,
            'sort_order': 1
        },
        {
            'name': 'team',
            'display_name': 'Team',
            'description': 'Collaboration features for growing teams.',
            'price_monthly': 9900,  # $99.00
            'price_yearly': 99000,  # $990.00 (2 months free)
            'max_users': 20,
            'max_agents': 50,
            'max_monthly_requests': 100000,
            'max_knowledge_docs': 200,
            'max_flows': 100,
            'max_mcp_instances': 10,
            'features_json': json.dumps(['priority_support', 'playground', 'custom_tools', 'api_access', 'sso', 'audit_logs', 'advanced_analytics']),
            'is_active': 1,
            'is_public': 1,
            'sort_order': 2
        },
        {
            'name': 'enterprise',
            'display_name': 'Enterprise',
            'description': 'Custom solutions for large organizations with advanced needs.',
            'price_monthly': 0,  # Custom pricing
            'price_yearly': 0,
            'max_users': -1,  # Unlimited
            'max_agents': -1,
            'max_monthly_requests': -1,
            'max_knowledge_docs': -1,
            'max_flows': -1,
            'max_mcp_instances': -1,
            'features_json': json.dumps(['dedicated_support', 'playground', 'custom_tools', 'api_access', 'sso', 'audit_logs', 'advanced_analytics', 'sla', 'on_premise', 'custom_integrations']),
            'is_active': 1,
            'is_public': 1,
            'sort_order': 3
        }
    ]

    for plan in plans:
        cursor.execute("""
            INSERT INTO subscription_plan (
                name, display_name, description, price_monthly, price_yearly,
                max_users, max_agents, max_monthly_requests, max_knowledge_docs,
                max_flows, max_mcp_instances, features_json, is_active, is_public, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            plan['name'], plan['display_name'], plan['description'],
            plan['price_monthly'], plan['price_yearly'],
            plan['max_users'], plan['max_agents'], plan['max_monthly_requests'],
            plan['max_knowledge_docs'], plan['max_flows'], plan['max_mcp_instances'],
            plan['features_json'], plan['is_active'], plan['is_public'], plan['sort_order']
        ))

    logger.info(f"✓ Seeded {len(plans)} default plans")


def migrate_tenant_plans(cursor):
    """Migrate existing tenant plan strings to plan_id references."""
    logger.info("Migrating existing tenant plans to plan_id...")

    # Get plan name -> id mapping
    cursor.execute("SELECT id, name FROM subscription_plan")
    plan_map = {row[1]: row[0] for row in cursor.fetchall()}

    # Update tenants with matching plan names
    cursor.execute("SELECT id, plan FROM tenant WHERE plan IS NOT NULL")
    tenants = cursor.fetchall()

    updated = 0
    for tenant_id, plan_name in tenants:
        if plan_name and plan_name.lower() in plan_map:
            plan_id = plan_map[plan_name.lower()]
            cursor.execute(
                "UPDATE tenant SET plan_id = ? WHERE id = ?",
                (plan_id, tenant_id)
            )
            updated += 1

    logger.info(f"✓ Migrated {updated} tenant plan references")


def downgrade(db_path: str):
    """Reverse the migration."""
    logger.info(f"Rolling back plans and SSO migration on {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # Drop tables in reverse order
        cursor.execute("DROP TABLE IF EXISTS tenant_sso_config")
        cursor.execute("DROP TABLE IF EXISTS subscription_plan")

        # Note: SQLite doesn't support DROP COLUMN, so we can't remove
        # auth_provider, google_id, avatar_url from user table
        # or plan_id from tenant table without recreating the tables

        conn.commit()
        logger.info("✓ Rollback completed (note: user and tenant columns preserved)")

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
        print("Usage: python add_plans_and_sso.py <db_path> [--downgrade]")
        sys.exit(1)

    db_path = sys.argv[1]

    if len(sys.argv) > 2 and sys.argv[2] == '--downgrade':
        downgrade(db_path)
    else:
        upgrade(db_path)
