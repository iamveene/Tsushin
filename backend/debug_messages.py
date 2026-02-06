"""
Debug script to query recent messages from Travels 2026 group
"""
import sqlite3
import sys

# MCP database path - corrected
mcp_db_path = "D:\\code\\whatsapp-mcp\\whatsapp-bridge\\store\\messages.db"

try:
    conn = sqlite3.connect(mcp_db_path)
    c = conn.cursor()

    print("\n" + "="*80)
    print("RECENT MESSAGES FROM 'Travels 2026' GROUP")
    print("="*80)

    # Query recent messages
    c.execute("""
        SELECT
            id,
            chat_name,
            sender_name,
            body,
            timestamp
        FROM messages
        WHERE chat_name LIKE '%Travels%'
        ORDER BY timestamp DESC
        LIMIT 30
    """)

    messages = c.fetchall()

    if not messages:
        print("[INFO] No messages found in Travels 2026 group")
    else:
        print(f"[INFO] Found {len(messages)} recent messages\n")

        for i, (msg_id, chat_name, sender_name, body, timestamp) in enumerate(messages, 1):
            print(f"\n--- Message {i} ---")
            print(f"ID: {msg_id}")
            print(f"Chat: {chat_name}")
            print(f"Sender: {sender_name}")
            print(f"Timestamp: {timestamp}")
            print(f"Body: {body[:200] if body else '(empty)'}...")  # First 200 chars

    conn.close()

except Exception as e:
    print(f"[ERROR] {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
