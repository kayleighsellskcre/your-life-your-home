"""
Migration script to convert existing homeowner_snapshots to use the new properties system.

This script:
1. Finds all existing snapshots without a property_id
2. Creates a default property for each user
3. Links the snapshot to the new property
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection, add_property

def migrate_snapshots_to_properties():
    """Migrate existing snapshots to use properties."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Find all snapshots without a property_id
    cur.execute("""
        SELECT id, user_id, value_estimate 
        FROM homeowner_snapshots 
        WHERE property_id IS NULL
    """)
    snapshots = cur.fetchall()
    
    print(f"Found {len(snapshots)} snapshots to migrate...")
    
    migrated = 0
    for snapshot in snapshots:
        snapshot_id = snapshot["id"]
        user_id = snapshot["user_id"]
        value_estimate = snapshot["value_estimate"]
        
        # Check if user already has a property
        cur.execute("SELECT id FROM properties WHERE user_id = ? AND is_primary = 1 LIMIT 1", (user_id,))
        existing_property = cur.fetchone()
        
        if existing_property:
            property_id = existing_property["id"]
            print(f"  User {user_id}: Using existing property {property_id}")
        else:
            # Create a default property for this user
            property_id = add_property(user_id, "My Home", value_estimate, "primary")
            print(f"  User {user_id}: Created new property {property_id}")
        
        # Link the snapshot to the property
        cur.execute("""
            UPDATE homeowner_snapshots 
            SET property_id = ? 
            WHERE id = ?
        """, (property_id, snapshot_id))
        
        migrated += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Migration complete! {migrated} snapshots migrated to properties system.")

if __name__ == "__main__":
    print("=" * 60)
    print("HOMEOWNER SNAPSHOTS TO PROPERTIES MIGRATION")
    print("=" * 60)
    print()
    
    migrate_snapshots_to_properties()
    
    print()
    print("=" * 60)
    print("Migration completed successfully!")
    print("=" * 60)
