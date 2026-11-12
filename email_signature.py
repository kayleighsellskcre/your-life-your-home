"""Email signature: each agent and lender writes one signature, and every email sent on their behalf ends with it."""
from flask import Blueprint, flash, redirect, render_template, request, url_for

bp = Blueprint("email_signature", __name__)
_H = {}
MAX_LEN = 600


def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    conn.execute("CREATE TABLE IF NOT EXISTS email_signatures (user_id INTEGER PRIMARY KEY, signature TEXT NOT NULL DEFAULT '')")
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
    saved = get_signature(u["id"])
    return render_template(f"{u['role']}/email_signature.html", saved=saved, suggestion=suggested(u), max_len=MAX_LEN)


def init_app(app, get_current_user):
    _H.update(get_current_user=get_current_user)
    ensure_tables()
    app.register_blueprint(bp)
