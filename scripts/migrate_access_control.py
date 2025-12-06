"""
Migration: Add access control, subscriptions, client relationships, and invitations
"""
import sqlite3
import sys
from pathlib import Path

# Add parent directory to path so we can import config
sys.path.insert(0, str(Path(__file__).parent.parent))

def migrate():
    conn = sqlite3.connect("ylh.db")
    cur = conn.cursor()
    
    print("Creating access control tables...")
    
    # 1. Subscriptions table for agents and lenders
    cur.execute("""
        CREATE TABLE IF NOT EXISTS subscriptions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            subscription_type TEXT NOT NULL,  -- 'agent', 'lender', 'premium'
            status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'inactive', 'trial', 'cancelled'
            start_date TEXT NOT NULL,
            end_date TEXT,
            trial_ends_at TEXT,
            stripe_subscription_id TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    print("✓ Created subscriptions table")
    
    # 2. Client relationships (agent/lender -> homeowner)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS client_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            professional_id INTEGER NOT NULL,  -- agent or lender user_id
            professional_type TEXT NOT NULL,  -- 'agent' or 'lender'
            client_id INTEGER,  -- homeowner user_id (NULL if guest)
            client_email TEXT,  -- for guests who haven't signed up yet
            referral_code TEXT UNIQUE,  -- unique code for tracking
            status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'pending', 'inactive'
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (professional_id) REFERENCES users(id),
            FOREIGN KEY (client_id) REFERENCES users(id)
        )
    """)
    print("✓ Created client_relationships table")
    
    # 3. Transaction participants (all parties involved in a transaction)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transaction_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT NOT NULL,  -- unique transaction identifier
            user_id INTEGER,  -- NULL if not yet registered
            email TEXT,  -- for inviting people who aren't users yet
            role TEXT NOT NULL,  -- 'agent', 'lender', 'homeowner', 'other_agent', 'transaction_coordinator', 'title_company', 'custom'
            custom_role_name TEXT,  -- for custom roles
            permissions TEXT NOT NULL DEFAULT 'view',  -- 'view', 'edit', 'admin' (JSON array)
            invited_by INTEGER,  -- user_id of who invited them
            status TEXT NOT NULL DEFAULT 'active',  -- 'active', 'pending', 'declined'
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (invited_by) REFERENCES users(id)
        )
    """)
    print("✓ Created transaction_participants table")
    
    # 4. Invitations table for pending invites
    cur.execute("""
        CREATE TABLE IF NOT EXISTS invitations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id TEXT,  -- NULL for general client invites
            invited_by INTEGER NOT NULL,  -- user_id of inviter
            invited_email TEXT NOT NULL,
            invited_role TEXT NOT NULL,  -- 'agent', 'lender', 'homeowner', etc.
            custom_role_name TEXT,
            invite_code TEXT UNIQUE NOT NULL,  -- unique code for accepting invite
            permissions TEXT DEFAULT 'view',
            message TEXT,  -- optional message from inviter
            status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'accepted', 'declined', 'expired'
            expires_at TEXT,
            accepted_at TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (invited_by) REFERENCES users(id)
        )
    """)
    print("✓ Created invitations table")
    
    # 5. Guest sessions table for homeowners using without account
    cur.execute("""
        CREATE TABLE IF NOT EXISTS guest_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT UNIQUE NOT NULL,
            referral_code TEXT,  -- if they came from agent/lender link
            data TEXT,  -- JSON blob of their progress
            email TEXT,  -- if they provide email before signup
            last_activity TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✓ Created guest_sessions table")
    
    # 6. Add subscription-related columns to users table if they don't exist
    try:
        cur.execute("ALTER TABLE users ADD COLUMN referral_code TEXT UNIQUE")
        print("✓ Added referral_code to users table")
    except sqlite3.OperationalError:
        print("  (referral_code column already exists)")
    
    try:
        cur.execute("ALTER TABLE users ADD COLUMN has_active_subscription INTEGER DEFAULT 0")
        print("✓ Added has_active_subscription to users table")
    except sqlite3.OperationalError:
        print("  (has_active_subscription column already exists)")
    
    # 7. Create indexes for performance
    cur.execute("CREATE INDEX IF NOT EXISTS idx_client_relationships_professional ON client_relationships(professional_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_client_relationships_client ON client_relationships(client_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_client_relationships_code ON client_relationships(referral_code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_transaction_participants_transaction ON transaction_participants(transaction_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_transaction_participants_user ON transaction_participants(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_invitations_code ON invitations(invite_code)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_invitations_email ON invitations(invited_email)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id)")
    print("✓ Created indexes")
    
    conn.commit()
    conn.close()
    
    print("\n✅ Migration completed successfully!")
    print("\nNew tables created:")
    print("  • subscriptions - Track agent/lender subscriptions")
    print("  • client_relationships - Link professionals to homeowner clients")
    print("  • transaction_participants - All parties in a transaction")
    print("  • invitations - Pending invites to join platform/transactions")
    print("  • guest_sessions - Guest homeowner data before signup")

if __name__ == "__main__":
    migrate()
