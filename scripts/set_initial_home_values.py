"""
Migration: Set initial_purchase_value for existing homeowner snapshots.
This allows the automatic appreciation formula to work correctly.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import get_connection

def set_initial_values():
    """
    Set initial_purchase_value to current value_estimate for all existing records.
    This creates a baseline for future appreciation calculations.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all snapshots that have a value but no initial value set
    cur.execute("""
        SELECT id, user_id, value_estimate, initial_purchase_value
        FROM homeowner_snapshots
        WHERE value_estimate IS NOT NULL
    """)
    
    snapshots = cur.fetchall()
    updated_count = 0
    
    for snap in snapshots:
        snap_id = snap['id']
        current_value = snap['value_estimate']
        initial_value = snap['initial_purchase_value']
        
        # Only set if not already set
        if initial_value is None and current_value:
            cur.execute("""
                UPDATE homeowner_snapshots
                SET initial_purchase_value = ?
                WHERE id = ?
            """, (current_value, snap_id))
            updated_count += 1
            print(f"✓ Set initial value for snapshot {snap_id}: ${current_value:,.0f}")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ Migration complete!")
    print(f"   Updated {updated_count} record(s)")
    print(f"   Total snapshots: {len(snapshots)}")
    print(f"\nℹ️  Future home values will now appreciate at 3.5% annually")
    print(f"   based on the time elapsed since loan_start_date")

if __name__ == "__main__":
    print("=" * 60)
    print("Setting Initial Home Values for Appreciation")
    print("=" * 60)
    print()
    
    set_initial_values()
