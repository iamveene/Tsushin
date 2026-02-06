"""
Migration: Add service-specific encryption keys (MED-001 fix)

This migration:
1. Adds 3 new encryption key columns to Config table:
   - telegram_encryption_key
   - amadeus_encryption_key
   - api_key_encryption_key
2. Generates unique Fernet keys for each service
3. Re-encrypts existing encrypted data from shared asana_encryption_key to service-specific keys:
   - TelegramBotInstance.bot_token_encrypted -> telegram_encryption_key
   - AmadeusIntegration.api_secret_encrypted, current_access_token_encrypted -> amadeus_encryption_key
   - ApiKey.api_key_encrypted -> api_key_encryption_key

Security Fix: MED-001 - Shared Encryption Key Across Services
This separates encryption keys per service to limit blast radius if one is compromised.
"""

import sqlite3
import os
import sys
import base64
import hashlib

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Standalone TokenEncryption implementation to avoid hub package circular imports
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC


def _derive_workspace_key(master_key: bytes, workspace_identifier: str, iterations: int = 100000) -> bytes:
    """Derive a workspace-specific key from master key using PBKDF2."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=workspace_identifier.encode(),
        iterations=iterations,
    )
    derived = kdf.derive(master_key)
    return base64.urlsafe_b64encode(derived)


class MigrationTokenEncryption:
    """Standalone TokenEncryption for migration (matches hub.security.TokenEncryption)."""

    def __init__(self, master_key: bytes):
        Fernet(master_key)  # Validate format
        self.master_key = master_key

    def encrypt(self, token: str, workspace_identifier: str) -> str:
        workspace_key = _derive_workspace_key(self.master_key, workspace_identifier)
        cipher = Fernet(workspace_key)
        encrypted = cipher.encrypt(token.encode())
        return encrypted.decode()

    def decrypt(self, encrypted_token: str, workspace_identifier: str) -> str:
        workspace_key = _derive_workspace_key(self.master_key, workspace_identifier)
        cipher = Fernet(workspace_key)
        decrypted = cipher.decrypt(encrypted_token.encode())
        return decrypted.decode()


# Alias for compatibility with original hub.security.TokenEncryption
TokenEncryption = MigrationTokenEncryption


def add_encryption_key_columns(cursor, conn):
    """Add the 3 new encryption key columns to Config table."""
    print("Step 1: Adding new encryption key columns to Config table...")

    # Get existing columns
    cursor.execute("PRAGMA table_info(config)")
    existing_columns = [row[1] for row in cursor.fetchall()]
    print(f"  Existing columns: {[c for c in existing_columns if 'encryption' in c.lower()]}")

    new_columns = [
        ('telegram_encryption_key', 'VARCHAR(500)'),
        ('amadeus_encryption_key', 'VARCHAR(500)'),
        ('api_key_encryption_key', 'VARCHAR(500)'),
    ]

    for col_name, col_type in new_columns:
        if col_name not in existing_columns:
            try:
                cursor.execute(f"ALTER TABLE config ADD COLUMN {col_name} {col_type} DEFAULT NULL")
                print(f"  ✓ Added {col_name} column")
            except sqlite3.OperationalError as e:
                print(f"  ✗ Failed to add {col_name}: {e}")
                return False
        else:
            print(f"  - {col_name} already exists")

    conn.commit()
    return True


def generate_and_save_keys(cursor, conn):
    """Generate new Fernet keys for each service."""
    from cryptography.fernet import Fernet

    print("\nStep 2: Generating service-specific encryption keys...")

    # Check which keys need to be generated
    cursor.execute("""
        SELECT
            telegram_encryption_key,
            amadeus_encryption_key,
            api_key_encryption_key
        FROM config
        LIMIT 1
    """)
    row = cursor.fetchone()

    if not row:
        print("  ✗ No config row found")
        return None, None, None

    existing_telegram, existing_amadeus, existing_api_key = row

    telegram_key = existing_telegram
    amadeus_key = existing_amadeus
    api_key_key = existing_api_key

    # Generate keys for any that don't exist
    if not telegram_key:
        telegram_key = Fernet.generate_key().decode()
        cursor.execute("UPDATE config SET telegram_encryption_key = ?", (telegram_key,))
        print(f"  ✓ Generated new telegram_encryption_key")
    else:
        print(f"  - telegram_encryption_key already exists")

    if not amadeus_key:
        amadeus_key = Fernet.generate_key().decode()
        cursor.execute("UPDATE config SET amadeus_encryption_key = ?", (amadeus_key,))
        print(f"  ✓ Generated new amadeus_encryption_key")
    else:
        print(f"  - amadeus_encryption_key already exists")

    if not api_key_key:
        api_key_key = Fernet.generate_key().decode()
        cursor.execute("UPDATE config SET api_key_encryption_key = ?", (api_key_key,))
        print(f"  ✓ Generated new api_key_encryption_key")
    else:
        print(f"  - api_key_encryption_key already exists")

    conn.commit()
    return telegram_key, amadeus_key, api_key_key


def get_asana_encryption_key(cursor):
    """Get the existing asana_encryption_key from database or environment."""
    import os

    # First check database
    cursor.execute("SELECT asana_encryption_key FROM config LIMIT 1")
    row = cursor.fetchone()
    if row and row[0]:
        return row[0]

    # Fall back to environment variable (used during initial encryption)
    env_key = os.getenv('ASANA_ENCRYPTION_KEY')
    if env_key:
        print("  Using ASANA_ENCRYPTION_KEY from environment variable")
        return env_key

    return None


def re_encrypt_telegram_tokens(cursor, conn, old_key, new_key):
    """Re-encrypt Telegram bot tokens with new telegram_encryption_key."""
    print("\nStep 3a: Re-encrypting Telegram bot tokens...")

    # Check if telegram_bot_instance table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='telegram_bot_instance'
    """)
    if not cursor.fetchone():
        print("  - telegram_bot_instance table does not exist. Skipping.")
        return 0

    # Find encrypted tokens
    cursor.execute("""
        SELECT id, bot_token_encrypted, tenant_id
        FROM telegram_bot_instance
        WHERE bot_token_encrypted IS NOT NULL AND bot_token_encrypted != ''
    """)
    tokens = cursor.fetchall()

    if not tokens:
        print("  - No Telegram bot tokens to re-encrypt")
        return 0

    print(f"  Found {len(tokens)} Telegram bot token(s) to re-encrypt")

    old_encryptor = TokenEncryption(old_key.encode())
    new_encryptor = TokenEncryption(new_key.encode())

    success_count = 0
    for token_id, encrypted_token, tenant_id in tokens:
        try:
            # Identifier used for Telegram is tenant_id
            identifier = tenant_id or "default"

            # Decrypt with old key
            plaintext = old_encryptor.decrypt(encrypted_token, identifier)

            # Re-encrypt with new key
            new_encrypted = new_encryptor.encrypt(plaintext, identifier)

            # Update the record
            cursor.execute("""
                UPDATE telegram_bot_instance
                SET bot_token_encrypted = ?
                WHERE id = ?
            """, (new_encrypted, token_id))

            success_count += 1
            print(f"  ✓ Re-encrypted Telegram token ID {token_id} (tenant: {identifier})")

        except Exception as e:
            import traceback
            print(f"  ✗ Failed to re-encrypt Telegram token ID {token_id}: {e}")
            traceback.print_exc()

    conn.commit()
    return success_count


def re_encrypt_amadeus_credentials(cursor, conn, old_key, new_key):
    """Re-encrypt Amadeus API credentials with new amadeus_encryption_key."""
    TokenEncryption = MigrationTokenEncryption

    print("\nStep 3b: Re-encrypting Amadeus API credentials...")

    # Check if amadeus_integration table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='amadeus_integration'
    """)
    if not cursor.fetchone():
        print("  - amadeus_integration table does not exist. Skipping.")
        return 0

    # Find encrypted credentials
    cursor.execute("""
        SELECT id, api_secret_encrypted, current_access_token_encrypted
        FROM amadeus_integration
        WHERE (api_secret_encrypted IS NOT NULL AND api_secret_encrypted != '')
           OR (current_access_token_encrypted IS NOT NULL AND current_access_token_encrypted != '')
    """)
    integrations = cursor.fetchall()

    if not integrations:
        print("  - No Amadeus credentials to re-encrypt")
        return 0

    print(f"  Found {len(integrations)} Amadeus integration(s) to re-encrypt")

    old_encryptor = TokenEncryption(old_key.encode())
    new_encryptor = TokenEncryption(new_key.encode())

    success_count = 0
    for integration_id, api_secret_encrypted, access_token_encrypted in integrations:
        try:
            # Identifier used for Amadeus is amadeus_{integration_id}
            identifier = f"amadeus_{integration_id}"

            new_api_secret = None
            new_access_token = None

            # Re-encrypt API secret if exists
            if api_secret_encrypted:
                plaintext = old_encryptor.decrypt(api_secret_encrypted, identifier)
                new_api_secret = new_encryptor.encrypt(plaintext, identifier)

            # Re-encrypt access token if exists
            if access_token_encrypted:
                plaintext = old_encryptor.decrypt(access_token_encrypted, identifier)
                new_access_token = new_encryptor.encrypt(plaintext, identifier)

            # Update the record
            if new_api_secret or new_access_token:
                if new_api_secret and new_access_token:
                    cursor.execute("""
                        UPDATE amadeus_integration
                        SET api_secret_encrypted = ?, current_access_token_encrypted = ?
                        WHERE id = ?
                    """, (new_api_secret, new_access_token, integration_id))
                elif new_api_secret:
                    cursor.execute("""
                        UPDATE amadeus_integration
                        SET api_secret_encrypted = ?
                        WHERE id = ?
                    """, (new_api_secret, integration_id))
                elif new_access_token:
                    cursor.execute("""
                        UPDATE amadeus_integration
                        SET current_access_token_encrypted = ?
                        WHERE id = ?
                    """, (new_access_token, integration_id))

            success_count += 1
            print(f"  ✓ Re-encrypted Amadeus integration ID {integration_id}")

        except Exception as e:
            print(f"  ✗ Failed to re-encrypt Amadeus integration ID {integration_id}: {e}")

    conn.commit()
    return success_count


def re_encrypt_api_keys(cursor, conn, old_key, new_key):
    """Re-encrypt API keys with new api_key_encryption_key."""
    TokenEncryption = MigrationTokenEncryption

    print("\nStep 3c: Re-encrypting LLM API keys...")

    # Check if api_key table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='api_key'
    """)
    if not cursor.fetchone():
        print("  - api_key table does not exist. Skipping.")
        return 0

    # Find encrypted keys
    cursor.execute("""
        SELECT id, service, api_key_encrypted, tenant_id
        FROM api_key
        WHERE api_key_encrypted IS NOT NULL AND api_key_encrypted != ''
    """)
    keys = cursor.fetchall()

    if not keys:
        print("  - No API keys to re-encrypt")
        return 0

    print(f"  Found {len(keys)} API key(s) to re-encrypt")

    old_encryptor = TokenEncryption(old_key.encode())
    new_encryptor = TokenEncryption(new_key.encode())

    success_count = 0
    for key_id, service, encrypted_key, tenant_id in keys:
        try:
            # Identifier used for API keys is apikey_{service}_{tenant_id or 'system'}
            identifier = f"apikey_{service}_{tenant_id or 'system'}"

            # Decrypt with old key
            plaintext = old_encryptor.decrypt(encrypted_key, identifier)

            # Re-encrypt with new key
            new_encrypted = new_encryptor.encrypt(plaintext, identifier)

            # Update the record
            cursor.execute("""
                UPDATE api_key
                SET api_key_encrypted = ?
                WHERE id = ?
            """, (new_encrypted, key_id))

            success_count += 1
            print(f"  ✓ Re-encrypted API key for {service} (tenant: {tenant_id or 'system'})")

        except Exception as e:
            print(f"  ✗ Failed to re-encrypt API key for {service}: {e}")

    conn.commit()
    return success_count


def run_migration(db_path: str):
    """Run the full migration."""
    print(f"=" * 60)
    print("MED-001 Migration: Service-Specific Encryption Keys")
    print(f"=" * 60)
    print(f"Database: {db_path}\n")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check if config table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='config'
    """)
    if not cursor.fetchone():
        print("✗ config table does not exist. Cannot proceed.")
        conn.close()
        return

    # Step 1: Add new columns
    if not add_encryption_key_columns(cursor, conn):
        print("\n✗ Migration failed at Step 1")
        conn.close()
        return

    # Step 2: Generate new keys
    telegram_key, amadeus_key, api_key_key = generate_and_save_keys(cursor, conn)
    if not all([telegram_key, amadeus_key, api_key_key]):
        print("\n✗ Migration failed at Step 2")
        conn.close()
        return

    # Get the old shared key
    old_key = get_asana_encryption_key(cursor)
    if not old_key:
        print("\n⚠️  No existing asana_encryption_key found.")
        print("   This is expected for fresh installations.")
        print("   No re-encryption needed - new keys generated.")
        conn.close()
        print("\n✅ Migration completed successfully (fresh install)")
        return

    # Step 3: Re-encrypt data
    telegram_count = re_encrypt_telegram_tokens(cursor, conn, old_key, telegram_key)
    amadeus_count = re_encrypt_amadeus_credentials(cursor, conn, old_key, amadeus_key)
    api_key_count = re_encrypt_api_keys(cursor, conn, old_key, api_key_key)

    conn.close()

    # Summary
    print("\n" + "=" * 60)
    print("Migration Summary")
    print("=" * 60)
    print(f"  Telegram tokens re-encrypted: {telegram_count}")
    print(f"  Amadeus credentials re-encrypted: {amadeus_count}")
    print(f"  API keys re-encrypted: {api_key_count}")
    print(f"\n✅ MED-001 Migration completed successfully!")
    print("\nServices now have isolated encryption keys:")
    print("  - telegram_encryption_key: Telegram bot tokens")
    print("  - amadeus_encryption_key: Amadeus API credentials")
    print("  - api_key_encryption_key: LLM provider API keys")
    print("  - asana_encryption_key: Asana OAuth tokens (unchanged)")


def verify_migration(db_path: str):
    """Verify the migration was successful."""
    print(f"\n" + "=" * 60)
    print("Verifying Migration")
    print("=" * 60)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Check encryption keys exist
    cursor.execute("""
        SELECT
            CASE WHEN telegram_encryption_key IS NOT NULL THEN 'SET' ELSE 'MISSING' END,
            CASE WHEN amadeus_encryption_key IS NOT NULL THEN 'SET' ELSE 'MISSING' END,
            CASE WHEN api_key_encryption_key IS NOT NULL THEN 'SET' ELSE 'MISSING' END,
            CASE WHEN asana_encryption_key IS NOT NULL THEN 'SET' ELSE 'MISSING' END,
            CASE WHEN google_encryption_key IS NOT NULL THEN 'SET' ELSE 'MISSING' END
        FROM config
        LIMIT 1
    """)
    row = cursor.fetchone()

    if row:
        print("\nEncryption Key Status:")
        print(f"  telegram_encryption_key: {row[0]}")
        print(f"  amadeus_encryption_key:  {row[1]}")
        print(f"  api_key_encryption_key:  {row[2]}")
        print(f"  asana_encryption_key:    {row[3]}")
        print(f"  google_encryption_key:   {row[4]}")

        all_set = all(status == 'SET' for status in row[:4])  # First 4 are the ones we care about
        if all_set:
            print("\n✅ All service-specific encryption keys are configured")
        else:
            print("\n⚠️  Some encryption keys are missing")
    else:
        print("  ✗ No config row found")

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
