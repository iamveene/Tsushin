"""
Database Migration: Add watcher.read Permission
Security Fix: CRIT-007 - Add authentication to watcher endpoints

This migration:
1. Adds the watcher.read permission to the permission table
2. Assigns it to all existing roles (owner, admin, member, readonly)

Run: python backend/migrations/add_watcher_permission.py
"""

import sys
import os
import sqlite3
from datetime import datetime
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def get_database_path():
    """Get database path from environment or default."""
    return os.getenv("INTERNAL_DB_PATH", "./data/agent.db")


def upgrade(conn):
    """Apply migration: Add watcher.read permission."""
    cursor = conn.cursor()

    print("\n=== Adding watcher.read Permission (CRIT-007 Security Fix) ===")

    # 1. Check if permission already exists
    cursor.execute("SELECT id FROM permission WHERE name = 'watcher.read'")
    existing = cursor.fetchone()

    if existing:
        print("[WARN] watcher.read permission already exists, skipping creation")
        perm_id = existing[0]
    else:
        # 2. Insert the watcher.read permission
        print("Inserting watcher.read permission...")
        cursor.execute("""
            INSERT INTO permission (name, resource, action, description)
            VALUES ('watcher.read', 'watcher', 'read', 'View watcher dashboard, messages, and agent runs')
        """)
        perm_id = cursor.lastrowid
        print(f"[OK] Permission created with id={perm_id}")

    # 3. Assign to all roles (owner, admin, member, readonly)
    roles_to_assign = ['owner', 'admin', 'member', 'readonly']

    for role_name in roles_to_assign:
        # Get role ID
        cursor.execute("SELECT id FROM role WHERE name = ?", (role_name,))
        role_row = cursor.fetchone()

        if not role_row:
            print(f"[WARN] Role '{role_name}' not found, skipping")
            continue

        role_id = role_row[0]

        # Check if mapping already exists
        cursor.execute("""
            SELECT id FROM role_permission
            WHERE role_id = ? AND permission_id = ?
        """, (role_id, perm_id))

        if cursor.fetchone():
            print(f"[OK] watcher.read already assigned to {role_name}")
        else:
            cursor.execute("""
                INSERT INTO role_permission (role_id, permission_id)
                VALUES (?, ?)
            """, (role_id, perm_id))
            print(f"[OK] watcher.read assigned to {role_name}")

    conn.commit()
    print("\n[OK] Migration completed successfully")


def verify(conn):
    """Verify the migration was successful."""
    cursor = conn.cursor()

    print("\n=== Verifying Migration ===")

    # Check permission exists
    cursor.execute("SELECT id, name FROM permission WHERE name = 'watcher.read'")
    perm = cursor.fetchone()
    if not perm:
        print("[ERROR] watcher.read permission not found!")
        return False
    print(f"[OK] Permission exists: id={perm[0]}, name={perm[1]}")

    # Check role assignments
    cursor.execute("""
        SELECT r.name
        FROM role r
        JOIN role_permission rp ON r.id = rp.role_id
        JOIN permission p ON rp.permission_id = p.id
        WHERE p.name = 'watcher.read'
    """)
    assigned_roles = [row[0] for row in cursor.fetchall()]
    print(f"[OK] Assigned to roles: {', '.join(assigned_roles)}")

    expected = {'owner', 'admin', 'member', 'readonly'}
    if set(assigned_roles) >= expected:
        print("[OK] All expected roles have watcher.read permission")
        return True
    else:
        missing = expected - set(assigned_roles)
        print(f"[WARN] Missing role assignments: {missing}")
        return False


def main():
    """Run the migration."""
    db_path = get_database_path()
    print(f"Database: {db_path}")

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found at {db_path}")
        sys.exit(1)

    conn = sqlite3.connect(db_path)

    try:
        upgrade(conn)
        verify(conn)
    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        conn.rollback()
        sys.exit(1)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
