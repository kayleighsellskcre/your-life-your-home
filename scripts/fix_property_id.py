"""Fix property_id data issue."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection

conn = get_connection()
cur = conn.cursor()

# Fix the property_id for the existing snapshot
cur.execute("UPDATE homeowner_snapshots SET property_id = 1 WHERE user_id = 1")

conn.commit()

# Verify
cur.execute("SELECT * FROM homeowner_snapshots")
snapshots = cur.fetchall()
print("Fixed snapshots:")
for snap in snapshots:
    print(f"  User {snap['user_id']} -> Property {snap['property_id']}")

conn.close()
print("✓ Fixed property_id data")
