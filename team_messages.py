"""Messages between a homeowner and their agent or lender, plus numbers a homeowner chooses to share with their lender.

A conversation is always between one homeowner and one connected professional. The homeowner decides exactly which numbers
go into a shared scenario; only those numbers are stored, and only that lender can see them."""
import json
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

bp = Blueprint("team", __name__)
_H = {}
MAX_BODY = 2000
MAX_PER_HOUR = 30
SCENARIO_FIELDS = [
    ("home_value", "What my home is worth"),
    ("loan_balance", "What I still owe"),
    ("rate", "My interest rate (%)"),
    ("payment", "My monthly payment"),
]
KINDS = {"payment": "Payment scenario", "refinance": "Refinance scenario"}


def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    conn.execute("""CREATE TABLE IF NOT EXISTS team_messages (
        id INTEGER PRIMARY KEY AUTOINCREMENT, homeowner_id INTEGER NOT NULL, pro_id INTEGER NOT NULL, sender_id INTEGER NOT NULL,
        body TEXT NOT NULL DEFAULT '', scenario_id INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, read_at TEXT)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_team_messages_pair ON team_messages (homeowner_id, pro_id)")
    conn.execute("""CREATE TABLE IF NOT EXISTS shared_scenarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT, homeowner_id INTEGER NOT NULL, lender_id INTEGER NOT NULL, kind TEXT NOT NULL,
        data TEXT NOT NULL DEFAULT '{}', note TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP, seen_at TEXT)""")
    conn.commit()
    conn.close()


# ───────────────────────── who is connected to whom ─────────────────────────
def pros_for(homeowner_id):
    """{'agent': {...}, 'lender': {...}} for the homeowner, whichever they have."""
    from database import get_homeowner_professionals, get_user_by_id, get_user_profile
    out = {}
    try:
        rows = [dict(r) for r in get_homeowner_professionals(homeowner_id)]
    except Exception:
        rows = []
    for r in rows:
        role = (r.get("professional_role") or r.get("professional_type") or "").lower()
        if role in ("agent", "lender") and role not in out:
            out[role] = {"id": r.get("professional_id") or r.get("user_id"), "name": r.get("name") or "", "email": r.get("email") or "",
                         "phone": r.get("phone") or "", "brokerage": r.get("brokerage_name") or r.get("team_name") or "",
                         "photo": r.get("professional_photo") or "", "role": role}
    if len(out) < 2:   # older accounts only have the id on the user row
        u = get_user_by_id(homeowner_id)
        u = dict(u) if u else {}
        for role, col in (("agent", "agent_id"), ("lender", "lender_id")):
            pid = u.get(col)
            if pid and role not in out:
                pu = get_user_by_id(pid)
                if pu:
                    pu = dict(pu)
                    pp = get_user_profile(pid)
                    pp = dict(pp) if pp else {}
                    out[role] = {"id": pid, "name": pu.get("name") or "", "email": pu.get("email") or "", "phone": pp.get("phone") or "",
                                 "brokerage": pp.get("brokerage_name") or pp.get("team_name") or "", "photo": pp.get("professional_photo") or "", "role": role}
    return out


def connected(homeowner_id, pro_id):
    return any(p["id"] == pro_id for p in pros_for(homeowner_id).values())


def client_ids(pro):
    """Homeowners connected to this agent or lender."""
    from database import get_agent_clients, get_lender_clients
    rows = get_agent_clients(pro["id"]) if pro["role"] == "agent" else get_lender_clients(pro["id"])
    return [dict(r) for r in rows]


# ───────────────────────── small helpers ─────────────────────────
def when_text(ts):
    try:
        d = datetime.strptime((ts or "")[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=ZoneInfo("UTC")).astimezone(ZoneInfo("America/Chicago"))
    except ValueError:
        return ""
    return f"{d.strftime('%b')} {d.day}, {d.strftime('%I:%M %p').lstrip('0')}"


def _num(v):
    try:
        return float(str(v).replace("$", "").replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def money(v, field):
    if field == "rate":
        return f"{v:g}%"
    return f"${v:,.0f}"


def unread_count(user):
    if not user or user.get("role") not in ("homeowner", "agent", "lender"):
        return 0
    col = "homeowner_id" if user["role"] == "homeowner" else "pro_id"
    try:
        conn = _db()
        try:
            return conn.execute(f"SELECT COUNT(*) FROM team_messages WHERE {col} = ? AND sender_id != ? AND read_at IS NULL", (user["id"], user["id"])).fetchone()[0]
        finally:
            conn.close()
    except Exception:
        return 0


def _scenario_view(row):
    d = json.loads(row["data"] or "{}")
    fields = [(label, money(d[k], k)) for k, label in SCENARIO_FIELDS if k in d]
    return {"id": row["id"], "kind": row["kind"], "kind_label": KINDS.get(row["kind"], "Scenario"), "fields": fields, "note": row["note"] or "",
            "when": when_text(row["created_at"])}


def _thread(conn, homeowner_id, pro_id, viewer_id):
    rows = [dict(r) for r in conn.execute("SELECT * FROM team_messages WHERE homeowner_id = ? AND pro_id = ? ORDER BY id", (homeowner_id, pro_id)).fetchall()]
    out = []
    for m in rows:
        m["when"] = when_text(m["created_at"])
        m["mine"] = m["sender_id"] == viewer_id
        m["scenario"] = None
        if m["scenario_id"]:
            s = conn.execute("SELECT * FROM shared_scenarios WHERE id = ?", (m["scenario_id"],)).fetchone()
            m["scenario"] = _scenario_view(s) if s else None
        out.append(m)
    conn.execute("UPDATE team_messages SET read_at = CURRENT_TIMESTAMP WHERE homeowner_id = ? AND pro_id = ? AND sender_id != ? AND read_at IS NULL",
                 (homeowner_id, pro_id, viewer_id))
    conn.commit()
    return out


def _too_many(conn, sender_id):
    n = conn.execute("SELECT COUNT(*) FROM team_messages WHERE sender_id = ? AND created_at >= datetime('now','-1 hour')", (sender_id,)).fetchone()[0]
    return n >= MAX_PER_HOUR


def _notify(sender, recipient_id, recipient_role, text, link_path):
    """A short email to the other person so they know to look. The page itself is where the conversation happens."""
    ns = _H["ns"]
    try:
        from database import get_user_by_id
        r = get_user_by_id(recipient_id)
        r = dict(r) if r else {}
        if not r.get("email"):
            return
        link = ns["_site_url"]().rstrip("/") + link_path
        first = (r.get("name") or "there").split()[0]
        body = f"Hi {first},\n\n{sender.get('name') or 'Someone'} sent you a message on Your Life, Your Home.\n\n{text}\n\nOpen it and reply here: {link}\n"
        kw = ns["pro_sender"](sender["id"]) if sender.get("role") in ("agent", "lender") else {}
        kw.pop("signature", None)
        ns["_bg"](ns["send_reminder_email"], r["email"], f"New message from {sender.get('name') or 'your home team'}", body, **kw)
    except Exception as e:
        print(f"[WARNING] message notice skipped: {e}")


def _save(conn, homeowner_id, pro_id, sender_id, body, scenario_id=None):
    conn.execute("INSERT INTO team_messages (homeowner_id, pro_id, sender_id, body, scenario_id) VALUES (?,?,?,?,?)",
                 (homeowner_id, pro_id, sender_id, body, scenario_id))
    conn.commit()


def _user(role=None):
    u = _H["get_current_user"]()
    if not u:
        return None
    if role == "pro":
        return u if u.get("role") in ("agent", "lender") else None
    return u if (role is None or u.get("role") == role) else None


def _login():
    flash("Please sign in first.", "error")
    return redirect(url_for("login"))


# ───────────────────────── homeowner: My Team ─────────────────────────
@bp.route("/homeowner/team")
def my_team():
    u = _user("homeowner")
    if not u:
        return _login()
    team = pros_for(u["id"])
    conn = _db()
    try:
        for p in team.values():
            p["unread"] = conn.execute("SELECT COUNT(*) FROM team_messages WHERE homeowner_id=? AND pro_id=? AND sender_id!=? AND read_at IS NULL",
                                       (u["id"], p["id"], u["id"])).fetchone()[0]
    finally:
        conn.close()
    return render_template("homeowner/team.html", team=team)


@bp.route("/homeowner/team/<int:pro_id>", methods=["GET", "POST"])
def home_thread(pro_id):
    u = _user("homeowner")
    if not u:
        return _login()
    team = {p["id"]: p for p in pros_for(u["id"]).values()}
    pro = team.get(pro_id)
    if not pro:
        flash("That person is not on your team.", "error")
        return redirect(url_for("team.my_team"))
    conn = _db()
    try:
        if request.method == "POST":
            body = (request.form.get("body") or "").strip()[:MAX_BODY]
            if not body:
                flash("Type a message first.", "error")
            elif _too_many(conn, u["id"]):
                flash("That is a lot of messages in a short time. Please wait a little and try again.", "error")
            else:
                _save(conn, u["id"], pro_id, u["id"], body)
                _notify(u, pro_id, pro["role"], body[:300], url_for("team.pro_thread", homeowner_id=u["id"]))
                flash("Sent.", "success")
            return redirect(url_for("team.home_thread", pro_id=pro_id))
        msgs = _thread(conn, u["id"], pro_id, u["id"])
    finally:
        conn.close()
    return render_template("homeowner/team_thread.html", pro=pro, messages=msgs, post_url=url_for("team.home_thread", pro_id=pro_id),
                           back_url=url_for("team.my_team"), me_id=u["id"], is_lender=pro["role"] == "lender")


def _prefill(homeowner_id):
    """The homeowner's own numbers, to save typing. They can change any of them before sharing."""
    out = {}
    try:
        from database import get_homeowner_snapshot_for_property, get_primary_property
        prop = get_primary_property(homeowner_id)
        snap = get_homeowner_snapshot_for_property(homeowner_id, prop.get("id")) if prop else None
        if snap:
            snap = dict(snap)
            for key, col in (("home_value", "value_estimate"), ("loan_balance", "loan_balance"), ("rate", "loan_rate"), ("payment", "loan_payment")):
                if snap.get(col):
                    out[key] = snap[col]
    except Exception:
        pass
    return out


@bp.route("/homeowner/team/ask-lender", methods=["GET", "POST"])
def ask_lender():
    u = _user("homeowner")
    if not u:
        return _login()
    lender = pros_for(u["id"]).get("lender")
    if not lender:
        flash("You do not have a lender on your team yet.", "error")
        return redirect(url_for("team.my_team"))
    if request.method == "POST":
        kind = request.form.get("kind") if request.form.get("kind") in KINDS else "payment"
        data = {}
        for key, _label in SCENARIO_FIELDS:
            if request.form.get("share_" + key):          # only numbers the homeowner ticked are ever kept
                v = _num(request.form.get(key))
                if v is not None and v >= 0:
                    data[key] = v
        note = (request.form.get("note") or "").strip()[:MAX_BODY]
        if not data and not note:
            flash("Tick at least one number to share, or write a note.", "error")
            return redirect(url_for("team.ask_lender"))
        conn = _db()
        try:
            if _too_many(conn, u["id"]):
                flash("That is a lot of messages in a short time. Please wait a little and try again.", "error")
                return redirect(url_for("team.my_team"))
            sid = conn.execute("INSERT INTO shared_scenarios (homeowner_id, lender_id, kind, data, note) VALUES (?,?,?,?,?)",
                               (u["id"], lender["id"], kind, json.dumps(data), note)).lastrowid
            _save(conn, u["id"], lender["id"], u["id"], f"Shared a {KINDS[kind].lower()} with you.", scenario_id=sid)
        finally:
            conn.close()
        _notify(u, lender["id"], "lender", f"{u.get('name') or 'A client'} shared a {KINDS[kind].lower()} with you. Open it to see the numbers.",
                url_for("team.shared_scenarios"))
        flash("Shared with your lender. They will reply right here.", "success")
        return redirect(url_for("team.home_thread", pro_id=lender["id"]))
    return render_template("homeowner/ask_lender.html", lender=lender, fields=SCENARIO_FIELDS, prefill=_prefill(u["id"]), kinds=KINDS)


# ───────────────────────── agents and lenders: Messages and Shared Scenarios ─────────────────────────
@bp.route("/messages")
def pro_messages():
    u = _user("pro")
    if not u:
        return _login()
    clients = client_ids(u)
    names = {c["id"]: c["name"] for c in clients}
    conn = _db()
    try:
        rows = conn.execute("""SELECT homeowner_id, MAX(id) AS last_id, SUM(CASE WHEN sender_id != ? AND read_at IS NULL THEN 1 ELSE 0 END) AS unread
                               FROM team_messages WHERE pro_id = ? GROUP BY homeowner_id ORDER BY last_id DESC""", (u["id"], u["id"])).fetchall()
        threads = []
        for r in rows:
            last = conn.execute("SELECT body, created_at, sender_id FROM team_messages WHERE id = ?", (r["last_id"],)).fetchone()
            name = names.get(r["homeowner_id"])
            if not name:
                hu = conn.execute("SELECT name FROM users WHERE id = ?", (r["homeowner_id"],)).fetchone()
                name = hu["name"] if hu else "Client"
            threads.append({"homeowner_id": r["homeowner_id"], "name": name, "unread": r["unread"] or 0, "snippet": (last["body"] or "")[:90],
                            "when": when_text(last["created_at"]), "you": last["sender_id"] == u["id"]})
    finally:
        conn.close()
    return render_template(f"{u['role']}/pro_messages.html", threads=threads, clients=clients, role=u["role"])


@bp.route("/messages/<int:homeowner_id>", methods=["GET", "POST"])
def pro_thread(homeowner_id):
    u = _user("pro")
    if not u:
        return _login()
    ids = {c["id"]: c for c in client_ids(u)}
    if homeowner_id not in ids and not connected(homeowner_id, u["id"]):
        flash("That client is not connected to your account.", "error")
        return redirect(url_for("team.pro_messages"))
    from database import get_user_by_id
    h = get_user_by_id(homeowner_id)
    h = dict(h) if h else {}
    conn = _db()
    try:
        if request.method == "POST":
            body = (request.form.get("body") or "").strip()[:MAX_BODY]
            if not body:
                flash("Type a message first.", "error")
            elif _too_many(conn, u["id"]):
                flash("That is a lot of messages in a short time. Please wait a little and try again.", "error")
            else:
                _save(conn, homeowner_id, u["id"], u["id"], body)
                _notify(u, homeowner_id, "homeowner", body[:300], url_for("team.home_thread", pro_id=u["id"]))
                flash("Sent.", "success")
            return redirect(url_for("team.pro_thread", homeowner_id=homeowner_id))
        msgs = _thread(conn, homeowner_id, u["id"], u["id"])
    finally:
        conn.close()
    return render_template(f"{u['role']}/thread.html", pro={"name": h.get("name") or "Client", "brokerage": "", "phone": ""}, messages=msgs,
                           post_url=url_for("team.pro_thread", homeowner_id=homeowner_id), back_url=url_for("team.pro_messages"),
                           me_id=u["id"], is_lender=False)


@bp.route("/lender/shared-scenarios")
def shared_scenarios():
    u = _user("lender")
    if not u:
        return _login()
    conn = _db()
    try:
        rows = conn.execute("""SELECT s.*, u.name AS client_name, u.email AS client_email FROM shared_scenarios s JOIN users u ON u.id = s.homeowner_id
                               WHERE s.lender_id = ? ORDER BY s.id DESC LIMIT 200""", (u["id"],)).fetchall()
        items = []
        for r in rows:
            v = _scenario_view(r)
            v.update(client=r["client_name"], homeowner_id=r["homeowner_id"], new=not r["seen_at"])
            items.append(v)
        conn.execute("UPDATE shared_scenarios SET seen_at = CURRENT_TIMESTAMP WHERE lender_id = ? AND seen_at IS NULL", (u["id"],))
        conn.commit()
    finally:
        conn.close()
    return render_template("lender/shared_scenarios.html", items=items)


def init_app(app, get_current_user, ns):
    _H.update(get_current_user=get_current_user, ns=ns)
    ensure_tables()
    app.register_blueprint(bp)
