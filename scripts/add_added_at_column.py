import sqlite3

DB_PATH = 'ylh.db'

if __name__ == '__main__':
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    try:
        cursor.execute("""
            ALTER TABLE transaction_participants ADD COLUMN added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
        """)
        print("✅ 'added_at' column added to transaction_participants table.")
    except sqlite3.OperationalError as e:
        if 'duplicate column name' in str(e):
            print("ℹ️  'added_at' column already exists.")
        else:
            print(f"❌ Error: {e}")
    finally:
        conn.commit()
        conn.close()
