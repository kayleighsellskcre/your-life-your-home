"""
Database migration script for AI Transaction Coordinator
Creates comprehensive schema for transaction management with auto-progression
"""

import sqlite3
from datetime import datetime

def migrate_transaction_system():
    conn = sqlite3.connect('ylh.db')
    cursor = conn.cursor()
    
    print("🚀 Creating AI Transaction Coordinator Schema...")
    
    # 1. TRANSACTIONS TABLE - Core transaction data
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            property_address TEXT NOT NULL,
            client_name TEXT NOT NULL,
            client_email TEXT,
            client_phone TEXT,
            side TEXT NOT NULL CHECK(side IN ('buyer', 'seller', 'both')),
            current_stage TEXT NOT NULL DEFAULT 'pre_contract' 
                CHECK(current_stage IN ('pre_contract', 'under_contract', 'in_escrow', 'clear_to_close', 'closed', 'cancelled')),
            purchase_price REAL,
            target_close_date DATE,
            actual_close_date DATE,
            status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active', 'closed', 'cancelled')),
            notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES users(id)
        )
    """)
    print("✅ Created transactions table")
    
    # 2. TRANSACTION DOCUMENTS - Smart document tracking with auto-progression
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transaction_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            document_type TEXT NOT NULL,
            document_name TEXT NOT NULL,
            file_path TEXT NOT NULL,
            file_size INTEGER,
            uploaded_by INTEGER NOT NULL,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            triggers_stage_change TEXT,
            notes TEXT,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
            FOREIGN KEY (uploaded_by) REFERENCES users(id)
        )
    """)
    print("✅ Created transaction_documents table")
    
    # 3. TRANSACTION PARTICIPANTS - Multi-party collaboration
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transaction_participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            participant_type TEXT NOT NULL 
                CHECK(participant_type IN ('client', 'lender', 'title_company', 'inspector', 'appraiser', 'attorney', 'other')),
            user_id INTEGER,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            company TEXT,
            permissions TEXT NOT NULL DEFAULT 'view_only' 
                CHECK(permissions IN ('view_only', 'upload_docs', 'full_access')),
            invitation_token TEXT UNIQUE,
            invitation_sent_at TIMESTAMP,
            invitation_accepted_at TIMESTAMP,
            status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'active', 'removed')),
            added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    print("✅ Created transaction_participants table")
    
    # 4. TRANSACTION TIMELINE - Activity log
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transaction_timeline (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            event_type TEXT NOT NULL 
                CHECK(event_type IN ('created', 'stage_changed', 'document_uploaded', 'participant_added', 'note_added', 'date_changed', 'closed', 'cancelled')),
            description TEXT NOT NULL,
            created_by INTEGER,
            metadata TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
            FOREIGN KEY (created_by) REFERENCES users(id)
        )
    """)
    print("✅ Created transaction_timeline table")
    
    # 5. DOCUMENT CHECKLISTS - Required docs per stage
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS document_checklists (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            stage TEXT NOT NULL,
            document_type TEXT NOT NULL,
            document_name TEXT NOT NULL,
            description TEXT,
            required BOOLEAN NOT NULL DEFAULT 0,
            triggers_stage_change TEXT,
            display_order INTEGER DEFAULT 0
        )
    """)
    print("✅ Created document_checklists table")
    
    # 6. TRANSACTION STAGE HISTORY - Track stage changes
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transaction_stage_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            from_stage TEXT,
            to_stage TEXT NOT NULL,
            changed_by INTEGER,
            auto_changed BOOLEAN DEFAULT 0,
            trigger_document_id INTEGER,
            changed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transaction_id) REFERENCES transactions(id) ON DELETE CASCADE,
            FOREIGN KEY (changed_by) REFERENCES users(id),
            FOREIGN KEY (trigger_document_id) REFERENCES transaction_documents(id)
        )
    """)
    print("✅ Created transaction_stage_history table")
    
    # Populate document checklists with smart auto-progression rules
    print("\n📋 Populating document checklists...")
    
    checklist_data = [
        # PRE-CONTRACT STAGE
        ('pre_contract', 'pre_approval_letter', 'Pre-Approval Letter', 'Buyer financing pre-approval', 0, None, 1),
        ('pre_contract', 'proof_of_funds', 'Proof of Funds', 'Bank statements or liquid assets', 0, None, 2),
        ('pre_contract', 'buyer_agency_agreement', 'Buyer Agency Agreement', 'Signed representation agreement', 0, None, 3),
        
        # UNDER CONTRACT STAGE
        ('under_contract', 'purchase_agreement', 'Purchase Agreement', 'Fully executed purchase contract', 1, 'under_contract', 1),
        ('under_contract', 'earnest_money_receipt', 'Earnest Money Receipt', 'Proof of deposit', 1, None, 2),
        ('under_contract', 'seller_disclosures', 'Seller Disclosures', 'Property condition disclosures', 1, None, 3),
        ('under_contract', 'hoa_documents', 'HOA Documents', 'CC&Rs, budget, meeting minutes', 0, None, 4),
        
        # IN ESCROW STAGE
        ('in_escrow', 'inspection_report', 'Home Inspection Report', 'Professional inspection findings', 1, None, 1),
        ('in_escrow', 'inspection_response', 'Inspection Response', 'Repair requests or acceptance', 1, None, 2),
        ('in_escrow', 'appraisal_report', 'Appraisal Report', 'Property valuation', 1, 'clear_to_close', 3),
        ('in_escrow', 'title_report', 'Title Report', 'Preliminary title report', 1, None, 4),
        ('in_escrow', 'loan_application', 'Loan Application', 'Submitted to lender', 1, None, 5),
        ('in_escrow', 'homeowners_insurance', 'Homeowners Insurance', 'Policy binder', 1, None, 6),
        
        # CLEAR TO CLOSE STAGE
        ('clear_to_close', 'final_walkthrough', 'Final Walkthrough', 'Property condition verification', 1, None, 1),
        ('clear_to_close', 'clear_to_close_letter', 'Clear to Close Letter', 'Lender approval', 1, None, 2),
        ('clear_to_close', 'closing_disclosure', 'Closing Disclosure', 'Final loan terms', 1, None, 3),
        ('clear_to_close', 'wire_instructions', 'Wire Instructions', 'Funds transfer details', 1, None, 4),
        ('clear_to_close', 'utilities_transfer', 'Utilities Transfer', 'Service change documentation', 0, None, 5),
        
        # CLOSED STAGE
        ('closed', 'recorded_deed', 'Recorded Deed', 'County-recorded ownership', 1, None, 1),
        ('closed', 'settlement_statement', 'Settlement Statement', 'Final HUD-1 or closing statement', 1, None, 2),
        ('closed', 'keys', 'Keys Delivered', 'Property access transferred', 1, None, 3),
    ]
    
    cursor.executemany("""
        INSERT INTO document_checklists 
        (stage, document_type, document_name, description, required, triggers_stage_change, display_order)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, checklist_data)
    
    print(f"✅ Inserted {len(checklist_data)} document checklist items")
    
    # Create indexes for performance
    print("\n⚡ Creating indexes...")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_agent ON transactions(agent_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_stage ON transactions(current_stage)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_documents_transaction ON transaction_documents(transaction_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_participants_transaction ON transaction_participants(transaction_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_timeline_transaction ON transaction_timeline(transaction_id)")
    print("✅ Created indexes")
    
    conn.commit()
    conn.close()
    
    print("\n🎉 Transaction Coordinator database schema created successfully!")
    print("\n📊 Schema Summary:")
    print("   • transactions - Core transaction data")
    print("   • transaction_documents - File uploads with auto-progression")
    print("   • transaction_participants - Multi-party collaboration")
    print("   • transaction_timeline - Activity history")
    print("   • document_checklists - Required docs per stage")
    print("   • transaction_stage_history - Stage change tracking")
    print("\n✨ Auto-progression rules configured:")
    print("   • Upload Purchase Agreement → Moves to 'Under Contract'")
    print("   • Upload Appraisal Report → Moves to 'Clear to Close'")

if __name__ == "__main__":
    migrate_transaction_system()
