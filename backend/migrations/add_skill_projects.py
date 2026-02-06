"""
Migration: Add Skill Projects tables and columns

Phase 15: Skill Projects - Cross-Channel Project Interaction

This migration:
1. Creates AgentProjectAccess table (agent-project permissions)
2. Creates UserProjectSession table (tracks active project sessions)
3. Creates ProjectCommandPattern table (multilingual command patterns)
4. Adds creator_id column to Project table (tenant-wide access)
5. Migrates existing user_id values to creator_id
6. Seeds default command patterns for PT and EN

Run with: python -m migrations.add_skill_projects
"""

import sqlite3
import os
from datetime import datetime


# Default command patterns for PT and EN
DEFAULT_COMMAND_PATTERNS = [
    # Enter project commands
    {
        "command_type": "enter",
        "language_code": "pt",
        "pattern": r"(?i)^(acessar|entrar n[oa])\s+projeto\s+(.+)$",
        "response_template": '📁 Você está no projeto "{project_name}". Pergunte sobre os documentos ou envie arquivos para adicionar.'
    },
    {
        "command_type": "enter",
        "language_code": "en",
        "pattern": r"(?i)^(access|enter)\s+project\s+(.+)$",
        "response_template": '📁 Now working in project "{project_name}". Ask questions or send files to add documents.'
    },
    # Exit project commands
    {
        "command_type": "exit",
        "language_code": "pt",
        "pattern": r"(?i)^sair\s+do\s+projeto$",
        "response_template": '✅ Você saiu do projeto "{project_name}". {summary}'
    },
    {
        "command_type": "exit",
        "language_code": "en",
        "pattern": r"(?i)^(exit|leave)\s+project$",
        "response_template": '✅ Left project "{project_name}". {summary}'
    },
    # Upload/add to project commands
    {
        "command_type": "upload",
        "language_code": "pt",
        "pattern": r"(?i)^adicionar\s+(ao\s+)?projeto$",
        "response_template": '📎 Documento "{filename}" adicionado ao projeto ({chunks} chunks processados).'
    },
    {
        "command_type": "upload",
        "language_code": "en",
        "pattern": r"(?i)^add\s+to\s+project$",
        "response_template": '📎 Document "{filename}" added to project ({chunks} chunks processed).'
    },
    # List projects commands
    {
        "command_type": "list",
        "language_code": "pt",
        "pattern": r"(?i)^(listar|meus)\s+projetos$",
        "response_template": "📋 Seus projetos:\n{project_list}"
    },
    {
        "command_type": "list",
        "language_code": "en",
        "pattern": r"(?i)^(list|my)\s+projects$",
        "response_template": "📋 Your projects:\n{project_list}"
    },
    # Help commands
    {
        "command_type": "help",
        "language_code": "pt",
        "pattern": r"(?i)^ajuda\s+(do\s+)?projeto$",
        "response_template": """📚 Comandos de Projeto:
• "acessar projeto [nome]" - Entrar em um projeto
• "sair do projeto" - Sair do projeto atual
• "listar projetos" - Ver seus projetos
• "adicionar ao projeto" - Adicionar documento (envie com o arquivo)"""
    },
    {
        "command_type": "help",
        "language_code": "en",
        "pattern": r"(?i)^project\s+help$",
        "response_template": """📚 Project Commands:
• "enter project [name]" - Enter a project
• "exit project" - Leave current project
• "list projects" - See your projects
• "add to project" - Add document (send with file)"""
    },
]


def run_migration(db_path: str):
    """Run the Skill Projects migration."""
    print(f"Running Skill Projects migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # =========================================================================
    # 1. Create AgentProjectAccess table
    # =========================================================================
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='agent_project_access'
    """)
    if not cursor.fetchone():
        print("\n1. Creating agent_project_access table...")
        cursor.execute("""
            CREATE TABLE agent_project_access (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_id INTEGER NOT NULL,
                project_id INTEGER NOT NULL,
                can_write BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agent(id),
                FOREIGN KEY (project_id) REFERENCES project(id),
                UNIQUE (agent_id, project_id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_project_agent ON agent_project_access(agent_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_agent_project_project ON agent_project_access(project_id)")
        print("  ✓ Created agent_project_access table")
    else:
        print("\n1. agent_project_access table already exists")

    # =========================================================================
    # 2. Create UserProjectSession table
    # =========================================================================
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='user_project_session'
    """)
    if not cursor.fetchone():
        print("\n2. Creating user_project_session table...")
        cursor.execute("""
            CREATE TABLE user_project_session (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id VARCHAR(50) NOT NULL,
                sender_key VARCHAR(100) NOT NULL,
                agent_id INTEGER NOT NULL,
                project_id INTEGER,
                channel VARCHAR(20) NOT NULL,
                conversation_id INTEGER,
                entered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (agent_id) REFERENCES agent(id),
                FOREIGN KEY (project_id) REFERENCES project(id),
                FOREIGN KEY (conversation_id) REFERENCES project_conversation(id),
                UNIQUE (tenant_id, sender_key, agent_id, channel)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_lookup ON user_project_session(tenant_id, sender_key, channel)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_session_tenant ON user_project_session(tenant_id)")
        print("  ✓ Created user_project_session table")
    else:
        print("\n2. user_project_session table already exists")

    # =========================================================================
    # 3. Create ProjectCommandPattern table
    # =========================================================================
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='project_command_pattern'
    """)
    if not cursor.fetchone():
        print("\n3. Creating project_command_pattern table...")
        cursor.execute("""
            CREATE TABLE project_command_pattern (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id VARCHAR(50) NOT NULL,
                command_type VARCHAR(30) NOT NULL,
                language_code VARCHAR(10) NOT NULL,
                pattern VARCHAR(200) NOT NULL,
                response_template TEXT,
                is_active BOOLEAN DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (tenant_id, command_type, language_code)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_command_pattern_tenant ON project_command_pattern(tenant_id)")
        print("  ✓ Created project_command_pattern table")
    else:
        print("\n3. project_command_pattern table already exists")

    # =========================================================================
    # 4. Add creator_id column to Project table
    # =========================================================================
    cursor.execute("PRAGMA table_info(project)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    if "creator_id" not in existing_columns:
        print("\n4. Adding creator_id column to project table...")
        cursor.execute("ALTER TABLE project ADD COLUMN creator_id INTEGER")
        print("  ✓ Added creator_id column")

        # Migrate user_id values to creator_id
        print("  Migrating user_id values to creator_id...")
        cursor.execute("UPDATE project SET creator_id = user_id WHERE creator_id IS NULL")
        migrated_count = cursor.rowcount
        print(f"  ✓ Migrated {migrated_count} projects")

        # Create index on creator_id
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_project_creator ON project(creator_id)")
        print("  ✓ Created index on creator_id")
    else:
        print("\n4. creator_id column already exists in project table")

    # =========================================================================
    # 5. Seed default command patterns (for system tenant "_system")
    # =========================================================================
    print("\n5. Seeding default command patterns...")

    # Check if patterns already exist for _system tenant
    cursor.execute("SELECT COUNT(*) FROM project_command_pattern WHERE tenant_id = '_system'")
    existing_count = cursor.fetchone()[0]

    if existing_count == 0:
        for pattern in DEFAULT_COMMAND_PATTERNS:
            cursor.execute("""
                INSERT INTO project_command_pattern
                (tenant_id, command_type, language_code, pattern, response_template, is_active)
                VALUES (?, ?, ?, ?, ?, 1)
            """, (
                "_system",
                pattern["command_type"],
                pattern["language_code"],
                pattern["pattern"],
                pattern["response_template"]
            ))
        print(f"  ✓ Seeded {len(DEFAULT_COMMAND_PATTERNS)} default command patterns")
    else:
        print(f"  - Default patterns already exist ({existing_count} patterns)")

    # =========================================================================
    # 6. Grant access to default agent for existing projects
    # =========================================================================
    print("\n6. Granting access to default agent for existing projects...")

    # Get default agent
    cursor.execute("SELECT id FROM agent WHERE is_default = 1 LIMIT 1")
    default_agent = cursor.fetchone()

    if default_agent:
        default_agent_id = default_agent[0]

        # Get projects that don't have any agent access
        cursor.execute("""
            SELECT p.id FROM project p
            LEFT JOIN agent_project_access apa ON p.id = apa.project_id
            WHERE apa.id IS NULL
        """)
        projects_without_access = cursor.fetchall()

        for (project_id,) in projects_without_access:
            cursor.execute("""
                INSERT OR IGNORE INTO agent_project_access (agent_id, project_id, can_write)
                VALUES (?, ?, 1)
            """, (default_agent_id, project_id))

        print(f"  ✓ Granted access to {len(projects_without_access)} projects for default agent")
    else:
        print("  - No default agent found, skipping")

    conn.commit()
    conn.close()
    print("\n✓ Skill Projects migration completed successfully!")


def seed_patterns_for_tenant(db_path: str, tenant_id: str):
    """
    Seed command patterns for a specific tenant.
    Call this when a new tenant is created.
    """
    print(f"Seeding command patterns for tenant: {tenant_id}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    for pattern in DEFAULT_COMMAND_PATTERNS:
        cursor.execute("""
            INSERT OR IGNORE INTO project_command_pattern
            (tenant_id, command_type, language_code, pattern, response_template, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (
            tenant_id,
            pattern["command_type"],
            pattern["language_code"],
            pattern["pattern"],
            pattern["response_template"]
        ))

    conn.commit()
    conn.close()
    print(f"  ✓ Seeded {len(DEFAULT_COMMAND_PATTERNS)} patterns for {tenant_id}")


if __name__ == "__main__":
    # Default database path
    db_path = os.environ.get("DATABASE_PATH", "/app/data/agent.db")

    # Also try local path for development
    if not os.path.exists(db_path):
        db_path = os.path.join(os.path.dirname(__file__), "..", "data", "agent.db")

    if os.path.exists(db_path):
        run_migration(db_path)
    else:
        print(f"Database not found at: {db_path}")
        print("Please provide a valid database path via DATABASE_PATH environment variable")
