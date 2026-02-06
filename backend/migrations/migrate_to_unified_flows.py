"""
Database Migration: Unified Flow Architecture
Phase 8.0: Merge ScheduledEvent with FlowDefinition/FlowNode system

Creates/Modifies:
- Adds new columns to flow_definition table (execution_method, scheduled_at, etc.)
- Adds new columns to flow_node table (name, timeout, retry, conversation settings)
- Adds new columns to flow_run table (step tracking)
- Adds new columns to flow_node_run table (retry tracking)
- Creates conversation_thread table for multi-turn conversations
- Migrates data from scheduled_events to the new unified flow system

Run: python backend/migrations/migrate_to_unified_flows.py
"""

import sys
import os
import json
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
    backup_path = backup_dir / f"agent_backup_pre_unified_flows_{timestamp}.db"

    print(f"Creating backup: {backup_path}")

    import shutil
    shutil.copy2(db_path, backup_path)

    print(f"[OK] Backup created: {backup_path}")
    return backup_path


def check_prerequisites(conn):
    """Verify database state before migration."""
    cursor = conn.cursor()

    # Check if flow_definition table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='flow_definition'
    """)
    if not cursor.fetchone():
        print("[ERROR] flow_definition table not found. Database may need earlier migrations.")
        return False

    # Check if already migrated (check for execution_method column)
    cursor.execute("PRAGMA table_info(flow_definition)")
    columns = [row[1] for row in cursor.fetchall()]
    if 'execution_method' in columns:
        print("[WARN] execution_method column already exists in flow_definition. Migration may have been run.")
        return True  # Continue anyway to ensure all columns exist

    print("[OK] Prerequisites check passed")
    return True


def upgrade(conn):
    """Apply migration: Add unified flow architecture tables and columns."""
    cursor = conn.cursor()

    print("\n=== Upgrading Database to Unified Flow Architecture ===")

    # 1. Update flow_definition table with new columns
    print("\n--- Updating flow_definition table ---")

    new_columns = [
        ("execution_method", "VARCHAR(20) DEFAULT 'immediate'"),
        ("scheduled_at", "DATETIME"),
        ("recurrence_rule", "TEXT"),  # JSON
        ("default_agent_id", "INTEGER"),
        ("last_executed_at", "DATETIME"),
        ("next_execution_at", "DATETIME"),
        ("execution_count", "INTEGER DEFAULT 0"),
    ]

    for col_name, col_type in new_columns:
        try:
            cursor.execute(f"ALTER TABLE flow_definition ADD COLUMN {col_name} {col_type}")
            print(f"[OK] Added column {col_name} to flow_definition")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"[SKIP] Column {col_name} already exists in flow_definition")
            else:
                raise

    # Add indexes for flow_definition
    try:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_flow_execution_method
            ON flow_definition(execution_method)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_flow_next_execution
            ON flow_definition(next_execution_at)
        """)
        print("[OK] Added indexes to flow_definition")
    except Exception as e:
        print(f"[WARN] Could not create indexes: {e}")

    # 2. Update flow_node table with new columns
    print("\n--- Updating flow_node table ---")

    flow_node_columns = [
        ("name", "VARCHAR(200)"),
        ("step_description", "TEXT"),
        ("timeout_seconds", "INTEGER DEFAULT 300"),
        ("retry_on_failure", "BOOLEAN DEFAULT 0"),
        ("max_retries", "INTEGER DEFAULT 0"),
        ("retry_delay_seconds", "INTEGER DEFAULT 1"),
        ("condition", "TEXT"),  # JSON
        ("on_success", "VARCHAR(50)"),
        ("on_failure", "VARCHAR(50)"),
        ("allow_multi_turn", "BOOLEAN DEFAULT 0"),
        ("max_turns", "INTEGER DEFAULT 20"),
        ("conversation_objective", "TEXT"),
        ("agent_id", "INTEGER"),
        ("persona_id", "INTEGER"),
    ]

    for col_name, col_type in flow_node_columns:
        try:
            cursor.execute(f"ALTER TABLE flow_node ADD COLUMN {col_name} {col_type}")
            print(f"[OK] Added column {col_name} to flow_node")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"[SKIP] Column {col_name} already exists in flow_node")
            else:
                raise

    # 3. Update flow_run table with new columns
    print("\n--- Updating flow_run table ---")

    flow_run_columns = [
        ("tenant_id", "VARCHAR(50)"),
        ("trigger_type", "VARCHAR(20)"),
        ("triggered_by", "VARCHAR(100)"),
        ("total_steps", "INTEGER DEFAULT 0"),
        ("completed_steps", "INTEGER DEFAULT 0"),
        ("failed_steps", "INTEGER DEFAULT 0"),
    ]

    for col_name, col_type in flow_run_columns:
        try:
            cursor.execute(f"ALTER TABLE flow_run ADD COLUMN {col_name} {col_type}")
            print(f"[OK] Added column {col_name} to flow_run")
        except sqlite3.OperationalError as e:
            if "duplicate column" in str(e).lower():
                print(f"[SKIP] Column {col_name} already exists in flow_run")
            else:
                raise

    # Add indexes to flow_run
    try:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_flow_run_status
            ON flow_run(status)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_flow_run_tenant_status
            ON flow_run(tenant_id, status)
        """)
        print("[OK] Added indexes to flow_run")
    except Exception as e:
        print(f"[WARN] Could not create indexes: {e}")

    # 4. Update flow_node_run table with new columns
    print("\n--- Updating flow_node_run table ---")

    try:
        cursor.execute("ALTER TABLE flow_node_run ADD COLUMN retry_count INTEGER DEFAULT 0")
        print("[OK] Added column retry_count to flow_node_run")
    except sqlite3.OperationalError as e:
        if "duplicate column" in str(e).lower():
            print("[SKIP] Column retry_count already exists in flow_node_run")
        else:
            raise

    # Add index to flow_node_run
    try:
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_step_run_status
            ON flow_node_run(status)
        """)
        print("[OK] Added index to flow_node_run")
    except Exception as e:
        print(f"[WARN] Could not create index: {e}")

    # 5. Create conversation_thread table
    print("\n--- Creating conversation_thread table ---")

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conversation_thread (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            flow_step_run_id INTEGER NOT NULL,

            status VARCHAR(20) DEFAULT 'active',
            current_turn INTEGER DEFAULT 0,
            max_turns INTEGER DEFAULT 20,

            recipient VARCHAR(100) NOT NULL,
            agent_id INTEGER NOT NULL,
            persona_id INTEGER,

            objective TEXT,

            conversation_history TEXT DEFAULT '[]',
            context_data TEXT DEFAULT '{}',

            goal_achieved BOOLEAN DEFAULT 0,
            goal_summary TEXT,

            started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            last_activity_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            completed_at DATETIME,
            timeout_at DATETIME,

            FOREIGN KEY (flow_step_run_id) REFERENCES flow_node_run(id) ON DELETE CASCADE
        )
    """)
    print("[OK] Created conversation_thread table")

    # Add indexes to conversation_thread
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_thread_status
        ON conversation_thread(status)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_thread_recipient
        ON conversation_thread(recipient)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_thread_active
        ON conversation_thread(status, recipient)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_conversation_thread_step_run
        ON conversation_thread(flow_step_run_id)
    """)
    print("[OK] Added indexes to conversation_thread")

    conn.commit()
    print("\n[OK] Schema migration completed successfully")


def migrate_scheduled_events(conn):
    """Migrate data from scheduled_events to the unified flow system."""
    cursor = conn.cursor()

    print("\n=== Migrating ScheduledEvent Data ===")

    # Check if scheduled_events table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='scheduled_events'
    """)
    if not cursor.fetchone():
        print("[SKIP] No scheduled_events table found - nothing to migrate")
        return

    # Count events to migrate
    cursor.execute("SELECT COUNT(*) FROM scheduled_events WHERE status != 'CANCELLED'")
    total_events = cursor.fetchone()[0]

    if total_events == 0:
        print("[SKIP] No scheduled events to migrate")
        return

    print(f"Found {total_events} scheduled events to migrate")

    # Fetch all non-cancelled events
    cursor.execute("""
        SELECT id, tenant_id, creator_type, creator_id, event_type,
               scheduled_at, status, payload, recurrence_rule,
               conversation_state, created_at
        FROM scheduled_events
        WHERE status != 'CANCELLED'
    """)
    events = cursor.fetchall()

    migrated_count = 0

    for event in events:
        event_id, tenant_id, creator_type, creator_id, event_type, \
            scheduled_at, status, payload_json, recurrence_rule, \
            conversation_state, created_at = event

        try:
            payload = json.loads(payload_json) if payload_json else {}
        except json.JSONDecodeError:
            payload = {}

        # Determine flow type and step type based on event_type
        if event_type == 'CONVERSATION':
            flow_type = 'conversation'
            step_type = 'conversation'
        elif event_type == 'NOTIFICATION':
            flow_type = 'notification'
            step_type = 'notification'
        elif event_type == 'MESSAGE':
            flow_type = 'workflow'
            step_type = 'message'
        else:
            flow_type = 'task'
            step_type = 'tool'

        # Determine execution method
        if recurrence_rule:
            execution_method = 'recurring'
        elif scheduled_at:
            execution_method = 'scheduled'
        else:
            execution_method = 'immediate'

        # Create flow_definition
        flow_name = f"Migrated {event_type} #{event_id}"
        flow_description = payload.get('objective') or payload.get('reminder_text') or f"Migrated from ScheduledEvent #{event_id}"

        cursor.execute("""
            INSERT INTO flow_definition (
                tenant_id, name, description, execution_method, scheduled_at,
                recurrence_rule, default_agent_id, flow_type, initiator_type,
                initiator_metadata, is_active, version, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            tenant_id,
            flow_name,
            flow_description,
            execution_method,
            scheduled_at,
            recurrence_rule,
            payload.get('agent_id'),
            flow_type,
            'programmatic' if creator_type == 'USER' else 'agentic',
            json.dumps({'migrated_from_event_id': event_id, 'original_creator_id': creator_id}),
            status in ('PENDING', 'ACTIVE'),
            created_at
        ))

        flow_id = cursor.lastrowid

        # Create flow_node (step)
        step_name = f"{event_type.title()} Step"

        # Build step config from payload
        step_config = {
            'recipient': payload.get('recipient'),
            'message_template': payload.get('reminder_text'),
            'objective': payload.get('objective'),
            'context': payload.get('context', {}),
        }

        cursor.execute("""
            INSERT INTO flow_node (
                flow_definition_id, name, type, position, config_json,
                allow_multi_turn, max_turns, conversation_objective,
                agent_id, persona_id, created_at
            ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?)
        """, (
            flow_id,
            step_name,
            step_type,
            json.dumps(step_config),
            event_type == 'CONVERSATION' and payload.get('max_turns', 1) > 1,
            payload.get('max_turns', 20),
            payload.get('objective'),
            payload.get('agent_id'),
            payload.get('persona_id'),
            created_at
        ))

        step_id = cursor.lastrowid

        # If event was ACTIVE/COMPLETED, create flow_run and flow_node_run
        if status in ('ACTIVE', 'COMPLETED', 'FAILED'):
            # Map status
            run_status_map = {
                'ACTIVE': 'running',
                'COMPLETED': 'completed',
                'FAILED': 'failed',
                'PAUSED': 'paused'
            }
            run_status = run_status_map.get(status, 'pending')

            cursor.execute("""
                INSERT INTO flow_run (
                    flow_definition_id, tenant_id, status, started_at,
                    initiator, trigger_type, total_steps, completed_steps,
                    trigger_context_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
            """, (
                flow_id,
                tenant_id,
                run_status,
                scheduled_at or created_at,
                creator_type.lower(),
                execution_method,
                1 if run_status == 'completed' else 0,
                json.dumps(payload),
                created_at
            ))

            run_id = cursor.lastrowid

            # Create flow_node_run
            cursor.execute("""
                INSERT INTO flow_node_run (
                    flow_run_id, flow_node_id, status, started_at,
                    input_json
                ) VALUES (?, ?, ?, ?, ?)
            """, (
                run_id,
                step_id,
                run_status,
                scheduled_at or created_at,
                json.dumps(payload)
            ))

            step_run_id = cursor.lastrowid

            # If there's conversation state, create conversation_thread
            if conversation_state and event_type == 'CONVERSATION':
                try:
                    conv_state = json.loads(conversation_state) if isinstance(conversation_state, str) else conversation_state
                except:
                    conv_state = {}

                cursor.execute("""
                    INSERT INTO conversation_thread (
                        flow_step_run_id, status, current_turn, max_turns,
                        recipient, agent_id, persona_id, objective,
                        conversation_history, context_data, goal_achieved,
                        started_at, last_activity_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    step_run_id,
                    'completed' if status == 'COMPLETED' else 'active',
                    conv_state.get('current_turn', 0),
                    payload.get('max_turns', 20),
                    payload.get('recipient'),
                    payload.get('agent_id'),
                    payload.get('persona_id'),
                    payload.get('objective'),
                    json.dumps(conv_state.get('conversation_history', [])),
                    json.dumps(conv_state.get('context_data', {})),
                    conv_state.get('goal_achieved', False),
                    scheduled_at or created_at,
                    datetime.utcnow().isoformat() + "Z"
                ))

        migrated_count += 1
        if migrated_count % 10 == 0:
            print(f"  Migrated {migrated_count}/{total_events} events...")

    conn.commit()
    print(f"\n[OK] Migrated {migrated_count} scheduled events to unified flow system")


def verify_migration(conn):
    """Verify migration was successful."""
    cursor = conn.cursor()

    print("\n=== Verifying Migration ===")

    # Check conversation_thread table exists
    cursor.execute("""
        SELECT name FROM sqlite_master
        WHERE type='table' AND name='conversation_thread'
    """)
    if not cursor.fetchone():
        raise Exception("conversation_thread table was not created")
    print("[OK] conversation_thread table exists")

    # Check flow_definition has new columns
    cursor.execute("PRAGMA table_info(flow_definition)")
    columns = {row[1] for row in cursor.fetchall()}
    required_cols = {'execution_method', 'scheduled_at', 'recurrence_rule', 'default_agent_id'}
    missing = required_cols - columns
    if missing:
        raise Exception(f"Missing columns in flow_definition: {missing}")
    print("[OK] flow_definition has all new columns")

    # Check flow_node has new columns
    cursor.execute("PRAGMA table_info(flow_node)")
    columns = {row[1] for row in cursor.fetchall()}
    required_cols = {'name', 'timeout_seconds', 'allow_multi_turn', 'max_turns'}
    missing = required_cols - columns
    if missing:
        raise Exception(f"Missing columns in flow_node: {missing}")
    print("[OK] flow_node has all new columns")

    # Check flow_run has new columns
    cursor.execute("PRAGMA table_info(flow_run)")
    columns = {row[1] for row in cursor.fetchall()}
    required_cols = {'total_steps', 'completed_steps', 'failed_steps'}
    missing = required_cols - columns
    if missing:
        raise Exception(f"Missing columns in flow_run: {missing}")
    print("[OK] flow_run has all new columns")

    # Count records
    for table in ['flow_definition', 'flow_node', 'flow_run', 'conversation_thread']:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f"[OK] Table {table}: {count} records")

    print("\n[OK] Verification completed successfully")


def main():
    """Run migration with safety checks."""
    import argparse

    parser = argparse.ArgumentParser(description="Unified Flow Architecture Migration")
    parser.add_argument("--verify-only", action="store_true", help="Only verify migration")
    parser.add_argument("--skip-data-migration", action="store_true", help="Skip migrating ScheduledEvent data")
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

        # Check prerequisites
        if not check_prerequisites(conn):
            sys.exit(1)

        # Create backup
        backup_path = backup_database(db_path)

        # Apply schema migration
        upgrade(conn)

        # Migrate data (unless skipped)
        if not args.skip_data_migration:
            migrate_scheduled_events(conn)

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
