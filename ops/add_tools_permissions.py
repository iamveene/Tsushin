#!/usr/bin/env python3
"""
Migration Script: Add tools.manage and tools.execute permissions
Phase 9.3: Custom Tools RBAC Integration

This script adds the missing tools.manage and tools.execute permissions
to existing tenants and assigns them to appropriate roles.

Run from the backend directory:
    python ../ops/add_tools_permissions.py

Or from the project root:
    docker compose exec backend python /app/../ops/add_tools_permissions.py
"""

import sys
import os

# Add backend to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker


def run_migration():
    """Add tools.manage and tools.execute permissions to existing database."""

    # Determine database path
    db_path = os.getenv('DATABASE_PATH', './backend/data/agent.db')
    if not os.path.exists(db_path):
        # Try alternative paths
        alt_paths = [
            './data/agent.db',
            '/app/data/agent.db',
            '../backend/data/agent.db'
        ]
        for path in alt_paths:
            if os.path.exists(path):
                db_path = path
                break

    print(f"[INFO] Using database: {db_path}")

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found at {db_path}")
        return False

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        # Check if permissions already exist
        result = session.execute(
            text("SELECT COUNT(*) FROM permission WHERE name IN ('tools.manage', 'tools.execute')")
        ).fetchone()

        if result[0] >= 2:
            print("[INFO] tools.manage and tools.execute permissions already exist")
        else:
            print("[INFO] Adding tools permissions...")

            # Add permissions
            permissions_to_add = [
                ("tools.manage", "tools", "manage", "Manage custom tools (create, update, delete)"),
                ("tools.execute", "tools", "execute", "Execute custom tools"),
            ]

            for name, resource, action, description in permissions_to_add:
                # Check if permission exists
                existing = session.execute(
                    text(f"SELECT id FROM permission WHERE name = '{name}'")
                ).fetchone()

                if not existing:
                    session.execute(
                        text(f"""INSERT INTO permission (name, resource, action, description)
                            VALUES ('{name}', '{resource}', '{action}', '{description}')""")
                    )
                    print(f"  [+] Added permission: {name}")
                else:
                    print(f"  [=] Permission already exists: {name}")

            session.commit()

        # Get permission IDs
        tools_manage_id = session.execute(
            text("SELECT id FROM permission WHERE name = 'tools.manage'")
        ).fetchone()[0]

        tools_execute_id = session.execute(
            text("SELECT id FROM permission WHERE name = 'tools.execute'")
        ).fetchone()[0]

        print(f"[INFO] Permission IDs: tools.manage={tools_manage_id}, tools.execute={tools_execute_id}")

        # Assign permissions to roles
        role_permissions = [
            # Owner and Admin get both manage and execute
            ("owner", [tools_manage_id, tools_execute_id]),
            ("admin", [tools_manage_id, tools_execute_id]),
            # Member only gets execute
            ("member", [tools_execute_id]),
        ]

        for role_name, perm_ids in role_permissions:
            # Get role ID
            role_result = session.execute(
                text(f"SELECT id FROM role WHERE name = '{role_name}'")
            ).fetchone()

            if not role_result:
                print(f"  [!] Role '{role_name}' not found, skipping")
                continue

            role_id = role_result[0]

            for perm_id in perm_ids:
                # Check if mapping exists
                existing_mapping = session.execute(
                    text(f"""SELECT id FROM role_permission
                        WHERE role_id = {role_id} AND permission_id = {perm_id}""")
                ).fetchone()

                if not existing_mapping:
                    session.execute(
                        text(f"""INSERT INTO role_permission (role_id, permission_id)
                            VALUES ({role_id}, {perm_id})""")
                    )
                    perm_name = "tools.manage" if perm_id == tools_manage_id else "tools.execute"
                    print(f"  [+] Assigned {perm_name} to role: {role_name}")

        session.commit()
        print("[SUCCESS] Tools permissions migration completed!")
        return True

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        session.rollback()
        return False
    finally:
        session.close()


if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
