print('>>> THIS IS THE REAL app.py BEING RUN <<<')

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
import secrets

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
    board_name = data.get("board_name", "").strip()
    summary = data.get("project_summary", "").strip()

    if not name:
        return jsonify({"success": False, "error": "Project name required"}), 400

    try:
        budget_val = float(budget) if budget else None
    except Exception:
        budget_val = None

    # If a board_name is provided, save as a design board note as well
    if board_name:
        note_title = name
        notes = request.form.get("project_notes", "").strip()
        note_details = summary or notes
        add_design_board_note(user_id, board_name, note_title, note_details)

    notes = request.form.get("project_notes", "").strip()
    add_homeowner_project(user_id, name, budget_val, status, notes)
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


def start_scheduler():
    scheduler = BackgroundScheduler()
    scheduler.add_job(send_due_reminders, "cron", hour=12, minute=0)
    scheduler.start()
    print("✓ Reminder scheduler started.")


# Start scheduler when app starts
start_scheduler()


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
    return {
        "new_leads": sum((c1["stage"] or "") == "new" for c1 in contacts),
        "active_transactions": 0,
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
    """
    role = request.args.get("role", "homeowner")
    if role not in ("homeowner", "agent", "lender"):
        role = "homeowner"

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
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

        if role == "agent":
            return redirect(url_for("agent_dashboard"))
        elif role == "lender":
            return redirect(url_for("lender_dashboard"))
        else:
            return redirect(url_for("homeowner_overview"))

    return render_template(
        "auth/signup.html", role=role, brand_name=FRONT_BRAND_NAME
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
    """
    user = get_current_user()
    snapshot = get_homeowner_snapshot_or_default(user)

    return render_template(
        "homeowner/overview.html",
        brand_name=FRONT_BRAND_NAME,
        snapshot=snapshot,
        cloud_cma_url=CLOUD_CMA_URL,
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


@app.route("/homeowner/design-boards", methods=["GET"])
def homeowner_design_boards():
    """
    Legacy route for Design Boards.
    All design boards are now managed inside homeowner_saved_notes,
    so this simply redirects users to the correct page.
    """
    return redirect(url_for("homeowner_saved_notes"))


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


@app.route("/homeowner/reno/material-cost", methods=["GET"])
def homeowner_reno_material_cost():
    return render_template(
        "homeowner/reno_material_cost.html",
        brand_name=FRONT_BRAND_NAME,
    )
