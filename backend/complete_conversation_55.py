"""
Manually complete conversation #55 (for testing)
"""
import sqlite3
from datetime import datetime

db = sqlite3.connect('data/agent.db')
cursor = db.cursor()

# Update conversation status to COMPLETED
cursor.execute('''
    UPDATE scheduled_events
    SET status = 'COMPLETED',
        completed_at = ?
    WHERE id = 55
''', (datetime.utcnow(),))

db.commit()
print(f"✅ Conversation #55 marked as COMPLETED")

# Verify
cursor.execute('SELECT id, status, completed_at FROM scheduled_events WHERE id = 55')
result = cursor.fetchone()
print(f"Verification: ID={result[0]}, Status={result[1]}, Completed={result[2]}")

db.close()
