"""
Migration: Encrypt existing plaintext API keys (CRIT-003 fix)

This migration:
1. Adds the api_key_encrypted column to the api_key table if not exists
2. Makes api_key column nullable (recreates table since SQLite can't ALTER NULL constraint)
3. Encrypts all existing plaintext API keys using Fernet encryption
4. Clears the plaintext api_key column after successful encryption

Phase SEC-001: Security hardening - encryption at rest for API keys
"""

import sqlite3
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def make_api_key_nullable(cursor, conn):
    """
    Recreate api_key table with nullable api_key column.
    SQLite doesn't support ALTER COLUMN to change nullability.
    """
    print("  Making api_key column nullable (requires table recreation)...")

    # Check current schema
    cursor.execute("PRAGMA table_info(api_key)")
    columns = cursor.fetchall()
    api_key_nullable = True
    for col in columns:
        if col[1] == 'api_key' and col[2] == 'VARCHAR(500)' and col[3] == 1:  # notnull=1
            api_key_nullable = False
            break

    if api_key_nullable:
        print("    - api_key column is already nullable")
        return

    # Create new table with nullable api_key
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS api_key_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service VARCHAR(50) NOT NULL,
            api_key VARCHAR(500),
            api_key_encrypted TEXT,
            is_active BOOLEAN DEFAULT 1,
            tenant_id VARCHAR(50),
            created_at DATETIME,
            updated_at DATETIME
        )
    """)

    # Copy data
    cursor.execute("""
        INSERT INTO api_key_new (id, service, api_key, api_key_encrypted, is_active, tenant_id, created_at, updated_at)
        SELECT id, service, api_key, api_key_encrypted, is_active, tenant_id, created_at, updated_at
        FROM api_key
    """)

    # Drop old table and rename new one
    cursor.execute("DROP TABLE api_key")
    cursor.execute("ALTER TABLE api_key_new RENAME TO api_key")

    # Recreate index
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_api_key_service_tenant ON api_key (service, tenant_id)")

    conn.commit()
    print("    ✓ Table recreated with nullable api_key column")


def run_migration(db_path: str):
    """Add api_key_encrypted column and encrypt existing keys."""
    print(f"Running API key encryption migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if api_key table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='api_key'
    """)
    if not cursor.fetchone():
        print("  ✗ api_key table does not exist. Skipping migration.")
        conn.close()
        return

    # Get existing columns
    cursor.execute("PRAGMA table_info(api_key)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    print(f"Existing columns in api_key: {existing_columns}")

    # Step 1: Add api_key_encrypted column if not exists
    if 'api_key_encrypted' not in existing_columns:
        try:
            print("Adding api_key_encrypted column...")
            cursor.execute("ALTER TABLE api_key ADD COLUMN api_key_encrypted TEXT DEFAULT NULL")
            print("  ✓ Added api_key_encrypted column")
            conn.commit()
        except sqlite3.OperationalError as e:
            print(f"  ✗ Failed to add api_key_encrypted column: {e}")
            conn.close()
            return
    else:
        print("  - api_key_encrypted column already exists")

    # Step 2: Make api_key column nullable
    make_api_key_nullable(cursor, conn)

    # Step 3: Check if there are plaintext keys to encrypt
    cursor.execute("""
        SELECT id, service, api_key, tenant_id
        FROM api_key
        WHERE api_key IS NOT NULL AND api_key != ''
        AND (api_key_encrypted IS NULL OR api_key_encrypted = '')
    """)
    plaintext_keys = cursor.fetchall()

    if not plaintext_keys:
        print("  - No plaintext API keys to encrypt")
        conn.close()
        print("\n✅ Migration completed - no keys needed encryption")
        return

    print(f"  Found {len(plaintext_keys)} plaintext API key(s) to encrypt")

    # Step 4: Import encryption utilities (need SQLAlchemy session for encryption key)
    try:
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from hub.security import TokenEncryption
        from services.encryption_key_service import get_api_key_encryption_key

        # Create SQLAlchemy session for encryption key retrieval
        engine = create_engine(f"sqlite:///{db_path}")
        Session = sessionmaker(bind=engine)
        db_session = Session()

        # Get API key-specific encryption key (MED-001 security fix)
        encryption_key = get_api_key_encryption_key(db_session)
        if not encryption_key:
            print("  ✗ Failed to get encryption key")
            db_session.close()
            conn.close()
            return

        encryptor = TokenEncryption(encryption_key.encode())
        print("  ✓ Encryption key loaded")

        # Step 5: Encrypt each key
        success_count = 0
        for key_id, service, plaintext_key, tenant_id in plaintext_keys:
            try:
                # Create identifier for key derivation
                identifier = f"apikey_{service}_{tenant_id or 'system'}"
                encrypted_key = encryptor.encrypt(plaintext_key, identifier)

                # Update the record
                cursor.execute("""
                    UPDATE api_key
                    SET api_key_encrypted = ?, api_key = NULL
                    WHERE id = ?
                """, (encrypted_key, key_id))

                success_count += 1
                print(f"  ✓ Encrypted API key for {service} (tenant: {tenant_id or 'system'})")

            except Exception as e:
                print(f"  ✗ Failed to encrypt API key for {service}: {e}")

        conn.commit()
        db_session.close()

        print(f"\n✅ Migration completed: {success_count}/{len(plaintext_keys)} keys encrypted")

        # Verify encryption worked
        cursor.execute("""
            SELECT COUNT(*) FROM api_key
            WHERE api_key IS NOT NULL AND api_key != ''
        """)
        remaining_plaintext = cursor.fetchone()[0]
        if remaining_plaintext > 0:
            print(f"⚠️  Warning: {remaining_plaintext} plaintext key(s) remain unencrypted")
        else:
            print("✅ All API keys are now encrypted")

    except ImportError as e:
        print(f"  ✗ Failed to import encryption modules: {e}")
        print("  Make sure you're running this from the backend directory")

    conn.close()


def verify_encryption(db_path: str):
    """Verify that API keys are properly encrypted."""
    print(f"\nVerifying encryption status on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            service,
            tenant_id,
            CASE WHEN api_key IS NOT NULL AND api_key != '' THEN 'PLAINTEXT' ELSE 'CLEARED' END as plaintext_status,
            CASE WHEN api_key_encrypted IS NOT NULL AND api_key_encrypted != '' THEN 'ENCRYPTED' ELSE 'MISSING' END as encrypted_status
        FROM api_key
    """)

    rows = cursor.fetchall()
    if not rows:
        print("  No API keys found in database")
    else:
        print(f"  Found {len(rows)} API key(s):")
        for service, tenant_id, plaintext_status, encrypted_status in rows:
            status = "✓ SECURE" if plaintext_status == "CLEARED" and encrypted_status == "ENCRYPTED" else "✗ INSECURE"
            print(f"    - {service} (tenant: {tenant_id or 'system'}): {status} (plaintext={plaintext_status}, encrypted={encrypted_status})")

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
        verify_encryption(db_path)
