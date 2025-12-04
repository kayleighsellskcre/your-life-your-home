"""
Migration script to add loan_term_years and loan_start_date columns to homeowner_snapshots table
"""
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "ylh.db"

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    # Check if columns already exist
    cur.execute("PRAGMA table_info(homeowner_snapshots)")
    columns = [row[1] for row in cur.fetchall()]
    
    # Add loan_term_years if it doesn't exist
    if 'loan_term_years' not in columns:
        print("Adding loan_term_years column...")
        cur.execute("ALTER TABLE homeowner_snapshots ADD COLUMN loan_term_years REAL")
        print("✓ loan_term_years column added")
    else:
        print("✓ loan_term_years column already exists")
    
    # Add loan_start_date if it doesn't exist
    if 'loan_start_date' not in columns:
        print("Adding loan_start_date column...")
        cur.execute("ALTER TABLE homeowner_snapshots ADD COLUMN loan_start_date TEXT")
        print("✓ loan_start_date column added")
    else:
        print("✓ loan_start_date column already exists")
    
    conn.commit()
    conn.close()
    print("\n✅ Migration completed successfully!")

if __name__ == "__main__":
    migrate()
