import sqlite3

conn = sqlite3.connect(r'D:\code\whatsapp-mcp\whatsapp-bridge\store\messages.db')
cursor = conn.cursor()

# Get all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = cursor.fetchall()
print("Tables:", [t[0] for t in tables])

# Check if there's a contacts table
for table in tables:
    print(f"\n{table[0]} schema:")
    cursor.execute(f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table[0]}'")
    print(cursor.fetchone()[0])

# Check a sample message with sender info
print("\n\nSample message with sender:")
cursor.execute("""
    SELECT m.sender, c.name as sender_name
    FROM messages m
    LEFT JOIN chats c ON m.sender = c.jid
    WHERE m.chat_jid LIKE '%@g.us%'
    LIMIT 5
""")
for row in cursor.fetchall():
    print(f"  Sender: {row[0]}, Name: {row[1]}")

conn.close()
