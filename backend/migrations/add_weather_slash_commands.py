"""
Database Migration: Add Weather Slash Commands

Registers /weather slash commands for programmatic weather access:
- /weather <location>          - Get current weather
- /weather forecast <location> [days] - Get weather forecast

These commands use WeatherCommandService for direct execution (zero AI tokens).

Run: python backend/migrations/add_weather_slash_commands.py
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


def check_prerequisites(conn):
    """Verify database state before migration."""
    cursor = conn.cursor()

    # Check if slash_command table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='slash_command'
    """)
    if not cursor.fetchone():
        raise Exception("slash_command table not found.")

    # Check if weather command already exists
    cursor.execute("""
        SELECT id FROM slash_command
        WHERE command_name = 'weather'
    """)
    if cursor.fetchone():
        print("[INFO] Weather slash commands already exist. Skipping.")
        return False

    return True


def upgrade(conn):
    """Add weather slash commands to the database."""
    cursor = conn.cursor()

    print("\n=== Adding Weather Slash Commands ===")

    # /weather <location> - English (current weather)
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'weather',
            'en',
            '^/weather\\s+(?!forecast\\s)(.+)$',
            '["clima", "tempo"]',
            'Get current weather for a location',
            'Usage: /weather <location>\n\nExamples:\n  /weather London\n  /weather New York,US\n  /weather Sao Paulo,BR\n\nNote: Add country code for more accurate results.',
            1,
            'built-in',
            '{"skill_type": "weather"}',
            70
        )
    """)

    # /weather <location> - Portuguese
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'weather',
            'pt',
            '^/weather\\s+(?!forecast\\s)(.+)$',
            '["clima", "tempo"]',
            'Obter clima atual de uma localidade',
            'Uso: /weather <local>\n\nExemplos:\n  /weather Londres\n  /weather Nova York,US\n  /weather Sao Paulo,BR\n\nNota: Adicione codigo do pais para resultados mais precisos.',
            1,
            'built-in',
            '{"skill_type": "weather"}',
            70
        )
    """)

    # /weather forecast <location> [days] - English
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'weather forecast',
            'en',
            '^/weather\\s+forecast\\s+(.+?)(?:\\s+(\\d+))?$',
            '["previsao"]',
            'Get weather forecast for a location',
            'Usage: /weather forecast <location> [days]\n\nExamples:\n  /weather forecast London\n  /weather forecast Tokyo 5\n  /weather forecast Paris 3\n\nDays: 1-5 (default: 3)',
            1,
            'built-in',
            '{"skill_type": "weather"}',
            71
        )
    """)

    # /weather forecast <location> [days] - Portuguese
    cursor.execute("""
        INSERT INTO slash_command (
            tenant_id, category, command_name, language_code, pattern,
            aliases, description, help_text, is_enabled, handler_type,
            handler_config, sort_order
        ) VALUES (
            '_system',
            'tool',
            'weather forecast',
            'pt',
            '^/weather\\s+forecast\\s+(.+?)(?:\\s+(\\d+))?$',
            '["previsao", "previsao do tempo"]',
            'Obter previsao do tempo para uma localidade',
            'Uso: /weather forecast <local> [dias]\n\nExemplos:\n  /weather forecast Londres\n  /weather forecast Toquio 5\n  /weather forecast Paris 3\n\nDias: 1-5 (padrao: 3)',
            1,
            'built-in',
            '{"skill_type": "weather"}',
            71
        )
    """)

    conn.commit()
    print("[OK] Weather slash commands added (weather, weather forecast - en, pt)")


def downgrade(conn):
    """Remove weather slash commands."""
    cursor = conn.cursor()

    print("\n=== Removing Weather Slash Commands ===")

    cursor.execute("""
        DELETE FROM slash_command
        WHERE command_name IN ('weather', 'weather forecast')
    """)

    conn.commit()
    print("[OK] Weather slash commands removed")


def main():
    """Run migration."""
    import argparse

    parser = argparse.ArgumentParser(description="Add Weather Slash Commands Migration")
    parser.add_argument("--downgrade", action="store_true", help="Remove the commands")
    parser.add_argument("--db-path", help="Database path")
    args = parser.parse_args()

    db_path = args.db_path or get_database_path()

    if not os.path.exists(db_path):
        print(f"[ERROR] Database not found: {db_path}")
        sys.exit(1)

    print(f"Using database: {db_path}")

    conn = sqlite3.connect(db_path)

    try:
        if args.downgrade:
            downgrade(conn)
        else:
            if check_prerequisites(conn):
                upgrade(conn)

        print("[SUCCESS] Migration completed!")

    except Exception as e:
        print(f"[ERROR] Migration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

    finally:
        conn.close()


if __name__ == "__main__":
    main()
