"""Email signature: each agent and lender writes one signature, and every email sent on their behalf ends with it."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

bp = Blueprint("email_signature", __name__)
_H = {}
MAX_LEN = 600


def _db():
    from database import get_connection
    return get_connection()


# Free email providers cannot be used as a "from" address by a sending service: they tell receiving mailboxes to reject
# mail that did not come from their own servers, so it would land in spam. People on these keep the "Name via ..." sender.
FREE_MAIL = {"gmail.com", "googlemail.com", "yahoo.com", "ymail.com", "outlook.com", "hotmail.com", "live.com", "msn.com", "icloud.com",
             "me.com", "mac.com", "aol.com", "comcast.net", "att.net", "sbcglobal.net", "verizon.net", "protonmail.com", "proton.me",
             "gmx.com", "mail.com", "cox.net", "earthlink.net", "charter.net", "bellsouth.net"}


def ensure_tables():
    conn = _db()
    conn.execute("CREATE TABLE IF NOT EXISTS email_signatures (user_id INTEGER PRIMARY KEY, signature TEXT NOT NULL DEFAULT '')")
    conn.execute("CREATE TABLE IF NOT EXISTS own_senders (user_id INTEGER PRIMARY KEY, email TEXT NOT NULL, verified INTEGER NOT NULL DEFAULT 0)")
    conn.commit()
    conn.close()


def get_signature(user_id):
    """The saved signature for this user, or "" if they have not written one."""
    if not user_id:
        return ""
    try:
        conn = _db()
        try:
            row = conn.execute("SELECT signature FROM email_signatures WHERE user_id = ?", (user_id,)).fetchone()
        finally:
            conn.close()
    except Exception:
        return ""
    return (row["signature"] if row else "") or ""


def _brevo(method, path, payload=None, timeout=10):
    """Call Brevo's API. Returns (status, json). Network trouble returns (0, {})."""
    import json
    import os
    import urllib.error
    import urllib.request
    key = os.environ.get("BREVO_API_KEY")
    if not key:
        return 0, {}
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request("https://api.brevo.com/v3" + path, data=data, method=method,
                                 headers={"api-key": key, "Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8") or "{}"
            return r.status, json.loads(raw)
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}
    except Exception:
        return 0, {}


def get_own_sender(user_id):
    """The person's own address, only if it has been confirmed and Brevo is the email service. Otherwise ""."""
    import os
    if not user_id or not os.environ.get("BREVO_API_KEY"):
        return ""
    try:
        conn = _db()
        try:
            row = conn.execute("SELECT email, verified FROM own_senders WHERE user_id = ?", (user_id,)).fetchone()
        finally:
            conn.close()
    except Exception:
        return ""
    return row["email"] if row and row["verified"] else ""


def _own_row(user_id):
    conn = _db()
    try:
        r = conn.execute("SELECT email, verified FROM own_senders WHERE user_id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    return dict(r) if r else None


def _valid_email(v):
    import re
    return bool(re.fullmatch(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}", v or ""))


def refresh_status(user_id):
    """Ask Brevo whether this person's address is confirmed, and remember the answer. Returns the row, or None."""
    row = _own_row(user_id)
    if not row:
        return None
    status, data = _brevo("GET", "/senders")
    if status == 200:
        active = any((s.get("email") or "").lower() == row["email"].lower() and s.get("active") for s in data.get("senders", []))
        if active != bool(row["verified"]):
            conn = _db()
            try:
                conn.execute("UPDATE own_senders SET verified = ? WHERE user_id = ?", (1 if active else 0, user_id))
                conn.commit()
            finally:
                conn.close()
            row["verified"] = 1 if active else 0
    return row


def suggested(user):
    """A starting signature built from what is already in their profile."""
    conn = _db()
    try:
        p = conn.execute("SELECT brokerage_name, phone, website_url FROM user_profiles WHERE user_id = ?", (user["id"],)).fetchone()
    finally:
        conn.close()
    p = dict(p) if p else {}
    lines = [(user.get("name") or "").strip(), (p.get("brokerage_name") or "").strip(),
             (p.get("phone") or "").strip(), (p.get("website_url") or "").strip()]
    return "\n".join(l for l in lines if l)


def with_signature(body, signature, name=""):
    """Add the signature under an email body. If the body already ends with just the person's name or first name as a
    sign-off, that line is replaced so the name does not appear twice."""
    sig = (signature or "").strip()
    if not sig:
        return body
    lines = (body or "").rstrip().split("\n")
    last = lines[-1].strip().rstrip(",").lower() if lines else ""
    first = (name or "").strip().split(" ")[0].lower() if name else ""
    if last and last in {(name or "").strip().lower(), first} and last:
        lines.pop()
    return "\n".join(lines).rstrip() + "\n\n" + sig


def html_with_signature(html, signature):
    sig = (signature or "").strip()
    if not sig or not html:
        return html
    from markupsafe import escape
    block = '<p style="margin-top:1.2em;">' + str(escape(sig)).replace("\n", "<br>") + "</p>"
    return html.replace("</body>", block + "</body>", 1) if "</body>" in html else html + block


def _pro():
    u = _H["get_current_user"]()
    return u if u and u.get("role") in ("agent", "lender") else None


@bp.route("/email-signature", methods=["GET", "POST"])
def signature_page():
    u = _pro()
    if not u:
        return redirect(url_for("login", role="agent"))
    if request.method == "POST":
        sig = "\n".join(l.rstrip() for l in (request.form.get("signature") or "").replace("\r", "").split("\n")).strip()[:MAX_LEN]
        conn = _db()
        try:
            conn.execute("INSERT INTO email_signatures (user_id, signature) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET signature = excluded.signature",
                         (u["id"], sig))
            conn.commit()
        finally:
            conn.close()
        flash("Saved. This now goes at the bottom of the emails you send from here." if sig else "Signature cleared.", "success")
        return redirect(url_for("email_signature.signature_page"))
    import os
    saved = get_signature(u["id"])
    own = refresh_status(u["id"]) if os.environ.get("BREVO_API_KEY") else _own_row(u["id"])
    return render_template(f"{u['role']}/email_signature.html", saved=saved, suggestion=suggested(u), max_len=MAX_LEN, own=own,
                           brevo_on=bool(os.environ.get("BREVO_API_KEY")), account_email=u.get("email") or "")


@bp.route("/email-signature/sender", methods=["POST"])
def sender_start():
    """Ask Brevo to confirm one of the person's own addresses. Brevo emails that address a confirmation link."""
    u = _pro()
    if not u:
        return redirect(url_for("login", role="agent"))
    addr = (request.form.get("email") or "").strip().lower()[:200]
    back = redirect(url_for("email_signature.signature_page") + "#sender")
    if not _valid_email(addr):
        flash("That email address does not look right.", "error")
        return back
    if addr.split("@")[-1] in FREE_MAIL:
        flash("Gmail, Yahoo, Outlook, iCloud and other free addresses cannot be used this way, because those companies reject mail sent for you by "
              "another service and it would land in spam. Your emails will keep showing your name and replies will still go to you. "
              "If you have an email at your own business or brokerage domain, use that one.", "error")
        return back
    status, data = _brevo("POST", "/senders", {"name": (u.get("name") or addr)[:80], "email": addr})
    if status not in (200, 201, 400, 409):
        flash("We could not reach the email service just now. Please try again in a minute.", "error")
        return back
    if status == 400 and "exist" not in str(data).lower():
        flash("The email service did not accept that address. Check it and try again.", "error")
        return back
    conn = _db()
    try:
        conn.execute("INSERT INTO own_senders (user_id, email, verified) VALUES (?,?,0) ON CONFLICT(user_id) DO UPDATE SET email = excluded.email, verified = 0",
                     (u["id"], addr))
        conn.commit()
    finally:
        conn.close()
    row = refresh_status(u["id"])
    if row and row["verified"]:
        flash(f"{addr} is confirmed. Your emails now come from it.", "success")
    else:
        flash(f"We sent a confirmation email to {addr}. Open it and tap the link, then come back here. Until then your emails keep going out the usual way.", "success")
    return back


@bp.route("/email-signature/sender/remove", methods=["POST"])
def sender_remove():
    u = _pro()
    if not u:
        return redirect(url_for("login", role="agent"))
    conn = _db()
    try:
        conn.execute("DELETE FROM own_senders WHERE user_id = ?", (u["id"],))
        conn.commit()
    finally:
        conn.close()
    flash("Done. Your emails go out the usual way again, with your name and replies coming to you.", "success")
    return redirect(url_for("email_signature.signature_page") + "#sender")


def init_app(app, get_current_user):
    _H.update(get_current_user=get_current_user)
    ensure_tables()
    app.register_blueprint(bp)
