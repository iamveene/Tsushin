from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import QueuePool
from contextlib import contextmanager
import os
import json
from models import Base, Config, SlashCommand
# Phase 7.6.3: Import RBAC models to register with Base.metadata
import models_rbac  # noqa: F401
from models_rbac import Role, Permission, RolePermission
from services.persona_seeding import seed_default_personas
from services.tone_preset_seeding import seed_default_tone_presets
from services.shell_pattern_seeding import seed_default_security_patterns


def get_engine(db_path: str):
    """Create SQLAlchemy engine for SQLite with connection pooling (Phase 6.11.1)

    IMPORTANT: Configured for WAL mode and proper transaction visibility
    across sessions. This is critical for the shell C2 architecture where
    one session queues commands and another session (beacon checkin) reads them.
    """
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={
            "check_same_thread": False,
            "timeout": 30,
        },
        # Phase 6.11.1: Connection pooling configuration
        poolclass=QueuePool,
        pool_size=10,          # 10 connections in pool
        max_overflow=20,       # Up to 30 total connections
        pool_pre_ping=True,    # Verify connections before use
        pool_recycle=3600      # Recycle connections after 1 hour
    )

    # Set up SQLite PRAGMAs on every new connection
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        """Configure SQLite for optimal concurrent access.

        FIX (2026-01-30): Changed from WAL mode to DELETE mode for the shell C2 architecture.
        WAL mode causes session isolation issues where commands queued by one session
        aren't immediately visible to the beacon checkin session. DELETE mode ensures
        all committed changes are immediately visible to all connections.
        """
        cursor = dbapi_connection.cursor()
        # Use DELETE mode (classic mode) for immediate visibility across sessions
        # WAL mode causes session isolation issues in C2 architecture
        cursor.execute("PRAGMA journal_mode=DELETE")
        # Use NORMAL synchronous mode (good balance of safety and speed)
        cursor.execute("PRAGMA synchronous=NORMAL")
        # Enable foreign keys
        cursor.execute("PRAGMA foreign_keys=ON")
        # Increase cache size for better performance (negative = KB)
        cursor.execute("PRAGMA cache_size=-64000")  # 64MB
        # Increase busy timeout for concurrent access
        cursor.execute("PRAGMA busy_timeout=30000")  # 30 seconds
        cursor.close()

    return engine

def seed_rbac_defaults(session):
    """
    Seed default roles and permissions for RBAC system.
    Phase 7.9: Multi-tenancy support.

    This ensures the database has the required roles and permissions
    for the authentication system to function properly.
    """
    # Check if roles already exist
    existing_roles = session.query(Role).first()
    if existing_roles:
        return  # Already seeded

    print("[RBAC] Seeding default roles and permissions...")

    # Define permissions
    permissions_data = [
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
        # Custom Tools (Phase 9.3)
        ("tools.manage", "tools", "manage", "Manage custom tools (create, update, delete)"),
        ("tools.execute", "tools", "execute", "Execute custom tools"),
        # Shell/Beacon (Phase 18)
        ("shell.read", "shell", "read", "View shell integrations and commands"),
        ("shell.write", "shell", "write", "Create and manage shell integrations"),
        ("shell.execute", "shell", "execute", "Execute shell commands on beacons"),
        ("shell.approve", "shell", "approve", "Approve high-risk shell commands"),
        # Watcher (Dashboard)
        ("watcher.read", "watcher", "read", "View watcher dashboard, messages, and agent runs"),
    ]

    # Create permissions
    permissions = {}
    for name, resource, action, description in permissions_data:
        perm = Permission(name=name, resource=resource, action=action, description=description)
        session.add(perm)
        permissions[name] = perm

    session.flush()  # Get IDs

    # Define roles
    roles_data = [
        ("owner", "Owner", "Full control over the organization including billing and team management"),
        ("admin", "Admin", "Full administrative access except billing"),
        ("member", "Member", "Standard user - can create and manage own resources"),
        ("readonly", "Read-Only", "Can view resources but cannot make changes"),
    ]

    # Create roles
    roles = {}
    for name, display_name, description in roles_data:
        role = Role(name=name, display_name=display_name, description=description, is_system_role=True)
        session.add(role)
        roles[name] = role

    session.flush()  # Get IDs

    # Define role-permission mappings
    role_permissions_map = {
        "owner": [
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
            "analytics.read", "audit.read",
            "tools.manage", "tools.execute",  # Phase 9.3: Custom Tools
            "shell.read", "shell.write", "shell.execute", "shell.approve",  # Phase 18: Shell/Beacon
            "watcher.read",  # Dashboard access
        ],
        "admin": [
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
            "billing.read",  # View only
            "analytics.read", "audit.read",
            "tools.manage", "tools.execute",  # Phase 9.3: Custom Tools
            "shell.read", "shell.write", "shell.execute", "shell.approve",  # Phase 18: Shell/Beacon
            "watcher.read",  # Dashboard access
        ],
        "member": [
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
            "tools.execute",  # Phase 9.3: Members can execute but not manage tools
            "watcher.read",  # Dashboard access
        ],
        "readonly": [
            "agents.read", "contacts.read", "memory.read", "flows.read",
            "knowledge.read", "mcp.instances.read", "telegram.instances.read",  # Phase 10.1.1
            "hub.read",
            "users.read", "org.settings.read", "analytics.read",
            "watcher.read",  # Dashboard access (view only)
        ],
    }

    # Create role-permission mappings
    for role_name, perm_names in role_permissions_map.items():
        role = roles[role_name]
        for perm_name in perm_names:
            perm = permissions[perm_name]
            rp = RolePermission(role_id=role.id, permission_id=perm.id)
            session.add(rp)

    session.commit()
    print("[RBAC] Default roles and permissions seeded successfully")


def ensure_rbac_permissions(session):
    """
    Ensure all required permissions exist and are assigned to roles.
    This handles upgrades where new permissions are added after initial seeding.
    """
    # Check if watcher.read permission exists
    watcher_perm = session.query(Permission).filter(Permission.name == "watcher.read").first()

    if not watcher_perm:
        print("[RBAC] Adding missing watcher.read permission...")
        watcher_perm = Permission(
            name="watcher.read",
            resource="watcher",
            action="read",
            description="View watcher dashboard, messages, and agent runs"
        )
        session.add(watcher_perm)
        session.flush()

        # Assign to all roles
        roles = session.query(Role).filter(Role.name.in_(["owner", "admin", "member", "readonly"])).all()
        for role in roles:
            existing_mapping = session.query(RolePermission).filter(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == watcher_perm.id
            ).first()
            if not existing_mapping:
                rp = RolePermission(role_id=role.id, permission_id=watcher_perm.id)
                session.add(rp)
                print(f"[RBAC] Assigned watcher.read to role: {role.name}")

        session.commit()
        print("[RBAC] watcher.read permission added successfully")
    else:
        # Check if permission is assigned to all roles
        roles = session.query(Role).filter(Role.name.in_(["owner", "admin", "member", "readonly"])).all()
        for role in roles:
            existing_mapping = session.query(RolePermission).filter(
                RolePermission.role_id == role.id,
                RolePermission.permission_id == watcher_perm.id
            ).first()
            if not existing_mapping:
                rp = RolePermission(role_id=role.id, permission_id=watcher_perm.id)
                session.add(rp)
                print(f"[RBAC] Assigned watcher.read to role: {role.name}")

        session.commit()

    # MED-010 FIX: Ensure shell permissions exist (Phase 18)
    # Shell permissions are restricted to owner and admin roles only
    shell_permissions_data = [
        ("shell.read", "shell", "read", "View shell integrations and commands"),
        ("shell.write", "shell", "write", "Create and manage shell integrations"),
        ("shell.execute", "shell", "execute", "Execute shell commands on beacons"),
        ("shell.approve", "shell", "approve", "Approve high-risk shell commands"),
    ]

    shell_perms_added = False
    for name, resource, action, description in shell_permissions_data:
        existing_perm = session.query(Permission).filter(Permission.name == name).first()
        if not existing_perm:
            print(f"[RBAC] Adding missing {name} permission...")
            perm = Permission(name=name, resource=resource, action=action, description=description)
            session.add(perm)
            session.flush()

            # Assign shell permissions only to owner and admin roles
            roles = session.query(Role).filter(Role.name.in_(["owner", "admin"])).all()
            for role in roles:
                rp = RolePermission(role_id=role.id, permission_id=perm.id)
                session.add(rp)
                print(f"[RBAC] Assigned {name} to role: {role.name}")

            shell_perms_added = True
        else:
            # Ensure shell permissions are assigned to owner and admin roles
            roles = session.query(Role).filter(Role.name.in_(["owner", "admin"])).all()
            for role in roles:
                existing_mapping = session.query(RolePermission).filter(
                    RolePermission.role_id == role.id,
                    RolePermission.permission_id == existing_perm.id
                ).first()
                if not existing_mapping:
                    rp = RolePermission(role_id=role.id, permission_id=existing_perm.id)
                    session.add(rp)
                    print(f"[RBAC] Assigned {name} to role: {role.name}")
                    shell_perms_added = True

    if shell_perms_added:
        session.commit()
        print("[RBAC] Shell permissions ensured successfully")

    # Phase 10.1.1: Ensure Telegram permissions exist
    telegram_permissions_data = [
        ("telegram.instances.create", "telegram_instances", "create", "Create Telegram bot instances"),
        ("telegram.instances.read", "telegram_instances", "read", "View Telegram bot instances"),
        ("telegram.instances.manage", "telegram_instances", "manage", "Start/stop Telegram instances"),
        ("telegram.instances.delete", "telegram_instances", "delete", "Delete Telegram bot instances"),
    ]

    # Role assignments: owner/admin get all, member gets read/create/manage, readonly gets read
    telegram_role_assignments = {
        "owner": ["telegram.instances.create", "telegram.instances.read", "telegram.instances.manage", "telegram.instances.delete"],
        "admin": ["telegram.instances.create", "telegram.instances.read", "telegram.instances.manage", "telegram.instances.delete"],
        "member": ["telegram.instances.read", "telegram.instances.create", "telegram.instances.manage"],
        "readonly": ["telegram.instances.read"],
    }

    telegram_perms_added = False
    for name, resource, action, description in telegram_permissions_data:
        existing_perm = session.query(Permission).filter(Permission.name == name).first()
        if not existing_perm:
            print(f"[RBAC] Adding missing {name} permission...")
            perm = Permission(name=name, resource=resource, action=action, description=description)
            session.add(perm)
            session.flush()

            # Assign to roles based on mapping
            for role_name, role_perms in telegram_role_assignments.items():
                if name in role_perms:
                    role = session.query(Role).filter(Role.name == role_name).first()
                    if role:
                        rp = RolePermission(role_id=role.id, permission_id=perm.id)
                        session.add(rp)
                        print(f"[RBAC] Assigned {name} to role: {role_name}")

            telegram_perms_added = True
        else:
            # Ensure permission is assigned to correct roles
            for role_name, role_perms in telegram_role_assignments.items():
                if name in role_perms:
                    role = session.query(Role).filter(Role.name == role_name).first()
                    if role:
                        existing_mapping = session.query(RolePermission).filter(
                            RolePermission.role_id == role.id,
                            RolePermission.permission_id == existing_perm.id
                        ).first()
                        if not existing_mapping:
                            rp = RolePermission(role_id=role.id, permission_id=existing_perm.id)
                            session.add(rp)
                            print(f"[RBAC] Assigned {name} to role: {role_name}")
                            telegram_perms_added = True

    if telegram_perms_added:
        session.commit()
        print("[RBAC] Telegram permissions ensured successfully")


def seed_slash_commands(session):
    """
    Seed default slash commands for all tenants.
    Phase 16: Slash Command System.

    Commands are seeded with tenant_id="_system" to be available to all tenants.
    Tenant-specific commands can override these.
    """
    # Check if commands already exist
    existing = session.query(SlashCommand).filter(SlashCommand.tenant_id == "_system").first()
    if existing:
        return  # Already seeded

    print("[Commands] Seeding default slash commands...")

    # Define default commands
    commands_data = [
        # Invocation commands
        {
            "tenant_id": "_system",
            "category": "invocation",
            "command_name": "invoke",
            "language_code": "en",
            "pattern": r"^/invoke\s+(.+)$",
            "aliases": json.dumps(["i"]),
            "description": "Switch to a different agent",
            "help_text": "Usage: /invoke <agent_name>\nExample: /invoke kira",
            "handler_type": "built-in",
            "sort_order": 1
        },
        {
            "tenant_id": "_system",
            "category": "invocation",
            "command_name": "invocar",
            "language_code": "pt",
            "pattern": r"^/invocar\s+(.+)$",
            "aliases": json.dumps([]),
            "description": "Trocar para outro agente",
            "help_text": "Uso: /invocar <nome_agente>\nExemplo: /invocar kira",
            "handler_type": "built-in",
            "sort_order": 2
        },
        # Project commands
        {
            "tenant_id": "_system",
            "category": "project",
            "command_name": "project enter",
            "language_code": "en",
            "pattern": r"^/project\s+enter\s+(.+)$",
            "aliases": json.dumps(["p enter"]),
            "description": "Enter a project context",
            "help_text": "Usage: /project enter <project_name>\nExample: /project enter ACME",
            "handler_type": "built-in",
            "sort_order": 10
        },
        {
            "tenant_id": "_system",
            "category": "project",
            "command_name": "projeto entrar",
            "language_code": "pt",
            "pattern": r"^/projeto\s+entrar\s+(.+)$",
            "aliases": json.dumps(["p entrar"]),
            "description": "Entrar em um projeto",
            "help_text": "Uso: /projeto entrar <nome_projeto>\nExemplo: /projeto entrar ACME",
            "handler_type": "built-in",
            "sort_order": 11
        },
        {
            "tenant_id": "_system",
            "category": "project",
            "command_name": "project exit",
            "language_code": "en",
            "pattern": r"^/project\s+exit$",
            "aliases": json.dumps(["p exit"]),
            "description": "Exit current project",
            "help_text": "Usage: /project exit\nLeaves the current project context.",
            "handler_type": "built-in",
            "sort_order": 12
        },
        {
            "tenant_id": "_system",
            "category": "project",
            "command_name": "projeto sair",
            "language_code": "pt",
            "pattern": r"^/projeto\s+sair$",
            "aliases": json.dumps(["p sair"]),
            "description": "Sair do projeto atual",
            "help_text": "Uso: /projeto sair\nSai do contexto do projeto atual.",
            "handler_type": "built-in",
            "sort_order": 13
        },
        {
            "tenant_id": "_system",
            "category": "project",
            "command_name": "project list",
            "language_code": "en",
            "pattern": r"^/project\s+list$",
            "aliases": json.dumps(["p list", "projects"]),
            "description": "List available projects",
            "help_text": "Usage: /project list\nShows all projects you have access to.",
            "handler_type": "built-in",
            "sort_order": 14
        },
        {
            "tenant_id": "_system",
            "category": "project",
            "command_name": "projeto listar",
            "language_code": "pt",
            "pattern": r"^/projeto\s+listar$",
            "aliases": json.dumps(["p listar", "projetos"]),
            "description": "Listar projetos disponíveis",
            "help_text": "Uso: /projeto listar\nMostra todos os projetos que você tem acesso.",
            "handler_type": "built-in",
            "sort_order": 15
        },
        {
            "tenant_id": "_system",
            "category": "project",
            "command_name": "project info",
            "language_code": "en",
            "pattern": r"^/project\s+info$",
            "aliases": json.dumps(["p info"]),
            "description": "Show current project info",
            "help_text": "Usage: /project info\nShows details about the current project.",
            "handler_type": "built-in",
            "sort_order": 16
        },
        # Agent commands
        {
            "tenant_id": "_system",
            "category": "agent",
            "command_name": "agent info",
            "language_code": "en",
            "pattern": r"^/agent\s+info$",
            "aliases": json.dumps([]),
            "description": "Show current agent info",
            "help_text": "Usage: /agent info\nShows details about the current agent.",
            "handler_type": "built-in",
            "sort_order": 22
        },
        {
            "tenant_id": "_system",
            "category": "agent",
            "command_name": "agent skills",
            "language_code": "en",
            "pattern": r"^/agent\s+skills$",
            "aliases": json.dumps([]),
            "description": "List agent's enabled skills",
            "help_text": "Usage: /agent skills\nLists all skills enabled for the current agent.",
            "handler_type": "built-in",
            "sort_order": 23
        },
        {
            "tenant_id": "_system",
            "category": "agent",
            "command_name": "agent list",
            "language_code": "en",
            "pattern": r"^/agent\s+list$",
            "aliases": json.dumps(["a list"]),
            "description": "List all available agents",
            "help_text": "Usage: /agent list\nShows all agents with their status, LLM models, skills, and tools.",
            "handler_type": "built-in",
            "sort_order": 24
        },
        # Memory commands
        {
            "tenant_id": "_system",
            "category": "memory",
            "command_name": "memory clear",
            "language_code": "en",
            "pattern": r"^/memory\s+clear$",
            "aliases": json.dumps(["clear"]),
            "description": "Clear conversation memory",
            "help_text": "Usage: /memory clear\nClears your conversation history with the agent.",
            "handler_type": "built-in",
            "sort_order": 30
        },
        {
            "tenant_id": "_system",
            "category": "memory",
            "command_name": "memoria limpar",
            "language_code": "pt",
            "pattern": r"^/memoria\s+limpar$",
            "aliases": json.dumps(["limpar"]),
            "description": "Limpar memória da conversa",
            "help_text": "Uso: /memoria limpar\nLimpa seu histórico de conversa com o agente.",
            "handler_type": "built-in",
            "sort_order": 31
        },
        {
            "tenant_id": "_system",
            "category": "memory",
            "command_name": "memory status",
            "language_code": "en",
            "pattern": r"^/memory\s+status$",
            "aliases": json.dumps([]),
            "description": "Show memory statistics",
            "help_text": "Usage: /memory status\nShows current memory usage and statistics.",
            "handler_type": "built-in",
            "sort_order": 32
        },
        {
            "tenant_id": "_system",
            "category": "memory",
            "command_name": "facts list",
            "language_code": "en",
            "pattern": r"^/facts\s+list$",
            "aliases": json.dumps(["facts"]),
            "description": "List learned facts",
            "help_text": "Usage: /facts list\nShows facts the agent has learned about you.",
            "handler_type": "built-in",
            "sort_order": 33
        },
        # System commands
        {
            "tenant_id": "_system",
            "category": "system",
            "command_name": "commands",
            "language_code": "en",
            "pattern": r"^/commands$",
            "aliases": json.dumps(["help", "?"]),
            "description": "List all available commands",
            "help_text": "Usage: /commands\nShows all commands you can use.",
            "handler_type": "built-in",
            "sort_order": 40
        },
        {
            "tenant_id": "_system",
            "category": "system",
            "command_name": "help",
            "language_code": "en",
            "pattern": r"^/help\s*(.*)$",
            "aliases": json.dumps([]),
            "description": "Get help on a command",
            "help_text": "Usage: /help [command]\nExamples: /help scheduler create, /help project enter",
            "handler_type": "built-in",
            "sort_order": 41
        },
        {
            "tenant_id": "_system",
            "category": "system",
            "command_name": "status",
            "language_code": "en",
            "pattern": r"^/status$",
            "aliases": json.dumps([]),
            "description": "Show system status",
            "help_text": "Usage: /status\nShows current agent, channel, and project context.",
            "handler_type": "built-in",
            "sort_order": 42
        },
        {
            "tenant_id": "_system",
            "category": "system",
            "command_name": "shortcuts",
            "language_code": "en",
            "pattern": r"^/shortcuts$",
            "aliases": json.dumps(["keys"]),
            "description": "Show keyboard shortcuts",
            "help_text": "Usage: /shortcuts\nShows available keyboard shortcuts.",
            "handler_type": "built-in",
            "sort_order": 43
        },
        # BUG-014 Fix: Add /tools command for listing agent tools
        {
            "tenant_id": "_system",
            "category": "system",
            "command_name": "tools",
            "language_code": "en",
            "pattern": r"^/tools$",
            "aliases": json.dumps(["t"]),
            "description": "List available tools for this agent",
            "help_text": "Usage: /tools\nShows all enabled tools and custom tools for the current agent.",
            "handler_type": "built-in",
            "sort_order": 44
        },
        {
            "tenant_id": "_system",
            "category": "system",
            "command_name": "ferramentas",
            "language_code": "pt",
            "pattern": r"^/ferramentas$",
            "aliases": json.dumps(["f"]),
            "description": "Listar ferramentas disponíveis para este agente",
            "help_text": "Uso: /ferramentas\nMostra todas as ferramentas habilitadas para o agente atual.",
            "handler_type": "built-in",
            "sort_order": 45
        },
        # Tool execution commands (singular /tool vs plural /tools for listing)
        {
            "tenant_id": "_system",
            "category": "tool",
            "command_name": "tool",
            "language_code": "en",
            "pattern": r"^/tool\s+(\w+)\s*(.*)$",
            "aliases": json.dumps([]),
            "description": "Execute a tool with arguments",
            "help_text": "Usage: /tool <tool_name> [arguments]\nExample: /tool nmap quick_scan scanme.nmap.org\nExample: /tool weather New York",
            "handler_type": "built-in",
            "sort_order": 46
        },
        {
            "tenant_id": "_system",
            "category": "tool",
            "command_name": "ferramenta",
            "language_code": "pt",
            "pattern": r"^/ferramenta\s+(\w+)\s*(.*)$",
            "aliases": json.dumps([]),
            "description": "Executar uma ferramenta com argumentos",
            "help_text": "Uso: /ferramenta <nome_ferramenta> [argumentos]\nExemplo: /ferramenta nmap quick_scan scanme.nmap.org\nExemplo: /ferramenta weather São Paulo",
            "handler_type": "built-in",
            "sort_order": 47
        },
        # Tool output injection commands
        {
            "tenant_id": "_system",
            "category": "tool",
            "command_name": "inject",
            "language_code": "en",
            "pattern": r"^/inject\s*(.*)$",
            "aliases": json.dumps(["recall"]),
            "description": "Inject tool execution output into conversation",
            "help_text": "Usage: /inject [id|tool_name|list|clear]\nExamples:\n  /inject list - List available tool executions\n  /inject 1 - Inject execution #1\n  /inject nmap - Inject latest nmap output\n  /inject clear - Clear all injected tool outputs",
            "handler_type": "built-in",
            "sort_order": 48
        },
        {
            "tenant_id": "_system",
            "category": "tool",
            "command_name": "inject list",
            "language_code": "en",
            "pattern": r"^/inject\s+list$",
            "aliases": json.dumps([]),
            "description": "List available tool executions for injection",
            "help_text": "Usage: /inject list\nShows all tool executions that can be injected into conversation.",
            "handler_type": "built-in",
            "sort_order": 49
        },
        {
            "tenant_id": "_system",
            "category": "tool",
            "command_name": "inject clear",
            "language_code": "en",
            "pattern": r"^/inject\s+clear$",
            "aliases": json.dumps([]),
            "description": "Clear all injected tool outputs",
            "help_text": "Usage: /inject clear\nRemoves all tool outputs from the injection buffer.",
            "handler_type": "built-in",
            "sort_order": 50
        },
        {
            "tenant_id": "_system",
            "category": "tool",
            "command_name": "injetar",
            "language_code": "pt",
            "pattern": r"^/injetar\s*(.*)$",
            "aliases": json.dumps([]),
            "description": "Injetar saída de execução de ferramenta na conversa",
            "help_text": "Uso: /injetar [id|nome_ferramenta|list|clear]\nExemplos:\n  /injetar list - Listar execuções disponíveis\n  /injetar 1 - Injetar execução #1\n  /injetar nmap - Injetar última saída do nmap\n  /injetar clear - Limpar todas as saídas injetadas",
            "handler_type": "built-in",
            "sort_order": 51
        },
        # Flows/Automation commands
        {
            "tenant_id": "_system",
            "category": "flows",
            "command_name": "flows run",
            "language_code": "en",
            "pattern": r"^/flows\s+run\s+(.+)$",
            "aliases": json.dumps([]),
            "description": "Execute a workflow by name or ID",
            "help_text": "Usage: /flows run <flow_name_or_id>\nExamples:\n  /flows run 5 - Run flow with ID 5\n  /flows run weekly-report - Run flow by name\n\nRequires: Automation skill enabled",
            "handler_type": "built-in",
            "sort_order": 52
        },
        {
            "tenant_id": "_system",
            "category": "flows",
            "command_name": "flows list",
            "language_code": "en",
            "pattern": r"^/flows\s+list$",
            "aliases": json.dumps([]),
            "description": "List all available workflows",
            "help_text": "Usage: /flows list\nShows all workflows with name, ID, type, and description.\n\nRequires: Automation skill enabled",
            "handler_type": "built-in",
            "sort_order": 53
        },
        # Scheduler commands
        {
            "tenant_id": "_system",
            "category": "scheduler",
            "command_name": "scheduler info",
            "language_code": "en",
            "pattern": r"^/scheduler\s+info$",
            "aliases": json.dumps(["sched info"]),
            "description": "Show scheduler provider and account info",
            "help_text": "Usage: /scheduler info\nDisplays which calendar provider is configured for this agent (Flows, Google Calendar, or Asana).",
            "handler_type": "built-in",
            "sort_order": 60
        },
        {
            "tenant_id": "_system",
            "category": "scheduler",
            "command_name": "scheduler list",
            "language_code": "en",
            "pattern": r"^/scheduler\s+list(?:\s+(.+))?$",
            "aliases": json.dumps(["sched list"]),
            "description": "List scheduled events",
            "help_text": "Usage: /scheduler list [filter]\n\nFilters:\n  all - Next 90 days\n  today - Today's events\n  tomorrow - Tomorrow's events\n  week - Next 7 days\n  month - Next 30 days\n  <date> - Specific date (e.g., 'Jan 1', '2026-01-15')\n\nExample: /scheduler list week",
            "handler_type": "built-in",
            "sort_order": 61
        },
        {
            "tenant_id": "_system",
            "category": "scheduler",
            "command_name": "scheduler create",
            "language_code": "en",
            "pattern": r"^/scheduler\s+create\s+(.+)$",
            "aliases": json.dumps(["sched create"]),
            "description": "Create a new event with natural language",
            "help_text": "Usage: /scheduler create <description> [duration] [recurrence]\n\nExamples:\n  /scheduler create Team meeting tomorrow at 3pm\n  /scheduler create Standup daily at 9am\n  /scheduler create 1:1 with John every Monday at 2pm 30min\n  /scheduler create Review weekly at 10am 1h\n  /scheduler create Monthly sync on Jan 15 at 2pm\n\nDuration: Add '30min', '1h', '2h' etc.\nRecurrence: Use 'daily', 'weekly', 'monthly', or 'every Monday/Tuesday/etc.'",
            "handler_type": "built-in",
            "sort_order": 62
        },
        {
            "tenant_id": "_system",
            "category": "scheduler",
            "command_name": "scheduler update",
            "language_code": "en",
            "pattern": r"^/scheduler\s+update\s+(.+?)\s+(?:new_name\s+(.+?)\s+)?(?:new_description\s+(.+))?$",
            "aliases": json.dumps(["sched update"]),
            "description": "Update an event's name or description",
            "help_text": "Usage: /scheduler update <event_id_or_name> [new_name <name>] [new_description <desc>]\n\nExamples:\n  /scheduler update 123 new_name \"Sprint Planning\"\n  /scheduler update \"Team Meeting\" new_name \"Sprint Planning\" new_description \"Q1 Sprint Review\"\n  /scheduler update 456 new_description \"Updated details\"\n\nYou can update just the name, just the description, or both.",
            "handler_type": "built-in",
            "sort_order": 63
        },
        {
            "tenant_id": "_system",
            "category": "scheduler",
            "command_name": "scheduler delete",
            "language_code": "en",
            "pattern": r"^/scheduler\s+delete\s+(.+)$",
            "aliases": json.dumps(["sched delete"]),
            "description": "Delete a scheduled event",
            "help_text": "Usage: /scheduler delete <event_id_or_name>\n\nExamples:\n  /scheduler delete 123\n  /scheduler delete \"Team Meeting\"\n\nYou can delete by event ID or by name. If multiple events match the name, you'll be asked to specify the ID.",
            "handler_type": "built-in",
            "sort_order": 64
        },
    ]

    # Create commands
    for cmd_data in commands_data:
        cmd = SlashCommand(**cmd_data)
        session.add(cmd)

    session.commit()
    print(f"[Commands] Seeded {len(commands_data)} default slash commands")


def init_database(engine):
    """Initialize all tables and default config"""
    Base.metadata.create_all(engine)

    # Phase 14.5: Initialize FTS5 search index for conversation search
    # This is a virtual table that must be created separately from SQLAlchemy ORM
    try:
        from migrations.create_conversation_search_fts5 import upgrade as create_fts5
        db_path = engine.url.database
        if db_path:
            create_fts5(db_path)
    except Exception as e:
        print(f"[FTS5] Initialization skipped or already exists: {e}")

    # Phase 20: Add sentinel_protected column to existing shell_integration tables
    try:
        from migrations.add_sentinel_protected_column import upgrade_from_engine
        upgrade_from_engine(engine)
    except Exception as e:
        print(f"[Sentinel Migration] Warning: {e}")

    # Phase Security-1: Add MCP API secret columns for SSRF prevention
    try:
        from migrations.add_mcp_api_secret import upgrade as upgrade_mcp_auth
        db_path = engine.url.database
        if db_path:
            upgrade_mcp_auth(db_path)
    except Exception as e:
        print(f"[MCP Auth Migration] Warning: {e}")

    # Create default config if not exists
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()

    try:
        config = session.query(Config).first()
        if not config:
            default_config = Config(
                messages_db_path=os.getenv("MCP_MESSAGES_DB_PATH", ""),
                system_prompt="You are a helpful assistant that can communicate in multiple languages. Detect the language the user is writing in and respond in the same language. Be concise, helpful, and adapt your tone to the context. Use tools when explicitly requested or when clearly beneficial.",
                response_template="{{answer}}",
                group_filters=[],
                number_filters=[],
                dm_auto_mode=True,  # Enable DM auto-reply by default for fresh installs
                ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
            )
            session.add(default_config)
            session.commit()

        # Phase 7.9: Seed RBAC defaults
        seed_rbac_defaults(session)

        # Ensure all required permissions exist (handles upgrades)
        ensure_rbac_permissions(session)

        # Phase 16: Seed default slash commands
        seed_slash_commands(session)

        # Seed default system personas (Persona Template Library)
        seed_default_personas(session)

        # Seed default system tone presets
        seed_default_tone_presets(session)

        # Phase 19: Seed default shell security patterns
        seed_default_security_patterns(session)

        # Phase 20: Seed Sentinel Security Agent configuration
        from services.sentinel_seeding import seed_sentinel_config, run_sentinel_migrations
        seed_sentinel_config(session)

        # Phase 20 Enhancement: Run Sentinel migrations (detection mode, exceptions)
        run_sentinel_migrations(session)

        # Phase v1.6.0: Sentinel Security Profiles
        from services.sentinel_seeding import migrate_to_profiles
        migrate_to_profiles(session)
    finally:
        session.close()

@contextmanager
def get_session(engine):
    """Context manager for database sessions"""
    SessionLocal = sessionmaker(bind=engine)
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# Global engine for FastAPI dependency injection
_global_engine = None


def set_global_engine(engine):
    """Set the global engine for FastAPI dependencies"""
    global _global_engine
    _global_engine = engine


def get_db():
    """
    FastAPI dependency for database sessions

    Usage:
        @app.get("/api/endpoint")
        def endpoint(db: Session = Depends(get_db)):
            # Use db here
    """
    if _global_engine is None:
        raise RuntimeError("Database engine not initialized. Call set_global_engine first.")

    SessionLocal = sessionmaker(bind=_global_engine)
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
