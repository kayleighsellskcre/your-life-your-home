"""'Discover Your Home's Worth': a simple on-site address form. The request goes to the homeowner's own agent
(a signed-in homeowner's agent, or the agent whose personal link brought them here), or to the default agent."""
import re
from flask import render_template, request, session, redirect, url_for, flash

_ns = {}


def _db():
    from database import get_connection
    return get_connection()


def _setup():
    conn = _db()
    conn.execute("""CREATE TABLE IF NOT EXISTS home_value_requests (
        id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER, user_id INTEGER, name TEXT, email TEXT, phone TEXT,
        address TEXT, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()


def _clean(v, n):
    return re.sub(r"[\r\n]+", " ", (v or "").strip())[:n]


def _agent_for(ref):
    """Returns the agent id who should receive the request."""
    from database import get_user_by_id, get_referral_link_by_token, get_or_create_default_agent
    uid = session.get("user_id")
    if uid:
        u = get_user_by_id(uid)
        u = dict(u) if u else {}
        if u.get("role") == "agent":
            return u["id"]
        if u.get("agent_id"):
            return u["agent_id"]
    if ref:
        try:
            link = get_referral_link_by_token(ref)
            if link and link.get("agent_id"):
                return link["agent_id"]
        except Exception:
            pass
    return get_or_create_default_agent()


def home_value_request():
    ref = (request.values.get("ref") or "").strip()[:80]
    uid = session.get("user_id")
    prefill = {"name": "", "email": ""}
    if uid:
        from database import get_user_by_id
        u = get_user_by_id(uid)
        u = dict(u) if u else {}
        prefill = {"name": u.get("name") or "", "email": u.get("email") or ""}
    if request.method == "POST":
        f = {k: _clean(request.form.get(k), n) for k, n in (("name", 120), ("email", 200), ("phone", 40), ("address", 250), ("note", 1000))}
        if not f["address"] or not f["name"] or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", f["email"]):
            flash("Please add the home address, your name and a valid email so we can reply.", "error")
            return render_template("main/home_value.html", f=f, ref=ref), 400
        agent_id = _agent_for(ref)
        conn = _db()
        conn.execute("INSERT INTO home_value_requests (agent_id, user_id, name, email, phone, address, note) VALUES (?,?,?,?,?,?,?)",
                     (agent_id, uid, f["name"], f["email"], f["phone"], f["address"], f["note"]))
        conn.commit()
        conn.close()
        try:
            from database import get_user_by_id
            agent = dict(get_user_by_id(agent_id) or {})
            if agent.get("email"):
                body = ("Someone asked what their home is worth.\n\n"
                        f"Name: {f['name']}\nEmail: {f['email']}\nPhone: {f['phone'] or 'not given'}\n"
                        f"Home address: {f['address']}\n" + (f"Note: {f['note']}\n" if f["note"] else "") +
                        "\nReply to them directly to share a value.")
                _ns["_bg"](_ns["send_reminder_email"], agent["email"], "Home value request: " + f["address"], body, reply_to=f["email"])
        except Exception as exc:
            print(f"home value email failed: {exc}")
        return render_template("main/home_value.html", done=True, f=f, ref=ref)
    return render_template("main/home_value.html", f=prefill | {"phone": "", "address": "", "note": ""}, ref=ref)


def init_app(app, ns):
    _ns.update({"_bg": ns["_bg"], "send_reminder_email": ns["send_reminder_email"]})
    _setup()
    app.add_url_rule("/home-value", endpoint="home_value_request", view_func=home_value_request, methods=["GET", "POST"])
