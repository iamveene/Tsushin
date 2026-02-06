"""
Migration: Add Custom Tools Permissions
Phase 9.3: Custom Tools Hub RBAC permissions

This migration adds tools.manage and tools.execute permissions to existing databases
and assigns them to the appropriate roles:
- owner: tools.manage, tools.execute
- admin: tools.manage, tools.execute
- member: tools.execute only

Run: python -m migrations.add_tools_permissions
"""

import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from models_rbac import Role, Permission, RolePermission


def migrate(db_path: str):
    """Add tools permissions to existing database."""

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        print("[Migration] Adding custom tools permissions...")

        # Check if permissions already exist
        existing_manage = session.query(Permission).filter(Permission.name == "tools.manage").first()
        existing_execute = session.query(Permission).filter(Permission.name == "tools.execute").first()

        # Create tools.manage permission if not exists
        if not existing_manage:
            perm_manage = Permission(
                name="tools.manage",
                resource="tools",
                action="manage",
                description="Manage custom tools (create, update, delete)"
            )
            session.add(perm_manage)
            session.flush()
            print("[Migration] Created tools.manage permission")
        else:
            perm_manage = existing_manage
            print("[Migration] tools.manage permission already exists")

        # Create tools.execute permission if not exists
        if not existing_execute:
            perm_execute = Permission(
                name="tools.execute",
                resource="tools",
                action="execute",
                description="Execute custom tools"
            )
            session.add(perm_execute)
            session.flush()
            print("[Migration] Created tools.execute permission")
        else:
            perm_execute = existing_execute
            print("[Migration] tools.execute permission already exists")

        # Get roles
        owner_role = session.query(Role).filter(Role.name == "owner").first()
        admin_role = session.query(Role).filter(Role.name == "admin").first()
        member_role = session.query(Role).filter(Role.name == "member").first()

        # Assign permissions to roles
        permissions_to_assign = [
            (owner_role, [perm_manage, perm_execute]),
            (admin_role, [perm_manage, perm_execute]),
            (member_role, [perm_execute]),  # Members can execute but not manage
        ]

        for role, perms in permissions_to_assign:
            if not role:
                continue
            for perm in perms:
                # Check if mapping already exists
                existing = session.query(RolePermission).filter(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == perm.id
                ).first()

                if not existing:
                    rp = RolePermission(role_id=role.id, permission_id=perm.id)
                    session.add(rp)
                    print(f"[Migration] Assigned {perm.name} to {role.name}")
                else:
                    print(f"[Migration] {perm.name} already assigned to {role.name}")

        session.commit()
        print("[Migration] Custom tools permissions migration completed successfully!")
        return True

    except Exception as e:
        session.rollback()
        print(f"[Migration] Error: {e}")
        return False
    finally:
        session.close()


if __name__ == "__main__":
    # Default database path
    db_path = os.environ.get("INTERNAL_DB_PATH", "/app/data/agent.db")

    # Allow override via command line
    if len(sys.argv) > 1:
        db_path = sys.argv[1]

    print(f"[Migration] Database: {db_path}")
    success = migrate(db_path)
    sys.exit(0 if success else 1)
