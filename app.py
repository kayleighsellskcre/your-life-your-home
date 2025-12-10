print('>>> THIS IS THE REAL app.py BEING RUN <<<')

import os
import boto3
from functools import wraps
from typing import Optional, List, Dict
from pathlib import Path
from uuid import uuid4
from datetime import datetime
import sqlite3
import json
from types import SimpleNamespace
from PIL import Image, ImageFilter
import numpy as np
import secrets
import pandas as pd
import io

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
    jsonify,
    Response,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# ---------------- R2 STORAGE CLIENT ----------------
R2_CLIENT = None
if all(
    key in os.environ
    for key in ["R2_ENDPOINT", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY"]
):
    R2_CLIENT = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
    )


# ---------------- SIMPLE IMAGE PROCESSING (NO BACKGROUND REMOVAL) ----------------
def remove_white_background(image_path):
    """Just convert to PNG format - no background removal."""
    try:
        img = Image.open(image_path)

        # Convert to RGB if needed (keep as-is)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")

        # Save as PNG
        img.save(image_path, "PNG", optimize=True)

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
    add_agent_transaction,
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
    add_lender_borrower,
    list_lender_borrowers,
    get_agent_contact,
    update_agent_contact,
    get_lender_borrower,
    update_lender_borrower,
    add_crm_interaction,
    list_crm_interactions,
    log_automated_email,
    get_contacts_for_automated_email,
    add_crm_task,
    list_crm_tasks,
    update_crm_task,
    delete_crm_task,
    add_crm_deal,
    list_crm_deals,
    update_crm_deal,
    delete_crm_deal,
    add_crm_relationship,
    list_crm_relationships,
    delete_crm_relationship,
    add_crm_saved_view,
    list_crm_saved_views,
    delete_crm_saved_view,
)

# ---------------- R2 STORAGE HELPERS ----------------
from r2_storage import (
    upload_file_to_r2,
    get_file_url_from_r2,
    delete_file_from_r2,
    is_r2_enabled,
)

# ---------------- FLASK APP INIT ----------------

# Initialize DBs so platform loads with no manual trigger
init_db()

app = Flask(__name__)
app.secret_key = os.environ.get("YLH_SECRET_KEY", "change-this-secret-key")
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Context processor to make professionals available to all homeowner templates
@app.context_processor
def inject_professionals():
    """Make professionals data available to all templates."""
    from database import get_homeowner_professionals
    professionals = []
    user = get_current_user()
    if user and user.get("role") == "homeowner" and user.get("id"):
        try:
            profs_raw = get_homeowner_professionals(user["id"])
            for prof in profs_raw:
                if hasattr(prof, 'keys'):
                    prof_dict = dict(prof)
                    professionals.append(prof_dict)
                    # Debug: print professional data
                    print(f"DEBUG: Found professional - role: {prof_dict.get('professional_role')}, type: {prof_dict.get('professional_type')}, name: {prof_dict.get('name')}, phone: {prof_dict.get('phone')}")
                else:
                    professionals.append(prof)
        except Exception as e:
            import traceback
            print(f"Error loading professionals in context processor: {traceback.format_exc()}")
    else:
        print(f"DEBUG: Context processor - user: {user}, role: {user.get('role') if user else 'None'}, id: {user.get('id') if user else 'None'}")
    return dict(professionals=professionals)

# ---------------- AJAX PLANNER ROUTE ----------------
@app.route("/homeowner/reno/planner/ajax-add", methods=["POST"])
def homeowner_reno_planner_ajax_add():
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401

    data = request.get_json() or {}
    name = data.get("project_name", "").strip()
    budget = data.get("project_budget")
    status = data.get("project_status", "Planning").strip()
    category = data.get("project_category", "Other").strip()  # Get category, default to "Other"
    board_name = data.get("board_name", "").strip()
    summary = data.get("project_summary", "").strip()

    if not name:
        return jsonify({"success": False, "error": "Project name required"}), 400

    # Convert budget to string (function expects string, not float)
    budget_str = str(budget) if budget else ""

    # Get notes from JSON data
    notes = data.get("project_notes", "").strip()
    
    # If a board_name is provided, save as a design board note as well
    if board_name:
        note_title = name
        note_details = summary or notes or f"Project: {name}"
        add_design_board_note(
            user_id, 
            board_name, 
            note_title, 
            note_details,
            photos=[],
            files=[]
        )

    # Fix: Add category parameter and correct argument order
    # Function signature: user_id, name, category, status, budget, notes
    add_homeowner_project(user_id, name, category, status, budget_str, notes)
    return jsonify({"success": True})


# ---------------- TRANSACTION HELPERS IMPORT ----------------
from transaction_helpers import (
    get_db,
    add_transaction_participant,
    create_transaction,
    get_agent_transactions,
    delete_transaction,
    get_transaction_detail,
    get_transaction_documents,
    get_transaction_participants,
    get_transaction_timeline,
    get_transaction_document_status,
)

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


# Helper to get current user id
def get_current_user_id() -> int:
    """Fallback to demo user for now."""
    return session.get("user_id") or 1


def get_current_user() -> Optional[dict]:
    user_id = session.get("user_id")
    if not user_id:
        return None
    row = get_user_by_id(user_id)
    return dict(row) if row else None


# ---------------- AGENT TRANSACTION ROUTES ----------------
@app.route("/agent/transactions/<int:tx_id>/participants/add", methods=["POST"])
def agent_add_participant(tx_id):
    """Add a participant to an agent transaction."""
    name = request.form.get("participant_name", "").strip()
    email = request.form.get("participant_email", "").strip()
    role = request.form.get("participant_role", "").strip()

    if not name or not email or not role:
        flash("All participant fields are required.", "error")
        return redirect(url_for("agent_transaction_detail", tx_id=tx_id))

    try:
        add_transaction_participant(tx_id, name, email, role)
        flash("Participant added successfully!", "success")
    except Exception as e:
        flash(f"Error adding participant: {e}", "error")

    return redirect(url_for("agent_transaction_detail", tx_id=tx_id))


# -------------------------------------------------
# EMAIL REMINDER AUTOMATION (GMAIL SMTP + APScheduler)
# -------------------------------------------------
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler

EMAIL_HOST = os.environ.get("EMAIL_HOST", "smtp.gmail.com")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", 587))
EMAIL_USER = os.environ.get("EMAIL_USER")
EMAIL_PASS = os.environ.get("EMAIL_PASS")


def send_reminder_email(to_email, subject, body):
    msg = MIMEMultipart()
    msg["From"] = EMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
        print(f"✓ Email sent to {to_email}")
        return True
    except Exception as e:
        print(f"✗ Failed to send email to {to_email}: {e}")
        return False


def get_due_reminders():
    """TODO: Replace with real DB logic to fetch due reminders."""
    return []


def send_due_reminders():
    reminders = get_due_reminders()
    for r in reminders:
        if r.get("email"):
            send_reminder_email(r["email"], r["subject"], r["body"])


# ====================== CRM AUTOMATED EMAIL FUNCTIONS ======================

def get_birthday_contacts():
    """Get contacts with birthdays today."""
    from datetime import datetime
    from database import get_connection
    today = datetime.now()
    today_str = f"{today.month:02d}/{today.day:02d}"
    
    contacts = []
    # Get agent contacts
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT id, agent_user_id, name, email, birthday
        FROM agent_contacts
        WHERE email IS NOT NULL AND email != '' 
          AND auto_birthday = 1
          AND birthday LIKE ?
        """,
        (f"%{today_str}%",)
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'agent_contact',
            'professional_id': row['agent_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    # Get lender borrowers
    cur.execute(
        """
        SELECT id, lender_user_id, name, email, birthday
        FROM lender_borrowers
        WHERE email IS NOT NULL AND email != '' 
          AND auto_birthday = 1
          AND birthday LIKE ?
        """,
        (f"%{today_str}%",)
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'lender_borrower',
            'professional_id': row['lender_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    conn.close()
    return contacts


def get_anniversary_contacts():
    """Get contacts with home anniversaries today."""
    from datetime import datetime
    from database import get_connection
    today = datetime.now()
    today_str = f"{today.month:02d}/{today.day:02d}"
    
    contacts = []
    conn = get_connection()
    cur = conn.cursor()
    
    # Agent contacts
    cur.execute(
        """
        SELECT id, agent_user_id, name, email, home_anniversary, property_address
        FROM agent_contacts
        WHERE email IS NOT NULL AND email != '' 
          AND auto_anniversary = 1
          AND home_anniversary LIKE ?
        """,
        (f"%{today_str}%",)
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'agent_contact',
            'professional_id': row['agent_user_id'],
            'name': row['name'],
            'email': row['email'],
            'property_address': row['property_address']
        })
    
    # Lender borrowers
    cur.execute(
        """
        SELECT id, lender_user_id, name, email, home_anniversary, property_address
        FROM lender_borrowers
        WHERE email IS NOT NULL AND email != '' 
          AND auto_anniversary = 1
          AND home_anniversary LIKE ?
        """,
        (f"%{today_str}%",)
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'lender_borrower',
            'professional_id': row['lender_user_id'],
            'name': row['name'],
            'email': row['email'],
            'property_address': row['property_address']
        })
    
    conn.close()
    return contacts


def send_birthday_emails():
    """Send birthday emails to contacts."""
    if not EMAIL_USER or not EMAIL_PASS:
        return
    
    contacts = get_birthday_contacts()
    for contact in contacts:
        subject = f"🎂 Happy Birthday, {contact['name']}!"
        body = f"""Hi {contact['name']},

Wishing you a wonderful birthday filled with joy and happiness!

Thank you for being part of our community.

Best regards,
Your Life, Your Home Team
"""
        if send_reminder_email(contact['email'], subject, body):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'birthday', contact['email'], subject, 'sent'
            )


def send_anniversary_emails():
    """Send home anniversary emails."""
    if not EMAIL_USER or not EMAIL_PASS:
        return
    
    contacts = get_anniversary_contacts()
    for contact in contacts:
        property_info = f" at {contact.get('property_address', 'your home')}" if contact.get('property_address') else ""
        subject = f"🏠 Happy Home Anniversary, {contact['name']}!"
        body = f"""Hi {contact['name']},

Congratulations on your home anniversary{property_info}!

We hope you're enjoying your home and creating wonderful memories.

Best regards,
Your Life, Your Home Team
"""
        if send_reminder_email(contact['email'], subject, body):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'anniversary', contact['email'], subject, 'sent'
            )


def send_seasonal_checklists():
    """Send seasonal home maintenance checklists."""
    if not EMAIL_USER or not EMAIL_PASS:
        return
    
    from datetime import datetime
    from database import get_connection
    month = datetime.now().month
    
    # Determine season
    if month in [12, 1, 2]:
        season = "Winter"
        checklist = """Winter Home Maintenance Checklist:
• Check heating system and change filters
• Inspect roof for ice dams
• Seal windows and doors
• Test smoke and carbon monoxide detectors
• Clean gutters and downspouts
• Insulate pipes to prevent freezing
• Check weatherstripping
• Service snow removal equipment"""
    elif month in [3, 4, 5]:
        season = "Spring"
        checklist = """Spring Home Maintenance Checklist:
• Clean gutters and downspouts
• Inspect roof for winter damage
• Service air conditioning system
• Check exterior paint and siding
• Clean windows and screens
• Inspect deck and patio
• Fertilize lawn and garden
• Check irrigation system"""
    elif month in [6, 7, 8]:
        season = "Summer"
        checklist = """Summer Home Maintenance Checklist:
• Service air conditioning
• Check and clean outdoor spaces
• Inspect and clean pool/spa if applicable
• Check for pest issues
• Maintain landscaping
• Inspect exterior for damage
• Check outdoor lighting
• Prepare for storm season"""
    else:  # 9, 10, 11
        season = "Fall"
        checklist = """Fall Home Maintenance Checklist:
• Clean gutters and downspouts
• Inspect roof and chimney
• Service heating system
• Seal windows and doors
• Check insulation
• Winterize outdoor plumbing
• Rake leaves and maintain yard
• Test smoke detectors"""
    
    # Get contacts with seasonal emails enabled
    contacts = []
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        SELECT id, agent_user_id, name, email
        FROM agent_contacts
        WHERE email IS NOT NULL AND email != '' AND auto_seasonal = 1
        """
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'agent_contact',
            'professional_id': row['agent_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    cur.execute(
        """
        SELECT id, lender_user_id, name, email
        FROM lender_borrowers
        WHERE email IS NOT NULL AND email != '' AND auto_seasonal = 1
        """
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'lender_borrower',
            'professional_id': row['lender_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    conn.close()
    
    # Send to all contacts (only once per season - you may want to track this)
    for contact in contacts:
        subject = f"🍂 {season} Home Maintenance Checklist"
        body = f"""Hi {contact['name']},

Here's your {season.lower()} home maintenance checklist to keep your home in great shape:

{checklist}

Stay safe and enjoy the season!

Best regards,
Your Life, Your Home Team
"""
        if send_reminder_email(contact['email'], subject, body):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'seasonal', contact['email'], subject, 'sent'
            )


def send_equity_updates():
    """Send equity update emails based on frequency."""
    if not EMAIL_USER or not EMAIL_PASS:
        return
    
    from datetime import datetime
    from database import get_connection
    today = datetime.now()
    
    # Only send on 1st of month for monthly, 1st of odd months for bimonthly, etc.
    if today.day != 1:
        return
    
    contacts = []
    conn = get_connection()
    cur = conn.cursor()
    
    # Monthly contacts
    if today.month % 1 == 0:  # Every month
        cur.execute(
            """
            SELECT id, agent_user_id, name, email, property_address, 
                   property_value, equity_estimate
            FROM agent_contacts
            WHERE email IS NOT NULL AND email != '' 
              AND auto_equity = 1 
              AND equity_frequency = 'monthly'
              AND equity_estimate IS NOT NULL
            """
        )
        for row in cur.fetchall():
            contacts.append(dict(row) | {'type': 'agent_contact', 'professional_id': row['agent_user_id']})
    
    # Bimonthly contacts (odd months)
    if today.month % 2 == 1:
        cur.execute(
            """
            SELECT id, agent_user_id, name, email, property_address,
                   property_value, equity_estimate
            FROM agent_contacts
            WHERE email IS NOT NULL AND email != '' 
              AND auto_equity = 1 
              AND equity_frequency = 'bimonthly'
              AND equity_estimate IS NOT NULL
            """
        )
        for row in cur.fetchall():
            contacts.append(dict(row) | {'type': 'agent_contact', 'professional_id': row['agent_user_id']})
    
    # Quarterly contacts (Jan, Apr, Jul, Oct)
    if today.month in [1, 4, 7, 10]:
        cur.execute(
            """
            SELECT id, agent_user_id, name, email, property_address,
                   property_value, equity_estimate
            FROM agent_contacts
            WHERE email IS NOT NULL AND email != '' 
              AND auto_equity = 1 
              AND equity_frequency = 'quarterly'
              AND equity_estimate IS NOT NULL
            """
        )
        for row in cur.fetchall():
            contacts.append(dict(row) | {'type': 'agent_contact', 'professional_id': row['agent_user_id']})
    
    # Same for lender borrowers
    if today.month % 1 == 0:
        cur.execute(
            """
            SELECT id, lender_user_id, name, email, property_address,
                   loan_amount, loan_rate
            FROM lender_borrowers
            WHERE email IS NOT NULL AND email != '' 
              AND auto_equity = 1 
              AND equity_frequency = 'monthly'
            """
        )
        for row in cur.fetchall():
            contacts.append(dict(row) | {'type': 'lender_borrower', 'professional_id': row['lender_user_id']})
    
    conn.close()
    
    for contact in contacts:
        equity = contact.get('equity_estimate', 0)
        property_val = contact.get('property_value', 0)
        subject = f"💰 Your Home Equity Update - {today.strftime('%B %Y')}"
        body = f"""Hi {contact['name']},

Here's your monthly equity update:

Property: {contact.get('property_address', 'Your Home')}
Estimated Value: ${property_val:,.0f}
Estimated Equity: ${equity:,.0f}

Your home equity continues to grow! This represents significant wealth you've built.

Best regards,
Your Life, Your Home Team
"""
        if send_reminder_email(contact['email'], subject, body):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'equity', contact['email'], subject, 'sent'
            )


def send_holiday_greetings():
    """Send holiday greeting emails."""
    if not EMAIL_USER or not EMAIL_PASS:
        return
    
    from datetime import datetime
    from database import get_connection
    today = datetime.now()
    
    # Only send on specific holidays
    holidays = {
        (12, 25): "Merry Christmas",
        (12, 31): "Happy New Year",
        (7, 4): "Happy 4th of July",
        (11, 25): "Happy Thanksgiving",  # Approximate
    }
    
    holiday = holidays.get((today.month, today.day))
    if not holiday:
        return
    
    contacts = []
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """
        SELECT id, agent_user_id, name, email
        FROM agent_contacts
        WHERE email IS NOT NULL AND email != '' AND auto_holidays = 1
        """
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'agent_contact',
            'professional_id': row['agent_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    cur.execute(
        """
        SELECT id, lender_user_id, name, email
        FROM lender_borrowers
        WHERE email IS NOT NULL AND email != '' AND auto_holidays = 1
        """
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'lender_borrower',
            'professional_id': row['lender_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    conn.close()
    
    for contact in contacts:
        subject = f"🎄 {holiday}, {contact['name']}!"
        body = f"""Hi {contact['name']},

{holiday}! We hope you have a wonderful celebration with family and friends.

Thank you for being part of our community.

Best regards,
Your Life, Your Home Team
"""
        if send_reminder_email(contact['email'], subject, body):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'holiday', contact['email'], subject, 'sent'
            )


def start_scheduler():
    """Start background scheduler safely without blocking app startup."""
    try:
        scheduler = BackgroundScheduler()
        scheduler.add_job(send_due_reminders, "cron", hour=12, minute=0)
        # CRM automated emails
        scheduler.add_job(send_birthday_emails, "cron", hour=9, minute=0)  # 9 AM daily
        scheduler.add_job(send_anniversary_emails, "cron", hour=9, minute=5)  # 9:05 AM daily
        scheduler.add_job(send_seasonal_checklists, "cron", day=1, hour=10, minute=0)  # 1st of month, 10 AM
        scheduler.add_job(send_equity_updates, "cron", day=1, hour=10, minute=5)  # 1st of month, 10:05 AM
        scheduler.add_job(send_holiday_greetings, "cron", hour=9, minute=10)  # 9:10 AM daily
        scheduler.start()
        print("✓ Reminder scheduler started with CRM automation.")
    except Exception as e:
        print(f"⚠ Scheduler could not start (non-critical): {e}")


# Start scheduler when app starts (non-blocking)
try:
    start_scheduler()
except Exception as e:
    print(f"⚠ Scheduler initialization failed (non-critical): {e}")


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
# HOMEOWNER SNAPSHOT + CRM METRICS
# -------------------------------------------------
def calculate_appreciated_value(
    initial_value: float, purchase_date: str, annual_rate: float = 0.035
) -> float:
    """
    Calculate home value with automatic appreciation over time.
    """
    if not initial_value or not purchase_date:
        return initial_value

    try:
        if isinstance(purchase_date, str):
            purchase_dt = datetime.strptime(purchase_date.split()[0], "%Y-%m-%d")
        else:
            purchase_dt = purchase_date

        today = datetime.now()
        years_elapsed = (today - purchase_dt).days / 365.25
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
    transactions = get_agent_transactions(user_id)
    
    # Convert Row objects to dicts if needed
    contacts_list = []
    for c in contacts:
        if hasattr(c, 'keys'):
            contacts_list.append(dict(c))
        else:
            contacts_list.append(c)
    
    return {
        "new_leads": sum((c1.get("stage") or "") == "new" for c1 in contacts_list),
        "active_transactions": len(transactions) if transactions else 0,
        "followups_today": max(len(contacts_list) // 2, 0),
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
    
    # Convert Row objects to dicts if needed
    borrowers_list = []
    for b in borrowers:
        if hasattr(b, 'keys'):
            borrowers_list.append(dict(b))
        else:
            borrowers_list.append(b)
    
    return {
        "new_applications": sum(
            (b1.get("status") or "") == "preapproval" for b1 in borrowers_list
        ),
        "loans_in_process": len(loans) if loans else 0,
        "nurture_contacts": max(len(borrowers_list) // 2, 0),
    }


# -------------------------------------------------
# MAIN / AUTH
# -------------------------------------------------
@app.route("/r/<referral_code>")
def referral_landing(referral_code):
    """
    Public landing page for agent/lender referral links.
    Shows professional info and home equity signup form.
    """
    from database import get_professional_by_referral_code
    
    professional = get_professional_by_referral_code(referral_code)
    
    if not professional:
        flash("Invalid referral link.", "error")
        return redirect(url_for("index"))
    
    # Store referral code in session for signup
    session["referral_code"] = referral_code
    
    # Convert to dict if needed
    if hasattr(professional, 'keys'):
        prof_dict = dict(professional)
    else:
        prof_dict = professional if professional else {}
    
    return render_template(
        "public/referral_landing.html",
        brand_name=FRONT_BRAND_NAME,
        professional=prof_dict,
        referral_code=referral_code
    )


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
    Tracks referral codes from ?ref=CODE parameter
    """
    role = request.args.get("role", "homeowner")
    if role not in ("homeowner", "agent", "lender"):
        role = "homeowner"
    
    # Get referral code from query parameter or session
    referral_code = request.args.get("ref") or session.get("referral_code")

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role_from_form = request.form.get("role", role)
        referral_code_from_form = request.form.get("referral_code") or referral_code

        if role_from_form in ("homeowner", "agent", "lender"):
            role = role_from_form

        if not email or not password:
            flash("Please fill in email and password.", "error")
            return redirect(url_for("signup", role=role, ref=referral_code_from_form))

        password_hash = generate_password_hash(password)

        try:
            user_id = create_user(name, email, password_hash, role)
        except Exception:
            flash("That email is already in use. Please sign in instead.", "error")
            return redirect(url_for("login"))

        # If homeowner signed up with a referral code, create relationship
        if role == "homeowner" and referral_code_from_form:
            from database import (
                get_professional_by_referral_code,
                create_client_relationship
            )
            professional = get_professional_by_referral_code(referral_code_from_form)
            if professional:
                create_client_relationship(
                    homeowner_id=user_id,
                    professional_id=professional["user_id"],
                    professional_role=professional["role"],
                    referral_code=referral_code_from_form
                )

        session["user_id"] = user_id
        session["role"] = role
        session["name"] = name or "Friend"
        session.pop("referral_code", None)  # Clear referral code from session

        if role == "agent":
            return redirect(url_for("agent_dashboard"))
        elif role == "lender":
            return redirect(url_for("lender_dashboard"))
        else:
            return redirect(url_for("homeowner_overview"))

    return render_template(
        "auth/signup.html", 
        role=role, 
        brand_name=FRONT_BRAND_NAME,
        referral_code=referral_code
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    role = request.args.get("role")
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
# HOMEOWNER ROUTES
# -------------------------------------------------
@app.route("/homeowner")
def homeowner_overview():
    """
    Overview dashboard (My Home Base).
    Shows agent/lender info if homeowner was referred.
    """
    from database import get_homeowner_professionals
    
    user = get_current_user()
    snapshot = get_homeowner_snapshot_or_default(user)
    
    # Get associated professionals
    professionals = []
    if user and user.get("id"):
        profs_raw = get_homeowner_professionals(user["id"])
        for prof in profs_raw:
            if hasattr(prof, 'keys'):
                professionals.append(dict(prof))
            else:
                professionals.append(prof)

    return render_template(
        "homeowner/overview.html",
        brand_name=FRONT_BRAND_NAME,
        snapshot=snapshot,
        cloud_cma_url=CLOUD_CMA_URL,
        professionals=professionals,
    )


@app.route("/homeowner/recent-activity")
def homeowner_recent_activity():
    return render_template(
        "homeowner/recent_activity.html",
        brand_name=FRONT_BRAND_NAME,
    )


# ----- SAVED NOTES / DESIGN BOARDS -----
@app.route("/homeowner/saved-notes", methods=["GET", "POST"])
def homeowner_saved_notes():
    """
    Manage premium mood boards for homeowners with advanced features like
    color palettes, vision statements, templates, and drag-and-drop uploads.
    """
    user_id = get_current_user_id()
    print(f"[DEBUG][SAVED NOTES] user_id: {user_id}")
    raw_boards = get_design_boards_for_user(user_id)
    print(
        f"[DEBUG][SAVED NOTES] get_design_boards_for_user({user_id}) returned: {raw_boards}"
    )

    design_dir = BASE_DIR / "static" / "uploads" / "design_boards"
    design_dir.mkdir(parents=True, exist_ok=True)

    if request.method == "POST":
        action = request.form.get("action") or "create_board"

        # ---------- CREATE BOARD ----------
        if action == "create_board":
            board_name = (request.form.get("board_name") or "").strip()
            vision_statement = (request.form.get("vision_statement") or "").strip()
            board_title = (request.form.get("board_title") or "").strip()
            board_notes = (request.form.get("board_notes") or "").strip()
            board_links = (request.form.get("board_links") or "").strip()

            if not board_name:
                flash("Please provide a board name.", "error")
                return redirect(url_for("homeowner_saved_notes"))

            # Photos
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
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    saved_photos.append(rel_path)
                except Exception:
                    flash(f"Could not save file: {safe_name}", "error")

            # Fixtures
            saved_fixtures = []
            fixture_files = request.files.getlist("board_fixtures")
            for f in fixture_files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                base_name = Path(safe_name).stem
                unique_name = f"{uuid4().hex}_fixture_{base_name}.png"
                save_path = design_dir / unique_name
                try:
                    f.save(save_path)
                    remove_white_background(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    saved_fixtures.append(rel_path)
                except Exception:
                    flash(f"Could not save fixture: {safe_name}", "error")

            colors = request.form.getlist("colors[]")
            color_palette = [c for c in colors if c]

            try:
                add_design_board_note(
                    user_id=user_id,
                    project_name=board_name,
                    title=board_title,
                    details=f"{board_notes}\n\nLinks:\n{board_links}"
                    if board_links
                    else board_notes,
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
            except Exception:
                flash("Could not create the board. Please try again.", "error")

            return redirect(url_for("homeowner_saved_notes", view=board_name))

        # ---------- EDIT BOARD ----------
        if action == "edit_board":
            board_name = (request.form.get("board_name") or "").strip()
            if not board_name:
                flash("Missing board name.", "error")
                return redirect(url_for("homeowner_saved_notes"))

            # Remove photos
            remove_photos_list = request.form.getlist("remove_photos")
            if remove_photos_list:
                try:
                    remove_photos_from_board(user_id, board_name, remove_photos_list)
                    for p in remove_photos_list:
                        try:
                            ppath = BASE_DIR / "static" / p
                            if ppath.exists():
                                ppath.unlink()
                        except Exception:
                            pass
                except Exception:
                    flash("Could not remove some photos.", "error")

            # Remove fixtures
            remove_fixtures_list = request.form.getlist("remove_fixtures")
            if remove_fixtures_list:
                try:
                    from database import remove_fixtures_from_board

                    remove_fixtures_from_board(
                        user_id, board_name, remove_fixtures_list
                    )
                    for f in remove_fixtures_list:
                        try:
                            fpath = BASE_DIR / "static" / f
                            if fpath.exists():
                                fpath.unlink()
                        except Exception:
                            pass
                except Exception:
                    flash("Could not remove some fixtures.", "error")

            # New photos
            new_photos = []
            files = request.files.getlist("new_photos")
            for f in files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                unique_name = f"{uuid4().hex}_{safe_name}"
                save_path = (
                    BASE_DIR / "static" / "uploads" / "design_boards" / unique_name
                )
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    f.save(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    new_photos.append(rel_path)
                except Exception:
                    flash(f"Could not save file: {safe_name}", "error")

            # New fixtures
            new_fixtures = []
            fixture_files = request.files.getlist("new_fixtures")
            for f in fixture_files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                base_name = Path(safe_name).stem
                unique_name = f"{uuid4().hex}_fixture_{base_name}.png"
                save_path = (
                    BASE_DIR / "static" / "uploads" / "design_boards" / unique_name
                )
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    f.save(save_path)
                    remove_white_background(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    new_fixtures.append(rel_path)
                except Exception:
                    flash(f"Could not save fixture: {safe_name}", "error")

            edit_title = (request.form.get("edit_title") or "").strip()
            edit_notes = (request.form.get("edit_notes") or "").strip()

            # New colors
            new_colors = request.form.getlist("new_colors[]")
            if new_colors:
                color_palette = [c for c in new_colors if c]
                try:
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

        # ---------- DELETE BOARD ----------
        if action == "delete_board":
            board_name = (request.form.get("board_name") or "").strip()
            if board_name:
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

    # ---------- GET: LIST & VIEW BOARDS ----------
    boards = get_design_boards_for_user(user_id) or []
    board_details = {}
    for b in boards:
        try:
            details = get_design_board_details(user_id, b)
            board_details[b] = details or {
                "project_name": b,
                "photos": [],
                "notes": [],
                "files": [],
            }
        except Exception:
            board_details[b] = {
                "project_name": b,
                "photos": [],
                "notes": [],
                "files": [],
            }

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




@app.route("/homeowner/design-boards/<path:board_name>", methods=["GET"])
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
    """Render a print-optimized view of a single board."""
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
        from weasyprint import HTML

        pdf = HTML(string=html, base_url=str(BASE_DIR / "static")).write_pdf()
        return Response(
            pdf,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{board_name}.pdf"'
            },
        )
    except Exception:
        flash(
            "WeasyPrint not available: rendering HTML. Install WeasyPrint to enable PDF downloads.",
            "info",
        )
        return html


@app.route("/homeowner/design-boards/<path:board_name>/duplicate", methods=["POST"])
def homeowner_design_board_duplicate(board_name):
    """Duplicate an existing board with a new name."""
    user_id = get_current_user_id()
    new_name = request.form.get("new_name", f"{board_name} (Copy)").strip()

    if not new_name:
        flash("New board name is required.", "error")
        return redirect(url_for("homeowner_design_board_view", board_name=board_name))

    try:
        duplicate_design_board(user_id, board_name, new_name)
        flash(f"✨ Board duplicated as '{new_name}'!", "success")
        return redirect(url_for("homeowner_design_board_view", board_name=new_name))
    except Exception:
        flash("Could not duplicate board.", "error")
        return redirect(url_for("homeowner_design_board_view", board_name=board_name))


@app.route("/homeowner/design-boards/<path:board_name>/privacy", methods=["POST"])
def homeowner_design_board_privacy(board_name):
    """Toggle privacy settings for a board."""
    user_id = get_current_user_id()
    is_private = int(request.form.get("is_private", 0))

    shareable_link = None
    if not is_private:
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


# ----- HOME TIMELINE & DOCUMENTS -----
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
    return send_from_directory(
        HOMEOWNER_DOCS_DIR, row["file_name"], as_attachment=False
    )


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

    return render_template(
        "homeowner/document_replace.html",
        document=row,
    )


@app.route("/homeowner/upload-documents", methods=["GET", "POST"])
def homeowner_upload_documents():
    user_id = get_current_user_id()
    docs = list_homeowner_documents(user_id)
    events = list_timeline_events(user_id)

    # DELETE FILE
    if request.method == "POST" and request.form.get("delete_id"):
        delete_id = request.form["delete_id"]
        delete_homeowner_document(delete_id)
        flash("Document removed.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    # REATTACH / REUPLOAD
    if (
        request.method == "POST"
        and request.form.get("reattach_id")
        and request.files.get("file")
    ):
        doc_id = request.form["reattach_id"]
        new_file = request.files["file"]
        save_name = secure_filename(new_file.filename)
        HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        new_file.save(HOMEOWNER_DOCS_DIR / save_name)
        update_homeowner_document_file(doc_id, save_name)
        flash("File updated.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    # NORMAL UPLOAD
    if request.method == "POST" and request.files.get("file"):
        file = request.files["file"]
        category = request.form.get("category", "Other")
        title = request.form.get("title", "").strip() or file.filename

        if not file or file.filename == "":
            flash("Please choose a file to upload.", "error")
            return redirect(url_for("homeowner_upload_documents"))

        filename = secure_filename(file.filename)

        # If using R2, upload there; else save locally
        if is_r2_enabled() and R2_CLIENT:
            r2_key = f"homeowner_docs/{user_id}/{uuid4().hex}_{filename}"
            upload_file_to_r2(file, r2_key)
            stored_name = filename  # For DB reference, still keep original name
        else:
            HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)
            save_path = HOMEOWNER_DOCS_DIR / filename
            file.save(save_path)
            r2_key = None
            stored_name = filename

        add_homeowner_document(
            user_id=user_id,
            title=title,
            category=category,
            file_name=stored_name,
            r2_key=r2_key,
        )
        flash("Document uploaded.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    return render_template(
        "homeowner/upload_documents.html",
        brand_name=FRONT_BRAND_NAME,
        documents=docs,
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

    properties = get_user_properties(user["id"])

    # Determine which property to display
    property_id_param = request.args.get("property_id")
    if property_id_param:
        try:
            current_property_id = int(property_id_param)
            current_property = get_property_by_id(current_property_id)
            if not current_property or current_property["user_id"] != user["id"]:
                current_property = None
                current_property_id = None
        except Exception:
            current_property = None
            current_property_id = None
    else:
        current_property = get_primary_property(user["id"])
        current_property_id = current_property["id"] if current_property else None

    # If no property exists, create a default one
    if not current_property:
        if not properties:
            default_address = "My Home"
            property_id = add_property(user["id"], default_address, None, "primary")
            current_property = get_property_by_id(property_id)
            current_property_id = property_id
            properties = [current_property]
        else:
            current_property = properties[0]
            current_property_id = current_property["id"]

    if request.method == "POST":
        def safe_float(val):
            if not val or val.strip() == "":
                return None
            try:
                return float(val.replace(",", ""))
            except Exception:
                return None

        value_estimate = safe_float(request.form.get("value_estimate", ""))
        loan_balance = safe_float(request.form.get("loan_balance", ""))
        loan_rate = safe_float(request.form.get("loan_rate", ""))
        loan_payment = safe_float(request.form.get("loan_payment", ""))
        loan_term_years = safe_float(request.form.get("loan_term_years", ""))
        loan_start_date = request.form.get("loan_start_date", "").strip() or None

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

        if value_estimate is not None:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE properties SET estimated_value = ? WHERE id = ?",
                (value_estimate, current_property_id),
            )
            conn.commit()
            conn.close()

        flash("Loan details updated successfully!", "success")
        return redirect(
            url_for(
                "homeowner_value_equity_overview",
                property_id=current_property_id,
            )
        )

    # GET: Display current data with calculations
    snapshot = get_homeowner_snapshot_for_property(user["id"], current_property_id)

    if not snapshot.get("value_estimate") and current_property.get("estimated_value"):
        snapshot["value_estimate"] = current_property["estimated_value"]

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

    # LTV
    ltv = 0
    if current_value > 0 and loan_balance > 0:
        ltv = (loan_balance / current_value) * 100

    # Years remaining and payoff date
    years_remaining = 0
    payoff_date = ""
    if loan_start_date and loan_term_years > 0:
        from datetime import timedelta

        try:
            start = datetime.fromisoformat(loan_start_date)
            end = start + timedelta(days=365.25 * loan_term_years)
            payoff_date = end.strftime("%b %Y")

            now = datetime.now()
            years_remaining = (end - now).days / 365.25
            if years_remaining < 0:
                years_remaining = 0
        except Exception:
            pass

    # Appreciation
    annual_appreciation_rate = 0.04  # 4%
    monthly_appreciation = (
        (current_value * annual_appreciation_rate) / 12 if current_value > 0 else 0
    )
    one_year_value = (
        current_value * (1 + annual_appreciation_rate) if current_value > 0 else 0
    )
    five_year_value = (
        current_value * ((1 + annual_appreciation_rate) ** 5)
        if current_value > 0
        else 0
    )

    estimated_down_payment = equity_estimate * 0.2 if equity_estimate > 0 else 0
    wealth_built = equity_estimate if equity_estimate > 0 else 0

    # Refi scenario
    current_rate_market = 6.0
    refinance_savings = 0
    new_monthly_payment = 0
    if loan_rate > 0 and loan_balance > 0 and loan_rate > current_rate_market:
        rate_diff = loan_rate - current_rate_market
        annual_savings = loan_balance * (rate_diff / 100)
        refinance_savings = annual_savings / 12
        if loan_payment > 0:
            new_monthly_payment = loan_payment - refinance_savings

    # Cash-out
    max_cash_out = 0
    if current_value > 0:
        max_loan_80_ltv = current_value * 0.80
        max_cash_out = (
            max_loan_80_ltv - loan_balance if max_loan_80_ltv > loan_balance else 0
        )

    # Rental income estimate
    monthly_rental_estimate = current_value * 0.009 if current_value > 0 else 0
    annual_rental_income = monthly_rental_estimate * 12

    # Extra payment scenario
    extra_payment_amount = 200
    interest_saved_extra = 0
    time_saved_months = 0
    if loan_balance > 0 and loan_rate > 0 and years_remaining > 0:
        time_saved_months = min(years_remaining * 12 * 0.15, 60)
        interest_saved_extra = extra_payment_amount * time_saved_months * 0.5

    tips = []
    if loan_rate > 6.5:
        tips.append(
            "🎯 Your interest rate is above 6.5%. Consider exploring refinance options to lower your monthly payment."
        )

    if years_remaining > 20 and equity_estimate > 50000:
        tips.append(
            "💡 With significant equity and many years remaining, making extra principal payments could save thousands in interest."
        )

    if ltv < 80 and loan_balance > 0:
        tips.append(
            "✨ Your loan-to-value ratio is below 80%. You may qualify to remove PMI if you're paying it."
        )

    if equity_estimate > 100000:
        tips.append(
            "🏡 You've built substantial equity! This could support renovations, debt consolidation, or future investment opportunities."
        )

    if refinance_savings > 50:
        tips.append(
            f"💰 Refinancing at current market rates could save you approximately ${refinance_savings:,.0f}/month."
        )

    if max_cash_out > 50000:
        tips.append(
            f"🏦 You could access up to ${max_cash_out:,.0f} through a cash-out refinance while staying at 80% LTV."
        )

    if not tips:
        tips.append(
            "📊 Enter your complete loan details above to receive personalized savings tips and strategies."
        )

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

    estimated_value = None
    value_str = request.form.get("estimated_value", "").strip()
    if value_str:
        try:
            estimated_value = float(value_str.replace(",", ""))
        except Exception:
            pass

    property_type = request.form.get("property_type", "primary").strip()

    property_id = add_property(user["id"], address, estimated_value, property_type)
    set_primary_property(user["id"], property_id)

    flash(f"Property '{address}' added successfully!", "success")
    return redirect(
        url_for("homeowner_value_equity_overview", property_id=property_id)
    )


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
    except Exception:
        flash("Invalid property ID.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))

    prop = get_property_by_id(property_id)
    if not prop or prop["user_id"] != user["id"]:
        flash("Property not found.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))

    set_primary_property(user["id"], property_id)

    flash(f"Switched to {prop['address']}", "success")
    return redirect(
        url_for("homeowner_value_equity_overview", property_id=property_id)
    )


# ----- RENOVATION & IMPROVEMENT -----
@app.route("/homeowner/reno/planner", methods=["GET", "POST"])
def homeowner_reno_planner():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        name = request.form.get("project_name", "").strip()
        budget_raw = (
            request.form.get("project_budget", "").replace(",", "").strip()
        )
        status = request.form.get("project_status", "Planning").strip()
        category = request.form.get("project_category", "Other").strip()  # Get category, default to "Other"
        notes = request.form.get("project_notes", "").strip()

        # Convert budget to string (function expects string, not float)
        budget_str = budget_raw if budget_raw else ""

        if name:
            # Fix: Add category parameter and correct argument order
            # Function signature: user_id, name, category, status, budget, notes
            add_homeowner_project(user_id, name, category, status, budget_str, notes)
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


@app.route("/homeowner/reno/material-cost", methods=["GET"])
def homeowner_reno_material_cost():
    return render_template(
        "homeowner/reno_material_cost.html",
        brand_name=FRONT_BRAND_NAME,
    )

@app.route("/agent", methods=["GET"])
def agent_dashboard():
    """Agent dashboard view."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    try:
        metrics = get_agent_dashboard_metrics(user["id"])
        transactions = get_agent_transactions(user["id"])
        
        # Ensure transactions are dicts (get_agent_transactions should already return dicts)
        if transactions:
            transactions_list = []
            for tx in transactions:
                if hasattr(tx, 'keys') and not isinstance(tx, dict):
                    transactions_list.append(dict(tx))
                else:
                    transactions_list.append(tx)
            transactions = transactions_list
    except Exception as e:
        import traceback
        print(f"Error in agent_dashboard: {traceback.format_exc()}")
        flash(f"Error loading dashboard: {str(e)}", "error")
        metrics = {"new_leads": 0, "active_transactions": 0, "followups_today": 0}
        transactions = []

    return render_template(
        "agent/dashboard.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        metrics=metrics,
        transactions=transactions,
    )

@app.route("/lender", methods=["GET"])
def lender_dashboard():
    """Lender dashboard view."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    metrics = get_lender_dashboard_metrics(user["id"])
    
    # Convert Row objects to dicts if needed
    loans_raw = list_lender_loans(user["id"])
    loans = []
    for loan in loans_raw:
        if hasattr(loan, 'keys'):
            loans.append(dict(loan))
        else:
            loans.append(loan)
    
    borrowers_raw = list_lender_borrowers(user["id"])
    borrowers = []
    for borrower in borrowers_raw:
        if hasattr(borrower, 'keys'):
            borrowers.append(dict(borrower))
        else:
            borrowers.append(borrower)

    return render_template(
        "lender/dashboard.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        metrics=metrics,
        loans=loans,
        borrowers=borrowers,
    )


# -------------------------------------------------
# AGENT ROUTES
# -------------------------------------------------
@app.route("/agent/crm", methods=["GET", "POST"])
def agent_crm():
    """Agent CRM - comprehensive contact management with automated emails."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "agent":
            return redirect(url_for("login", role="agent"))
    except Exception as e:
        import traceback
        print(f"Error in agent_crm (user check): {traceback.format_exc()}")
        return f"Error: {e}", 500

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        print(f"\n=== POST REQUEST RECEIVED ===")
        print(f"Action: '{action}'")
        print(f"Form data keys: {list(request.form.keys())}")
        print(f"User ID: {user.get('id')}")
        
        if action == "add":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            stage = request.form.get("stage", "new").strip()
            birthday = request.form.get("birthday", "").strip()
            home_anniversary = request.form.get("home_anniversary", "").strip()
            address = request.form.get("address", "").strip()
            notes = request.form.get("notes", "").strip()
            tags = request.form.get("tags", "").strip()
            property_address = request.form.get("property_address", "").strip()
            property_value = request.form.get("property_value", "").strip()
            equity_estimate = request.form.get("equity_estimate", "").strip()
            
            print(f"Name: '{name}'")
            print(f"Email: '{email}'")
            print(f"Phone: '{phone}'")
            print(f"Stage: '{stage}'")
            
            if not name:
                print("ERROR: Name is required but empty")
                flash("Name is required!", "error")
                return redirect(url_for("agent_crm"))
            else:
                try:
                    prop_val = float(property_value) if property_value else None
                    equity_val = float(equity_estimate) if equity_estimate else None
                    print(f"Calling add_agent_contact with user_id={user['id']}, name='{name}'")
                    contact_id = add_agent_contact(
                        user["id"], name, email, phone, stage, email or phone, "",
                        birthday, home_anniversary, address, notes, tags,
                        property_address, prop_val, equity_val
                    )
                    print(f"SUCCESS: Contact added with ID {contact_id}")
                    
                    # If email provided, try to link to existing homeowner account
                    if email:
                        from database import get_user_by_email, create_client_relationship, get_or_create_referral_code
                        homeowner = get_user_by_email(email)
                        if homeowner and homeowner.get("role") == "homeowner":
                            # Create relationship
                            referral_code = get_or_create_referral_code(user["id"], "agent")
                            create_client_relationship(
                                homeowner_id=homeowner["id"],
                                professional_id=user["id"],
                                professional_role="agent",
                                referral_code=referral_code
                            )
                            flash(f"Contact added and linked to homeowner account ({email})!", "success")
                        else:
                            flash("Contact added successfully!", "success")
                    else:
                        flash("Contact added successfully!", "success")
                    return redirect(url_for("agent_crm"))
                except Exception as e:
                    import traceback
                    error_trace = traceback.format_exc()
                    print(f"ERROR adding contact: {error_trace}")
                    flash(f"Error adding contact: {str(e)}", "error")
                    return redirect(url_for("agent_crm"))
        
        elif action == "update":
            contact_id = request.form.get("contact_id")
            if contact_id:
                updates = {}
                for field in ['name', 'email', 'phone', 'stage', 'birthday', 
                            'home_anniversary', 'address', 'notes', 'tags',
                            'property_address', 'property_value', 'equity_estimate',
                            'auto_birthday', 'auto_anniversary',
                            'auto_seasonal', 'auto_equity', 'auto_holidays',
                            'equity_frequency']:
                    val = request.form.get(field, "").strip()
                    if val or field in ['auto_birthday', 'auto_anniversary', 
                                       'auto_seasonal', 'auto_equity', 'auto_holidays']:
                        if field in ['auto_birthday', 'auto_anniversary', 
                                    'auto_seasonal', 'auto_equity', 'auto_holidays']:
                            updates[field] = 1 if request.form.get(field) else 0
                        elif field in ['property_value', 'equity_estimate']:
                            try:
                                updates[field] = float(val) if val else None
                            except:
                                pass
                        else:
                            updates[field] = val if val else None
                
                try:
                    update_agent_contact(int(contact_id), user["id"], **updates)
                    flash("Contact updated successfully!", "success")
                except Exception as e:
                    flash(f"Error updating contact: {e}", "error")
                    import traceback
                    print(f"Error updating contact: {traceback.format_exc()}")
        
        elif action == "add_interaction":
            contact_id = request.form.get("contact_id")
            interaction_type = request.form.get("interaction_type", "").strip()
            subject = request.form.get("subject", "").strip()
            notes = request.form.get("notes", "").strip()
            channel = request.form.get("channel", "email").strip()
            
            if contact_id and interaction_type:
                try:
                    add_crm_interaction(
                        int(contact_id), "agent_contact", user["id"],
                        interaction_type, subject, notes, channel
                    )
                    flash("Interaction logged successfully!", "success")
                except Exception as e:
                    flash(f"Error logging interaction: {e}", "error")
        
        elif action == "add_task":
            contact_id = request.form.get("contact_id")
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            due_date = request.form.get("due_date", "").strip()
            priority = request.form.get("priority", "medium").strip()
            reminder_date = request.form.get("reminder_date", "").strip() or None
            
            if contact_id and title:
                try:
                    add_crm_task(
                        int(contact_id), "agent_contact", user["id"],
                        title, description, due_date or None, priority, reminder_date
                    )
                    flash("Task added successfully!", "success")
                except Exception as e:
                    flash(f"Error adding task: {e}", "error")
        
        elif action == "update_task":
            task_id = request.form.get("task_id")
            status = request.form.get("status", "").strip()
            if task_id and status:
                try:
                    updates = {"status": status}
                    if status == "completed":
                        updates["completed_at"] = datetime.now().isoformat()
                    update_crm_task(int(task_id), user["id"], **updates)
                    flash("Task updated successfully!", "success")
                except Exception as e:
                    flash(f"Error updating task: {e}", "error")
        
        elif action == "delete_task":
            task_id = request.form.get("task_id")
            if task_id:
                try:
                    delete_crm_task(int(task_id), user["id"])
                    flash("Task deleted successfully!", "success")
                except Exception as e:
                    flash(f"Error deleting task: {e}", "error")
        
        elif action == "add_deal":
            contact_id = request.form.get("contact_id")
            deal_name = request.form.get("deal_name", "").strip()
            deal_type = request.form.get("deal_type", "other").strip()
            property_address = request.form.get("property_address", "").strip()
            deal_value = request.form.get("deal_value", "").strip()
            commission_rate = request.form.get("commission_rate", "").strip()
            stage = request.form.get("stage", "prospect").strip()
            probability = request.form.get("probability", "0").strip()
            expected_close_date = request.form.get("expected_close_date", "").strip()
            notes = request.form.get("notes", "").strip()
            
            if contact_id and deal_name:
                try:
                    deal_val = float(deal_value) if deal_value else None
                    comm_rate = float(commission_rate) if commission_rate else None
                    prob = int(probability) if probability else 0
                    add_crm_deal(
                        int(contact_id), "agent_contact", user["id"],
                        deal_name, deal_type, property_address, deal_val, comm_rate,
                        stage, prob, expected_close_date or None, notes
                    )
                    flash("Deal added successfully!", "success")
                except Exception as e:
                    flash(f"Error adding deal: {e}", "error")
        
        elif action == "update_deal":
            deal_id = request.form.get("deal_id")
            if deal_id:
                try:
                    updates = {}
                    for field in ['deal_name', 'deal_type', 'property_address', 'stage',
                                'expected_close_date', 'actual_close_date', 'notes']:
                        val = request.form.get(field, "").strip()
                        if val:
                            updates[field] = val if val else None
                    
                    for field in ['deal_value', 'commission_rate', 'probability']:
                        val = request.form.get(field, "").strip()
                        if val:
                            try:
                                updates[field] = float(val) if field != 'probability' else int(val)
                            except:
                                pass
                    
                    if updates:
                        update_crm_deal(int(deal_id), user["id"], **updates)
                        flash("Deal updated successfully!", "success")
                except Exception as e:
                    flash(f"Error updating deal: {e}", "error")
        
        elif action == "delete_deal":
            deal_id = request.form.get("deal_id")
            if deal_id:
                try:
                    delete_crm_deal(int(deal_id), user["id"])
                    flash("Deal deleted successfully!", "success")
                except Exception as e:
                    flash(f"Error deleting deal: {e}", "error")
        
        elif action == "add_relationship":
            contact_id_1 = request.form.get("contact_id_1")
            contact_id_2 = request.form.get("contact_id_2")
            relationship_type = request.form.get("relationship_type", "other").strip()
            notes = request.form.get("notes", "").strip()
            
            if contact_id_1 and contact_id_2:
                try:
                    result = add_crm_relationship(
                        int(contact_id_1), int(contact_id_2), "agent_contact",
                        user["id"], relationship_type, notes
                    )
                    if result:
                        flash("Relationship added successfully!", "success")
                    else:
                        flash("Relationship already exists!", "error")
                except Exception as e:
                    flash(f"Error adding relationship: {e}", "error")
        
        elif action == "bulk_action":
            contact_ids = request.form.getlist("contact_ids")
            bulk_action_type = request.form.get("bulk_action_type", "").strip()
            
            if contact_ids and bulk_action_type:
                try:
                    for contact_id in contact_ids:
                        if bulk_action_type == "add_tag":
                            tag = request.form.get("bulk_tag", "").strip()
                            contact = get_agent_contact(int(contact_id), user["id"])
                            if contact:
                                contact_dict = dict(contact) if hasattr(contact, 'keys') else contact
                                existing_tags = (contact_dict.get("tags") or "").split(",")
                                existing_tags = [t.strip() for t in existing_tags if t.strip()]
                                if tag and tag not in existing_tags:
                                    existing_tags.append(tag)
                                    update_agent_contact(int(contact_id), user["id"], tags=", ".join(existing_tags))
                        elif bulk_action_type == "change_stage":
                            stage = request.form.get("bulk_stage", "").strip()
                            if stage:
                                update_agent_contact(int(contact_id), user["id"], stage=stage)
                    flash(f"Bulk action completed for {len(contact_ids)} contact(s)!", "success")
                except Exception as e:
                    flash(f"Error performing bulk action: {e}", "error")

    stage_filter = request.args.get("stage")
    search_query = request.args.get("search", "").strip()
    tag_filter = request.args.get("tag", "").strip()
    sort_by = request.args.get("sort", "name")  # name, stage, last_touch, created_at
    
    try:
        contacts = list_agent_contacts(user["id"], stage_filter)
        # Convert contacts to dicts for JSON serialization in template
        # Handle None values and ensure all fields exist
        contacts_list = []
        for contact in contacts:
            try:
                # Convert sqlite3.Row to dict, handling missing columns gracefully
                # sqlite3.Row objects need to be converted to dict explicitly
                import sqlite3
                if isinstance(contact, sqlite3.Row):
                    contact_dict = {key: contact[key] for key in contact.keys()}
                elif hasattr(contact, 'keys') and not isinstance(contact, dict):
                    # It's a Row-like object
                    contact_dict = {key: contact[key] for key in contact.keys()}
                elif isinstance(contact, dict):
                    contact_dict = contact.copy()
                else:
                    # Fallback: try to convert
                    try:
                        contact_dict = dict(contact)
                    except:
                        contact_dict = {key: getattr(contact, key, None) for key in dir(contact) if not key.startswith('_')}
                
                # Ensure all expected fields exist with defaults
                expected_fields = {
                    'id': None, 'created_at': '', 'name': '', 'email': '', 'phone': '',
                    'stage': 'new', 'best_contact': '', 'last_touch': '', 'birthday': '',
                    'home_anniversary': '', 'address': '', 'notes': '', 'tags': '',
                    'property_address': '', 'property_value': None, 'equity_estimate': None,
                    'auto_birthday': 1, 'auto_anniversary': 1, 'auto_seasonal': 1,
                    'auto_equity': 1, 'auto_holidays': 1, 'equity_frequency': 'monthly'
                }
                for field, default in expected_fields.items():
                    if field not in contact_dict:
                        contact_dict[field] = default
                
                # Apply search filter
                if search_query:
                    search_lower = search_query.lower()
                    matches = (
                        search_lower in (contact_dict.get('name') or '').lower() or
                        search_lower in (contact_dict.get('email') or '').lower() or
                        search_lower in (contact_dict.get('phone') or '').lower() or
                        search_lower in (contact_dict.get('property_address') or '').lower() or
                        search_lower in (contact_dict.get('notes') or '').lower() or
                        search_lower in (contact_dict.get('tags') or '').lower()
                    )
                    if not matches:
                        continue
                
                # Apply tag filter
                if tag_filter:
                    contact_tags = (contact_dict.get('tags') or '').lower()
                    if tag_filter.lower() not in contact_tags:
                        continue
                
                # Fetch interaction count and history for this contact
                try:
                    interactions = list_crm_interactions(
                        contact_dict['id'], "agent_contact", user["id"], limit=50
                    )
                    contact_dict['interaction_count'] = len(interactions)
                    contact_dict['recent_interactions'] = [
                        dict(i) if hasattr(i, 'keys') else i for i in interactions[:3]
                    ]
                    contact_dict['all_interactions'] = [
                        dict(i) if hasattr(i, 'keys') else i for i in interactions
                    ]
                except Exception as e:
                    print(f"Error fetching interactions: {e}")
                    contact_dict['interaction_count'] = 0
                    contact_dict['recent_interactions'] = []
                    contact_dict['all_interactions'] = []
                
                # Fetch tasks for this contact
                try:
                    tasks = list_crm_tasks(user["id"], contact_dict['id'], "agent_contact", status="pending")
                    tasks_list = []
                    for t in tasks:
                        if hasattr(t, 'keys'):
                            tasks_list.append(dict(t))
                        else:
                            tasks_list.append(t)
                    contact_dict['pending_tasks'] = tasks_list
                    contact_dict['task_count'] = len(tasks_list)
                except Exception as e:
                    print(f"Error fetching tasks: {e}")
                    contact_dict['pending_tasks'] = []
                    contact_dict['task_count'] = 0
                
                # Fetch deals for this contact
                try:
                    deals = list_crm_deals(user["id"], contact_dict['id'], "agent_contact")
                    deals_list = []
                    for d in deals:
                        if hasattr(d, 'keys'):
                            deals_list.append(dict(d))
                        else:
                            deals_list.append(d)
                    contact_dict['deals'] = deals_list
                    contact_dict['deal_count'] = len(deals_list)
                    contact_dict['total_pipeline_value'] = sum([
                        (d.get('deal_value') if isinstance(d, dict) else (d['deal_value'] if 'deal_value' in d else 0)) or 0 
                        for d in deals_list
                    ])
                except Exception as e:
                    print(f"Error fetching deals for contact {contact_dict.get('id')}: {e}")
                    contact_dict['deals'] = []
                    contact_dict['deal_count'] = 0
                    contact_dict['total_pipeline_value'] = 0
                
                # Fetch relationships for this contact
                try:
                    relationships = list_crm_relationships(contact_dict['id'], "agent_contact", user["id"])
                    relationships_list = []
                    for r in relationships:
                        if hasattr(r, 'keys'):
                            relationships_list.append(dict(r))
                        else:
                            relationships_list.append(r)
                    contact_dict['relationships'] = relationships_list
                except Exception as e:
                    print(f"Error fetching relationships for contact {contact_dict.get('id')}: {e}")
                    contact_dict['relationships'] = []
                
                contacts_list.append(contact_dict)
            except Exception as e:
                import traceback
                print(f"Error converting contact: {traceback.format_exc()}")
                continue
        
        # Ensure all contacts are dicts before sorting/stats
        contacts_list_dicts = []
        for c in contacts_list:
            if isinstance(c, dict):
                contacts_list_dicts.append(c)
            elif hasattr(c, 'keys'):
                try:
                    import sqlite3
                    if isinstance(c, sqlite3.Row):
                        contacts_list_dicts.append({key: c[key] for key in c.keys()})
                    else:
                        contacts_list_dicts.append(dict(c))
                except Exception as e:
                    print(f"Error converting contact to dict: {e}")
                    continue
            else:
                print(f"Skipping invalid contact: {type(c)}")
                continue
        
        # Sort contacts
        if sort_by == "name":
            contacts_list_dicts.sort(key=lambda x: (x.get('name') or '').lower() if isinstance(x, dict) else '')
        elif sort_by == "stage":
            stage_order = {'new': 0, 'nurture': 1, 'active': 2, 'past': 3, 'sphere': 4}
            contacts_list_dicts.sort(key=lambda x: stage_order.get(x.get('stage', 'new') if isinstance(x, dict) else 'new', 5))
        elif sort_by == "last_touch":
            contacts_list_dicts.sort(key=lambda x: (x.get('last_touch') or '') if isinstance(x, dict) else '', reverse=True)
        elif sort_by == "created_at":
            contacts_list_dicts.sort(key=lambda x: (x.get('created_at') or '') if isinstance(x, dict) else '', reverse=True)
        
        # Calculate stats
        total_contacts = len(contacts_list_dicts)
        all_tasks = list_crm_tasks(user["id"], status="pending")
        all_deals_raw = list_crm_deals(user["id"])
        
        # Convert all_deals to dicts
        all_deals = []
        for d in all_deals_raw:
            if hasattr(d, 'keys'):
                all_deals.append(dict(d))
            else:
                all_deals.append(d)
        
        # Get follow-up threshold from user settings
        from database import get_user_by_id
        user_details = get_user_by_id(user["id"])
        if user_details and hasattr(user_details, 'keys'):
            user_details = dict(user_details)
        follow_up_days = user_details.get('follow_up_days', 30) if user_details and isinstance(user_details, dict) else 30
        
        # Get contacts needing follow-up
        try:
            from database import get_contacts_needing_followup
            contacts_needing_followup = get_contacts_needing_followup(user["id"], follow_up_days)
            needs_followup_count = len(contacts_needing_followup)
        except Exception as e:
            print(f"Error getting contacts needing followup: {e}")
            needs_followup_count = 0
        
        stats = {
            'total': total_contacts,
            'new': len([c for c in contacts_list_dicts if c.get('stage') == 'new']),
            'active': len([c for c in contacts_list_dicts if c.get('stage') == 'active']),
            'past': len([c for c in contacts_list_dicts if c.get('stage') == 'past']),
            'with_automation': len([c for c in contacts_list_dicts if any([
                c.get('auto_birthday'), c.get('auto_anniversary'),
                c.get('auto_seasonal'), c.get('auto_equity'), c.get('auto_holidays')
            ])]),
            'total_equity': sum([c.get('equity_estimate') or 0 for c in contacts_list_dicts]),
            'pending_tasks': len(all_tasks),
            'total_deals': len(all_deals),
            'pipeline_value': sum([(d.get('deal_value') if isinstance(d, dict) else 0) or 0 for d in all_deals]),
            'expected_commission': sum([(d.get('expected_commission') if isinstance(d, dict) else 0) or 0 for d in all_deals]),
            'needs_followup': needs_followup_count,
            'follow_up_days': follow_up_days,
        }
        
        # Get all unique tags
        all_tags = set()
        for contact in contacts_list_dicts:
            tags = contact.get('tags', '') or '' if isinstance(contact, dict) else ''
            if tags:
                all_tags.update([t.strip() for t in tags.split(',') if t.strip()])
        all_tags = sorted(list(all_tags))
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error loading contacts: {error_trace}")
        flash(f"Error loading contacts: {e}", "error")
        contacts_list = []
        contacts_list_dicts = []  # Ensure this is defined even on error
        stats = {'total': 0, 'new': 0, 'active': 0, 'past': 0, 'with_automation': 0, 'total_equity': 0, 'pending_tasks': 0, 'total_deals': 0, 'pipeline_value': 0, 'expected_commission': 0, 'needs_followup': 0, 'follow_up_days': 30}
        all_tags = []
    
    # Get all pending tasks for dashboard
    try:
        all_pending_tasks = list_crm_tasks(user["id"], status="pending")
        upcoming_tasks = []
        for t in all_pending_tasks[:10]:
            if hasattr(t, 'keys'):
                upcoming_tasks.append(dict(t))
            else:
                upcoming_tasks.append(t)
    except Exception as e:
        print(f"Error fetching upcoming tasks: {e}")
        upcoming_tasks = []
    
    # Get email templates for quick actions
    try:
        email_templates = list_message_templates(user["id"], "agent", "email")
    except:
        email_templates = []
    
    try:
        return render_template(
            "agent/crm.html",
            brand_name=FRONT_BRAND_NAME,
            user=user,
            contacts=contacts_list_dicts,  # Use the converted dicts list
            stage_filter=stage_filter,
            search_query=search_query,
            tag_filter=tag_filter,
            sort_by=sort_by,
            stats=stats,
            all_tags=all_tags,
            upcoming_tasks=upcoming_tasks,
            email_templates=email_templates,
        )
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"Error rendering template: {error_msg}")
        return f"Template Error: {e}<br><pre>{error_msg}</pre>", 500


@app.route("/agent/crm/import", methods=["GET", "POST"])
def agent_crm_import():
    """Agent CRM bulk import from Excel/CSV."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "agent":
            return redirect(url_for("login", role="agent"))
    except Exception as e:
        return f"Error: {e}", 500

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "upload":
            # Handle file upload
            if 'file' not in request.files:
                flash("Please select a file to upload.", "error")
                return redirect(url_for("agent_crm_import"))
            
            file = request.files['file']
            if file.filename == '':
                flash("Please select a file to upload.", "error")
                return redirect(url_for("agent_crm_import"))
            
            # Check file extension
            filename = file.filename.lower()
            if not (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
                flash("Please upload an Excel (.xlsx, .xls) or CSV file.", "error")
                return redirect(url_for("agent_crm_import"))
            
            try:
                # Read file into pandas
                if filename.endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
                
                # Convert to list of dicts for preview
                data = df.to_dict('records')
                
                # Get column names for mapping
                columns = list(df.columns)
                
                # Store in session for import step
                session['crm_import_data'] = json.dumps(data, default=str)
                session['crm_import_columns'] = columns
                
                return render_template(
                    "agent/crm_import_preview.html",
                    brand_name=FRONT_BRAND_NAME,
                    user=user,
                    data=data[:10],  # Preview first 10 rows
                    total_rows=len(data),
                    columns=columns,
                    sample_data=data[0] if data else {},
                )
            except Exception as e:
                import traceback
                flash(f"Error reading file: {str(e)}", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("agent_crm_import"))
        
        elif action == "import":
            # Actually import the data
            import_data_json = session.get('crm_import_data')
            if not import_data_json:
                flash("No import data found. Please upload a file again.", "error")
                return redirect(url_for("agent_crm_import"))
            
            try:
                data = json.loads(import_data_json)
                
                # Get column mappings from form
                mappings = {
                    'name': request.form.get('map_name', '').strip(),
                    'email': request.form.get('map_email', '').strip(),
                    'phone': request.form.get('map_phone', '').strip(),
                    'stage': request.form.get('map_stage', '').strip(),
                    'birthday': request.form.get('map_birthday', '').strip(),
                    'home_anniversary': request.form.get('map_anniversary', '').strip(),
                    'address': request.form.get('map_address', '').strip(),
                    'property_address': request.form.get('map_property_address', '').strip(),
                    'property_value': request.form.get('map_property_value', '').strip(),
                    'equity_estimate': request.form.get('map_equity', '').strip(),
                    'notes': request.form.get('map_notes', '').strip(),
                    'tags': request.form.get('map_tags', '').strip(),
                }
                
                # Default stage if not mapped
                default_stage = request.form.get('default_stage', 'new').strip()
                
                # Import settings
                skip_duplicates = request.form.get('skip_duplicates') == 'on'
                duplicate_check = request.form.get('duplicate_check', 'email').strip()
                
                imported = 0
                skipped = 0
                errors = []
                
                for idx, row in enumerate(data):
                    try:
                        # Map columns to fields
                        name = str(row.get(mappings['name'], '')).strip() if mappings['name'] else ''
                        email = str(row.get(mappings['email'], '')).strip() if mappings['email'] else ''
                        phone = str(row.get(mappings['phone'], '')).strip() if mappings['phone'] else ''
                        stage = str(row.get(mappings['stage'], default_stage)).strip() if mappings['stage'] else default_stage
                        birthday = str(row.get(mappings['birthday'], '')).strip() if mappings['birthday'] else ''
                        home_anniversary = str(row.get(mappings['home_anniversary'], '')).strip() if mappings['home_anniversary'] else ''
                        address = str(row.get(mappings['address'], '')).strip() if mappings['address'] else ''
                        property_address = str(row.get(mappings['property_address'], '')).strip() if mappings['property_address'] else ''
                        notes = str(row.get(mappings['notes'], '')).strip() if mappings['notes'] else ''
                        tags = str(row.get(mappings['tags'], '')).strip() if mappings['tags'] else ''
                        
                        # Parse numeric values
                        try:
                            property_value = float(row.get(mappings['property_value'], 0)) if mappings['property_value'] and str(row.get(mappings['property_value'], '')).strip() else None
                        except:
                            property_value = None
                        
                        try:
                            equity_estimate = float(row.get(mappings['equity_estimate'], 0)) if mappings['equity_estimate'] and str(row.get(mappings['equity_estimate'], '')).strip() else None
                        except:
                            equity_estimate = None
                        
                        if not name:
                            errors.append(f"Row {idx + 1}: Missing name")
                            continue
                        
                        # Check for duplicates if enabled
                        if skip_duplicates:
                            existing_contacts = list_agent_contacts(user["id"])
                            is_duplicate = False
                            for existing in existing_contacts:
                                if duplicate_check == 'email' and email:
                                    if existing.get('email') and existing['email'].lower() == email.lower():
                                        is_duplicate = True
                                        break
                                elif duplicate_check == 'phone' and phone:
                                    if existing.get('phone') and existing['phone'] == phone:
                                        is_duplicate = True
                                        break
                                elif duplicate_check == 'name' and name:
                                    if existing.get('name') and existing['name'].lower() == name.lower():
                                        is_duplicate = True
                                        break
                            
                            if is_duplicate:
                                skipped += 1
                                continue
                        
                        # Add contact
                        add_agent_contact(
                            user["id"], name, email, phone, stage, email or phone, "",
                            birthday, home_anniversary, address, notes, tags,
                            property_address, property_value, equity_estimate
                        )
                        imported += 1
                    except Exception as e:
                        errors.append(f"Row {idx + 1}: {str(e)}")
                
                # Clear session
                session.pop('crm_import_data', None)
                session.pop('crm_import_columns', None)
                
                flash(f"Import complete! {imported} contacts imported, {skipped} skipped, {len(errors)} errors.", "success")
                if errors:
                    flash(f"Errors: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''}", "error")
                
                return redirect(url_for("agent_crm"))
            except Exception as e:
                import traceback
                flash(f"Error during import: {str(e)}", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("agent_crm_import"))
    
    # GET request - show upload form
    return render_template(
        "agent/crm_import.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/agent/transactions", methods=["GET", "POST"])
def agent_transactions():
    """Agent transactions - list and create transactions."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if request.method == "POST":
        property_address = request.form.get("property_address", "").strip()
        client_name = request.form.get("client_name", "").strip()
        side = request.form.get("side", "buyer").strip()
        stage = request.form.get("stage", "pre_contract").strip()
        close_date = request.form.get("close_date", "").strip() or None

        if property_address and client_name:
            try:
                create_transaction(
                    agent_id=user["id"],
                    property_address=property_address,
                    client_name=client_name,
                    side=side,
                    current_stage=stage,
                    target_close_date=close_date,
                    client_email=request.form.get("client_email", "").strip(),
                    client_phone=request.form.get("client_phone", "").strip(),
                    purchase_price=request.form.get("purchase_price", "").strip() or None,
                    notes=request.form.get("notes", "").strip(),
                )
                flash("Transaction created successfully!", "success")
            except Exception as e:
                flash(f"Error creating transaction: {e}", "error")

    # Get contact info if coming from CRM
    contact_id = request.args.get("contact_id")
    contact_info = None
    if contact_id:
        try:
            contact = get_agent_contact(int(contact_id), user["id"])
            if contact:
                contact_dict = dict(contact) if hasattr(contact, 'keys') else contact
                contact_info = {
                    'name': contact_dict.get('name', '') if isinstance(contact_dict, dict) else (contact_dict['name'] if 'name' in contact_dict else ''),
                    'email': contact_dict.get('email', '') if isinstance(contact_dict, dict) else (contact_dict['email'] if 'email' in contact_dict else ''),
                    'phone': contact_dict.get('phone', '') if isinstance(contact_dict, dict) else (contact_dict['phone'] if 'phone' in contact_dict else ''),
                    'property_address': contact_dict.get('property_address', '') if isinstance(contact_dict, dict) else (contact_dict['property_address'] if 'property_address' in contact_dict else ''),
                }
        except:
            pass
    
    transactions = get_agent_transactions(user["id"])
    return render_template(
        "agent/transactions.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        transactions=transactions,
        contact_info=contact_info,
    )


@app.route("/agent/transactions/<int:tx_id>", methods=["GET"])
def agent_transaction_detail(tx_id):
    """View transaction details."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("Transaction not found.", "error")
        return redirect(url_for("agent_transactions"))

    documents = get_transaction_documents(tx_id)
    participants = get_transaction_participants(tx_id)
    timeline = get_transaction_timeline(tx_id)
    doc_status = get_transaction_document_status(tx_id)

    return render_template(
        "agent/transaction_detail.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        transaction=transaction,
        tx=transaction,  # Also provide as 'tx' for backward compatibility
        documents=documents,
        participants=participants,
        timeline=timeline,
        doc_status=doc_status,
    )


@app.route("/agent/transactions/<int:tx_id>/delete", methods=["POST"])
def agent_transaction_delete(tx_id):
    """Delete a transaction."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if delete_transaction(tx_id, user["id"]):
        flash("Transaction deleted.", "success")
    else:
        flash("Could not delete transaction.", "error")

    return redirect(url_for("agent_transactions"))


@app.route("/agent/communications", methods=["GET", "POST"])
def agent_communications():
    """Agent communications - message templates."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if request.method == "POST":
        template_name = request.form.get("template_name", "").strip()
        template_content = request.form.get("template_content", "").strip()
        template_type = request.form.get("template_type", "email").strip()

        if template_name and template_content:
            try:
                add_message_template(user["id"], template_name, template_content, template_type)
                flash("Template saved!", "success")
            except Exception as e:
                flash(f"Error saving template: {e}", "error")

    templates = list_message_templates(user["id"])
    return render_template(
        "agent/communications.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        templates=templates,
    )


@app.route("/agent/marketing", methods=["GET", "POST"])
def agent_marketing():
    """Agent marketing - marketing templates and campaigns."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if request.method == "POST":
        template_name = request.form.get("template_name", "").strip()
        template_content = request.form.get("template_content", "").strip()
        template_type = request.form.get("template_type", "social").strip()

        if template_name and template_content:
            try:
                add_marketing_template(user["id"], template_name, template_content, template_type)
                flash("Marketing template saved!", "success")
            except Exception as e:
                flash(f"Error saving template: {e}", "error")

    templates = list_marketing_templates(user["id"])
    return render_template(
        "agent/marketing.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        templates=templates,
    )


@app.route("/agent/power-tools", methods=["GET"])
def agent_power_tools():
    """Agent power tools - advanced agent features."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    return render_template(
        "agent/power_tools.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/agent/referrals", methods=["GET"])
def agent_referrals():
    """Agent referral link management."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    try:
        from database import get_referral_stats, get_or_create_referral_code
        
        # Ensure referral code exists
        try:
            referral_code = get_or_create_referral_code(user["id"], "agent")
        except Exception as e:
            print(f"Error getting referral code: {e}")
            # Fallback code
            referral_code = f"AGENT-{user['id']:06d}"
        
        # Get stats with fallback
        try:
            stats = get_referral_stats(user["id"])
        except Exception as e:
            print(f"Error getting stats: {e}")
            stats = {'total_clients': 0, 'clients_this_month': 0, 'referral_code': referral_code}
        
        # Build referral URL
        base_url = request.url_root.rstrip('/')
        referral_url = f"{base_url}/signup?role=homeowner&ref={referral_code}"
        
        return render_template(
            "agent/referrals.html",
            brand_name=FRONT_BRAND_NAME,
            user=user,
            referral_code=referral_code,
            referral_url=referral_url,
            stats=stats,
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in agent_referrals: {error_trace}")
        flash(f"Error loading referral page: {str(e)}", "error")
        return redirect(url_for("agent_dashboard"))


@app.route("/agent/settings/profile", methods=["GET", "POST"])
def agent_settings_profile():
    """Agent settings and profile."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    from database import get_user_profile, create_or_update_user_profile

    # Handle POST - update profile
    if request.method == "POST":
        try:
            # Handle file uploads
            professional_photo = None
            brokerage_logo = None
            
            # Upload professional photo
            if "professional_photo" in request.files:
                photo_file = request.files["professional_photo"]
                if photo_file and photo_file.filename:
                    safe_name = secure_filename(photo_file.filename)
                    unique_name = f"{uuid4().hex}_{safe_name}"
                    save_path = BASE_DIR / "static" / "uploads" / "profiles" / unique_name
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    photo_file.save(save_path)
                    professional_photo = str(Path("uploads") / "profiles" / unique_name).replace("\\", "/")
            
            # Upload brokerage logo
            if "brokerage_logo" in request.files:
                logo_file = request.files["brokerage_logo"]
                if logo_file and logo_file.filename:
                    safe_name = secure_filename(logo_file.filename)
                    unique_name = f"{uuid4().hex}_{safe_name}"
                    save_path = BASE_DIR / "static" / "uploads" / "profiles" / unique_name
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    logo_file.save(save_path)
                    brokerage_logo = str(Path("uploads") / "profiles" / unique_name).replace("\\", "/")
            
            # Get existing profile to preserve existing photos/logos if not uploading new ones
            existing_profile = get_user_profile(user["id"])
            if existing_profile:
                if not professional_photo:
                    professional_photo = existing_profile.get("professional_photo")
                if not brokerage_logo:
                    brokerage_logo = existing_profile.get("brokerage_logo")
            
            # Get form data
            profile_id = create_or_update_user_profile(
                user_id=user["id"],
                role="agent",
                professional_photo=professional_photo,
                brokerage_logo=brokerage_logo,
                team_name=request.form.get("team_name", "").strip() or None,
                brokerage_name=request.form.get("brokerage_name", "").strip() or None,
                website_url=request.form.get("website_url", "").strip() or None,
                facebook_url=request.form.get("facebook_url", "").strip() or None,
                instagram_url=request.form.get("instagram_url", "").strip() or None,
                linkedin_url=request.form.get("linkedin_url", "").strip() or None,
                twitter_url=request.form.get("twitter_url", "").strip() or None,
                youtube_url=request.form.get("youtube_url", "").strip() or None,
                phone=request.form.get("phone", "").strip() or None,
                call_button_enabled=1 if request.form.get("call_button_enabled") == "on" else 0,
                schedule_button_enabled=1 if request.form.get("schedule_button_enabled") == "on" else 0,
                schedule_url=request.form.get("schedule_url", "").strip() or None,
                bio=request.form.get("bio", "").strip() or None,
                specialties=request.form.get("specialties", "").strip() or None,
                years_experience=int(request.form.get("years_experience")) if request.form.get("years_experience") else None,
                languages=request.form.get("languages", "").strip() or None,
                service_areas=request.form.get("service_areas", "").strip() or None,
                license_number=request.form.get("license_number", "").strip() or None,
                company_address=request.form.get("company_address", "").strip() or None,
                company_city=request.form.get("company_city", "").strip() or None,
                company_state=request.form.get("company_state", "").strip() or None,
                company_zip=request.form.get("company_zip", "").strip() or None,
            )
            flash("Profile updated successfully!", "success")
            return redirect(url_for("agent_settings_profile"))
        except Exception as e:
            import traceback
            print(f"Error updating profile: {traceback.format_exc()}")
            flash(f"Error updating profile: {str(e)}", "error")
    
    # GET - load profile
    profile = get_user_profile(user["id"])
    profile_dict = dict(profile) if profile and hasattr(profile, 'keys') else (profile if profile else {})
    
    return render_template(
        "agent/settings_profile.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        profile=profile_dict,
    )


# -------------------------------------------------
# LENDER ROUTES
# -------------------------------------------------
@app.route("/lender/crm", methods=["GET", "POST"])
def lender_crm():
    """Lender CRM - comprehensive borrower management with automated emails."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    if request.method == "POST":
        action = request.form.get("action", "add")
        
        if action == "add":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            status = request.form.get("status", "prospect").strip()
            loan_type = request.form.get("loan_type", "").strip()
            target_payment = request.form.get("target_payment", "").strip()
            birthday = request.form.get("birthday", "").strip()
            home_anniversary = request.form.get("home_anniversary", "").strip()
            address = request.form.get("address", "").strip()
            notes = request.form.get("notes", "").strip()
            tags = request.form.get("tags", "").strip()
            property_address = request.form.get("property_address", "").strip()
            loan_amount = request.form.get("loan_amount", "").strip()
            loan_rate = request.form.get("loan_rate", "").strip()
            
            try:
                loan_amt = float(loan_amount) if loan_amount else None
                rate = float(loan_rate) if loan_rate else None
                borrower_id = add_lender_borrower(
                    user["id"], name, status, loan_type, target_payment, "",
                    email, phone, birthday, home_anniversary, address, notes, tags,
                    property_address, loan_amt, rate
                )
                
                # If email provided, try to link to existing homeowner account
                if email:
                    from database import get_user_by_email, create_client_relationship, get_or_create_referral_code
                    homeowner = get_user_by_email(email)
                    if homeowner and homeowner.get("role") == "homeowner":
                        # Create relationship
                        referral_code = get_or_create_referral_code(user["id"], "lender")
                        create_client_relationship(
                            homeowner_id=homeowner["id"],
                            professional_id=user["id"],
                            professional_role="lender",
                            referral_code=referral_code
                        )
                        flash(f"Borrower added and linked to homeowner account ({email})!", "success")
                    else:
                        flash("Borrower added successfully!", "success")
                else:
                    flash("Borrower added successfully!", "success")
            except Exception as e:
                flash(f"Error adding borrower: {e}", "error")
        
        elif action == "update":
            borrower_id = request.form.get("borrower_id")
            if borrower_id:
                updates = {}
                for field in ['name', 'email', 'phone', 'status', 'loan_type', 
                            'target_payment', 'birthday', 'home_anniversary', 
                            'address', 'notes', 'tags', 'property_address',
                            'loan_amount', 'loan_rate', 'auto_birthday', 
                            'auto_anniversary', 'auto_seasonal', 'auto_equity',
                            'auto_holidays', 'equity_frequency']:
                    val = request.form.get(field, "").strip()
                    if val or field in ['auto_birthday', 'auto_anniversary', 
                                       'auto_seasonal', 'auto_equity', 'auto_holidays']:
                        if field in ['auto_birthday', 'auto_anniversary', 
                                    'auto_seasonal', 'auto_equity', 'auto_holidays']:
                            updates[field] = 1 if request.form.get(field) else 0
                        elif field in ['loan_amount', 'loan_rate']:
                            try:
                                updates[field] = float(val) if val else None
                            except:
                                pass
                        else:
                            updates[field] = val if val else None
                
                try:
                    update_lender_borrower(int(borrower_id), user["id"], **updates)
                    flash("Borrower updated successfully!", "success")
                except Exception as e:
                    flash(f"Error updating borrower: {e}", "error")
        
        elif action == "add_interaction":
            borrower_id = request.form.get("borrower_id")
            interaction_type = request.form.get("interaction_type", "").strip()
            subject = request.form.get("subject", "").strip()
            notes = request.form.get("notes", "").strip()
            channel = request.form.get("channel", "email").strip()
            
            if borrower_id and interaction_type:
                try:
                    add_crm_interaction(
                        int(borrower_id), "lender_borrower", user["id"],
                        interaction_type, subject, notes, channel
                    )
                    flash("Interaction logged successfully!", "success")
                except Exception as e:
                    flash(f"Error logging interaction: {e}", "error")
        
        elif action == "add_task":
            borrower_id = request.form.get("borrower_id")
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            due_date = request.form.get("due_date", "").strip()
            priority = request.form.get("priority", "medium").strip()
            reminder_date = request.form.get("reminder_date", "").strip() or None
            
            if borrower_id and title:
                try:
                    add_crm_task(
                        int(borrower_id), "lender_borrower", user["id"],
                        title, description, due_date or None, priority, reminder_date
                    )
                    flash("Task added successfully!", "success")
                except Exception as e:
                    flash(f"Error adding task: {e}", "error")
        
        elif action == "update_task":
            task_id = request.form.get("task_id")
            status = request.form.get("status", "").strip()
            if task_id and status:
                try:
                    updates = {"status": status}
                    if status == "completed":
                        updates["completed_at"] = datetime.now().isoformat()
                    update_crm_task(int(task_id), user["id"], **updates)
                    flash("Task updated successfully!", "success")
                except Exception as e:
                    flash(f"Error updating task: {e}", "error")
        
        elif action == "add_deal":
            borrower_id = request.form.get("borrower_id")
            deal_name = request.form.get("deal_name", "").strip()
            deal_type = request.form.get("deal_type", "other").strip()
            property_address = request.form.get("property_address", "").strip()
            deal_value = request.form.get("deal_value", "").strip()
            commission_rate = request.form.get("commission_rate", "").strip()
            stage = request.form.get("stage", "prospect").strip()
            probability = request.form.get("probability", "0").strip()
            expected_close_date = request.form.get("expected_close_date", "").strip()
            notes = request.form.get("notes", "").strip()
            
            if borrower_id and deal_name:
                try:
                    deal_val = float(deal_value) if deal_value else None
                    comm_rate = float(commission_rate) if commission_rate else None
                    prob = int(probability) if probability else 0
                    add_crm_deal(
                        int(borrower_id), "lender_borrower", user["id"],
                        deal_name, deal_type, property_address, deal_val, comm_rate,
                        stage, prob, expected_close_date or None, notes
                    )
                    flash("Deal added successfully!", "success")
                except Exception as e:
                    flash(f"Error adding deal: {e}", "error")
        
        elif action == "bulk_action":
            borrower_ids = request.form.getlist("borrower_ids")
            bulk_action_type = request.form.get("bulk_action_type", "").strip()
            
            if borrower_ids and bulk_action_type:
                try:
                    for borrower_id in borrower_ids:
                        if bulk_action_type == "add_tag":
                            tag = request.form.get("bulk_tag", "").strip()
                            borrower = get_lender_borrower(int(borrower_id), user["id"])
                            if borrower:
                                existing_tags = (borrower.get("tags") or "").split(",")
                                existing_tags = [t.strip() for t in existing_tags if t.strip()]
                                if tag and tag not in existing_tags:
                                    existing_tags.append(tag)
                                    update_lender_borrower(int(borrower_id), user["id"], tags=", ".join(existing_tags))
                        elif bulk_action_type == "change_status":
                            status = request.form.get("bulk_status", "").strip()
                            if status:
                                update_lender_borrower(int(borrower_id), user["id"], status=status)
                    flash(f"Bulk action completed for {len(borrower_ids)} borrower(s)!", "success")
                except Exception as e:
                    flash(f"Error performing bulk action: {e}", "error")
        
        elif action == "update_followup_days":
            follow_up_days = request.form.get("follow_up_days", "30").strip()
            try:
                days = int(follow_up_days)
                if 1 <= days <= 365:
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE users SET follow_up_days = ? WHERE id = ?",
                        (days, user["id"])
                    )
                    conn.commit()
                    conn.close()
                    flash(f"Follow-up reminder set to {days} days!", "success")
                else:
                    flash("Please enter a number between 1 and 365.", "error")
            except ValueError:
                flash("Invalid number. Please enter a number between 1 and 365.", "error")

    status_filter = request.args.get("status")
    borrowers = list_lender_borrowers(user["id"], status_filter)
    
    # Convert borrowers to dicts and enrich with tasks/deals
    borrowers_list = []
    for borrower in borrowers:
        try:
            borrower_dict = dict(borrower)
            
            # Fetch interaction count
            try:
                interactions = list_crm_interactions(
                    borrower_dict['id'], "lender_borrower", user["id"], limit=50
                )
                borrower_dict['interaction_count'] = len(interactions)
                borrower_dict['recent_interactions'] = [dict(i) for i in interactions[:3]]
            except:
                borrower_dict['interaction_count'] = 0
                borrower_dict['recent_interactions'] = []
            
            # Fetch tasks
            try:
                tasks = list_crm_tasks(user["id"], borrower_dict['id'], "lender_borrower", status="pending")
                borrower_dict['pending_tasks'] = [dict(t) for t in tasks]
                borrower_dict['task_count'] = len(tasks)
            except:
                borrower_dict['pending_tasks'] = []
                borrower_dict['task_count'] = 0
            
            # Fetch deals
            try:
                deals = list_crm_deals(user["id"], borrower_dict['id'], "lender_borrower")
                borrower_dict['deals'] = [dict(d) for d in deals]
                borrower_dict['deal_count'] = len(deals)
                borrower_dict['total_pipeline_value'] = sum([d.get('deal_value') or 0 for d in deals])
            except:
                borrower_dict['deals'] = []
                borrower_dict['deal_count'] = 0
                borrower_dict['total_pipeline_value'] = 0
            
            borrowers_list.append(borrower_dict)
        except:
            continue
    
    # Calculate stats
    all_tasks = list_crm_tasks(user["id"], status="pending")
    all_deals = list_crm_deals(user["id"])
    
    # Get follow-up threshold from user settings
    from database import get_user_by_id
    user_details = get_user_by_id(user["id"])
    follow_up_days = user_details.get('follow_up_days', 30) if user_details else 30
    
    # Get borrowers needing follow-up
    try:
        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=follow_up_days)
        cutoff_iso = cutoff_date.isoformat()
        
        cur.execute("""
            SELECT DISTINCT lb.id
            FROM lender_borrowers lb
            LEFT JOIN crm_interactions ci ON ci.contact_id = lb.id 
                AND ci.contact_type = 'lender_borrower' 
                AND ci.professional_user_id = lb.lender_user_id
            WHERE lb.lender_user_id = ?
            AND (
                COALESCE(
                    (SELECT MAX(ci2.interaction_date) 
                     FROM crm_interactions ci2 
                     WHERE ci2.contact_id = lb.id 
                     AND ci2.contact_type = 'lender_borrower' 
                     AND ci2.professional_user_id = lb.lender_user_id),
                    lb.last_touch,
                    lb.created_at
                ) < ? OR
                COALESCE(
                    (SELECT MAX(ci3.interaction_date) 
                     FROM crm_interactions ci3 
                     WHERE ci3.contact_id = lb.id 
                     AND ci3.contact_type = 'lender_borrower' 
                     AND ci3.professional_user_id = lb.lender_user_id),
                    lb.last_touch
                ) IS NULL
            )
        """, (user["id"], cutoff_iso))
        needs_followup_count = len(cur.fetchall())
        conn.close()
    except Exception as e:
        print(f"Error getting borrowers needing followup: {e}")
        needs_followup_count = 0
    
    stats = {
        'total': len(borrowers_list),
        'prospect': len([b for b in borrowers_list if b.get('status') == 'prospect']),
        'preapproval': len([b for b in borrowers_list if b.get('status') == 'preapproval']),
        'in_process': len([b for b in borrowers_list if b.get('status') == 'in_process']),
        'closed': len([b for b in borrowers_list if b.get('status') == 'closed']),
        'pending_tasks': len(all_tasks),
        'total_deals': len(all_deals),
        'pipeline_value': sum([d.get('deal_value') or 0 for d in all_deals]),
        'expected_commission': sum([d.get('expected_commission') or 0 for d in all_deals]),
        'needs_followup': needs_followup_count,
        'follow_up_days': follow_up_days,
        'with_automation': len([b for b in borrowers_list if any([
            b.get('auto_birthday'), b.get('auto_anniversary'),
            b.get('auto_seasonal'), b.get('auto_equity'), b.get('auto_holidays')
        ])]),
    }
    
    # Get all unique tags
    all_tags = set()
    for borrower in borrowers_list:
        tags = borrower.get('tags', '') or ''
        if tags:
            all_tags.update([t.strip() for t in tags.split(',') if t.strip()])
    all_tags = sorted(list(all_tags))
    
    # Get upcoming tasks
    try:
        upcoming_tasks = [dict(t) for t in all_tasks[:10]]
    except:
        upcoming_tasks = []
    
    return render_template(
        "lender/crm.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        borrowers=borrowers_list,
        status_filter=status_filter,
        stats=stats,
        all_tags=all_tags,
        upcoming_tasks=upcoming_tasks,
    )


@app.route("/lender/crm/import", methods=["GET", "POST"])
def lender_crm_import():
    """Lender CRM bulk import from Excel/CSV."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "lender":
            return redirect(url_for("login", role="lender"))
    except Exception as e:
        return f"Error: {e}", 500

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "upload":
            # Handle file upload
            if 'file' not in request.files:
                flash("Please select a file to upload.", "error")
                return redirect(url_for("lender_crm_import"))
            
            file = request.files['file']
            if file.filename == '':
                flash("Please select a file to upload.", "error")
                return redirect(url_for("lender_crm_import"))
            
            # Check file extension
            filename = file.filename.lower()
            if not (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
                flash("Please upload an Excel (.xlsx, .xls) or CSV file.", "error")
                return redirect(url_for("lender_crm_import"))
            
            try:
                # Read file into pandas
                if filename.endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
                
                # Convert to list of dicts for preview
                data = df.to_dict('records')
                
                # Get column names for mapping
                columns = list(df.columns)
                
                # Store in session for import step
                session['crm_import_data'] = json.dumps(data, default=str)
                session['crm_import_columns'] = columns
                
                return render_template(
                    "lender/crm_import_preview.html",
                    brand_name=FRONT_BRAND_NAME,
                    user=user,
                    data=data[:10],  # Preview first 10 rows
                    total_rows=len(data),
                    columns=columns,
                    sample_data=data[0] if data else {},
                )
            except Exception as e:
                import traceback
                flash(f"Error reading file: {str(e)}", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("lender_crm_import"))
        
        elif action == "import":
            # Actually import the data
            import_data_json = session.get('crm_import_data')
            if not import_data_json:
                flash("No import data found. Please upload a file again.", "error")
                return redirect(url_for("lender_crm_import"))
            
            try:
                data = json.loads(import_data_json)
                
                # Get column mappings from form
                mappings = {
                    'name': request.form.get('map_name', '').strip(),
                    'email': request.form.get('map_email', '').strip(),
                    'phone': request.form.get('map_phone', '').strip(),
                    'status': request.form.get('map_status', '').strip(),
                    'loan_type': request.form.get('map_loan_type', '').strip(),
                    'target_payment': request.form.get('map_target_payment', '').strip(),
                    'birthday': request.form.get('map_birthday', '').strip(),
                    'home_anniversary': request.form.get('map_anniversary', '').strip(),
                    'address': request.form.get('map_address', '').strip(),
                    'property_address': request.form.get('map_property_address', '').strip(),
                    'loan_amount': request.form.get('map_loan_amount', '').strip(),
                    'loan_rate': request.form.get('map_loan_rate', '').strip(),
                    'notes': request.form.get('map_notes', '').strip(),
                    'tags': request.form.get('map_tags', '').strip(),
                }
                
                # Default status if not mapped
                default_status = request.form.get('default_status', 'prospect').strip()
                
                # Import settings
                skip_duplicates = request.form.get('skip_duplicates') == 'on'
                duplicate_check = request.form.get('duplicate_check', 'email').strip()
                
                imported = 0
                skipped = 0
                errors = []
                
                for idx, row in enumerate(data):
                    try:
                        # Map columns to fields
                        name = str(row.get(mappings['name'], '')).strip() if mappings['name'] else ''
                        email = str(row.get(mappings['email'], '')).strip() if mappings['email'] else ''
                        phone = str(row.get(mappings['phone'], '')).strip() if mappings['phone'] else ''
                        status = str(row.get(mappings['status'], default_status)).strip() if mappings['status'] else default_status
                        loan_type = str(row.get(mappings['loan_type'], '')).strip() if mappings['loan_type'] else ''
                        target_payment = str(row.get(mappings['target_payment'], '')).strip() if mappings['target_payment'] else ''
                        birthday = str(row.get(mappings['birthday'], '')).strip() if mappings['birthday'] else ''
                        home_anniversary = str(row.get(mappings['home_anniversary'], '')).strip() if mappings['home_anniversary'] else ''
                        address = str(row.get(mappings['address'], '')).strip() if mappings['address'] else ''
                        property_address = str(row.get(mappings['property_address'], '')).strip() if mappings['property_address'] else ''
                        notes = str(row.get(mappings['notes'], '')).strip() if mappings['notes'] else ''
                        tags = str(row.get(mappings['tags'], '')).strip() if mappings['tags'] else ''
                        
                        # Parse numeric values
                        try:
                            loan_amount = float(row.get(mappings['loan_amount'], 0)) if mappings['loan_amount'] and str(row.get(mappings['loan_amount'], '')).strip() else None
                        except:
                            loan_amount = None
                        
                        try:
                            loan_rate = float(row.get(mappings['loan_rate'], 0)) if mappings['loan_rate'] and str(row.get(mappings['loan_rate'], '')).strip() else None
                        except:
                            loan_rate = None
                        
                        if not name:
                            errors.append(f"Row {idx + 1}: Missing name")
                            continue
                        
                        # Check for duplicates if enabled
                        if skip_duplicates:
                            existing_borrowers = list_lender_borrowers(user["id"])
                            is_duplicate = False
                            for existing in existing_borrowers:
                                if duplicate_check == 'email' and email:
                                    if existing.get('email') and existing['email'].lower() == email.lower():
                                        is_duplicate = True
                                        break
                                elif duplicate_check == 'phone' and phone:
                                    if existing.get('phone') and existing['phone'] == phone:
                                        is_duplicate = True
                                        break
                                elif duplicate_check == 'name' and name:
                                    if existing.get('name') and existing['name'].lower() == name.lower():
                                        is_duplicate = True
                                        break
                            
                            if is_duplicate:
                                skipped += 1
                                continue
                        
                        # Add borrower
                        add_lender_borrower(
                            user["id"], name, status, loan_type, target_payment, "",
                            email, phone, birthday, home_anniversary, address, notes, tags,
                            property_address, loan_amount, loan_rate
                        )
                        imported += 1
                    except Exception as e:
                        errors.append(f"Row {idx + 1}: {str(e)}")
                
                # Clear session
                session.pop('crm_import_data', None)
                session.pop('crm_import_columns', None)
                
                flash(f"Import complete! {imported} borrowers imported, {skipped} skipped, {len(errors)} errors.", "success")
                if errors:
                    flash(f"Errors: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''}", "error")
                
                return redirect(url_for("lender_crm"))
            except Exception as e:
                import traceback
                flash(f"Error during import: {str(e)}", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("lender_crm_import"))
    
    # GET request - show upload form
    return render_template(
        "lender/crm_import.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/loans", methods=["GET", "POST"])
def lender_loans():
    """Lender loans management."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    if request.method == "POST":
        borrower_name = request.form.get("borrower_name", "").strip()
        loan_amount = request.form.get("loan_amount", "").strip()
        loan_type = request.form.get("loan_type", "conventional").strip()
        status = request.form.get("status", "preapproval").strip()

        if borrower_name and loan_amount:
            try:
                add_lender_loan(user["id"], borrower_name, loan_amount, loan_type, status)
                flash("Loan added successfully!", "success")
            except Exception as e:
                flash(f"Error adding loan: {e}", "error")

    loans = list_lender_loans(user["id"])
    return render_template(
        "lender/loans.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        loans=loans,
    )


@app.route("/lender/marketing", methods=["GET"])
def lender_marketing():
    """Lender marketing tools."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/marketing.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/messages", methods=["GET"])
def lender_messages():
    """Lender messages."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/messages.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/documents", methods=["GET"])
def lender_documents():
    """Lender documents."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/documents.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/power-suite", methods=["GET"])
def lender_power_suite():
    """Lender power suite."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/power_suite.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@app.route("/lender/referrals", methods=["GET"])
def lender_referrals():
    """Lender referral link management."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    try:
        from database import get_referral_stats, get_or_create_referral_code
        
        # Ensure referral code exists
        try:
            referral_code = get_or_create_referral_code(user["id"], "lender")
        except Exception as e:
            print(f"Error getting referral code: {e}")
            # Fallback code
            referral_code = f"LENDER-{user['id']:06d}"
        
        # Get stats with fallback
        try:
            stats = get_referral_stats(user["id"])
        except Exception as e:
            print(f"Error getting stats: {e}")
            stats = {'total_clients': 0, 'clients_this_month': 0, 'referral_code': referral_code}
        
        # Build referral URL
        base_url = request.url_root.rstrip('/')
        referral_url = f"{base_url}/signup?role=homeowner&ref={referral_code}"
        
        return render_template(
            "lender/referrals.html",
            brand_name=FRONT_BRAND_NAME,
            user=user,
            referral_code=referral_code,
            referral_url=referral_url,
            stats=stats,
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in lender_referrals: {error_trace}")
        flash(f"Error loading referral page: {str(e)}", "error")
        return redirect(url_for("lender_dashboard"))


@app.route("/lender/settings/profile", methods=["GET", "POST"])
def lender_settings_profile():
    """Lender settings and profile."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    from database import get_user_profile, create_or_update_user_profile

    # Handle POST - update profile
    if request.method == "POST":
        try:
            # Handle file uploads
            professional_photo = None
            brokerage_logo = None
            
            # Upload professional photo
            if "professional_photo" in request.files:
                photo_file = request.files["professional_photo"]
                if photo_file and photo_file.filename:
                    safe_name = secure_filename(photo_file.filename)
                    unique_name = f"{uuid4().hex}_{safe_name}"
                    save_path = BASE_DIR / "static" / "uploads" / "profiles" / unique_name
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    photo_file.save(save_path)
                    professional_photo = str(Path("uploads") / "profiles" / unique_name).replace("\\", "/")
            
            # Upload company logo
            if "brokerage_logo" in request.files:
                logo_file = request.files["brokerage_logo"]
                if logo_file and logo_file.filename:
                    safe_name = secure_filename(logo_file.filename)
                    unique_name = f"{uuid4().hex}_{safe_name}"
                    save_path = BASE_DIR / "static" / "uploads" / "profiles" / unique_name
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    logo_file.save(save_path)
                    brokerage_logo = str(Path("uploads") / "profiles" / unique_name).replace("\\", "/")
            
            # Get existing profile to preserve existing photos/logos if not uploading new ones
            existing_profile = get_user_profile(user["id"])
            if existing_profile:
                if not professional_photo:
                    professional_photo = existing_profile.get("professional_photo")
                if not brokerage_logo:
                    brokerage_logo = existing_profile.get("brokerage_logo")
            
            # Get form data
            profile_id = create_or_update_user_profile(
                user_id=user["id"],
                role="lender",
                professional_photo=professional_photo,
                brokerage_logo=brokerage_logo,
                team_name=request.form.get("team_name", "").strip() or None,
                brokerage_name=request.form.get("brokerage_name", "").strip() or None,
                website_url=request.form.get("website_url", "").strip() or None,
                facebook_url=request.form.get("facebook_url", "").strip() or None,
                instagram_url=request.form.get("instagram_url", "").strip() or None,
                linkedin_url=request.form.get("linkedin_url", "").strip() or None,
                twitter_url=request.form.get("twitter_url", "").strip() or None,
                youtube_url=request.form.get("youtube_url", "").strip() or None,
                phone=request.form.get("phone", "").strip() or None,
                call_button_enabled=1 if request.form.get("call_button_enabled") == "on" else 0,
                schedule_button_enabled=1 if request.form.get("schedule_button_enabled") == "on" else 0,
                schedule_url=request.form.get("schedule_url", "").strip() or None,
                application_url=request.form.get("application_url", "").strip() or None,
                bio=request.form.get("bio", "").strip() or None,
                specialties=request.form.get("specialties", "").strip() or None,
                years_experience=int(request.form.get("years_experience")) if request.form.get("years_experience") else None,
                languages=request.form.get("languages", "").strip() or None,
                service_areas=request.form.get("service_areas", "").strip() or None,
                nmls_number=request.form.get("nmls_number", "").strip() or None,
                license_number=request.form.get("license_number", "").strip() or None,
                company_address=request.form.get("company_address", "").strip() or None,
                company_city=request.form.get("company_city", "").strip() or None,
                company_state=request.form.get("company_state", "").strip() or None,
                company_zip=request.form.get("company_zip", "").strip() or None,
            )
            flash("Profile updated successfully!", "success")
            return redirect(url_for("lender_settings_profile"))
        except Exception as e:
            import traceback
            print(f"Error updating profile: {traceback.format_exc()}")
            flash(f"Error updating profile: {str(e)}", "error")
    
    # GET - load profile
    profile = get_user_profile(user["id"])
    profile_dict = dict(profile) if profile and hasattr(profile, 'keys') else (profile if profile else {})
    
    return render_template(
        "lender/settings_profile.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        profile=profile_dict,
    )


# -------------------------------------------------
# HOMEOWNER ROUTES (Missing)
# -------------------------------------------------
@app.route("/homeowner/reno/roi-guide", methods=["GET"])
def homeowner_reno_roi_guide():
    """Renovation ROI guide."""
    return render_template(
        "homeowner/reno_roi_guide.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/reno/before-after", methods=["GET"])
def homeowner_reno_before_after():
    """Before and after renovation gallery."""
    return render_template(
        "homeowner/reno_before_after.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/plan-my-move", methods=["GET", "POST"])
def homeowner_next_plan_move():
    """Plan my move - next home planning."""
    user = get_current_user()
    if request.method == "POST":
        plan_data = {
            "target_date": request.form.get("target_date", "").strip(),
            "target_location": request.form.get("target_location", "").strip(),
            "budget": request.form.get("budget", "").strip(),
            "notes": request.form.get("notes", "").strip(),
        }
        if user:
            upsert_next_move_plan(user["id"], plan_data)
            flash("Plan saved!", "success")

    plan = get_next_move_plan(user["id"]) if user else None
    return render_template(
        "homeowner/next_plan_move.html",
        brand_name=FRONT_BRAND_NAME,
        plan=plan,
    )


@app.route("/homeowner/next/buy-sell-guidance", methods=["GET"])
def homeowner_next_buy_sell_guidance():
    """Buy and sell guidance."""
    return render_template(
        "homeowner/next_buy_sell_guidance.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/pathways", methods=["GET"])
def homeowner_next_pathways():
    """Next home pathways."""
    return render_template(
        "homeowner/next_pathways.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/loan-paths", methods=["GET"])
def homeowner_next_loan_paths():
    """Loan paths guidance."""
    return render_template(
        "homeowner/next_loan_paths.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/next/affordability", methods=["GET"])
def homeowner_next_affordability():
    """Affordability calculator."""
    return render_template(
        "homeowner/next_affordability.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/maintenance-guide", methods=["GET"])
def homeowner_care_maintenance_guide():
    """Home maintenance guide."""
    return render_template(
        "homeowner/care_maintenance_guide.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/seasonal-checklists", methods=["GET"])
def homeowner_care_seasonal_checklists():
    """Seasonal maintenance checklists."""
    return render_template(
        "homeowner/care_seasonal_checklists.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/home-protection", methods=["GET"])
def homeowner_care_home_protection():
    """Home protection guide."""
    return render_template(
        "homeowner/care_home_protection.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/warranty-log", methods=["GET"])
def homeowner_care_warranty_log():
    """Warranty log."""
    return render_template(
        "homeowner/care_warranty_log.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/care/energy-savings", methods=["GET"])
def homeowner_care_energy_savings():
    """Energy savings guide."""
    return render_template(
        "homeowner/care_energy_savings.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/ask-question", methods=["GET", "POST"])
def homeowner_support_ask_question():
    """Ask a question."""
    user = get_current_user()
    if request.method == "POST":
        topic = request.form.get("topic", "").strip()
        question = request.form.get("question", "").strip()
        if topic and question and user:
            add_homeowner_question(user["id"], topic, question)
            flash("Question submitted! We'll get back to you soon.", "success")
            return redirect(url_for("homeowner_support_ask_question"))

    return render_template(
        "homeowner/support_ask_question.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/chat-human", methods=["GET"])
def homeowner_support_chat_human():
    """Chat with human support."""
    return render_template(
        "homeowner/support_chat_human.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/schedule-chat", methods=["GET"])
def homeowner_support_schedule_chat():
    """Schedule a chat."""
    return render_template(
        "homeowner/support_schedule_chat.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/resources", methods=["GET"])
def homeowner_support_resources():
    """Support resources."""
    return render_template(
        "homeowner/support_resources.html",
        brand_name=FRONT_BRAND_NAME,
    )


@app.route("/homeowner/support/meet-team", methods=["GET"])
def homeowner_support_meet_team():
    """Meet the team."""
    return render_template(
        "homeowner/support_meet_team.html",
        brand_name=FRONT_BRAND_NAME,
    )


# ---------------- DEVELOPMENT SERVER ----------------
if __name__ == "__main__":
    # Only runs when executing directly with Python (not with gunicorn)
    # Gunicorn will import the app and won't execute this block
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=True,  # Enable debug mode for development
    )

