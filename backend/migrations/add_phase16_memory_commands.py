"""
Migration: Add Phase 16 Project Memory and Slash Commands

Phase 16: Project Memory System & Slash Command System

This migration:
1. Creates project_semantic_memory table (episodic memory with embeddings)
2. Creates project_fact_memory table (factual memory with CRUD)
3. Creates slash_command table (centralized command registry)
4. Adds KB/memory configuration columns to project table
5. Seeds default slash commands for all categories

Run with: python -m migrations.add_phase16_memory_commands
"""

import sqlite3
import os
from datetime import datetime


# Default slash commands for the system
DEFAULT_SLASH_COMMANDS = [
    # =====================================================================
    # INVOCATION COMMANDS
    # =====================================================================
    {
        "category": "invocation",
        "command_name": "invoke",
        "language_code": "en",
        "pattern": r"^/invoke\s+(\w+)(.*)$",
        "aliases": ["inv"],
        "description": "Directly invoke a specific agent",
        "help_text": "Usage: /invoke <agent_name> [message]\nExample: /invoke assistant Hello!",
        "sort_order": 1
    },
    {
        "category": "invocation",
        "command_name": "invocar",
        "language_code": "pt",
        "pattern": r"^/invocar\s+(\w+)(.*)$",
        "aliases": ["inv"],
        "description": "Invocar um agente específico",
        "help_text": "Uso: /invocar <nome_agente> [mensagem]\nExemplo: /invocar assistant Olá!",
        "sort_order": 1
    },
    # =====================================================================
    # PROJECT COMMANDS
    # =====================================================================
    {
        "category": "project",
        "command_name": "project enter",
        "language_code": "en",
        "pattern": r"^/project\s+enter\s+(.+)$",
        "aliases": ["p enter", "proj enter"],
        "description": "Enter a project workspace",
        "help_text": "Usage: /project enter <project_name>\nEnters the specified project context.",
        "sort_order": 10
    },
    {
        "category": "project",
        "command_name": "projeto entrar",
        "language_code": "pt",
        "pattern": r"^/projeto\s+entrar\s+(.+)$",
        "aliases": ["p entrar", "proj entrar"],
        "description": "Entrar em um projeto",
        "help_text": "Uso: /projeto entrar <nome_projeto>\nEntra no contexto do projeto.",
        "sort_order": 10
    },
    {
        "category": "project",
        "command_name": "project exit",
        "language_code": "en",
        "pattern": r"^/project\s+exit$",
        "aliases": ["p exit", "proj exit"],
        "description": "Exit current project",
        "help_text": "Usage: /project exit\nLeaves the current project context.",
        "sort_order": 11
    },
    {
        "category": "project",
        "command_name": "projeto sair",
        "language_code": "pt",
        "pattern": r"^/projeto\s+sair$",
        "aliases": ["p sair", "proj sair"],
        "description": "Sair do projeto atual",
        "help_text": "Uso: /projeto sair\nSai do contexto do projeto atual.",
        "sort_order": 11
    },
    {
        "category": "project",
        "command_name": "project list",
        "language_code": "en",
        "pattern": r"^/project\s+list$",
        "aliases": ["p list", "projects"],
        "description": "List available projects",
        "help_text": "Usage: /project list\nShows all projects you have access to.",
        "sort_order": 12
    },
    {
        "category": "project",
        "command_name": "projeto listar",
        "language_code": "pt",
        "pattern": r"^/projeto\s+listar$",
        "aliases": ["p listar", "projetos"],
        "description": "Listar projetos disponíveis",
        "help_text": "Uso: /projeto listar\nMostra todos os projetos que você tem acesso.",
        "sort_order": 12
    },
    {
        "category": "project",
        "command_name": "project info",
        "language_code": "en",
        "pattern": r"^/project\s+info$",
        "aliases": ["p info"],
        "description": "Show current project info",
        "help_text": "Usage: /project info\nDisplays details about the current project.",
        "sort_order": 13
    },
    # =====================================================================
    # AGENT COMMANDS
    # =====================================================================
    {
        "category": "agent",
        "command_name": "switch",
        "language_code": "en",
        "pattern": r"^/switch\s+(\w+)$",
        "aliases": ["sw"],
        "description": "Switch to another agent",
        "help_text": "Usage: /switch <agent_name>\nChanges the active agent.",
        "sort_order": 20
    },
    {
        "category": "agent",
        "command_name": "trocar",
        "language_code": "pt",
        "pattern": r"^/trocar\s+(\w+)$",
        "aliases": ["tr"],
        "description": "Trocar para outro agente",
        "help_text": "Uso: /trocar <nome_agente>\nMuda o agente ativo.",
        "sort_order": 20
    },
    {
        "category": "agent",
        "command_name": "agent info",
        "language_code": "en",
        "pattern": r"^/agent\s+info$",
        "aliases": ["a info"],
        "description": "Show current agent info",
        "help_text": "Usage: /agent info\nDisplays details about the current agent.",
        "sort_order": 21
    },
    {
        "category": "agent",
        "command_name": "agent skills",
        "language_code": "en",
        "pattern": r"^/agent\s+skills$",
        "aliases": ["a skills"],
        "description": "List agent skills",
        "help_text": "Usage: /agent skills\nShows enabled skills for the current agent.",
        "sort_order": 22
    },
    # =====================================================================
    # TOOL COMMANDS
    # =====================================================================
    {
        "category": "tool",
        "command_name": "tool",
        "language_code": "en",
        "pattern": r"^/tool\s+(\w+)\s*(.*)$",
        "aliases": ["t"],
        "description": "Execute a specific tool",
        "help_text": "Usage: /tool <tool_name> [arguments]\nExample: /tool weather São Paulo",
        "sort_order": 30
    },
    {
        "category": "tool",
        "command_name": "ferramenta",
        "language_code": "pt",
        "pattern": r"^/ferramenta\s+(\w+)\s*(.*)$",
        "aliases": ["f"],
        "description": "Executar uma ferramenta específica",
        "help_text": "Uso: /ferramenta <nome> [argumentos]\nExemplo: /ferramenta clima São Paulo",
        "sort_order": 30
    },
    {
        "category": "tool",
        "command_name": "weather",
        "language_code": "en",
        "pattern": r"^/weather\s+(.+)$",
        "aliases": ["w", "clima"],
        "description": "Get weather for a location",
        "help_text": "Usage: /weather <city>\nExample: /weather New York",
        "sort_order": 31
    },
    {
        "category": "tool",
        "command_name": "search",
        "language_code": "en",
        "pattern": r"^/search\s+(.+)$",
        "aliases": ["s", "buscar"],
        "description": "Search the web",
        "help_text": "Usage: /search <query>\nExample: /search latest news",
        "sort_order": 32
    },
    {
        "category": "tool",
        "command_name": "schedule",
        "language_code": "en",
        "pattern": r"^/schedule\s+(.+)$",
        "aliases": ["sched", "agendar"],
        "description": "Schedule a reminder or event",
        "help_text": "Usage: /schedule <time> <message>\nExample: /schedule 3pm Call John",
        "sort_order": 33
    },
    # =====================================================================
    # MEMORY COMMANDS
    # =====================================================================
    {
        "category": "memory",
        "command_name": "memory clear",
        "language_code": "en",
        "pattern": r"^/memory\s+clear$",
        "aliases": ["m clear", "mem clear"],
        "description": "Clear conversation memory",
        "help_text": "Usage: /memory clear\nClears the current conversation history.",
        "sort_order": 40
    },
    {
        "category": "memory",
        "command_name": "memoria limpar",
        "language_code": "pt",
        "pattern": r"^/memoria\s+limpar$",
        "aliases": ["m limpar", "mem limpar"],
        "description": "Limpar memória da conversa",
        "help_text": "Uso: /memoria limpar\nLimpa o histórico da conversa atual.",
        "sort_order": 40
    },
    {
        "category": "memory",
        "command_name": "memory status",
        "language_code": "en",
        "pattern": r"^/memory\s+status$",
        "aliases": ["m status", "mem status"],
        "description": "Show memory statistics",
        "help_text": "Usage: /memory status\nDisplays memory usage and statistics.",
        "sort_order": 41
    },
    {
        "category": "memory",
        "command_name": "facts list",
        "language_code": "en",
        "pattern": r"^/facts\s+list$",
        "aliases": ["facts", "fatos"],
        "description": "List learned facts",
        "help_text": "Usage: /facts list\nShows all learned facts about you.",
        "sort_order": 42
    },
    # =====================================================================
    # KB COMMANDS
    # =====================================================================
    {
        "category": "kb",
        "command_name": "kb search",
        "language_code": "en",
        "pattern": r"^/kb\s+search\s+(.+)$",
        "aliases": ["knowledge search"],
        "description": "Search knowledge base",
        "help_text": "Usage: /kb search <query>\nSearches the knowledge base.",
        "sort_order": 50
    },
    {
        "category": "kb",
        "command_name": "kb upload",
        "language_code": "en",
        "pattern": r"^/kb\s+upload$",
        "aliases": ["knowledge upload"],
        "description": "Upload to knowledge base",
        "help_text": "Usage: /kb upload\nEnables upload mode for the next file sent.",
        "sort_order": 51
    },
    # =====================================================================
    # CONFIG COMMANDS
    # =====================================================================
    {
        "category": "config",
        "command_name": "config set",
        "language_code": "en",
        "pattern": r"^/config\s+set\s+(\w+)\s+(.+)$",
        "aliases": ["cfg set"],
        "description": "Set a configuration value",
        "help_text": "Usage: /config set <key> <value>\nExample: /config set language pt",
        "sort_order": 60
    },
    {
        "category": "config",
        "command_name": "config get",
        "language_code": "en",
        "pattern": r"^/config\s+get\s+(\w+)$",
        "aliases": ["cfg get"],
        "description": "Get a configuration value",
        "help_text": "Usage: /config get <key>\nExample: /config get language",
        "sort_order": 61
    },
    # =====================================================================
    # SYSTEM COMMANDS
    # =====================================================================
    {
        "category": "system",
        "command_name": "commands",
        "language_code": "en",
        "pattern": r"^/commands$",
        "aliases": ["cmds", "comandos"],
        "description": "List all available commands",
        "help_text": "Usage: /commands\nShows all available slash commands.",
        "sort_order": 70
    },
    {
        "category": "system",
        "command_name": "help",
        "language_code": "en",
        "pattern": r"^/help\s*(\w*)$",
        "aliases": ["h", "ajuda"],
        "description": "Get help on commands",
        "help_text": "Usage: /help [command]\nExample: /help project",
        "sort_order": 71
    },
    {
        "category": "system",
        "command_name": "status",
        "language_code": "en",
        "pattern": r"^/status$",
        "aliases": ["st"],
        "description": "Show system status",
        "help_text": "Usage: /status\nDisplays current system and agent status.",
        "sort_order": 72
    },
    {
        "category": "system",
        "command_name": "shortcuts",
        "language_code": "en",
        "pattern": r"^/shortcuts$",
        "aliases": ["keys", "atalhos"],
        "description": "Show keyboard shortcuts",
        "help_text": "Usage: /shortcuts\nDisplays available keyboard shortcuts.",
        "sort_order": 73
    },
]


def run_migration(db_path: str):
    """Run the Phase 16 migration."""
    print(f"Running Phase 16 migration on: {db_path}")

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # =========================================================================
    # 1. Add KB/Memory configuration columns to project table
    # =========================================================================
    print("\n1. Adding KB/Memory configuration columns to project table...")
    cursor.execute("PRAGMA table_info(project)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    new_columns = [
        ("kb_chunk_size", "INTEGER DEFAULT 500"),
        ("kb_chunk_overlap", "INTEGER DEFAULT 50"),
        ("kb_embedding_model", "VARCHAR(100) DEFAULT 'all-MiniLM-L6-v2'"),
        ("enable_semantic_memory", "BOOLEAN DEFAULT 1"),
        ("semantic_memory_results", "INTEGER DEFAULT 10"),
        ("semantic_similarity_threshold", "REAL DEFAULT 0.5"),
        ("enable_factual_memory", "BOOLEAN DEFAULT 1"),
        ("factual_extraction_threshold", "INTEGER DEFAULT 5"),
    ]

    for col_name, col_def in new_columns:
        if col_name not in existing_columns:
            cursor.execute(f"ALTER TABLE project ADD COLUMN {col_name} {col_def}")
            print(f"  ✓ Added {col_name} column")
        else:
            print(f"  - {col_name} already exists")

    # =========================================================================
    # 2. Create project_semantic_memory table
    # =========================================================================
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='project_semantic_memory'
    """)
    if not cursor.fetchone():
        print("\n2. Creating project_semantic_memory table...")
        cursor.execute("""
            CREATE TABLE project_semantic_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                sender_key VARCHAR(100) NOT NULL,
                content TEXT NOT NULL,
                role VARCHAR(20) NOT NULL,
                embedding_id VARCHAR(100),
                metadata_json TEXT DEFAULT '{}',
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES project(id)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proj_semantic_project ON project_semantic_memory(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proj_semantic_sender ON project_semantic_memory(project_id, sender_key)")
        print("  ✓ Created project_semantic_memory table")
    else:
        print("\n2. project_semantic_memory table already exists")

    # =========================================================================
    # 3. Create project_fact_memory table
    # =========================================================================
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='project_fact_memory'
    """)
    if not cursor.fetchone():
        print("\n3. Creating project_fact_memory table...")
        cursor.execute("""
            CREATE TABLE project_fact_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                project_id INTEGER NOT NULL,
                sender_key VARCHAR(100),
                topic VARCHAR(100) NOT NULL,
                key VARCHAR(255) NOT NULL,
                value TEXT NOT NULL,
                confidence REAL DEFAULT 1.0,
                source VARCHAR(50) DEFAULT 'manual',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (project_id) REFERENCES project(id),
                UNIQUE (project_id, sender_key, topic, key)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proj_fact_project ON project_fact_memory(project_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proj_fact_topic ON project_fact_memory(project_id, topic)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_proj_fact_sender ON project_fact_memory(project_id, sender_key)")
        print("  ✓ Created project_fact_memory table")
    else:
        print("\n3. project_fact_memory table already exists")

    # =========================================================================
    # 4. Create slash_command table
    # =========================================================================
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='slash_command'
    """)
    if not cursor.fetchone():
        print("\n4. Creating slash_command table...")
        cursor.execute("""
            CREATE TABLE slash_command (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tenant_id VARCHAR(50) NOT NULL,
                category VARCHAR(30) NOT NULL,
                command_name VARCHAR(50) NOT NULL,
                language_code VARCHAR(10) DEFAULT 'en',
                pattern VARCHAR(300) NOT NULL,
                aliases TEXT DEFAULT '[]',
                description TEXT,
                help_text TEXT,
                permission_required VARCHAR(50),
                is_enabled BOOLEAN DEFAULT 1,
                handler_type VARCHAR(30) DEFAULT 'built-in',
                handler_config TEXT DEFAULT '{}',
                sort_order INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE (tenant_id, command_name, language_code)
            )
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_slash_cmd_tenant ON slash_command(tenant_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_slash_cmd_category ON slash_command(tenant_id, category)")
        print("  ✓ Created slash_command table")
    else:
        print("\n4. slash_command table already exists")

    # =========================================================================
    # 5. Seed default slash commands
    # =========================================================================
    print("\n5. Seeding default slash commands...")

    # Check if commands already exist for _system tenant
    cursor.execute("SELECT COUNT(*) FROM slash_command WHERE tenant_id = '_system'")
    existing_count = cursor.fetchone()[0]

    if existing_count == 0:
        import json
        for cmd in DEFAULT_SLASH_COMMANDS:
            cursor.execute("""
                INSERT INTO slash_command
                (tenant_id, category, command_name, language_code, pattern, aliases,
                 description, help_text, is_enabled, handler_type, sort_order)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 'built-in', ?)
            """, (
                "_system",
                cmd["category"],
                cmd["command_name"],
                cmd["language_code"],
                cmd["pattern"],
                json.dumps(cmd.get("aliases", [])),
                cmd.get("description", ""),
                cmd.get("help_text", ""),
                cmd.get("sort_order", 0)
            ))
        print(f"  ✓ Seeded {len(DEFAULT_SLASH_COMMANDS)} default slash commands")
    else:
        print(f"  - Default commands already exist ({existing_count} commands)")

    conn.commit()
    conn.close()
    print("\n✓ Phase 16 migration completed successfully!")


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
