#!/usr/bin/env python3
"""
Monitor a specific conversation flow in real-time
"""
import sqlite3
import json
import sys
import time
from datetime import datetime

def monitor_flow(flow_id: int, interval: int = 3):
    """Monitor a conversation flow"""
    db_path = 'backend/data/agent.db'

    print(f"Monitoring Flow {flow_id} (checking every {interval}s, Ctrl+C to stop)...\n")

    last_log_count = 0
    last_turn = 0
    last_status = None

    try:
        while True:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Get flow status
            cursor.execute('SELECT status, conversation_state FROM scheduled_events WHERE id = ?', (flow_id,))
            row = cursor.fetchone()

            if not row:
                print(f"Flow {flow_id} not found!")
                return

            status, state_json = row
            state = json.loads(state_json) if state_json else {}

            current_turn = state.get('current_turn', 0)
            objective_achieved = state.get('objective_progress', {}).get('achieved', False)

            # Get message count
            cursor.execute('SELECT COUNT(*) FROM conversation_logs WHERE scheduled_event_id = ?', (flow_id,))
            log_count = cursor.fetchone()[0]

            # Check for changes
            changed = False
            if status != last_status:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Status changed: {last_status} -> {status}")
                last_status = status
                changed = True

            if current_turn != last_turn:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Turn changed: {last_turn} -> {current_turn}")
                last_turn = current_turn
                changed = True

            if log_count != last_log_count:
                # Get new messages
                cursor.execute('''
                    SELECT message_direction, message_content, conversation_turn, message_timestamp
                    FROM conversation_logs
                    WHERE scheduled_event_id = ?
                    ORDER BY message_timestamp
                ''', (flow_id,))

                all_logs = cursor.fetchall()
                new_messages = all_logs[last_log_count:]

                for msg in new_messages:
                    direction, content, turn, timestamp = msg
                    preview = content[:100] + '...' if len(content) > 100 else content
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] Turn {turn} [{direction}]: {preview}")

                last_log_count = log_count
                changed = True

            if objective_achieved:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] OBJECTIVE ACHIEVED!")
                print(f"Final status: {status}")
                print(f"Total messages: {log_count}")
                break

            if status in ['COMPLETED', 'FAILED', 'CANCELLED']:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Flow ended with status: {status}")
                print(f"Total messages: {log_count}")
                break

            if not changed:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] No changes (Status: {status}, Turn: {current_turn}, Messages: {log_count})")

            conn.close()
            time.sleep(interval)

    except KeyboardInterrupt:
        print("\n\nMonitoring stopped by user")
        print(f"Final state: Status={status}, Turn={current_turn}, Messages={log_count}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python ops/monitor_flow.py <flow_id> [interval_seconds]")
        sys.exit(1)

    flow_id = int(sys.argv[1])
    interval = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    monitor_flow(flow_id, interval)
