import sqlite3
import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime

# Use persistent storage path - Railway or local
# Railway: Use persistent volume path if available
# IMPORTANT: Railway's filesystem is ephemeral - database MUST be in a persistent volume
# Set RAILWAY_VOLUME_MOUNT_PATH environment variable in Railway to your volume mount path
volume_path = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
if volume_path:
    # Railway deployment with persistent volume
    DB_PATH = Path(volume_path) / "ylh.db"
    try:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        print(f"[DATABASE] Using Railway persistent volume: {DB_PATH}")
    except (PermissionError, OSError) as e:
        print(f"[DATABASE] WARNING: Cannot access volume path {volume_path}: {e}")
        # Fallback - but this will be wiped on redeploy!
        DB_PATH = Path(__file__).parent / "ylh.db"
        print(f"[DATABASE] WARNING: Using ephemeral path (will be lost on redeploy): {DB_PATH}")
elif os.environ.get("RAILWAY_ENVIRONMENT"):
    # Railway but no volume configured - use project dir (WILL BE WIPED ON REDEPLOY)
    DB_PATH = Path(__file__).parent / "ylh.db"
    print(f"[DATABASE] WARNING: Railway detected but no persistent volume configured!")
    print(f"[DATABASE] Database will be wiped on redeploy. Set RAILWAY_VOLUME_MOUNT_PATH environment variable.")
    print(f"[DATABASE] Using ephemeral path: {DB_PATH}")
else:
    # Local development
    DB_PATH = Path(__file__).parent / "ylh.db"
    print(f"[DATABASE] Using local storage: {DB_PATH}")


def get_connection() -> sqlite3.Connection:
    """
    Get a database connection with proper timeout and thread safety.
    SQLite timeout allows waiting for locks to be released (default 5 seconds).
    """
    conn = sqlite3.connect(DB_PATH, timeout=10.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    # Enable WAL mode for better concurrency
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except:
        pass  # WAL might not be available in all SQLite versions
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    # ---------------- USERS ----------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            name TEXT,
            email TEXT UNIQUE,
            password_hash TEXT,
            role TEXT CHECK(role IN ('homeowner','agent','lender')) NOT NULL,
            follow_up_days INTEGER DEFAULT 30
        )
        """
    )
    
    # Add follow_up_days column if it doesn't exist
    try:
        cur.execute("ALTER TABLE users ADD COLUMN follow_up_days INTEGER DEFAULT 30")
    except:
        pass
    
    # Add agent_id and lender_id columns for homeowner linking
    try:
        cur.execute("ALTER TABLE users ADD COLUMN agent_id INTEGER REFERENCES users(id)")
    except:
        pass
    try:
        cur.execute("ALTER TABLE users ADD COLUMN lender_id INTEGER REFERENCES users(id)")
    except:
        pass
    
    # Add subscription_tier column for premium features (free, basic, premium, pro)
    try:
        cur.execute("ALTER TABLE users ADD COLUMN subscription_tier TEXT DEFAULT 'free' CHECK(subscription_tier IN ('free','basic','premium','pro'))")
    except:
        pass

    # ------------- USER PROFILES -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS user_profiles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            role TEXT CHECK(role IN ('agent','lender')) NOT NULL,
            referral_code TEXT UNIQUE,
            professional_photo TEXT,
            brokerage_logo TEXT,
            team_name TEXT,
            brokerage_name TEXT,
            website_url TEXT,
            facebook_url TEXT,
            instagram_url TEXT,
            linkedin_url TEXT,
            twitter_url TEXT,
            youtube_url TEXT,
            phone TEXT,
            call_button_enabled INTEGER DEFAULT 1,
            schedule_button_enabled INTEGER DEFAULT 1,
            schedule_url TEXT,
            bio TEXT,
            specialties TEXT,
            years_experience INTEGER,
            languages TEXT,
            service_areas TEXT,
            nmls_number TEXT,
            license_number TEXT,
            company_address TEXT,
            company_city TEXT,
            company_state TEXT,
            company_zip TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # Add referral_code column if it doesn't exist
    try:
        # Check if column exists
        cur.execute("PRAGMA table_info(user_profiles)")
        columns = [row[1] for row in cur.fetchall()]
        if 'referral_code' not in columns:
            # Add column without UNIQUE constraint (SQLite limitation)
            cur.execute("ALTER TABLE user_profiles ADD COLUMN referral_code TEXT")
            # Create unique index for referral_code
            try:
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_referral_code ON user_profiles(referral_code) WHERE referral_code IS NOT NULL")
            except:
                pass  # Index might already exist
    except Exception as e:
        print(f"Warning: Could not add referral_code column: {e}")
        pass
    
    # Add application_url column if it doesn't exist (for lenders)
    try:
        cur.execute("ALTER TABLE user_profiles ADD COLUMN application_url TEXT")
    except:
        pass
    
    # Add homebot_widget_id column if it doesn't exist (for agents/lenders)
    try:
        cur.execute("ALTER TABLE user_profiles ADD COLUMN homebot_widget_id TEXT")
    except:
        pass
    
    # Add market rate columns if they don't exist (for lenders/agents to set rates)
    try:
        cur.execute("ALTER TABLE user_profiles ADD COLUMN va_rate_30yr REAL")
    except:
        pass
    try:
        cur.execute("ALTER TABLE user_profiles ADD COLUMN fha_rate_30yr REAL")
    except:
        pass
    try:
        cur.execute("ALTER TABLE user_profiles ADD COLUMN conventional_rate_30yr REAL")
    except:
        pass

    # ---------------- VIDEO STUDIO ----------------
    # Table for video projects
    cur.execute("""
        CREATE TABLE IF NOT EXISTS video_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            transaction_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            video_type TEXT NOT NULL,
            aspect_ratio TEXT NOT NULL,
            duration INTEGER NOT NULL,
            style_preset TEXT NOT NULL,
            headline TEXT,
            property_address TEXT,
            highlights TEXT,
            media_files TEXT,
            include_lender INTEGER DEFAULT 0,
            include_captions INTEGER DEFAULT 1,
            render_status TEXT DEFAULT 'draft',
            output_path TEXT,
            thumbnail_path TEXT,
            FOREIGN KEY (user_id) REFERENCES users (id),
            FOREIGN KEY (transaction_id) REFERENCES agent_transactions (id)
        )
    """)

    # ------------- CLIENT RELATIONSHIPS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS client_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            homeowner_id INTEGER NOT NULL,
            professional_id INTEGER NOT NULL,
            professional_role TEXT CHECK(professional_role IN ('agent','lender')) NOT NULL,
            referral_code TEXT,
            status TEXT DEFAULT 'active' CHECK(status IN ('active','inactive','removed')),
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (homeowner_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (professional_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(homeowner_id, professional_id, professional_role)
        )
        """
    )
    
    # Migration: Ensure homeowner_id column exists (for existing databases)
    try:
        cur.execute("ALTER TABLE client_relationships ADD COLUMN homeowner_id INTEGER")
        # If homeowner_id was missing, we need to handle existing data
        # For now, we'll just ensure the column exists
    except:
        pass  # Column already exists
    
    # Migration: Ensure status column exists
    try:
        cur.execute("ALTER TABLE client_relationships ADD COLUMN status TEXT DEFAULT 'active'")
    except:
        pass  # Column already exists

    # ------------- REFERRAL LINKS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS referral_links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT UNIQUE NOT NULL,
            agent_id INTEGER REFERENCES users(id),
            lender_id INTEGER REFERENCES users(id),
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            CHECK(agent_id IS NOT NULL OR lender_id IS NOT NULL)
        )
        """
    )
    
    # Create index on token for fast lookups
    try:
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_referral_links_token ON referral_links(token)")
    except:
        pass

    # ------------- TRUSTED VENDORS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS trusted_vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            contact_name TEXT,
            phone TEXT,
            email TEXT,
            website TEXT,
            address TEXT,
            notes TEXT,
            is_active INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # Create index for faster lookups
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trusted_vendors_agent_id ON trusted_vendors(agent_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_trusted_vendors_category ON trusted_vendors(category)")
    except:
        pass

    # ------------- TRANSACTION VENDOR LINKS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transaction_vendors (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            transaction_id INTEGER NOT NULL,
            vendor_id INTEGER NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (transaction_id) REFERENCES agent_transactions(id) ON DELETE CASCADE,
            FOREIGN KEY (vendor_id) REFERENCES trusted_vendors(id) ON DELETE CASCADE,
            UNIQUE(transaction_id, vendor_id)
        )
        """
    )

    # ------------- PROPERTIES -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            address TEXT NOT NULL,
            estimated_value REAL,
            property_type TEXT DEFAULT 'primary',
            is_primary INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ------------- HOMEOWNER SNAPSHOTS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_snapshots (
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
            last_value_refresh TEXT,
            value_refresh_source TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE,
            UNIQUE(user_id, property_id)
        )
        """
    )
    
    # Add refresh tracking columns if they don't exist (migration)
    try:
        cur.execute("ALTER TABLE homeowner_snapshots ADD COLUMN last_value_refresh TEXT")
    except:
        pass
    try:
        cur.execute("ALTER TABLE homeowner_snapshots ADD COLUMN value_refresh_source TEXT")
    except:
        pass
    
    # Add initial purchase value for appreciation calculation
    try:
        cur.execute("ALTER TABLE homeowner_snapshots ADD COLUMN initial_purchase_value REAL")
    except:
        pass
    
    # Add property tax, insurance, and PMI columns for accurate payment calculations
    try:
        cur.execute("ALTER TABLE homeowner_snapshots ADD COLUMN property_tax_monthly REAL")
    except:
        pass
    try:
        cur.execute("ALTER TABLE homeowner_snapshots ADD COLUMN homeowners_insurance_monthly REAL")
    except:
        pass
    try:
        cur.execute("ALTER TABLE homeowner_snapshots ADD COLUMN pmi_monthly REAL")
    except:
        pass

    # ------------- SNAPSHOT HISTORY (Monthly tracking) -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_snapshot_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            property_id INTEGER,
            snapshot_date TEXT DEFAULT CURRENT_TIMESTAMP,
            value_estimate REAL,
            equity_estimate REAL,
            loan_balance REAL,
            loan_rate REAL,
            loan_payment REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (property_id) REFERENCES properties(id) ON DELETE CASCADE
        )
        """
    )
    
    # Create index for faster history queries
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_snapshot_history_user_property ON homeowner_snapshot_history(user_id, property_id, snapshot_date)")
    except:
        pass

    # ------------- HOMEOWNER NOTES (DESIGN BOARDS) -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            project_name TEXT,          -- board name
            title TEXT,
            tags TEXT,
            details TEXT,
            links TEXT,
            photos TEXT,                -- JSON list of photo filenames
            files TEXT,                 -- JSON list of file filenames
            vision_statement TEXT,
            color_palette TEXT,         -- JSON list of hex colors
            board_template TEXT,        -- 'minimal', 'modern', 'cozy', 'bold'
            label_style TEXT,          -- 'none', 'subtle', 'bold'
            is_private INTEGER DEFAULT 0,
            shareable_link TEXT,
            product_sources TEXT,
            show_notes_panel INTEGER DEFAULT 1,
            fixtures TEXT               -- JSON list of fixture image filenames
        )
        """
    )
    
    # Migration: Add missing columns to homeowner_notes if they don't exist
    migration_columns = [
        ("links", "TEXT"),
        ("vision_statement", "TEXT"),
        ("color_palette", "TEXT"),
        ("board_template", "TEXT"),
        ("label_style", "TEXT"),
        ("is_private", "INTEGER DEFAULT 0"),
        ("shareable_link", "TEXT"),
        ("product_sources", "TEXT"),
        ("show_notes_panel", "INTEGER DEFAULT 1"),
        ("fixtures", "TEXT"),
    ]
    
    for col_name, col_type in migration_columns:
        try:
            cur.execute(f"ALTER TABLE homeowner_notes ADD COLUMN {col_name} {col_type}")
            print(f"[DB MIGRATION] Added column '{col_name}' to homeowner_notes")
        except Exception as e:
            # Column already exists, ignore
            pass

    # ------------- HOMEOWNER DOCUMENTS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            name TEXT,
            category TEXT,
            file_path TEXT,
            r2_key TEXT,
            r2_url TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # Migration: Add name column if it doesn't exist (for existing databases)
    try:
        cur.execute("ALTER TABLE homeowner_documents ADD COLUMN name TEXT")
        print("[DB MIGRATION] Added 'name' column to homeowner_documents")
    except:
        pass  # Column already exists
    
    # Migration: Ensure all required columns exist
    try:
        cur.execute("ALTER TABLE homeowner_documents ADD COLUMN r2_key TEXT")
    except:
        pass
    try:
        cur.execute("ALTER TABLE homeowner_documents ADD COLUMN r2_url TEXT")
    except:
        pass

    # ------------- HOMEOWNER WARRANTY LOG -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_warranty_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_name TEXT NOT NULL,
            category TEXT NOT NULL,
            purchase_date TEXT,
            warranty_start TEXT,
            warranty_expiry TEXT,
            warranty_provider TEXT,
            warranty_number TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # Create index for faster lookups
    try:
        cur.execute("CREATE INDEX IF NOT EXISTS idx_warranty_log_user_id ON homeowner_warranty_log(user_id)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_warranty_log_category ON homeowner_warranty_log(category)")
    except:
        pass

    # ------------- HOMEOWNER PROJECTS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            name TEXT,
            category TEXT,
            status TEXT,
            budget TEXT,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # Add category column if it doesn't exist (migration for existing databases)
    try:
        cur.execute("PRAGMA table_info(homeowner_projects)")
        columns = [row[1] for row in cur.fetchall()]
        if 'category' not in columns:
            cur.execute("ALTER TABLE homeowner_projects ADD COLUMN category TEXT")
    except Exception as e:
        print(f"Warning: Could not add category column to homeowner_projects: {e}")
        pass

    # ------------- NEXT MOVE PLAN -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS next_move_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            timeline TEXT,
            budget_range TEXT,
            location_preferences TEXT,
            property_type_preferences TEXT,
            must_haves TEXT,
            nice_to_haves TEXT,
            concerns TEXT,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ------------- HOMEOWNER QUESTIONS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            topic TEXT,
            question TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ------------- AGENT CONTACTS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_contacts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            name TEXT,
            email TEXT,
            phone TEXT,
            stage TEXT,
            best_contact TEXT,
            last_touch TEXT,
            birthday TEXT,
            home_anniversary TEXT,
            address TEXT,
            notes TEXT,
            tags TEXT,
            property_address TEXT,
            property_value REAL,
            equity_estimate REAL,
            auto_birthday INTEGER DEFAULT 1,
            auto_anniversary INTEGER DEFAULT 1,
            auto_seasonal INTEGER DEFAULT 1,
            auto_equity INTEGER DEFAULT 1,
            auto_holidays INTEGER DEFAULT 1,
            equity_frequency TEXT DEFAULT 'monthly',
            FOREIGN KEY (agent_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # Add new columns to existing table (migration)
    for col in ['birthday', 'home_anniversary', 'address', 'notes', 'tags', 
                'property_address', 'property_value', 'equity_estimate',
                'auto_birthday', 'auto_anniversary', 'auto_seasonal', 
                'auto_equity', 'auto_holidays', 'equity_frequency']:
        try:
            if col in ['auto_birthday', 'auto_anniversary', 'auto_seasonal', 
                      'auto_equity', 'auto_holidays']:
                cur.execute(f"ALTER TABLE agent_contacts ADD COLUMN {col} INTEGER DEFAULT 1")
            elif col == 'equity_frequency':
                cur.execute(f"ALTER TABLE agent_contacts ADD COLUMN {col} TEXT DEFAULT 'monthly'")
            elif col in ['property_value', 'equity_estimate']:
                cur.execute(f"ALTER TABLE agent_contacts ADD COLUMN {col} REAL")
            else:
                cur.execute(f"ALTER TABLE agent_contacts ADD COLUMN {col} TEXT")
        except:
            pass

    # ------------- LENDER BORROWERS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lender_borrowers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lender_user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            name TEXT,
            status TEXT,
            loan_type TEXT,
            target_payment TEXT,
            last_touch TEXT,
            email TEXT,
            phone TEXT,
            birthday TEXT,
            home_anniversary TEXT,
            address TEXT,
            notes TEXT,
            tags TEXT,
            property_address TEXT,
            loan_amount REAL,
            loan_rate REAL,
            auto_birthday INTEGER DEFAULT 1,
            auto_anniversary INTEGER DEFAULT 1,
            auto_seasonal INTEGER DEFAULT 1,
            auto_equity INTEGER DEFAULT 1,
            auto_holidays INTEGER DEFAULT 1,
            equity_frequency TEXT DEFAULT 'monthly',
            FOREIGN KEY (lender_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # Add new columns to existing table (migration)
    for col in ['email', 'phone', 'birthday', 'home_anniversary', 'address', 
                'notes', 'tags', 'property_address', 'loan_amount', 'loan_rate',
                'auto_birthday', 'auto_anniversary', 'auto_seasonal', 
                'auto_equity', 'auto_holidays', 'equity_frequency']:
        try:
            if col in ['auto_birthday', 'auto_anniversary', 'auto_seasonal', 
                      'auto_equity', 'auto_holidays']:
                cur.execute(f"ALTER TABLE lender_borrowers ADD COLUMN {col} INTEGER DEFAULT 1")
            elif col == 'equity_frequency':
                cur.execute(f"ALTER TABLE lender_borrowers ADD COLUMN {col} TEXT DEFAULT 'monthly'")
            elif col in ['loan_amount', 'loan_rate']:
                cur.execute(f"ALTER TABLE lender_borrowers ADD COLUMN {col} REAL")
            else:
                cur.execute(f"ALTER TABLE lender_borrowers ADD COLUMN {col} TEXT")
        except:
            pass

    # ------------- AGENT TRANSACTIONS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            property_address TEXT,
            client_name TEXT,
            side TEXT,
            stage TEXT,
            close_date TEXT,
            FOREIGN KEY (agent_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # Migrate transaction_participants table to new schema if needed
    try:
        cur.execute("PRAGMA table_info(transaction_participants)")
        columns = [col[1] for col in cur.fetchall()]
        
        # Add missing columns for new transaction system
        if 'participant_type' not in columns:
            cur.execute("ALTER TABLE transaction_participants ADD COLUMN participant_type TEXT")
            # Migrate existing 'role' to 'participant_type' if role exists
            if 'role' in columns:
                cur.execute("UPDATE transaction_participants SET participant_type = role WHERE participant_type IS NULL")
        
        if 'name' not in columns:
            cur.execute("ALTER TABLE transaction_participants ADD COLUMN name TEXT")
        
        if 'phone' not in columns:
            cur.execute("ALTER TABLE transaction_participants ADD COLUMN phone TEXT")
        
        if 'company' not in columns:
            cur.execute("ALTER TABLE transaction_participants ADD COLUMN company TEXT")
        
        if 'invitation_token' not in columns:
            cur.execute("ALTER TABLE transaction_participants ADD COLUMN invitation_token TEXT")
            # Add unique constraint separately if needed
            try:
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_invitation_token ON transaction_participants(invitation_token) WHERE invitation_token IS NOT NULL")
            except:
                pass
        
        if 'invitation_sent_at' not in columns:
            cur.execute("ALTER TABLE transaction_participants ADD COLUMN invitation_sent_at TIMESTAMP")
        
        if 'invitation_accepted_at' not in columns:
            cur.execute("ALTER TABLE transaction_participants ADD COLUMN invitation_accepted_at TIMESTAMP")
        
        # Update transaction_id to INTEGER if it's TEXT
        if 'transaction_id' in columns:
            cur.execute("SELECT typeof(transaction_id) FROM transaction_participants LIMIT 1")
            result = cur.fetchone()
            if result and result[0] == 'text':
                # SQLite doesn't support changing column type directly, so we'll handle it in queries
                pass
        
        # Ensure added_at exists
        if 'added_at' not in columns:
            cur.execute("ALTER TABLE transaction_participants ADD COLUMN added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP")
    except Exception as e:
        print(f"Note: Could not migrate transaction_participants table: {e}")
        pass

    # ------------- LENDER LOANS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS lender_loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lender_user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            borrower_name TEXT,
            status TEXT,
            loan_type TEXT,
            target_payment TEXT,
            stage TEXT,
            close_date TEXT,
            FOREIGN KEY (lender_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ------------- MESSAGE TEMPLATES -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS message_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER,
            role TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            label TEXT,
            category TEXT,
            channel TEXT,
            subject TEXT,
            body TEXT,
            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ------------- MARKETING TEMPLATES -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS marketing_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_user_id INTEGER,
            role TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            template_type TEXT,
            name TEXT,
            description TEXT,
            content TEXT,
            FOREIGN KEY (owner_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # ------------- CRM INTERACTION HISTORY -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_interactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER,
            contact_type TEXT CHECK(contact_type IN ('agent_contact', 'lender_borrower')),
            professional_user_id INTEGER,
            interaction_type TEXT,
            interaction_date TEXT DEFAULT CURRENT_TIMESTAMP,
            subject TEXT,
            notes TEXT,
            channel TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (professional_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # ------------- AUTOMATED EMAIL LOGS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS automated_email_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER,
            contact_type TEXT CHECK(contact_type IN ('agent_contact', 'lender_borrower')),
            professional_user_id INTEGER,
            email_type TEXT,
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            recipient_email TEXT,
            subject TEXT,
            status TEXT DEFAULT 'sent',
            error_message TEXT,
            FOREIGN KEY (professional_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # ------------- CRM TASKS / FOLLOW-UPS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER,
            contact_type TEXT CHECK(contact_type IN ('agent_contact', 'lender_borrower')),
            professional_user_id INTEGER,
            title TEXT NOT NULL,
            description TEXT,
            due_date TEXT,
            priority TEXT DEFAULT 'medium' CHECK(priority IN ('low', 'medium', 'high', 'urgent')),
            status TEXT DEFAULT 'pending' CHECK(status IN ('pending', 'in_progress', 'completed', 'cancelled')),
            reminder_date TEXT,
            completed_at TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (professional_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # ------------- CRM DEALS / TRANSACTIONS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_deals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id INTEGER,
            contact_type TEXT CHECK(contact_type IN ('agent_contact', 'lender_borrower')),
            professional_user_id INTEGER,
            deal_name TEXT NOT NULL,
            deal_type TEXT CHECK(deal_type IN ('sale', 'purchase', 'refinance', 'listing', 'other')),
            property_address TEXT,
            deal_value REAL,
            commission_rate REAL,
            expected_commission REAL,
            stage TEXT DEFAULT 'prospect' CHECK(stage IN ('prospect', 'qualified', 'offer', 'under_contract', 'closed', 'lost')),
            probability INTEGER DEFAULT 0 CHECK(probability >= 0 AND probability <= 100),
            expected_close_date TEXT,
            actual_close_date TEXT,
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (professional_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # ------------- CRM CONTACT RELATIONSHIPS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_relationships (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            contact_id_1 INTEGER NOT NULL,
            contact_id_2 INTEGER NOT NULL,
            contact_type TEXT CHECK(contact_type IN ('agent_contact', 'lender_borrower')),
            professional_user_id INTEGER,
            relationship_type TEXT CHECK(relationship_type IN ('spouse', 'referral_source', 'related_contact', 'business_partner', 'other')),
            notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (professional_user_id) REFERENCES users(id) ON DELETE CASCADE,
            UNIQUE(contact_id_1, contact_id_2, contact_type, professional_user_id)
        )
        """
    )
    
    # ------------- CRM SAVED VIEWS / FILTERS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS crm_saved_views (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            professional_user_id INTEGER,
            role TEXT CHECK(role IN ('agent', 'lender')),
            view_name TEXT NOT NULL,
            filters_json TEXT,
            is_default INTEGER DEFAULT 0,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (professional_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ------------- HOMEOWNER TIMELINE EVENTS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_timeline_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            event_date TEXT,
            title TEXT,
            category TEXT,
            cost TEXT,
            notes TEXT,
            files TEXT,     -- JSON list of uploaded file names
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ------------- SIMPLE NOTES -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS simple_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            content TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # ------------- FEATURE SPOTLIGHT CARD SETS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS spotlight_card_sets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_user_id INTEGER NOT NULL,
            transaction_id INTEGER,
            set_name TEXT NOT NULL,
            property_address TEXT,
            features_json TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (agent_user_id) REFERENCES users(id) ON DELETE CASCADE,
            FOREIGN KEY (transaction_id) REFERENCES agent_transactions(id) ON DELETE SET NULL
        )
        """
    )
    
    print("[DATABASE] ✓ All tables created/verified including spotlight_card_sets")

    conn.commit()
    conn.close()


# =========================
# USER MANAGEMENT
# =========================


def create_user(name: str, email: str, password_hash: str, role: str, agent_id: Optional[int] = None, lender_id: Optional[int] = None) -> int:
    """
    Create a new user account.
    For homeowners, at least one of agent_id or lender_id must be provided.
    Uses proper error handling to ensure connections are always closed.
    """
    # Validate homeowner requirements
    if role == 'homeowner' and not agent_id and not lender_id:
        raise ValueError("Homeowners must be linked to at least one agent or lender")
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        cur.execute(
            "INSERT INTO users (name, email, password_hash, role, agent_id, lender_id) VALUES (?, ?, ?, ?, ?, ?)",
            (name, email.lower().strip(), password_hash, role, agent_id, lender_id),
        )
        user_id = cur.lastrowid
        conn.commit()
        
        # Verify the user was actually created
        if not user_id:
            raise ValueError("Failed to create user account - no user ID returned")
        
        return user_id
    except sqlite3.OperationalError as e:
        # Re-raise operational errors (like database locked) so retry logic can handle them
        raise
    except Exception as e:
        # Rollback on any other error
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise
    finally:
        # Always close the connection
        if conn:
            try:
                conn.close()
            except:
                pass


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    """
    Get user by email address.
    Uses proper error handling to ensure connections are always closed.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM users WHERE email = ?",
            (email.lower().strip(),),
        )
        row = cur.fetchone()
        return row
    except Exception as e:
        # Re-raise exceptions so callers can handle retries
        raise
    finally:
        # Always close the connection
        if conn:
            try:
                conn.close()
            except:
                pass


def update_user_password(user_id: int, password_hash: str, name: str = None, role: str = None, agent_id: Optional[int] = None, lender_id: Optional[int] = None) -> bool:
    """
    Update a user's password hash and optionally name, role, agent_id, lender_id.
    Used to complete incomplete accounts that were created without passwords.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Build update query dynamically based on what's provided
        updates = ["password_hash = ?"]
        values = [password_hash]
        
        if name:
            updates.append("name = ?")
            values.append(name)
        
        if role:
            updates.append("role = ?")
            values.append(role)
        
        if agent_id is not None:
            updates.append("agent_id = ?")
            values.append(agent_id)
        
        if lender_id is not None:
            updates.append("lender_id = ?")
            values.append(lender_id)
        
        values.append(user_id)
        
        query = f"UPDATE users SET {', '.join(updates)} WHERE id = ?"
        cur.execute(query, tuple(values))
        
        conn.commit()
        return True
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


def find_incomplete_accounts() -> List[sqlite3.Row]:
    """
    Find all accounts that have an email but no password_hash.
    These are incomplete accounts that need to be cleaned up or completed.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM users WHERE email IS NOT NULL AND (password_hash IS NULL OR password_hash = '')"
        )
        rows = cur.fetchall()
        return rows
    except Exception as e:
        raise
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


def delete_incomplete_account(user_id: int) -> bool:
    """
    Delete an incomplete account (one without a password_hash).
    Use with caution - only for cleaning up truly incomplete accounts.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Verify it's actually incomplete before deleting
        cur.execute("SELECT password_hash FROM users WHERE id = ?", (user_id,))
        user = cur.fetchone()
        
        if user and (not user[0] or user[0] == ''):
            cur.execute("DELETE FROM users WHERE id = ?", (user_id,))
            conn.commit()
            return True
        else:
            return False  # Account has password, don't delete
    except Exception as e:
        if conn:
            try:
                conn.rollback()
            except:
                pass
        raise
    finally:
        if conn:
            try:
                conn.close()
            except:
                pass


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    """
    Get user by ID.
    Uses proper error handling to ensure connections are always closed.
    """
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        return row
    except Exception as e:
        # Re-raise exceptions so callers can handle them
        raise
    finally:
        # Always close the connection
        if conn:
            try:
                conn.close()
            except:
                pass


# =========================
# HOMEOWNER SNAPSHOT / VALUE
# =========================


def get_homeowner_snapshot_for_user(user_id: int) -> Optional[Dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT value_estimate,
               equity_estimate,
               loan_rate,
               loan_payment,
               loan_balance,
               loan_term_years,
               loan_start_date,
               last_value_refresh,
               value_refresh_source
        FROM homeowner_snapshots
        WHERE user_id = ?
        """,
        (user_id,),
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return None
    return dict(row)


def upsert_homeowner_snapshot(
    user_id: int,
    value_estimate: float,
    equity_estimate: float,
    loan_rate: float,
    loan_payment: float,
    loan_balance: float,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_snapshots (
            user_id, value_estimate, equity_estimate,
            loan_rate, loan_payment, loan_balance
        )
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            value_estimate = excluded.value_estimate,
            equity_estimate = excluded.equity_estimate,
            loan_rate = excluded.loan_rate,
            loan_payment = excluded.loan_payment,
            loan_balance = excluded.loan_balance,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, value_estimate, equity_estimate, loan_rate, loan_payment, loan_balance),
    )
    conn.commit()
    conn.close()


def upsert_homeowner_snapshot_full(
    user_id: int,
    value_estimate: Optional[float] = None,
    loan_balance: Optional[float] = None,
    loan_rate: Optional[float] = None,
    loan_payment: Optional[float] = None,
    loan_term_years: Optional[float] = None,
    loan_start_date: Optional[str] = None,
) -> None:
    """Update homeowner snapshot with optional fields, merging with existing data."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get existing data
    cur.execute("SELECT * FROM homeowner_snapshots WHERE user_id = ?", (user_id,))
    existing = cur.fetchone()
    
    if existing:
        existing = dict(existing)
        # Merge: use new value if provided, else keep existing
        merged_value = value_estimate if value_estimate is not None else existing.get("value_estimate")
        merged_loan_balance = loan_balance if loan_balance is not None else existing.get("loan_balance")
        merged_loan_rate = loan_rate if loan_rate is not None else existing.get("loan_rate")
        merged_loan_payment = loan_payment if loan_payment is not None else existing.get("loan_payment")
        merged_loan_term_years = loan_term_years if loan_term_years is not None else existing.get("loan_term_years")
        merged_loan_start_date = loan_start_date if loan_start_date is not None else existing.get("loan_start_date")
    else:
        merged_value = value_estimate
        merged_loan_balance = loan_balance
        merged_loan_rate = loan_rate
        merged_loan_payment = loan_payment
        merged_loan_term_years = loan_term_years
        merged_loan_start_date = loan_start_date
    
    # Calculate equity
    equity = None
    if merged_value is not None and merged_loan_balance is not None:
        equity = merged_value - merged_loan_balance
    
    # Upsert
    cur.execute(
        """
        INSERT INTO homeowner_snapshots (
            user_id, value_estimate, equity_estimate,
            loan_rate, loan_payment, loan_balance,
            loan_term_years, loan_start_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            value_estimate = excluded.value_estimate,
            equity_estimate = excluded.equity_estimate,
            loan_rate = excluded.loan_rate,
            loan_payment = excluded.loan_payment,
            loan_balance = excluded.loan_balance,
            loan_term_years = excluded.loan_term_years,
            loan_start_date = excluded.loan_start_date,
            updated_at = CURRENT_TIMESTAMP
        """,
        (user_id, merged_value, equity, merged_loan_rate, merged_loan_payment,
         merged_loan_balance, merged_loan_term_years, merged_loan_start_date),
    )
    conn.commit()
    conn.close()


# =========================
# HOMEOWNER NOTES / DESIGN BOARDS
# =========================


def add_homeowner_note(
    user_id: int,
    project_name: str = None,
    title: str = None,
    tags: str = None,
    details: str = None,
    links: str = None,
    photos: List[str] = None,
    files: List[str] = None,
    vision_statement: str = None,
    color_palette: List[str] = None,
    board_template: str = "minimal",
    label_style: str = "subtle",
    is_private: int = 0,
    shareable_link: str = None,
    product_sources: str = None,
    show_notes_panel: int = 1,
    fixtures: List[str] = None,
) -> int:
    """Add a homeowner note (design board). Returns the note ID."""
    if not user_id:
        raise ValueError("user_id is required")
    if not project_name:
        raise ValueError("project_name is required")
    
    conn = None
    try:
        conn = get_connection()
        if not conn:
            raise ValueError("Failed to get database connection")
        
        cur = conn.cursor()
        if not cur:
            raise ValueError("Failed to create database cursor")
        
        # Prepare JSON fields
        photos_json = json.dumps(photos or [])
        files_json = json.dumps(files or [])
        color_palette_json = json.dumps(color_palette or [])
        fixtures_json = json.dumps(fixtures or [])
        
        print(f"[DB] Inserting note: user_id={user_id}, project_name={project_name}")
        print(f"[DB] Connection: {conn}, Cursor: {cur}")
        
        # Verify table exists
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='homeowner_notes'")
        table_exists = cur.fetchone()
        if not table_exists:
            raise ValueError("homeowner_notes table does not exist! Run init_db() first.")
        print(f"[DB] Table 'homeowner_notes' exists: {table_exists}")
        
        # Build the insert statement
        insert_sql = """
            INSERT INTO homeowner_notes (
                user_id, project_name, title, tags, details, links,
                photos, files, vision_statement, color_palette,
                board_template, label_style, is_private, shareable_link,
                product_sources, show_notes_panel, fixtures
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        insert_values = (
            user_id,
            project_name,
            title,
            tags,
            details,
            links,
            photos_json,
            files_json,
            vision_statement,
            color_palette_json,
            board_template,
            label_style,
            is_private,
            shareable_link,
            product_sources,
            show_notes_panel,
            fixtures_json,
        )
        
        print(f"[DB] Executing INSERT with {len(insert_values)} values")
        print(f"[DB] Values: user_id={user_id}, project_name='{project_name}', title={title}")
        
        try:
            cur.execute(insert_sql, insert_values)
            note_id = cur.lastrowid
            print(f"[DB] Insert executed, lastrowid: {note_id}")
        except Exception as insert_error:
            print(f"[DB ERROR] Insert failed: {str(insert_error)}")
            import traceback
            print(traceback.format_exc())
            raise
        
        # Commit the transaction
        try:
            conn.commit()
            print(f"[DB] Transaction committed successfully")
        except Exception as commit_error:
            print(f"[DB ERROR] Commit failed: {str(commit_error)}")
            conn.rollback()
            raise
        
        if not note_id or note_id == 0:
            raise ValueError("INSERT succeeded but no ID was returned (lastrowid is None or 0)")
        
        print(f"[DB] Note inserted successfully with ID: {note_id}")
        
        # Verify the insert
        cur.execute("SELECT id, project_name, created_at FROM homeowner_notes WHERE id = ?", (note_id,))
        verify = cur.fetchone()
        if verify:
            print(f"[DB] Verified: Note {note_id} exists in database")
        else:
            print(f"[DB] WARNING: Note {note_id} was not found after insert!")
        
        return note_id
    except Exception as e:
        import traceback
        print(f"[DB ERROR] Failed to insert homeowner note: {str(e)}")
        print(traceback.format_exc())
        if conn:
            try:
                conn.rollback()
                print(f"[DB] Rolled back transaction")
            except:
                pass
        raise
    finally:
        if conn:
            try:
                conn.close()
                print(f"[DB] Connection closed")
            except:
                pass


def list_homeowner_notes(user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, project_name, title, tags, details, links,
               photos, files, vision_statement, color_palette,
               board_template, label_style, is_private, shareable_link,
               product_sources, show_notes_panel, fixtures
        FROM homeowner_notes
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def add_homeowner_document(
    user_id: int,
    name: str,
    category: str,
    file_path: str = None,
    r2_key: str = None,
    r2_url: str = None,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_documents (user_id, name, category, file_path, r2_key, r2_url)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, name, category, file_path, r2_key, r2_url),
    )
    doc_id = cur.lastrowid
    conn.commit()
    conn.close()
    return doc_id


# =========================
# WARRANTY LOG MANAGEMENT
# =========================

def add_warranty_log_item(
    user_id: int,
    item_name: str,
    category: str,
    purchase_date: Optional[str] = None,
    warranty_start: Optional[str] = None,
    warranty_expiry: Optional[str] = None,
    warranty_provider: Optional[str] = None,
    warranty_number: Optional[str] = None,
    notes: Optional[str] = None
) -> int:
    """Add a new warranty log item."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO homeowner_warranty_log 
           (user_id, item_name, category, purchase_date, warranty_start, warranty_expiry, 
            warranty_provider, warranty_number, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (user_id, item_name, category, purchase_date, warranty_start, warranty_expiry,
         warranty_provider, warranty_number, notes)
    )
    item_id = cur.lastrowid
    conn.commit()
    conn.close()
    return item_id


def list_warranty_log_items(user_id: int) -> List[sqlite3.Row]:
    """List all warranty log items for a user."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM homeowner_warranty_log 
           WHERE user_id = ? 
           ORDER BY warranty_expiry ASC NULLS LAST, created_at DESC""",
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_warranty_log_item(item_id: int, user_id: int) -> bool:
    """Delete a warranty log item (only if it belongs to the user)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """DELETE FROM homeowner_warranty_log 
           WHERE id = ? AND user_id = ?""",
        (item_id, user_id)
    )
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


def list_homeowner_documents(user_id: int) -> List[sqlite3.Row]:
    """List all documents for a homeowner. Handles schema migration if needed."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check what columns exist in the table
    try:
        cur.execute("PRAGMA table_info(homeowner_documents)")
        columns = [row[1] for row in cur.fetchall()]
        
        # Build SELECT statement based on available columns
        select_cols = []
        if 'id' in columns:
            select_cols.append('id')
        if 'created_at' in columns:
            select_cols.append('created_at')
        if 'name' in columns:
            select_cols.append('name')
        elif 'title' in columns:
            select_cols.append('title AS name')  # Use title as name if name doesn't exist
        elif 'file_name' in columns:
            select_cols.append('file_name AS name')  # Use file_name as name
        if 'category' in columns:
            select_cols.append('category')
        if 'file_path' in columns:
            select_cols.append('file_path')
        if 'r2_key' in columns:
            select_cols.append('r2_key')
        if 'r2_url' in columns:
            select_cols.append('r2_url')
        
        if not select_cols:
            # Fallback: select all columns
            cur.execute(
                """
                SELECT *
                FROM homeowner_documents
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
        else:
            select_sql = f"""
                SELECT {', '.join(select_cols)}
                FROM homeowner_documents
                WHERE user_id = ?
                ORDER BY created_at DESC
            """
            cur.execute(select_sql, (user_id,))
        
        rows = cur.fetchall()
        conn.close()
        return rows
    except Exception as e:
        print(f"[DB ERROR] Error listing homeowner documents: {str(e)}")
        import traceback
        print(traceback.format_exc())
        # Fallback: try selecting all columns
        try:
            cur.execute(
                """
                SELECT *
                FROM homeowner_documents
                WHERE user_id = ?
                ORDER BY created_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
            conn.close()
            return rows
        except:
            conn.close()
            return []


def add_homeowner_project(
    user_id: int,
    name: str,
    category: str,
    status: str,
    budget: str,
    notes: str,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_projects (user_id, name, category, status, budget, notes)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (user_id, name, category, status, budget, notes),
    )
    project_id = cur.lastrowid
    conn.commit()
    conn.close()
    return project_id


def list_homeowner_projects(user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, name, category, status, budget, notes
        FROM homeowner_projects
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_homeowner_project(project_id: int, user_id: int) -> Optional[sqlite3.Row]:
    """Get a single project by ID, ensuring it belongs to the user."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, name, category, status, budget, notes
        FROM homeowner_projects
        WHERE id = ? AND user_id = ?
        """,
        (project_id, user_id),
    )
    row = cur.fetchone()
    conn.close()
    return row


def update_homeowner_project(
    project_id: int,
    user_id: int,
    name: str = None,
    category: str = None,
    status: str = None,
    budget: str = None,
    notes: str = None,
) -> None:
    """Update a homeowner project. Only updates provided fields."""
    conn = get_connection()
    cur = conn.cursor()
    
    updates = []
    params = []
    
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if category is not None:
        updates.append("category = ?")
        params.append(category)
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if budget is not None:
        updates.append("budget = ?")
        params.append(budget)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    
    if not updates:
        conn.close()
        return
    
    params.append(project_id)
    params.append(user_id)
    
    cur.execute(
        f"""
        UPDATE homeowner_projects
        SET {', '.join(updates)}
        WHERE id = ? AND user_id = ?
        """,
        tuple(params),
    )
    conn.commit()
    conn.close()


def delete_homeowner_project(project_id: int, user_id: int) -> None:
    """Delete a homeowner project."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM homeowner_projects WHERE id = ? AND user_id = ?",
        (project_id, user_id),
    )
    conn.commit()
    conn.close()


def upsert_next_move_plan(
    user_id: int,
    timeline: str = None,
    budget_range: str = None,
    location_preferences: str = None,
    property_type_preferences: str = None,
    must_haves: str = None,
    nice_to_haves: str = None,
    concerns: str = None,
    notes: str = None,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO next_move_plans (
            user_id, timeline, budget_range, location_preferences,
            property_type_preferences, must_haves, nice_to_haves, concerns, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            timeline = excluded.timeline,
            budget_range = excluded.budget_range,
            location_preferences = excluded.location_preferences,
            property_type_preferences = excluded.property_type_preferences,
            must_haves = excluded.must_haves,
            nice_to_haves = excluded.nice_to_haves,
            concerns = excluded.concerns,
            notes = excluded.notes,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            timeline,
            budget_range,
            location_preferences,
            property_type_preferences,
            must_haves,
            nice_to_haves,
            concerns,
            notes,
        ),
    )
    conn.commit()
    conn.close()


def get_next_move_plan(user_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM next_move_plans WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def add_homeowner_question(
    user_id: Optional[int],
    topic: str,
    question: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_questions (user_id, topic, question)
        VALUES (?, ?, ?)
        """,
        (user_id, topic, question),
    )
    conn.commit()
    conn.close()


# =========================
# AGENT CRM / CONTACTS
# =========================


def add_agent_contact(
    agent_user_id: int,
    name: str,
    email: str = "",
    phone: str = "",
    stage: str = "new",
    best_contact: str = "",
    last_touch: str = "",
    birthday: str = "",
    home_anniversary: str = "",
    address: str = "",
    notes: str = "",
    tags: str = "",
    property_address: str = "",
    property_value: float = None,
    equity_estimate: float = None,
    auto_birthday: int = 1,
    auto_anniversary: int = 1,
    auto_seasonal: int = 1,
    auto_equity: int = 1,
    auto_holidays: int = 1,
    equity_frequency: str = "monthly",
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO agent_contacts (
            agent_user_id, name, email, phone, stage, best_contact, last_touch,
            birthday, home_anniversary, address, notes, tags, property_address,
            property_value, equity_estimate, auto_birthday, auto_anniversary,
            auto_seasonal, auto_equity, auto_holidays, equity_frequency
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (agent_user_id, name, email, phone, stage, best_contact, last_touch,
         birthday, home_anniversary, address, notes, tags, property_address,
         property_value, equity_estimate, auto_birthday, auto_anniversary,
         auto_seasonal, auto_equity, auto_holidays, equity_frequency),
    )
    contact_id = cur.lastrowid
    conn.commit()
    conn.close()
    return contact_id


def list_agent_contacts(agent_user_id: int, stage_filter: str = None) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    query = """
        SELECT id, created_at, name, email, phone, stage, best_contact, last_touch,
               birthday, home_anniversary, address, notes, tags, property_address,
               property_value, equity_estimate, auto_birthday, auto_anniversary,
               auto_seasonal, auto_equity, auto_holidays, equity_frequency
        FROM agent_contacts
        WHERE agent_user_id = ?
    """
    params = [agent_user_id]
    if stage_filter:
        query += " AND stage = ?"
        params.append(stage_filter)
    query += " ORDER BY created_at DESC"
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_contacts_needing_followup(agent_user_id: int, days_threshold: int = 30) -> List[sqlite3.Row]:
    """Get contacts that haven't been communicated with in X days"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Calculate the cutoff date (days_threshold days ago)
    from datetime import timedelta
    cutoff_date = datetime.now() - timedelta(days=days_threshold)
    cutoff_iso = cutoff_date.isoformat()
    
    # Get contacts where last interaction or last_touch is older than threshold
    query = """
        SELECT DISTINCT ac.id, ac.created_at, ac.name, ac.email, ac.phone, ac.stage, 
               ac.last_touch, ac.property_address,
               COALESCE(
                   (SELECT MAX(ci.interaction_date) 
                    FROM crm_interactions ci 
                    WHERE ci.contact_id = ac.id 
                    AND ci.contact_type = 'agent_contact' 
                    AND ci.professional_user_id = ac.agent_user_id),
                   ac.last_touch,
                   ac.created_at
               ) as effective_last_contact
        FROM agent_contacts ac
        WHERE ac.agent_user_id = ?
        AND (
            COALESCE(
                (SELECT MAX(ci.interaction_date) 
                 FROM crm_interactions ci 
                 WHERE ci.contact_id = ac.id 
                 AND ci.contact_type = 'agent_contact' 
                 AND ci.professional_user_id = ac.agent_user_id),
                ac.last_touch,
                ac.created_at
            ) < ? OR
            COALESCE(
                (SELECT MAX(ci.interaction_date) 
                 FROM crm_interactions ci 
                 WHERE ci.contact_id = ac.id 
                 AND ci.contact_type = 'agent_contact' 
                 AND ci.professional_user_id = ac.agent_user_id),
                ac.last_touch
            ) IS NULL
        )
        ORDER BY effective_last_contact ASC
    """
    cur.execute(query, (agent_user_id, cutoff_iso))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_agent_contact(contact_id: int, agent_user_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, name, email, phone, stage, best_contact, last_touch,
               birthday, home_anniversary, address, notes, tags, property_address,
               property_value, equity_estimate, auto_birthday, auto_anniversary,
               auto_seasonal, auto_equity, auto_holidays, equity_frequency
        FROM agent_contacts
        WHERE id = ? AND agent_user_id = ?
        """,
        (contact_id, agent_user_id),
    )
    row = cur.fetchone()
    conn.close()
    return row


def update_agent_contact(
    contact_id: int,
    agent_user_id: int,
    **kwargs
) -> None:
    """Update agent contact fields. Pass any fields to update as kwargs."""
    if not kwargs:
        return
    conn = get_connection()
    cur = conn.cursor()
    updates = []
    values = []
    for key, value in kwargs.items():
        updates.append(f"{key} = ?")
        values.append(value)
    values.extend([contact_id, agent_user_id])
    cur.execute(
        f"""
        UPDATE agent_contacts
        SET {', '.join(updates)}, last_touch = CURRENT_TIMESTAMP
        WHERE id = ? AND agent_user_id = ?
        """,
        tuple(values),
    )
    conn.commit()
    conn.close()


def add_agent_transaction(
    agent_user_id: int,
    property_address: str,
    client_name: str,
    side: str,
    stage: str,
    close_date: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO agent_transactions (
            agent_user_id, property_address, client_name, side, stage, close_date
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (agent_user_id, property_address, client_name, side, stage, close_date),
    )
    conn.commit()
    conn.close()


def list_agent_transactions(agent_user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, property_address, client_name, side, stage, close_date
        FROM agent_transactions
        WHERE agent_user_id = ?
        ORDER BY created_at DESC
        """,
        (agent_user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_agent_transaction(
    agent_user_id: int,
    tx_id: int,
) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, property_address, client_name, side, stage, close_date
        FROM agent_transactions
        WHERE agent_user_id = ? AND id = ?
        """,
        (agent_user_id, tx_id),
    )
    row = cur.fetchone()
    conn.close()
    return row


# =========================
# LENDER CRM / LOANS
# =========================


def add_lender_borrower(
    lender_user_id: int,
    name: str,
    status: str = "prospect",
    loan_type: str = "",
    target_payment: str = "",
    last_touch: str = "",
    email: str = "",
    phone: str = "",
    birthday: str = "",
    home_anniversary: str = "",
    address: str = "",
    notes: str = "",
    tags: str = "",
    property_address: str = "",
    loan_amount: float = None,
    loan_rate: float = None,
    auto_birthday: int = 1,
    auto_anniversary: int = 1,
    auto_seasonal: int = 1,
    auto_equity: int = 1,
    auto_holidays: int = 1,
    equity_frequency: str = "monthly",
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO lender_borrowers (
            lender_user_id, name, status, loan_type, target_payment, last_touch,
            email, phone, birthday, home_anniversary, address, notes, tags,
            property_address, loan_amount, loan_rate, auto_birthday, auto_anniversary,
            auto_seasonal, auto_equity, auto_holidays, equity_frequency
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (lender_user_id, name, status, loan_type, target_payment, last_touch,
         email, phone, birthday, home_anniversary, address, notes, tags,
         property_address, loan_amount, loan_rate, auto_birthday, auto_anniversary,
         auto_seasonal, auto_equity, auto_holidays, equity_frequency),
    )
    borrower_id = cur.lastrowid
    conn.commit()
    conn.close()
    return borrower_id


def list_lender_borrowers(lender_user_id: int, status_filter: str = None) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    query = """
        SELECT id, created_at, name, status, loan_type, target_payment, last_touch,
               email, phone, birthday, home_anniversary, address, notes, tags,
               property_address, loan_amount, loan_rate, auto_birthday, auto_anniversary,
               auto_seasonal, auto_equity, auto_holidays, equity_frequency
        FROM lender_borrowers
        WHERE lender_user_id = ?
    """
    params = [lender_user_id]
    if status_filter:
        query += " AND status = ?"
        params.append(status_filter)
    query += " ORDER BY created_at DESC"
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_lender_borrower(borrower_id: int, lender_user_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, name, status, loan_type, target_payment, last_touch,
               email, phone, birthday, home_anniversary, address, notes, tags,
               property_address, loan_amount, loan_rate, auto_birthday, auto_anniversary,
               auto_seasonal, auto_equity, auto_holidays, equity_frequency
        FROM lender_borrowers
        WHERE id = ? AND lender_user_id = ?
        """,
        (borrower_id, lender_user_id),
    )
    row = cur.fetchone()
    conn.close()
    return row


def update_lender_borrower(
    borrower_id: int,
    lender_user_id: int,
    **kwargs
) -> None:
    """Update lender borrower fields. Pass any fields to update as kwargs."""
    if not kwargs:
        return
    conn = get_connection()
    cur = conn.cursor()
    updates = []
    values = []
    for key, value in kwargs.items():
        updates.append(f"{key} = ?")
        values.append(value)
    values.extend([borrower_id, lender_user_id])
    cur.execute(
        f"""
        UPDATE lender_borrowers
        SET {', '.join(updates)}, last_touch = CURRENT_TIMESTAMP
        WHERE id = ? AND lender_user_id = ?
        """,
        tuple(values),
    )
    conn.commit()
    conn.close()


def add_lender_loan(
    lender_user_id: int,
    borrower_name: str,
    status: str,
    loan_type: str,
    target_payment: str,
    stage: str,
    close_date: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO lender_loans (
            lender_user_id, borrower_name, status, loan_type, target_payment, stage, close_date
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (lender_user_id, borrower_name, status, loan_type, target_payment, stage, close_date),
    )
    conn.commit()
    conn.close()


def list_lender_loans(lender_user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, borrower_name, status, loan_type, target_payment, stage, close_date
        FROM lender_loans
        WHERE lender_user_id = ?
        ORDER BY created_at DESC
        """,
        (lender_user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# =========================
# TEMPLATES (EMAIL / MARKETING)
# =========================


def add_message_template(
    owner_user_id: int,
    role: str,
    label: str,
    category: str,
    channel: str,
    subject: str,
    body: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO message_templates (
            owner_user_id, role, label, category, channel, subject, body
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (owner_user_id, role, label, category, channel, subject, body),
    )
    conn.commit()
    conn.close()


def list_message_templates(
    role: str,
    owner_user_id: Optional[int] = None,
) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    if owner_user_id:
        cur.execute(
            """
            SELECT id, created_at, label, category, channel, subject, body
            FROM message_templates
            WHERE role = ? AND owner_user_id = ?
            ORDER BY created_at DESC
            """,
            (role, owner_user_id),
        )
    else:
        cur.execute(
            """
            SELECT id, created_at, label, category, channel, subject, body
            FROM message_templates
            WHERE role = ?
            ORDER BY created_at DESC
            """,
            (role,),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def add_marketing_template(
    owner_user_id: int,
    role: str,
    template_type: str,
    name: str,
    description: str,
    content: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO marketing_templates (
            owner_user_id, role, template_type, name, description, content
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (owner_user_id, role, template_type, name, description, content),
    )
    conn.commit()
    conn.close()


def list_marketing_templates(
    role: str,
    owner_user_id: Optional[int] = None,
) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    if owner_user_id:
        cur.execute(
            """
            SELECT id, created_at, template_type, name, description, content
            FROM marketing_templates
            WHERE role = ? AND owner_user_id = ?
            ORDER BY created_at DESC
            """,
            (role, owner_user_id),
        )
    else:
        cur.execute(
            """
            SELECT id, created_at, template_type, name, description, content
            FROM marketing_templates
            WHERE role = ?
            ORDER BY created_at DESC
            """,
            (role,),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


# =========================
# DOCUMENT MANAGEMENT
# =========================


def delete_homeowner_document(doc_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM homeowner_documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()


def update_homeowner_document_file(
    doc_id: int,
    file_path: str = None,
    r2_key: str = None,
    r2_url: str = None,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    updates = []
    values = []
    if file_path is not None:
        updates.append("file_path = ?")
        values.append(file_path)
    if r2_key is not None:
        updates.append("r2_key = ?")
        values.append(r2_key)
    if r2_url is not None:
        updates.append("r2_url = ?")
        values.append(r2_url)
    if updates:
        values.append(doc_id)
        cur.execute(
            f"UPDATE homeowner_documents SET {', '.join(updates)} WHERE id = ?",
            tuple(values),
        )
        conn.commit()
    conn.close()


def get_homeowner_document_for_user(doc_id: int, user_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM homeowner_documents WHERE id = ? AND user_id = ?",
        (doc_id, user_id),
    )
    row = cur.fetchone()
    conn.close()
    return row


# =========================
# TIMELINE EVENTS
# =========================


def add_timeline_event(
    user_id: int,
    event_date: str,
    title: str,
    category: str,
    cost: str = None,
    notes: str = None,
    files: List[str] = None,
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_timeline_events (
            user_id, event_date, title, category, cost, notes, files
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, event_date, title, category, cost, notes, json.dumps(files or [])),
    )
    event_id = cur.lastrowid
    conn.commit()
    conn.close()
    return event_id


def list_timeline_events(user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, event_date, title, category, cost, notes, files
        FROM homeowner_timeline_events
        WHERE user_id = ?
        ORDER BY event_date DESC, created_at DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_timeline_event(event_id: int, user_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM homeowner_timeline_events WHERE id = ? AND user_id = ?",
        (event_id, user_id),
    )
    conn.commit()
    conn.close()


# =========================
# SIMPLE NOTES
# =========================


def add_simple_note(user_id: int, content: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT INTO simple_notes (user_id, content) VALUES (?, ?)", (user_id, content))
    note_id = cur.lastrowid
    conn.commit()
    conn.close()
    return note_id


def list_simple_notes(user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, created_at, content FROM simple_notes WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_simple_note(note_id: int, user_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM simple_notes WHERE id = ? AND user_id = ?", (note_id, user_id))
    conn.commit()
    conn.close()


# =========================
# DESIGN BOARD NOTES
# =========================


def add_design_board_note(
    user_id: int,
    project_name: str,
    title: str = None,
    tags: str = None,
    details: str = None,
    links: str = None,
    photos: List[str] = None,
    files: List[str] = None,
    vision_statement: str = None,
    color_palette: List[str] = None,
    board_template: str = "minimal",
    label_style: str = "subtle",
    is_private: int = 0,
    fixtures: List[str] = None,
) -> int:
    return add_homeowner_note(
        user_id=user_id,
        project_name=project_name,
        title=title,
        tags=tags,
        details=details,
        links=links,
        photos=photos,
        files=files,
        vision_statement=vision_statement,
        color_palette=color_palette,
        board_template=board_template,
        label_style=label_style,
        is_private=is_private,
        fixtures=fixtures,
    )


def get_design_boards_for_user(user_id: int) -> Dict[str, Any]:
    """Get all unique design boards (project_name) for a user."""
    if not user_id:
        print(f"[DB WARNING] get_design_boards_for_user called with invalid user_id: {user_id}")
        return {}
    
    conn = None
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            SELECT DISTINCT project_name, 
                   MIN(created_at) as first_created,
                   COUNT(*) as note_count
            FROM homeowner_notes
            WHERE user_id = ? AND project_name IS NOT NULL AND project_name != ''
            GROUP BY project_name
            ORDER BY first_created DESC
            """,
            (user_id,),
        )
        rows = cur.fetchall()
        boards = {}
        for row in rows:
            board_name = row["project_name"] if hasattr(row, 'keys') else row[0]
            boards[board_name] = {
                "first_created": row["first_created"] if hasattr(row, 'keys') else row[1],
                "note_count": row["note_count"] if hasattr(row, 'keys') else row[2],
            }
        print(f"[DB] Found {len(boards)} boards for user {user_id}: {list(boards.keys())}")
        return boards
    except Exception as e:
        import traceback
        print(f"[DB ERROR] Error getting boards for user {user_id}: {str(e)}")
        print(traceback.format_exc())
        return {}
    finally:
        if conn:
            conn.close()


def get_design_board_details(user_id: int, project_name: str) -> List[sqlite3.Row]:
    """Get all notes for a specific design board."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, project_name, title, tags, details, links,
               photos, files, vision_statement, color_palette,
               board_template, label_style, is_private, shareable_link,
               product_sources, show_notes_panel, fixtures
        FROM homeowner_notes
        WHERE user_id = ? AND project_name = ?
        ORDER BY created_at ASC
        """,
        (user_id, project_name),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_design_board(user_id: int, project_name: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM homeowner_notes WHERE user_id = ? AND project_name = ?",
        (user_id, project_name),
    )
    conn.commit()
    conn.close()


def update_homeowner_note_photos(user_id: int, project_name: str, photos: List[str]) -> None:
    """Update photos for all notes in a design board."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE homeowner_notes SET photos = ? WHERE user_id = ? AND project_name = ?",
        (json.dumps(photos), user_id, project_name),
    )
    conn.commit()
    conn.close()


def remove_photos_from_board(user_id: int, project_name: str, photos_to_remove: List[str]) -> None:
    """Remove specific photos from all notes in a design board."""
    if not photos_to_remove:
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, photos FROM homeowner_notes WHERE user_id = ? AND project_name = ?",
        (user_id, project_name),
    )
    rows = cur.fetchall()

    for row in rows:
        note_id = row["id"]
        photos_json = row["photos"] or "[]"
        try:
            photos = json.loads(photos_json)
        except Exception:
            photos = []

        filtered = [p for p in photos if p not in photos_to_remove]
        if len(filtered) != len(photos):
            cur.execute(
                "UPDATE homeowner_notes SET photos = ? WHERE id = ?",
                (json.dumps(filtered), note_id),
            )

    conn.commit()
    conn.close()


def remove_fixtures_from_board(user_id: int, project_name: str, fixtures_to_remove: List[str]) -> None:
    """Remove specific fixtures from all notes in a design board."""
    if not fixtures_to_remove:
        return

    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, fixtures FROM homeowner_notes WHERE user_id = ? AND project_name = ?",
        (user_id, project_name),
    )
    rows = cur.fetchall()

    for row in rows:
        note_id = row["id"]
        fixtures_json = row["fixtures"] or "[]"
        try:
            fixtures = json.loads(fixtures_json)
        except Exception:
            fixtures = []

        filtered = [f for f in fixtures if f not in fixtures_to_remove]
        if len(filtered) != len(fixtures):
            cur.execute(
                "UPDATE homeowner_notes SET fixtures = ? WHERE id = ?",
                (json.dumps(filtered), note_id),
            )

    conn.commit()
    conn.close()


def get_homeowner_note_by_id(note_id: int, user_id: int) -> Optional[sqlite3.Row]:
    """Get a single note by ID, ensuring it belongs to the user."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, project_name, title, tags, details, links,
               photos, files, vision_statement, color_palette,
               board_template, label_style, is_private, shareable_link,
               product_sources, show_notes_panel, fixtures
        FROM homeowner_notes
        WHERE id = ? AND user_id = ?
        """,
        (note_id, user_id),
    )
    row = cur.fetchone()
    conn.close()
    return row


def update_homeowner_note(
    note_id: int,
    user_id: int,
    title: str = None,
    details: str = None,
    tags: str = None,
) -> None:
    """Update a homeowner note. Only updates provided fields."""
    conn = get_connection()
    cur = conn.cursor()
    
    updates = []
    params = []
    
    if title is not None:
        updates.append("title = ?")
        params.append(title)
    if details is not None:
        updates.append("details = ?")
        params.append(details)
    if tags is not None:
        updates.append("tags = ?")
        params.append(tags)
    
    if not updates:
        conn.close()
        return
    
    params.append(note_id)
    params.append(user_id)
    
    cur.execute(
        f"""
        UPDATE homeowner_notes
        SET {', '.join(updates)}
        WHERE id = ? AND user_id = ?
        """,
        tuple(params),
    )
    conn.commit()
    conn.close()


def delete_homeowner_note(note_id: int, user_id: int) -> None:
    """Delete a single homeowner note by ID."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM homeowner_notes WHERE id = ? AND user_id = ?",
        (note_id, user_id),
    )
    conn.commit()
    conn.close()


def duplicate_design_board(user_id: int, original_name: str, new_name: str) -> None:
    """Create a duplicate of a design board with a new name."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Copy all notes from the original board to the new board
    cur.execute(
        """
        INSERT INTO homeowner_notes 
        (user_id, project_name, title, tags, details, links, photos, files,
         vision_statement, color_palette, board_template, label_style, 
         is_private, product_sources, show_notes_panel)
        SELECT user_id, ?, title, tags, details, links, photos, files,
               vision_statement, color_palette, board_template, label_style,
               is_private, product_sources, show_notes_panel
        FROM homeowner_notes
        WHERE user_id = ? AND (project_name = ? OR title = ?)
        """,
        (new_name, user_id, original_name, original_name),
    )
    
    conn.commit()
    conn.close()


def update_board_privacy(user_id: int, project_name: str, is_private: int, shareable_link: str = None) -> None:
    """Update privacy settings and shareable link for a board."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        UPDATE homeowner_notes 
        SET is_private = ?, shareable_link = ?
        WHERE user_id = ? AND (project_name = ? OR title = ?)
        """,
        (is_private, shareable_link, user_id, project_name, project_name),
    )
    
    conn.commit()
    conn.close()


def update_board_colors(user_id: int, project_name: str, color_palette: List[str]) -> None:
    """Update color palette for the first note in a board."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        UPDATE homeowner_notes 
        SET color_palette = ?
        WHERE id = (
            SELECT id FROM homeowner_notes 
            WHERE user_id = ? AND (project_name = ? OR title = ?)
            ORDER BY created_at ASC LIMIT 1
        )
        """,
        (json.dumps(color_palette or []), user_id, project_name, project_name),
    )
    
    conn.commit()
    conn.close()


def update_board_template(user_id: int, project_name: str, board_template: str) -> None:
    """Update board template style for the first note in a board."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        UPDATE homeowner_notes 
        SET board_template = ?
        WHERE id = (
            SELECT id FROM homeowner_notes 
            WHERE user_id = ? AND (project_name = ? OR title = ?)
            ORDER BY created_at ASC LIMIT 1
        )
        """,
        (board_template, user_id, project_name, project_name),
    )
    
    conn.commit()
    conn.close()


# ====================== PROPERTY MANAGEMENT ======================

def add_property(user_id: int, address: str, estimated_value: float = None, 
                 property_type: str = "primary") -> int:
    """Add a new property for the user.
    
    If this is the user's first property, automatically set it as primary.
    Returns the new property_id.
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if user has any properties
    cur.execute("SELECT COUNT(*) as count FROM properties WHERE user_id = ?", (user_id,))
    count = cur.fetchone()["count"]
    is_primary = 1 if count == 0 else 0
    
    cur.execute(
        """INSERT INTO properties (user_id, address, estimated_value, property_type, is_primary)
           VALUES (?, ?, ?, ?, ?)""",
        (user_id, address, estimated_value, property_type, is_primary)
    )
    property_id = cur.lastrowid
    conn.commit()
    conn.close()
    return property_id


def get_user_properties(user_id: int) -> List[dict]:
    """Get all properties for a user, ordered by primary first."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, address, estimated_value, property_type, is_primary, created_at
           FROM properties 
           WHERE user_id = ?
           ORDER BY is_primary DESC, created_at DESC""",
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_property_by_id(property_id: int) -> dict:
    """Get a specific property by ID."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, user_id, address, estimated_value, property_type, is_primary, created_at
           FROM properties WHERE id = ?""",
        (property_id,)
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def set_primary_property(user_id: int, property_id: int) -> None:
    """Set a property as primary and unset all others for this user."""
    conn = get_connection()
    cur = conn.cursor()
    # Unset all primary flags for user
    cur.execute("UPDATE properties SET is_primary = 0 WHERE user_id = ?", (user_id,))
    # Set the selected property as primary
    cur.execute(
        "UPDATE properties SET is_primary = 1 WHERE id = ? AND user_id = ?",
        (property_id, user_id)
    )
    conn.commit()
    conn.close()


def get_primary_property(user_id: int) -> dict:
    """Get the user's primary property."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT id, address, estimated_value, property_type, is_primary, created_at
           FROM properties 
           WHERE user_id = ? AND is_primary = 1
           LIMIT 1""",
        (user_id,)
    )
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def delete_property(property_id: int, user_id: int) -> None:
    """Delete a property and its associated snapshots."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM properties WHERE id = ? AND user_id = ?", (property_id, user_id))
    conn.commit()
    conn.close()


def get_homeowner_snapshot_for_property(user_id: int, property_id: int) -> dict:
    """Get homeowner snapshot for a specific property."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT value_estimate, equity_estimate, loan_rate, loan_payment, 
                  loan_balance, loan_term_years, loan_start_date,
                  last_value_refresh, value_refresh_source, updated_at,
                  property_tax_monthly, homeowners_insurance_monthly, pmi_monthly
           FROM homeowner_snapshots
           WHERE user_id = ? AND property_id = ?
           LIMIT 1""",
        (user_id, property_id)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        return {}
    return dict(row)


def upsert_homeowner_snapshot_for_property(
    user_id: int,
    property_id: int,
    value_estimate: float = None,
    loan_balance: float = None,
    loan_rate: float = None,
    loan_payment: float = None,
    loan_term_years: float = None,
    loan_start_date: str = None,
    property_tax_monthly: float = None,
    homeowners_insurance_monthly: float = None,
    pmi_monthly: float = None,
) -> None:
    """Insert or update homeowner snapshot for a specific property."""
    conn = get_connection()
    cur = conn.cursor()

    # Get existing data if it exists
    cur.execute(
        """SELECT value_estimate, loan_balance, loan_rate, loan_payment, 
                  loan_term_years, loan_start_date, property_tax_monthly,
                  homeowners_insurance_monthly, pmi_monthly
           FROM homeowner_snapshots
           WHERE user_id = ? AND property_id = ?""",
        (user_id, property_id),
    )
    existing = cur.fetchone()

    # Merge with existing data - only update fields that are explicitly provided (not None)
    # This ensures empty form fields don't overwrite existing data
    if existing:
        # Only update fields that were explicitly provided (not None)
        # If a field is None, it means the form didn't provide it, so keep existing value
        merged_value = value_estimate if value_estimate is not None else existing.get("value_estimate")
        merged_loan_balance = loan_balance if loan_balance is not None else existing.get("loan_balance")
        merged_loan_rate = loan_rate if loan_rate is not None else existing.get("loan_rate")
        merged_loan_payment = loan_payment if loan_payment is not None else existing.get("loan_payment")
        merged_loan_term_years = loan_term_years if loan_term_years is not None else existing.get("loan_term_years")
        merged_loan_start_date = loan_start_date if loan_start_date is not None else existing.get("loan_start_date")
        merged_property_tax = property_tax_monthly if property_tax_monthly is not None else existing.get("property_tax_monthly")
        merged_insurance = homeowners_insurance_monthly if homeowners_insurance_monthly is not None else existing.get("homeowners_insurance_monthly")
        merged_pmi = pmi_monthly if pmi_monthly is not None else existing.get("pmi_monthly")
    else:
        # No existing data - use provided values (or None if not provided)
        merged_value = value_estimate
        merged_loan_balance = loan_balance
        merged_loan_rate = loan_rate
        merged_loan_payment = loan_payment
        merged_loan_term_years = loan_term_years
        merged_loan_start_date = loan_start_date
        merged_property_tax = property_tax_monthly
        merged_insurance = homeowners_insurance_monthly
        merged_pmi = pmi_monthly
    
    # Debug logging
    print(f"[SNAPSHOT UPDATE] user_id={user_id}, property_id={property_id}")
    print(f"[SNAPSHOT UPDATE] Input values: value={value_estimate}, balance={loan_balance}, rate={loan_rate}")
    print(f"[SNAPSHOT UPDATE] Merged values: value={merged_value}, balance={merged_loan_balance}, rate={merged_loan_rate}")

    # Calculate equity
    equity = None
    if merged_value is not None and merged_loan_balance is not None:
        equity = merged_value - merged_loan_balance

    # Upsert - merged values are already correct, just insert/update them
    # Note: We already merged in Python, so we don't need COALESCE here
    cur.execute(
        """INSERT INTO homeowner_snapshots 
           (user_id, property_id, value_estimate, equity_estimate, loan_balance, 
            loan_rate, loan_payment, loan_term_years, loan_start_date, 
            property_tax_monthly, homeowners_insurance_monthly, pmi_monthly, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(user_id, property_id) DO UPDATE SET
               value_estimate = excluded.value_estimate,
               equity_estimate = excluded.equity_estimate,
               loan_balance = excluded.loan_balance,
               loan_rate = excluded.loan_rate,
               loan_payment = excluded.loan_payment,
               loan_term_years = excluded.loan_term_years,
               loan_start_date = excluded.loan_start_date,
               property_tax_monthly = excluded.property_tax_monthly,
               homeowners_insurance_monthly = excluded.homeowners_insurance_monthly,
               pmi_monthly = excluded.pmi_monthly,
               updated_at = CURRENT_TIMESTAMP""",
        (user_id, property_id, merged_value, equity, merged_loan_balance, 
         merged_loan_rate, merged_loan_payment, merged_loan_term_years, merged_loan_start_date,
         merged_property_tax, merged_insurance, merged_pmi),
    )
    conn.commit()
    print(f"[SNAPSHOT UPDATE] Successfully saved to database")
    
    # Create monthly history record when snapshot is updated (only if we have meaningful data)
    if merged_value is not None or merged_loan_balance is not None:
        try:
            # Check if we already have a history record for today
            cur.execute(
                """SELECT id FROM homeowner_snapshot_history 
                   WHERE user_id = ? AND property_id = ? AND date(snapshot_date) = date('now')
                   LIMIT 1""",
                (user_id, property_id)
            )
            existing_today = cur.fetchone()
            
            if not existing_today:
                # Only create new history if we don't have one for today
                cur.execute(
                    """INSERT INTO homeowner_snapshot_history 
                       (user_id, property_id, snapshot_date, value_estimate, equity_estimate, 
                        loan_balance, loan_rate, loan_payment)
                       VALUES (?, ?, date('now'), ?, ?, ?, ?, ?)""",
                    (user_id, property_id, merged_value, equity, merged_loan_balance, 
                     merged_loan_rate, merged_loan_payment),
                )
                conn.commit()
        except Exception as e:
            print(f"Error creating snapshot history: {e}")
            # Don't fail the main update if history fails
    
    conn.close()


def get_snapshot_history(user_id: int, property_id: int, limit: int = 12) -> List[Dict[str, Any]]:
    """Get historical snapshots for a property, ordered by date descending."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT snapshot_date, value_estimate, equity_estimate, loan_balance, 
                  loan_rate, loan_payment
           FROM homeowner_snapshot_history
           WHERE user_id = ? AND property_id = ?
           ORDER BY snapshot_date DESC
           LIMIT ?""",
        (user_id, property_id, limit)
    )
    rows = cur.fetchall()
    conn.close()
    return [dict(row) for row in rows] if rows else []


# ====================== CRM INTERACTIONS & AUTOMATED EMAILS ======================

def add_crm_interaction(
    contact_id: int,
    contact_type: str,
    professional_user_id: int,
    interaction_type: str,
    subject: str = "",
    notes: str = "",
    channel: str = "email",
    interaction_date: str = None,
) -> int:
    """Add an interaction record for a CRM contact."""
    conn = get_connection()
    cur = conn.cursor()
    if not interaction_date:
        interaction_date = datetime.now().isoformat()
    cur.execute(
        """
        INSERT INTO crm_interactions (
            contact_id, contact_type, professional_user_id, interaction_type,
            interaction_date, subject, notes, channel
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (contact_id, contact_type, professional_user_id, interaction_type,
         interaction_date, subject, notes, channel),
    )
    interaction_id = cur.lastrowid
    conn.commit()
    conn.close()
    return interaction_id


def list_crm_interactions(
    contact_id: int,
    contact_type: str,
    professional_user_id: int,
    limit: int = 50,
) -> List[sqlite3.Row]:
    """List interactions for a contact."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, interaction_type, interaction_date, subject, notes, channel, created_at
        FROM crm_interactions
        WHERE contact_id = ? AND contact_type = ? AND professional_user_id = ?
        ORDER BY interaction_date DESC, created_at DESC
        LIMIT ?
        """,
        (contact_id, contact_type, professional_user_id, limit),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


# ====================== CRM TASKS ======================

def add_crm_task(
    contact_id: int,
    contact_type: str,
    professional_user_id: int,
    title: str,
    description: str = "",
    due_date: str = None,
    priority: str = "medium",
    reminder_date: str = None,
) -> int:
    """Add a task/follow-up for a CRM contact."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO crm_tasks (
            contact_id, contact_type, professional_user_id, title, description,
            due_date, priority, reminder_date, status
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (contact_id, contact_type, professional_user_id, title, description,
         due_date, priority, reminder_date),
    )
    task_id = cur.lastrowid
    conn.commit()
    conn.close()
    return task_id


def list_crm_tasks(
    professional_user_id: int,
    contact_id: int = None,
    contact_type: str = None,
    status: str = None,
    include_overdue: bool = True,
) -> List[sqlite3.Row]:
    """List tasks for contacts."""
    conn = get_connection()
    cur = conn.cursor()
    query = """
        SELECT id, contact_id, contact_type, title, description, due_date, priority,
               status, reminder_date, completed_at, created_at
        FROM crm_tasks
        WHERE professional_user_id = ?
    """
    params = [professional_user_id]
    
    if contact_id and contact_type:
        query += " AND contact_id = ? AND contact_type = ?"
        params.extend([contact_id, contact_type])
    
    if status:
        query += " AND status = ?"
        params.append(status)
    elif not include_overdue:
        query += " AND (status != 'completed' OR status IS NULL)"
    
    query += " ORDER BY due_date ASC, priority DESC, created_at DESC"
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows


def update_crm_task(
    task_id: int,
    professional_user_id: int,
    **kwargs
) -> None:
    """Update a CRM task."""
    if not kwargs:
        return
    conn = get_connection()
    cur = conn.cursor()
    updates = []
    values = []
    for key, value in kwargs.items():
        updates.append(f"{key} = ?")
        values.append(value)
    values.extend([task_id, professional_user_id])
    cur.execute(
        f"""
        UPDATE crm_tasks
        SET {', '.join(updates)}
        WHERE id = ? AND professional_user_id = ?
        """,
        tuple(values),
    )
    conn.commit()
    conn.close()


def delete_crm_task(task_id: int, professional_user_id: int) -> None:
    """Delete a CRM task."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM crm_tasks WHERE id = ? AND professional_user_id = ?",
        (task_id, professional_user_id),
    )
    conn.commit()
    conn.close()


# ====================== CRM DEALS ======================

def add_crm_deal(
    contact_id: int,
    contact_type: str,
    professional_user_id: int,
    deal_name: str,
    deal_type: str = "other",
    property_address: str = "",
    deal_value: float = None,
    commission_rate: float = None,
    stage: str = "prospect",
    probability: int = 0,
    expected_close_date: str = None,
    notes: str = "",
) -> int:
    """Add a deal for a CRM contact."""
    conn = get_connection()
    cur = conn.cursor()
    expected_commission = None
    if deal_value and commission_rate:
        expected_commission = deal_value * (commission_rate / 100)
    
    cur.execute(
        """
        INSERT INTO crm_deals (
            contact_id, contact_type, professional_user_id, deal_name, deal_type,
            property_address, deal_value, commission_rate, expected_commission,
            stage, probability, expected_close_date, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (contact_id, contact_type, professional_user_id, deal_name, deal_type,
         property_address, deal_value, commission_rate, expected_commission,
         stage, probability, expected_close_date, notes),
    )
    deal_id = cur.lastrowid
    conn.commit()
    conn.close()
    return deal_id


def list_crm_deals(
    professional_user_id: int,
    contact_id: int = None,
    contact_type: str = None,
    stage: str = None,
) -> List[sqlite3.Row]:
    """List deals for contacts."""
    conn = get_connection()
    cur = conn.cursor()
    query = """
        SELECT id, contact_id, contact_type, deal_name, deal_type, property_address,
               deal_value, commission_rate, expected_commission, stage, probability,
               expected_close_date, actual_close_date, notes, created_at, updated_at
        FROM crm_deals
        WHERE professional_user_id = ?
    """
    params = [professional_user_id]
    
    if contact_id and contact_type:
        query += " AND contact_id = ? AND contact_type = ?"
        params.extend([contact_id, contact_type])
    
    if stage:
        query += " AND stage = ?"
        params.append(stage)
    
    query += " ORDER BY expected_close_date ASC, created_at DESC"
    cur.execute(query, tuple(params))
    rows = cur.fetchall()
    conn.close()
    return rows


def update_crm_deal(
    deal_id: int,
    professional_user_id: int,
    **kwargs
) -> None:
    """Update a CRM deal."""
    if not kwargs:
        return
    conn = get_connection()
    cur = conn.cursor()
    updates = []
    values = []
    
    # Recalculate expected_commission if deal_value or commission_rate changes
    if 'deal_value' in kwargs or 'commission_rate' in kwargs:
        # Get current values
        cur.execute(
            "SELECT deal_value, commission_rate FROM crm_deals WHERE id = ? AND professional_user_id = ?",
            (deal_id, professional_user_id)
        )
        row = cur.fetchone()
        if row:
            deal_value = kwargs.get('deal_value', row['deal_value'])
            commission_rate = kwargs.get('commission_rate', row['commission_rate'])
            if deal_value and commission_rate:
                kwargs['expected_commission'] = deal_value * (commission_rate / 100)
    
    for key, value in kwargs.items():
        updates.append(f"{key} = ?")
        values.append(value)
    
    updates.append("updated_at = CURRENT_TIMESTAMP")
    values.extend([deal_id, professional_user_id])
    
    cur.execute(
        f"""
        UPDATE crm_deals
        SET {', '.join(updates)}
        WHERE id = ? AND professional_user_id = ?
        """,
        tuple(values),
    )
    conn.commit()
    conn.close()


def delete_crm_deal(deal_id: int, professional_user_id: int) -> None:
    """Delete a CRM deal."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM crm_deals WHERE id = ? AND professional_user_id = ?",
        (deal_id, professional_user_id),
    )
    conn.commit()
    conn.close()


# ====================== CRM RELATIONSHIPS ======================

def add_crm_relationship(
    contact_id_1: int,
    contact_id_2: int,
    contact_type: str,
    professional_user_id: int,
    relationship_type: str = "other",
    notes: str = "",
) -> int:
    """Add a relationship between two contacts."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO crm_relationships (
                contact_id_1, contact_id_2, contact_type, professional_user_id,
                relationship_type, notes
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (contact_id_1, contact_id_2, contact_type, professional_user_id,
             relationship_type, notes),
        )
        relationship_id = cur.lastrowid
        conn.commit()
        conn.close()
        return relationship_id
    except sqlite3.IntegrityError:
        conn.close()
        return None  # Relationship already exists


def list_crm_relationships(
    contact_id: int,
    contact_type: str,
    professional_user_id: int,
) -> List[sqlite3.Row]:
    """List relationships for a contact."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, contact_id_1, contact_id_2, relationship_type, notes, created_at
        FROM crm_relationships
        WHERE professional_user_id = ? AND contact_type = ?
        AND (contact_id_1 = ? OR contact_id_2 = ?)
        """,
        (professional_user_id, contact_type, contact_id, contact_id),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_crm_relationship(relationship_id: int, professional_user_id: int) -> None:
    """Delete a CRM relationship."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM crm_relationships WHERE id = ? AND professional_user_id = ?",
        (relationship_id, professional_user_id),
    )
    conn.commit()
    conn.close()


# ====================== CRM SAVED VIEWS ======================

def add_crm_saved_view(
    professional_user_id: int,
    role: str,
    view_name: str,
    filters_json: str,
    is_default: int = 0,
) -> int:
    """Add a saved view/filter combination."""
    conn = get_connection()
    cur = conn.cursor()
    
    # If this is set as default, unset other defaults
    if is_default:
        cur.execute(
            "UPDATE crm_saved_views SET is_default = 0 WHERE professional_user_id = ? AND role = ?",
            (professional_user_id, role)
        )
    
    cur.execute(
        """
        INSERT INTO crm_saved_views (
            professional_user_id, role, view_name, filters_json, is_default
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (professional_user_id, role, view_name, filters_json, is_default),
    )
    view_id = cur.lastrowid
    conn.commit()
    conn.close()
    return view_id


def list_crm_saved_views(
    professional_user_id: int,
    role: str,
) -> List[sqlite3.Row]:
    """List saved views for a user."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, view_name, filters_json, is_default, created_at
        FROM crm_saved_views
        WHERE professional_user_id = ? AND role = ?
        ORDER BY is_default DESC, created_at DESC
        """,
        (professional_user_id, role),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_crm_saved_view(view_id: int, professional_user_id: int) -> None:
    """Delete a saved view."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM crm_saved_views WHERE id = ? AND professional_user_id = ?",
        (view_id, professional_user_id),
    )
    conn.commit()
    conn.close()


def log_automated_email(
    contact_id: int,
    contact_type: str,
    professional_user_id: int,
    email_type: str,
    recipient_email: str,
    subject: str,
    status: str = "sent",
    error_message: str = None,
) -> int:
    """Log an automated email send."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO automated_email_logs (
            contact_id, contact_type, professional_user_id, email_type,
            recipient_email, subject, status, error_message
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (contact_id, contact_type, professional_user_id, email_type,
         recipient_email, subject, status, error_message),
    )
    log_id = cur.lastrowid
    conn.commit()
    conn.close()
    return log_id


def get_contacts_for_automated_email(
    professional_user_id: int,
    email_type: str,
    contact_type: str = "agent_contact",
) -> List[sqlite3.Row]:
    """Get contacts that should receive automated emails of a specific type."""
    conn = get_connection()
    cur = conn.cursor()
    
    if contact_type == "agent_contact":
        table = "agent_contacts"
        user_id_col = "agent_user_id"
        email_col = "email"
        if email_type == "birthday":
            enabled_col = "auto_birthday"
        elif email_type == "anniversary":
            enabled_col = "auto_anniversary"
        elif email_type == "seasonal":
            enabled_col = "auto_seasonal"
        elif email_type == "equity":
            enabled_col = "auto_equity"
        elif email_type == "holiday":
            enabled_col = "auto_holidays"
        else:
            return []
    else:  # lender_borrower
        table = "lender_borrowers"
        user_id_col = "lender_user_id"
        email_col = "email"
        if email_type == "birthday":
            enabled_col = "auto_birthday"
        elif email_type == "anniversary":
            enabled_col = "auto_anniversary"
        elif email_type == "seasonal":
            enabled_col = "auto_seasonal"
        elif email_type == "equity":
            enabled_col = "auto_equity"
        elif email_type == "holiday":
            enabled_col = "auto_holidays"
        else:
            return []
    
    query = f"""
        SELECT id, name, {email_col} as email, birthday, home_anniversary,
               property_address, property_value, equity_estimate, equity_frequency
        FROM {table}
        WHERE {user_id_col} = ? AND {email_col} IS NOT NULL AND {email_col} != ''
              AND {enabled_col} = 1
    """
    cur.execute(query, (professional_user_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


# ------------- USER PROFILES -------------
def get_user_profile(user_id: int) -> Optional[sqlite3.Row]:
    """Get user profile by user_id."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM user_profiles WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


def create_or_update_user_profile(
    user_id: int,
    role: str,
    professional_photo: Optional[str] = None,
    brokerage_logo: Optional[str] = None,
    team_name: Optional[str] = None,
    brokerage_name: Optional[str] = None,
    website_url: Optional[str] = None,
    facebook_url: Optional[str] = None,
    instagram_url: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    twitter_url: Optional[str] = None,
    youtube_url: Optional[str] = None,
    phone: Optional[str] = None,
    call_button_enabled: int = 1,
    schedule_button_enabled: int = 1,
    schedule_url: Optional[str] = None,
    application_url: Optional[str] = None,
    bio: Optional[str] = None,
    specialties: Optional[str] = None,
    years_experience: Optional[int] = None,
    languages: Optional[str] = None,
    service_areas: Optional[str] = None,
    nmls_number: Optional[str] = None,
    license_number: Optional[str] = None,
    company_address: Optional[str] = None,
    company_city: Optional[str] = None,
    company_state: Optional[str] = None,
    company_zip: Optional[str] = None,
    homebot_widget_id: Optional[str] = None,
    va_rate_30yr: Optional[float] = None,
    fha_rate_30yr: Optional[float] = None,
    conventional_rate_30yr: Optional[float] = None,
) -> int:
    """Create or update user profile. Returns profile id."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if profile exists
    cur.execute("SELECT id FROM user_profiles WHERE user_id = ?", (user_id,))
    existing = cur.fetchone()
    
    if existing:
        # Check if referral code exists, generate if not
        cur.execute("SELECT referral_code FROM user_profiles WHERE user_id = ?", (user_id,))
        ref_row = cur.fetchone()
        referral_code = ref_row[0] if ref_row and ref_row[0] else None
        
        if not referral_code:
            from database import generate_referral_code
            referral_code = generate_referral_code(user_id, role)
        
        # Get existing values to preserve if None is passed
        cur.execute("SELECT professional_photo, brokerage_logo FROM user_profiles WHERE user_id = ?", (user_id,))
        existing_media = cur.fetchone()
        existing_photo = existing_media[0] if existing_media and existing_media[0] else None
        existing_logo = existing_media[1] if existing_media and existing_media[1] else None
        
        # Use provided values, or preserve existing if None or empty string
        # CRITICAL: Empty string means "don't update", None means "use existing"
        final_photo = professional_photo if (professional_photo is not None and professional_photo != "") else existing_photo
        final_logo = brokerage_logo if (brokerage_logo is not None and brokerage_logo != "") else existing_logo
        
        print(f"[PROFILE UPDATE] user_id={user_id}, provided_photo={professional_photo}, existing_photo={existing_photo}, final_photo={final_photo}")
        print(f"[PROFILE UPDATE] provided_logo={brokerage_logo}, existing_logo={existing_logo}, final_logo={final_logo}")
        
        # Update existing profile
        query = """
            UPDATE user_profiles SET
                role = ?,
                referral_code = COALESCE(referral_code, ?),
                professional_photo = ?,
                brokerage_logo = ?,
                team_name = ?,
                brokerage_name = ?,
                website_url = ?,
                facebook_url = ?,
                instagram_url = ?,
                linkedin_url = ?,
                twitter_url = ?,
                youtube_url = ?,
                phone = ?,
                call_button_enabled = ?,
                schedule_button_enabled = ?,
                schedule_url = ?,
                application_url = ?,
                bio = ?,
                specialties = ?,
                years_experience = ?,
                languages = ?,
                service_areas = ?,
                nmls_number = ?,
                license_number = ?,
                company_address = ?,
                company_city = ?,
                company_state = ?,
                company_zip = ?,
                homebot_widget_id = ?,
                va_rate_30yr = COALESCE(?, va_rate_30yr),
                fha_rate_30yr = COALESCE(?, fha_rate_30yr),
                conventional_rate_30yr = COALESCE(?, conventional_rate_30yr),
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
        """
        cur.execute(query, (
            role, referral_code, final_photo, final_logo, team_name, brokerage_name,
            website_url, facebook_url, instagram_url, linkedin_url, twitter_url,
            youtube_url, phone, call_button_enabled, schedule_button_enabled,
            schedule_url, application_url, bio, specialties, years_experience, languages,
            service_areas, nmls_number, license_number, company_address,
            company_city, company_state, company_zip, homebot_widget_id,
            va_rate_30yr, fha_rate_30yr, conventional_rate_30yr, user_id
        ))
        profile_id = existing[0]
    else:
        # Generate referral code for new profile
        from database import generate_referral_code
        referral_code = generate_referral_code(user_id, role)
        
        # Create new profile
        query = """
            INSERT INTO user_profiles (
                user_id, role, referral_code, professional_photo, brokerage_logo, team_name,
                brokerage_name, website_url, facebook_url, instagram_url,
                linkedin_url, twitter_url, youtube_url, phone,
                call_button_enabled, schedule_button_enabled, schedule_url, application_url,
                bio, specialties, years_experience, languages, service_areas,
                nmls_number, license_number, company_address, company_city,
                company_state, company_zip, homebot_widget_id, va_rate_30yr, fha_rate_30yr, conventional_rate_30yr
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        cur.execute(query, (
            user_id, role, referral_code, professional_photo, brokerage_logo, team_name,
            brokerage_name, website_url, facebook_url, instagram_url,
            linkedin_url, twitter_url, youtube_url, phone,
            call_button_enabled, schedule_button_enabled, schedule_url, application_url,
            bio, specialties, years_experience, languages, service_areas,
            nmls_number, license_number, company_address, company_city,
            company_state, company_zip, homebot_widget_id, va_rate_30yr, fha_rate_30yr, conventional_rate_30yr
        ))
        profile_id = cur.lastrowid
    
    conn.commit()
    conn.close()
    return profile_id


def get_homebot_widget_id(user_id: int) -> Optional[str]:
    """Get Homebot widget ID for a user (agent or lender)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT homebot_widget_id FROM user_profiles WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    if row and row[0]:
        return row[0]
    return None


def update_homebot_widget_id(user_id: int, widget_id: Optional[str]) -> None:
    """Update Homebot widget ID for a user."""
    conn = get_connection()
    cur = conn.cursor()
    # Ensure profile exists
    cur.execute("SELECT id FROM user_profiles WHERE user_id = ?", (user_id,))
    if not cur.fetchone():
        # Create minimal profile if it doesn't exist
        from database import get_user_by_id
        user = get_user_by_id(user_id)
        if user:
            role = user.get("role", "agent")
            cur.execute("""
                INSERT INTO user_profiles (user_id, role) VALUES (?, ?)
            """, (user_id, role))
    # Update widget ID
    cur.execute("""
        UPDATE user_profiles SET homebot_widget_id = ? WHERE user_id = ?
    """, (widget_id, user_id))
    conn.commit()
    conn.close()


def generate_referral_code(user_id: int, role: str) -> str:
    """Generate a unique referral code for an agent or lender."""
    import secrets
    import string
    
    # Create a code like "AGENT-ABC123" or "LENDER-XYZ789"
    prefix = "AGENT" if role == "agent" else "LENDER"
    code_length = 6
    alphabet = string.ascii_uppercase + string.digits
    
    # Check if referral_code column exists
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(user_profiles)")
    columns = [row[1] for row in cur.fetchall()]
    has_referral_code = 'referral_code' in columns
    conn.close()
    
    # Try up to 10 times to get a unique code
    for _ in range(10):
        random_part = ''.join(secrets.choice(alphabet) for _ in range(code_length))
        code = f"{prefix}-{random_part}"
        
        if has_referral_code:
            conn = get_connection()
            cur = conn.cursor()
            try:
                cur.execute("SELECT id FROM user_profiles WHERE referral_code = ?", (code,))
                if not cur.fetchone():
                    conn.close()
                    return code
            except Exception:
                # Column might not exist yet, just use this code
                conn.close()
                return code
            conn.close()
        else:
            # Column doesn't exist, just return the code
            return code
    
    # Fallback: use user_id if all random codes are taken (unlikely)
    return f"{prefix}-{user_id:06d}"


def get_or_create_referral_code(user_id: int, role: str) -> str:
    """Get existing referral code or create a new one."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Check if referral_code column exists
        cur.execute("PRAGMA table_info(user_profiles)")
        columns = [row[1] for row in cur.fetchall()]
        has_referral_code = 'referral_code' in columns
        
        # If column exists, try to get existing code
        if has_referral_code:
            cur.execute("SELECT referral_code FROM user_profiles WHERE user_id = ?", (user_id,))
            row = cur.fetchone()
            if row and row[0]:
                conn.close()
                return row[0]
        
        # Check if profile exists
        cur.execute("SELECT id FROM user_profiles WHERE user_id = ?", (user_id,))
        profile_exists = cur.fetchone()
        
        # Generate new code
        code = generate_referral_code(user_id, role)
        
        # Ensure column exists before proceeding
        if not has_referral_code:
            try:
                cur.execute("ALTER TABLE user_profiles ADD COLUMN referral_code TEXT")
                cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_user_profiles_referral_code ON user_profiles(referral_code) WHERE referral_code IS NOT NULL")
                has_referral_code = True
            except Exception as e:
                # Column might already exist from concurrent request
                print(f"Note: Could not add referral_code column (may already exist): {e}")
                # Check again
                cur.execute("PRAGMA table_info(user_profiles)")
                columns = [row[1] for row in cur.fetchall()]
                has_referral_code = 'referral_code' in columns
        
        if profile_exists:
            # Update existing profile
            if has_referral_code:
                cur.execute("UPDATE user_profiles SET referral_code = ? WHERE user_id = ?", (code, user_id))
            else:
                raise Exception("Could not add referral_code column to existing profile")
        else:
            # Create new profile
            if has_referral_code:
                cur.execute("""
                    INSERT INTO user_profiles (user_id, role, referral_code)
                    VALUES (?, ?, ?)
                """, (user_id, role, code))
            else:
                # Create without referral_code first, then update
                cur.execute("""
                    INSERT INTO user_profiles (user_id, role)
                    VALUES (?, ?)
                """, (user_id, role))
                if has_referral_code:
                    cur.execute("UPDATE user_profiles SET referral_code = ? WHERE user_id = ?", (code, user_id))
        
        conn.commit()
        conn.close()
        return code
    except Exception as e:
        import traceback
        print(f"Error in get_or_create_referral_code: {traceback.format_exc()}")
        # Return a fallback code if everything fails
        return f"{role[:1].upper()}-{user_id:06d}"


def get_professional_by_referral_code(referral_code: str) -> Optional[sqlite3.Row]:
    """Get professional (agent or lender) by their referral code."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if referral_code column exists
    cur.execute("PRAGMA table_info(user_profiles)")
    columns = [row[1] for row in cur.fetchall()]
    has_referral_code = 'referral_code' in columns
    
    if not has_referral_code:
        conn.close()
        return None
    
    cur.execute("""
        SELECT up.*, u.name, u.email, u.id as user_id
        FROM user_profiles up
        JOIN users u ON up.user_id = u.id
        WHERE up.referral_code = ?
    """, (referral_code,))
    row = cur.fetchone()
    conn.close()
    return row


def create_client_relationship(
    homeowner_id: int,
    professional_id: int,
    professional_role: str,
    referral_code: Optional[str] = None
) -> int:
    """Create a relationship between a homeowner and a professional."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check table structure to use correct column names
    cur.execute("PRAGMA table_info(client_relationships)")
    columns = [row[1] for row in cur.fetchall()]
    homeowner_col = 'homeowner_id' if 'homeowner_id' in columns else 'client_id'
    role_col = 'professional_role' if 'professional_role' in columns else 'professional_type'
    
    # Check if relationship already exists
    cur.execute(f"""
        SELECT id FROM client_relationships
        WHERE {homeowner_col} = ? AND professional_id = ? AND {role_col} = ?
    """, (homeowner_id, professional_id, professional_role))
    existing = cur.fetchone()
    
    if existing:
        # Update existing relationship to active
        cur.execute(f"""
            UPDATE client_relationships
            SET status = 'active', referral_code = COALESCE(?, referral_code)
            WHERE id = ?
        """, (referral_code, existing[0]))
        relationship_id = existing[0]
    else:
        # Create new relationship using the correct column names
        if homeowner_col == 'homeowner_id':
            cur.execute("""
                INSERT INTO client_relationships (homeowner_id, professional_id, professional_role, referral_code)
                VALUES (?, ?, ?, ?)
            """, (homeowner_id, professional_id, professional_role, referral_code))
        else:
            cur.execute("""
                INSERT INTO client_relationships (client_id, professional_id, professional_type, referral_code)
                VALUES (?, ?, ?, ?)
            """, (homeowner_id, professional_id, professional_role, referral_code))
        relationship_id = cur.lastrowid
    
    conn.commit()
    conn.close()
    return relationship_id


def get_homeowner_professionals(homeowner_id: int) -> List[sqlite3.Row]:
    """Get all professionals (agents and lenders) associated with a homeowner."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if homeowner_id column exists, otherwise use client_id
    cur.execute("PRAGMA table_info(client_relationships)")
    columns = [row[1] for row in cur.fetchall()]
    homeowner_col = 'homeowner_id' if 'homeowner_id' in columns else 'client_id'
    role_col = 'professional_role' if 'professional_role' in columns else 'professional_type'
    
    cur.execute(f"""
        SELECT cr.*, 
               u.name, u.email, u.id as user_id,
               up.professional_photo, up.brokerage_logo, up.brokerage_name,
               up.phone, up.call_button_enabled, up.schedule_button_enabled, up.schedule_url,
               up.team_name, up.website_url, up.bio, up.specialties,
               cr.{role_col} as professional_role
        FROM client_relationships cr
        JOIN users u ON cr.professional_id = u.id
        LEFT JOIN user_profiles up ON cr.professional_id = up.user_id
        WHERE cr.{homeowner_col} = ? AND cr.status = 'active'
        ORDER BY cr.created_at DESC
    """, (homeowner_id,))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_referral_stats(professional_id: int) -> Dict[str, Any]:
    """Get referral statistics for a professional."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check table structure to use correct column names
    cur.execute("PRAGMA table_info(client_relationships)")
    columns = [row[1] for row in cur.fetchall()]
    homeowner_col = 'homeowner_id' if 'homeowner_id' in columns else 'client_id'
    
    # Get total clients
    cur.execute(f"""
        SELECT COUNT(*) FROM client_relationships
        WHERE professional_id = ? AND status = 'active'
    """, (professional_id,))
    total_row = cur.fetchone()
    total_clients = total_row[0] if total_row else 0
    
    # Get clients this month
    cur.execute(f"""
        SELECT COUNT(*) FROM client_relationships
        WHERE professional_id = ? AND status = 'active'
        AND strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')
    """, (professional_id,))
    month_row = cur.fetchone()
    clients_this_month = month_row[0] if month_row else 0
    
    # Get referral code - check if column exists first
    referral_code = None
    try:
        cur.execute("PRAGMA table_info(user_profiles)")
        profile_columns = [row[1] for row in cur.fetchall()]
        if 'referral_code' in profile_columns:
            cur.execute("""
                SELECT referral_code FROM user_profiles WHERE user_id = ?
            """, (professional_id,))
            ref_row = cur.fetchone()
            referral_code = ref_row[0] if ref_row and ref_row[0] else None
    except Exception as e:
        print(f"Warning: Could not get referral code: {e}")
    
    conn.close()
    
    return {
        'total_clients': total_clients,
        'clients_this_month': clients_this_month,
        'referral_code': referral_code
    }


# =========================
# REFERRAL LINKS MANAGEMENT
# =========================

def create_referral_link(agent_id: Optional[int] = None, lender_id: Optional[int] = None) -> str:
    """
    Create a new referral link for an agent, lender, or both.
    Returns the token that should be used in the URL.
    """
    import secrets
    import string
    
    if not agent_id and not lender_id:
        raise ValueError("At least one of agent_id or lender_id must be provided")
    
    # Generate a secure random token
    alphabet = string.ascii_letters + string.digits
    token = ''.join(secrets.choice(alphabet) for _ in range(16))
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Ensure token is unique
    while True:
        cur.execute("SELECT id FROM referral_links WHERE token = ?", (token,))
        if not cur.fetchone():
            break
        token = ''.join(secrets.choice(alphabet) for _ in range(16))
    
    cur.execute(
        """INSERT INTO referral_links (token, agent_id, lender_id, is_active)
           VALUES (?, ?, ?, 1)""",
        (token, agent_id, lender_id)
    )
    conn.commit()
    conn.close()
    return token


def get_referral_link_by_token(token: str) -> Optional[sqlite3.Row]:
    """Get a referral link by its token. Returns None if not found or inactive."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM referral_links 
           WHERE token = ? AND is_active = 1""",
        (token,)
    )
    row = cur.fetchone()
    conn.close()
    return row


def get_referral_links_for_agent(agent_id: int) -> List[sqlite3.Row]:
    """Get all active referral links for an agent."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM referral_links 
           WHERE agent_id = ? AND is_active = 1
           ORDER BY created_at DESC""",
        (agent_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_referral_links_for_lender(lender_id: int) -> List[sqlite3.Row]:
    """Get all active referral links for a lender."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT * FROM referral_links 
           WHERE lender_id = ? AND is_active = 1
           ORDER BY created_at DESC""",
        (lender_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def deactivate_referral_link(token: str) -> bool:
    """Deactivate a referral link. Returns True if successful."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """UPDATE referral_links SET is_active = 0, updated_at = CURRENT_TIMESTAMP
           WHERE token = ?""",
        (token,)
    )
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


# =========================
# SPOTLIGHT CARD SETS
# =========================

def save_spotlight_card_set(agent_user_id: int, transaction_id: Optional[int], set_name: str, 
                            property_address: str, features: List[Dict[str, str]]) -> int:
    """Save a new spotlight card set."""
    conn = get_connection()
    cur = conn.cursor()
    
    features_json = json.dumps(features)
    
    cur.execute(
        """INSERT INTO spotlight_card_sets 
           (agent_user_id, transaction_id, set_name, property_address, features_json)
           VALUES (?, ?, ?, ?, ?)""",
        (agent_user_id, transaction_id, set_name, property_address, features_json)
    )
    
    set_id = cur.lastrowid
    conn.commit()
    conn.close()
    return set_id


def get_spotlight_card_sets(agent_user_id: int, transaction_id: Optional[int] = None) -> List[Dict[str, Any]]:
    """Get all spotlight card sets for an agent, optionally filtered by transaction."""
    conn = get_connection()
    cur = conn.cursor()
    
    if transaction_id:
        cur.execute(
            """SELECT * FROM spotlight_card_sets 
               WHERE agent_user_id = ? AND transaction_id = ?
               ORDER BY updated_at DESC""",
            (agent_user_id, transaction_id)
        )
    else:
        cur.execute(
            """SELECT * FROM spotlight_card_sets 
               WHERE agent_user_id = ?
               ORDER BY updated_at DESC""",
            (agent_user_id,)
        )
    
    rows = cur.fetchall()
    conn.close()
    
    result = []
    for row in rows:
        result.append({
            'id': row['id'],
            'transaction_id': row['transaction_id'],
            'set_name': row['set_name'],
            'property_address': row['property_address'],
            'features': json.loads(row['features_json']),
            'created_at': row['created_at'],
            'updated_at': row['updated_at']
        })
    
    return result


def get_spotlight_card_set(set_id: int, agent_user_id: int) -> Optional[Dict[str, Any]]:
    """Get a specific spotlight card set."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """SELECT * FROM spotlight_card_sets 
           WHERE id = ? AND agent_user_id = ?""",
        (set_id, agent_user_id)
    )
    
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        'id': row['id'],
        'transaction_id': row['transaction_id'],
        'set_name': row['set_name'],
        'property_address': row['property_address'],
        'features': json.loads(row['features_json']),
        'created_at': row['created_at'],
        'updated_at': row['updated_at']
    }


def update_spotlight_card_set(set_id: int, agent_user_id: int, set_name: str, 
                              property_address: str, features: List[Dict[str, str]]) -> bool:
    """Update an existing spotlight card set."""
    conn = get_connection()
    cur = conn.cursor()
    
    features_json = json.dumps(features)
    
    cur.execute(
        """UPDATE spotlight_card_sets 
           SET set_name = ?, property_address = ?, features_json = ?, updated_at = CURRENT_TIMESTAMP
           WHERE id = ? AND agent_user_id = ?""",
        (set_name, property_address, features_json, set_id, agent_user_id)
    )
    
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


def delete_spotlight_card_set(set_id: int, agent_user_id: int) -> bool:
    """Delete a spotlight card set."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """DELETE FROM spotlight_card_sets 
           WHERE id = ? AND agent_user_id = ?""",
        (set_id, agent_user_id)
    )
    
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


# =========================
# ACCESS CONTROL
# =========================

def can_access_homeowner(current_user_id: int, current_user_role: str, homeowner_id: int) -> bool:
    """
    Check if a user can access a homeowner's data.
    - Homeowners can only access their own data
    - Agents can only access homeowners where homeowner.agent_id = agent.id
    - Lenders can only access homeowners where homeowner.lender_id = lender.id
    """
    if current_user_role == 'homeowner':
        return current_user_id == homeowner_id
    
    if current_user_role == 'agent':
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM users WHERE id = ? AND agent_id = ?",
            (homeowner_id, current_user_id)
        )
        can_access = cur.fetchone() is not None
        conn.close()
        return can_access
    
    if current_user_role == 'lender':
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM users WHERE id = ? AND lender_id = ?",
            (homeowner_id, current_user_id)
        )
        can_access = cur.fetchone() is not None
        conn.close()
        return can_access
    
    return False


def get_accessible_homeowners(user_id: int, user_role: str) -> List[int]:
    """
    Get list of homeowner IDs that a user can access.
    Returns empty list for homeowners (they only access themselves).
    """
    if user_role == 'homeowner':
        return [user_id]
    
    conn = get_connection()
    cur = conn.cursor()
    
    if user_role == 'agent':
        cur.execute("SELECT id FROM users WHERE role = 'homeowner' AND agent_id = ?", (user_id,))
    elif user_role == 'lender':
        cur.execute("SELECT id FROM users WHERE role = 'homeowner' AND lender_id = ?", (user_id,))
    else:
        conn.close()
        return []
    
    homeowner_ids = [row[0] for row in cur.fetchall()]
    conn.close()
    return homeowner_ids


# =========================
# TRUSTED VENDORS MANAGEMENT
# =========================

def create_trusted_vendor(
    agent_id: int,
    name: str,
    category: str,
    contact_name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    website: Optional[str] = None,
    address: Optional[str] = None,
    notes: Optional[str] = None
) -> int:
    """Create a new trusted vendor for an agent."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO trusted_vendors 
           (agent_id, name, category, contact_name, phone, email, website, address, notes)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (agent_id, name, category, contact_name, phone, email, website, address, notes)
    )
    vendor_id = cur.lastrowid
    conn.commit()
    conn.close()
    return vendor_id


def get_trusted_vendors(agent_id: int, category: Optional[str] = None) -> List[sqlite3.Row]:
    """Get all trusted vendors for an agent, optionally filtered by category."""
    conn = get_connection()
    cur = conn.cursor()
    if category:
        cur.execute(
            """SELECT * FROM trusted_vendors 
               WHERE agent_id = ? AND category = ? AND is_active = 1
               ORDER BY name ASC""",
            (agent_id, category)
        )
    else:
        cur.execute(
            """SELECT * FROM trusted_vendors 
               WHERE agent_id = ? AND is_active = 1
               ORDER BY category ASC, name ASC""",
            (agent_id,)
        )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_trusted_vendor_by_id(vendor_id: int) -> Optional[sqlite3.Row]:
    """Get a specific trusted vendor by ID."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM trusted_vendors WHERE id = ?", (vendor_id,))
    row = cur.fetchone()
    conn.close()
    return row


def update_trusted_vendor(
    vendor_id: int,
    name: Optional[str] = None,
    category: Optional[str] = None,
    contact_name: Optional[str] = None,
    phone: Optional[str] = None,
    email: Optional[str] = None,
    website: Optional[str] = None,
    address: Optional[str] = None,
    notes: Optional[str] = None
) -> bool:
    """Update a trusted vendor. Returns True if successful."""
    conn = get_connection()
    cur = conn.cursor()
    
    updates = []
    params = []
    
    if name is not None:
        updates.append("name = ?")
        params.append(name)
    if category is not None:
        updates.append("category = ?")
        params.append(category)
    if contact_name is not None:
        updates.append("contact_name = ?")
        params.append(contact_name)
    if phone is not None:
        updates.append("phone = ?")
        params.append(phone)
    if email is not None:
        updates.append("email = ?")
        params.append(email)
    if website is not None:
        updates.append("website = ?")
        params.append(website)
    if address is not None:
        updates.append("address = ?")
        params.append(address)
    if notes is not None:
        updates.append("notes = ?")
        params.append(notes)
    
    if not updates:
        conn.close()
        return False
    
    updates.append("updated_at = CURRENT_TIMESTAMP")
    params.append(vendor_id)
    
    cur.execute(
        f"UPDATE trusted_vendors SET {', '.join(updates)} WHERE id = ?",
        params
    )
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


def delete_trusted_vendor(vendor_id: int) -> bool:
    """Soft delete a trusted vendor (set is_active = 0). Returns True if successful."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE trusted_vendors SET is_active = 0, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (vendor_id,)
    )
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


def link_vendor_to_transaction(transaction_id: int, vendor_id: int) -> bool:
    """Link a trusted vendor to a transaction. Returns True if successful."""
    conn = get_connection()
    cur = conn.cursor()
    try:
        cur.execute(
            "INSERT INTO transaction_vendors (transaction_id, vendor_id) VALUES (?, ?)",
            (transaction_id, vendor_id)
        )
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        # Already linked
        conn.close()
        return False


def get_transaction_vendors(transaction_id: int) -> List[sqlite3.Row]:
    """Get all vendors linked to a transaction."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """SELECT tv.* FROM trusted_vendors tv
           JOIN transaction_vendors txv ON tv.id = txv.vendor_id
           WHERE txv.transaction_id = ? AND tv.is_active = 1
           ORDER BY tv.name ASC""",
        (transaction_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def unlink_vendor_from_transaction(transaction_id: int, vendor_id: int) -> bool:
    """Unlink a vendor from a transaction. Returns True if successful."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM transaction_vendors WHERE transaction_id = ? AND vendor_id = ?",
        (transaction_id, vendor_id)
    )
    success = cur.rowcount > 0
    conn.commit()
    conn.close()
    return success


# =========================
# DEFAULT AGENT MANAGEMENT
# =========================

def get_or_create_default_agent() -> int:
    """
    Get or create the default agent (Kayleigh Biggs).
    Returns the user_id of the default agent.
    """
    DEFAULT_AGENT_EMAIL = "kayleighsellskcre@gmail.com"
    DEFAULT_AGENT_NAME = "Kayleigh Biggs"
    DEFAULT_BROKERAGE = "Worth Clark Realty"
    DEFAULT_TEAM = "KC Hometown Team"
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Try to find existing agent by email
    cur.execute("SELECT id FROM users WHERE email = ? AND role = 'agent'", (DEFAULT_AGENT_EMAIL,))
    existing = cur.fetchone()
    
    if existing:
        agent_id = existing[0]
        conn.close()
        return agent_id
    
    # Create default agent user
    from werkzeug.security import generate_password_hash
    import secrets
    import string
    
    # Generate a random password (agent will need to reset it)
    password = ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(16))
    password_hash = generate_password_hash(password)
    
    cur.execute(
        "INSERT INTO users (name, email, password_hash, role) VALUES (?, ?, ?, ?)",
        (DEFAULT_AGENT_NAME, DEFAULT_AGENT_EMAIL, password_hash, "agent")
    )
    agent_id = cur.lastrowid
    
    # Create user profile for the agent
    try:
        cur.execute("""
            INSERT INTO user_profiles (user_id, role, brokerage_name, team_name)
            VALUES (?, ?, ?, ?)
        """, (agent_id, "agent", DEFAULT_BROKERAGE, DEFAULT_TEAM))
    except Exception as e:
        print(f"Note: Could not create default agent profile: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"Created default agent: {DEFAULT_AGENT_NAME} (ID: {agent_id})")
    return agent_id
