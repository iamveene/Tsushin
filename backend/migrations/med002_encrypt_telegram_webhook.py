"""
Migration: Encrypt Telegram Webhook Secret (MED-002 fix)

This migration:
1. Adds webhook_secret_encrypted column to telegram_bot_instance
2. Encrypts any existing plaintext webhook secrets using Fernet encryption
3. Drops the plaintext webhook_secret column

Phase SEC-MED-002: Security hardening - encryption at rest for webhook secrets
"""

import sqlite3
import os
import sys
from base64 import urlsafe_b64encode
from hashlib import pbkdf2_hmac

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _derive_workspace_key(master_key: bytes, workspace_identifier: str) -> bytes:
    """Derive a workspace-specific key using PBKDF2."""
    salt = f"tsushin_workspace_{workspace_identifier}".encode()
    derived = pbkdf2_hmac('sha256', master_key, salt, 100000, dklen=32)
    return urlsafe_b64encode(derived)


class MigrationTokenEncryption:
    """Standalone TokenEncryption for migration (matches hub.security.TokenEncryption)."""

    def __init__(self, master_key: bytes):
        from cryptography.fernet import Fernet
        Fernet(master_key)
        self.master_key = master_key

    def encrypt(self, token: str, workspace_identifier: str) -> str:
        from cryptography.fernet import Fernet
        workspace_key = _derive_workspace_key(self.master_key, workspace_identifier)
        cipher = Fernet(workspace_key)
        return cipher.encrypt(token.encode()).decode()


def run_migration(db_path: str):
    """Add webhook_secret_encrypted column and encrypt existing secrets."""
    print(f"Running Telegram webhook secret encryption migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if telegram_bot_instance table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='telegram_bot_instance'
    """)
    if not cursor.fetchone():
        print("  ✗ telegram_bot_instance table does not exist. Skipping migration.")
        conn.close()
        return

    # Get existing columns
    cursor.execute("PRAGMA table_info(telegram_bot_instance)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns in telegram_bot_instance: {existing_columns}")

    # Step 1: Add webhook_secret_encrypted column if not exists
    if 'webhook_secret_encrypted' not in existing_columns:
        try:
            print("Adding webhook_secret_encrypted column...")
            cursor.execute("ALTER TABLE telegram_bot_instance ADD COLUMN webhook_secret_encrypted TEXT DEFAULT NULL")
            print("  ✓ Added webhook_secret_encrypted column")
            conn.commit()
        except sqlite3.OperationalError as e:
            print(f"  ✗ Failed to add webhook_secret_encrypted column: {e}")
            conn.close()
            return
    else:
        print("  - webhook_secret_encrypted column already exists")

    # Step 2: Check if there are plaintext secrets to encrypt
    if 'webhook_secret' in existing_columns:
        cursor.execute("""
            SELECT id, tenant_id, bot_username, webhook_secret
            FROM telegram_bot_instance
            WHERE webhook_secret IS NOT NULL AND webhook_secret != ''
            AND (webhook_secret_encrypted IS NULL OR webhook_secret_encrypted = '')
        """)
        plaintext_secrets = cursor.fetchall()

        if plaintext_secrets:
            print(f"  Found {len(plaintext_secrets)} plaintext webhook secret(s) to encrypt")

            # Get encryption key
            try:
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                from services.encryption_key_service import get_telegram_encryption_key

                engine = create_engine(f"sqlite:///{db_path}")
                Session = sessionmaker(bind=engine)
                db_session = Session()

                encryption_key = get_telegram_encryption_key(db_session)
                if not encryption_key:
                    print("  ✗ Failed to get telegram encryption key")
                    db_session.close()
                    conn.close()
                    return

                encryptor = MigrationTokenEncryption(encryption_key.encode())
                print("  ✓ Telegram encryption key loaded")

                # Encrypt each secret
                success_count = 0
                for inst_id, tenant_id, bot_username, plaintext_secret in plaintext_secrets:
                    try:
                        identifier = f"telegram_webhook_{tenant_id}"
                        encrypted_secret = encryptor.encrypt(plaintext_secret, identifier)

                        cursor.execute("""
                            UPDATE telegram_bot_instance
                            SET webhook_secret_encrypted = ?, webhook_secret = NULL
                            WHERE id = ?
                        """, (encrypted_secret, inst_id))

                        success_count += 1
                        print(f"  ✓ Encrypted webhook secret for @{bot_username}")

                    except Exception as e:
                        print(f"  ✗ Failed to encrypt webhook secret for @{bot_username}: {e}")

                conn.commit()
                db_session.close()
                print(f"\n✅ Migration completed: {success_count}/{len(plaintext_secrets)} secrets encrypted")

            except ImportError as e:
                print(f"  ✗ Failed to import encryption modules: {e}")
                print("  Make sure you're running this from the backend directory")
        else:
            print("  - No plaintext webhook secrets to encrypt")

    # Step 3: Remove plaintext webhook_secret column via table rebuild
    # SQLite doesn't support DROP COLUMN directly, so we recreate the table
    if 'webhook_secret' in existing_columns:
        print("\n  Removing plaintext webhook_secret column (table rebuild)...")
        try:
            cursor.execute("""
                CREATE TABLE telegram_bot_instance_new (
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

            cursor.execute("""
                INSERT INTO telegram_bot_instance_new
                    (id, tenant_id, bot_token_encrypted, bot_username, bot_name, bot_id,
                     status, health_status, last_health_check, error_message,
                     use_webhook, webhook_url, webhook_secret_encrypted, last_update_id,
                     created_by, created_at, updated_at)
                SELECT
                    id, tenant_id, bot_token_encrypted, bot_username, bot_name, bot_id,
                    status, health_status, last_health_check, error_message,
                    use_webhook, webhook_url, webhook_secret_encrypted, last_update_id,
                    created_by, created_at, updated_at
                FROM telegram_bot_instance
            """)

            cursor.execute("DROP TABLE telegram_bot_instance")
            cursor.execute("ALTER TABLE telegram_bot_instance_new RENAME TO telegram_bot_instance")

            # Recreate indexes
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_telegram_instance_tenant ON telegram_bot_instance(tenant_id)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_telegram_instance_status ON telegram_bot_instance(status)")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_telegram_instance_username ON telegram_bot_instance(bot_username)")

            conn.commit()
            print("  ✓ Removed plaintext webhook_secret column")

        except Exception as e:
            print(f"  ✗ Failed to remove plaintext column: {e}")
            conn.rollback()

    conn.close()
    print("\n✅ MED-002 Migration completed")


def verify_migration(db_path: str):
    """Verify the migration was successful."""
    print(f"\nVerifying migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(telegram_bot_instance)")
    columns = [row[1] for row in cursor.fetchall()]

    has_encrypted = 'webhook_secret_encrypted' in columns
    has_plaintext = 'webhook_secret' in columns

    print(f"  - webhook_secret_encrypted: {'✓ EXISTS' if has_encrypted else '✗ MISSING'}")
    print(f"  - webhook_secret (plaintext): {'✗ STILL EXISTS' if has_plaintext else '✓ REMOVED'}")

    if has_encrypted and not has_plaintext:
        print("\n✅ MED-002 verification passed: Webhook secrets are now encrypted")
    else:
        print("\n⚠️  MED-002 verification issues found")

    conn.close()


if __name__ == "__main__":
    # Default database path
    db_path = os.environ.get("DATABASE_PATH", "/app/data/agent.db")

    if not os.path.exists(db_path):
        # Try local path for development
        db_path = "data/agent.db"

    if not os.path.exists(db_path):
        print(f"Database not found at: {db_path}")
        print("Please provide a valid database path via DATABASE_PATH environment variable")
    else:
        run_migration(db_path)
        verify_migration(db_path)
