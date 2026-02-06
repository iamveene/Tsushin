"""
Database Migration: Add Browser Automation Skill (Phase 14.5)

Creates:
- browser_automation_integration table (polymorphic child of hub_integration)
- /browser slash command for manual browser control

Run: python backend/migrations/add_browser_automation_skill.py
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
    backup_path = backup_dir / f"agent_backup_pre_browser_automation_{timestamp}.db"

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

    # Check if hub_integration table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='hub_integration'
    """)
    if not cursor.fetchone():
        raise Exception("hub_integration table not found. Run core migrations first.")

    # Check if slash_command table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='slash_command'
    """)
    if not cursor.fetchone():
        raise Exception("slash_command table not found. Run core migrations first.")

    # Check if browser_automation_integration already exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='browser_automation_integration'
    """)
    if cursor.fetchone():
        print("[WARN] browser_automation_integration table already exists. Skipping table creation.")
        return "table_exists"

    print("[OK] Prerequisites check passed")
    return True


def upgrade(conn):
    """Apply migration: Create browser automation tables and slash command."""
    cursor = conn.cursor()

    print("\n=== Upgrading Database: Browser Automation Skill ===")

    # 1. Create browser_automation_integration table (polymorphic child of hub_integration)
    print("Creating browser_automation_integration table...")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS browser_automation_integration (
            id INTEGER PRIMARY KEY,

            -- Provider settings
            provider_type VARCHAR(50) DEFAULT 'playwright',
            mode VARCHAR(20) DEFAULT 'container',

            -- Browser configuration
            browser_type VARCHAR(20) DEFAULT 'chromium',
            headless INTEGER DEFAULT 1,
            timeout_seconds INTEGER DEFAULT 30,
            viewport_width INTEGER DEFAULT 1280,
            viewport_height INTEGER DEFAULT 720,
            max_concurrent_sessions INTEGER DEFAULT 3,
            user_agent TEXT,
            proxy_url TEXT,

            -- Host mode settings (Phase 8)
            allowed_user_keys_json TEXT,
            require_approval_per_action INTEGER DEFAULT 0,
            blocked_domains_json TEXT,

            FOREIGN KEY (id) REFERENCES hub_integration(id) ON DELETE CASCADE
        )
    """)

    print("[OK] browser_automation_integration table created")

    # 2. Create default system-wide integration
    print("Creating default browser automation integration...")

    # First, insert base hub_integration record
    cursor.execute("""
        SELECT id FROM hub_integration
        WHERE type = 'browser_automation' AND tenant_id = '_system'
    """)
    existing = cursor.fetchone()

    if not existing:
        cursor.execute("""
            INSERT INTO hub_integration (
                type, name, display_name, is_active, tenant_id, health_status
            ) VALUES (
                'browser_automation',
                'Browser Automation (Playwright)',
                'Browser Automation',
                1,
                '_system',
                'unknown'
            )
        """)
        integration_id = cursor.lastrowid

        # Insert browser_automation_integration child record
        cursor.execute("""
            INSERT INTO browser_automation_integration (
                id, provider_type, mode, browser_type, headless,
                timeout_seconds, viewport_width, viewport_height,
                max_concurrent_sessions
            ) VALUES (?, 'playwright', 'container', 'chromium', 1, 30, 1280, 720, 3)
        """, (integration_id,))

        print(f"[OK] Default integration created (ID: {integration_id})")
    else:
        print("[INFO] Default integration already exists, skipping")

    # 3. Add /browser slash command
    print("Adding /browser slash command...")

    # Check if command already exists
    cursor.execute("""
        SELECT id FROM slash_command
        WHERE command_name = 'browser'
    """)
    if cursor.fetchone():
        print("[INFO] /browser slash command already exists, skipping")
    else:
        # Insert /browser command (English)
        cursor.execute("""
            INSERT INTO slash_command (
                tenant_id, category, command_name, language_code, pattern,
                aliases, description, help_text, is_enabled, handler_type,
                handler_config, sort_order
            ) VALUES (
                '_system',
                'tool',
                'browser',
                'en',
                '^/browser\\s+(.+)$',
                '["browse", "web", "webpage"]',
                'Control a web browser with AI-powered automation',
                'Usage: /browser <instruction>

Examples:
  /browser go to google.com
  /browser navigate to example.com and take a screenshot
  /browser extract the page title from example.com
  /browser fill the search box with "test" on google.com

Actions:
  - navigate: Go to a URL
  - click: Click an element by selector
  - fill: Fill a form field
  - extract: Extract text content
  - screenshot: Capture a screenshot
  - execute: Run JavaScript

Note: Enable the Browser Automation skill for AI-assisted web automation.',
                1,
                'built-in',
                '{"skill_type": "browser_automation"}',
                60
            )
        """)

        # Insert /browser command (Portuguese)
        cursor.execute("""
            INSERT INTO slash_command (
                tenant_id, category, command_name, language_code, pattern,
                aliases, description, help_text, is_enabled, handler_type,
                handler_config, sort_order
            ) VALUES (
                '_system',
                'tool',
                'browser',
                'pt',
                '^/browser\\s+(.+)$',
                '["browse", "web", "pagina"]',
                'Controle um navegador web com automacao assistida por IA',
                'Uso: /browser <instrucao>

Exemplos:
  /browser va para google.com
  /browser navegue ate example.com e tire uma screenshot
  /browser extraia o titulo da pagina de example.com
  /browser preencha a caixa de busca com "teste" no google.com

Acoes:
  - navigate: Ir para uma URL
  - click: Clicar em um elemento por seletor
  - fill: Preencher um campo de formulario
  - extract: Extrair conteudo de texto
  - screenshot: Capturar uma screenshot
  - execute: Executar JavaScript

Nota: Habilite a skill Browser Automation para automacao web assistida por IA.',
                1,
                'built-in',
                '{"skill_type": "browser_automation"}',
                60
            )
        """)

        print("[OK] /browser slash command added (en, pt)")

    conn.commit()
    print("\n[OK] Migration completed successfully")


def verify_migration(conn):
    """Verify migration was successful."""
    cursor = conn.cursor()

    print("\n=== Verifying Migration ===")

    # Check table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='browser_automation_integration'
    """)
    if not cursor.fetchone():
        raise Exception("browser_automation_integration table was not created")
    print("[OK] Table browser_automation_integration exists")

    # Check default integration exists
    cursor.execute("""
        SELECT hi.id, hi.name, bai.provider_type, bai.mode
        FROM hub_integration hi
        JOIN browser_automation_integration bai ON hi.id = bai.id
        WHERE hi.type = 'browser_automation' AND hi.tenant_id = '_system'
    """)
    row = cursor.fetchone()
    if row:
        print(f"[OK] Default integration: ID={row[0]}, name={row[1]}, provider={row[2]}, mode={row[3]}")
    else:
        print("[WARN] Default integration not found")

    # Check slash command exists
    cursor.execute("""
        SELECT id, command_name, language_code
        FROM slash_command
        WHERE command_name = 'browser'
    """)
    commands = cursor.fetchall()
    if commands:
        for cmd in commands:
            print(f"[OK] Slash command: ID={cmd[0]}, name={cmd[1]}, lang={cmd[2]}")
    else:
        print("[WARN] /browser slash command not found")

    print("\n[OK] Verification completed successfully")


def downgrade(conn):
    """
    Rollback migration: Remove browser automation tables and slash command.
    """
    cursor = conn.cursor()

    print("\n=== Rolling Back Migration ===")

    # Safety check
    try:
        cursor.execute("""
            SELECT COUNT(*) FROM browser_automation_integration
        """)
        count = cursor.fetchone()[0]

        if count > 0:
            confirm = input(f"[WARN] {count} browser automation integrations exist. This will delete all data. Continue? (yes/no): ")
            if confirm.lower() != 'yes':
                print("Rollback cancelled")
                return
    except sqlite3.OperationalError:
        pass  # Table doesn't exist

    # Drop browser_automation_integration table
    print("Dropping browser_automation_integration table...")
    cursor.execute("DROP TABLE IF EXISTS browser_automation_integration")

    # Remove hub_integration entries with type='browser_automation'
    print("Removing browser_automation entries from hub_integration...")
    try:
        cursor.execute("DELETE FROM hub_integration WHERE type = 'browser_automation'")
    except sqlite3.OperationalError:
        pass

    # Remove /browser slash command
    print("Removing /browser slash command...")
    cursor.execute("DELETE FROM slash_command WHERE command_name = 'browser'")

    conn.commit()
    print("\n[OK] Rollback completed successfully")


def main():
    """Run migration with safety checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Browser Automation Skill Migration (Phase 14.5)")
    parser.add_argument("--downgrade", action="store_true", help="Rollback migration")
    parser.add_argument("--verify-only", action="store_true", help="Only verify migration")
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

        if args.downgrade:
            downgrade(conn)
        else:
            # Check prerequisites
            result = check_prerequisites(conn)
            if result == "table_exists":
                # Table exists but we should still check slash command
                upgrade(conn)
            elif result:
                # Create backup
                backup_path = backup_database(db_path)

                # Apply migration
                upgrade(conn)

                # Verify
                verify_migration(conn)

                print(f"\n[SUCCESS] Migration completed successfully!")
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
