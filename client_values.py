"""Client Values: an optional page for agents who like to see how their clients' homes are doing and reach out.

Off by default. Clients stay free to check their own value whenever they like, with no calls or nudges from this
feature, unless their agent switches it on in Settings. When it is on the agent gets:
  - a page that lists their clients with value, recent change, equity and when they last spoke
  - an email when a client's value rises by 3 percent or more
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

bp = Blueprint("client_values", __name__)
_H = {}

SORTS = {
    "rise": "Biggest rise",
    "equity": "Most equity",
    "quiet": "Longest since we spoke",
    "name": "Name",
}


def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    conn.execute("CREATE TABLE IF NOT EXISTS agent_prefs (user_id INTEGER PRIMARY KEY, value_call_list INTEGER NOT NULL DEFAULT 0)")
    conn.commit()
    conn.close()


def is_on(user_id):
    if not user_id:
        return False
    try:
        conn = _db()
        r = conn.execute("SELECT value_call_list FROM agent_prefs WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        return bool(r and r[0])
    except Exception:
        return False


def set_on(user_id, on):
    conn = _db()
    conn.execute("INSERT INTO agent_prefs (user_id, value_call_list) VALUES (?, ?) "
                 "ON CONFLICT(user_id) DO UPDATE SET value_call_list = excluded.value_call_list", (user_id, 1 if on else 0))
    conn.commit()
    conn.close()


def _agent():
    u = _H["get_current_user"]()
    return u if u and u.get("role") == "agent" else None


def _changes(conn, ids):
    """Percent change in value over the last year for each client, from their saved history."""
    out = {}
    if not ids:
        return out
    since = (date.today() - timedelta(days=365)).isoformat()
    marks = ",".join("?" * len(ids))
    rows = conn.execute(
        f"""SELECT user_id, snapshot_date, value_estimate FROM homeowner_snapshot_history
            WHERE user_id IN ({marks}) AND value_estimate IS NOT NULL AND snapshot_date >= ?
            ORDER BY user_id, snapshot_date""", list(ids) + [since]).fetchall()
    first, last = {}, {}
    for r in rows:
        first.setdefault(r["user_id"], (r["snapshot_date"], r["value_estimate"]))
        last[r["user_id"]] = (r["snapshot_date"], r["value_estimate"])
    for uid, (d0, v0) in first.items():
        v1 = last[uid][1]
        if v0 and uid in last and last[uid][0] != d0:
            out[uid] = dict(amount=float(v1) - float(v0), pct=(float(v1) - float(v0)) / float(v0) * 100, since=d0)
    return out


def _phones(conn, ids):
    if not ids:
        return {}
    marks = ",".join("?" * len(ids))
    try:
        return {r[0]: r[1] for r in conn.execute(f"SELECT id, phone FROM users WHERE id IN ({marks})", list(ids)).fetchall()}
    except Exception:
        return {}


def build_rows(agent_id, sort="rise"):
    from database import get_agent_clients
    from planner import ago
    clients = get_agent_clients(agent_id)
    conn = _db()
    try:
        ids = [c["id"] for c in clients]
        ch = _changes(conn, ids)
        ph = _phones(conn, ids)
    finally:
        conn.close()
    rows = []
    for c in clients:
        label, days = ago(c.get("last_touch"))
        v = c.get("value_estimate")
        eq = c.get("equity_estimate")
        if eq is None and v and c.get("loan_balance") is not None:
            eq = float(v) - float(c["loan_balance"])
        rows.append(dict(
            id=c["id"], name=c.get("name") or c.get("email") or "Client", email=c.get("email") or "", phone=ph.get(c["id"]) or "",
            address=c.get("property_address") or "", value=float(v) if v else None, equity=float(eq) if eq is not None else None,
            change=ch.get(c["id"]), last=label, days=days, contact_id=c.get("crm_contact_id")))
    if sort == "equity":
        rows.sort(key=lambda r: (r["equity"] is None, -(r["equity"] or 0)))
    elif sort == "quiet":
        rows.sort(key=lambda r: (r["days"] is not None, -(r["days"] or 0)))
    elif sort == "name":
        rows.sort(key=lambda r: r["name"].lower())
    else:
        rows.sort(key=lambda r: (r["change"] is None, -(r["change"]["pct"] if r["change"] else 0)))
    return rows


@bp.route("/agent/client-values")
def client_values_page():
    u = _agent()
    if not u:
        return redirect(url_for("login", role="agent"))
    if not is_on(u["id"]):
        flash("Client Values is optional. Turn it on in Settings if you would like it.", "info")
        return redirect(url_for("agent_settings_profile") + "#client-values")
    sort = request.args.get("sort") if request.args.get("sort") in SORTS else "rise"
    return render_template("agent/client_values.html", rows=build_rows(u["id"], sort), sort=sort, sorts=SORTS)


@bp.route("/agent/client-values/toggle", methods=["POST"])
def client_values_toggle():
    u = _agent()
    if not u:
        return redirect(url_for("login", role="agent"))
    on = request.form.get("on") == "1"
    set_on(u["id"], on)
    if on:
        flash("Client Values is on. You will find it in your menu, and you will get an email when a client's value rises.", "success")
        return redirect(url_for("client_values.client_values_page"))
    flash("Client Values is off. Your clients can still check their own home value any time.", "success")
    return redirect(url_for("agent_settings_profile") + "#client-values")


def init_app(app, get_current_user):
    _H.update(get_current_user=get_current_user)
    ensure_tables()
    app.register_blueprint(bp)

    def client_values_on():
        uid = session.get("user_id")
        return is_on(uid) if uid and session.get("role") == "agent" else False

    app.add_template_global(client_values_on, "client_values_on")
