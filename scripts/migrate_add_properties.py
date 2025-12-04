"""
Add property_id column to homeowner_snapshots and migrate existing data.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection, add_property

def add_property_id_column():
    """Add property_id column to homeowner_snapshots."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if column exists
    cur.execute("PRAGMA table_info(homeowner_snapshots)")
    columns = [row['name'] for row in cur.fetchall()]
    
    if 'property_id' in columns:
        print("✓ property_id column already exists")
        conn.close()
        return True
    
    print("Adding property_id column to homeowner_snapshots...")
    
    # Add the column
    cur.execute("""
        ALTER TABLE homeowner_snapshots 
        ADD COLUMN property_id INTEGER 
        REFERENCES properties(id) ON DELETE CASCADE
    """)
    
    conn.commit()
    conn.close()
    print("✓ Column added successfully")
    return True

def migrate_existing_data():
    """Create default properties for users with snapshots and link them."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all users with snapshots but no property
    cur.execute("""
        SELECT DISTINCT user_id 
        FROM homeowner_snapshots 
        WHERE property_id IS NULL
    """)
    user_ids = [row['user_id'] for row in cur.fetchall()]
    
    print(f"\nMigrating {len(user_ids)} users to properties system...")
    
    for user_id in user_ids:
        # Get the snapshot data
        cur.execute("""
            SELECT value_estimate 
            FROM homeowner_snapshots 
            WHERE user_id = ? 
            LIMIT 1
        """, (user_id,))
        row = cur.fetchone()
        value_estimate = row['value_estimate'] if row else None
        
        # Check if user already has a property
        cur.execute("SELECT id FROM properties WHERE user_id = ? LIMIT 1", (user_id,))
        existing = cur.fetchone()
        
        if existing:
            property_id = existing['id']
            print(f"  User {user_id}: Using existing property {property_id}")
        else:
            # Create default property
            property_id = add_property(user_id, "My Home", value_estimate, "primary")
            print(f"  User {user_id}: Created property {property_id}")
        
        # Link snapshot to property
        cur.execute("""
            UPDATE homeowner_snapshots 
            SET property_id = ? 
            WHERE user_id = ? AND property_id IS NULL
        """, (property_id, user_id))
    
    conn.commit()
    conn.close()
    print(f"✓ Migration complete for {len(user_ids)} users")

def remove_unique_constraint():
    """Remove UNIQUE constraint from user_id to allow multiple snapshots per user."""
    conn = get_connection()
    cur = conn.cursor()
    
    print("\nUpdating table constraints...")
    
    # SQLite doesn't support dropping constraints directly, so we need to recreate the table
    # First, backup the data
    cur.execute("""
        CREATE TABLE homeowner_snapshots_backup AS 
        SELECT * FROM homeowner_snapshots
    """)
    
    # Drop the old table
    cur.execute("DROP TABLE homeowner_snapshots")
    
    # Recreate with new schema
    cur.execute("""
        CREATE TABLE homeowner_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            property_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            value_estimate REAL,
            equity_estimate REAL,
            loan_rate REAL,
            loan_payment REAL,
            loan_balance REAL,
            loan_term_years REAL,
            loan_start_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE,
            UNIQUE(user_id, property_id)
        )
    """)
    
    # Restore the data
    cur.execute("""
        INSERT INTO homeowner_snapshots 
        SELECT * FROM homeowner_snapshots_backup
    """)
    
    # Drop backup
    cur.execute("DROP TABLE homeowner_snapshots_backup")
    
    conn.commit()
    conn.close()
    print("✓ Table constraints updated")

if __name__ == "__main__":
    print("=" * 70)
    print("MIGRATING TO PROPERTIES SYSTEM")
    print("=" * 70)
    
    try:
        # Step 1: Add property_id column if needed
        add_property_id_column()
        
        # Step 2: Migrate existing data
        migrate_existing_data()
        
        # Step 3: Remove unique constraint on user_id
        remove_unique_constraint()
        
        print("\n" + "=" * 70)
        print("✅ MIGRATION COMPLETED SUCCESSFULLY!")
        print("=" * 70)
        print("\nYour application now supports multiple properties per user.")
        print("Existing data has been preserved and linked to default properties.")
        
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        print("\nMigration failed. Please check the error above.")
        import traceback
        traceback.print_exc()
