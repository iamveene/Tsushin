"""
Phase 10.1.1: Telegram Integration Migration

Adds:
- telegram_id, telegram_username to Contact table
- TelegramBotInstance table
- channel field to MessageCache
- RBAC permissions for Telegram
"""

import sqlite3
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

def run_migration(db_path: str = "backend/data/agent.db"):
    """Run the Telegram integration migration."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    try:
        # 1. Add telegram fields to Contact
        cursor.execute("PRAGMA table_info(contact)")
        columns = [col[1] for col in cursor.fetchall()]

        if "telegram_id" not in columns:
            cursor.execute("ALTER TABLE contact ADD COLUMN telegram_id TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_telegram_id ON contact(telegram_id)")
            logger.info("Added contact.telegram_id column")

        if "telegram_username" not in columns:
            cursor.execute("ALTER TABLE contact ADD COLUMN telegram_username TEXT")
            logger.info("Added contact.telegram_username column")

        # 2. Add channel to MessageCache
        cursor.execute("PRAGMA table_info(message_cache)")
        columns = [col[1] for col in cursor.fetchall()]

        if "channel" not in columns:
            cursor.execute("ALTER TABLE message_cache ADD COLUMN channel TEXT")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_message_cache_channel ON message_cache(channel)")
            logger.info("Added message_cache.channel column")

        # 3. Create TelegramBotInstance table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS telegram_bot_instance (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id TEXT NOT NULL,
                bot_token_encrypted TEXT NOT NULL,
                bot_username TEXT NOT NULL,
                bot_name TEXT,
                bot_id TEXT,
                status TEXT DEFAULT 'inactive',
                health_status TEXT DEFAULT 'unknown',
                last_health_check TIMESTAMP,
                error_message TEXT,
                use_webhook INTEGER DEFAULT 0,
                webhook_url TEXT,
                webhook_secret_encrypted TEXT,
                last_update_id INTEGER DEFAULT 0,
                created_by INTEGER NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tenant_id) REFERENCES tenant(id),
                FOREIGN KEY (created_by) REFERENCES user(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_telegram_instance_tenant ON telegram_bot_instance(tenant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_telegram_instance_status ON telegram_bot_instance(status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_telegram_instance_username ON telegram_bot_instance(bot_username)")
        logger.info("Created telegram_bot_instance table")

        # 4. Add RBAC permissions
        telegram_permissions = [
            ("telegram.instances.create", "telegram_instances", "create", "Create Telegram bot instances"),
            ("telegram.instances.read", "telegram_instances", "read", "View Telegram bot instances"),
            ("telegram.instances.manage", "telegram_instances", "manage", "Start/stop Telegram instances"),
            ("telegram.instances.delete", "telegram_instances", "delete", "Delete Telegram bot instances"),
        ]

        for perm_name, resource, action, perm_desc in telegram_permissions:
            cursor.execute(
                "INSERT OR IGNORE INTO permission (name, resource, action, description) VALUES (?, ?, ?, ?)",
                (perm_name, resource, action, perm_desc)
            )

        # Add permissions to owner and admin roles
        for role_name in ["owner", "admin"]:
            cursor.execute("SELECT id FROM role WHERE name = ?", (role_name,))
            role = cursor.fetchone()
            if role:
                for perm_name, _, _, _ in telegram_permissions:
                    cursor.execute("SELECT id FROM permission WHERE name = ?", (perm_name,))
                    perm = cursor.fetchone()
                    if perm:
                        cursor.execute(
                            "INSERT OR IGNORE INTO role_permission (role_id, permission_id) VALUES (?, ?)",
                            (role[0], perm[0])
                        )

        logger.info("Added Telegram RBAC permissions")

        conn.commit()
        logger.info("Telegram integration migration completed successfully")

    except Exception as e:
        conn.rollback()
        logger.error(f"Migration failed: {e}")
        raise
    finally:
        conn.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_migration()
