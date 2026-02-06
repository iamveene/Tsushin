import sqlite3

conn = sqlite3.connect(r'D:\code\whatsapp-mcp\whatsapp-bridge\store\messages.db')
cursor = conn.cursor()

# Get chats table schema
cursor.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='chats'")
print('Chats table schema:', cursor.fetchone())

# Get distinct group names
cursor.execute("""
    SELECT DISTINCT c.name, c.jid
    FROM chats c
    WHERE c.jid LIKE '%@g.us'
    ORDER BY c.jid DESC
    LIMIT 10
""")
print('\nGroup chats:')
for row in cursor.fetchall():
    print(f"  Name: '{row[0]}' - JID: {row[1]}")

# Get recent messages with chat info
cursor.execute("""
    SELECT c.name, m.content, m.timestamp
    FROM messages m
    JOIN chats c ON m.chat_jid = c.jid
    WHERE c.jid LIKE '%@g.us'
    ORDER BY m.timestamp DESC
    LIMIT 5
""")
print('\nRecent group messages:')
for row in cursor.fetchall():
    content = row[1] if row[1] else '[media]'
    print(f"  Chat: '{row[0]}' - Message: {content[:50]}... ({row[2]})")

conn.close()
