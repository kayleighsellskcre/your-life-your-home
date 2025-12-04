"""
Quick test to verify the equity overview setup
"""
import sys
sys.path.insert(0, '..')

from database import get_connection, upsert_homeowner_snapshot_full

def test_columns():
    conn = get_connection()
    cur = conn.cursor()
    
    # Check table schema
    cur.execute("PRAGMA table_info(homeowner_snapshots)")
    columns = {row[1]: row[2] for row in cur.fetchall()}
    
    print("Current homeowner_snapshots columns:")
    for col, dtype in columns.items():
        print(f"  - {col}: {dtype}")
    
    # Check if new columns exist
    has_term = 'loan_term_years' in columns
    has_start = 'loan_start_date' in columns
    
    print(f"\n✓ loan_term_years: {'EXISTS' if has_term else 'MISSING'}")
    print(f"✓ loan_start_date: {'EXISTS' if has_start else 'MISSING'}")
    
    if not has_term or not has_start:
        print("\nAdding missing columns...")
        if not has_term:
            cur.execute("ALTER TABLE homeowner_snapshots ADD COLUMN loan_term_years REAL")
        if not has_start:
            cur.execute("ALTER TABLE homeowner_snapshots ADD COLUMN loan_start_date TEXT")
        conn.commit()
        print("✅ Columns added!")
    
    conn.close()
    return has_term and has_start

if __name__ == "__main__":
    test_columns()
