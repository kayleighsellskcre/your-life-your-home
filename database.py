import sqlite3
import json
from pathlib import Path
from typing import Optional, Dict, Any, List

DB_PATH = Path(__file__).parent / "ylh.db"


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
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
            role TEXT CHECK(role IN ('homeowner','agent','lender')) NOT NULL
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
            photos TEXT,                -- stored JSON list
            files TEXT,                 -- stored JSON list
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ------------- HOMEOWNER DOCUMENTS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            file_name TEXT,
            category TEXT,
            project_name TEXT,          -- allows board linking later
            r2_key TEXT,                -- Cloudflare R2 object key
            r2_url TEXT,                -- Public URL if available
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )
    
    # Add r2_key and r2_url columns if they don't exist (migration)
    try:
        cur.execute("ALTER TABLE homeowner_documents ADD COLUMN r2_key TEXT")
    except:
        pass  # Column already exists
    try:
        cur.execute("ALTER TABLE homeowner_documents ADD COLUMN r2_url TEXT")
    except:
        pass  # Column already exists

    # ------------- HOMEOWNER PROJECTS -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_projects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            name TEXT,
            budget REAL,
            status TEXT,
            notes TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ------------- NEXT MOVE PLAN -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_next_move_plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            timeline TEXT,
            budget TEXT,
            preapproved TEXT,
            areas TEXT,
            home_type TEXT,
            beds_baths TEXT,
            must_haves TEXT,
            dealbreakers TEXT,
            condition TEXT,
            feeling TEXT,
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
            status TEXT DEFAULT 'open',
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
            FOREIGN KEY (agent_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

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
            FOREIGN KEY (lender_user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

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

    # ------------- SIMPLE SAVED NOTES (brain dump) -------------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS homeowner_simple_notes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            title TEXT,
            body TEXT,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
        """
    )

    # ------------------ MIGRATIONS FOR EXISTING DBs ------------------
    # Older DBs may not include the `project_name`, `photos`, or `files`
    # columns on the `homeowner_notes` table; ensure they exist so code
    # relying on those columns does not fail with "no such column".
    try:
        cur.execute("PRAGMA table_info(homeowner_notes)")
        existing = [row[1] for row in cur.fetchall()]
        # add missing columns safely
        if "project_name" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN project_name TEXT")
        if "photos" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN photos TEXT")
        if "files" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN files TEXT")
        # Some older DBs used `body` instead of `details` for note text.
        if "details" not in existing and "body" in existing:
            # add a `details` column and copy `body` contents into it
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN details TEXT")
            cur.execute("UPDATE homeowner_notes SET details = body WHERE details IS NULL OR details = ''")
        elif "details" not in existing:
            # ensure details exists even if body wasn't present
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN details TEXT")
        # Premium mood board features
        if "color_palette" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN color_palette TEXT")  # JSON list of hex codes
        if "board_template" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN board_template TEXT")  # 'collage', 'grid', 'editorial'
        if "label_style" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN label_style TEXT")  # 'handwritten', 'sans-serif'
        if "is_private" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN is_private INTEGER DEFAULT 0")
        if "shareable_link" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN shareable_link TEXT")
        if "vision_statement" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN vision_statement TEXT")
        if "product_sources" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN product_sources TEXT")  # JSON list
        if "show_notes_panel" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN show_notes_panel INTEGER DEFAULT 1")
        if "fixtures" not in existing:
            cur.execute("ALTER TABLE homeowner_notes ADD COLUMN fixtures TEXT")  # JSON list of fixture images with positioning
    except Exception:
        # If the table doesn't exist yet or PRAGMA fails, ignore and proceed.
        pass

    conn.commit()
    conn.close()


# =========================
# USERS
# =========================


def create_user(name: str, email: str, password_hash: str, role: str) -> int:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO users (name, email, password_hash, role)
        VALUES (?, ?, ?, ?)
        """,
        (name, email.lower().strip(), password_hash, role),
    )
    conn.commit()
    user_id = cur.lastrowid
    conn.close()
    return user_id


def get_user_by_email(email: str) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM users WHERE email = ?",
        (email.lower().strip(),),
    )
    row = cur.fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return row


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
        value_estimate = value_estimate if value_estimate is not None else existing.get('value_estimate')
        loan_balance = loan_balance if loan_balance is not None else existing.get('loan_balance')
        loan_rate = loan_rate if loan_rate is not None else existing.get('loan_rate')
        loan_payment = loan_payment if loan_payment is not None else existing.get('loan_payment')
        loan_term_years = loan_term_years if loan_term_years is not None else existing.get('loan_term_years')
        loan_start_date = loan_start_date if loan_start_date is not None else existing.get('loan_start_date')
    
    # Calculate equity if both value and balance are available
    equity_estimate = None
    if value_estimate and loan_balance:
        equity_estimate = value_estimate - loan_balance
    elif existing:
        equity_estimate = existing.get('equity_estimate')
    
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
        (user_id, value_estimate, equity_estimate, loan_rate, loan_payment, 
         loan_balance, loan_term_years, loan_start_date),
    )
    conn.commit()
    conn.close()


# =========================
# HOMEOWNER NOTES / DOCS / PROJECTS / PLANS
# =========================


def add_homeowner_note(
    user_id: int,
    project_name: str,
    title: str,
    tags: str,
    details: str,
    links: str = "",
    photos_json: str = "[]",
    files_json: str = "[]",
) -> None:
    """
    Insert a new design-board style note.
    photos_json and files_json should be JSON strings (lists).
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_notes (
            user_id, project_name, title, tags, details, links, photos, files
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            project_name,
            title,
            tags,
            details,
            links,
            photos_json,
            files_json,
        ),
    )
    conn.commit()
    conn.close()


def list_homeowner_notes(user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id,
            created_at,
            project_name,
            title,
            tags,
            details,
            links,
            photos,
            files
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
    filename: str,
    category: str,
    project_name: str = "",
    r2_key: str = None,
    r2_url: str = None,
) -> None:
    """
    Store a document record. filename is saved into the filename column.
    r2_key and r2_url store Cloudflare R2 information if available.
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_documents (user_id, filename, category, r2_key, r2_url)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, filename, category, r2_key, r2_url),
    )
    conn.commit()
    conn.close()


def list_homeowner_documents(user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
            id,
            created_at,
            filename,
            category,
            r2_key,
            r2_url
        FROM homeowner_documents
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def add_homeowner_project(
    user_id: int,
    name: str,
    budget: Optional[float],
    status: str,
    notes: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_projects (user_id, name, budget, status, notes)
        VALUES (?, ?, ?, ?, ?)
        """,
        (user_id, name, budget, status, notes),
    )
    conn.commit()
    conn.close()


def list_homeowner_projects(user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, name, budget, status, notes
        FROM homeowner_projects
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def upsert_next_move_plan(
    user_id: int,
    timeline: str,
    budget: str,
    preapproved: str,
    areas: str,
    home_type: str,
    beds_baths: str,
    must_haves: str,
    dealbreakers: str,
    condition: str,
    feeling: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_next_move_plans (
            user_id, timeline, budget, preapproved, areas, home_type,
            beds_baths, must_haves, dealbreakers, condition, feeling
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            timeline     = excluded.timeline,
            budget       = excluded.budget,
            preapproved  = excluded.preapproved,
            areas        = excluded.areas,
            home_type    = excluded.home_type,
            beds_baths   = excluded.beds_baths,
            must_haves   = excluded.must_haves,
            dealbreakers = excluded.dealbreakers,
            condition    = excluded.condition,
            feeling      = excluded.feeling,
            updated_at   = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            timeline,
            budget,
            preapproved,
            areas,
            home_type,
            beds_baths,
            must_haves,
            dealbreakers,
            condition,
            feeling,
        ),
    )
    conn.commit()
    conn.close()


def get_next_move_plan(user_id: int) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT * FROM homeowner_next_move_plans WHERE user_id = ?",
        (user_id,),
    )
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
# AGENT CRM / TRANSACTIONS
# =========================


def add_agent_contact(
    agent_user_id: int,
    name: str,
    email: str,
    phone: str,
    stage: str,
    best_contact: str,
    last_touch: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO agent_contacts (
            agent_user_id, name, email, phone, stage, best_contact, last_touch
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (agent_user_id, name, email, phone, stage, best_contact, last_touch),
    )
    conn.commit()
    conn.close()


def list_agent_contacts(agent_user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, name, email, phone, stage, best_contact, last_touch
        FROM agent_contacts
        WHERE agent_user_id = ?
        ORDER BY created_at DESC
        """,
        (agent_user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


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
    status: str,
    loan_type: str,
    target_payment: str,
    last_touch: str,
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO lender_borrowers (
            lender_user_id, name, status, loan_type, target_payment, last_touch
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (lender_user_id, name, status, loan_type, target_payment, last_touch),
    )
    conn.commit()
    conn.close()


def list_lender_borrowers(lender_user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, name, status, loan_type, target_payment, last_touch
        FROM lender_borrowers
        WHERE lender_user_id = ?
        ORDER BY created_at DESC
        """,
        (lender_user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


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
            lender_user_id, borrower_name, status, loan_type,
            target_payment, stage, close_date
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
        SELECT id, created_at, borrower_name, status, loan_type,
               target_payment, stage, close_date
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
            SELECT *
            FROM message_templates
            WHERE role = ?
              AND (owner_user_id IS NULL OR owner_user_id = ?)
            ORDER BY created_at DESC
            """,
            (role, owner_user_id),
        )
    else:
        cur.execute(
            """
            SELECT *
            FROM message_templates
            WHERE role = ?
              AND owner_user_id IS NULL
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
            SELECT *
            FROM marketing_templates
            WHERE role = ?
              AND (owner_user_id IS NULL OR owner_user_id = ?)
            ORDER BY created_at DESC
            """,
            (role, owner_user_id),
        )
    else:
        cur.execute(
            """
            SELECT *
            FROM marketing_templates
            WHERE role = ?
              AND owner_user_id IS NULL
            ORDER BY created_at DESC
            """,
            (role,),
        )
    rows = cur.fetchall()
    conn.close()
    return rows


# =========================
# DOCUMENT HELPERS
# =========================


def delete_homeowner_document(doc_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM homeowner_documents WHERE id = ?", (doc_id,))
    conn.commit()
    conn.close()


def update_homeowner_document_file(doc_id: int, new_filename: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE homeowner_documents
        SET file_name = ?, created_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (new_filename, doc_id),
    )
    conn.commit()
    conn.close()


def get_homeowner_document_for_user(
    doc_id: int,
    user_id: int,
) -> Optional[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM homeowner_documents
        WHERE id = ? AND user_id = ?
        """,
        (doc_id, user_id),
    )
    row = cur.fetchone()
    conn.close()
    return row


# =========================
# HOMEOWNER TIMELINE EVENTS
# =========================


def add_timeline_event(
    user_id: int,
    event_date: str,
    title: str,
    category: str,
    cost: str,
    notes: str,
    files: List[str],
) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_timeline_events
        (user_id, event_date, title, category, cost, notes, files)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, event_date, title, category, cost, notes, json.dumps(files)),
    )
    conn.commit()
    conn.close()


def list_timeline_events(user_id: int) -> List[sqlite3.Row]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT *
        FROM homeowner_timeline_events
        WHERE user_id = ?
        ORDER BY event_date DESC
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
# SIMPLE SAVED NOTES
# =========================


def add_simple_note(
    user_id: int,
    title: str,
    body: str,
) -> None:
    """Add a new simple note for a homeowner."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_simple_notes (user_id, title, body)
        VALUES (?, ?, ?)
        """,
        (user_id, title, body),
    )
    conn.commit()
    conn.close()


def list_simple_notes(user_id: int) -> List[sqlite3.Row]:
    """Get all simple notes for a user, sorted by most recent first."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, created_at, title, body
        FROM homeowner_simple_notes
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def delete_simple_note(note_id: int, user_id: int) -> None:
    """Delete a simple note (security: verify user_id)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM homeowner_simple_notes WHERE id = ? AND user_id = ?",
        (note_id, user_id),
    )
    conn.commit()
    conn.close()


# =========================
# DESIGN BOARDS (MOOD BOARDS)
# =========================


def add_design_board_note(
    user_id: int,
    project_name: str,
    title: str,
    details: str,
    photos: List[str],
    files: List[str],
    tags: str = "",
    vision_statement: str = "",
    color_palette: List[str] = None,
    board_template: str = "collage",
    label_style: str = "sans-serif",
    is_private: int = 0,
    product_sources: List[str] = None,
    fixtures: List[str] = None,
) -> None:
    """Add a note to a design board project with premium features."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO homeowner_notes
        (user_id, project_name, title, tags, details, photos, files, 
         vision_statement, color_palette, board_template, label_style, 
         is_private, product_sources, fixtures)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            project_name,
            title,
            tags,
            details,
            json.dumps(photos or []),
            json.dumps(files or []),
            vision_statement,
            json.dumps(color_palette or []),
            board_template,
            label_style,
            is_private,
            json.dumps(product_sources or []),
            json.dumps(fixtures or []),
        ),
    )
    conn.commit()
    conn.close()


def get_design_boards_for_user(user_id: int) -> List[str]:
    """Get all unique project names (board titles) for a user."""
    conn = get_connection()
    cur = conn.cursor()
    # Support legacy rows where the board name may have been stored in `title`.
    cur.execute(
        """
        SELECT DISTINCT COALESCE(NULLIF(project_name, ''), NULLIF(title, '')) AS project_name
        FROM homeowner_notes
        WHERE user_id = ? AND (project_name IS NOT NULL OR title IS NOT NULL)
        ORDER BY project_name ASC
        """,
        (user_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return [row[0] for row in rows if row[0]]


def get_design_board_details(user_id: int, project_name: str) -> Dict[str, Any]:
    """Get all notes, photos, and files for a design board with premium features."""
    conn = get_connection()
    cur = conn.cursor()
    # Match rows where the board name is stored in `project_name`, or legacy rows
    # where it was stored in `title`.
    cur.execute(
        """
        SELECT id, created_at, title, details, photos, files, tags, project_name,
               vision_statement, color_palette, board_template, label_style,
               is_private, shareable_link, product_sources, show_notes_panel, fixtures
        FROM homeowner_notes
        WHERE user_id = ? AND (project_name = ? OR title = ?)
        ORDER BY created_at ASC
        """,
        (user_id, project_name, project_name),
    )
    rows = cur.fetchall()
    conn.close()

    if not rows:
        return None

    # Aggregate all photos, files, notes, colors, product sources, fixtures
    all_photos = []
    all_files = []
    all_notes = []
    all_colors = []
    all_product_sources = []
    all_fixtures = []
    first_row = rows[0]

    for row in rows:
        # Parse photos JSON
        photos_json = row["photos"] or "[]"
        try:
            photos = json.loads(photos_json)
            all_photos.extend(photos)
        except Exception:
            pass

        # Parse files JSON
        files_json = row["files"] or "[]"
        try:
            files = json.loads(files_json)
            all_files.extend(files)
        except Exception:
            pass
        
        # Parse color palette JSON
        color_json = row["color_palette"] if "color_palette" in row.keys() else None
        if color_json:
            try:
                colors = json.loads(color_json)
                all_colors.extend(colors)
            except Exception:
                pass
        
        # Parse product sources JSON
        products_json = row["product_sources"] if "product_sources" in row.keys() else None
        if products_json:
            try:
                products = json.loads(products_json)
                all_product_sources.extend(products)
            except Exception:
                pass
        
        # Parse fixtures JSON
        fixtures_json = row["fixtures"] if "fixtures" in row.keys() else None
        if fixtures_json:
            try:
                fixtures = json.loads(fixtures_json)
                all_fixtures.extend(fixtures)
            except Exception:
                pass

        # Collect note info
        all_notes.append(
            {
                "id": row["id"],
                "title": row["title"],
                "details": row["details"],
                "created_at": row["created_at"],
            }
        )

    # Remove duplicate colors
    all_colors = list(dict.fromkeys(all_colors))  # Preserves order

    return {
        "project_name": project_name,
        "tags": first_row["tags"] or "",
        "vision_statement": first_row["vision_statement"] if "vision_statement" in first_row.keys() else "",
        "board_template": first_row["board_template"] if "board_template" in first_row.keys() else "collage",
        "label_style": first_row["label_style"] if "label_style" in first_row.keys() else "sans-serif",
        "is_private": first_row["is_private"] if "is_private" in first_row.keys() else 0,
        "shareable_link": first_row["shareable_link"] if "shareable_link" in first_row.keys() else "",
        "show_notes_panel": first_row["show_notes_panel"] if "show_notes_panel" in first_row.keys() else 1,
        "photos": all_photos,
        "files": all_files,
        "notes": all_notes,
        "color_palette": all_colors,
        "product_sources": all_product_sources,
        "fixtures": all_fixtures,
    }


def delete_design_board(user_id: int, project_name: str) -> None:
    """Delete entire design board (all notes for a project).
    
    Handles both new format (project_name) and legacy format (title) where board
    names might be stored.
    """
    conn = get_connection()
    cur = conn.cursor()
    # Delete rows matching either project_name or title (for backward compatibility)
    cur.execute(
        """DELETE FROM homeowner_notes 
           WHERE user_id = ? AND (project_name = ? OR title = ?)""",
        (user_id, project_name, project_name),
    )
    conn.commit()
    conn.close()


def update_homeowner_note_photos(note_id: int, photos: List[str]) -> None:
    """Update the photos JSON for a specific homeowner_notes row."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE homeowner_notes SET photos = ? WHERE id = ?",
        (json.dumps(photos or []), note_id),
    )
    conn.commit()
    conn.close()


def remove_photos_from_board(user_id: int, project_name: str, photos_to_remove: List[str]) -> None:
    """Remove matching photo paths from all notes in a board (best-effort).

    photos_to_remove should be a list of relative paths (matching what's stored in DB).
    Handles both new format (project_name) and legacy format (title).
    """
    if not photos_to_remove:
        return

    conn = get_connection()
    cur = conn.cursor()
    # Fetch rows matching either project_name or title (for backward compatibility)
    cur.execute(
        """SELECT id, photos FROM homeowner_notes 
           WHERE user_id = ? AND (project_name = ? OR title = ?)""",
        (user_id, project_name, project_name),
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
            # Update only when something changed
            cur.execute(
                "UPDATE homeowner_notes SET photos = ? WHERE id = ?",
                (json.dumps(filtered), note_id),
            )

    conn.commit()
    conn.close()


def remove_fixtures_from_board(user_id: int, project_name: str, fixtures_to_remove: List[str]) -> None:
    """Remove matching fixture paths from all notes in a board (best-effort).

    fixtures_to_remove should be a list of relative paths (matching what's stored in DB).
    Handles both new format (project_name) and legacy format (title).
    """
    if not fixtures_to_remove:
        return

    conn = get_connection()
    cur = conn.cursor()
    # Fetch rows matching either project_name or title (for backward compatibility)
    cur.execute(
        """SELECT id, fixtures FROM homeowner_notes 
           WHERE user_id = ? AND (project_name = ? OR title = ?)""",
        (user_id, project_name, project_name),
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
            # Update only when something changed
            cur.execute(
                "UPDATE homeowner_notes SET fixtures = ? WHERE id = ?",
                (json.dumps(filtered), note_id),
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
                  loan_balance, loan_term_years, loan_start_date
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
) -> None:
    """Insert or update homeowner snapshot for a specific property."""
    conn = get_connection()
    cur = conn.cursor()

    # Get existing data if it exists
    cur.execute(
        """SELECT value_estimate, loan_balance, loan_rate, loan_payment, 
                  loan_term_years, loan_start_date
           FROM homeowner_snapshots
           WHERE user_id = ? AND property_id = ?""",
        (user_id, property_id),
    )
    existing = cur.fetchone()

    # Merge with existing data
    if existing:
        merged_value = value_estimate if value_estimate is not None else existing["value_estimate"]
        merged_loan_balance = loan_balance if loan_balance is not None else existing["loan_balance"]
        merged_loan_rate = loan_rate if loan_rate is not None else existing["loan_rate"]
        merged_loan_payment = loan_payment if loan_payment is not None else existing["loan_payment"]
        merged_loan_term_years = loan_term_years if loan_term_years is not None else existing["loan_term_years"]
        merged_loan_start_date = loan_start_date if loan_start_date is not None else existing["loan_start_date"]
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
        """INSERT INTO homeowner_snapshots 
           (user_id, property_id, value_estimate, equity_estimate, loan_balance, 
            loan_rate, loan_payment, loan_term_years, loan_start_date, updated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
           ON CONFLICT(user_id, property_id) DO UPDATE SET
               value_estimate = excluded.value_estimate,
               equity_estimate = excluded.equity_estimate,
               loan_balance = excluded.loan_balance,
               loan_rate = excluded.loan_rate,
               loan_payment = excluded.loan_payment,
               loan_term_years = excluded.loan_term_years,
               loan_start_date = excluded.loan_start_date,
               updated_at = CURRENT_TIMESTAMP""",
        (user_id, property_id, merged_value, equity, merged_loan_balance, 
         merged_loan_rate, merged_loan_payment, merged_loan_term_years, merged_loan_start_date),
    )
    conn.commit()
    conn.close()

