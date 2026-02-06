import sqlite3

conn = sqlite3.connect('data/agent.db')
cursor = conn.cursor()
cursor.execute('SELECT id, event_type, status, scheduled_at FROM scheduled_events ORDER BY id DESC LIMIT 5')
print('\nRecent scheduled events:')
for row in cursor.fetchall():
    print(f'  ID={row[0]}, Type={row[1]}, Status={row[2]}, Scheduled={row[3]}')
conn.close()
