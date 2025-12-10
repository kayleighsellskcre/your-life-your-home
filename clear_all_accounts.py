"""
Script to clear all user accounts and related data from the database.
WARNING: This will delete ALL users, profiles, relationships, and associated data.
Use with caution!

Usage:
    python clear_all_accounts.py              # Interactive mode
    python clear_all_accounts.py --confirm    # Non-interactive mode
"""

import sqlite3
import sys
from pathlib import Path

# Database path
DB_PATH = Path(__file__).parent / "ylh.db"

def clear_all_accounts(confirm=False):
    """Delete all user accounts and related data."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    
    print("⚠️  WARNING: This will delete ALL user accounts and related data!")
    print("This includes:")
    print("  - All users (homeowners, agents, lenders)")
    print("  - All user profiles")
    print("  - All client relationships")
    print("  - All contacts/borrowers")
    print("  - All transactions/loans")
    print("  - All homeowner snapshots")
    print("  - All documents and notes")
    print()
    
    if not confirm:
        response = input("Type 'DELETE ALL' to confirm: ")
        if response != "DELETE ALL":
            print("❌ Cancelled. No data was deleted.")
            conn.close()
            return
    
    try:
        # Delete in order to respect foreign key constraints
        print("\n🗑️  Deleting data...")
        
        # Delete client relationships
        cur.execute("DELETE FROM client_relationships")
        print(f"  ✓ Deleted client relationships")
        
        # Delete CRM relationships
        cur.execute("DELETE FROM crm_relationships")
        print(f"  ✓ Deleted CRM relationships")
        
        # Delete CRM tasks
        cur.execute("DELETE FROM crm_tasks")
        print(f"  ✓ Deleted CRM tasks")
        
        # Delete CRM deals
        cur.execute("DELETE FROM crm_deals")
        print(f"  ✓ Deleted CRM deals")
        
        # Delete CRM interactions
        cur.execute("DELETE FROM crm_interactions")
        print(f"  ✓ Deleted CRM interactions")
        
        # Delete agent contacts
        cur.execute("DELETE FROM agent_contacts")
        print(f"  ✓ Deleted agent contacts")
        
        # Delete agent transactions
        cur.execute("DELETE FROM agent_transactions")
        print(f"  ✓ Deleted agent transactions")
        
        # Delete lender borrowers
        cur.execute("DELETE FROM lender_borrowers")
        print(f"  ✓ Deleted lender borrowers")
        
        # Delete lender loans
        cur.execute("DELETE FROM lender_loans")
        print(f"  ✓ Deleted lender loans")
        
        # Delete homeowner snapshots
        cur.execute("DELETE FROM homeowner_snapshots")
        print(f"  ✓ Deleted homeowner snapshots")
        
        # Delete homeowner notes
        cur.execute("DELETE FROM homeowner_notes")
        print(f"  ✓ Deleted homeowner notes")
        
        # Delete homeowner documents
        cur.execute("DELETE FROM homeowner_documents")
        print(f"  ✓ Deleted homeowner documents")
        
        # Delete homeowner projects
        cur.execute("DELETE FROM homeowner_projects")
        print(f"  ✓ Deleted homeowner projects")
        
        # Delete next move plans
        cur.execute("DELETE FROM next_move_plans")
        print(f"  ✓ Deleted next move plans")
        
        # Delete homeowner questions
        cur.execute("DELETE FROM homeowner_questions")
        print(f"  ✓ Deleted homeowner questions")
        
        # Delete user profiles (must be before users due to foreign key)
        cur.execute("DELETE FROM user_profiles")
        print(f"  ✓ Deleted user profiles")
        
        # Delete all users (this will cascade delete related data)
        cur.execute("DELETE FROM users")
        print(f"  ✓ Deleted all users")
        
        conn.commit()
        print("\n✅ Successfully deleted all accounts and related data!")
        print("   The database structure remains intact for new signups.")
        
    except Exception as e:
        conn.rollback()
        print(f"\n❌ Error: {e}")
        print("   Changes were rolled back. No data was deleted.")
    finally:
        conn.close()

if __name__ == "__main__":
    # Check for --confirm flag
    confirm = "--confirm" in sys.argv or "-y" in sys.argv
    clear_all_accounts(confirm=confirm)

