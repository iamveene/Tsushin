import sqlite3

conn = sqlite3.connect('data/agent.db')
cursor = conn.cursor()

cursor.execute('SELECT group_filters FROM config WHERE id = 1')
print('Configured groups:', cursor.fetchone()[0])

cursor.execute('SELECT chat_name, body, timestamp FROM message_cache ORDER BY seen_at DESC LIMIT 5')
print('\nRecent messages:')
for row in cursor.fetchall():
    print(f'  {row[0]}: {row[1][:50]}... ({row[2]})')

conn.close()
