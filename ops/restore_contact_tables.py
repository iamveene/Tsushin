#!/usr/bin/env python3
"""
Restore missing contact and contact_agent_mapping tables
This script recreates the tables and restores data from the October 7 backup
"""
import sqlite3
import os
import sys
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

CURRENT_DB = "./data/agent.db"
BACKUP_DB = "./data/backups/agent_backup_20251007_123303.db"


def restore_contact_tables():
    """Restore contact and contact_agent_mapping tables from backup"""

    print("=" * 60)
    print("Contact Tables Restoration Script")
    print("=" * 60)

    # Check if files exist
    if not os.path.exists(CURRENT_DB):
        print(f"ERROR: Current database not found at {CURRENT_DB}")
        return False

    if not os.path.exists(BACKUP_DB):
        print(f"ERROR: Backup database not found at {BACKUP_DB}")
        return False

    print(f"\nCurrent DB: {CURRENT_DB}")
    print(f"Backup DB: {BACKUP_DB}")

    # Create a backup of the current database before making changes
    backup_name = f"data/backups/pre_contact_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}.db"
    print(f"\nCreating safety backup: {backup_name}")
    import shutil
    shutil.copy2(CURRENT_DB, backup_name)
    print("[OK] Safety backup created")

    try:
        # Connect to both databases
        current_conn = sqlite3.connect(CURRENT_DB)
        backup_conn = sqlite3.connect(BACKUP_DB)

        current_cursor = current_conn.cursor()
        backup_cursor = backup_conn.cursor()

        # Check if contact table exists in current database
        current_cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='contact'
        """)
        contact_exists = current_cursor.fetchone() is not None

        if contact_exists:
            print("\n[INFO] Contact table already exists in current database")
            current_cursor.execute("SELECT COUNT(*) FROM contact")
            count = current_cursor.fetchone()[0]
            print(f"       Current contact count: {count}")

            response = input("\nDo you want to replace existing contact table? (yes/no): ")
            if response.lower() != 'yes':
                print("Aborted by user")
                current_conn.close()
                backup_conn.close()
                return False

            print("\nDropping existing contact table...")
            current_cursor.execute("DROP TABLE IF EXISTS contact")
            print("[OK] Contact table dropped")

        # Check if contact_agent_mapping table exists
        current_cursor.execute("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='contact_agent_mapping'
        """)
        mapping_exists = current_cursor.fetchone() is not None

        if mapping_exists:
            print("\nDropping existing contact_agent_mapping table...")
            current_cursor.execute("DROP TABLE IF EXISTS contact_agent_mapping")
            print("[OK] Contact_agent_mapping table dropped")

        # Get contact table schema from backup
        print("\nRecreating contact table...")
        backup_cursor.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='contact'
        """)
        contact_schema = backup_cursor.fetchone()[0]
        current_cursor.execute(contact_schema)
        print("[OK] Contact table created")

        # Get contact_agent_mapping table schema from backup
        print("\nRecreating contact_agent_mapping table...")
        backup_cursor.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='table' AND name='contact_agent_mapping'
        """)
        mapping_schema = backup_cursor.fetchone()[0]
        current_cursor.execute(mapping_schema)
        print("[OK] Contact_agent_mapping table created")

        # Copy data from backup to current database
        print("\nRestoring contact data...")
        backup_cursor.execute("SELECT * FROM contact")
        contacts = backup_cursor.fetchall()

        # Get column info
        backup_cursor.execute("PRAGMA table_info(contact)")
        columns = [col[1] for col in backup_cursor.fetchall()]
        placeholders = ','.join(['?' for _ in columns])

        for contact in contacts:
            current_cursor.execute(f"INSERT INTO contact VALUES ({placeholders})", contact)

        print(f"[OK] Restored {len(contacts)} contacts")

        # Restore contact_agent_mapping data
        print("\nRestoring contact-agent mappings...")
        backup_cursor.execute("SELECT * FROM contact_agent_mapping")
        mappings = backup_cursor.fetchall()

        backup_cursor.execute("PRAGMA table_info(contact_agent_mapping)")
        mapping_columns = [col[1] for col in backup_cursor.fetchall()]
        mapping_placeholders = ','.join(['?' for _ in mapping_columns])

        for mapping in mappings:
            current_cursor.execute(f"INSERT INTO contact_agent_mapping VALUES ({mapping_placeholders})", mapping)

        print(f"[OK] Restored {len(mappings)} contact-agent mappings")

        # Recreate indexes if they exist
        print("\nRecreating indexes...")
        backup_cursor.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='index' AND tbl_name='contact' AND sql IS NOT NULL
        """)
        for row in backup_cursor.fetchall():
            try:
                current_cursor.execute(row[0])
            except sqlite3.Error as e:
                print(f"[WARN] Index creation failed: {e}")

        backup_cursor.execute("""
            SELECT sql FROM sqlite_master
            WHERE type='index' AND tbl_name='contact_agent_mapping' AND sql IS NOT NULL
        """)
        for row in backup_cursor.fetchall():
            try:
                current_cursor.execute(row[0])
            except sqlite3.Error as e:
                print(f"[WARN] Index creation failed: {e}")

        print("[OK] Indexes recreated")

        # Commit changes
        current_conn.commit()

        # Verify restoration
        print("\n" + "=" * 60)
        print("Verification")
        print("=" * 60)

        current_cursor.execute("SELECT COUNT(*) FROM contact")
        contact_count = current_cursor.fetchone()[0]
        print(f"\nContacts in database: {contact_count}")

        current_cursor.execute("SELECT id, friendly_name, role FROM contact")
        for contact in current_cursor.fetchall():
            print(f"  - [{contact[0]}] {contact[1]} ({contact[2]})")

        current_cursor.execute("SELECT COUNT(*) FROM contact_agent_mapping")
        mapping_count = current_cursor.fetchone()[0]
        print(f"\nContact-Agent mappings: {mapping_count}")

        current_cursor.execute("""
            SELECT cam.id, c.friendly_name, cam.agent_id
            FROM contact_agent_mapping cam
            JOIN contact c ON c.id = cam.contact_id
        """)
        for mapping in current_cursor.fetchall():
            print(f"  - [{mapping[0]}] {mapping[1]} → Agent {mapping[2]}")

        # Close connections
        current_conn.close()
        backup_conn.close()

        print("\n" + "=" * 60)
        print("[SUCCESS] Contact tables restored successfully!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Restart the backend container/service")
        print("2. Check Agent Studio → Contacts to verify data")
        print("3. Check Agent Studio → Contact Mapping to verify mappings")

        return True

    except Exception as e:
        print(f"\n[ERROR] Restoration failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = restore_contact_tables()
    sys.exit(0 if success else 1)
