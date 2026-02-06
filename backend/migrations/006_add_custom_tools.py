"""
Phase 6.1: Add Custom Tools tables
Migration script to add custom_tools, custom_tool_commands, custom_tool_parameters, and custom_tool_executions tables.
"""

import sys
import os
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_migration(db_path: str = "./data/agent.db"):
    """Run the migration to add custom tools tables."""

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        logger.info("Starting Phase 6.1 migration: Adding custom tools tables")

        # Create custom_tools table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS custom_tools (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) UNIQUE NOT NULL,
                tool_type VARCHAR(20) NOT NULL,
                system_prompt TEXT NOT NULL,
                workspace_dir VARCHAR(255),
                is_enabled BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """))
        logger.info("Created table: custom_tools")

        # Create custom_tool_commands table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS custom_tool_commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tool_id INTEGER NOT NULL,
                command_name VARCHAR(100) NOT NULL,
                command_template TEXT NOT NULL,
                is_long_running BOOLEAN DEFAULT 0,
                timeout_seconds INTEGER DEFAULT 30,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (tool_id) REFERENCES custom_tools(id) ON DELETE CASCADE
            )
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_custom_tool_commands_tool_id
            ON custom_tool_commands(tool_id)
        """))
        logger.info("Created table: custom_tool_commands")

        # Create custom_tool_parameters table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS custom_tool_parameters (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                command_id INTEGER NOT NULL,
                parameter_name VARCHAR(100) NOT NULL,
                is_mandatory BOOLEAN DEFAULT 0,
                default_value TEXT,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (command_id) REFERENCES custom_tool_commands(id) ON DELETE CASCADE
            )
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_custom_tool_parameters_command_id
            ON custom_tool_parameters(command_id)
        """))
        logger.info("Created table: custom_tool_parameters")

        # Create custom_tool_executions table
        session.execute(text("""
            CREATE TABLE IF NOT EXISTS custom_tool_executions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                agent_run_id INTEGER,
                tool_id INTEGER NOT NULL,
                command_id INTEGER NOT NULL,
                rendered_command TEXT NOT NULL,
                status VARCHAR(20) NOT NULL,
                output TEXT,
                error TEXT,
                execution_time_ms INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TIMESTAMP,
                FOREIGN KEY (agent_run_id) REFERENCES agent_run(id) ON DELETE SET NULL,
                FOREIGN KEY (tool_id) REFERENCES custom_tools(id) ON DELETE CASCADE,
                FOREIGN KEY (command_id) REFERENCES custom_tool_commands(id) ON DELETE CASCADE
            )
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_custom_tool_executions_agent_run_id
            ON custom_tool_executions(agent_run_id)
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_custom_tool_executions_tool_id
            ON custom_tool_executions(tool_id)
        """))
        session.execute(text("""
            CREATE INDEX IF NOT EXISTS idx_custom_tool_executions_command_id
            ON custom_tool_executions(command_id)
        """))
        logger.info("Created table: custom_tool_executions")

        session.commit()
        logger.info("Phase 6.1 migration completed successfully")

        # Verify tables
        result = session.execute(text("""
            SELECT name FROM sqlite_master
            WHERE type='table' AND name LIKE 'custom_%'
            ORDER BY name
        """))
        tables = [row[0] for row in result]
        logger.info(f"Verified tables: {tables}")

        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Migration failed: {e}", exc_info=True)
        return False

    finally:
        session.close()


def seed_nuclei_tool(db_path: str = "./data/agent.db"):
    """Seed the database with the Nuclei tool."""

    engine = create_engine(f"sqlite:///{db_path}")
    Session = sessionmaker(bind=engine)
    session = Session()

    try:
        logger.info("Seeding Nuclei tool")

        # Check if Nuclei tool already exists
        result = session.execute(text("SELECT id FROM custom_tools WHERE name = 'nuclei'"))
        if result.fetchone():
            logger.info("Nuclei tool already exists, skipping seed")
            return True

        # Insert Nuclei tool
        session.execute(text("""
            INSERT INTO custom_tools (name, tool_type, system_prompt, workspace_dir, is_enabled)
            VALUES (
                'nuclei',
                'command',
                'You are a security analyst assistant with access to the Nuclei vulnerability scanner. Nuclei is a fast, template-based vulnerability scanner that can detect security issues. You can scan URLs for vulnerabilities using pre-defined templates. When the user asks to scan a URL, use the ''scan_url'' command. Default test URL: http://testphp.vulnweb.com',
                './data/workspace/nuclei',
                1
            )
        """))

        # Get tool ID
        result = session.execute(text("SELECT id FROM custom_tools WHERE name = 'nuclei'"))
        tool_id = result.fetchone()[0]

        # Insert scan_url command
        session.execute(text("""
            INSERT INTO custom_tool_commands (tool_id, command_name, command_template, is_long_running, timeout_seconds)
            VALUES (
                :tool_id,
                'scan_url',
                'nuclei -u <url> -o <output_file> -silent',
                0,
                120
            )
        """), {"tool_id": tool_id})

        # Get command ID
        result = session.execute(text("SELECT id FROM custom_tool_commands WHERE tool_id = :tool_id"), {"tool_id": tool_id})
        command_id = result.fetchone()[0]

        # Insert parameters
        session.execute(text("""
            INSERT INTO custom_tool_parameters (command_id, parameter_name, is_mandatory, default_value, description)
            VALUES
                (:command_id, 'url', 1, 'http://testphp.vulnweb.com', 'Target URL to scan for vulnerabilities'),
                (:command_id, 'output_file', 0, 'nuclei_results.txt', 'Output file for scan results')
        """), {"command_id": command_id})

        session.commit()
        logger.info("Nuclei tool seeded successfully")

        return True

    except Exception as e:
        session.rollback()
        logger.error(f"Seeding failed: {e}", exc_info=True)
        return False

    finally:
        session.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Phase 6.1: Add Custom Tools tables")
    parser.add_argument("--db-path", default="./data/agent.db", help="Path to database")
    parser.add_argument("--skip-seed", action="store_true", help="Skip seeding Nuclei tool")
    args = parser.parse_args()

    # Run migration
    success = run_migration(args.db_path)

    if success and not args.skip_seed:
        # Seed Nuclei tool
        seed_nuclei_tool(args.db_path)

    sys.exit(0 if success else 1)
