"""Check the current database schema."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection

conn = get_connection()
cur = conn.cursor()

print("Checking homeowner_snapshots table...")
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='homeowner_snapshots'")
row = cur.fetchone()
if row:
    print(row['sql'])
else:
    print("Table not found")

print("\nChecking properties table...")
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='properties'")
row = cur.fetchone()
if row:
    print(row['sql'])
else:
    print("Table not found")

conn.close()
