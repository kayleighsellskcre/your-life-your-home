import time
print('>>> THIS IS THE REAL app.py BEING RUN <<<')

import os
import boto3
from functools import wraps
from typing import Optional, List, Dict, Tuple
from pathlib import Path
from uuid import uuid4
from datetime import datetime
import sqlite3
import json
from types import SimpleNamespace
from PIL import Image
import secrets
import pandas as pd
import io

# Load environment variables from .env file (if it exists)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv not installed - that's okay, will use system env vars
    pass

from flask import (
    send_file,
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
    make_response,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

# Stripe integration
try:
    from stripe_payments import (
        create_checkout_session, create_customer_portal_session,
        handle_checkout_completed, handle_subscription_deleted,
        verify_webhook, SUBSCRIPTION_TIERS
    )
except ImportError:
    print("[WARNING] stripe_payments module not found. Stripe features will not work.")
    SUBSCRIPTION_TIERS = {}

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

        print(f"[OK] Processed fixture: {Path(image_path).name}")
        return True

    except Exception as e:
        print(f" Failed: {Path(image_path).name} - {e}")
        return False


# ---------------- HELPER FUNCTIONS FOR FILE UPLOADS ----------------
def handle_profile_file_upload(file_field_name: str, folder: str = "profiles", role_prefix: str = ""):
    """
    Consolidated helper for handling profile photo/logo uploads.
    Stores files as base64 data URLs in the database so they NEVER disappear on Railway redeploys.
    Returns the data URL or None if no file was uploaded.
    """
    import base64
    
    if file_field_name not in request.files:
        return None
    
    file = request.files[file_field_name]
    if not file or not file.filename:
        return None
    
    try:
        # Read file content
        file_content = file.read()
        
        # Detect image type from magic bytes (first few bytes of file)
        img_type = 'png'  # default
        if file_content.startswith(b'\xff\xd8\xff'):
            img_type = 'jpeg'
        elif file_content.startswith(b'\x89PNG'):
            img_type = 'png'
        elif file_content.startswith(b'GIF87a') or file_content.startswith(b'GIF89a'):
            img_type = 'gif'
        elif file_content.startswith(b'RIFF') and file_content[8:12] == b'WEBP':
            img_type = 'webp'
        elif file_content.startswith(b'<svg') or file_content.startswith(b'<?xml'):
            img_type = 'svg+xml'
        else:
            # Fallback to filename extension
            ext = file.filename.rsplit('.', 1)[-1].lower() if '.' in file.filename else 'png'
            img_type = 'jpeg' if ext == 'jpg' else ext
        
        # Convert to base64
        base64_encoded = base64.b64encode(file_content).decode('utf-8')
        
        # Create data URL
        data_url = f"data:image/{img_type};base64,{base64_encoded}"
        
        print(f"{role_prefix}PROFILE: File converted to data URL (size: {len(data_url)} chars, type: {img_type})")
        return data_url
        
    except Exception as e:
        import traceback
        print(f"{role_prefix}PROFILE: Error uploading file: {e}")
        print(traceback.format_exc())
        flash("We could not upload that file. Please try a different image.", "error")
        return None


def preserve_existing_profile_media(user_id: int, professional_photo: Optional[str] = None,
                                     brokerage_logo: Optional[str] = None):
    """
    Preserve existing profile photos/logos if new ones aren't being uploaded.
    Always reads the latest DB values so a transient lookup failure never
    causes previously-saved media to be lost.
    Returns tuple: (final_photo, final_logo)
    """
    from database import get_user_profile
    try:
        existing_profile = get_user_profile(user_id)
        if existing_profile:
            if hasattr(existing_profile, 'keys') and not isinstance(existing_profile, dict):
                existing_profile = dict(existing_profile)
            elif not isinstance(existing_profile, dict):
                existing_profile = {}
            existing_photo = existing_profile.get("professional_photo") or None
            existing_logo  = existing_profile.get("brokerage_logo") or None
        else:
            existing_photo = None
            existing_logo  = None
    except Exception as e:
        print(f"[PRESERVE MEDIA] Warning: could not read existing profile for user {user_id}: {e}")
        existing_photo = None
        existing_logo  = None

    # Only replace when a genuinely new file was uploaded
    final_photo = professional_photo if (professional_photo and professional_photo != "") else existing_photo
    final_logo  = brokerage_logo  if (brokerage_logo  and brokerage_logo  != "") else existing_logo
    return final_photo, final_logo


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
    get_homeowner_project,
    update_homeowner_project,
    delete_homeowner_project,
    get_homeowner_note_by_id,
    update_homeowner_note,
    row_to_dict,
    rows_to_dicts,
    delete_homeowner_note,
    upsert_next_move_plan,
    get_next_move_plan,
    add_homeowner_question,
    add_agent_contact,
    list_agent_contacts,
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
    remove_fixtures_from_board,
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
get_db_connection = get_connection

# Alias so financials routes can call get_db_connection()
get_db_connection = get_connection

# Initialize DBs so platform loads with no manual trigger
init_db()
try:
    from database import ensure_rbac_tables
    ensure_rbac_tables()
    from database import ensure_indexes
    ensure_indexes()
except Exception as _rbac_err:
    print(f"[DATABASE] RBAC tables check skipped: {_rbac_err}")

# Run Stripe column migration safely
try:
    from database import ensure_stripe_columns
    ensure_stripe_columns()
except Exception as e:
    print(f"[Startup] Stripe migration warning: {e}")

# Initialize promo codes table and seed launch codes
try:
    from database import ensure_promo_codes_table, seed_promo_codes
    ensure_promo_codes_table()
    seed_promo_codes([
        ("YLH-GOLD-LAUNCH1", "VIP Launch Code 1"),
        ("YLH-GOLD-LAUNCH2", "VIP Launch Code 2"),
        ("YLH-GOLD-LAUNCH3", "VIP Launch Code 3"),
        ("YLH-GOLD-LAUNCH4", "VIP Launch Code 4"),
        ("YLH-GOLD-LAUNCH5", "VIP Launch Code 5"),
    ])
except Exception as e:
    print(f"[Startup] Promo code init warning: {e}")

app = Flask(__name__)
_IS_PRODUCTION = bool(os.environ.get("RAILWAY_ENVIRONMENT") or os.environ.get("YLH_ENV") == "production")
_secret = os.environ.get("YLH_SECRET_KEY")
if not _secret:
    # The old fallback string is public in git history; anyone who knows it can forge
    # a session. Keep a fallback so the app still boots, but be loud about it.
    print("[SECURITY WARNING] YLH_SECRET_KEY is not set. Set it to a long random value "
          "(python -c \"import secrets; print(secrets.token_hex(32))\") in your environment.")
    _secret = "change-this-secret-key"
app.secret_key = _secret
app.config["TEMPLATES_AUTO_RELOAD"] = not _IS_PRODUCTION
app.config["PERMANENT_SESSION_LIFETIME"] = 86400 * 30  # 30 days for persistent sessions
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_SECURE"] = _IS_PRODUCTION  # HTTPS only in production
app.config["MAX_CONTENT_LENGTH"] = 250 * 1024 * 1024  # 250 MB upload cap


# ── Security hardening: headers + cross-site POST guard ─────────────────────
_CSRF_EXEMPT_PATHS = ("/stripe/webhook", "/api/homebot/webhook", "/api/lead-intake/")


_AREA_HOME = {"agent": "agent_dashboard", "lender": "lender_dashboard", "homeowner": "homeowner_overview"}


@app.before_request
def _enforce_area_access():
    """Each area (/agent, /lender, /homeowner) is for signed-in members of that role only."""
    area = request.path.split("/")[1] if request.path.count("/") >= 1 else ""
    if area not in _AREA_HOME:
        return None
    uid, role = session.get("user_id"), session.get("role")
    if not uid:
        return redirect(url_for("login", role=area))
    if role == "admin" or role == area:
        return None
    return redirect(url_for(_AREA_HOME.get(role, "index")))


@app.before_request
def _block_cross_site_posts():
    """Reject state-changing requests whose Origin header points at another site.

    Browsers always send Origin on cross-origin POSTs, so this stops classic CSRF
    without needing a token in every form. Server-to-server webhooks (no Origin)
    and the explicitly exempt public endpoints are unaffected.
    """
    if request.method in ("GET", "HEAD", "OPTIONS"):
        return None
    if request.path.startswith(_CSRF_EXEMPT_PATHS):
        return None
    origin = request.headers.get("Origin")
    if origin and origin != "null":
        from urllib.parse import urlparse
        if urlparse(origin).netloc != request.host:
            return ("Cross-site request blocked.", 403)
    return None


if _IS_PRODUCTION:
    # Railway terminates HTTPS in front of the app: trust one proxy hop so request.remote_addr
    # is the real client IP and url_for(_external=True) builds https:// links.
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)


# ── Simple in-memory rate limiting (per worker) ──────────────────────────────
import time as _time
import threading as _threading

_RATE_HITS = {}
_RATE_LOCK = _threading.Lock()
# endpoint -> (max requests, window seconds)
_RATE_RULES = {
    "login": (8, 900),             # 8 sign-in attempts / 15 min per IP
    "signup": (10, 3600),
    "forgot_password": (5, 3600),
    "reset_password": (10, 3600),
    "concierge_chat": (20, 600),   # public AI chat costs real money per message
    "lead_intake_webhook": (30, 600),
    "resend_verification": (3, 3600),
    "login_verify": (10, 900),
}


def _rate_limited(key, limit, window):
    now = _time.time()
    with _RATE_LOCK:
        hits = [t for t in _RATE_HITS.get(key, []) if now - t < window]
        if len(hits) >= limit:
            _RATE_HITS[key] = hits
            return True
        hits.append(now)
        _RATE_HITS[key] = hits
        if len(_RATE_HITS) > 5000:  # keep memory bounded
            for k in [k for k, v in _RATE_HITS.items() if not v or now - v[-1] > 3600]:
                _RATE_HITS.pop(k, None)
    return False


@app.before_request
def _apply_rate_limits():
    rule = _RATE_RULES.get(request.endpoint or "")
    if not rule or request.method != "POST":
        return None
    limit, window = rule
    ip = request.remote_addr or "unknown"
    keys = [f"{request.endpoint}:ip:{ip}"]
    if request.endpoint == "login":
        email = (request.form.get("email") or "").strip().lower()
        if email:
            keys.append(f"login:email:{email}")  # also blunts distributed guessing
    if any(_rate_limited(k, limit, window) for k in keys):
        if request.is_json or request.path.startswith("/api/") or request.endpoint == "concierge_chat":
            return jsonify({"error": "Too many requests. Please slow down and try again shortly."}), 429
        flash("That was a lot of tries in a row. Please wait a few minutes and try again.", "error")
        return redirect(url_for("login")), 303
    return None


_ALLOWED_UPLOAD_EXT = {
    "png", "jpg", "jpeg", "gif", "webp", "heic", "heif", "bmp", "tif", "tiff",   # images
    "pdf", "doc", "docx", "xls", "xlsx", "csv", "txt", "rtf", "ppt", "pptx",     # documents
    "mp4", "mov", "webm", "m4v",                                                 # video
}


@app.before_request
def _validate_uploads():
    """One allow-list for every upload form. Blocks .html/.svg/.js/.exe etc. that could
    run scripts or malware when opened from our domain."""
    if request.method != "POST" or not request.files:
        return None
    for f in [fl for key in request.files for fl in request.files.getlist(key)]:
        name = (f.filename or "").strip()
        if not name:
            continue  # empty file input
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in _ALLOWED_UPLOAD_EXT:
            msg = "That file type isn't supported. Please upload an image, PDF, Word, Excel or CSV file."
            if request.is_json or request.path.startswith("/api/") or request.headers.get("X-Requested-With"):
                return jsonify({"error": msg}), 400
            flash(msg, "error")
            return redirect(request.referrer or url_for("index")), 303
    return None


@app.template_filter("load_json")
def _load_json_filter(value):
    """Parse a JSON string (e.g. a stored list of file names); empty list if blank or invalid."""
    import json as _json
    try:
        return _json.loads(value) if value else []
    except (TypeError, ValueError):
        return []


@app.context_processor
def _inject_now_year():
    from datetime import datetime
    try:
        css_v = int((Path(app.static_folder) / "css" / "ylh.bundle.css").stat().st_mtime)
    except OSError:
        css_v = 0
    return {"now_year": datetime.now().year, "css_version": css_v}


@app.after_request
def _cache_static(response):
    """Let browsers keep static files: the stylesheet is versioned (?v=...), so it can be cached for a
    year; images and other files are kept for a week so a swapped photo still shows up soon."""
    if request.path.startswith("/static/") and response.status_code == 200 and response.headers.get("Cache-Control", "no-cache") == "no-cache":
        if request.args.get("v") and request.path.endswith((".css", ".js")):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        else:
            response.headers["Cache-Control"] = "public, max-age=604800"
    return response


@app.after_request
def _security_headers(response):
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    if _IS_PRODUCTION:
        response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response

# ── Custom Jinja2 filters ────────────────────────────────────────────────────
@app.template_filter("min")
def jinja_min(value):
    """Return the minimum of an iterable (Jinja2 doesn't have |min built-in)."""
    try:
        return min(value)
    except Exception:
        return value

@app.template_filter("max")
def jinja_max(value):
    """Return the maximum of an iterable."""
    try:
        return max(value)
    except Exception:
        return value

@app.template_filter("strftime")
def jinja_strftime(value, fmt="%b %d, %Y"):
    """Format a date string or datetime object using strftime."""
    if not value:
        return ""
    try:
        if isinstance(value, str):
            import dateutil.parser as _dp
            value = _dp.parse(value)
        return value.strftime(fmt)
    except Exception:
        return str(value)
# ─────────────────────────────────────────────────────────────────────────────

# Context processor to make professionals available to all homeowner templates
def hex_to_color_name(hex_code):
    """Convert hex color code to official Sherwin-Williams color name."""
    if not hex_code:
        return hex_code
    
    # Normalize hex code (remove #, convert to uppercase)
    hex_clean = hex_code.strip().upper().replace('#', '')
    if len(hex_clean) == 3:
        hex_clean = ''.join([c*2 for c in hex_clean])
    hex_clean = '#' + hex_clean
    
    # Complete Sherwin-Williams Color Database (323 official colors)
    # Extracted from the create board area to ensure accuracy
    color_map = {
        # WHITES
        '#EDEAE0': 'Alabaster', '#F3F1EC': 'Extra White', '#EFEEE8': 'Pure White',
        '#F4F0E8': 'Polar Bear', '#F0EBE1': 'Greek Villa', '#F3F2ED': 'Snowbound',
        '#F7F5F0': 'High Reflective White', '#F0EDE4': 'Westhighland White',
        '#F2EFE7': 'Cotton White', '#F1EDE3': 'White Duck', '#F5F2E9': 'Divine White',
        '#EAE7DD': 'City Loft', '#EFECE3': 'Moderne White', '#F1EEE6': 'Origami White',
        '#F0EDE5': 'Roman Column', '#EFE9DD': 'Pearly White', '#F2EBDB': 'Creamy',
        '#E8DDCC': 'Navajo White', '#E9E0D1': 'Antique White', '#F0E8D9': 'Vanilla Milkshake',
        '#F5F0E6': 'Steamed Milk', '#F4F1EA': 'Ethereal White', '#F6F3EC': 'Marshmallow',
        '#F2EFE8': 'Cloud White', '#F3EFE6': 'Eider White', '#F0ECE2': 'Swiss Coffee',
        '#EFEADE': 'Ivory Tower', '#F1EAE0': 'Cashmere', '#F4F0E7': 'Twinkle',
        '#F3EEE5': 'Summer White', '#F2EDE4': 'White Flour', '#F0ECE3': 'Zurich White',
        '#F1EBE1': 'Pearl Oyster', '#F3EDE3': 'Morning Delight', '#F0EAE0': 'White Heron',
        '#F2ECE2': 'Cotton Seed', '#F0E9DF': 'Nacre', '#F2EDE5': 'China White',
        '#F0EBE3': 'White Lilac', '#EFEAE2': 'White Raisin', '#F3EEE6': 'Gauze',
        '#F1ECE4': 'Opaline', '#EFE9DE': 'Vanilla Mocha', '#F0EAE1': 'Crisp Linen',
        '#EFE8DC': 'Buff', '#F2EDE6': 'Paperwhite', '#F1EBE2': 'Grecian Ivory',
        '#EFE9DE': 'Palish Peach', '#F3EEE7': 'Panda White', '#F1ECE4': 'Nouveau Narrative',
        
        # NEUTRALS & BEIGES
        '#D6C8B8': 'Accessible Beige', '#E2DACF': 'Natural Linen', '#CFC0A8': 'Kilim Beige',
        '#D5C7B8': 'Balanced Beige', '#C8BAAC': 'Perfect Greige', '#D7CCBB': 'Nomadic Desert',
        '#DDD3C1': 'Wool Skein', '#E5D8C5': 'Sand Beach', '#E9E3D7': 'Aesthetic White',
        '#E7DDD3': 'Shoji White', '#EBE5DC': 'Canvas Tan', '#DAD0C0': 'Naturale',
        '#E4DCCE': 'Patience', '#CFC0AE': 'Shiitake', '#D8CCBA': 'Utterly Beige',
        '#E1D6C6': 'Softer Tan', '#D5C7B3': 'Whole Wheat', '#D9CCBA': 'Believable Buff',
        '#CEC0B0': 'Smoky Sand', '#D0C2B2': 'Nantucket Dune', '#D4CEC3': 'Gateway Gray',
        '#CBC0B2': 'On the Rocks', '#D9C7B5': 'Sanderling', '#E5D5C3': 'Cottage Cream',
        '#E1D3BF': 'Crisp Linen', '#DFD4C1': 'Loggia', '#CEC0AF': 'Relaxed Khaki',
        '#E7DED1': 'Relaxed White', '#DFD1BD': 'Bagel', '#D3C4B0': 'Universal Khaki',
        
        # GRAYS
        '#D5CFC1': 'Agreeable Gray', '#C9CCC4': 'Repose Gray', '#C2BDB1': 'Worldly Gray',
        '#D1CEC4': 'Colonnade Gray', '#C5C5BD': 'Mindful Gray', '#B8B5AF': 'Requisite Gray',
        '#BFB9AE': 'Anonymous', '#D0CCC2': 'Pediment', '#C7C3B9': 'Useful Gray',
        '#D2CFC8': 'Gossamer Veil', '#D9D6CD': 'Incredible White', '#CAC6BC': 'Aesthetic',
        '#BEB9AE': 'Versatile Gray', '#C6C3BA': 'Popular Gray', '#D3D0C7': 'Passive',
        '#C2C0BA': 'Big Chill', '#C4BFB5': 'Alpaca', '#C9C6BC': 'Collonade Gray',
        '#C4C0B7': 'Twilight Gray', '#B6B3AB': 'Gray Clouds', '#ACA9A0': 'Dorian Gray',
        '#BBB7AD': 'Mega Greige', '#ADA9A0': 'Pavestone', '#B9B5AB': 'Perfect Greige',
        '#C8C5BD': 'Gray Screen', '#B3AFA6': 'Argos', '#CFD1CD': 'Light French Gray',
        '#C2C5C1': 'Silverplate', '#B5B8B4': 'Gray Shingle', '#ADB1AD': 'Front Porch',
        '#A6AAA6': 'Unusual Gray', '#9FA3A0': 'Magnetic Gray', '#989C99': 'Online',
        '#919594': 'Software', '#8A8E8D': 'Grays Harbor', '#838786': 'Mount Etna',
        '#C4C5C0': 'Classic French Gray', '#BDBDB8': 'Ellie Gray', '#D6D7D2': 'Site White',
        '#CFCFC9': 'Moderne White', '#B3B4AF': 'Conservative Gray', '#ACACA7': 'Serious Gray',
        '#A5A5A0': 'Functional Gray', '#9E9E99': 'Cityscape', '#989893': 'Westchester Gray',
        '#91918C': 'Attitude Gray',
        
        # GREENS & SAGE
        '#D1D9CA': 'Sea Salt', '#8F9E8A': 'Evergreen Fog', '#B8C5B4': 'Clary Sage',
        '#C9D4CB': 'Comfort Gray', '#A5B2A0': 'Softened Green', '#8B9B8A': 'Retreat',
        '#B5BFB3': 'Acacia Haze', '#7D8C7A': 'Dried Thyme', '#B2BFB0': 'Svelte Sage',
        '#C2CFBC': 'Contented', '#C7D4C7': 'Filmy Green', '#B8C8B6': 'Liveable Green',
        '#D1DCC9': 'Lacewing', '#B1C0A8': 'Gratifying Green', '#C5D1C3': 'Rare Gray',
        '#ADBCA8': 'Celadon', '#94A88B': 'Basil', '#A3B59D': 'Restful',
        '#99AA94': 'Haven', '#8FA087': 'Nurture Green', '#7E9078': 'Artichoke',
        '#6E8266': 'Relish', '#4D6A4B': 'Woodland Green', '#5F7A5D': 'Garden Grove',
        '#6D886B': 'Privilege Green', '#7E9879': 'Bonsai Tint', '#8FA68C': 'Nurture Green',
        '#A3B5A0': 'Jardin Day', '#B2C3B0': 'Jocular Green', '#C1D2C0': 'Spirited Green',
        '#D0E0CF': 'Lighter Mint', '#B9D4BC': 'Mint Condition', '#728A70': 'Vogue Green',
        '#869885': 'Garden Sage', '#9AA799': 'Jade Dragon', '#AEB6AD': 'Halcyon Green',
        '#C2C5C0': 'Oyster Bay', '#C7C8C3': 'Collonade Gray',
        
        # BLUES & AQUAS
        '#B5C4C7': 'Rain', '#C4D4D9': 'Topsail', '#A8BCC4': 'Quietude',
        '#B8CAD1': 'Spa', '#89A3AE': 'Interesting Aqua', '#7B95A3': 'Refuge',
        '#A0B5BF': 'Jetstream', '#B8C9D2': 'Atmospheric', '#A5BAC7': 'Sleepy Blue',
        '#9DB0BC': 'Meditative', '#CAD9E1': 'Mountain Air', '#C2D4DE': 'Mild Blue',
        '#D4E4E8': 'Hint of Mint', '#B5CAD6': 'Byte Blue', '#9EAEB9': 'North Star',
        '#8FA2B0': 'Resolute Blue', '#3E5671': 'Needlepoint Navy', '#26465A': 'Naval',
        '#29465F': 'Loyal Blue', '#2E4F66': 'Anchors Aweigh', '#7799A0': 'Cascade Green',
        '#8BAAB5': 'Pool Blue', '#A0BBC8': 'Powder Blue', '#B5CDDB': 'Copen Blue',
        '#CADEE8': 'Aviary Blue', '#5A8CA0': 'Blissful Blue', '#4C7C93': 'Georgian Bay',
        '#3E6C86': 'Secure Blue', '#7095A8': 'Stream', '#84A5B7': 'Leisure Blue',
        '#98B6C6': 'Windy Blue', '#ACC7D5': 'Languid Blue', '#C0D8E4': 'Rhythmic Blue',
        '#5577AA': 'Jacaranda', '#4466A8': 'Blue Chip', '#33559A': 'Dignity Blue',
        '#224488': 'Honorable Blue', '#113366': 'Commodore',
        
        # WARM TONES & CREAMS
        '#F2E8DA': 'Napery', '#F1E5D5': 'Ivory Lace', '#E8DCC9': 'Wool Skein',
        '#E3D4BE': 'Toasted Pine Nut', '#E2D5C0': 'Buff', '#D9CAB3': 'Crewel Tan',
        '#D5C6AF': 'Mannered Gold', '#E7DAC7': 'Rice Grain', '#F0E3D1': 'Nacre',
        '#EFE2D0': 'Honied White', '#DCCDB7': 'Rustic City', '#D8C9B2': 'Bittersweet Stem',
        '#E8DCC8': 'Sand Dollar', '#E5D8C4': 'Navajo White', '#E2D5C1': 'Oyster Bar',
        '#DFD1BD': 'Latte', '#DBCEB9': 'Whole Wheat', '#D8CAB6': 'Softer Tan',
        '#D5C7B2': 'Macadamia', '#D1C3AE': 'Nomadic Desert', '#CEC0AB': 'Sand Beach',
        '#CABCA7': 'Pavilion Beige', '#C7B9A4': 'Ramie', '#C3B5A0': 'Tony Taupe',
        '#C0B29D': 'Tavern Taupe', '#BCAE99': 'Doeskin', '#B9AB96': 'Khaki Shade',
        '#B5A792': 'Corkboard', '#E6D9C8': 'Dhurrie Beige', '#E3D6C5': 'Toasted Pine Nut',
        '#DFD2C1': 'Crewel Tan', '#DCCFBE': 'Mannered Gold', '#D8CBBA': 'Diverse Beige',
        '#D5C8B7': 'Wool Skein', '#D1C4B3': 'Smoky Beige', '#CEC1AF': 'Sanderling',
        '#CABDAC': 'Stone Lion', '#C7BAA8': 'Brandon Beige', '#C3B6A5': 'Balanced Beige',
        '#C0B3A1': 'Taupe Tone', '#BCAF9E': 'Versatile Gray', '#B9AC9A': 'Pathway',
        '#B5A897': 'Tea Chest', '#B2A593': 'Harmonic Tan',
        
        # DARK & DRAMATIC
        '#3A3A38': 'Iron Ore', '#3E3E3D': 'Black Magic', '#3C3A35': 'Urbane Bronze',
        '#6B685F': 'Muddled Basil', '#57675D': 'Jasper', '#4E5D53': 'Pewter Green',
        '#2F2F30': 'Tricorn Black', '#3B3935': 'Black Bean', '#635F58': 'Peppercorn',
        '#393937': 'Andiron', '#31353D': 'Inkwell', '#32383F': 'Caviar',
        '#2E3134': 'Cyberspace', '#3E3E3C': 'Domino', '#504C48': 'Gauntlet Gray',
        '#4B4542': 'Sealskin', '#6C6861': 'Grizzle Gray', '#736E67': 'Mink',
        '#6D6864': 'Garret Gray', '#7A6E63': 'Brainstorm Bronze', '#6B6259': 'Urbane Bronze',
        '#635F57': 'Black Fox', '#5D5955': 'Thunderous', '#5A5550': 'Sable',
        '#585551': 'Anew Gray', '#6B6A5F': 'Muddled Basil', '#3C4A3E': 'Rookwood Dark Green',
        '#384337': 'Foxhall Green', '#2A4030': 'Shamrock', '#2C3D32': 'Roycroft Bottle Green',
        
        # ACCENT COLORS - REDS & PINKS
        '#8E2C2A': 'Real Red', '#99322F': 'Fireweed', '#A43833': 'Red Bay',
        '#AF3E38': 'Positive Red', '#BA443C': 'Tanager', '#C54A41': 'Habanero Chile',
        '#E57A6E': 'Coral', '#EA8A7F': 'Charisma', '#EF9A90': 'Dishy Coral',
        '#F4AAA1': 'Jovial', '#F9BAB2': 'Mellow Coral', '#F5E5E3': 'Touching White',
        '#D9B1B1': 'Rose Colored', '#E4C8C8': 'Rose Embroidery',
        
        # ACCENT COLORS - YELLOWS & GOLDS
        '#C89D34': 'Gold Rush', '#D3A83A': 'Nugget', '#DEB340': 'Golden Fleece',
        '#E9BE46': 'Glitzy Gold', '#F4C94C': 'Fun Yellow', '#F9D452': 'Lively Yellow',
        '#FEDF58': 'Confident Yellow', '#F5E682': 'Daffodil', '#F9EA8C': 'Lucent Yellow',
        '#FDEE96': 'Banana Cream', '#FFF2A0': 'Butter Up', '#FFF6AA': 'Lantern Light',
        
        # ACCENT COLORS - PURPLES & LAVENDERS
        '#6A5B7B': 'Kimono Violet', '#5C4D66': 'Plummy', '#4E3F51': 'Dewberry',
        '#766889': 'Fabulous Grape', '#8A7A9E': 'Venture Violet', '#9E8DB3': 'Brave Purple',
        '#B3A0C8': 'Novel Lilac', '#C7B3DD': 'Rhapsody Lilac', '#DBC6F2': 'Inspired Lilac',
        '#E8D9F5': 'Elation', '#F4EDFA': 'Potentially Purple', '#C7B5D8': 'Spangle',
        
        # ACCENT COLORS - ORANGES & TERRACOTTA
        '#A54826': 'Cayenne', '#B5532C': 'Determined Orange', '#C55E32': 'Copper Mountain',
        '#D56938': 'Husky Orange', '#E5743E': 'Energetic Orange', '#F57F44': 'Tango',
        '#FA8A4A': 'Outgoing Orange', '#FE9550': 'Surprise Amber', '#FFA056': 'Kumquat',
        '#FFAB5C': 'Succulent Peach', '#FFB662': 'Tangerine', '#FFC168': 'Exciting Orange',
    }
    
    # Fallback for common custom colors not in Sherwin-Williams database
    fallback_map = {
        '#F6E9DF': 'Cream',  # Custom cream color
        '#B79F82': 'Taupe',  # Custom taupe color
        '#6B6A45': 'Olive Green',  # Custom olive (close to Muddled Basil)
        '#3A352C': 'Charcoal',  # Custom charcoal (close to Urbane Bronze)
    }
    
    # Check exact match in main database first
    if hex_clean in color_map:
        return color_map[hex_clean]
    
    # Check fallback map
    if hex_clean in fallback_map:
        return fallback_map[hex_clean]
    
    # Try to find closest match by RGB distance (for custom colors)
    try:
        r1 = int(hex_clean[1:3], 16)
        g1 = int(hex_clean[3:5], 16)
        b1 = int(hex_clean[5:7], 16)
        
        closest_name = None
        min_distance = float('inf')
        
        # Search through all Sherwin-Williams colors
        for hex_val, name in color_map.items():
            if hex_val.startswith('#'):
                r2 = int(hex_val[1:3], 16)
                g2 = int(hex_val[3:5], 16)
                b2 = int(hex_val[5:7], 16)
                
                distance = ((r1-r2)**2 + (g1-g2)**2 + (b1-b2)**2)**0.5
                if distance < min_distance:
                    min_distance = distance
                    closest_name = name
        
        # If very close (within 15 color units), use the closest Sherwin-Williams name
        if min_distance < 15:
            return closest_name
    except Exception:
        pass
    
    # Fallback: return hex code if no match found
    return hex_code


@app.context_processor
def inject_professionals():
    """Make professionals data available to all templates - CRITICAL FOR DASHBOARD DISPLAY."""
    from database import get_homeowner_professionals
    professionals = []
    user = get_current_user()
    if user and user.get("role") == "homeowner" and user.get("id"):
        try:
            homeowner_id = user.get("id")
            profs_raw = get_homeowner_professionals(homeowner_id)
            _dbg(f"CONTEXT PROCESSOR: Loading professionals for homeowner {homeowner_id} - found {len(profs_raw)}")
            
            for prof in profs_raw:
                if hasattr(prof, 'keys'):
                    prof_dict = dict(prof)
                    # Ensure professional_role is set correctly
                    if not prof_dict.get('professional_role'):
                        prof_dict['professional_role'] = prof_dict.get('professional_type') or prof_dict.get('role') or prof_dict.get('user_id')
                    
                    # Ensure we have the professional_id
                    if not prof_dict.get('professional_id'):
                        prof_dict['professional_id'] = prof_dict.get('user_id')
                    
                    professionals.append(prof_dict)
                    _dbg(f"CONTEXT PROCESSOR: Added professional - role: {prof_dict.get('professional_role')}, name: {prof_dict.get('name')}, id: {prof_dict.get('professional_id')}, phone: {prof_dict.get('phone')}")
                else:
                    professionals.append(prof)
            
            if not professionals:
                _dbg(f"CONTEXT PROCESSOR WARNING: No professionals found for homeowner {homeowner_id}")
                # Try to get from agent_id column as fallback
                from database import get_user_by_id
                homeowner_user = get_user_by_id(homeowner_id)
                if homeowner_user:
                    homeowner_dict = dict(homeowner_user) if hasattr(homeowner_user, 'keys') and not isinstance(homeowner_user, dict) else homeowner_user
                    agent_id = homeowner_dict.get("agent_id")
                    if agent_id:
                        _dbg(f"CONTEXT PROCESSOR: Found agent_id {agent_id} in user record, attempting to load...")
                        try:
                            from database import get_user_by_id, get_user_profile
                            agent_user = get_user_by_id(agent_id)
                            if agent_user:
                                agent_dict = dict(agent_user) if hasattr(agent_user, 'keys') and not isinstance(agent_user, dict) else agent_user
                                agent_profile = get_user_profile(agent_id)
                                prof_data = {
                                    'professional_id': agent_id,
                                    'professional_role': 'agent',
                                    'name': agent_dict.get('name'),
                                    'email': agent_dict.get('email'),
                                    'user_id': agent_id
                                }
                                if agent_profile:
                                    profile_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') and not isinstance(agent_profile, dict) else agent_profile
                                    prof_data.update({
                                        'professional_photo': profile_dict.get('professional_photo'),
                                        'brokerage_logo': profile_dict.get('brokerage_logo'),
                                        'brokerage_name': profile_dict.get('brokerage_name'),
                                        'phone': profile_dict.get('phone'),
                                        'team_name': profile_dict.get('team_name'),
                                        'website_url': profile_dict.get('website_url'),
                                        'bio': profile_dict.get('bio'),
                                    })
                                professionals.append(prof_data)
                                _dbg(f"CONTEXT PROCESSOR: Added agent from agent_id column - {prof_data.get('name')}")
                        except Exception as fallback_error:
                            print(f"CONTEXT PROCESSOR: Fallback failed - {str(fallback_error)}")
        except Exception as e:
            import traceback
            print(f"CONTEXT PROCESSOR ERROR: {traceback.format_exc()}")
    else:
        if user:
            _dbg(f"CONTEXT PROCESSOR: User is not a homeowner - role: {user.get('role')}, id: {user.get('id')}")
        else:
            _dbg(f"CONTEXT PROCESSOR: No user logged in")
    
    # Helper function to check if photo exists and return correct path
    def get_professional_photo_url(photo_path):
        """Get professional photo URL, checking if file exists."""
        if not photo_path:
            return None
        # If it's already a full URL, return it
        if photo_path.startswith('http://') or photo_path.startswith('https://'):
            return photo_path
        # If it's a base64 data URL, return it directly (never try to use it as a file path)
        if photo_path.startswith('data:'):
            return photo_path
        # Check if file exists in static folder
        from pathlib import Path
        import os
        static_folder = app.static_folder or 'static'
        static_path = Path(static_folder) / photo_path
        # Normalize path to handle any directory separators
        static_path = static_path.resolve()
        static_folder_path = Path(static_folder).resolve()
        # Ensure the path is within static folder for security
        try:
            static_path.relative_to(static_folder_path)
            if static_path.exists() and static_path.is_file():
                return url_for('static', filename=photo_path)
        except ValueError:
            # Path is outside static folder, don't serve it
            pass
        return None
    
    return dict(professionals=professionals, hex_to_color_name=hex_to_color_name, get_professional_photo_url=get_professional_photo_url)


@app.context_processor
def inject_current_user():
    """Inject current_user into every template so layouts can check role."""
    user = get_current_user()
    return dict(current_user=user)


# ---------------- AJAX PLANNER ROUTE ----------------


# ---------------- TRANSACTION HELPERS IMPORT ----------------
from transaction_helpers import (
    get_db,
    add_transaction_participant,
    create_transaction,
    get_agent_transactions,
    delete_transaction,
    update_transaction,
    get_transaction_detail,
    get_transaction_documents,
    get_transaction_participants,
    get_transaction_timeline,
    get_transaction_document_status,
)

def _dbg(*args, **kwargs):
    """Chatty diagnostics: only printed when the YLH_DEBUG environment variable is set."""
    if os.environ.get("YLH_DEBUG"):
        print(*args, **kwargs)


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
    """Return the logged-in user's id; unauthenticated visitors get a 401 (never another user's data)."""
    uid = session.get("user_id")
    if not uid:
        abort(401)
    return uid


def get_current_user() -> Optional[dict]:
    """Get current logged-in user from session."""
    user_id = session.get("user_id")
    if not user_id:
        return None
    
    try:
        # Ensure user_id is integer
        user_id = int(user_id)
        row = get_user_by_id(user_id)
        
        if not row:
            # User not found in database - clear invalid session
            session.clear()
            return None
        
        # Convert Row to dict
        if hasattr(row, 'keys') and not isinstance(row, dict):
            return dict(row)
        
        return row if isinstance(row, dict) else None
    except (ValueError, TypeError) as e:
        # Invalid user_id in session - clear it
        print(f"ERROR get_current_user: Invalid user_id '{user_id}' - {str(e)}")
        session.clear()
        return None
    except Exception as e:
        print(f"ERROR get_current_user: Error getting user {user_id} - {str(e)}")
        import traceback
        print(traceback.format_exc())
        return None


def require_homeowner_access(homeowner_id: int) -> Tuple[Optional[dict], Optional[str]]:
    """
    Check if the current user can access a homeowner's data.
    Returns (user, error_message).
    If error_message is None, access is granted.
    """
    from database import can_access_homeowner
    
    user = get_current_user()
    if not user:
        return None, "Please log in to access this page."
    
    user_role = user.get("role")
    user_id = user.get("id")
    
    # Homeowners can only access their own data
    if user_role == "homeowner":
        if user_id != homeowner_id:
            return None, "You can only access your own dashboard."
        return user, None
    
    # Agents and lenders can access their linked homeowners
    if user_role in ("agent", "lender"):
        if can_access_homeowner(user_id, user_role, homeowner_id):
            return user, None
        return None, "You don't have access to this homeowner's data."
    
    return None, "Invalid user role."


# ---------------- AGENT TRANSACTION ROUTES ----------------
def _tx_docs_dir(tx_id):
    base = os.environ.get("RAILWAY_VOLUME_MOUNT_PATH")
    root = Path(base) / "tx_docs" if base else BASE_DIR / "uploads" / "tx_docs"
    d = root / str(int(tx_id))
    d.mkdir(parents=True, exist_ok=True)
    return d


PARTICIPANT_ROLES = {"client", "lender", "title_company", "transaction_coordinator", "other_agent", "inspector", "appraiser", "attorney", "other"}


# -------------------------------------------------
# EMAIL REMINDER AUTOMATION (GMAIL SMTP + APScheduler)
# -------------------------------------------------
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from apscheduler.schedulers.background import BackgroundScheduler

# Accept either EMAIL_* or MAIL_* variable names (Railway uses MAIL_*)
EMAIL_HOST = os.environ.get("EMAIL_HOST") or os.environ.get("MAIL_SERVER") or "smtp.gmail.com"
EMAIL_PORT = int(os.environ.get("EMAIL_PORT") or os.environ.get("MAIL_PORT") or 587)
EMAIL_USER = os.environ.get("EMAIL_USER") or os.environ.get("MAIL_USERNAME")
EMAIL_PASS = os.environ.get("EMAIL_PASS") or os.environ.get("MAIL_PASSWORD")


def _clean_header(value):
    """Keep names and addresses on one line so they can't inject extra email headers."""
    return " ".join(str(value or "").split())


_EMAIL_LAST = {"ok": None, "detail": ""}   # the most recent send result, shown on the admin Email Check page


def _from_address(from_name=None):
    """MAIL_FROM, with its display name swapped for from_name when one is given."""
    from email.utils import parseaddr, formataddr
    name, addr = parseaddr(os.environ.get("MAIL_FROM") or EMAIL_USER or "")
    if from_name:
        name = _clean_header(from_name)
    return name, addr, (formataddr((name, addr)) if addr else "")


def _reply_to_address(reply_to=None):
    """Who replies go to: the agent or lender when given, otherwise MAIL_REPLY_TO (if set)."""
    return _clean_header(reply_to or os.environ.get("MAIL_REPLY_TO") or "")


def _send_via_resend(to_email, subject, body, from_name=None, reply_to=None, html=None):
    """Send over HTTPS (port 443) with Resend. Works on hosts that block SMTP, like Railway's Hobby plan."""
    import json as _json
    import urllib.request as _req
    _, _, sender = _from_address(from_name)
    if not sender:
        print("[WARNING] RESEND_API_KEY is set but MAIL_FROM is not; cannot send.")
        _EMAIL_LAST.update(ok=False, detail="MAIL_FROM is not set in Railway.")
        return False
    data = {"from": sender, "to": [to_email], "subject": subject, "text": body}
    if html:
        data["html"] = html
    reply = _reply_to_address(reply_to)
    if reply:
        data["reply_to"] = [reply]
    payload = _json.dumps(data).encode("utf-8")
    request_ = _req.Request(
        "https://api.resend.com/emails", data=payload, method="POST",
        headers={"Authorization": f"Bearer {os.environ['RESEND_API_KEY']}", "Content-Type": "application/json"})
    try:
        with _req.urlopen(request_, timeout=15) as resp:
            ok = 200 <= resp.status < 300
        print(f"[OK] Email sent to {to_email} via Resend" if ok else f"[WARNING] Resend returned {resp.status}")
        _EMAIL_LAST.update(ok=ok, detail="" if ok else f"Resend returned {resp.status}.")
        return ok
    except Exception as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        print(f" Failed to send email to {to_email} via Resend: {e} {detail}")
        _EMAIL_LAST.update(ok=False, detail=f"Resend said: {detail or e}")
        return False


def _send_via_brevo(to_email, subject, body, from_name=None, reply_to=None, html=None):
    """Send over HTTPS (port 443) with Brevo's API. Works on hosts that block SMTP, like Railway's Hobby plan."""
    import json as _json
    import html as _html
    import urllib.request as _req
    name, addr, _ = _from_address(from_name)
    if not addr:
        print("[WARNING] BREVO_API_KEY is set but MAIL_FROM is not; cannot send.")
        _EMAIL_LAST.update(ok=False, detail="MAIL_FROM is not set in Railway.")
        return False
    sender = {"email": addr}
    if name:
        sender["name"] = name
    html_body = html or ("<div style=\"font-family:Arial,sans-serif;font-size:15px;line-height:1.5\">"
                         + _html.escape(body).replace("\n", "<br>") + "</div>")
    data = {
        "sender": sender, "to": [{"email": to_email}], "subject": subject,
        "htmlContent": html_body, "textContent": body,
    }
    reply = _reply_to_address(reply_to)
    if reply:
        data["replyTo"] = {"email": reply}
    payload = _json.dumps(data).encode("utf-8")
    request_ = _req.Request(
        "https://api.brevo.com/v3/smtp/email", data=payload, method="POST",
        headers={"api-key": os.environ["BREVO_API_KEY"], "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with _req.urlopen(request_, timeout=15) as resp:
            ok = 200 <= resp.status < 300
        print(f"[OK] Email sent to {to_email} via Brevo" if ok else f"[WARNING] Brevo returned {resp.status}")
        _EMAIL_LAST.update(ok=ok, detail="" if ok else f"Brevo returned {resp.status}.")
        return ok
    except Exception as e:
        detail = ""
        try:
            detail = e.read().decode("utf-8")[:200]
        except Exception:
            pass
        print(f" Failed to send email to {to_email} via Brevo: {e} {detail}")
        _EMAIL_LAST.update(ok=False, detail=f"Brevo said: {detail or e}")
        return False


def _email_ready():
    """True when any email route is configured: Resend, Brevo, or SMTP login details."""
    return bool(os.environ.get("RESEND_API_KEY") or os.environ.get("BREVO_API_KEY") or (EMAIL_USER and EMAIL_PASS))


def send_reminder_email(to_email, subject, body, from_name=None, reply_to=None, html=None):
    """Send an email. Uses Resend or Brevo over HTTPS when their API key is set, otherwise SMTP (with a timeout).

    from_name replaces the display name (e.g. "Jane Smith via Your Life Your Home") and reply_to sends
    replies to that address. The From address itself always stays MAIL_FROM, so emails stay authenticated.
    """
    if os.environ.get("RESEND_API_KEY"):
        return _send_via_resend(to_email, subject, body, from_name, reply_to, html=html)
    if os.environ.get("BREVO_API_KEY"):
        return _send_via_brevo(to_email, subject, body, from_name, reply_to, html=html)
    if not EMAIL_USER or not EMAIL_PASS:
        print(f"[WARNING] Email not configured - cannot send to {to_email}")
        _EMAIL_LAST.update(ok=False, detail="No email service is set up. Add BREVO_API_KEY and MAIL_FROM in Railway.")
        return False

    msg = MIMEMultipart("alternative") if html else MIMEMultipart()
    msg["From"] = _from_address(from_name)[2] or EMAIL_USER
    msg["To"] = to_email
    msg["Subject"] = subject
    reply = _reply_to_address(reply_to)
    if reply:
        msg["Reply-To"] = reply
    msg.attach(MIMEText(body, "plain"))
    if html:
        msg.attach(MIMEText(html, "html"))
    try:
        with smtplib.SMTP(EMAIL_HOST, EMAIL_PORT, timeout=10) as server:
            server.starttls()
            server.login(EMAIL_USER, EMAIL_PASS)
            server.sendmail(EMAIL_USER, to_email, msg.as_string())
        print(f"[OK] Email sent to {to_email}")
        _EMAIL_LAST.update(ok=True, detail="")
        return True
    except Exception as e:
        _EMAIL_LAST.update(ok=False, detail=f"SMTP failed: {e}")
        print(f" Failed to send email to {to_email}: {e} (if this says timed out or unreachable, your host may block SMTP; set BREVO_API_KEY or RESEND_API_KEY to send over HTTPS)")
        return False


def pro_sender(user_id):
    """Sender details for an email sent on an agent's or lender's behalf.

    Returns kwargs for send_reminder_email: the display name reads "<their name> via Your Life Your Home"
    and replies go to their own email. Returns {} if they can't be found, so the email still sends normally.
    """
    if not user_id:
        return {}
    try:
        conn = get_connection()
        try:
            row = conn.execute(
                "SELECT u.name, u.email, up.full_name FROM users u "
                "LEFT JOIN user_profiles up ON up.user_id = u.id WHERE u.id = ?", (user_id,)).fetchone()
        finally:
            conn.close()
    except Exception as e:
        print(f"[WARNING] pro_sender lookup failed for user {user_id}: {e}")
        return {}
    if not row:
        return {}
    row = dict(row)
    name = _clean_header(row.get("full_name") or row.get("name"))
    out = {}
    if name:
        out["from_name"] = f"{name} via Your Life Your Home"
    if row.get("email"):
        out["reply_to"] = row["email"]
    return out


def send_new_lead_notification(agent_id, homeowner_name, homeowner_email, referral_token=None, signup_timestamp=None):
    """Send email notification to agent when a new lead signs up."""
    if not _email_ready():
        print(f"[WARNING] Email not configured - cannot send lead notification")
        return False
    
    try:
        from database import get_user_by_id, get_user_profile
        
        # Get agent information
        agent_user = get_user_by_id(agent_id)
        if not agent_user:
            print(f"[WARNING] Agent {agent_id} not found - cannot send notification")
            return False
        
        agent_dict = dict(agent_user) if hasattr(agent_user, 'keys') and not isinstance(agent_user, dict) else agent_user
        agent_email = agent_dict.get('email')
        agent_name = agent_dict.get('name', 'Agent')
        
        if not agent_email:
            print(f"[WARNING] Agent {agent_id} has no email - cannot send notification")
            return False
        
        # Get agent profile for additional info
        agent_profile = get_user_profile(agent_id)
        brokerage_name = ""
        if agent_profile:
            profile_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') and not isinstance(agent_profile, dict) else agent_profile
            brokerage_name = profile_dict.get('brokerage_name', '')
        
        # Build email subject and body
        from flask import request
        base_url = request.url_root.rstrip('/') if hasattr(request, 'url_root') else 'https://itsyourlifeyourhome.com'
        
        subject = f"Good news: {homeowner_name} just signed up!"
        
        body = f"""Hi {agent_name.split(' ')[0]},

Good news! {homeowner_name} just signed up through your link and is now in your CRM as a new contact.

Name: {homeowner_name}
Email: {homeowner_email}
Signed up: {signup_timestamp or 'Just now'}
How they found you: {referral_token if referral_token and referral_token != 'default' else 'Your main sign-up link'}

A quick, friendly hello while you are fresh in their mind goes a long way. You can see them here:
{base_url}/agent/crm

Cheering you on,
Your Life, Your Home
"""
        
        # Send the email
        success = send_reminder_email(agent_email, subject, body)
        
        if success:
            print(f"[OK] New lead notification sent to {agent_name} ({agent_email})")
            # Log the email in the database
            try:
                from database import log_automated_email
                # We need the contact_id, but we don't have it here
                # For now, just log that we sent the notification
                print(f"[OK] Lead notification logged for agent {agent_id}")
            except Exception as log_error:
                print(f"[WARNING] Could not log email notification: {log_error}")
        
        return success
        
    except Exception as e:
        import traceback
        print(f" Error sending new lead notification: {e}")
        print(traceback.format_exc())
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

def _already_emailed_today(conn, email_type):
    """Contacts who already got this kind of email in the last 20 hours, so a restart or a rerun never sends twice."""
    try:
        rows = conn.execute(
            "SELECT contact_type, contact_id FROM automated_email_logs WHERE email_type = ? AND status = 'sent' "
            "AND sent_at >= datetime('now', '-20 hours')", (email_type,)).fetchall()
        return {(r[0], r[1]) for r in rows}
    except Exception:
        return set()


def get_birthday_contacts():
    """Get contacts with birthdays today."""
    from datetime import datetime
    from database import get_connection
    today = datetime.now()
    today_str = f"{today.month:02d}/{today.day:02d}"
    today_dash = f"{today.month:02d}-{today.day:02d}"
    
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
          AND (birthday LIKE ? OR birthday LIKE ?)
        """,
        (f"%{today_str}%", f"%-{today_dash}%")
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
          AND (birthday LIKE ? OR birthday LIKE ?)
        """,
        (f"%{today_str}%", f"%-{today_dash}%")
    )
    for row in cur.fetchall():
        contacts.append({
            'id': row['id'],
            'type': 'lender_borrower',
            'professional_id': row['lender_user_id'],
            'name': row['name'],
            'email': row['email']
        })
    
    done = _already_emailed_today(conn, 'birthday')
    conn.close()
    return [c for c in contacts if (c['type'], c['id']) not in done]


def get_anniversary_contacts():
    """Get contacts with home anniversaries today."""
    from datetime import datetime
    from database import get_connection
    today = datetime.now()
    today_str = f"{today.month:02d}/{today.day:02d}"
    today_dash = f"{today.month:02d}-{today.day:02d}"
    
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
          AND (home_anniversary LIKE ? OR home_anniversary LIKE ?)
        """,
        (f"%{today_str}%", f"%-{today_dash}%")
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
          AND (home_anniversary LIKE ? OR home_anniversary LIKE ?)
        """,
        (f"%{today_str}%", f"%-{today_dash}%")
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
    
    done = _already_emailed_today(conn, 'anniversary')
    conn.close()
    return [c for c in contacts if (c['type'], c['id']) not in done]


def _pro_names(professional_id):
    """(full name, first name) of the agent or lender an automated email is sent on behalf of."""
    name = ""
    try:
        from database import get_user_by_id
        row = get_user_by_id(professional_id) if professional_id else None
        name = (dict(row).get("name") or "") if row else ""
    except Exception:
        pass
    return (name or "Your Life, Your Home"), ((name or "").split(" ")[0] or "your friends at Your Life, Your Home")


def _first(name):
    return (name or "").strip().split(" ")[0] or "there"


def send_birthday_emails():
    """Send birthday emails to contacts."""
    if not _email_ready():
        return
    
    contacts = get_birthday_contacts()
    for contact in contacts:
        pro_full, pro_first = _pro_names(contact.get('professional_id'))
        subject = f"Happy birthday, {_first(contact['name'])}!"
        body = f"""Hi {_first(contact['name'])},

Happy birthday! I hope your day is full of people you love and something delicious. I feel lucky to know you.

With warmth,
{pro_full}
"""
        if send_reminder_email(contact['email'], subject, body, **pro_sender(contact.get('professional_id'))):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'birthday', contact['email'], subject, 'sent'
            )


def send_anniversary_emails():
    """Send home anniversary emails."""
    if not _email_ready():
        return
    
    contacts = get_anniversary_contacts()
    for contact in contacts:
        property_info = f" at {contact.get('property_address', 'your home')}" if contact.get('property_address') else ""
        pro_full, pro_first = _pro_names(contact.get('professional_id'))
        subject = f"Happy home anniversary, {_first(contact['name'])}!"
        body = f"""Hi {_first(contact['name'])},

Happy home anniversary{property_info}! I hope your home has been filling your days with good memories. I am so glad I got to be part of your story.

If you ever have a question about your home or what it is worth, I would love to help.

Warmly,
{pro_full}
"""
        if send_reminder_email(contact['email'], subject, body, **pro_sender(contact.get('professional_id'))):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'anniversary', contact['email'], subject, 'sent'
            )


def send_seasonal_checklists():
    """Send seasonal home maintenance checklists."""
    if not _email_ready():
        return
    
    from datetime import datetime
    from database import get_connection
    month = datetime.now().month
    
    # Determine season
    if month in [12, 1, 2]:
        season = "Winter"
        checklist = """Winter Home Maintenance Checklist:
- Check heating system and change filters
- Inspect roof for ice dams
- Seal windows and doors
- Test smoke and carbon monoxide detectors
- Clean gutters and downspouts
- Insulate pipes to prevent freezing
- Check weatherstripping
- Service snow removal equipment"""
    elif month in [3, 4, 5]:
        season = "Spring"
        checklist = """Spring Home Maintenance Checklist:
- Clean gutters and downspouts
- Inspect roof for winter damage
- Service air conditioning system
- Check exterior paint and siding
- Clean windows and screens
- Inspect deck and patio
- Fertilize lawn and garden
- Check irrigation system"""
    elif month in [6, 7, 8]:
        season = "Summer"
        checklist = """Summer Home Maintenance Checklist:
- Service air conditioning
- Check and clean outdoor spaces
- Inspect and clean pool/spa if applicable
- Check for pest issues
- Maintain landscaping
- Inspect exterior for damage
- Check outdoor lighting
- Prepare for storm season"""
    else:  # 9, 10, 11
        season = "Fall"
        checklist = """Fall Home Maintenance Checklist:
- Clean gutters and downspouts
- Inspect roof and chimney
- Service heating system
- Seal windows and doors
- Check insulation
- Winterize outdoor plumbing
- Rake leaves and maintain yard
- Test smoke detectors"""
    
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
        pro_full, pro_first = _pro_names(contact.get('professional_id'))
        subject = f"Your {season.lower()} home care list"
        body = f"""Hi {_first(contact['name'])},

I put together a few things to help you care for your home this {season.lower()}. There is no need to do it all, just pick what feels helpful:

{checklist}

I am thinking of you and your home. Reach out anytime if I can help with anything.

Warmly,
{pro_full}
"""
        if send_reminder_email(contact['email'], subject, body, **pro_sender(contact.get('professional_id'))):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'seasonal', contact['email'], subject, 'sent'
            )


def send_equity_updates():
    """Send equity update emails based on frequency."""
    if not _email_ready():
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
        pro_full, pro_first = _pro_names(contact.get('professional_id'))
        subject = f"Your home equity update for {today.strftime('%B %Y')}"
        body = f"""Hi {_first(contact['name'])},

Here is a quick look at where your home stands this month:

Home: {contact.get('property_address', 'Your home')}
Estimated value: ${property_val:,.0f}
Estimated equity: ${equity:,.0f}

These are estimates, but they are a nice reminder of how much you have built. I am proud of you. If you would like to talk it through, I am just a call or message away.

Warmly,
{pro_full}
"""
        if send_reminder_email(contact['email'], subject, body, **pro_sender(contact.get('professional_id'))):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'equity', contact['email'], subject, 'sent'
            )


def send_holiday_greetings():
    """Send holiday greeting emails."""
    if not _email_ready():
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
        pro_full, pro_first = _pro_names(contact.get('professional_id'))
        subject = f"{holiday}, {_first(contact['name'])}!"
        body = f"""Hi {_first(contact['name'])},

{holiday}! I am wishing you and your family a warm and wonderful celebration. Thank you for letting me be part of your journey.

Warmly,
{pro_full}
"""
        if send_reminder_email(contact['email'], subject, body, **pro_sender(contact.get('professional_id'))):
            log_automated_email(
                contact['id'], contact['type'], contact['professional_id'],
                'holiday', contact['email'], subject, 'sent'
            )


def _value_rise_emails(user_id, property_id, old, new, pct):
    """Good news for the homeowner, and a friendly nudge for their agent: a real estimate just rose."""
    try:
        from database import get_user_by_id, get_homeowner_professionals
        home = get_user_by_id(user_id)
        home = dict(home) if home else {}
        conn = get_connection()
        addr = (conn.execute("SELECT address FROM properties WHERE id = ?", (property_id,)).fetchone() or {"address": "your home"})["address"]
        conn.close()
        base = os.environ.get("YLH_SITE_URL", "https://itsyourlifeyourhome.com")
        agent = next((p for p in get_homeowner_professionals(user_id) if p.get("professional_role") == "agent"), None)
        agent_id = ((agent.get("professional_id") or agent.get("user_id")) if agent else None) or home.get("agent_id")
        agent_row = dict(get_user_by_id(agent_id)) if agent_id and get_user_by_id(agent_id) else {}
        first = (home.get("name") or "there").split(" ")[0]
        if home.get("email"):
            body = (f"Hi {first},\n\nGood news about your home. The latest market estimate for {addr} is ${new:,.0f}, "
                    f"up {pct:.1f}% from ${old:,.0f}.\n\nSee your value, equity and what-ifs here: {base}/homeowner\n\n"
                    f"This is an automated estimate, not an appraisal. "
                    + (f"If you'd like to talk about what it means for you, {agent_row.get('name')} would be glad to help." if agent_row.get("name") else "")
                    + "\n\nWarmly,\nYour Life, Your Home")
            send_reminder_email(home["email"], f"Your home's value is up {pct:.0f}%", body, **pro_sender(agent_id))
        import client_values
        if agent_row.get("email") and client_values.is_on(agent_id):
            body = (f"Hi {(agent_row.get('name') or 'there').split(' ')[0]},\n\n{home.get('name') or 'A client'}'s home at {addr} "
                    f"is now estimated at ${new:,.0f}, up {pct:.1f}% from ${old:,.0f}.\n\n"
                    f"That is a natural reason to reach out: see how they are feeling about their home and their plans. "
                    f"Their details are in your Client Portal: {base}/agent/clients\n\nYour Life, Your Home")
            send_reminder_email(agent_row["email"], f"{home.get('name') or 'A client'}'s home value is up {pct:.0f}%", body)
    except Exception:
        print("[VALUES] value-rise email failed")


def _register_value_alerts():
    import valuation
    valuation.set_change_handler(lambda *a: _bg(_value_rise_emails, *a))


_register_value_alerts()


def update_home_values_daily():
    """Nightly home value refresh from real market data (RentCast). Never invents or simulates values."""
    import valuation
    if not valuation.provider_configured():
        print("[VALUES] No value provider configured (set RENTCAST_API_KEY); values are left as they are.")
        return
    valuation.refresh_stale_values()


def schedule_new_lead_drip(agent_user_id: int, contact_id: int, contact_email: str):
    """
    Schedule a 4-step follow-up drip when a new lead enters the CRM.
    Steps: Day 1, Day 3, Day 7, Day 14.
    """
    if not contact_email:
        return
    from database import get_connection
    from datetime import timedelta
    today = datetime.now().date()
    steps = [
        (1,  "Following up on your home search"),
        (3,  "Just checking in"),
        (7,  "Still thinking about buying or selling?"),
        (14, "Touching base"),
    ]
    conn = get_connection()
    cur = conn.cursor()
    for day_offset, subject in steps:
        scheduled = (today + timedelta(days=day_offset)).isoformat()
        cur.execute("""
            INSERT INTO crm_drip_sequences
                (agent_user_id, contact_id, sequence_name, step_number, scheduled_date, status)
            VALUES (?, ?, 'new_lead', ?, ?, 'pending')
        """, (agent_user_id, contact_id, day_offset, scheduled))
    conn.commit()
    conn.close()


def send_drip_emails():
    """Send any pending drip sequence emails that are due today."""
    from database import get_connection
    from datetime import date
    today = date.today().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT ds.id, ds.agent_user_id, ds.contact_id, ds.step_number, ds.scheduled_date,
               ac.name as contact_name, ac.email as contact_email,
               u.email as agent_email,
               up.full_name as agent_name, up.phone as agent_phone
        FROM crm_drip_sequences ds
        JOIN agent_contacts ac ON ac.id = ds.contact_id
        JOIN users u ON u.id = ds.agent_user_id
        LEFT JOIN user_profiles up ON up.user_id = ds.agent_user_id
        WHERE ds.status = 'pending'
          AND ds.scheduled_date <= ?
          AND ac.email IS NOT NULL AND ac.email != ''
    """, (today,))
    rows = cur.fetchall()
    conn.close()
    for row in rows:
        row = dict(row)
        step = row["step_number"]
        contact_name = (row.get("contact_name") or "there").split()[0]
        agent_name = row.get("agent_name") or "Your agent"
        agent_email = row.get("agent_email") or ""
        agent_phone = row.get("agent_phone") or ""
        # Subject lines per step
        subjects = {
            1:  f"Great to connect with you, {contact_name}",
            3:  f"Checking in, {contact_name}",
            7:  f"Still here to help, {contact_name}",
            14: f"Thinking of you, {contact_name}",
        }
        bodies = {
            1: (f"Hi {contact_name},\n\nJust wanted to reach out and say it was great to connect with you. "
                f"I am here whenever you are ready to talk about buying or selling. "
                f"Feel free to reach me at {agent_phone or agent_email} anytime.\n\nWarm regards,\n{agent_name}"),
            3: (f"Hi {contact_name},\n\nJust checking in to see if you have any questions or if there is "
                f"anything I can help you with. No pressure at all, I just want to make sure you have "
                f"everything you need.\n\nWarm regards,\n{agent_name}"),
            7: (f"Hi {contact_name},\n\nI know life gets busy, so I just wanted to pop back in and let you "
                f"know I am still here for you whenever the timing is right. Whether it is a question about "
                f"the market or you are ready to take the next step, I am just a call or text away.\n\n"
                f"Warm regards,\n{agent_name}\n{agent_phone}"),
            14: (f"Hi {contact_name},\n\nI wanted to touch base one more time. Real estate decisions are "
                 f"big ones, and I never want to rush you. If you are still exploring your options or have "
                 f"questions, I am happy to chat, with zero pressure.\n\n"
                 f"Warm regards,\n{agent_name}\n{agent_phone or agent_email}"),
        }
        subject = subjects.get(step, f"Thinking of you, {contact_name}")
        body = bodies.get(step, f"Hi {contact_name},\n\nJust wanted to check in.\n\n{agent_name}")
        try:
            send_reminder_email(row["contact_email"], subject, body, **pro_sender(row.get("agent_user_id")))
            # Mark as sent
            conn2 = get_connection()
            cur2 = conn2.cursor()
            cur2.execute("""
                UPDATE crm_drip_sequences
                SET status = 'sent', sent_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (row["id"],))
            conn2.commit()
            conn2.close()
            print(f"[DRIP] Sent step {step} to {row['contact_email']}")
        except Exception as e:
            print(f"[DRIP] Error sending to {row.get('contact_email')}: {e}")


def schedule_review_request(agent_user_id: int, transaction_id: int,
                             client_name: str, client_email: str):
    """Schedule a Google review request 3 days after closing."""
    if not client_email:
        return
    from database import get_connection
    from datetime import timedelta
    send_date = (datetime.now().date() + timedelta(days=3)).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO review_requests
            (agent_user_id, transaction_id, client_email, client_name, scheduled_date, status)
        VALUES (?, ?, ?, ?, ?, 'pending')
    """, (agent_user_id, transaction_id, client_email, client_name, send_date))
    conn.commit()
    conn.close()


def send_review_requests():
    """Send any pending review request emails that are due today."""
    from database import get_connection
    from datetime import date
    today = date.today().isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT rr.id, rr.agent_user_id, rr.client_email, rr.client_name,
               up.full_name as agent_name, up.phone as agent_phone,
               up.google_review_link
        FROM review_requests rr
        LEFT JOIN user_profiles up ON up.user_id = rr.agent_user_id
        WHERE rr.status = 'pending' AND rr.scheduled_date <= ?
    """, (today,))
    rows = cur.fetchall()
    conn.close()
    for row in rows:
        row = dict(row)
        client_first = (row.get("client_name") or "there").split()[0]
        agent_name = row.get("agent_name") or "your agent"
        review_link = row.get("google_review_link") or ""
        review_cta = (f"\n\nIf you have a moment, I would be so grateful if you left me a review:\n{review_link}\n"
                      if review_link else "\n\nIf you have a moment, a review or a referral means the world to me.\n")
        subject = f"It was a pleasure working with you, {client_first}!"
        body = (f"Hi {client_first},\n\n"
                f"Congratulations again on your closing! It was truly a pleasure working with you, "
                f"and I hope you are settling in and loving your new home.\n"
                f"{review_cta}"
                f"And please remember that I am always here for you, your family, and anyone you know "
                f"who is thinking about buying or selling. I love referrals!\n\n"
                f"Warmly,\n{agent_name}")
        try:
            send_reminder_email(row["client_email"], subject, body, **pro_sender(row.get("agent_user_id")))
            conn2 = get_connection()
            cur2 = conn2.cursor()
            cur2.execute("""
                UPDATE review_requests SET status = 'sent', sent_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (row["id"],))
            conn2.commit()
            conn2.close()
            print(f"[REVIEW] Sent review request to {row['client_email']}")
        except Exception as e:
            print(f"[REVIEW] Error sending to {row.get('client_email')}: {e}")


# ---------------- EMAIL VERIFICATION ----------------
def _verify_serializer():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(app.secret_key, salt="ylh-verify-email")


def _mark_email_verified(user_id):
    try:
        conn = get_connection()
        conn.execute("UPDATE users SET email_verified=1 WHERE id=?", (int(user_id),))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[VERIFY] could not mark verified: {e}")


def _send_verification_email(user_id, email, background=False):
    """Email a 3-day confirmation link. Never raises; signup must not fail on email trouble.
    The link is built here (needs the request); with background=True only the slow sending is deferred."""
    try:
        token = _verify_serializer().dumps({"uid": int(user_id), "email": email.lower()})
        link = url_for("verify_email", token=token, _external=True)
        sender = (lambda *a: _bg(send_reminder_email, *a)) if background else send_reminder_email
        return sender(
            email,
            "Welcome! Please confirm your email",
            "Welcome to Your Life, Your Home. We are so glad you are here!\n\n"
            "Please confirm your email address by opening this link:\n\n"
            f"{link}\n\nThe link works for 3 days. If you did not sign up, you can safely ignore this message and nothing will change.\n\n"
            "Warmly,\nYour Life, Your Home",
        )
    except Exception as e:
        print(f"[VERIFY] send failed: {e}")
        return False


@app.route("/verify-email/<token>")
def verify_email(token):
    from itsdangerous import BadSignature, SignatureExpired
    from database import get_user_by_id
    try:
        data = _verify_serializer().loads(token, max_age=3 * 24 * 3600)
        row = get_user_by_id(data["uid"])
        if not row or str(row["email"]).lower() != data.get("email"):
            raise BadSignature("mismatch")
    except (SignatureExpired, BadSignature, KeyError, TypeError):
        flash("That confirmation link has expired or is not quite right. Sign in and we will send you a new one.", "error")
        return redirect(url_for("login"))
    _mark_email_verified(data["uid"])
    flash("Thanks! Your email is confirmed.", "success")
    return redirect(url_for("index") if session.get("user_id") else url_for("login"))


@app.route("/resend-verification", methods=["POST"])
def resend_verification():
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login"))
    row = get_connection().execute("SELECT email, email_verified FROM users WHERE id=?", (uid,)).fetchone()
    if row and not row["email_verified"]:
        if _send_verification_email(uid, row["email"]):
            flash("Confirmation email sent. Check your inbox.", "success")
        else:
            flash("We could not send that email just now. Please try again in a little while.", "error")
    return redirect(request.referrer or url_for("index"))


@app.context_processor
def _inject_is_site_admin():
    """Lets the menu show a 'Site Admin' link to the owner/admins only."""
    uid = session.get("user_id")
    if not uid or session.get("role") not in ("agent", "admin"):
        return {"is_site_admin": False}
    try:
        from rbac import is_site_admin
        return {"is_site_admin": bool(is_site_admin(uid))}
    except Exception:
        return {"is_site_admin": False}


@app.context_processor
def _inject_unverified():
    uid = session.get("user_id")
    if not uid:
        return {"email_unverified": False}
    try:
        conn = get_connection()
        row = conn.execute("SELECT email_verified FROM users WHERE id=?", (uid,)).fetchone()
        conn.close()
        return {"email_unverified": bool(row) and not row["email_verified"]}
    except Exception:
        return {"email_unverified": False}


# ── CONNECTIVE AUTOMATION HELPERS ──────────────────────────────────────────
def _bg(fn, *args, **kwargs):
    """Run slow work (email) off the request thread; run inline under tests."""
    if app.config.get("TESTING"):
        return fn(*args, **kwargs)
    import threading
    threading.Thread(target=fn, args=args, kwargs=kwargs, daemon=True).start()


def _site_url():
    try:
        return request.url_root.rstrip("/")
    except RuntimeError:
        return os.environ.get("YLH_SITE_URL", "https://itsyourlifeyourhome.com")


# ── ONBOARDING CHECKLIST ───────────────────────────────────────────────────
def _count(conn, sql, args):
    try:
        return conn.execute(sql, args).fetchone()[0]
    except Exception:
        return 0


@app.context_processor
def _inject_onboarding():
    def onboarding_checklist():
        """Return {'steps': [...], 'done': n} for the signed-in user, or None when hidden/finished."""
        uid, role = session.get("user_id"), session.get("role")
        if not uid or role not in ("agent", "lender", "homeowner"):
            return None
        conn = get_connection()
        try:
            if _count(conn, "SELECT onboarding_dismissed FROM users WHERE id=?", (uid,)):
                return None
            if role == "agent":
                spec = [
                    ("Add your photo and contact info", "agent_settings_profile",
                     "SELECT COUNT(*) FROM user_profiles WHERE user_id=? AND professional_photo IS NOT NULL AND professional_photo<>''"),
                    ("Add your first client to the CRM", "agent_crm", "SELECT COUNT(*) FROM agent_contacts WHERE agent_user_id=?"),
                    ("Start a transaction", "agent_transactions", "SELECT COUNT(*) FROM transactions WHERE agent_id=?"),
                    ("Add a trusted vendor", "agent_vendors", "SELECT COUNT(*) FROM trusted_vendors WHERE agent_id=?"),
                ]
            elif role == "lender":
                spec = [
                    ("Add your photo and contact info", "lender_settings_profile",
                     "SELECT COUNT(*) FROM user_profiles WHERE user_id=? AND professional_photo IS NOT NULL AND professional_photo<>''"),
                    ("Add your first borrower", "lender_crm", "SELECT COUNT(*) FROM lender_borrowers WHERE lender_user_id=?"),
                    ("Add a loan", "lender_loans", "SELECT COUNT(*) FROM lender_borrowers WHERE lender_user_id=? AND COALESCE(loan_stage, '') <> ''"),
                ]
            else:
                spec = [
                    ("Add your home", "homeowner_value_equity_overview", "SELECT COUNT(*) FROM properties WHERE user_id=?"),
                    ("Upload an important document", "homeowner_upload_documents", "SELECT COUNT(*) FROM homeowner_documents WHERE user_id=?"),
                    ("Log a home project or repair", "homeowner_home_timeline", "SELECT COUNT(*) FROM homeowner_timeline_events WHERE user_id=?"),
                    ("Track a warranty or appliance", "homeowner_care_warranty_log", "SELECT COUNT(*) FROM homeowner_warranty_log WHERE user_id=?"),
                ]
            steps = [{"label": l, "url": url_for(ep), "done": bool(_count(conn, q, (uid,)))} for l, ep, q in spec]
        finally:
            conn.close()
        done = sum(1 for s in steps if s["done"])
        if done == len(steps):
            return None
        return {"steps": steps, "done": done}
    return {"onboarding_checklist": onboarding_checklist}


@app.route("/digest/unsubscribe/<token>")
def digest_unsubscribe(token):
    import automation
    uid = automation.digest_unsubscribe_uid(token)
    if uid:
        conn = get_connection()
        conn.execute("UPDATE users SET digest_enabled = 0 WHERE id = ?", (uid,))
        conn.commit()
        conn.close()
        flash("You're unsubscribed from the daily summary email.", "success")
    else:
        flash("That link isn't valid.", "error")
    return redirect(url_for("index"))


@app.route("/onboarding/dismiss", methods=["POST"])
def onboarding_dismiss():
    uid = session.get("user_id")
    if uid:
        conn = get_connection()
        conn.execute("UPDATE users SET onboarding_dismissed=1 WHERE id=?", (uid,))
        conn.commit()
        conn.close()
    return redirect(request.referrer or url_for("index"))


def backup_database(keep=7):
    """Write a consistent snapshot of the SQLite DB next to it (backups/), keeping the newest `keep`."""
    import sqlite3
    from datetime import datetime as _dt
    from database import DB_PATH
    bdir = Path(DB_PATH).parent / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    dest = bdir / f"ylh-{_dt.now().strftime('%Y%m%d-%H%M%S')}.db"
    src = sqlite3.connect(DB_PATH, timeout=30)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    for old in sorted(bdir.glob("ylh-*.db"))[:-keep]:
        try:
            old.unlink()
        except OSError:
            pass
    print(f"[BACKUP] Saved {dest.name}")
    return dest


def start_scheduler():
    """Start background scheduler safely without blocking app startup."""
    try:
        # Run on Central time so "9 AM" emails land at 9 AM for clients, not 3 AM. One run at a time per job.
        scheduler = BackgroundScheduler(timezone=os.environ.get("YLH_TIMEZONE", "America/Chicago"),
                                        job_defaults={"coalesce": True, "max_instances": 1, "misfire_grace_time": 1800})
        scheduler.add_job(send_due_reminders, "cron", hour=12, minute=0)
        # CRM automated emails
        scheduler.add_job(send_birthday_emails, "cron", hour=9, minute=0)  # 9 AM daily
        scheduler.add_job(send_anniversary_emails, "cron", hour=9, minute=5)  # 9:05 AM daily
        scheduler.add_job(send_seasonal_checklists, "cron", day=1, hour=10, minute=0)  # 1st of month, 10 AM
        scheduler.add_job(send_equity_updates, "cron", day=1, hour=10, minute=5)  # 1st of month, 10:05 AM
        scheduler.add_job(send_holiday_greetings, "cron", hour=9, minute=10)  # 9:10 AM daily
        # Drip sequences and review requests
        scheduler.add_job(send_drip_emails, "cron", hour=9, minute=20)  # 9:20 AM daily
        scheduler.add_job(send_review_requests, "cron", hour=9, minute=25)  # 9:25 AM daily
        # Nightly home value refresh from real market data
        scheduler.add_job(update_home_values_daily, "cron", hour=2, minute=0)  # 2 AM daily
        scheduler.add_job(lambda: send_contest_invites_scheduled(), "cron", hour=9, minute=30)  # 9:30 AM daily, bracket contest invites
        scheduler.add_job(lambda: __import__("pies").send_reminders(), "cron", hour=17, minute=0)
        scheduler.add_job(lambda: __import__("booking").send_reminders(), "cron", hour=17, minute=10)  # day-before booking reminders
        scheduler.add_job(lambda: __import__("tc").send_deadline_reminders(), "cron", hour=9, minute=0)  # 9 AM Central deadline heads-ups  # day-before pie pickup reminders
        scheduler.add_job(lambda: __import__("pies").send_thank_yous(), "cron", hour=10, minute=15)  # pie thank-you emails on their chosen date
        scheduler.add_job(backup_database, "cron", hour=3, minute=0)  # 3 AM daily DB snapshot
        scheduler.add_job(
            lambda: __import__("automation").send_daily_digests(send_reminder_email, os.environ.get("YLH_SITE_URL", "https://itsyourlifeyourhome.com")),
            "cron", hour=7, minute=30)  # 7:30 AM daily pro digest
        scheduler.start()
        print("[OK] Reminder scheduler started with CRM automation and daily value updates.")
    except Exception as e:
        print(f"[WARNING] Scheduler could not start (non-critical): {e}")


_scheduler_lock_fh = None


def _acquire_scheduler_lock():
    """With several gunicorn workers, let exactly one run the daily jobs (no double emails)."""
    global _scheduler_lock_fh
    try:
        import fcntl, tempfile
        _scheduler_lock_fh = open(os.path.join(tempfile.gettempdir(), "ylh_scheduler.lock"), "w")
        fcntl.flock(_scheduler_lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except ImportError:
        return True  # Windows/dev: single process
    except OSError:
        return False  # another worker already owns the scheduler


def _apply_emergency_password():
    """Locked out and email isn't working? Set YLH_RESET_EMAIL and YLH_RESET_PASSWORD in the host's
    variables, redeploy, sign in, then DELETE both variables. Only an existing account is changed."""
    email = (os.environ.get("YLH_RESET_EMAIL") or "").strip().lower()
    new_pw = os.environ.get("YLH_RESET_PASSWORD") or ""
    if not email or not new_pw:
        return
    try:
        if len(new_pw) < 8:
            print("[ADMIN] YLH_RESET_PASSWORD is shorter than 8 characters; ignored.")
            return
        from database import get_user_by_email, update_user_password
        row = get_user_by_email(email)
        if not row:
            print(f"[ADMIN] YLH_RESET_EMAIL: no account found for {email}; nothing changed.")
            return
        user = dict(row)
        update_user_password(user["id"], generate_password_hash(new_pw))
        print(f"[ADMIN] Password set for {email}. Sign in, then DELETE YLH_RESET_EMAIL and YLH_RESET_PASSWORD.")
    except Exception as e:
        print(f"[ADMIN] Emergency password reset failed: {e}")


_apply_emergency_password()

# Start scheduler when app starts (non-blocking)
try:
    if _acquire_scheduler_lock():
        start_scheduler()
    else:
        print("[Scheduler] Another worker is running scheduled jobs; skipping here.")
except Exception as e:
    print(f"[WARNING] Scheduler initialization failed (non-critical): {e}")


# -------------------------------------------------
# SHARED UTILS
# -------------------------------------------------


# -------------------------------------------------
# HOMEOWNER SNAPSHOT + CRM METRICS
# -------------------------------------------------
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
            # aliases used by ai_dashboard_briefing
            "active": 0,
            "needs_followup": 0,
            "pending_tasks": 0,
        }
    from datetime import date as _date
    transactions = get_agent_transactions(user_id)
    today_str = _date.today().isoformat()
    # Counted in the database, so the dashboard opens just as fast with 5,000 contacts as with 50.
    _c = get_connection()
    try:
        new_leads = _c.execute("SELECT COUNT(*) FROM agent_contacts WHERE agent_user_id = ? AND stage = 'new'", (user_id,)).fetchone()[0]
        followups = _c.execute(
            """SELECT COUNT(*) FROM agent_contacts
               WHERE agent_user_id = ? AND LOWER(COALESCE(stage, '')) NOT IN ('closed', 'hold', 'past')
                 AND ((COALESCE(next_action_date, '') != '' AND next_action_date <= ?)
                      OR (COALESCE(next_action_date, '') = '' AND COALESCE(last_touch, '') = ''))""",
            (user_id, today_str)).fetchone()[0]
    finally:
        _c.close()
    active_tx = len(transactions) if transactions else 0

    return {
        "new_leads":          new_leads,
        "active_transactions": active_tx,
        "followups_today":    followups,
        # aliases so ai_dashboard_briefing gets real numbers
        "active":             active_tx,
        "needs_followup":     followups,
        "pending_tasks":      followups,
    }


def get_lender_dashboard_metrics(user_id):
    if not user_id:
        return {
            "new_applications": 0,
            "loans_in_process": 0,
            "nurture_contacts": 0,
        }
    loans = list_lender_loans(user_id)
    _c = get_connection()
    try:
        total = _c.execute("SELECT COUNT(*) FROM lender_borrowers WHERE lender_user_id = ?", (user_id,)).fetchone()[0]
        preapproved = _c.execute("SELECT COUNT(*) FROM lender_borrowers WHERE lender_user_id = ? AND status = 'preapproval'", (user_id,)).fetchone()[0]
    finally:
        _c.close()
    return {
        "new_applications": preapproved,
        "loans_in_process": len(loans) if loans else 0,
        "nurture_contacts": max(total // 2, 0),
    }


# -------------------------------------------------
# MAIN / AUTH
# -------------------------------------------------
@app.route("/r/<referral_code>")
def referral_landing(referral_code):
    """
    Public landing page for agent/lender referral links (legacy support).
    Redirects to new signup flow with ref token.
    """
    # A signed-in homeowner who opens someone's link is asked first; nothing changes until they say yes.
    _u = get_current_user()
    if _u and _u.get("role") == "homeowner":
        return redirect(url_for("connect_with_professional", token=referral_code))
    if _u:
        flash("This invite link is for homeowners. Share it with your clients so they connect with you.", "info")
        return redirect(url_for("agent_dashboard") if _u.get("role") == "agent" else url_for("lender_dashboard"))
    return redirect(url_for("signup", role="homeowner", ref=referral_code))


@app.route("/connect/<token>", methods=["GET", "POST"])
def connect_with_professional(token):
    """A homeowner chooses whether to connect with the agent or lender behind an invite link.
    A homeowner has at most one agent and one lender, and only changes it by confirming here."""
    user = get_current_user()
    if not user or user.get("role") != "homeowner":
        session["pending_connect"] = token
        flash("Please sign in to connect with this professional.", "info")
        return redirect(url_for("login", role="homeowner"))
    from database import (get_referral_link_by_token, get_user_by_id, get_user_profile,
                          get_active_professional_id, connect_homeowner_to_professional)
    link = get_referral_link_by_token(token)
    if not link:
        flash("That invite link is no longer active. Please ask for their current link.", "error")
        return redirect(url_for("homeowner_overview"))
    link = dict(link)
    pro_id = link.get("agent_id") or link.get("lender_id")
    role = "agent" if link.get("agent_id") else "lender"
    pro = get_user_by_id(pro_id)
    if not pro:
        return redirect(url_for("homeowner_overview"))
    pro = dict(pro)
    prof = get_user_profile(pro_id) or {}
    prof = dict(prof) if not isinstance(prof, dict) else prof
    cur_id = get_active_professional_id(user["id"], role)
    cur_row = get_user_by_id(cur_id) if cur_id and cur_id != pro_id else None
    cur_pro = dict(cur_row) if cur_row else None
    if request.method == "POST":
        if request.form.get("choice") != "yes":
            flash("No problem. Nothing was changed.", "info")
            return redirect(url_for("homeowner_overview"))
        result = connect_homeowner_to_professional(user["id"], pro_id, role, referral_code=token, replace=True)
        if result == "connected":
            try:
                if role == "agent":
                    from database import add_agent_contact, list_agent_contacts
                    have = any((dict(c).get("email") or "").lower() == (user.get("email") or "").lower() for c in list_agent_contacts(pro_id))
                    if not have:
                        add_agent_contact(agent_user_id=pro_id, name=user.get("name") or "", email=user.get("email") or "", phone="",
                                          stage="new", best_contact=user.get("email") or "", last_touch="", birthday="",
                                          home_anniversary="", address="", notes="Chose to connect via invite link",
                                          tags="referral", property_address="", property_value=None, equity_estimate=None,
                                          user_id=user["id"])
                else:
                    from database import add_lender_borrower, list_lender_borrowers
                    have = any((dict(c).get("email") or "").lower() == (user.get("email") or "").lower() for c in list_lender_borrowers(pro_id))
                    if not have:
                        add_lender_borrower(lender_user_id=pro_id, name=user.get("name") or "", email=user.get("email") or "",
                                            status="prospect", notes="Chose to connect via invite link", tags="referral",
                                            user_id=user["id"])
            except Exception as exc:
                print(f"connect: CRM add skipped: {exc}")
        session.pop("pending_connect", None)
        flash(f"You are now connected with {pro.get('name') or 'your professional'}.", "success")
        return redirect(url_for("homeowner_overview"))
    return render_template("homeowner/connect.html", brand_name=FRONT_BRAND_NAME, pro=pro, prof=prof, role=role,
                           cur_pro=cur_pro, token=token, already=(cur_id == pro_id))


def _hero_photos():
    """Landing-page hero images: static/img/hero-1.jpg, hero-2.jpg, ... (any of jpg/jpeg/webp/png).
    A single legacy hero-home.* file still works. Drop in or remove files to change the slideshow."""
    img_dir = BASE_DIR / "static" / "img"
    found = []
    for n in range(1, 11):
        for e in ("jpg", "jpeg", "webp", "png"):
            if (img_dir / f"hero-{n}.{e}").exists():
                found.append(f"img/hero-{n}.{e}")
                break
    if not found:
        for e in ("jpg", "jpeg", "webp", "png"):
            if (img_dir / f"hero-home.{e}").exists():
                found.append(f"img/hero-home.{e}")
                break
    return found


@app.route("/")
def index():
    """
    Landing page with three paths:
    - Homeowner dashboard
    - Agent dashboard
    - Lender dashboard
    
    Tracks default agent assignment for visitors without referral tokens.
    """
    # Track default agent assignment for anonymous visitors
    referral_token = request.args.get("ref")
    if not referral_token and not session.get("user_id"):
        from database import get_or_create_default_agent
        default_agent_id = get_or_create_default_agent()
        session["default_agent_id"] = default_agent_id
        session["referral_token"] = None  # Mark as default assignment
    
    return render_template(
        "main/index.html",
        brand_name=FRONT_BRAND_NAME,
        cloud_cma_url=CLOUD_CMA_URL,
        hero_photos=_hero_photos(),
    )


@app.route("/robots.txt")
def robots_txt():
    body = chr(10).join([
        "User-agent: *",
        "Allow: /",
        "Disallow: /admin",
        "Disallow: /agent/",
        "Disallow: /lender/",
        "Disallow: /homeowner",
        "Disallow: /api/",
        "Disallow: /debug/",
        f"Sitemap: {request.url_root}sitemap.xml",
        "",
    ])
    return Response(body, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    urls = [url_for("index", _external=True), url_for("login", _external=True), url_for("signup", _external=True)]
    xml = '<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    xml += "".join(f"<url><loc>{u}</loc></url>" for u in urls) + "</urlset>"
    return Response(xml, mimetype="application/xml")


@app.errorhandler(404)
def _not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return render_template("errors/404.html"), 404


@app.errorhandler(401)
def _unauthorized(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Please sign in"}), 401
    flash("Please sign in to continue.", "warning")
    return redirect(url_for("login"))


@app.errorhandler(500)
def _server_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Server error"}), 500
    return render_template("errors/500.html"), 500


def _inviter_for_token(token):
    """Who sent this invite link? Used to greet new homeowners with their agent/lender's name,
    photo and brokerage. Returns None for missing/invalid/default tokens."""
    if not token or token == "default":
        return None
    try:
        from database import get_referral_link_by_token, get_user_by_id, get_user_profile
        link = get_referral_link_by_token(token)
        if not link:
            return None
        pro_id = link.get("agent_id") or link.get("lender_id")
        role = "agent" if link.get("agent_id") else "lender"
        user = get_user_by_id(pro_id) if pro_id else None
        if not user:
            return None
        user = dict(user)
        prof = get_user_profile(pro_id) or {}
        prof = dict(prof) if not isinstance(prof, dict) else prof
        bio = (prof.get("bio") or "").strip()
        if len(bio) > 160:
            bio = bio[:157].rsplit(" ", 1)[0] + "…"
        return {
            "name": user.get("name") or "",
            "first_name": (user.get("name") or "").split(" ")[0],
            "role": role,
            "brokerage": prof.get("brokerage_name") or prof.get("team_name") or "",
            "photo": prof.get("professional_photo") or "",
            "bio": bio,
            "hero": prof.get("hero_image") or "",
        }
    except Exception as exc:  # never break signup over a greeting
        print(f"inviter lookup failed: {exc}")
        return None


@app.route("/signup", methods=["GET", "POST"])
def signup():
    """
    Sign up for any role: homeowner | agent | lender
    For homeowners: Uses referral token if provided, otherwise assigns to default agent (Kayleigh Biggs)
    For agents/lenders: No referral token required
    """
    role = request.args.get("role", "homeowner")
    if role not in ("homeowner", "agent", "lender"):
        role = "homeowner"
    
    # Get referral token from query parameter or session
    referral_token = request.args.get("ref") or request.form.get("ref_token") or session.get("referral_token")
    
    # For homeowners without referral token, use default agent (no error, just assign)
    if role == "homeowner" and not referral_token:
        from database import get_or_create_default_agent
        default_agent_id = get_or_create_default_agent()
        # Store in session for tracking
        if not session.get("default_agent_id"):
            session["default_agent_id"] = default_agent_id
        session["referral_token"] = None  # Mark as default assignment

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role_from_form = request.form.get("role", "").strip()
        referral_token_from_form = request.form.get("ref_token") or referral_token

        # Determine role: prioritize form value, then URL parameter, default to homeowner
        if role_from_form in ("agent", "lender", "homeowner"):
            role = role_from_form
        elif role in ("agent", "lender", "homeowner"):
            role = role  # Use URL parameter
        else:
            role = "homeowner"  # Default fallback

        # Validate required fields
        if not name:
            flash("What should we call you? Please add your full name.", "error")
            return redirect(url_for("signup", role=role, ref=referral_token_from_form))
        
        if not email:
            flash("We will need your email address to set up your account.", "error")
            return redirect(url_for("signup", role=role, ref=referral_token_from_form))
        
        if not password:
            flash("Please choose a password to keep your account safe.", "error")
            return redirect(url_for("signup", role=role, ref=referral_token_from_form))
        
        if len(password) < 8:
            flash("Your password needs at least 8 characters. A little longer is even better.", "error")
            return redirect(url_for("signup", role=role, ref=referral_token_from_form))

        password_hash = generate_password_hash(password)
        
        # For homeowners, validate referral token and get agent_id/lender_id
        agent_id = None
        lender_id = None
        
        if role == "homeowner":
            from database import get_referral_link_by_token, get_or_create_default_agent
            
            # If no referral token, use default agent (from session if available, otherwise create/get)
            if not referral_token_from_form:
                agent_id = session.get("default_agent_id") or get_or_create_default_agent()
                if not session.get("default_agent_id"):
                    session["default_agent_id"] = agent_id
                referral_token_from_form = "default"  # Mark as default assignment
            else:
                referral_link = get_referral_link_by_token(referral_token_from_form)
                
                if not referral_link:
                    # An invite link that is no longer active must never quietly connect the client to
                    # someone else. Ask them to get a fresh link from their own agent or lender.
                    flash("That invite link is no longer active. Please ask your agent or lender for their current link, "
                          "so you are connected to the right person.", "error")
                    return redirect(url_for("signup", role="homeowner"))
                else:
                    # Extract agent_id and lender_id from referral link
                    # Convert Row to dict if needed
                    if hasattr(referral_link, 'keys') and not isinstance(referral_link, dict):
                        referral_link = dict(referral_link)
                    
                    agent_id = referral_link.get("agent_id") if referral_link.get("agent_id") else None
                    lender_id = referral_link.get("lender_id") if referral_link.get("lender_id") else None
                    
                    print(f"SIGNUP: Referral link found - agent_id: {agent_id}, lender_id: {lender_id}")
                    
                    # If referral link has no agent or lender, use default agent
                    if not agent_id and not lender_id:
                        agent_id = get_or_create_default_agent()
                        referral_token_from_form = "default"
                        print(f"SIGNUP: No agent/lender in referral link, using default agent {agent_id}")

        kept_existing = False
        # Debug: Print signup attempt
        print(f"Signup attempt: role={role}, agent_id={agent_id}, lender_id={lender_id}")
        
        # Use retry logic for database operations to handle locking
        max_retries = 5
        retry_count = 0
        user_id = None
        last_error = None
        
        while retry_count < max_retries:
            try:
                user_id = create_user(name, email, password_hash, role, agent_id=agent_id, lender_id=lender_id)
                _dbg(f"DEBUG Signup: User created successfully with ID {user_id}")
                
                # Verify the account was actually created by querying the database
                from database import get_user_by_email
                verify_user = get_user_by_email(email)
                if not verify_user:
                    raise ValueError("Account creation failed - user not found in database after creation")
                
                # Convert Row to dict if needed
                if hasattr(verify_user, 'keys') and not isinstance(verify_user, dict):
                    verify_user = dict(verify_user)
                
                # Verify the password hash matches
                if not verify_user.get("password_hash"):
                    raise ValueError("Account creation failed - password hash not set")
                
                _dbg(f"DEBUG Signup: Account verified - user exists with ID {verify_user.get('id')}")
                user_id = verify_user.get('id')  # Use verified user ID
                break  # Success, exit retry loop
                
            except sqlite3.OperationalError as e:
                last_error = e
                error_str = str(e).lower()
                if "locked" in error_str and retry_count < max_retries - 1:
                    retry_count += 1
                    import time
                    wait_time = 0.5 * retry_count  # Exponential backoff: 0.5s, 1s, 1.5s, 2s
                    print(f"DEBUG Signup: Database locked, retrying in {wait_time}s ({retry_count}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    # Re-raise if not a lock issue or max retries reached
                    print(f"DEBUG Signup: OperationalError - {str(e)}")
                    if "locked" in error_str:
                        flash("Things are a little busy right now. Please give it a moment and try again.", "error")
                    else:
                        flash("Something went wrong on our end. Please try again in a moment.", "error")
                    import traceback
                    print(f"Database operational error during signup: {traceback.format_exc()}")
                    return redirect(url_for("signup", role=role, ref=referral_token_from_form))
            except ValueError as e:
                print(f"DEBUG Signup: ValueError - {str(e)}")
                flash(str(e), "error")
                return redirect(url_for("signup", role=role, ref=referral_token_from_form))
            except sqlite3.IntegrityError as e:
                # Check if it's a unique constraint violation (duplicate email)
                print(f"DEBUG Signup: IntegrityError - {str(e)}")
                if "UNIQUE constraint failed" in str(e) or "email" in str(e).lower():
                    # Check if the existing account is incomplete (no password_hash)
                    from database import get_user_by_email, update_user_password
                    existing_user = get_user_by_email(email)
                    
                    if existing_user:
                        # Convert Row to dict if needed
                        if hasattr(existing_user, 'keys') and not isinstance(existing_user, dict):
                            existing_user = dict(existing_user)
                        
                        # Check if account is incomplete (missing password_hash)
                        if not existing_user.get("password_hash"):
                            print("Signup: completing an incomplete account")
                            try:
                                # Check if role matches - if not, we can't complete it
                                existing_role = existing_user.get("role")
                                if existing_role and existing_role != role:
                                    print(f"DEBUG Signup: Role mismatch - existing: {existing_role}, requested: {role}")
                                    flash(f"This email is registered as a {existing_role}, not a {role}. Please sign in instead.", "error")
                                    return redirect(url_for("login", role=existing_role))
                                
                                # A pre-created client keeps the agent/lender who added them. A different link
                                # (or the default agent) never takes them over; it is offered as an optional connect.
                                if role == "homeowner":
                                    from database import get_active_professional_id
                                    offered = False
                                    keep_a = get_active_professional_id(existing_user["id"], "agent")
                                    keep_l = get_active_professional_id(existing_user["id"], "lender")
                                    if keep_a and agent_id and keep_a != agent_id:
                                        agent_id, offered = None, True
                                    if keep_l and lender_id and keep_l != lender_id:
                                        lender_id, offered = None, True
                                    kept_existing = bool(keep_a or keep_l)
                                    if offered and referral_token_from_form not in (None, "", "default"):
                                        session["pending_connect"] = referral_token_from_form
                                # Update the incomplete account with password, name, and role/agent_id/lender_id if needed
                                update_user_password(
                                    existing_user["id"],
                                    password_hash,
                                    name if name else existing_user.get("name"),
                                    role if role else existing_role,
                                    agent_id if role == "homeowner" else None,
                                    lender_id if role == "homeowner" else None
                                )
                                
                                # Verify the update worked
                                verify_user = get_user_by_email(email)
                                if verify_user:
                                    # Convert Row to dict if needed
                                    if hasattr(verify_user, 'keys') and not isinstance(verify_user, dict):
                                        verify_user = dict(verify_user)
                                    
                                    if verify_user.get("password_hash"):
                                        user_id = existing_user["id"]
                                        _dbg(f"DEBUG Signup: Incomplete account completed successfully - ID {user_id}")
                                        # Break out of retry loop and continue with signup flow
                                        break
                                    else:
                                        raise ValueError("Account update failed - password hash still not set")
                                else:
                                    raise ValueError("Account update failed - user not found after update")
                            except Exception as update_error:
                                print(f"DEBUG Signup: Error completing incomplete account - {str(update_error)}")
                                flash("Something went wrong while finishing your account. Please try again.", "error")
                                return redirect(url_for("signup", role=role, ref=referral_token_from_form))
                        else:
                            # Account already has a password: never overwrite it from signup.
                            if role == "homeowner" and referral_token_from_form not in (None, "", "default"):
                                session["pending_connect"] = referral_token_from_form
                            flash("An account with that email already exists. Please sign in, or use \"Forgot password?\".", "error")
                            return redirect(url_for("login", role=existing_user.get("role") or role))
                    else:
                        # Email constraint failed but user not found - this shouldn't happen
                        print(f"DEBUG Signup: IntegrityError but user not found - {str(e)}")
                        flash("That email is already in use. Please sign in instead.", "error")
                        return redirect(url_for("login", role=role))
                else:
                    flash("Something went wrong while creating your account. Please try again.", "error")
                    import traceback
                    print(f"Database error during signup: {traceback.format_exc()}")
                    return redirect(url_for("signup", role=role, ref=referral_token_from_form))
            except Exception as e:
                last_error = e
                print(f"DEBUG Signup: Exception - {type(e).__name__}: {str(e)}")
                # For non-lock errors, don't retry
                if "locked" not in str(e).lower():
                    flash("Something went wrong on our end. Please try again in a moment.", "error")
                    import traceback
                    print(f"Unexpected error during signup: {traceback.format_exc()}")
                    return redirect(url_for("signup", role=role, ref=referral_token_from_form))
                # If it's a lock error but not OperationalError, retry
                if retry_count < max_retries - 1:
                    retry_count += 1
                    import time
                    wait_time = 0.5 * retry_count
                    print(f"DEBUG Signup: Retrying after error ({retry_count}/{max_retries})...")
                    time.sleep(wait_time)
                    continue
                else:
                    flash("Something went wrong on our end. Please try again in a moment.", "error")
                    import traceback
                    print(f"Unexpected error during signup: {traceback.format_exc()}")
                    return redirect(url_for("signup", role=role, ref=referral_token_from_form))
        
        if not user_id:
            # If we get here, all retries failed
            error_msg = f"Unable to create account. {str(last_error) if last_error else 'Please try again in a moment.'}"
            if last_error and "locked" in str(last_error).lower():
                flash("Things are a little busy right now. Please give it a moment and try again.", "error")
            else:
                flash(error_msg, "error")
            print(f"DEBUG Signup: All retries failed. Last error: {last_error}")
            return redirect(url_for("signup", role=role, ref=referral_token_from_form))

        # CRITICAL: Create client relationship AND CRM contact - MUST WORK
        if role == "homeowner":
            print(f"\n{'='*60}")
            print(f"SIGNUP: Setting up homeowner relationships")
            print(f"  Homeowner ID: {user_id}")
            print(f"  Agent ID: {agent_id}")
            print(f"  Lender ID: {lender_id}")
            print(f"  Referral Token: {referral_token_from_form}")
            print(f"{'='*60}\n")
            
            from database import (
                create_client_relationship, 
                add_agent_contact, 
                list_agent_contacts,
                get_user_by_id
            )
            
            relationships_created = []
            crm_contacts_created = []
            
            # Handle agent relationship
            if agent_id:
                try:
                    # Verify agent exists
                    agent_user = get_user_by_id(agent_id)
                    if not agent_user:
                        print(f"SIGNUP ERROR: Agent {agent_id} not found!")
                        flash("We could not find that agent. Please reach out and we will sort it out for you.", "error")
                    else:
                        agent_dict = dict(agent_user) if hasattr(agent_user, 'keys') and not isinstance(agent_user, dict) else agent_user
                        print(f"SIGNUP: Agent verified - {agent_dict.get('name')} (ID: {agent_id})")
                        
                        # Create client relationship - CRITICAL
                        try:
                            relationship_id = create_client_relationship(
                                homeowner_id=user_id,
                                professional_id=agent_id,
                                professional_role="agent",
                                referral_code=referral_token_from_form if referral_token_from_form != "default" else None
                            )
                            relationships_created.append(f"agent relationship (ID: {relationship_id})")
                            print(f"SIGNUP SUCCESS: Created client relationship - homeowner {user_id} -> agent {agent_id} (relationship ID: {relationship_id})")
                        except Exception as rel_error:
                            print(f"SIGNUP ERROR: Failed to create client relationship - {str(rel_error)}")
                            import traceback
                            print(traceback.format_exc())
                            flash("Your account is ready, but we could not connect you to your agent yet. Please reach out and we will fix it right away.", "error")
                        
                        # Create CRM contact - CRITICAL
                        try:
                            # Check if contact already exists
                            existing_contacts = list_agent_contacts(agent_id)
                            contact_exists = False
                            existing_contact_id = None
                            for existing in existing_contacts:
                                existing_dict = dict(existing) if hasattr(existing, 'keys') and not isinstance(existing, dict) else existing
                                if existing_dict.get("email") and existing_dict.get("email").lower() == email.lower():
                                    contact_exists = True
                                    existing_contact_id = existing_dict.get("id")
                                    print(f"SIGNUP: CRM contact already exists (ID: {existing_contact_id})")
                                    break
                            
                            if not contact_exists:
                                contact_id = add_agent_contact(
                                    agent_user_id=agent_id,
                                    name=name,
                                    email=email,
                                    phone="",
                                    stage="new",
                                    best_contact=email if email else "",
                                    last_touch="",
                                    birthday="",
                                    home_anniversary="",
                                    address="",
                                    notes=f"Signed up via referral link on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                    tags="referral",
                                    property_address="",
                                    property_value=None,
                                    equity_estimate=None,
                                    user_id=user_id,
                                )
                                crm_contacts_created.append(f"CRM contact (ID: {contact_id})")
                                print(f"SIGNUP SUCCESS: Created CRM contact {contact_id} for agent {agent_id}")
                                
                                # VERIFY: Check that contact was actually created
                                verify_contacts = list_agent_contacts(agent_id)
                                found_contact = False
                                for vc in verify_contacts:
                                    vc_dict = dict(vc) if hasattr(vc, 'keys') and not isinstance(vc, dict) else vc
                                    if vc_dict.get("id") == contact_id:
                                        found_contact = True
                                        print(f"SIGNUP VERIFICATION: CRM contact {contact_id} confirmed in agent's CRM")
                                        break
                                
                                if not found_contact:
                                    print(f"SIGNUP VERIFICATION ERROR: CRM contact {contact_id} NOT found in agent's CRM after creation!")
                                    flash("Your account is ready, but we could not finish connecting you to your agent. Please reach out and we will take care of it.", "error")
                                
                                # SEND EMAIL NOTIFICATION TO AGENT
                                signup_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                                try:
                                    send_new_lead_notification(
                                        agent_id=agent_id,
                                        homeowner_name=name,
                                        homeowner_email=email,
                                        referral_token=referral_token_from_form if referral_token_from_form != "default" else None,
                                        signup_timestamp=signup_time
                                    )
                                    print(f"SIGNUP: Email notification sent to agent {agent_id}")
                                except Exception as email_error:
                                    print(f"SIGNUP WARNING: Could not send email notification - {str(email_error)}")
                                    # Don't fail signup if email fails
                            else:
                                # Contact already existed — link user_id so CRM ↔ portal are bridged
                                print(f"SIGNUP: CRM contact already exists (ID: {existing_contact_id}), skipping creation")
                                crm_contacts_created.append(f"CRM contact (ID: {existing_contact_id}, already existed)")
                                if existing_contact_id:
                                    try:
                                        from database import get_connection as _gc
                                        _conn = _gc()
                                        _conn.execute(
                                            "UPDATE agent_contacts SET user_id = ? WHERE id = ? AND user_id IS NULL",
                                            (user_id, existing_contact_id)
                                        )
                                        _conn.commit()
                                        _conn.close()
                                    except Exception as _link_err:
                                        print(f"SIGNUP: Could not link existing CRM contact user_id - {_link_err}")
                        except Exception as crm_error:
                            print(f"SIGNUP ERROR: Failed to create CRM contact - {str(crm_error)}")
                            import traceback
                            print(traceback.format_exc())
                            flash("Your account is ready, but we could not finish connecting you to your agent. Please reach out and we will take care of it.", "error")
                except Exception as agent_error:
                    print(f"SIGNUP ERROR: Agent setup failed - {str(agent_error)}")
                    import traceback
                    print(traceback.format_exc())
                    flash("Your account is ready, but we could not connect you to your agent yet. Please reach out and we will fix it right away.", "error")
            
            # Handle lender relationship
            if lender_id:
                try:
                    relationship_id = create_client_relationship(
                        homeowner_id=user_id,
                        professional_id=lender_id,
                        professional_role="lender",
                        referral_code=referral_token_from_form if referral_token_from_form != "default" else None
                    )
                    relationships_created.append(f"lender relationship (ID: {relationship_id})")
                    print(f"SIGNUP SUCCESS: Created client relationship - homeowner {user_id} -> lender {lender_id}")
                    
                    # Create lender CRM borrower record linked to the homeowner's account
                    from database import add_lender_borrower, list_lender_borrowers
                    try:
                        existing_borrowers = list_lender_borrowers(lender_id)
                        borrower_exists = any(
                            (b.get("email") or "").lower() == email.lower()
                            for b in existing_borrowers
                        )
                        if not borrower_exists:
                            borrower_id = add_lender_borrower(
                                lender_user_id=lender_id,
                                name=name,
                                email=email,
                                status="prospect",
                                notes=f"Signed up via referral link on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                                tags="referral",
                                user_id=user_id,
                            )
                            relationships_created.append(f"lender CRM borrower (ID: {borrower_id})")
                            print(f"SIGNUP SUCCESS: Created lender CRM borrower {borrower_id} for lender {lender_id}")
                        else:
                            # Link existing borrower record to this user account
                            try:
                                from database import get_connection as _gc2
                                _conn2 = _gc2()
                                _conn2.execute(
                                    "UPDATE lender_borrowers SET user_id = ? WHERE lender_user_id = ? AND LOWER(email) = LOWER(?) AND user_id IS NULL",
                                    (user_id, lender_id, email)
                                )
                                _conn2.commit()
                                _conn2.close()
                            except Exception as _lb_err:
                                print(f"SIGNUP: Could not link existing lender borrower user_id - {_lb_err}")
                    except Exception as lb_error:
                        print(f"SIGNUP WARNING: Could not create lender CRM borrower - {str(lb_error)}")

                except Exception as lender_error:
                    print(f"SIGNUP ERROR: Failed to create lender relationship - {str(lender_error)}")
                    import traceback
                    print(traceback.format_exc())
            
            # Final verification - verify relationships were actually created
            from database import get_homeowner_professionals
            try:
                verify_profs = get_homeowner_professionals(user_id)
                print(f"SIGNUP VERIFICATION: Found {len(verify_profs)} professionals for homeowner {user_id}")
                for vp in verify_profs:
                    vp_dict = dict(vp) if hasattr(vp, 'keys') and not isinstance(vp, dict) else vp
                    print(f"  - {vp_dict.get('professional_role')}: {vp_dict.get('name')} (ID: {vp_dict.get('professional_id')})")
            except Exception as verify_error:
                print(f"SIGNUP VERIFICATION ERROR: {str(verify_error)}")
            
            # Final summary
            print(f"\n{'='*60}")
            print(f"SIGNUP: Relationship Summary")
            print(f"  Relationships created: {len(relationships_created)}")
            for rel in relationships_created:
                print(f"    - {rel}")
            print(f"  CRM contacts created: {len(crm_contacts_created)}")
            for crm in crm_contacts_created:
                print(f"    - {crm}")
            print(f"{'='*60}\n")
            
            # Success message
            if kept_existing and not relationships_created:
                flash("Welcome back! You are still connected with the agent or lender who set you up.", "success")
            elif referral_token_from_form == "default":
                flash("Welcome! You've been connected to Kayleigh Biggs at Worth Clark Realty.", "success")
            else:
                if relationships_created and crm_contacts_created:
                    flash("Welcome! You've been connected to your professional team and added to their CRM.", "success")
                elif relationships_created:
                    flash("Welcome! You've been connected to your professional team.", "success")
                else:
                    flash("Your account is ready, but we could not connect you to your agent yet. Please reach out and we will fix it right away.", "error")

        # Auto-login after signup (permanent session for convenience)
        session.permanent = True
        session["user_id"] = user_id
        session["role"] = role
        session["name"] = name or "Friend"
        _send_verification_email(user_id, email, background=True)
        
        # Success message for agents/lenders
        if role == "agent":
            flash("Account created! Welcome to Your Life Your Home.", "success")
        elif role == "lender":
            flash("Account created! Welcome to Your Life Your Home.", "success")
        
        # Save email to localStorage (will be handled by JavaScript)
        response = redirect(url_for("agent_dashboard") if role == "agent"
                           else url_for("lender_dashboard") if role == "lender"
                           else url_for("homeowner_overview"))
        
        # Set cookie to trigger JavaScript to save email
        response.set_cookie("save_email", email, max_age=365*24*60*60)
        
        return response

    return render_template(
        "auth/signup.html", 
        role=role, 
        brand_name=FRONT_BRAND_NAME,
        referral_code=referral_token,  # Keep for backward compatibility in template
        inviter=_inviter_for_token(referral_token) if role == "homeowner" else None,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    """REWRITTEN: Simple, direct login that always works."""
    role = request.args.get("role") or request.form.get("role")
    
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        selected_role = request.form.get("role", "").strip()
        
        if not email or not password:
            flash("Please enter your email and password so we can sign you in.", "error")
            return redirect(url_for("login", role=selected_role))
        
        if not selected_role:
            flash("Please choose how you use the site: homeowner, agent or lender.", "error")
            return redirect(url_for("login"))
        
        # Get user
        try:
            user_row = get_user_by_email(email)
        except Exception as e:
            print(f"LOGIN ERROR: {str(e)}")
            flash("Something went wrong on our end. Please try again in a moment.", "error")
            return redirect(url_for("login", role=selected_role))
        
        if not user_row:
            flash("We could not find a match for that email and password. Please try again, or use \"Forgot password?\" and we will help you get back in.", "error")
            return redirect(url_for("login", role=selected_role))
        
        # Convert to dict
        user = dict(user_row) if hasattr(user_row, 'keys') and not isinstance(user_row, dict) else (user_row if isinstance(user_row, dict) else {})
        
        user_id = user.get("id")
        user_role = str(user.get("role") or "").strip().lower()
        stored_hash = user.get("password_hash")
        
        # Check password hash exists
        if not stored_hash or not stored_hash.strip():
            flash("Account incomplete. Please sign up again with the same email to set your password.", "error")
            return redirect(url_for("signup", role=selected_role))
        
        # Verify password
        try:
            password_correct = check_password_hash(stored_hash, password)
        except Exception as e:
            print(f"LOGIN PASSWORD CHECK ERROR: {str(e)}")
            password_correct = False

        if not password_correct:
            flash("We could not find a match for that email and password. Please try again, or use \"Forgot password?\" and we will help you get back in.", "error")
            return redirect(url_for("login", role=selected_role))

        # Check role
        if user_role != str(selected_role).strip().lower():
            flash(f"This account is registered as a {user.get('role', 'user').title()}. Please select the correct role.", "error")
            return redirect(url_for("login", role=user.get("role", "homeowner")))
        
        # Two-step login: park the user until they enter their authenticator code
        try:
            from mfa import is_mfa_enabled
            if is_mfa_enabled(int(user_id)):
                session.clear()
                session["mfa_pending"] = {
                    "uid": int(user_id), "name": str(user.get("name") or "User"),
                    "role": str(user.get("role")), "remember": request.form.get("remember") == "on",
                    "ts": time.time(),
                }
                return redirect(url_for("login_verify"))
        except Exception as _e:
            print(f"[MFA] check skipped: {_e}")

        # Set session
        session.clear()
        session.permanent = request.form.get("remember") == "on"
        session["user_id"] = int(user_id)
        session["name"] = str(user.get("name") or "User")
        session["role"] = str(user.get("role"))
        session.modified = True
        try:
            from database import get_connection as _gc_login
            _c = _gc_login()
            _c.execute("UPDATE users SET last_login = datetime('now') WHERE id = ?", (int(user_id),))
            _c.commit()
            _c.close()
        except Exception as _e:
            print(f"[LOGIN] last_login update skipped: {_e}")

        # Redirect
        redirect_map = {
            "homeowner": url_for("homeowner_overview"),
            "agent": url_for("agent_dashboard"),
            "lender": url_for("lender_dashboard")
        }
        redirect_url = redirect_map.get(user_role, url_for("index"))
        
        response = redirect(redirect_url)
        response.set_cookie("save_email", email, max_age=365*24*60*60 if session.permanent else None)
        return response
    
    return render_template("auth/login.html", role=role)


def _finish_login(uid, name, role, remember=False):
    session.clear()
    session.permanent = bool(remember)
    session["user_id"] = int(uid)
    session["name"] = name
    session["role"] = role
    session.modified = True
    try:
        c = get_connection()
        c.execute("UPDATE users SET last_login = datetime('now') WHERE id = ?", (int(uid),))
        c.commit()
        c.close()
    except Exception as e:
        print(f"[LOGIN] last_login update skipped: {e}")
    target = {"homeowner": "homeowner_overview", "agent": "agent_dashboard", "lender": "lender_dashboard"}.get(role, "index")
    return redirect(url_for(target))


@app.route("/login/verify", methods=["GET", "POST"])
def login_verify():
    pend = session.get("mfa_pending")
    if not pend or time.time() - pend.get("ts", 0) > 300:
        session.pop("mfa_pending", None)
        flash("Please sign in again.", "error")
        return redirect(url_for("login"))
    if request.method == "POST":
        from mfa import verify_mfa_code
        ok, _used_backup = verify_mfa_code(pend["uid"], request.form.get("code", "").strip().replace(" ", ""))
        if ok:
            return _finish_login(pend["uid"], pend["name"], pend["role"], pend.get("remember"))
        flash("That code didn't work. Try the current 6-digit code, or a backup code.", "error")
        return redirect(url_for("login_verify"))
    return render_template("auth/login_verify.html")


@app.route("/account/security", methods=["GET", "POST"])
def account_security():
    uid = session.get("user_id")
    if not uid:
        return redirect(url_for("login"))
    from mfa import generate_mfa_secret, verify_mfa_code, enable_mfa, disable_mfa, is_mfa_enabled
    enabled = bool(is_mfa_enabled(uid))
    action = request.form.get("action") if request.method == "POST" else None
    if action == "start" and not enabled:
        c = get_connection()
        row = c.execute("SELECT email FROM users WHERE id=?", (uid,)).fetchone()
        c.close()
        secret, qr, codes = generate_mfa_secret(uid, row["email"])
        return render_template("account/security.html", enabled=False, setup=True, secret=secret, qr=qr, codes=codes)
    if action == "confirm" and not enabled:
        code = request.form.get("code", "").strip().replace(" ", "")
        import pyotp
        c = get_connection()
        row = c.execute("SELECT secret FROM mfa_settings WHERE user_id=?", (uid,)).fetchone()
        c.close()
        if row and pyotp.TOTP(row["secret"]).verify(code, valid_window=1):
            enable_mfa(uid)
            flash("Two-step sign-in is on.", "success")
        else:
            flash("That code didn't match. Start again and scan the new QR code.", "error")
        return redirect(url_for("account_security"))
    if action == "disable" and enabled:
        ok, _ = verify_mfa_code(uid, request.form.get("code", "").strip().replace(" ", ""))
        if ok:
            disable_mfa(uid)
            flash("Two-step sign-in is off.", "success")
        else:
            flash("That code didn't match, so it was left on.", "error")
        return redirect(url_for("account_security"))
    return render_template("account/security.html", enabled=enabled, setup=False)


# ---------------- PASSWORD RESET (emailed, single-use, expiring link) ----------------
def _reset_serializer():
    from itsdangerous import URLSafeTimedSerializer
    return URLSafeTimedSerializer(app.secret_key, salt="ylh-password-reset")


def _reset_fingerprint(password_hash):
    """Tie a token to the current password so it dies the moment the password changes."""
    import hashlib
    return hashlib.sha256((password_hash or "").encode()).hexdigest()[:16]


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """Step 1: ask for an email; send a reset link if the account exists."""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if email:
            try:
                user_row = get_user_by_email(email)
                if user_row:
                    user = dict(user_row) if hasattr(user_row, "keys") and not isinstance(user_row, dict) else user_row
                    token = _reset_serializer().dumps(
                        {"uid": user["id"], "fp": _reset_fingerprint(user.get("password_hash"))}
                    )
                    link = url_for("reset_password", token=token, _external=True)
                    _bg(
                        send_reminder_email,
                        email,
                        "Reset your password",
                        "Hi there,\n\nNo worries, it happens to all of us. Here is your link to choose a new password:\n\n"
                        f"{link}\n\nIt works for 1 hour. If you did not ask for this, you can ignore this email and your password will stay just as it is.\n\n"
                        "Take care,\nYour Life, Your Home",
                    )
            except Exception as e:
                print(f"FORGOT PASSWORD ERROR: {e}")
        # Same message whether or not the account exists (prevents account enumeration)
        flash("If an account exists for that email, a reset link is on its way.", "success")
        return redirect(url_for("login"))
    return render_template("auth/forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    """Step 2: set a new password using the emailed link."""
    from itsdangerous import BadSignature, SignatureExpired
    from database import update_user_password, get_user_by_id
    try:
        data = _reset_serializer().loads(token, max_age=3600)
        user_row = get_user_by_id(data["uid"])
        user = dict(user_row) if user_row and hasattr(user_row, "keys") and not isinstance(user_row, dict) else user_row
        if not user or _reset_fingerprint(user.get("password_hash")) != data.get("fp"):
            raise BadSignature("stale")
    except (SignatureExpired, BadSignature, KeyError, TypeError):
        flash("That reset link has expired or is not quite right. No worries, you can request a new one.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        new_password = request.form.get("password", "")
        if new_password != request.form.get("confirm_password", ""):
            flash("Those two passwords do not match yet. Please try again.", "error")
            return redirect(url_for("reset_password", token=token))
        if len(new_password) < 8:
            flash("Please choose a password with at least 8 characters.", "error")
            return redirect(url_for("reset_password", token=token))
        update_user_password(user["id"], generate_password_hash(new_password))
        _mark_email_verified(user["id"])
        flash("Password updated. Please sign in with your new password.", "success")
        return redirect(url_for("login", role=user.get("role", "homeowner")))
    return render_template("auth/reset_password.html", token=token)


@app.route("/logout")
def logout():
    """Logout and clear session."""
    user_id = session.get("user_id")
    session.clear()
    session.modified = True  # Ensure session is saved
    print(f"LOGOUT: User {user_id} logged out")
    flash("You have been signed out.", "success")
    return redirect(url_for("index"))


# -------------------------------------------------
# HOMEOWNER ROUTES
# -------------------------------------------------


# ----- SAVED NOTES / DESIGN BOARDS -----


# ----- HOME TIMELINE & DOCUMENTS -----


# ----- VALUE & EQUITY -----


def _value_change_last_year(history, snapshot):
    """Dollar change in estimated value over the available history (up to a year). None if unknown."""
    try:
        now = (snapshot or {}).get("value_estimate")
        pts = [h for h in (history or []) if h.get("value_estimate")]
        if not now or len(pts) < 2:
            return None
        oldest = sorted(pts, key=lambda h: h["snapshot_date"])[0]
        return float(now) - float(oldest["value_estimate"])
    except Exception:
        return None


# ----- RENOVATION & IMPROVEMENT -----


# -------------------------------------------------
# AGENT ROUTES
# -------------------------------------------------


def _parse_address_city_state_zip(addr_str):
    """Parse 'Street, City, ST 12345' format when city/state/zip are missing from DB."""
    import re
    if not addr_str or not addr_str.strip():
        return None, None, None, None
    s = addr_str.strip()
    # Match ", City, ST 12345" or ", City, ST 12345-6789" at end
    m = re.search(r',\s*([^,]+),\s*([A-Za-z]{2})\s+(\d{5}(?:-\d{4})?)\s*$', s)
    if m:
        city = m.group(1).strip()
        state = m.group(2).strip().upper()
        zip_code = m.group(3).strip()
        street = s[:m.start()].strip().rstrip(',')
        return street, city, state, zip_code
    return None, None, None, None


def _build_full_address(c):
    """Build full address string with street, city, state, zip."""
    street = (c.get("address") or c.get("property_address") or "").strip()
    city = (c.get("city") or "").strip()
    state = (c.get("state") or "").strip()
    # Normalize zip: strip float suffix (.0) if stored that way
    raw_zip = str(c.get("zip_code") or "").strip()
    if raw_zip.endswith(".0") and raw_zip[:-2].isdigit():
        raw_zip = raw_zip[:-2]
    zip_code = raw_zip
    # If city/state/zip empty but address has "Street, City, ST 12345" format, parse it
    if not (city or state or zip_code) and street:
        parsed_street, parsed_city, parsed_state, parsed_zip = _parse_address_city_state_zip(street)
        if parsed_city:
            street = parsed_street or street
            city, state, zip_code = parsed_city, parsed_state, parsed_zip
    parts = []
    if street:
        parts.append(street)
    if city or state or zip_code:
        csz = ", ".join(filter(None, [city, " ".join(filter(None, [state, zip_code]))]))
        if csz:
            parts.append(csz.strip().rstrip(","))
    return "\n".join(parts) if parts else ""


def _normalize_phone(s):
    """Normalize phone for duplicate check: digits only, last 10 for US."""
    if not s:
        return ""
    digits = "".join(c for c in str(s) if c.isdigit())
    return digits[-10:] if len(digits) >= 10 else digits


def _normalize_name_for_match(s):
    """Normalize name for flexible matching."""
    if not s:
        return ""
    s = str(s).strip().lower()
    s = " ".join(s.split())  # collapse spaces
    s = s.replace("&", " ").replace(" and ", " ")
    return " ".join(s.split())


def _names_match(excel_name, db_name):
    """Flexible name matching: exact, or one contains the other."""
    a = _normalize_name_for_match(excel_name)
    b = _normalize_name_for_match(db_name)
    if not a or not b:
        return False
    if a == b:
        return True
    if a in b or b in a:
        return True
    # Try matching first/last parts (e.g. "Carr, Michael" vs "Carr, Michael & Megan")
    a_parts = set(p for p in a.split() if len(p) > 1)
    b_parts = set(p for p in b.split() if len(p) > 1)
    overlap = a_parts & b_parts
    if len(overlap) >= 2:  # at least 2 words match (e.g. first + last name)
        return True
    return False


def extract_features_from_notes(notes):
    """
    Extract spotlight card features from walkthrough notes using AI.
    Returns a list of feature dictionaries with title, room, and description.
    """
    openai_api_key = os.environ.get('OPENAI_API_KEY')
    
    if not openai_api_key:
        # Fallback: return empty list if no AI available
        print("OpenAI API key not found - cannot extract features from notes")
        return []
    
    try:
        # Try new OpenAI API (v1.0+)
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_api_key)
            
            prompt = f"""You are helping a real estate agent create property feature spotlight cards to highlight every notable update and feature of a home.

Walkthrough Notes:
{notes}

Your job is to create ONE spotlight card for EVERY distinct item, update, or feature mentioned. Do not skip any item, every line or bullet in the notes should become its own card.

For each feature:
1. room/area: Use the most relevant label (e.g., HOME, KITCHEN, PRIMARY BATH, BACKYARD, BASEMENT, HOA, etc.)
2. title: Short, catchy, buyer-focused title (4-7 words)
3. description: 1-2 warm, natural sentences a buyer would appreciate. Include the year if mentioned.

IMPORTANT: Return a JSON object with a single key "features" whose value is an array. Do not truncate. Include every single item. No markdown, no explanation.

Example:
{{
  "features": [
    {{"room": "KITCHEN", "title": "Black Quartzite Countertops with New Sink", "description": "Upgraded in 2021, sleek black quartzite countertops paired with a new sink and faucet bring a bold, modern elegance to the kitchen."}},
    {{"room": "HOME", "title": "New Roof (2024)", "description": "A brand-new roof installed in July 2024 gives buyers peace of mind and years of worry-free ownership."}}
  ]
}}"""

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "You are a real estate feature writer. Extract every single item from the notes as its own spotlight card. Return ONLY a complete, valid JSON array with no truncation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=4000,
                response_format={"type": "json_object"}
            )
            
            import json
            raw = __import__("ai_platform").humanize(response.choices[0].message.content.strip())
            parsed = json.loads(raw)
            # Handle both {"features": [...]} wrapper and bare array
            if isinstance(parsed, dict):
                result = parsed.get("features") or parsed.get("items") or list(parsed.values())[0]
            else:
                result = parsed
            
            # Validate result is a list
            if isinstance(result, list) and len(result) > 0:
                # Ensure all features have required fields
                valid_features = []
                for feature in result:
                    if 'room' in feature and 'title' in feature and 'description' in feature:
                        valid_features.append({
                            'room': feature['room'],
                            'title': feature['title'],
                            'description': feature['description']
                        })
                return valid_features
            
            return []
            
        except (ImportError, AttributeError):
            # Fall back to old OpenAI API format
            import openai
            openai.api_key = openai_api_key
            
            prompt = f"""You are helping a real estate agent create property feature spotlight cards to highlight every notable update and feature of a home.

Walkthrough Notes:
{notes}

Your job is to create ONE spotlight card for EVERY distinct item, update, or feature mentioned. Do not skip any item.

For each feature:
1. room/area: Use the most relevant label (e.g., HOME, KITCHEN, PRIMARY BATH, BACKYARD, BASEMENT, HOA, etc.)
2. title: Short, catchy, buyer-focused title (4-7 words)
3. description: 1-2 warm, natural sentences a buyer would appreciate. Include the year if mentioned.

IMPORTANT: Return ONLY a valid JSON array. Do not truncate. Include every single item. No markdown, no explanation."""

            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo-16k",
                messages=[
                    {"role": "system", "content": "You are a real estate feature writer. Extract every single item from the notes as its own spotlight card. Return ONLY a complete, valid JSON array with no truncation."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=4000
            )
            
            import json
            result = json.loads(__import__("ai_platform").humanize(response.choices[0].message.content.strip()))
            
            # Validate result is a list
            if isinstance(result, list) and len(result) > 0:
                # Ensure all features have required fields
                valid_features = []
                for feature in result:
                    if 'room' in feature and 'title' in feature and 'description' in feature:
                        valid_features.append({
                            'room': feature['room'],
                            'title': feature['title'],
                            'description': feature['description']
                        })
                return valid_features
            
            return []
            
    except Exception as e:
        import traceback
        print(f"Error extracting features from notes: {traceback.format_exc()}")
        return []


def refine_feature_text(feature):
    """
    Refine feature title and description to be more elegant, human, and professional.
    Uses OpenAI if available, otherwise uses simple text processing.
    """
    title = feature.get('title', '').strip()
    description = feature.get('description', '').strip()
    room = feature.get('room', '').strip()
    
    # Simple refinement rules (fallback)
    refined_title = title.strip()
    refined_description = description.strip()
    
    # Clean up title
    if refined_title:
        refined_title = refined_title[0].upper() + refined_title[1:] if len(refined_title) > 1 else refined_title.upper()
    
    # Clean up description
    if refined_description:
        if refined_description[-1] not in '.!?':
            refined_description += '.'
        refined_description = refined_description[0].upper() + refined_description[1:] if len(refined_description) > 1 else refined_description.upper()
    
    # Try OpenAI if available
    try:
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        if openai_api_key:
            try:
                # Try new OpenAI API (v1.0+)
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=openai_api_key)
                    
                    prompt = f"""You are helping write property feature descriptions that sound natural, human, and luxurious.

Original Feature:
Title: {title}
Room: {room}
Description: {description}

Make this sound better by:
1. Using natural, conversational language that regular people use
2. Sounding like a real person describing a beautiful, high-quality home
3. Being clear and specific (1-2 short sentences max)
4. Adding subtle luxury through quality words, not fancy jargon
5. Focusing on what people care about (comfort, space, quality, light, style)

AVOID overly fancy words like: meticulously, exquisite, boasts, showcases, curated, bespoke, epitome, essence, seamlessly, impeccably

LUXURY WORDS TO USE (sparingly, naturally): beautiful, spacious, custom, elegant, warm, bright, open, generous, premium, quality, designer, modern, classic, updated, refined, inviting, peaceful, private, sun-filled, hand-crafted

EVERYDAY CONNECTORS: has, includes, offers, with, perfect for, great for, opens to, leads to, keeps, helps, makes, gives you

Return ONLY a JSON object with "title" and "description" fields. No other text.

Example format:
{{"title": "Custom Walk-In Pantry", "description": "Beautiful custom shelving offers generous storage space and keeps counters clear for easy meal prep."}}"""

                    response = client.chat.completions.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant who writes natural, conversational property descriptions with subtle luxury. Sound human and authentic."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.65,
                        max_tokens=150
                    )
                    
                    import json
                    result = json.loads(__import__("ai_platform").humanize(response.choices[0].message.content.strip()))
                    refined_title = result.get('title', refined_title)
                    refined_description = result.get('description', refined_description)
                except (ImportError, AttributeError):
                    # Fall back to old OpenAI API format
                    import openai
                    openai.api_key = openai_api_key
                    
                    prompt = f"""You are helping write property feature descriptions that sound natural, human, and luxurious.

Original Feature:
Title: {title}
Room: {room}
Description: {description}

Make this sound better by:
1. Using natural, conversational language that regular people use
2. Sounding like a real person describing a beautiful, high-quality home
3. Being clear and specific (1-2 short sentences max)
4. Adding subtle luxury through quality words, not fancy jargon
5. Focusing on what people care about (comfort, space, quality, light, style)

AVOID overly fancy words like: meticulously, exquisite, boasts, showcases, curated, bespoke, epitome, essence, seamlessly, impeccably

LUXURY WORDS TO USE (sparingly, naturally): beautiful, spacious, custom, elegant, warm, bright, open, generous, premium, quality, designer, modern, classic, updated, refined, inviting, peaceful, private, sun-filled, hand-crafted

EVERYDAY CONNECTORS: has, includes, offers, with, perfect for, great for, opens to, leads to, keeps, helps, makes, gives you

Return ONLY a JSON object with "title" and "description" fields. No other text.

Example format:
{{"title": "Custom Walk-In Pantry", "description": "Beautiful custom shelving offers generous storage space and keeps counters clear for easy meal prep."}}"""

                    response = openai.ChatCompletion.create(
                        model="gpt-3.5-turbo",
                        messages=[
                            {"role": "system", "content": "You are a helpful assistant who writes natural, conversational property descriptions with subtle luxury. Sound human and authentic."},
                            {"role": "user", "content": prompt}
                        ],
                        temperature=0.65,
                        max_tokens=150
                    )
                    
                    import json
                    result = json.loads(__import__("ai_platform").humanize(response.choices[0].message.content.strip()))
                    refined_title = result.get('title', refined_title)
                    refined_description = result.get('description', refined_description)
            except ImportError:
                # OpenAI library not installed
                pass
            except Exception as e:
                # OpenAI API call failed, use simple refinement
                print(f"OpenAI refinement failed, using simple refinement: {e}")
                import traceback
                print(traceback.format_exc())
                pass
    except Exception as e:
        # Fall back to simple refinement
        print(f"Refinement error: {e}")
        pass
    
    return {
        'title': refined_title,
        'room': room,
        'description': refined_description
    }


# -------------------------------------------------
# MARKETING HUB ROUTES
# -------------------------------------------------


# ─────────────────────────────────────────────
#  INVOICE ROUTES
# ─────────────────────────────────────────────


# ─────────────────────────────────────────────
#  SEASONAL CHECKLISTS
# ─────────────────────────────────────────────

def _get_checklist_data(season: str, role: str) -> dict:
    """Return homeowner seasonal checklist content."""
    palette = {
        "spring": {"accent": "#6B8F5E", "light": "#EEF4EB", "icon": "", "label": "Spring"},
        "summer": {"accent": "#8B7A2F", "light": "#F7F3E3", "icon": "", "label": "Summer"},
        "fall":   {"accent": "#8B5A2B", "light": "#F5EDE3", "icon": "", "label": "Fall"},
        "winter": {"accent": "#4A6580", "light": "#E8EFF5", "icon": "", "label": "Winter"},
    }
    p = palette.get(season, palette["spring"])

    # Year-round homeowner maintenance plan — balanced so no task is overdone or missed.
    # Key system lifecycles woven throughout:
    #   Irrigation: Spring (start up) -> Summer (adjust) -> Fall (drain & shut off)
    #   HVAC: Spring (tune-up + filter) -> Summer (monthly filter check) -> Fall (furnace + filter) -> Winter (monthly filter check)
    #   Roof/Gutters: Spring (winter damage) -> Fall (pre-winter)
    #   Smoke/CO: Spring (annual battery + test) -> Winter (mid-season test)
    #   Caulking/Sealing: Spring (repair freeze damage) -> Fall (prep for winter cold)
    #   Deck/Fence: Summer (UV re-seal, one time per year)
    #   Lawn: Summer (grubs/weeds) -> Fall (aerate, overseed, fertilize)
    homeowner = {
        "spring": {
            "title": "Spring Home Refresh",
            "subtitle": "Wake your home up right after winter",
            "tagline": "Spring is your reset season. Undo winter's damage, restart your systems and set your home up for a smooth, worry-free summer.",
            "sections": [
                {
                    "heading": "Exterior & Curb Appeal",
                    "items": [
                        "Inspect roof for winter damage, missing shingles, lifted flashing, damaged gutters",
                        "Clean gutters and downspouts of winter debris, check for sagging or separation",
                        "Power wash siding, driveway, walkways and patio surfaces",
                        "Inspect foundation and basement walls for new cracks or moisture intrusion",
                        "Repair any caulking around windows, doors and exterior trim damaged by freeze-thaw",
                        "Fill and repair driveway and walkway cracks opened by winter frost heaving",
                        "Freshen landscaping, edge beds, add fresh mulch and plant seasonal color",
                        "Inspect fences, gates and retaining walls for winter heaving or damage",
                        "Start up the irrigation system, test each zone, check heads and connections",
                        "Trim tree branches back from the roofline and any overhead power lines",
                        "Touch up exterior paint and wood stain on trim, siding and decks",
                    ],
                },
                {
                    "heading": "Interior & Home Systems",
                    "items": [
                        "Schedule a professional AC tune-up before the first heat wave hits",
                        "Replace HVAC filters, set a monthly reminder through the summer",
                        "Test every smoke detector and CO alarm, replace all batteries annually",
                        "Test the sump pump before spring rains, pour water in the pit to confirm it activates",
                        "Flush sediment from the water heater and test the pressure relief valve",
                        "Deep clean behind the refrigerator (coils), stove and dryer, clear the dryer vent fully",
                        "Inspect plumbing under all sinks and around toilets for slow leaks or corrosion",
                        "Inspect crawl space and attic for moisture, pest activity or winter damage",
                        "Wash windows inside and out, check seals for fogging or failure",
                        "Test GFCI outlets in kitchen, bathrooms, garage and all outdoor locations",
                        "Schedule a professional pest inspection before warm weather opens the door for them",
                    ],
                },
            ],
        },
        "summer": {
            "title": "Summer Home Care",
            "subtitle": "Maintain, enjoy and keep cool all season",
            "tagline": "Summer heat tests your home's systems daily. These are the tasks that keep everything running smoothly while you enjoy the season.",
            "sections": [
                {
                    "heading": "Cooling & Indoor Comfort",
                    "items": [
                        "Check and replace HVAC filters monthly, heavy use means faster buildup",
                        "Keep the AC condenser unit clear of grass clippings, weeds and debris",
                        "Program your thermostat with away schedules to save energy all season",
                        "Check attic ventilation, proper airflow reduces cooling costs noticeably",
                        "Set ceiling fans to spin counterclockwise for a cooling downward breeze",
                        "Add window film or thermal curtains to west and south-facing windows",
                        "Check window AC units for proper drainage and clean their filters",
                        "Clean bathroom and kitchen exhaust fans, they help pull heat from the home",
                    ],
                },
                {
                    "heading": "Exterior & Outdoor Living",
                    "items": [
                        "Inspect and re-seal deck, patio and wood fence, UV and moisture cause real damage",
                        "Check deck boards and railings for rot, looseness or splinters, repair promptly",
                        "Clean and inspect the outdoor grill, replace worn parts before peak grilling",
                        "Adjust irrigation schedules for peak summer, water deeply 2–3x per week, not daily",
                        "Inspect outdoor hoses, faucets and sprinkler heads for leaks or low-pressure clogs",
                        "Treat the lawn for grubs and summer weeds before they take hold",
                        "Check pool filter, balance chemicals and inspect all equipment on a weekly schedule",
                        "Confirm ground around your foundation slopes away from the home, never toward it",
                        "Repair or replace damaged window and door screens to keep pests out",
                        "Check outdoor light fixtures, clean lenses and replace any burned-out bulbs",
                    ],
                },
            ],
        },
        "fall": {
            "title": "Fall Home Prep",
            "subtitle": "Winterize everything before the cold arrives",
            "tagline": "Fall is your last clear window to protect your home before winter. Every task you complete now is one less emergency you deal with in January.",
            "sections": [
                {
                    "heading": "Heating & Weatherproofing",
                    "items": [
                        "Schedule a furnace or boiler inspection and cleaning before first use of the season",
                        "Replace HVAC filters and stock up on extras, heating season means heavy monthly use",
                        "Have chimney and fireplace professionally cleaned and inspected, fire safety first",
                        "Replace worn weatherstripping on all exterior doors, test the seal with a dollar bill",
                        "Re-caulk around windows, pipes and exterior penetrations to prevent winter heat loss",
                        "Insulate any exposed pipes in unheated areas, garage, crawlspace, basement, attic",
                        "Drain all outdoor faucets, hose bibs and irrigation lines completely, prevent pipe bursts",
                        "Check attic insulation depth, if you can see the floor joists, add more before winter",
                        "Upgrade to a smart thermostat if you haven't, the energy savings pay for it quickly",
                        "Stock up on ice melt, sand and snow removal tools before the first freeze",
                    ],
                },
                {
                    "heading": "Exterior & Lawn",
                    "items": [
                        "Clean gutters and downspouts once all leaves have fallen, prevents dangerous ice dams",
                        "Inspect roof flashing, valleys and penetrations one final time before winter arrives",
                        "Remove dead or weak tree branches that could fall on your home in a winter storm",
                        "Rake leaves from the lawn before they mat down and suffocate the grass",
                        "Aerate and overseed the lawn, fall is the best time for recovery and thickening",
                        "Apply a slow-release winterizing fertilizer to your lawn and all garden beds",
                        "Plant spring bulbs now, tulips, daffodils and hyacinths need time to root before spring",
                        "Drain garden hoses, outdoor fountains and potted irrigation lines, store them indoors",
                        "Store patio furniture indoors or cover with weatherproof covers before hard frost",
                        "Seal driveway and walkway cracks before freeze-thaw cycles turn small cracks into big ones",
                        "Test outdoor lighting and improve coverage, days shorten fast and safety matters",
                    ],
                },
            ],
        },
        "winter": {
            "title": "Winter Home Watch",
            "subtitle": "Protect, monitor and plan through the cold",
            "tagline": "Winter asks a lot of your home. Stay ahead with these protection and planning tasks, and use the quiet season to set yourself up for a strong spring.",
            "sections": [
                {
                    "heading": "Safety & Warmth",
                    "items": [
                        "Know exactly where your main water shut-off valve is, burst pipes demand immediate action",
                        "Open cabinet doors under sinks when outdoor temps drop below 20°F",
                        "Let exposed faucets drip slightly during extreme cold snaps to prevent freezing",
                        "Keep a fire extinguisher accessible, holiday candles, fireplaces and cooking raise the risk",
                        "Restock your emergency kit, flashlights, batteries, blankets, bottled water, first aid",
                        "Run a whole-home humidifier to protect wood floors, furniture and your comfort",
                        "Monitor your water heater, cold inlet water puts extra stress on older units",
                        "Replace HVAC filters monthly throughout the heating season, don't skip",
                        "Keep the thermostat no lower than 55°F even while away for holidays or travel",
                        "Keep the garage door closed as much as possible, cold garages put pipes at risk",
                    ],
                },
                {
                    "heading": "Cold-Weather Exterior & Planning",
                    "items": [
                        "Clear snow and ice from all walkways and steps promptly, prevent dangerous falls",
                        "Use calcium chloride or sand near landscaping and concrete, rock salt causes damage",
                        "After heavy snowfall, safely remove buildup from the roof with a roof rake",
                        "Watch for ice dams forming at roof eaves, they signal an attic heat loss issue",
                        "Check the attic after major snow events for frost or moisture buildup",
                        "Test smoke and CO alarms mid-season, winter heating and cooking raise the stakes",
                        "Document all home improvements and repairs from this year for taxes and insurance",
                        "Review your homeowner's insurance policy, confirm coverage reflects your home's current value",
                        "Book spring contractors now (HVAC, landscaping, roofing, painters) before their schedules fill",
                        "Plan and budget your spring home improvement projects, the quiet season is perfect for it",
                    ],
                },
            ],
        },
    }

    season_data = homeowner.get(season, homeowner["spring"])
    return {**season_data, **p, "season": season, "role": role}


SEASONS = ["spring", "summer", "fall", "winter"]


# -------------------------------------------------
# AGENT VIDEO STUDIO ROUTES
# -------------------------------------------------


# -------------------------------------------------
# ADMIN SETTINGS ROUTES
# -------------------------------------------------


# ═══════════════════════════════════════════════════════════════════════════
#  STRIPE SUBSCRIPTION ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/stripe/webhook", methods=["POST"])
def stripe_webhook():
    """Handle Stripe webhook events."""
    from database import update_user_subscription, downgrade_user_subscription_by_stripe_id

    payload = request.get_data(as_text=True)
    sig_header = request.headers.get("Stripe-Signature", "")

    event, error = verify_webhook(payload, sig_header)
    if error:
        print(f"[Stripe Webhook] Error: {error}")
        return jsonify({"error": error}), 400

    event_type = event.get("type")
    print(f"[Stripe Webhook] Received: {event_type}")

    if event_type == "checkout.session.completed":
        session_data = event["data"]["object"]
        handle_checkout_completed(
            session_data,
            lambda uid, tier, cid, sid: update_user_subscription(uid, tier, cid, sid)
        )

    elif event_type in ("customer.subscription.deleted", "customer.subscription.canceled"):
        sub_data = event["data"]["object"]
        handle_subscription_deleted(
            sub_data,
            lambda sid: downgrade_user_subscription_by_stripe_id(sid)
        )

    elif event_type == "customer.subscription.updated":
        sub_data = event["data"]["object"]
        # Handle plan changes
        metadata = sub_data.get("metadata", {})
        user_id = metadata.get("user_id")
        tier = metadata.get("tier")
        if user_id and tier:
            try:
                update_user_subscription(int(user_id), tier)
                print(f"[Stripe] Updated subscription for user {user_id} to {tier}")
            except Exception as e:
                print(f"[Stripe] Error updating subscription: {e}")

    return jsonify({"status": "ok"}), 200


# ═══════════════════════════════════════════════════════════════════════════
#  PROMO CODE REDEMPTION ROUTES
# ═══════════════════════════════════════════════════════════════════════════

@app.route("/redeem-promo", methods=["POST"])
def redeem_promo():
    """Redeem a promo code to upgrade subscription tier."""
    if "user_id" not in session:
        return redirect(url_for("login"))

    code = request.form.get("promo_code", "").strip()
    if not code:
        flash("Please enter a promo code.", "error")
        # Redirect back to wherever they came from
        role = session.get("role", "agent")
        if role == "lender":
            return redirect(url_for("lender_subscription"))
        return redirect(url_for("agent_subscription"))

    from database import redeem_promo_code
    success, message, tier = redeem_promo_code(code, session["user_id"])

    if success:
        flash(message, "success")
        # Update session with new tier
        session["subscription_tier"] = tier
    else:
        flash(message, "error")

    role = session.get("role", "agent")
    if role == "lender":
        return redirect(url_for("lender_subscription"))
    return redirect(url_for("agent_subscription"))


# ═══════════════════════════════════════════════════════════════════════════
#  END STRIPE SUBSCRIPTION ROUTES
# ═══════════════════════════════════════════════════════════════════════════


# -------------------------------------------------
# AGENT SETTINGS ROUTES
# -------------------------------------------------
@app.route("/settings/invite-hero", methods=["POST"])
def settings_invite_hero():
    """Agents/lenders choose the banner photo their clients see on their invite page."""
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "lender"):
        return redirect(url_for("login"))
    role = user["role"]
    back = url_for("agent_settings_profile" if role == "agent" else "lender_settings_profile")
    if request.form.get("action") == "remove":
        new_value = ""
    else:
        f = request.files.get("hero_image")
        if not f or not f.filename:
            flash("Choose a photo first.", "error")
            return redirect(back)
        try:
            import base64, io
            from PIL import Image, ImageOps
            img = ImageOps.exif_transpose(Image.open(f.stream)).convert("RGB")
            if img.width < 600:
                flash("That photo is too small. Please use one at least 1200 pixels wide.", "error")
                return redirect(back)
            if img.width > 1600:
                img = img.resize((1600, round(img.height * 1600 / img.width)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=80, optimize=True)
            new_value = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
        except Exception:
            flash("We couldn't read that file. Please upload a JPG or PNG photo.", "error")
            return redirect(back)
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM user_profiles WHERE user_id = ?", (user["id"],))
    if cur.fetchone():
        cur.execute("UPDATE user_profiles SET hero_image = ? WHERE user_id = ?", (new_value, user["id"]))
    else:
        cur.execute("INSERT INTO user_profiles (user_id, role, hero_image) VALUES (?, ?, ?)",
                    (user["id"], role, new_value))
    conn.commit()
    conn.close()
    flash("Invite photo removed." if new_value == "" else "Invite photo saved. New clients will see it on your invite link.", "success")
    return redirect(back)


# -------------------------------------------------
# LENDER ROUTES
# -------------------------------------------------


# -------------------------------------------------
# LENDER MARKETING HUB ROUTES
# -------------------------------------------------


# -------------------------------------------------
# HOMEOWNER ROUTES (Missing)
# -------------------------------------------------


# ── NEXT HOME HUB ──────────────────────────────────────────────────────────


# ---------------- HOMEBOT WEBHOOK ----------------


# ============================================================================
# ADMIN RBAC ROUTES
# ============================================================================

def _admin_session_user():
    """The real, logged-in site admin (even while viewing as another user), else None."""
    from rbac import is_site_admin
    imp = session.get("impersonation") or {}
    real_id = imp.get("admin_id") or session.get("user_id")
    if not real_id or not is_site_admin(real_id):
        return None
    row = get_user_by_id(int(real_id))
    if not row:
        return None
    u = dict(row)
    return {"id": u["id"], "name": u.get("name"), "role": u.get("role"), "email": u.get("email")}


# -------------------------------------------------
# AI CONCIERGE ROUTES
# -------------------------------------------------

# Public-facing homeowner concierge chat
@app.route("/concierge/<agent_token>")
def concierge_landing(agent_token):
    """
    Public landing page for homeowner AI concierge.
    Branded per agent, luxury feel.
    """
    # Get agent from token (could be username, custom slug, or ID)
    conn = get_connection()
    cur = conn.cursor()
    
    # Try to find agent by token (for now, use agent ID)
    try:
        agent_id = int(agent_token)
        cur.execute("SELECT id, name FROM users WHERE id = ? AND role = 'agent'", (agent_id,))
        agent = row_to_dict(cur.fetchone())
    except Exception:
        agent = None
    
    if not agent:
        conn.close()
        abort(404, "Concierge not found")
    
    # Get concierge settings
    cur.execute("SELECT * FROM concierge_settings WHERE agent_id = ?", (agent['id'],))
    settings = row_to_dict(cur.fetchone())
    conn.close()
    
    # Use defaults if no settings
    if not settings:
        settings = {
            'branding_name': 'Your Home Concierge',
            'branding_tagline': 'Answers, guidance, and trusted local connections',
            'primary_color': '#1a1a1a',
            'secondary_color': '#f5f5f5',
            'welcome_message': 'How can I help you with your home today?'
        }
    
    return render_template(
        'concierge/landing.html',
        agent=agent,
        settings=settings,
        agent_token=agent_token
    )


@app.route("/concierge/<agent_token>/chat", methods=["POST"])
def concierge_chat(agent_token):
    """
    AI chat endpoint - processes homeowner messages.
    Returns JSON with AI response.
    """
    from ai_concierge import ConciergeAI
    
    # Get agent
    try:
        agent_id = int(agent_token)
    except Exception:
        return jsonify({"error": "Invalid agent"}), 404
    
    # Get message and session
    data = request.get_json(silent=True) or {}
    user_message = str(data.get('message', '')).strip()[:1000]  # cap length: every message costs money
    session_id = str(data.get('session_id') or '')[:64] or None

    if not user_message:
        return jsonify({"error": "Message required"}), 400

    # Per-agent daily ceiling so a guessed/abused link can't run up the OpenAI bill
    if _rate_limited(f"concierge:agent:{agent_id}", 300, 86400):
        return jsonify({"response": "This assistant is very busy right now. Please contact your agent directly.",
                        "session_id": session_id or "", "metadata": {}}), 200
    
    if not session_id:
        # Generate new session ID
        import uuid
        session_id = str(uuid.uuid4())
    
    # Get visitor IP
    visitor_ip = request.remote_addr
    
    # Process with AI
    ai = ConciergeAI(agent_id)
    response_text, metadata = ai.chat(session_id, user_message, visitor_ip)
    
    return jsonify({
        "response": response_text,
        "session_id": session_id,
        "metadata": metadata
    })


# Agent dashboard for AI concierge


# ─────────────────────────────────────────────────────────────────────────────
# PLATFORM-WIDE AI ENDPOINTS
# All AI features across the platform route through here.
# Powered by ai_platform.py — one module, one key, one model standard.
# ─────────────────────────────────────────────────────────────────────────────


# ─────────────────────────────────────────────────────────────────────────────
# LEAD INTAKE WEBHOOK
# Kayleigh can POST leads here from her website contact form or Zapier.
# URL: POST /api/lead-intake/<agent_token>
# Params (JSON or form): name, email, phone, source, message
# ─────────────────────────────────────────────────────────────────────────────


# =============================================================
# CLIENT CONTESTS (Bracket Contests — NFL Playoffs & NCAA)
# =============================================================

def _get_db_contest(contest_id, agent_user_id):
    """Fetch a single contest, verifying ownership."""
    conn = get_db_connection()
    row = conn.execute(
        "SELECT * FROM agent_contests WHERE id=? AND agent_user_id=?",
        (contest_id, agent_user_id)
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def _list_db_contests(agent_user_id):
    conn = get_db_connection()
    rows = conn.execute(
        "SELECT * FROM agent_contests WHERE agent_user_id=? ORDER BY season_year DESC, contest_type",
        (agent_user_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def _send_contest_invites_for(contest, agent_user):
    """Send bracket contest invite emails to all CRM contacts with emails. Returns count sent."""
    from database import list_agent_contacts
    import datetime
    if not _email_ready():
        return 0
    contacts = list_agent_contacts(agent_user["id"])
    type_label = "NFL Playoffs" if contest["contest_type"] == "nfl_playoffs" else "NCAA March Madness"
    type_emoji = "" if contest["contest_type"] == "nfl_playoffs" else ""
    agent_name = agent_user.get("name", "Your Agent")
    count = 0
    for c in contacts:
        email = c.get("email", "").strip()
        if not email:
            continue
        client_name = c.get("name", "Friend").split()[0]
        cbs_line = ""
        if contest.get("cbs_group_link"):
            cbs_line = f"\n Join the group here: {contest['cbs_group_link']}"
        if contest.get("cbs_group_code"):
            cbs_line += f"\n Group Code: {contest['cbs_group_code']}"
        deadline_line = ""
        if contest.get("deadline_date"):
            deadline_line = f"\n⏰ Bracket deadline: {contest['deadline_date']}"
        subject = f"{type_emoji} {contest['contest_name']}: You're Invited!"
        body = f"""Hi {client_name}!

It's that time of year again, and I'm doing something fun for my clients!

{type_emoji} {contest['contest_name']}

I'm hosting a FREE bracket contest for my clients this year, and I'd love for you to join!

 Prize: {contest.get('prize_description', '$25 Amazon Gift Card')} for the winner{cbs_line}{deadline_line}

How to join:
1. Download the CBS Sports app (free on iPhone or Android)
2. Go to "Bracket Games" and search for my group
3. Fill out your bracket. No sports knowledge required, just have fun!

{contest.get('notes', '').strip() + chr(10) if contest.get('notes') else ''}This is just my small way of having some fun with the people I care about. Thanks for being such a great client. I'm grateful for you!

Good luck! 

{agent_name}
"""
        if send_reminder_email(email, subject, body, **pro_sender(agent_user["id"])):
            count += 1
    # Mark as sent
    conn = get_db_connection()
    conn.execute(
        "UPDATE agent_contests SET invite_sent_at=? WHERE id=?",
        (datetime.now().isoformat(), contest["id"])
    )
    conn.commit()
    conn.close()
    return count


def send_contest_invites_scheduled():
    """Scheduler job: daily check, send invites for any contest whose invite_date is today."""
    import datetime
    today = datetime.date.today().isoformat()
    conn = get_db_connection()
    due = conn.execute(
        "SELECT * FROM agent_contests WHERE invite_date=? AND (invite_sent_at IS NULL OR invite_sent_at='')",
        (today,)
    ).fetchall()
    conn.close()
    for row in due:
        contest = dict(row)
        # Get the agent user
        agent_conn = get_db_connection()
        agent_row = agent_conn.execute("SELECT * FROM users WHERE id=?", (contest["agent_user_id"],)).fetchone()
        agent_conn.close()
        if agent_row:
            agent_user = dict(agent_row)
            count = _send_contest_invites_for(contest, agent_user)
            print(f"[CONTESTS] Sent {count} invites for contest '{contest['contest_name']}' (agent {agent_user.get('name')})")


# ============================================================
# AGENT FINANCIALS HUB  (Realtyzam-equivalent)
# ============================================================


# ============================================================
# LENDER FINANCIALS HUB
# ============================================================


# ---------------- DEVELOPMENT SERVER ----------------
import pies as _pies
_pies.init_app(app, get_current_user, _bg, send_reminder_email)
import planner as _planner
_planner.init_app(app, get_current_user)
import homeowner_home as _homeowner_home
_homeowner_home.init_app(app, get_current_user)
import client_values as _client_values
_client_values.init_app(app, get_current_user)
import refi_alerts as _refi_alerts
_refi_alerts.init_app(app, get_current_user)
import care_alerts as _care_alerts
_care_alerts.init_app(app, get_current_user, globals())
import followups as _followups
_followups.init_app(app, get_current_user)
import events as _events
_events.init_app(app, get_current_user)
import email_check as _email_check
_email_check.init_app(app, globals())

# ---------------- LENDER ROUTES ----------------
# The lender pages live in lender_routes.py. They run in this module's namespace, so they behave exactly as before.
import lender_routes as _lender_routes
_lender_routes.install(globals())

# ---------------- AGENT ROUTES ----------------
# The agent pages live in agent_routes.py (same arrangement as the lender pages above).
import agent_routes as _agent_routes
_agent_routes.install(globals())

# ---------------- HOMEOWNER ROUTES ----------------
import homeowner_routes as _homeowner_routes
_homeowner_routes.install(globals())

# ---------------- ADMIN ROUTES ----------------
import admin_routes as _admin_routes
_admin_routes.install(globals())

# ---------------- API ROUTES ----------------
import api_routes as _api_routes
_api_routes.install(globals())
import booking as _booking
_booking.init_app(app, get_current_user, _bg, send_reminder_email)
import tc as _tc
_tc.init_app(app, get_current_user, _bg, send_reminder_email, get_transaction_detail,
             lambda tx_id, kind, text, uid: __import__("transaction_helpers").log_timeline_event(tx_id, kind, text, uid))


if __name__ == "__main__":
    # Only runs when executing directly with Python (not with gunicorn)
    app.run(
        host="127.0.0.1",
        port=5000,
        debug=not _IS_PRODUCTION,
        use_reloader=False,  # Disable reloader on Windows to avoid import issues
    )
