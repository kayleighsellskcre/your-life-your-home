"""Verify the migrated data."""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection

conn = get_connection()
cur = conn.cursor()

print("=" * 60)
print("PROPERTIES DATA")
print("=" * 60)
cur.execute("SELECT * FROM properties")
properties = cur.fetchall()
if properties:
    for prop in properties:
        print(f"Property ID: {prop['id']}")
        print(f"  User ID: {prop['user_id']}")
        print(f"  Address: {prop['address']}")
        print(f"  Value: ${prop['estimated_value']:,.0f}" if prop['estimated_value'] else "  Value: Not set")
        print(f"  Type: {prop['property_type']}")
        print(f"  Primary: {'Yes' if prop['is_primary'] else 'No'}")
        print()
else:
    print("No properties found")

print("=" * 60)
print("HOMEOWNER SNAPSHOTS")
print("=" * 60)
cur.execute("SELECT * FROM homeowner_snapshots")
snapshots = cur.fetchall()
if snapshots:
    for snap in snapshots:
        print(f"Snapshot ID: {snap['id']}")
        print(f"  User ID: {snap['user_id']}")
        print(f"  Property ID: {snap['property_id']}")
        print(f"  Value: ${snap['value_estimate']:,.0f}" if snap['value_estimate'] else "  Value: Not set")
        print(f"  Loan Balance: ${snap['loan_balance']:,.0f}" if snap['loan_balance'] else "  Loan Balance: Not set")
        print(f"  Equity: ${snap['equity_estimate']:,.0f}" if snap['equity_estimate'] else "  Equity: Not set")
        print()
else:
    print("No snapshots found")

conn.close()
print("=" * 60)
