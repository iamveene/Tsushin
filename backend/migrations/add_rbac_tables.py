"""
Database Migration: Add RBAC & Multi-Tenancy Tables
Phase 7.9: Role-Based Access Control and Multi-Tenancy

Creates:
- tenant (organization/workspace)
- user (user accounts)
- role (role definitions)
- permission (permission definitions)
- role_permission (role-permission mappings)
- user_role (user-role-tenant mappings)
- user_invitation (pending invitations)
- password_reset_token (password reset tokens)
- system_integration (global admin managed integrations)
- tenant_system_integration_usage (tenant usage tracking)
- global_admin_audit_log (audit trail for global admin actions)

Run: python backend/migrations/add_rbac_tables.py
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


def backup_database(db_path):
    """Create timestamped backup of database."""
    backup_dir = Path("./data/backups")
    backup_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"agent_backup_pre_rbac_migration_{timestamp}.db"

    print(f"Creating backup: {backup_path}")

    import shutil
    shutil.copy2(db_path, backup_path)

    print(f"[OK] Backup created: {backup_path}")
    return backup_path


def check_prerequisites(conn):
    """
    Verify database state before migration.
    """
    cursor = conn.cursor()

    # Check if RBAC tables already exist
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='tenant'
    """)
    if cursor.fetchone():
        print("[WARN] RBAC tables already exist. Skipping migration.")
        return False

    print("[OK] Prerequisites check passed")
    return True


def upgrade(conn):
    """Apply migration: Create RBAC tables."""
    cursor = conn.cursor()

    print("\n=== Upgrading Database with RBAC Tables ===")

    # 1. Create tenant table
    print("Creating tenant table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenant (
            id VARCHAR(50) PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            slug VARCHAR(100) NOT NULL UNIQUE,
            plan VARCHAR(50) DEFAULT 'free',
            max_users INTEGER DEFAULT 1,
            max_agents INTEGER DEFAULT 1,
            max_monthly_requests INTEGER DEFAULT 1000,
            is_active BOOLEAN DEFAULT 1,
            status VARCHAR(20) DEFAULT 'active',
            created_by_global_admin INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            deleted_at DATETIME
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenant_slug ON tenant(slug)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenant_status ON tenant(status)")
    print("[OK] tenant table created")

    # 2. Create user table
    print("Creating user table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id VARCHAR(50) REFERENCES tenant(id),
            email VARCHAR(255) NOT NULL UNIQUE,
            password_hash VARCHAR(255) NOT NULL,
            full_name VARCHAR(255),
            is_global_admin BOOLEAN DEFAULT 0,
            is_active BOOLEAN DEFAULT 1,
            email_verified BOOLEAN DEFAULT 0,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_login_at DATETIME,
            deleted_at DATETIME
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_email ON user(email)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_tenant ON user(tenant_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_global_admin ON user(is_global_admin)")
    print("[OK] user table created")

    # 3. Create role table
    print("Creating role table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(50) NOT NULL UNIQUE,
            display_name VARCHAR(100) NOT NULL,
            description TEXT,
            is_system_role BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_role_name ON role(name)")
    print("[OK] role table created")

    # 4. Create permission table
    print("Creating permission table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS permission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name VARCHAR(100) NOT NULL UNIQUE,
            resource VARCHAR(50) NOT NULL,
            action VARCHAR(50) NOT NULL,
            description TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_permission_name ON permission(name)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_permission_resource ON permission(resource)")
    print("[OK] permission table created")

    # 5. Create role_permission table
    print("Creating role_permission table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS role_permission (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL REFERENCES role(id) ON DELETE CASCADE,
            permission_id INTEGER NOT NULL REFERENCES permission(id) ON DELETE CASCADE,
            UNIQUE(role_id, permission_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_role_permission_role ON role_permission(role_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_role_permission_perm ON role_permission(permission_id)")
    print("[OK] role_permission table created")

    # 6. Create user_role table
    print("Creating user_role table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_role (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            role_id INTEGER NOT NULL REFERENCES role(id) ON DELETE CASCADE,
            tenant_id VARCHAR(50) NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            assigned_by INTEGER REFERENCES user(id),
            UNIQUE(user_id, tenant_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_role_user ON user_role(user_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_user_role_tenant ON user_role(tenant_id)")
    print("[OK] user_role table created")

    # 7. Create user_invitation table
    print("Creating user_invitation table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_invitation (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id VARCHAR(50) NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            email VARCHAR(255) NOT NULL,
            role_id INTEGER NOT NULL REFERENCES role(id),
            invited_by INTEGER NOT NULL REFERENCES user(id),
            invitation_token VARCHAR(255) NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            accepted_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(tenant_id, email)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invitation_token ON user_invitation(invitation_token)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invitation_tenant ON user_invitation(tenant_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_invitation_email ON user_invitation(email)")
    print("[OK] user_invitation table created")

    # 8. Create password_reset_token table
    print("Creating password_reset_token table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS password_reset_token (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL REFERENCES user(id) ON DELETE CASCADE,
            token VARCHAR(255) NOT NULL UNIQUE,
            expires_at DATETIME NOT NULL,
            used_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_token ON password_reset_token(token)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_reset_user ON password_reset_token(user_id)")
    print("[OK] password_reset_token table created")

    # 9. Create system_integration table
    print("Creating system_integration table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_integration (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            service_type VARCHAR(50) NOT NULL,
            service_name VARCHAR(50) NOT NULL UNIQUE,
            display_name VARCHAR(100) NOT NULL,
            api_key TEXT,
            config_json TEXT,
            is_active BOOLEAN DEFAULT 1,
            usage_count INTEGER DEFAULT 0,
            last_used_at DATETIME,
            configured_by_global_admin INTEGER NOT NULL REFERENCES user(id),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_integration_type ON system_integration(service_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_sys_integration_active ON system_integration(is_active)")
    print("[OK] system_integration table created")

    # 10. Create tenant_system_integration_usage table
    print("Creating tenant_system_integration_usage table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tenant_system_integration_usage (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tenant_id VARCHAR(50) NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
            system_integration_id INTEGER NOT NULL REFERENCES system_integration(id) ON DELETE CASCADE,
            usage_count INTEGER DEFAULT 0,
            last_used_at DATETIME,
            UNIQUE(tenant_id, system_integration_id)
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenant_usage_tenant ON tenant_system_integration_usage(tenant_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_tenant_usage_integration ON tenant_system_integration_usage(system_integration_id)")
    print("[OK] tenant_system_integration_usage table created")

    # 11. Create global_admin_audit_log table
    print("Creating global_admin_audit_log table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS global_admin_audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            global_admin_id INTEGER NOT NULL REFERENCES user(id),
            action VARCHAR(100) NOT NULL,
            target_tenant_id VARCHAR(50),
            resource_type VARCHAR(50),
            resource_id VARCHAR(100),
            details_json TEXT,
            ip_address VARCHAR(50),
            user_agent VARCHAR(500),
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_admin ON global_admin_audit_log(global_admin_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_action ON global_admin_audit_log(action)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_tenant ON global_admin_audit_log(target_tenant_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_audit_created ON global_admin_audit_log(created_at)")
    print("[OK] global_admin_audit_log table created")

    # 12. Add tenant_id to agent table if not exists
    print("Adding tenant_id column to agent table...")
    try:
        cursor.execute("""
            ALTER TABLE agent
            ADD COLUMN tenant_id VARCHAR(50)
            REFERENCES tenant(id)
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_tenant ON agent(tenant_id)")
        print("[OK] tenant_id column added to agent table")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("[WARN] tenant_id column already exists in agent table")
        else:
            raise

    # 13. Add tenant_id to contact table if not exists
    print("Adding tenant_id column to contact table...")
    try:
        cursor.execute("""
            ALTER TABLE contact
            ADD COLUMN tenant_id VARCHAR(50)
            REFERENCES tenant(id)
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_contact_tenant ON contact(tenant_id)")
        print("[OK] tenant_id column added to contact table")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("[WARN] tenant_id column already exists in contact table")
        else:
            raise

    conn.commit()
    print("\n[OK] RBAC migration completed successfully")


def seed_default_roles_and_permissions(conn):
    """Seed default roles and permissions."""
    cursor = conn.cursor()

    print("\n=== Seeding Default Roles and Permissions ===")

    # Define permissions
    permissions = [
        # Agents
        ("agents.read", "agents", "read", "View agents"),
        ("agents.write", "agents", "write", "Create and update agents"),
        ("agents.delete", "agents", "delete", "Delete agents"),
        ("agents.execute", "agents", "execute", "Execute/run agents"),
        # Contacts
        ("contacts.read", "contacts", "read", "View contacts"),
        ("contacts.write", "contacts", "write", "Create and update contacts"),
        ("contacts.delete", "contacts", "delete", "Delete contacts"),
        # Memory
        ("memory.read", "memory", "read", "View memory/conversations"),
        ("memory.write", "memory", "write", "Create and update memory"),
        ("memory.delete", "memory", "delete", "Delete memory"),
        # Flows
        ("flows.read", "flows", "read", "View flows"),
        ("flows.write", "flows", "write", "Create and update flows"),
        ("flows.delete", "flows", "delete", "Delete flows"),
        ("flows.execute", "flows", "execute", "Execute flows"),
        # Knowledge
        ("knowledge.read", "knowledge", "read", "View knowledge base"),
        ("knowledge.write", "knowledge", "write", "Create and update knowledge"),
        ("knowledge.delete", "knowledge", "delete", "Delete knowledge"),
        # MCP Instances
        ("mcp.instances.read", "mcp_instances", "read", "View MCP instances"),
        ("mcp.instances.create", "mcp_instances", "create", "Create MCP instances"),
        ("mcp.instances.manage", "mcp_instances", "manage", "Manage MCP instances"),
        ("mcp.instances.delete", "mcp_instances", "delete", "Delete MCP instances"),
        # Telegram Instances (Phase 10.1.1)
        ("telegram.instances.create", "telegram_instances", "create", "Create Telegram bot instances"),
        ("telegram.instances.read", "telegram_instances", "read", "View Telegram bot instances"),
        ("telegram.instances.manage", "telegram_instances", "manage", "Start/stop Telegram instances"),
        ("telegram.instances.delete", "telegram_instances", "delete", "Delete Telegram bot instances"),
        # Hub Integrations
        ("hub.read", "hub", "read", "View hub integrations"),
        ("hub.write", "hub", "write", "Create and update hub integrations"),
        ("hub.delete", "hub", "delete", "Delete hub integrations"),
        # Users/Team
        ("users.read", "users", "read", "View team members"),
        ("users.invite", "users", "invite", "Invite team members"),
        ("users.manage", "users", "manage", "Manage team member roles"),
        ("users.remove", "users", "remove", "Remove team members"),
        # Organization settings
        ("org.settings.read", "org_settings", "read", "View organization settings"),
        ("org.settings.write", "org_settings", "write", "Update organization settings"),
        # Billing
        ("billing.read", "billing", "read", "View billing information"),
        ("billing.write", "billing", "write", "Manage billing/subscriptions"),
        # Analytics
        ("analytics.read", "analytics", "read", "View analytics and reports"),
        # Audit logs
        ("audit.read", "audit", "read", "View audit logs"),
        # Watcher (monitoring dashboard) - CRIT-007 security fix
        ("watcher.read", "watcher", "read", "View watcher dashboard, messages, and agent runs"),
    ]

    # Insert permissions
    print("Inserting permissions...")
    for name, resource, action, description in permissions:
        cursor.execute("""
            INSERT OR IGNORE INTO permission (name, resource, action, description)
            VALUES (?, ?, ?, ?)
        """, (name, resource, action, description))
    print(f"[OK] Inserted {len(permissions)} permissions")

    # Define roles
    roles = [
        ("owner", "Owner", "Full control over the organization including billing and team management", True),
        ("admin", "Admin", "Full administrative access except billing", True),
        ("member", "Member", "Standard user - can create and manage own resources", True),
        ("readonly", "Read-Only", "Can view resources but cannot make changes", True),
    ]

    # Insert roles
    print("Inserting roles...")
    for name, display_name, description, is_system in roles:
        cursor.execute("""
            INSERT OR IGNORE INTO role (name, display_name, description, is_system_role)
            VALUES (?, ?, ?, ?)
        """, (name, display_name, description, is_system))
    print(f"[OK] Inserted {len(roles)} roles")

    # Define role-permission mappings
    role_permissions = {
        "owner": [
            # All permissions
            "agents.read", "agents.write", "agents.delete", "agents.execute",
            "contacts.read", "contacts.write", "contacts.delete",
            "memory.read", "memory.write", "memory.delete",
            "flows.read", "flows.write", "flows.delete", "flows.execute",
            "knowledge.read", "knowledge.write", "knowledge.delete",
            "mcp.instances.read", "mcp.instances.create", "mcp.instances.manage", "mcp.instances.delete",
            "telegram.instances.create", "telegram.instances.read", "telegram.instances.manage", "telegram.instances.delete",  # Phase 10.1.1
            "hub.read", "hub.write", "hub.delete",
            "users.read", "users.invite", "users.manage", "users.remove",
            "org.settings.read", "org.settings.write",
            "billing.read", "billing.write",
            "analytics.read",
            "audit.read",
            "watcher.read",
        ],
        "admin": [
            # All except billing.write
            "agents.read", "agents.write", "agents.delete", "agents.execute",
            "contacts.read", "contacts.write", "contacts.delete",
            "memory.read", "memory.write", "memory.delete",
            "flows.read", "flows.write", "flows.delete", "flows.execute",
            "knowledge.read", "knowledge.write", "knowledge.delete",
            "mcp.instances.read", "mcp.instances.create", "mcp.instances.manage", "mcp.instances.delete",
            "telegram.instances.create", "telegram.instances.read", "telegram.instances.manage", "telegram.instances.delete",  # Phase 10.1.1
            "hub.read", "hub.write", "hub.delete",
            "users.read", "users.invite", "users.manage", "users.remove",
            "org.settings.read", "org.settings.write",
            "billing.read",  # Can view but not write
            "analytics.read",
            "audit.read",
            "watcher.read",
        ],
        "member": [
            # Standard user permissions
            "agents.read", "agents.write", "agents.execute",
            "contacts.read", "contacts.write",
            "memory.read", "memory.write",
            "flows.read", "flows.write", "flows.execute",
            "knowledge.read", "knowledge.write",
            "mcp.instances.read", "mcp.instances.create", "mcp.instances.manage",
            "telegram.instances.read", "telegram.instances.create", "telegram.instances.manage",  # Phase 10.1.1
            "hub.read", "hub.write",
            "users.read",
            "org.settings.read",
            "analytics.read",
            "watcher.read",
        ],
        "readonly": [
            # View-only permissions
            "agents.read",
            "contacts.read",
            "memory.read",
            "flows.read",
            "knowledge.read",
            "mcp.instances.read",
            "telegram.instances.read",  # Phase 10.1.1
            "hub.read",
            "users.read",
            "org.settings.read",
            "analytics.read",
            "watcher.read",
        ],
    }

    # Insert role-permission mappings
    print("Mapping permissions to roles...")
    for role_name, perm_names in role_permissions.items():
        # Get role ID
        cursor.execute("SELECT id FROM role WHERE name = ?", (role_name,))
        role_row = cursor.fetchone()
        if not role_row:
            print(f"[WARN] Role {role_name} not found, skipping")
            continue
        role_id = role_row[0]

        for perm_name in perm_names:
            # Get permission ID
            cursor.execute("SELECT id FROM permission WHERE name = ?", (perm_name,))
            perm_row = cursor.fetchone()
            if not perm_row:
                print(f"[WARN] Permission {perm_name} not found, skipping")
                continue
            perm_id = perm_row[0]

            # Insert mapping
            cursor.execute("""
                INSERT OR IGNORE INTO role_permission (role_id, permission_id)
                VALUES (?, ?)
            """, (role_id, perm_id))

    conn.commit()
    print("[OK] Role-permission mappings created")

    # Summary
    cursor.execute("SELECT COUNT(*) FROM permission")
    perm_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM role")
    role_count = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM role_permission")
    mapping_count = cursor.fetchone()[0]

    print(f"\n[OK] Seeding completed:")
    print(f"     - {perm_count} permissions")
    print(f"     - {role_count} roles")
    print(f"     - {mapping_count} role-permission mappings")


def verify_migration(conn):
    """Verify migration was successful."""
    cursor = conn.cursor()

    print("\n=== Verifying Migration ===")

    # Check all tables exist
    tables = [
        'tenant', 'user', 'role', 'permission', 'role_permission',
        'user_role', 'user_invitation', 'password_reset_token',
        'system_integration', 'tenant_system_integration_usage',
        'global_admin_audit_log'
    ]

    for table in tables:
        cursor.execute(f"""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name=?
        """, (table,))
        if not cursor.fetchone():
            raise Exception(f"Table {table} was not created")

        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"[OK] Table {table}: {count} records")

    # Check agent table has tenant_id
    cursor.execute("PRAGMA table_info(agent)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'tenant_id' in columns:
        print("[OK] Agent table has tenant_id column")
    else:
        print("[WARN] Agent table missing tenant_id column")

    # Check contact table has tenant_id
    cursor.execute("PRAGMA table_info(contact)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'tenant_id' in columns:
        print("[OK] Contact table has tenant_id column")
    else:
        print("[WARN] Contact table missing tenant_id column")

    print("\n[OK] Verification completed successfully")


def downgrade(conn):
    """Rollback migration: Remove RBAC tables."""
    cursor = conn.cursor()

    print("\n=== Rolling Back RBAC Migration ===")

    # Safety check: No users exist
    try:
        cursor.execute("SELECT COUNT(*) FROM user")
        user_count = cursor.fetchone()[0]
        if user_count > 0:
            raise Exception(
                f"Cannot downgrade: {user_count} users exist. "
                "Delete all users first or backup and recreate database."
            )
    except sqlite3.OperationalError:
        pass  # Table doesn't exist

    # Drop tables in reverse order (respecting foreign keys)
    tables = [
        'global_admin_audit_log',
        'tenant_system_integration_usage',
        'system_integration',
        'password_reset_token',
        'user_invitation',
        'user_role',
        'role_permission',
        'permission',
        'role',
        'user',
        'tenant',
    ]

    for table in tables:
        print(f"Dropping {table} table...")
        cursor.execute(f"DROP TABLE IF EXISTS {table}")

    conn.commit()
    print("\n[OK] Rollback completed successfully")


def main():
    """Run migration with safety checks."""
    import argparse

    parser = argparse.ArgumentParser(description="RBAC Tables Migration")
    parser.add_argument("--downgrade", action="store_true", help="Rollback migration")
    parser.add_argument("--verify-only", action="store_true", help="Only verify migration")
    parser.add_argument("--seed-only", action="store_true", help="Only seed roles/permissions (tables must exist)")
    parser.add_argument("--db-path", help="Database path (default: from env or ./data/agent.db)")
    args = parser.parse_args()

    # Get database path
    db_path = args.db_path or get_database_path()

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    print(f"Using database: {db_path}")

    # Connect to database
    conn = sqlite3.connect(db_path)

    try:
        if args.verify_only:
            verify_migration(conn)
            return

        if args.seed_only:
            seed_default_roles_and_permissions(conn)
            return

        if args.downgrade:
            confirm = input("[WARN] Are you sure you want to rollback? This will delete all RBAC data. (yes/no): ")
            if confirm.lower() != 'yes':
                print("Rollback cancelled")
                return
            downgrade(conn)
        else:
            # Check prerequisites
            if not check_prerequisites(conn):
                # Tables exist, but maybe we need to seed
                print("Running seeding only...")
                seed_default_roles_and_permissions(conn)
                verify_migration(conn)
                return

            # Create backup
            backup_path = backup_database(db_path)

            # Apply migration
            upgrade(conn)

            # Seed default data
            seed_default_roles_and_permissions(conn)

            # Verify
            verify_migration(conn)

            print(f"\n[SUCCESS] RBAC Migration completed successfully!")
            print(f"Backup: {backup_path}")
            print(f"Database: {db_path}")

    except Exception as e:
        print(f"\n[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
