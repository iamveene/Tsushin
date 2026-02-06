"""
Migration: Fix GoogleFlightsIntegration encryption (CRIT-004)

This migration re-encrypts all existing GoogleFlightsIntegration.api_key_encrypted
values using the correct encryption key and identifier pattern.

Problem:
- Old encryption used JWT_SECRET_KEY which is volatile (auto-generated on container restart)
- New encryption uses api_key_encryption_key which is stored in Config table

Solution:
- Get the decrypted API key from ApiKey table (which uses correct encryption)
- Re-encrypt it for GoogleFlightsIntegration using the same encryption key and identifier

Run with: python migrations/crit004_fix_googleflights_encryption.py
"""

import os
import sys
import logging
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def derive_workspace_key(master_key: bytes, workspace_identifier: str) -> bytes:
    """Derive a workspace-specific Fernet key from master key."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=workspace_identifier.encode(),
        iterations=100000,
    )
    derived = kdf.derive(master_key)
    return base64.urlsafe_b64encode(derived)


def decrypt_api_key(encrypted_value: str, encryption_key: str, identifier: str) -> str:
    """Decrypt an API key."""
    workspace_key = derive_workspace_key(encryption_key.encode(), identifier)
    cipher = Fernet(workspace_key)
    return cipher.decrypt(encrypted_value.encode()).decode()


def encrypt_api_key(plaintext_key: str, encryption_key: str, identifier: str) -> str:
    """Encrypt an API key."""
    workspace_key = derive_workspace_key(encryption_key.encode(), identifier)
    cipher = Fernet(workspace_key)
    return cipher.encrypt(plaintext_key.encode()).decode()


def run_migration(db_path: str):
    """Re-encrypt GoogleFlightsIntegration keys with correct encryption."""
    logger.info(f"Running GoogleFlightsIntegration encryption fix on: {db_path}")

    from sqlalchemy import create_engine, text

    engine = create_engine(f"sqlite:///{db_path}")

    with engine.connect() as conn:
        try:
            # Get the encryption key from Config table
            result = conn.execute(text("SELECT api_key_encryption_key FROM config LIMIT 1"))
            row = result.fetchone()
            if not row or not row[0]:
                logger.error("ERROR: No api_key_encryption_key found in config table")
                return False

            encryption_key = row[0]
            logger.info("Got encryption key from config table")

            # Get all GoogleFlightsIntegration records
            result = conn.execute(text("""
                SELECT gf.id, gf.api_key_encrypted, hi.tenant_id
                FROM google_flights_integration gf
                JOIN hub_integration hi ON gf.id = hi.id
            """))
            integrations = result.fetchall()
            logger.info(f"Found {len(integrations)} GoogleFlightsIntegration record(s)")

            if not integrations:
                logger.info("No GoogleFlightsIntegration records to migrate")
                return True

            success_count = 0
            skip_count = 0
            error_count = 0

            for integration_id, current_encrypted, tenant_id in integrations:
                try:
                    # Get the decrypted API key from ApiKey table
                    # First try google_flights service, then serpapi
                    api_key_result = conn.execute(text("""
                        SELECT api_key, api_key_encrypted, tenant_id, service
                        FROM api_key
                        WHERE service IN ('google_flights', 'serpapi')
                          AND is_active = 1
                          AND (tenant_id = :tenant_id OR tenant_id IS NULL)
                        ORDER BY
                          CASE WHEN service = 'google_flights' THEN 0 ELSE 1 END,
                          CASE WHEN tenant_id = :tenant_id THEN 0 ELSE 1 END
                        LIMIT 1
                    """), {"tenant_id": tenant_id})
                    api_key_row = api_key_result.fetchone()

                    if not api_key_row:
                        logger.warning(f"  SKIP: No API key found for integration id={integration_id} (tenant: {tenant_id or 'system'})")
                        skip_count += 1
                        continue

                    plaintext_key, encrypted_key, key_tenant_id, service = api_key_row

                    # Get decrypted key
                    decrypted_key = None
                    if plaintext_key:
                        decrypted_key = plaintext_key
                        logger.debug(f"    Using plaintext key from {service}")
                    elif encrypted_key:
                        try:
                            identifier = f"apikey_{service}_{key_tenant_id or 'system'}"
                            decrypted_key = decrypt_api_key(encrypted_key, encryption_key, identifier)
                            logger.debug(f"    Decrypted key from {service}")
                        except Exception as decrypt_err:
                            logger.error(f"  ERROR: Could not decrypt API key for integration id={integration_id}: {decrypt_err}")
                            error_count += 1
                            continue

                    if not decrypted_key:
                        logger.warning(f"  SKIP: No decrypted key available for integration id={integration_id}")
                        skip_count += 1
                        continue

                    # Re-encrypt with correct identifier for GoogleFlightsIntegration
                    identifier = f"apikey_google_flights_{tenant_id or 'system'}"
                    new_encrypted = encrypt_api_key(decrypted_key, encryption_key, identifier)

                    # Update the record
                    conn.execute(text("""
                        UPDATE google_flights_integration
                        SET api_key_encrypted = :new_encrypted
                        WHERE id = :id
                    """), {"new_encrypted": new_encrypted, "id": integration_id})
                    conn.commit()

                    logger.info(f"  OK: Re-encrypted integration id={integration_id} (tenant: {tenant_id or 'system'})")
                    success_count += 1

                except Exception as e:
                    logger.error(f"  ERROR: Failed to re-encrypt integration id={integration_id}: {e}")
                    error_count += 1

            logger.info(f"\nMigration completed: {success_count} success, {skip_count} skipped, {error_count} errors")
            return error_count == 0

        except Exception as e:
            logger.error(f"Migration failed: {e}")
            import traceback
            traceback.print_exc()
            return False


def main():
    # Try common database paths
    db_paths = [
        os.environ.get("DATABASE_PATH"),
        "/app/data/agent.db",
        "data/agent.db",
        "../data/agent.db",
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "agent.db")
    ]

    db_path = None
    for path in db_paths:
        if path and os.path.exists(path):
            db_path = path
            break

    if not db_path:
        logger.error(f"Database not found. Tried: {[p for p in db_paths if p]}")
        sys.exit(1)

    success = run_migration(db_path)
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
