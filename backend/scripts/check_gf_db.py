
import sqlite3
import os

DB_PATH = "data/agent.db"

def check_db():
    if not os.path.exists(DB_PATH):
        print(f"Database not found at {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Check if table exists
    try:
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='google_flights_integration'")
        table = cursor.fetchone()
        if table:
            print("Table 'google_flights_integration' exists.")
        else:
            print("Table 'google_flights_integration' DOES NOT exist.")
    except Exception as e:
        print(f"Error checking table: {e}")

    # Check if integration exists
    try:
        cursor.execute("SELECT * FROM hub_integration WHERE type='google_flights'")
        rows = cursor.fetchall()
        print(f"Found {len(rows)} google_flights integrations.")
        for row in rows:
            print(row)
    except Exception as e:
        print(f"Error checking integrations: {e}")

    conn.close()

if __name__ == "__main__":
    check_db()
