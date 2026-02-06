"""
Migration: Encrypt Tenant SSO Client Secret (MED-007 fix)

This migration:
1. Adds google_client_secret_encrypted column to tenant_sso_config
2. Encrypts any existing plaintext google_client_secret values
3. Drops the plaintext google_client_secret column

Phase SEC-MED-007: Security hardening - encryption at rest for SSO secrets
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
    """Add google_client_secret_encrypted column and encrypt existing secrets."""
    print(f"Running SSO client secret encryption migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if tenant_sso_config table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='tenant_sso_config'
    """)
    if not cursor.fetchone():
        print("  ✗ tenant_sso_config table does not exist. Skipping migration.")
        conn.close()
        return

    # Get existing columns
    cursor.execute("PRAGMA table_info(tenant_sso_config)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns in tenant_sso_config: {existing_columns}")

    # Step 1: Add google_client_secret_encrypted column if not exists
    if 'google_client_secret_encrypted' not in existing_columns:
        try:
            print("Adding google_client_secret_encrypted column...")
            cursor.execute("ALTER TABLE tenant_sso_config ADD COLUMN google_client_secret_encrypted TEXT DEFAULT NULL")
            print("  ✓ Added google_client_secret_encrypted column")
            conn.commit()
        except sqlite3.OperationalError as e:
            print(f"  ✗ Failed to add google_client_secret_encrypted column: {e}")
            conn.close()
            return
    else:
        print("  - google_client_secret_encrypted column already exists")

    # Step 2: Check if there are plaintext secrets to encrypt
    if 'google_client_secret' in existing_columns:
        cursor.execute("""
            SELECT id, tenant_id, google_client_secret
            FROM tenant_sso_config
            WHERE google_client_secret IS NOT NULL AND google_client_secret != ''
            AND (google_client_secret_encrypted IS NULL OR google_client_secret_encrypted = '')
        """)
        plaintext_secrets = cursor.fetchall()

        if plaintext_secrets:
            print(f"  Found {len(plaintext_secrets)} plaintext SSO client secret(s) to encrypt")

            # Get encryption key
            try:
                from sqlalchemy import create_engine
                from sqlalchemy.orm import sessionmaker
                from services.encryption_key_service import get_google_encryption_key

                engine = create_engine(f"sqlite:///{db_path}")
                Session = sessionmaker(bind=engine)
                db_session = Session()

                encryption_key = get_google_encryption_key(db_session)
                if not encryption_key:
                    print("  ✗ Failed to get Google encryption key")
                    db_session.close()
                    conn.close()
                    return

                encryptor = MigrationTokenEncryption(encryption_key.encode())
                print("  ✓ Google encryption key loaded")

                # Encrypt each secret
                success_count = 0
                for config_id, tenant_id, plaintext_secret in plaintext_secrets:
                    try:
                        identifier = f"sso_client_secret_{tenant_id}"
                        encrypted_secret = encryptor.encrypt(plaintext_secret, identifier)

                        cursor.execute("""
                            UPDATE tenant_sso_config
                            SET google_client_secret_encrypted = ?, google_client_secret = NULL
                            WHERE id = ?
                        """, (encrypted_secret, config_id))

                        success_count += 1
                        print(f"  ✓ Encrypted SSO client secret for tenant: {tenant_id}")

                    except Exception as e:
                        print(f"  ✗ Failed to encrypt SSO client secret for tenant {tenant_id}: {e}")

                conn.commit()
                db_session.close()
                print(f"\n✅ Migration completed: {success_count}/{len(plaintext_secrets)} secrets encrypted")

            except ImportError as e:
                print(f"  ✗ Failed to import encryption modules: {e}")
                print("  Make sure you're running this from the backend directory")
        else:
            print("  - No plaintext SSO client secrets to encrypt")

    # Step 3: Remove plaintext google_client_secret column via table rebuild
    if 'google_client_secret' in existing_columns:
        print("\n  Removing plaintext google_client_secret column (table rebuild)...")
        try:
            cursor.execute("""
                CREATE TABLE tenant_sso_config_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tenant_id VARCHAR(50) UNIQUE NOT NULL,
                    google_sso_enabled INTEGER DEFAULT 0,
                    google_client_id VARCHAR(255),
                    google_client_secret_encrypted TEXT,
                    allowed_domains TEXT,
                    auto_provision_users INTEGER DEFAULT 0,
                    default_role_id INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (tenant_id) REFERENCES tenant(id),
                    FOREIGN KEY (default_role_id) REFERENCES role(id)
                )
            """)

            cursor.execute("""
                INSERT INTO tenant_sso_config_new
                    (id, tenant_id, google_sso_enabled, google_client_id, google_client_secret_encrypted,
                     allowed_domains, auto_provision_users, default_role_id, created_at, updated_at)
                SELECT
                    id, tenant_id, google_sso_enabled, google_client_id, google_client_secret_encrypted,
                    allowed_domains, auto_provision_users, default_role_id, created_at, updated_at
                FROM tenant_sso_config
            """)

            cursor.execute("DROP TABLE tenant_sso_config")
            cursor.execute("ALTER TABLE tenant_sso_config_new RENAME TO tenant_sso_config")

            # Recreate index
            cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tenant_sso_config_tenant ON tenant_sso_config(tenant_id)")

            conn.commit()
            print("  ✓ Removed plaintext google_client_secret column")

        except Exception as e:
            print(f"  ✗ Failed to remove plaintext column: {e}")
            conn.rollback()

    conn.close()
    print("\n✅ MED-007 Migration completed")


def verify_migration(db_path: str):
    """Verify the migration was successful."""
    print(f"\nVerifying migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(tenant_sso_config)")
    columns = [row[1] for row in cursor.fetchall()]

    has_encrypted = 'google_client_secret_encrypted' in columns
    has_plaintext = 'google_client_secret' in columns

    print(f"  - google_client_secret_encrypted: {'✓ EXISTS' if has_encrypted else '✗ MISSING'}")
    print(f"  - google_client_secret (plaintext): {'✗ STILL EXISTS' if has_plaintext else '✓ REMOVED'}")

    if has_encrypted and not has_plaintext:
        print("\n✅ MED-007 verification passed: SSO client secrets are now encrypted")
    else:
        print("\n⚠️  MED-007 verification issues found")

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
