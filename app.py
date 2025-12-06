import os
import boto3
from functools import wraps
from typing import Optional
from pathlib import Path
from uuid import uuid4
from datetime import datetime
import sqlite3
import json
from types import SimpleNamespace
from PIL import Image, ImageFilter
import numpy as np

# ---------------- R2 STORAGE CLIENT ----------------
R2_CLIENT = None
if all(key in os.environ for key in ["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"]):
    R2_CLIENT = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )

# ---------------- FLASK + SECURITY ----------------
from flask import (
    Flask,
    render_template,
    redirect,
    url_for,
    request,
    session,
    flash,
    abort,
    send_from_directory,
)
from flask import Response
from werkzeug.security import generate_password_hash, check_password_hash  # noqa
from werkzeug.utils import secure_filename

# ---------------- SIMPLE IMAGE PROCESSING (NO BACKGROUND REMOVAL) ----------------
def remove_white_background(image_path):
    """Just convert to PNG format - no background removal."""
    try:
        img = Image.open(image_path)
        
        # Convert to RGB if needed (keep as-is)
        if img.mode not in ('RGB', 'RGBA'):
            img = img.convert('RGB')
        
        # Save as PNG
        img.save(image_path, 'PNG', optimize=True)
        
        print(f"✓ Processed fixture: {Path(image_path).name}")
        
        return True
        
    except Exception as e:
        print(f"✗ Failed: {Path(image_path).name} - {e}")
        return False

# ---------------- YOUR PLATFORM DATABASES ----------------
from database import (
    init_db,
    get_connection,
    create_user,
    get_user_by_email,
    get_user_by_id,
    get_homeowner_snapshot_for_user,
    upsert_homeowner_snapshot,
    upsert_homeowner_snapshot_full,
    add_homeowner_note,
    list_homeowner_notes,
    add_homeowner_document,
    list_homeowner_documents,
    add_homeowner_project,
    list_homeowner_projects,
    upsert_next_move_plan,
    get_next_move_plan,
    add_homeowner_question,
    add_agent_contact,
    list_agent_contacts,
    add_lender_borrower,
    list_lender_borrowers,
    add_agent_transaction,
    list_agent_transactions,
    get_agent_transaction,
    add_lender_loan,
    list_lender_loans,
    add_message_template,
    list_message_templates,
    add_marketing_template,
    list_marketing_templates,
    delete_homeowner_document,
    update_homeowner_document_file,
    get_homeowner_document_for_user,
    add_timeline_event,
    list_timeline_events,
    delete_timeline_event,
    add_simple_note,
    list_simple_notes,
    delete_simple_note,
    add_design_board_note,
    get_design_boards_for_user,
    get_design_board_details,
    delete_design_board,
    update_homeowner_note_photos,
    remove_photos_from_board,
    duplicate_design_board,
    update_board_privacy,
    update_board_colors,
    update_board_template,
    add_property,
    get_user_properties,
    get_property_by_id,
    set_primary_property,
    get_primary_property,
    delete_property,
    get_homeowner_snapshot_for_property,
    upsert_homeowner_snapshot_for_property,
)

# ---------------- R2 STORAGE HELPERS ----------------
from r2_storage import (
    upload_file_to_r2,
    get_file_url_from_r2,
    delete_file_from_r2,
    is_r2_enabled,
)

# ---------------- FLASK APP INIT ----------------

from flask import Flask
app = Flask(__name__)
app.secret_key = os.environ.get("YLH_SECRET_KEY", "change-this-secret-key")
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Initialize DBs so platform loads with no manual trigger
init_db()

# ---------------- JINJA FILTERS ----------------
def _load_json_filter(value):
    try:
        if value is None or value == "":
            return []
        return json.loads(value)
    except Exception:
        return []

app.jinja_env.filters["load_json"] = _load_json_filter

# ---------------- GLOBAL BRAND CONFIG ----------------
FRONT_BRAND_NAME = "Your Life, Your Home"
CLOUD_CMA_URL = os.environ.get(
    "CLOUD_CMA_URL",
    "https://app.cloudcma.com/api_widget/0183b47b7401642c6ec736103095ebbb/show?post_url=https://app.cloudcma.com&source_url=ua",
)

BASE_DIR = Path(__file__).resolve().parent

# Homeowner document storage
HOMEOWNER_DOCS_DIR = BASE_DIR / "static" / "uploads" / "homeowner_docs"
HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)

# Timeline upload storage
UPLOAD_TIMELINE = BASE_DIR / "uploads" / "timeline"
UPLOAD_TIMELINE.mkdir(parents=True, exist_ok=True)


# -------------------------------------------------
# AUTH HELPERS
# -------------------------------------------------
def get_current_user_id() -> int:
    """Fallback to demo user for now."""
    return session.get("user_id") or 1


def login_required(view):
    @wraps(view)
    def wrapper(*a, **kw):
        if not session.get("user_id"):
            flash("Please sign in to access your dashboard.", "error")
            return redirect(url_for("login"))
        return view(*a, **kw)

    return wrapper


def role_required(*roles):
    def decorator(view):
        @wraps(view)
        def wrapper(*a, **kw):
            if not session.get("user_id"):
                flash("Please sign in first.", "error")
                return redirect(url_for("login"))
            if roles and session.get("role") not in roles:
                abort(403)
            return view(*a, **kw)

        return wrapper

    return decorator


def get_current_user() -> Optional[dict]:
    user_id = session.get("user_id")
    if not user_id:
        return None
    row = get_user_by_id(user_id)
    return dict(row) if row else None


# -------------------------------------------------
# ACCESS CONTROL & SUBSCRIPTION HELPERS
# -------------------------------------------------
import secrets
import string

def generate_referral_code(length=8):
    """Generate a unique referral code."""
    chars = string.ascii_uppercase + string.digits
    return ''.join(secrets.choice(chars) for _ in range(length))

def has_active_subscription(user_id: int) -> bool:
    """Check if user has an active subscription (includes trial)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id FROM subscriptions 
        WHERE user_id = ? 
        AND status IN ('active', 'trial')
        AND (end_date IS NULL OR end_date > datetime('now'))
        AND (trial_ends_at IS NULL OR trial_ends_at > datetime('now'))
    """, (user_id,))
    result = cur.fetchone()
    conn.close()
    return result is not None

def subscription_required(view):
    """Decorator to require active subscription for agents/lenders."""
    @wraps(view)
    def wrapper(*a, **kw):
        if not session.get("user_id"):
            flash("Please sign in to access your dashboard.", "error")
            return redirect(url_for("login"))
        
        user = get_current_user()
        role = user.get("role")
        
        # Only agents and lenders need subscriptions
        if role in ["agent", "lender"]:
            if not has_active_subscription(session["user_id"]):
                # Check if user exists but has no subscription - create trial
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("SELECT id FROM subscriptions WHERE user_id = ?", (session["user_id"],))
                if not cur.fetchone():
                    # No subscription exists, create a trial
                    from datetime import timedelta
                    trial_ends = (datetime.now() + timedelta(days=14)).isoformat()
                    cur.execute("""
                        INSERT INTO subscriptions 
                        (user_id, subscription_type, status, start_date, trial_ends_at)
                        VALUES (?, ?, 'trial', datetime('now'), ?)
                    """, (session["user_id"], role, trial_ends))
                    cur.execute("UPDATE users SET has_active_subscription = 1 WHERE id = ?", (session["user_id"],))
                    conn.commit()
                    conn.close()
                    flash("Welcome! You have a 14-day free trial.", "success")
                    return view(*a, **kw)  # Now they have a trial, proceed
                conn.close()
                
                # Still no active subscription
                flash("An active subscription is required to access this feature.", "warning")
                return redirect(url_for("subscription_required_page"))
        
        return view(*a, **kw)
    return wrapper

def get_or_create_referral_code(user_id: int) -> str:
    """Get existing referral code or create new one for user."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if user already has a code
    cur.execute("SELECT referral_code FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    
    if row and row[0]:
        conn.close()
        return row[0]
    
    # Generate new unique code
    while True:
        code = generate_referral_code()
        cur.execute("SELECT id FROM users WHERE referral_code = ?", (code,))
        if not cur.fetchone():
            break
    
    # Save to user
    cur.execute("UPDATE users SET referral_code = ? WHERE id = ?", (code, user_id))
    conn.commit()
    conn.close()
    
    return code

def link_client_to_professional(professional_id: int, professional_type: str, client_email: str, referral_code: str = None):
    """Link a client (homeowner) to an agent or lender."""
    conn = get_connection()
    cur = conn.cursor()
    
    # Check if client exists
    cur.execute("SELECT id FROM users WHERE email = ?", (client_email,))
    client_row = cur.fetchone()
    client_id = client_row[0] if client_row else None
    
    # Create or update relationship
    if not referral_code:
        referral_code = generate_referral_code()
    
    cur.execute("""
        INSERT INTO client_relationships (professional_id, professional_type, client_id, client_email, referral_code, status)
        VALUES (?, ?, ?, ?, ?, 'active')
        ON CONFLICT(referral_code) DO UPDATE SET
            client_id = excluded.client_id,
            client_email = excluded.client_email,
            status = 'active'
    """, (professional_id, professional_type, client_id, client_email, referral_code))
    
    conn.commit()
    conn.close()
    
    return referral_code

def get_client_relationships(professional_id: int):
    """Get all clients for an agent or lender."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            cr.id,
            cr.client_id,
            cr.client_email,
            cr.referral_code,
            cr.status,
            cr.created_at,
            u.name as client_name,
            u.email as client_registered_email
        FROM client_relationships cr
        LEFT JOIN users u ON cr.client_id = u.id
        WHERE cr.professional_id = ?
        ORDER BY cr.created_at DESC
    """, (professional_id,))
    
    rows = cur.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def save_guest_session_data(session_id: str, data: dict, referral_code: str = None):
    """Save guest homeowner session data."""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO guest_sessions (session_id, data, referral_code, last_activity)
        VALUES (?, ?, ?, datetime('now'))
        ON CONFLICT(session_id) DO UPDATE SET
            data = excluded.data,
            last_activity = datetime('now')
    """, (session_id, json.dumps(data), referral_code))
    
    conn.commit()
    conn.close()

def get_guest_session_data(session_id: str):
    """Retrieve guest session data."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT data, referral_code FROM guest_sessions 
        WHERE session_id = ?
    """, (session_id,))
    
    row = cur.fetchone()
    conn.close()
    
    if row:
        return {
            'data': json.loads(row[0]) if row[0] else {},
            'referral_code': row[1]
        }
    return None


# -------------------------------------------------
# SHARED UTILS
# -------------------------------------------------
def json_or_list(value):
    """Convert DB string/json text into a Python list safely."""
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return [ln.strip() for ln in value.splitlines() if ln.strip()]
    return []


def _row_get(row, key, default=None):
    """Safe getter that supports dicts, sqlite rows, objects."""
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        pass
    return getattr(row, key, default)


# -------------------------------------------------
# DESIGN BOARD LOAD
# -------------------------------------------------

# -------------------------------------------------
# HOMEOWNER SNAPSHOT + CRM METRICS
# -------------------------------------------------
def calculate_appreciated_value(initial_value: float, purchase_date: str, annual_rate: float = 0.035) -> float:
    """
    Calculate home value with automatic appreciation over time.
    
    Args:
        initial_value: The original purchase price or last set value
        purchase_date: Date in format 'YYYY-MM-DD' or similar
        annual_rate: Annual appreciation rate (default 3.5% = 0.035)
    
    Returns:
        Appreciated home value
    """
    if not initial_value or not purchase_date:
        return initial_value
    
    try:
        # Parse the purchase date
        if isinstance(purchase_date, str):
            purchase_dt = datetime.strptime(purchase_date.split()[0], '%Y-%m-%d')
        else:
            purchase_dt = purchase_date
        
        # Calculate years elapsed
        today = datetime.now()
        years_elapsed = (today - purchase_dt).days / 365.25
        
        # Apply compound appreciation: Value = Initial * (1 + rate)^years
        appreciated_value = initial_value * ((1 + annual_rate) ** years_elapsed)
        
        return round(appreciated_value, 2)
    except Exception as e:
        print(f"Error calculating appreciation: {e}")
        return initial_value


def get_homeowner_snapshot_or_default(user_row: Optional[dict]):
    if not user_row:
        return {
            "name": "Friend",
            "value_estimate": None,
            "equity_estimate": None,
            "loan_rate": None,
            "loan_payment": None,
            "loan_balance": None,
            "next_steps": [
                "Check home value + equity.",
                "Upload documents to keep things organized.",
                "Plan your Next-Home move anytime.",
            ],
        }
    snap = get_homeowner_snapshot_for_user(user_row["id"])
    if not snap:
        base = get_homeowner_snapshot_or_default(None)
        base["name"] = user_row.get("name", "Friend")
        return base
    
    # Use the exact value from the database without automatic appreciation
    value_estimate = snap["value_estimate"]
    equity_estimate = snap["equity_estimate"]
    
    return {
        "name": user_row.get("name", "Friend"),
        "value_estimate": value_estimate,
        "equity_estimate": equity_estimate,
        "loan_rate": snap["loan_rate"],
        "loan_payment": snap["loan_payment"],
        "loan_balance": snap["loan_balance"],
        "loan_start_date": snap.get("loan_start_date"),
        "last_value_refresh": snap.get("last_value_refresh"),
        "next_steps": [
            "Review equity growth.",
            "Consider refinancing or payment changes.",
            "Use renovation + next-move planners anytime.",
        ],
    }


def get_agent_dashboard_metrics(user_id):
    if not user_id:
        return {
            "new_leads": 0,
            "active_transactions": 0,
            "followups_today": 0,
        }
    contacts = list_agent_contacts(user_id)
    transactions = list_agent_transactions(user_id)
    return {
        "new_leads": sum((c1["stage"] or "") == "new" for c1 in contacts),
        "active_transactions": len(transactions),
        "followups_today": max(len(contacts) // 2, 0),
    }


def get_lender_dashboard_metrics(user_id):
    if not user_id:
        return {
            "new_applications": 0,
            "loans_in_process": 0,
            "nurture_contacts": 0,
        }
    borrowers = list_lender_borrowers(user_id)
    loans = list_lender_loans(user_id)
    return {
        "new_applications": sum(
            (b1["status"] or "") == "preapproval" for b1 in borrowers
        ),
        "loans_in_process": len(loans),
        "nurture_contacts": max(len(borrowers) // 2, 0),
    }


# -------------------------------------------------
# MAIN / AUTH
# -------------------------------------------------
@app.route("/")
def index():
    """
    Landing page with three paths:
    - Homeowner dashboard
    - Agent dashboard
    - Lender dashboard
    """
    return render_template(
        "main/index.html",
        brand_name=FRONT_BRAND_NAME,
        cloud_cma_url=CLOUD_CMA_URL,
    )


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """
    Sign up for any role: homeowner | agent | lender
    (role can be preselected via ?role=agent)
    Converts guest session data to registered account for homeowners.
    """
    role = request.args.get("role", "homeowner")
    prefilled_email = request.args.get("email", "")
    
    if role not in ("homeowner", "agent", "lender"):
        role = "homeowner"

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "")
        role_from_form = request.form.get("role", role)

        if role_from_form in ("homeowner", "agent", "lender"):
            role = role_from_form

        if not email or not password:
            flash("Please fill in email and password.", "error")
            return redirect(url_for("signup", role=role))

        password_hash = generate_password_hash(password)

        try:
            user_id = create_user(name, email, password_hash, role)
        except Exception:
            flash("That email is already in use. Please sign in instead.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user_id
        session["role"] = role
        session["name"] = name or "Friend"
        
        # For homeowners: convert guest session data to registered account
        if role == "homeowner" and session.get('guest_session_id'):
            guest_data = get_guest_session_data(session['guest_session_id'])
            if guest_data and guest_data.get('data'):
                # Save guest data to user's account
                data = guest_data['data']
                if data.get('value_estimate') or data.get('loan_balance'):
                    # Transfer to homeowner_snapshots table
                    upsert_homeowner_snapshot(
                        user_id,
                        value_estimate=data.get('value_estimate'),
                        equity_estimate=data.get('equity_estimate'),
                        loan_balance=data.get('loan_balance'),
                        loan_rate=data.get('loan_rate'),
                        loan_payment=data.get('loan_payment')
                    )
            
            # Link to professional if they came via referral
            if session.get('referral_code'):
                conn = get_connection()
                cur = conn.cursor()
                cur.execute("""
                    UPDATE client_relationships 
                    SET client_id = ?, client_email = ?, status = 'active'
                    WHERE referral_code = ?
                """, (user_id, email, session['referral_code']))
                conn.commit()
                conn.close()
            
            # Clear guest session
            if 'guest_session_id' in session:
                del session['guest_session_id']
            if 'referral_code' in session:
                del session['referral_code']
        
        # Create free trial subscription for agents/lenders
        if role in ["agent", "lender"]:
            conn = get_connection()
            cur = conn.cursor()
            from datetime import timedelta
            trial_ends = (datetime.now() + timedelta(days=14)).isoformat()
            cur.execute("""
                INSERT INTO subscriptions 
                (user_id, subscription_type, status, start_date, trial_ends_at)
                VALUES (?, ?, 'trial', datetime('now'), ?)
            """, (user_id, role, trial_ends))
            cur.execute("UPDATE users SET has_active_subscription = 1 WHERE id = ?", (user_id,))
            conn.commit()
            conn.close()
            flash(f"Welcome! You have a 14-day free trial.", "success")

        # Process pending invitation if exists
        if session.get('pending_invite'):
            return redirect(url_for("process_invitation"))

        if role == "agent":
            return redirect(url_for("agent_dashboard"))
        elif role == "lender":
            return redirect(url_for("lender_dashboard"))
        else:
            return redirect(url_for("homeowner_overview"))

    return render_template("auth/signup.html", role=role, brand_name=FRONT_BRAND_NAME, 
                         prefilled_email=prefilled_email)


@app.route("/login", methods=["GET", "POST"])
def login():
    role = request.args.get("role")  # optional query param for convenience
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        password = request.form["password"]
        user = get_user_by_email(email)

        if not user or not check_password_hash(user["password_hash"], password):
            flash("Email or password did not match. Please try again.", "error")
            return redirect(url_for("login"))

        session["user_id"] = user["id"]
        session["name"] = user["name"]
        session["role"] = user["role"]

        # Redirect by role
        if user["role"] == "homeowner":
            return redirect(url_for("homeowner_overview"))
        elif user["role"] == "agent":
            return redirect(url_for("agent_dashboard"))
        elif user["role"] == "lender":
            return redirect(url_for("lender_dashboard"))
        else:
            return redirect(url_for("index"))

    return render_template("auth/login.html", role=role)


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))


# -------------------------------------------------
# SUBSCRIPTION & ACCESS CONTROL ROUTES
# -------------------------------------------------
@app.route("/subscription-required")
def subscription_required_page():
    """Landing page for users who need a subscription."""
    user = get_current_user()
    return render_template(
        "subscription_required.html",
        brand_name=FRONT_BRAND_NAME,
        user=user
    )

@app.route("/invite", methods=["GET", "POST"])
@login_required
def send_invitation():
    """Send invitation to participate in transaction or become a client."""
    user = get_current_user()
    user_id = user["id"]
    
    if request.method == "POST":
        invited_email = request.form.get("invited_email", "").strip()
        invited_role = request.form.get("invited_role", "homeowner")
        custom_role_name = request.form.get("custom_role_name", "").strip()
        transaction_id = request.form.get("transaction_id", "").strip()
        message = request.form.get("message", "").strip()
        
        if not invited_email:
            flash("Please provide an email address.", "error")
            return redirect(request.url)
        
        # Generate unique invite code
        invite_code = generate_referral_code(12)
        
        # Calculate expiration (30 days from now)
        from datetime import timedelta
        expires_at = (datetime.now() + timedelta(days=30)).isoformat()
        
        # Save invitation
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO invitations 
            (transaction_id, invited_by, invited_email, invited_role, custom_role_name, 
             invite_code, message, expires_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (transaction_id or None, user_id, invited_email, invited_role, 
              custom_role_name or None, invite_code, message or None, expires_at))
        conn.commit()
        conn.close()
        
        # Generate invitation link
        invite_url = f"{request.url_root}accept-invite?code={invite_code}"
        
        flash(f"Invitation sent! Share this link: {invite_url}", "success")
        return redirect(request.referrer or url_for("index"))
    
    # GET request - show invitation form
    transaction_id = request.args.get("transaction_id")
    return render_template(
        "send_invitation.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        transaction_id=transaction_id
    )

@app.route("/accept-invite")
def accept_invitation():
    """Accept an invitation and join platform or transaction."""
    invite_code = request.args.get("code")
    
    if not invite_code:
        flash("Invalid invitation link.", "error")
        return redirect(url_for("index"))
    
    # Look up invitation
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, transaction_id, invited_by, invited_email, invited_role, 
               custom_role_name, message, status, expires_at
        FROM invitations
        WHERE invite_code = ?
    """, (invite_code,))
    
    invite = cur.fetchone()
    conn.close()
    
    if not invite:
        flash("Invitation not found.", "error")
        return redirect(url_for("index"))
    
    invite_dict = dict(invite)
    
    # Check if expired
    if invite_dict['expires_at']:
        expires = datetime.fromisoformat(invite_dict['expires_at'])
        if datetime.now() > expires:
            flash("This invitation has expired.", "error")
            return redirect(url_for("index"))
    
    # Check if already accepted
    if invite_dict['status'] == 'accepted':
        flash("This invitation has already been used.", "info")
        return redirect(url_for("login"))
    
    # Store invite code in session
    session['pending_invite'] = invite_code
    
    # Check if user is logged in
    user = get_current_user()
    if user:
        # User is logged in, process invitation directly
        return redirect(url_for("process_invitation"))
    else:
        # Redirect to signup with email pre-filled
        flash(f"Please sign up or log in to accept this invitation.", "info")
        return redirect(url_for("signup", email=invite_dict['invited_email'], 
                               role=invite_dict['invited_role']))

@app.route("/process-invitation")
@login_required
def process_invitation():
    """Process pending invitation after user logs in/signs up."""
    invite_code = session.get('pending_invite')
    if not invite_code:
        return redirect(url_for("index"))
    
    user = get_current_user()
    user_id = user["id"]
    
    # Get invitation details
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, transaction_id, invited_by, invited_role, custom_role_name
        FROM invitations
        WHERE invite_code = ? AND status = 'pending'
    """, (invite_code,))
    
    invite = cur.fetchone()
    if not invite:
        flash("Invitation has already been processed or is invalid.", "info")
        del session['pending_invite']
        return redirect(url_for("index"))
    
    invite_dict = dict(invite)
    
    # Mark invitation as accepted
    cur.execute("""
        UPDATE invitations 
        SET status = 'accepted', accepted_at = datetime('now')
        WHERE invite_code = ?
    """, (invite_code,))
    
    # Add to transaction participants if transaction_id exists
    if invite_dict['transaction_id']:
        cur.execute("""
            INSERT INTO transaction_participants 
            (transaction_id, user_id, email, role, custom_role_name, invited_by, status)
            VALUES (?, ?, ?, ?, ?, ?, 'active')
        """, (invite_dict['transaction_id'], user_id, user['email'], 
              invite_dict['invited_role'], invite_dict['custom_role_name'], 
              invite_dict['invited_by']))
    else:
        # Client relationship invitation
        cur.execute("""
            SELECT role FROM users WHERE id = ?
        """, (invite_dict['invited_by'],))
        inviter_row = cur.fetchone()
        if inviter_row:
            inviter_role = inviter_row[0]
            if inviter_role in ['agent', 'lender']:
                # Create client relationship
                cur.execute("""
                    INSERT INTO client_relationships 
                    (professional_id, professional_type, client_id, client_email, status)
                    VALUES (?, ?, ?, ?, 'active')
                """, (invite_dict['invited_by'], inviter_role, user_id, user['email']))
    
    conn.commit()
    conn.close()
    
    # Clear pending invite
    del session['pending_invite']
    
    flash("Invitation accepted! You now have access.", "success")
    
    # Redirect based on role
    if user['role'] == 'agent':
        return redirect(url_for("agent_dashboard"))
    elif user['role'] == 'lender':
        return redirect(url_for("lender_dashboard"))
    else:
        return redirect(url_for("homeowner_overview"))


# -------------------------------------------------
# HOMEOWNER ROUTES
# -------------------------------------------------
@app.route("/homeowner")
def homeowner_overview():
    """
    Overview dashboard (My Home Base).
    Supports guest mode - homeowners can use without account.
    """
    # Check for referral code in URL
    referral_code = request.args.get('ref')
    if referral_code:
        session['referral_code'] = referral_code
    
    # Get user or prepare guest mode
    user = get_current_user()
    
    # If guest mode (no user logged in)
    if not user:
        # Create or retrieve guest session
        if 'guest_session_id' not in session:
            session['guest_session_id'] = str(uuid4())
        
        # Load any saved guest data
        guest_data = get_guest_session_data(session['guest_session_id'])
        if guest_data:
            snapshot = guest_data.get('data', {})
        else:
            snapshot = get_homeowner_snapshot_or_default(None)
        
        # Add guest mode flag
        snapshot['is_guest'] = True
        snapshot['referral_code'] = session.get('referral_code')
        
        return render_template(
            "homeowner/overview.html",
            brand_name=FRONT_BRAND_NAME,
            snapshot=snapshot,
            cloud_cma_url=CLOUD_CMA_URL,
            is_guest=True,
        )
    
    # Authenticated user
    snapshot = get_homeowner_snapshot_or_default(user)
    
    # Link to professional if they came via referral
    if session.get('referral_code'):
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            UPDATE client_relationships 
            SET client_id = ?, client_email = ?, status = 'active'
            WHERE referral_code = ? AND client_id IS NULL
        """, (user['id'], user['email'], session['referral_code']))
        conn.commit()
        conn.close()
        del session['referral_code']  # Clear after linking

    return render_template(
        "homeowner/overview.html",
        brand_name=FRONT_BRAND_NAME,
        snapshot=snapshot,
        cloud_cma_url=CLOUD_CMA_URL,
        is_guest=False,
    )


@app.route("/homeowner/recent-activity")
def homeowner_recent_activity():
    return render_template(
        "homeowner/recent_activity.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/saved-notes", methods=["GET", "POST"])
def homeowner_saved_notes():
    """Manage premium mood boards for homeowners with advanced features like
    color palettes, vision statements, templates, and drag-and-drop uploads."""
    user_id = get_current_user_id()

    # Directory for saving design board uploads
    design_dir = BASE_DIR / "static" / "uploads" / "design_boards"
    design_dir.mkdir(parents=True, exist_ok=True)

    if request.method == "POST":
        action = request.form.get("action") or "create_board"

        # Create a new design board note with premium features
        if action == "create_board":
            board_name = (request.form.get("board_name") or "").strip()
            vision_statement = (request.form.get("vision_statement") or "").strip()
            board_title = (request.form.get("board_title") or "").strip()
            board_notes = (request.form.get("board_notes") or "").strip()
            board_links = (request.form.get("board_links") or "").strip()

            if not board_name:
                flash("Please provide a board name.", "error")
                return redirect(url_for("homeowner_saved_notes"))

            # Process uploaded photos
            saved_photos = []
            files = request.files.getlist("board_photos")
            for f in files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                unique_name = f"{uuid4().hex}_{safe_name}"
                save_path = design_dir / unique_name
                try:
                    f.save(save_path)
                    rel_path = str(Path("uploads") / "design_boards" / unique_name).replace("\\", "/")
                    saved_photos.append(rel_path)
                except Exception:
                    flash(f"Could not save file: {safe_name}", "error")
            
            # Process uploaded fixtures with background removal
            saved_fixtures = []
            fixture_files = request.files.getlist("board_fixtures")
            for f in fixture_files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                # Force PNG format for transparency
                base_name = Path(safe_name).stem
                unique_name = f"{uuid4().hex}_fixture_{base_name}.png"
                save_path = design_dir / unique_name
                try:
                    # Save original first
                    f.save(save_path)
                    # Remove white background
                    remove_white_background(save_path)
                    rel_path = str(Path("uploads") / "design_boards" / unique_name).replace("\\", "/")
                    saved_fixtures.append(rel_path)
                except Exception as e:
                    flash(f"Could not save fixture: {safe_name}", "error")

            # Process color palette
            colors = request.form.getlist("colors[]")
            color_palette = [c for c in colors if c]  # Remove empty values

            # Persist board with premium features
            try:
                add_design_board_note(
                    user_id=user_id,
                    project_name=board_name,
                    title=board_title,
                    details=f"{board_notes}\n\nLinks:\n{board_links}" if board_links else board_notes,
                    photos=saved_photos,
                    files=[],
                    vision_statement=vision_statement,
                    color_palette=color_palette,
                    board_template="collage",
                    label_style="sans-serif",
                    is_private=0,
                    fixtures=saved_fixtures,
                )
                flash("✨ Beautiful board created!", "success")
            except Exception as e:
                flash("Could not create the board. Please try again.", "error")

            return redirect(url_for("homeowner_saved_notes", view=board_name))

        # Edit an existing board
        if action == "edit_board":
            board_name = (request.form.get("board_name") or "").strip()
            if not board_name:
                flash("Missing board name.", "error")
                return redirect(url_for("homeowner_saved_notes"))

            # Remove selected photos
            remove_photos = request.form.getlist("remove_photos")
            if remove_photos:
                try:
                    remove_photos_from_board(user_id, board_name, remove_photos)
                    for p in remove_photos:
                        try:
                            ppath = BASE_DIR / "static" / p
                            if ppath.exists():
                                ppath.unlink()
                        except Exception:
                            pass
                except Exception:
                    flash("Could not remove some photos.", "error")

            # Remove selected fixtures
            remove_fixtures = request.form.getlist("remove_fixtures")
            if remove_fixtures:
                try:
                    from database import remove_fixtures_from_board
                    remove_fixtures_from_board(user_id, board_name, remove_fixtures)
                    for f in remove_fixtures:
                        try:
                            fpath = BASE_DIR / "static" / f
                            if fpath.exists():
                                fpath.unlink()
                        except Exception:
                            pass
                except Exception:
                    flash("Could not remove some fixtures.", "error")

            # Save newly uploaded photos
            new_photos = []
            files = request.files.getlist("new_photos")
            for f in files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                unique_name = f"{uuid4().hex}_{safe_name}"
                save_path = BASE_DIR / "static" / "uploads" / "design_boards" / unique_name
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    f.save(save_path)
                    rel_path = str(Path("uploads") / "design_boards" / unique_name).replace("\\", "/")
                    new_photos.append(rel_path)
                except Exception:
                    flash(f"Could not save file: {safe_name}", "error")
            
            # Save newly uploaded fixtures with background removal
            new_fixtures = []
            fixture_files = request.files.getlist("new_fixtures")
            for f in fixture_files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                # Force PNG format for transparency
                base_name = Path(safe_name).stem
                unique_name = f"{uuid4().hex}_fixture_{base_name}.png"
                save_path = BASE_DIR / "static" / "uploads" / "design_boards" / unique_name
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    # Save original first
                    f.save(save_path)
                    # Remove white background
                    remove_white_background(save_path)
                    rel_path = str(Path("uploads") / "design_boards" / unique_name).replace("\\", "/")
                    new_fixtures.append(rel_path)
                except Exception as e:
                    flash(f"Could not save fixture: {safe_name}", "error")

            edit_title = (request.form.get("edit_title") or "").strip()
            edit_notes = (request.form.get("edit_notes") or "").strip()
            
            # Process new colors if provided
            new_colors = request.form.getlist("new_colors[]")
            if new_colors:
                color_palette = [c for c in new_colors if c]
                try:
                    from database import update_board_colors
                    update_board_colors(user_id, board_name, color_palette)
                except Exception:
                    pass

            if new_photos or new_fixtures or edit_title or edit_notes:
                try:
                    add_design_board_note(
                        user_id=user_id,
                        project_name=board_name,
                        title=edit_title,
                        details=edit_notes,
                        photos=new_photos,
                        files=[],
                        fixtures=new_fixtures,
                    )
                    flash("Board updated successfully!", "success")
                except Exception:
                    flash("Could not update board.", "error")

            return redirect(url_for("homeowner_saved_notes", view=board_name))

        # Delete an entire board (all notes/files)
        if action == "delete_board":
            board_name = (request.form.get("board_name") or "").strip()
            if board_name:
                # remove files from disk (best-effort)
                try:
                    details = get_design_board_details(user_id, board_name)
                    if details and details.get("photos"):
                        for photo in details.get("photos", []):
                            try:
                                file_path = BASE_DIR / "static" / photo
                                if file_path.exists():
                                    file_path.unlink()
                            except Exception:
                                pass
                    delete_design_board(user_id, board_name)
                    flash("Board deleted.", "success")
                except Exception:
                    flash("Could not delete that board.", "error")

            return redirect(url_for("homeowner_saved_notes"))

    # GET: list boards and aggregate details for display
    boards = get_design_boards_for_user(user_id) or []
    board_details = {}
    for b in boards:
        try:
            details = get_design_board_details(user_id, b)
            board_details[b] = details or {"project_name": b, "photos": [], "notes": [], "files": []}
        except Exception:
            board_details[b] = {"project_name": b, "photos": [], "notes": [], "files": []}
    # If a specific board should be shown in the side panel (e.g., after creation)
    selected_board = request.args.get("view")
    selected_details = board_details.get(selected_board) if selected_board else None

    return render_template(
        "homeowner/saved_notes.html",
        brand_name=FRONT_BRAND_NAME,
        boards=boards,
        board_details=board_details,
        selected_board=selected_board,
        selected_details=selected_details,
    )


@app.route("/homeowner/design-boards")
def homeowner_design_boards():
    """Redirect to saved notes (boards now integrated there)."""
    return redirect(url_for("homeowner_saved_notes"))


@app.route("/homeowner/design-boards/<path:board_name>")
def homeowner_design_board_view(board_name):
    """Display a dedicated detail page for a single design board."""
    user_id = get_current_user_id()
    details = get_design_board_details(user_id, board_name)
    if not details:
        flash("That board could not be found.", "error")
        return redirect(url_for("homeowner_saved_notes"))

    return render_template(
        "homeowner/board_detail.html",
        selected_board=board_name,
        selected_details=details,
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/design-boards/<path:board_name>/download")
def homeowner_design_board_download(board_name):
    """Render a print-optimized view of a single board and try to return a PDF.

    If `weasyprint` is installed this will return a generated PDF. If not, the
    HTML view is rendered and a message prompts installing `weasyprint`.
    """
    user_id = get_current_user_id()
    details = get_design_board_details(user_id, board_name)
    if not details:
        flash("That board could not be found.", "error")
        return redirect(url_for("homeowner_saved_notes"))

    html = render_template(
        "homeowner/board_print.html",
        selected_board=board_name,
        selected_details=details,
        brand_name=FRONT_BRAND_NAME,
    )

    try:
        # Lazy import to keep optional dependency
        from weasyprint import HTML

        pdf = HTML(string=html, base_url=str(BASE_DIR / "static")).write_pdf()
        return Response(pdf, mimetype="application/pdf", headers={
            "Content-Disposition": f'attachment; filename="{board_name}.pdf"'
        })
    except Exception:
        # Fallback: render the HTML and suggest installing WeasyPrint for direct PDFs
        flash("WeasyPrint not available: rendering HTML. Install WeasyPrint to enable PDF downloads.", "info")
        return html


@app.route("/homeowner/design-boards/<path:board_name>/duplicate", methods=["POST"])
def homeowner_design_board_duplicate(board_name):
    """Duplicate an existing board with a new name."""
    user_id = get_current_user_id()
    new_name = request.form.get("new_name", f"{board_name} (Copy)").strip()
    
    try:
        duplicate_design_board(user_id, board_name, new_name)
        flash(f"✨ Board duplicated as '{new_name}'!", "success")
        return redirect(url_for("homeowner_design_board_view", board_name=new_name))
    except Exception as e:
        flash("Could not duplicate board.", "error")
        return redirect(url_for("homeowner_design_board_view", board_name=board_name))


@app.route("/homeowner/design-boards/<path:board_name>/privacy", methods=["POST"])
def homeowner_design_board_privacy(board_name):
    """Toggle privacy settings for a board."""
    user_id = get_current_user_id()
    is_private = int(request.form.get("is_private", 0))
    
    # Generate shareable link if making public
    shareable_link = None
    if not is_private:
        import secrets
        shareable_link = secrets.token_urlsafe(16)
    
    try:
        update_board_privacy(user_id, board_name, is_private, shareable_link)
        status = "private" if is_private else "shareable"
        flash(f"Board is now {status}.", "success")
    except Exception:
        flash("Could not update privacy settings.", "error")
    
    return redirect(url_for("homeowner_design_board_view", board_name=board_name))


@app.route("/homeowner/design-boards/<path:board_name>/template", methods=["POST"])
def homeowner_design_board_template(board_name):
    """Change the board template style."""
    user_id = get_current_user_id()
    template = request.form.get("template", "collage")
    
    if template not in ["collage", "grid", "editorial"]:
        template = "collage"
    
    try:
        update_board_template(user_id, board_name, template)
        flash(f"Board template changed to {template}.", "success")
    except Exception:
        flash("Could not update template.", "error")
    
    return redirect(url_for("homeowner_design_board_view", board_name=board_name))


@app.route("/homeowner/crop-photo", methods=["POST"])
def homeowner_crop_photo():
    """Crop a photo and replace the original."""
    from flask import jsonify
    
    try:
        user_id = get_current_user_id()
        board_name = request.form.get("board_name")
        original_path = request.form.get("original_path")
        cropped_file = request.files.get("cropped_image")
        
        if not all([board_name, original_path, cropped_file]):
            return jsonify({"success": False, "error": "Missing data"})
        
        # Verify user owns this board
        details = get_design_board_details(user_id, board_name)
        if not details or original_path not in details.get("photos", []):
            return jsonify({"success": False, "error": "Photo not found"})
        
        # Save cropped image over original
        file_path = BASE_DIR / "static" / original_path
        cropped_file.save(file_path)
        
        return jsonify({"success": True})
    except Exception as e:
        print(f"Crop error: {e}")
        return jsonify({"success": False, "error": str(e)})


@app.route("/homeowner/upload-documents", methods=["GET", "POST"])
def homeowner_upload_documents():
    user_id = get_current_user_id()
    docs = list_homeowner_documents(user_id)
    events = list_timeline_events(user_id)  # Add timeline events

    # -------- DELETE FILE ----------
    if request.method == "POST" and request.form.get("delete_id"):
        delete_id = request.form["delete_id"]
        delete_homeowner_document(delete_id)
        flash("Document removed.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    # -------- REATTACH / REUPLOAD ----------
    if (
        request.method == "POST"
        and request.form.get("reattach_id")
        and request.files.get("file")
    ):
        doc_id = request.form["reattach_id"]
        new_file = request.files["file"]
        save_name = secure_filename(new_file.filename)
        new_file.save(HOMEOWNER_DOCS_DIR / save_name)
        update_homeowner_document_file(doc_id, save_name)
        flash("File updated.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    # -------- NORMAL UPLOAD ----------
    if request.method == "POST" and request.files.get("file"):
        file = request.files["file"]
        category = request.form.get("category", "Other")
        save_name = secure_filename(file.filename)
        
        # Upload to R2 if configured, otherwise save locally
        if is_r2_enabled():
            try:
                # Upload to R2
                result = upload_file_to_r2(file, save_name, folder="documents")
                add_homeowner_document(
                    user_id, 
                    save_name, 
                    category,
                    r2_key=result["key"],
                    r2_url=result["url"]
                )
                flash("Document uploaded to cloud storage.", "success")
            except Exception as e:
                flash(f"Upload failed: {str(e)}", "error")
                return redirect(url_for("homeowner_upload_documents"))
        else:
            # Fallback to local storage
            file.save(HOMEOWNER_DOCS_DIR / save_name)
            add_homeowner_document(user_id, save_name, category)
            flash("Document uploaded.", "success")
        
        return redirect(url_for("homeowner_upload_documents"))

    return render_template("homeowner/upload_documents.html", docs=docs, events=events)


@app.route("/homeowner/documents/<int:doc_id>/view")
def homeowner_document_view(doc_id):
    user_id = get_current_user_id()
    row = get_homeowner_document_for_user(doc_id, user_id)
    if not row:
        flash("That document could not be found.", "error")
        return redirect(url_for("homeowner_upload_documents"))

    # If file is in R2, redirect to R2 URL
    if row.get("r2_key"):
        try:
            file_url = get_file_url_from_r2(row["r2_key"])
            return redirect(file_url)
        except Exception as e:
            flash(f"Could not retrieve file: {str(e)}", "error")
            return redirect(url_for("homeowner_upload_documents"))
    
    # Fallback to local file
    filename = row["file_name"]
    return send_from_directory(HOMEOWNER_DOCS_DIR, filename, as_attachment=False)


@app.route("/homeowner/documents/<int:doc_id>/replace", methods=["GET", "POST"])
def homeowner_document_replace(doc_id):
    user_id = get_current_user_id()
    row = get_homeowner_document_for_user(doc_id, user_id)
    if not row:
        flash("That document could not be found.", "error")
        return redirect(url_for("homeowner_upload_documents"))

    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Please choose a file to upload.", "error")
            return redirect(request.url)

        safe_name = secure_filename(file.filename)
        save_path = HOMEOWNER_DOCS_DIR / safe_name
        HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        file.save(save_path)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE homeowner_documents
            SET file_name = ?, uploaded_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                safe_name,
                datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
                doc_id,
                user_id,
            ),
        )
        conn.commit()
        conn.close()

        flash("Document updated.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    # GET: tiny page to pick replacement file
    return render_template(
        "homeowner/document_replace.html",
        document=row,
    )


@app.route("/homeowner/home-timeline", methods=["GET", "POST"])
def homeowner_home_timeline():
    user_id = get_current_user_id()

    if request.method == "POST":
        title = request.form.get("title")
        category = request.form.get("category")
        event_date = request.form.get("event_date")
        cost = request.form.get("cost")
        notes = request.form.get("notes")
        files = request.files.getlist("files")

        saved_files = []
        for f in files:
            if f.filename:
                filename = secure_filename(f.filename)
                filepath = UPLOAD_TIMELINE / filename
                f.save(filepath)
                saved_files.append(filename)

        add_timeline_event(user_id, event_date, title, category, cost, notes, saved_files)
        return redirect(url_for("homeowner_home_timeline"))

    events = list_timeline_events(user_id)
    return render_template(
        "homeowner/home_timeline.html",
        brand_name=FRONT_BRAND_NAME,
        events=events,
    )


@app.route("/homeowner/home-timeline/delete/<int:event_id>")
def homeowner_timeline_delete(event_id):
    delete_timeline_event(event_id, get_current_user_id())
    return redirect(url_for("homeowner_home_timeline"))


@app.route("/homeowner/home-timeline/print")
def homeowner_timeline_print():
    events = list_timeline_events(get_current_user_id())
    return render_template(
        "homeowner/home_timeline_print.html",
        brand_name=FRONT_BRAND_NAME,
        events=events,
    )


# ----- VALUE & EQUITY -----
@app.route("/homeowner/value/my-home")
def homeowner_value_my_home():
    """
    Landing for 'My Home Value' – can link out to Cloud CMA.
    """
    user = get_current_user()
    snapshot = get_homeowner_snapshot_or_default(user)
    return render_template(
        "homeowner/value_my_home.html",
        brand_name=FRONT_BRAND_NAME,
        snapshot=snapshot,
        cloud_cma_url=CLOUD_CMA_URL,
    )


@app.route("/homeowner/value/equity-overview", methods=["GET", "POST"])
def homeowner_value_equity_overview():
    user = get_current_user()
    if not user:
        flash("Please log in to access this page.", "warning")
        return redirect(url_for("login"))
    
    # Get all properties for the user
    properties = get_user_properties(user["id"])
    
    # Determine which property to display
    property_id_param = request.args.get("property_id")
    if property_id_param:
        try:
            current_property_id = int(property_id_param)
            current_property = get_property_by_id(current_property_id)
            # Verify ownership
            if not current_property or current_property["user_id"] != user["id"]:
                current_property = None
                current_property_id = None
        except:
            current_property = None
            current_property_id = None
    else:
        current_property = get_primary_property(user["id"])
        current_property_id = current_property["id"] if current_property else None
    
    # If no property exists, create a default one
    if not current_property:
        if not properties:
            # Create a default property for first-time users
            default_address = "My Home"
            property_id = add_property(user["id"], default_address, None, "primary")
            current_property = get_property_by_id(property_id)
            current_property_id = property_id
            properties = [current_property]
        else:
            current_property = properties[0]
            current_property_id = current_property["id"]
    
    if request.method == "POST":
        # Helper to safely parse float values
        def safe_float(val):
            if not val or val.strip() == "":
                return None
            try:
                return float(val.replace(",", ""))
            except:
                return None
        
        # Parse form data
        value_estimate = safe_float(request.form.get("value_estimate", ""))
        loan_balance = safe_float(request.form.get("loan_balance", ""))
        loan_rate = safe_float(request.form.get("loan_rate", ""))
        loan_payment = safe_float(request.form.get("loan_payment", ""))
        loan_term_years = safe_float(request.form.get("loan_term_years", ""))
        loan_start_date = request.form.get("loan_start_date", "").strip() or None
        
        # Update database for current property
        upsert_homeowner_snapshot_for_property(
            user_id=user["id"],
            property_id=current_property_id,
            value_estimate=value_estimate,
            loan_balance=loan_balance,
            loan_rate=loan_rate,
            loan_payment=loan_payment,
            loan_term_years=loan_term_years,
            loan_start_date=loan_start_date,
        )
        
        # Update property estimated value if provided
        if value_estimate is not None:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE properties SET estimated_value = ? WHERE id = ?",
                (value_estimate, current_property_id)
            )
            conn.commit()
            conn.close()
        
        flash("Loan details updated successfully!", "success")
        return redirect(url_for("homeowner_value_equity_overview", property_id=current_property_id))
    
    # GET: Display current data with calculations
    snapshot = get_homeowner_snapshot_for_property(user["id"], current_property_id)
    
    # Use property estimated value if snapshot doesn't have one
    if not snapshot.get("value_estimate") and current_property.get("estimated_value"):
        snapshot["value_estimate"] = current_property["estimated_value"]
    
    # Calculate derived metrics
    # Helper to safely convert to float
    def safe_float_convert(val, default=0):
        if val is None or val == "":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default
    
    current_value = safe_float_convert(snapshot.get("value_estimate"))
    loan_balance = safe_float_convert(snapshot.get("loan_balance"))
    equity_estimate = safe_float_convert(snapshot.get("equity_estimate"))
    loan_rate = safe_float_convert(snapshot.get("loan_rate"))
    loan_payment = safe_float_convert(snapshot.get("loan_payment"))
    loan_term_years = safe_float_convert(snapshot.get("loan_term_years"))
    loan_start_date = snapshot.get("loan_start_date") or ""
    
    # Calculate LTV (Loan-to-Value ratio)
    ltv = 0
    if current_value > 0 and loan_balance > 0:
        ltv = (loan_balance / current_value) * 100
    
    # Calculate years remaining and payoff date
    years_remaining = 0
    payoff_date = ""
    if loan_start_date and loan_term_years > 0:
        from datetime import datetime, timedelta
        try:
            start = datetime.fromisoformat(loan_start_date)
            end = start + timedelta(days=365.25 * loan_term_years)
            payoff_date = end.strftime("%b %Y")
            
            now = datetime.now()
            years_remaining = (end - now).days / 365.25
            if years_remaining < 0:
                years_remaining = 0
        except:
            pass
    
    # Calculate appreciation metrics
    # Assume 3-5% annual appreciation (can be made dynamic later)
    annual_appreciation_rate = 0.04  # 4% default
    monthly_appreciation = (current_value * annual_appreciation_rate) / 12 if current_value > 0 else 0
    one_year_value = current_value * (1 + annual_appreciation_rate) if current_value > 0 else 0
    five_year_value = current_value * ((1 + annual_appreciation_rate) ** 5) if current_value > 0 else 0
    
    # Calculate net worth built (equity accumulated)
    # Estimate original purchase price (rough estimate: current equity built over time)
    estimated_down_payment = equity_estimate * 0.2 if equity_estimate > 0 else 0
    wealth_built = equity_estimate if equity_estimate > 0 else 0
    
    # Refinance scenario calculations
    current_rate_market = 6.0  # Can be pulled from market data API later
    refinance_savings = 0
    new_monthly_payment = 0
    if loan_rate > 0 and loan_balance > 0 and loan_rate > current_rate_market:
        # Simplified calculation: difference in rate * balance / 12
        rate_diff = loan_rate - current_rate_market
        annual_savings = (loan_balance * (rate_diff / 100))
        refinance_savings = annual_savings / 12
        # Rough estimate of new payment
        if loan_payment > 0:
            new_monthly_payment = loan_payment - refinance_savings
    
    # Cash-out refinance potential (80% LTV threshold)
    max_cash_out = 0
    if current_value > 0:
        max_loan_80_ltv = current_value * 0.80
        max_cash_out = max_loan_80_ltv - loan_balance if max_loan_80_ltv > loan_balance else 0
    
    # Rental income potential (estimate 0.8-1% of home value per month)
    monthly_rental_estimate = current_value * 0.009 if current_value > 0 else 0  # 0.9% of value
    annual_rental_income = monthly_rental_estimate * 12
    
    # Extra payment scenario (pay $200 extra per month)
    extra_payment_amount = 200
    interest_saved_extra = 0
    time_saved_months = 0
    if loan_balance > 0 and loan_rate > 0 and years_remaining > 0:
        # Simplified: extra payments reduce principal faster
        # Rough estimate: $200/month extra could save 3-5 years on a 30-year mortgage
        time_saved_months = min(years_remaining * 12 * 0.15, 60)  # Up to 5 years
        interest_saved_extra = extra_payment_amount * time_saved_months * 0.5  # Rough interest savings
    
    # Generate tips based on current situation
    tips = []
    if loan_rate > 6.5:
        tips.append("🎯 Your interest rate is above 6.5%. Consider exploring refinance options to lower your monthly payment.")
    
    if years_remaining > 20 and equity_estimate > 50000:
        tips.append("💡 With significant equity and many years remaining, making extra principal payments could save thousands in interest.")
    
    if ltv < 80 and loan_balance > 0:
        tips.append("✨ Your loan-to-value ratio is below 80%. You may qualify to remove PMI if you're paying it.")
    
    if equity_estimate > 100000:
        tips.append("🏡 You've built substantial equity! This could support renovations, debt consolidation, or future investment opportunities.")
    
    if refinance_savings > 50:
        tips.append(f"💰 Refinancing at current market rates could save you approximately ${refinance_savings:,.0f}/month.")
    
    if max_cash_out > 50000:
        tips.append(f"🏦 You could access up to ${max_cash_out:,.0f} through a cash-out refinance while staying at 80% LTV.")
    
    if not tips:
        tips.append("📊 Enter your complete loan details above to receive personalized savings tips and strategies.")
    
    return render_template(
        "homeowner/value_equity_overview.html",
        brand_name=FRONT_BRAND_NAME,
        snapshot=snapshot,
        properties=properties,
        current_property=current_property,
        current_property_id=current_property_id,
        current_value=current_value,
        loan_balance=loan_balance,
        equity_estimate=equity_estimate,
        loan_rate=loan_rate,
        loan_payment=loan_payment,
        loan_term_years=loan_term_years,
        loan_start_date=loan_start_date,
        ltv=ltv,
        years_remaining=years_remaining,
        payoff_date=payoff_date,
        tips=tips,
        monthly_appreciation=monthly_appreciation,
        one_year_value=one_year_value,
        five_year_value=five_year_value,
        wealth_built=wealth_built,
        refinance_savings=refinance_savings,
        new_monthly_payment=new_monthly_payment,
        current_rate_market=current_rate_market,
        max_cash_out=max_cash_out,
        monthly_rental_estimate=monthly_rental_estimate,
        annual_rental_income=annual_rental_income,
        extra_payment_amount=extra_payment_amount,
        interest_saved_extra=interest_saved_extra,
        time_saved_months=time_saved_months,
    )


@app.route("/homeowner/add-property", methods=["POST"])
def homeowner_add_property():
    """Add a new property for the homeowner."""
    user = get_current_user()
    if not user:
        flash("Please log in to add a property.", "warning")
        return redirect(url_for("login"))
    
    address = request.form.get("property_address", "").strip()
    if not address:
        flash("Property address is required.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    # Parse estimated value (optional)
    estimated_value = None
    value_str = request.form.get("estimated_value", "").strip()
    if value_str:
        try:
            estimated_value = float(value_str.replace(",", ""))
        except:
            pass
    
    property_type = request.form.get("property_type", "primary").strip()
    
    # Add property to database
    property_id = add_property(user["id"], address, estimated_value, property_type)
    
    # Set as primary and redirect to view it
    set_primary_property(user["id"], property_id)
    
    flash(f"Property '{address}' added successfully!", "success")
    return redirect(url_for("homeowner_value_equity_overview", property_id=property_id))


@app.route("/homeowner/switch-property", methods=["POST"])
def homeowner_switch_property():
    """Switch to a different property."""
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))
    
    property_id = request.form.get("property_id")
    if not property_id:
        flash("No property selected.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    try:
        property_id = int(property_id)
    except:
        flash("Invalid property ID.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    # Verify property belongs to user
    prop = get_property_by_id(property_id)
    if not prop or prop["user_id"] != user["id"]:
        flash("Property not found.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    # Set as primary
    set_primary_property(user["id"], property_id)
    
    flash(f"Switched to {prop['address']}", "success")
    return redirect(url_for("homeowner_value_equity_overview", property_id=property_id))


    # Get current property
    property_id_param = request.args.get("property_id")
    if property_id_param:
        try:
            current_property_id = int(property_id_param)
            current_property = get_property_by_id(current_property_id)
            if not current_property or current_property["user_id"] != user["id"]:
                current_property = get_primary_property(user["id"])
                current_property_id = current_property["id"] if current_property else None
        except:
            current_property = get_primary_property(user["id"])
            current_property_id = current_property["id"] if current_property else None
    else:
        current_property = get_primary_property(user["id"])
        current_property_id = current_property["id"] if current_property else None
    
    if not current_property:
        flash("No property found. Please add a property first.", "warning")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    # Get snapshot data
    snapshot = get_homeowner_snapshot_for_property(user["id"], current_property_id)
    
    # Helper to safely convert to float
    def safe_float_convert(val, default=0):
        if val is None or val == "":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default
    
    current_value = safe_float_convert(snapshot.get("value_estimate"))
    loan_balance = safe_float_convert(snapshot.get("loan_balance"))
    loan_rate = safe_float_convert(snapshot.get("loan_rate"))
    loan_payment = safe_float_convert(snapshot.get("loan_payment"))
    loan_term_years = safe_float_convert(snapshot.get("loan_term_years"))
    loan_start_date = snapshot.get("loan_start_date") or ""
    
    # Calculate years remaining
    years_remaining = loan_term_years
    if loan_start_date and loan_term_years > 0:
        from datetime import datetime, timedelta
        try:
            start = datetime.fromisoformat(loan_start_date)
            end = start + timedelta(days=365.25 * loan_term_years)
            now = datetime.now()
            years_remaining = max(0, (end - now).days / 365.25)
        except:
            pass
    
    # Market rates for different scenarios
    market_rates = {
        "excellent": 5.5,
        "good": 6.0,
        "average": 6.5,
        "fair": 7.0,
    }
    
    # Calculate refinance scenarios for each rate
    scenarios = []
    for credit_tier, new_rate in market_rates.items():
        if loan_balance > 0 and years_remaining > 0:
            # Calculate new monthly payment using mortgage formula
            # M = P [ i(1 + i)^n ] / [ (1 + i)^n – 1]
            monthly_rate = (new_rate / 100) / 12
            num_payments = years_remaining * 12
            
            if monthly_rate > 0:
                new_monthly_payment = loan_balance * (monthly_rate * (1 + monthly_rate)**num_payments) / ((1 + monthly_rate)**num_payments - 1)
            else:
                new_monthly_payment = loan_balance / num_payments
            
            # Calculate current payment if not provided
            if loan_payment <= 0 and loan_rate > 0:
                current_monthly_rate = (loan_rate / 100) / 12
                if current_monthly_rate > 0:
                    loan_payment = loan_balance * (current_monthly_rate * (1 + current_monthly_rate)**num_payments) / ((1 + current_monthly_rate)**num_payments - 1)
            
            monthly_savings = loan_payment - new_monthly_payment
            annual_savings = monthly_savings * 12
            lifetime_savings = monthly_savings * num_payments
            
            # Calculate total interest paid (current vs new)
            current_total_paid = loan_payment * num_payments if loan_payment > 0 else 0
            current_interest = current_total_paid - loan_balance
            
            new_total_paid = new_monthly_payment * num_payments
            new_interest = new_total_paid - loan_balance
            
            interest_saved = current_interest - new_interest
            
            # Closing costs estimate (2-5% of loan amount, average 3%)
            closing_costs = loan_balance * 0.03
            
            # Break-even months
            break_even_months = closing_costs / monthly_savings if monthly_savings > 0 else 0
            
            scenarios.append({
                "tier": credit_tier.title(),
                "rate": new_rate,
                "new_payment": new_monthly_payment,
                "monthly_savings": monthly_savings,
                "monthly_savings_abs": abs(monthly_savings),
                "annual_savings": annual_savings,
                "annual_savings_abs": abs(annual_savings),
                "lifetime_savings": lifetime_savings,
                "interest_saved": interest_saved,
                "interest_saved_abs": abs(interest_saved),
                "closing_costs": closing_costs,
                "break_even_months": break_even_months,
                "is_better": monthly_savings > 0,
            })
    
    return render_template(
        "homeowner/value_refinance_calculator.html",
        brand_name=FRONT_BRAND_NAME,
        current_property=current_property,
        current_value=current_value,
        loan_balance=loan_balance,
        loan_rate=loan_rate,
        loan_payment=loan_payment,
        years_remaining=years_remaining,
        scenarios=scenarios,
    )


# ----- RENOVATION & IMPROVEMENT -----
@app.route("/homeowner/reno/planner", methods=["GET", "POST"])
def homeowner_reno_planner():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        name = request.form.get("project_name", "").strip()
        budget_raw = request.form.get("project_budget", "").replace(",", "").strip()
        status = request.form.get("project_status", "Planning").strip()
        notes = request.form.get("project_notes", "").strip()

        budget = None
        if budget_raw:
            try:
                budget = float(budget_raw)
            except ValueError:
                budget = None

        if name:
            add_homeowner_project(user_id, name, budget, status, notes)
            flash("Project saved.", "success")

    projects = list_homeowner_projects(user_id) if user_id else []

    return render_template(
        "homeowner/reno_planner.html",
        brand_name=FRONT_BRAND_NAME,
        projects=projects,
    )


@app.route("/homeowner/reno/design-ideas")
def homeowner_reno_design_ideas():
    return render_template(
        "homeowner/reno_design_ideas.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/reno/material-cost")
def homeowner_reno_material_cost():
    return render_template(
        "homeowner/reno_material_cost.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/reno/roi-guide")
def homeowner_reno_roi_guide():
    return render_template(
        "homeowner/reno_roi_guide.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/reno/before-after")
def homeowner_reno_before_after():
    return render_template(
        "homeowner/reno_before_after.html",
        brand_name=FRONT_BRAND_NAME,
    )


# ----- NEXT HOME STRATEGY -----
@app.route("/homeowner/next/plan-my-move", methods=["GET", "POST"])
def homeowner_next_plan_move():
    user = get_current_user()
    user_id = user["id"] if user else None

    existing_plan = get_next_move_plan(user_id) if user_id else None

    if request.method == "POST" and user_id:
        timeline = request.form.get("timeline", "")
        budget = request.form.get("budget", "")
        preapproved = request.form.get("preapproved", "")
        areas = request.form.get("areas", "")
        home_type = request.form.get("home_type", "")
        beds_baths = request.form.get("beds_baths", "")
        must_haves = request.form.get("must_haves", "")
        dealbreakers = request.form.get("dealbreakers", "")
        condition = request.form.get("condition", "")
        feeling = request.form.get("feeling", "")

        upsert_next_move_plan(
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
        )
        flash("Your next-home plan has been saved.", "success")
        existing_plan = get_next_move_plan(user_id)

    return render_template(
        "homeowner/next_plan_move.html",
        brand_name=FRONT_BRAND_NAME,
        plan=existing_plan,
    )


@app.route("/homeowner/next/buy-sell-guidance")
def homeowner_next_buy_sell_guidance():
    return render_template(
        "homeowner/next_buy_sell_guidance.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/pathways")
def homeowner_next_pathways():
    return render_template(
        "homeowner/next_pathways.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/pathway/first-time-buyer")
def homeowner_pathway_first_time_buyer():
    return render_template(
        "homeowner/pathway_first_time_buyer.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/pathway/selling-buying")
def homeowner_pathway_selling_buying():
    return render_template(
        "homeowner/pathway_selling_buying.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/pathway/building-new")
def homeowner_pathway_building_new():
    return render_template(
        "homeowner/pathway_building_new.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/pathway/investing")
def homeowner_pathway_investing():
    return render_template(
        "homeowner/pathway_investing.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/pathway/relocating")
def homeowner_pathway_relocating():
    return render_template(
        "homeowner/pathway_relocating.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/loan-paths")
def homeowner_next_loan_paths():
    return render_template(
        "homeowner/next_loan_paths.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/affordability")
def homeowner_next_affordability():
    return render_template(
        "homeowner/next_affordability.html",
        brand_name=FRONT_BRAND_NAME,
    )


# ----- OWNERSHIP CARE -----
@app.route("/homeowner/care/maintenance-guide")
def homeowner_care_maintenance_guide():
    return render_template(
        "homeowner/care_maintenance_guide.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/seasonal-checklists")
def homeowner_care_seasonal_checklists():
    return render_template(
        "homeowner/care_seasonal_checklists.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/home-protection")
def homeowner_care_home_protection():
    return render_template(
        "homeowner/care_home_protection.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/warranty-log")
def homeowner_care_warranty_log():
    return render_template(
        "homeowner/care_warranty_log.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/energy-savings")
def homeowner_care_energy_savings():
    return render_template(
        "homeowner/care_energy_savings.html",
        brand_name=FRONT_BRAND_NAME,
    )


# ----- SUPPORT & CONVERSATIONS -----
@app.route("/homeowner/support/ask-question", methods=["GET", "POST"])
def homeowner_support_ask_question():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST":
        topic = request.form.get("topic", "").strip()
        question = request.form.get("question", "").strip()
        if question:
            add_homeowner_question(user_id, topic, question)
            flash("Your question has been sent. We’ll follow up with care.", "success")
            return redirect(url_for("homeowner_support_ask_question"))

    return render_template(
        "homeowner/support_ask_question.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/chat-human")
def homeowner_support_chat_human():
    return render_template(
        "homeowner/support_chat_human.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/schedule-chat")
def homeowner_support_schedule_chat():
    return render_template(
        "homeowner/support_schedule_chat.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/resources")
def homeowner_support_resources():
    return render_template(
        "homeowner/support_resources.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/meet-team")
def homeowner_support_meet_team():
    return render_template(
        "homeowner/support_meet_team.html",
        brand_name=FRONT_BRAND_NAME,
    )


# -------------------------------------------------
# AGENT ROUTES
# -------------------------------------------------
@app.route("/agent")
@role_required("agent")
@subscription_required
def agent_dashboard():
    """
    Agent dashboard - requires authentication and active subscription.
    Shows client list and referral link.
    """
    user = get_current_user()
    user_id = user["id"]
    
    # Get or create referral code for this agent
    referral_code = get_or_create_referral_code(user_id)
    referral_url = f"{request.url_root}homeowner?ref={referral_code}"
    
    # Get client relationships
    clients = get_client_relationships(user_id)
    
    metrics = get_agent_dashboard_metrics(user_id)
    metrics['referral_url'] = referral_url
    metrics['referral_code'] = referral_code
    metrics['clients'] = clients
    
    return render_template("agent/dashboard.html", metrics=metrics, user=user)


@app.route("/agent/settings/profile")
def agent_settings_profile():
    user = get_current_user()
    return render_template(
        "agent/settings_profile.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/agent/crm", methods=["GET", "POST"])
def agent_crm():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        phone = request.form.get("phone", "").strip()
        stage = request.form.get("stage", "new").strip()
        best_contact = email or phone
        last_touch = "Today"
        if name:
            add_agent_contact(
                user_id, name, email, phone, stage, best_contact, last_touch
            )
            flash("Contact added to your CRM.", "success")

    contacts = list_agent_contacts(user_id) if user_id else []

    return render_template(
        "agent/crm.html",
        brand_name=FRONT_BRAND_NAME,
        contacts=contacts,
    )


@app.route("/agent/clients")
def agent_clients():
    return render_template(
        "agent/clients.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/agent/transactions", methods=["GET", "POST"])
def agent_transactions():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        property_address = request.form.get("property_address", "").strip()
        client_name = request.form.get("client_name", "").strip()
        side = request.form.get("side", "buyer").strip()
        stage = request.form.get("stage", "under_contract").strip()
        close_date = request.form.get("close_date", "").strip()

        if property_address and client_name:
            add_agent_transaction(
                user_id, property_address, client_name, side, stage, close_date
            )
            flash("Transaction added to your coordinator view.", "success")

    transactions = list_agent_transactions(user_id) if user_id else []

    return render_template(
        "agent/transactions.html",
        brand_name=FRONT_BRAND_NAME,
        transactions=transactions,
    )


@app.route("/agent/transactions/<int:tx_id>")
def agent_transaction_detail(tx_id: int):
    user = get_current_user()
    user_id = user["id"] if user else None

    tx = get_agent_transaction(user_id, tx_id) if user_id else None
    if not tx:
        abort(404)

    stages = [
        {"key": "under_contract", "label": "Under contract"},
        {"key": "earnest_money", "label": "Earnest money"},
        {"key": "inspection", "label": "Inspection"},
        {"key": "appraisal", "label": "Appraisal"},
        {"key": "loan_commitment", "label": "Loan commitment"},
        {"key": "final_walkthrough", "label": "Final walkthrough"},
        {"key": "closing", "label": "Closing"},
    ]

    return render_template(
        "agent/transaction_detail.html",
        brand_name=FRONT_BRAND_NAME,
        tx=tx,
        stages=stages,
    )


@app.route("/agent/documents")
def agent_documents():
    return render_template(
        "agent/documents.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/agent/communications", methods=["GET", "POST"])
def agent_communications():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        label = request.form.get("label", "").strip()
        category = request.form.get("category", "general").strip()
        channel = request.form.get("channel", "email").strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()

        if label and body:
            add_message_template(
                owner_user_id=user_id,
                role="agent",
                label=label,
                category=category,
                channel=channel,
                subject=subject,
                body=body,
            )
            flash("Template saved.", "success")

    templates = (
        list_message_templates("agent", owner_user_id=user_id) if user_id else []
    )

    return render_template(
        "agent/communications.html",
        brand_name=FRONT_BRAND_NAME,
        templates=templates,
    )


@app.route("/agent/marketing", methods=["GET", "POST"])
def agent_marketing():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        template_type = request.form.get("template_type", "just_listed").strip()
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        content = request.form.get("content", "").strip()

        if name and content:
            add_marketing_template(
                owner_user_id=user_id,
                role="agent",
                template_type=template_type,
                name=name,
                description=description,
                content=content,
            )
            flash("Marketing template saved.", "success")

    templates = (
        list_marketing_templates("agent", owner_user_id=user_id) if user_id else []
    )

    return render_template(
        "agent/marketing.html",
        brand_name=FRONT_BRAND_NAME,
        templates=templates,
    )


@app.route("/agent/power-tools")
def agent_power_tools():
    return render_template(
        "agent/power_tools.html",
        brand_name=FRONT_BRAND_NAME,
    )


# -------------------------------------------------
# LENDER ROUTES
# -------------------------------------------------
@app.route("/lender")
@role_required("lender")
@subscription_required
def lender_dashboard():
    """
    Lender dashboard - requires authentication and active subscription.
    Shows client list and referral link.
    """
    user = get_current_user()
    user_id = user["id"]
    
    # Get or create referral code for this lender
    referral_code = get_or_create_referral_code(user_id)
    referral_url = f"{request.url_root}homeowner?ref={referral_code}"
    
    # Get client relationships
    clients = get_client_relationships(user_id)
    
    metrics = get_lender_dashboard_metrics(user_id)
    metrics['referral_url'] = referral_url
    metrics['referral_code'] = referral_code
    metrics['clients'] = clients
    
    return render_template("lender/dashboard.html", metrics=metrics, user=user)


@app.route("/lender/settings/profile")
def lender_settings_profile():
    user = get_current_user()
    return render_template(
        "lender/settings_profile.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/crm", methods=["GET", "POST"])
def lender_crm():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        name = request.form.get("name", "").strip()
        status = request.form.get("status", "preapproval").strip()
        loan_type = request.form.get("loan_type", "").strip()
        target_payment = request.form.get("target_payment", "").strip()
        last_touch = "Today"

        if name:
            add_lender_borrower(
                user_id, name, status, loan_type, target_payment, last_touch
            )
            flash("Borrower added to your CRM.", "success")

    borrowers = list_lender_borrowers(user_id) if user_id else []

    return render_template(
        "lender/crm.html",
        brand_name=FRONT_BRAND_NAME,
        borrowers=borrowers,
    )


@app.route("/lender/loans", methods=["GET", "POST"])
def lender_loans():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        borrower_name = request.form.get("borrower_name", "").strip()
        status = request.form.get("status", "preapproval").strip()
        loan_type = request.form.get("loan_type", "Conventional").strip()
        target_payment = request.form.get("target_payment", "").strip()
        stage = request.form.get("stage", "preapproval_started").strip()
        close_date = request.form.get("close_date", "").strip()

        if borrower_name:
            add_lender_loan(
                user_id,
                borrower_name,
                status,
                loan_type,
                target_payment,
                stage,
                close_date,
            )
            flash("Loan added to your pipeline.", "success")

    loans = list_lender_loans(user_id) if user_id else []

    return render_template(
        "lender/loans.html",
        brand_name=FRONT_BRAND_NAME,
        loans=loans,
    )


@app.route("/lender/roles")
def lender_roles():
    return render_template(
        "lender/roles.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/lender/documents")
def lender_documents():
    return render_template(
        "lender/documents.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/lender/messages", methods=["GET", "POST"])
def lender_messages():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        label = request.form.get("label", "").strip()
        category = request.form.get("category", "general").strip()
        channel = request.form.get("channel", "email").strip()
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()

        if label and body:
            add_message_template(
                owner_user_id=user_id,
                role="lender",
                label=label,
                category=category,
                channel=channel,
                subject=subject,
                body=body,
            )
            flash("Template saved.", "success")

    templates = (
        list_message_templates("lender", owner_user_id=user_id) if user_id else []
    )

    return render_template(
        "lender/messages.html",
        brand_name=FRONT_BRAND_NAME,
        templates=templates,
    )


@app.route("/lender/marketing", methods=["GET", "POST"])
def lender_marketing():
    """
    Lender marketing hub.

    - GET: show all saved lender marketing templates for the logged-in user
    - POST: create/save a new marketing template
    """
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        template_type = (request.form.get("template_type") or "loan_flyer").strip()
        name = (request.form.get("name") or "").strip()
        description = (request.form.get("description") or "").strip()
        content = (request.form.get("content") or "").strip()

        if name and content:
            add_marketing_template(
                owner_user_id=user_id,
                role="lender",
                template_type=template_type,
                name=name,
                description=description,
                content=content,
            )
            flash("Marketing template saved.", "success")

    templates = (
        list_marketing_templates("lender", owner_user_id=user_id) if user_id else []
    )

    return render_template(
        "lender/marketing.html",
        brand_name=FRONT_BRAND_NAME,
        templates=templates,
    )


@app.route("/lender/power-suite")
def lender_power_suite():
    """
    Lender ‘power suite’ overview page.
    """
    return render_template(
        "lender/power_suite.html",
        brand_name=FRONT_BRAND_NAME,
    )


# -------------------------------------------------
# BOARD VIEW + DEBUG
# -------------------------------------------------




# -------------------------------------------------
# DEV ENTRYPOINT
# -------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
