"""Admin email check: which email service is active, whether the sender address is verified in Brevo, and a test email
sent to the signed-in admin's own address, with the service's real answer if it fails. No keys are ever shown."""
import json
import os
import urllib.error
import urllib.request

from flask import Blueprint, flash, redirect, render_template, url_for

bp = Blueprint("email_check", __name__)
_H = {}


def _get_json(url, api_key, timeout=10):
    req = urllib.request.Request(url, headers={"api-key": api_key, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def provider():
    if os.environ.get("RESEND_API_KEY"):
        return "Resend"
    if os.environ.get("BREVO_API_KEY"):
        return "Brevo"
    if os.environ.get("EMAIL_USER") and os.environ.get("EMAIL_PASS"):
        return "SMTP"
    return None


def sender_check(addr):
    """Is the From address allowed to send in Brevo? Returns (state, message): ok, warn or bad."""
    key = os.environ.get("BREVO_API_KEY")
    if not key:
        return "warn", "Sender verification is only checked for Brevo."
    if not addr:
        return "bad", "MAIL_FROM is not set. Add it in Railway (for example hello@itsyourlifeyourhome.com)."
    domain = addr.split("@")[-1].lower()
    try:
        senders = _get_json("https://api.brevo.com/v3/senders", key).get("senders", [])
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            return "bad", "Brevo rejected the API key. Create a new API key in Brevo and update BREVO_API_KEY."
        return "warn", f"Could not read your Brevo senders (error {e.code})."
    except Exception as e:
        return "warn", f"Could not reach Brevo to check ({type(e).__name__})."
    for s in senders:
        if (s.get("email") or "").lower() == addr.lower():
            if s.get("active"):
                return "ok", f"{addr} is a verified sender in Brevo."
            return "bad", f"{addr} is in Brevo but not verified yet. Open the verification email Brevo sent, or re-send it in Brevo under Senders."
    try:
        for d in _get_json("https://api.brevo.com/v3/senders/domains", key).get("domains", []):
            if (d.get("domain_name") or "").lower() == domain and d.get("authenticated"):
                return "ok", f"{domain} is an authenticated domain in Brevo, so {addr} can send."
    except Exception:
        pass
    return "bad", f"{addr} is not a verified sender in Brevo. Add it under Senders, Domains and Dedicated IPs, then click the link Brevo emails you."


def status():
    from email.utils import parseaddr
    prov = provider()
    addr = parseaddr(os.environ.get("MAIL_FROM") or os.environ.get("EMAIL_USER") or "")[1]
    out = dict(provider=prov, mail_from=addr, key_set=bool(prov), reply_to=os.environ.get("MAIL_REPLY_TO") or "")
    out["sender_state"], out["sender_msg"] = sender_check(addr) if prov == "Brevo" else (
        ("warn", "Sender verification is only checked for Brevo.") if prov else ("bad", "No email service is set up. Add BREVO_API_KEY and MAIL_FROM in Railway."))
    return out


def _admin():
    return _H["ns"]["_admin_session_user"]()


@bp.route("/admin/email-check")
def email_check_page():
    u = _admin()
    if not u:
        flash("That area is just for site administrators.", "error")
        return redirect(url_for("login", role="agent"))
    return render_template("admin/email_check.html", st=status(), me=u.get("email") or "")


@bp.route("/admin/email-check/send", methods=["POST"])
def email_check_send():
    u = _admin()
    if not u:
        flash("That area is just for site administrators.", "error")
        return redirect(url_for("login", role="agent"))
    ns = _H["ns"]
    to = u.get("email")
    if not to:
        flash("Your account has no email address to test with.", "error")
        return redirect(url_for("email_check.email_check_page"))
    ns["_EMAIL_LAST"].update(ok=None, detail="")
    ok = ns["send_reminder_email"](
        to, "Your Life, Your Home: email test",
        "This is a test from your Email Check page. If you can read this, email sending works.\n\nYour Life, Your Home")
    if ok:
        flash(f"Sent. Check the inbox for {to} (and the spam folder the first time).", "success")
    else:
        detail = ns["_EMAIL_LAST"].get("detail") or "The email service did not accept the message."
        flash(f"The test email did not send. {detail}", "error")
    return redirect(url_for("email_check.email_check_page"))


def init_app(app, ns):
    _H.update(ns=ns)
    app.register_blueprint(bp)
