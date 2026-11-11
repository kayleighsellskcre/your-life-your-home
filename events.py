"""Events: a place for agents and lenders to plan community events, keep a "what to bring" checklist, and write down what to
do better next time. An event can be one time or yearly. Each time you hold it is a "run" with its own ticked-off checklist
and notes; the checklist itself carries forward, so next year you start from last year's list and last year's lessons."""
from datetime import date, datetime

from flask import Blueprint, flash, jsonify, redirect, render_template, request, session, url_for

bp = Blueprint("events", __name__)
_H = {}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]


def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    conn.execute("""CREATE TABLE IF NOT EXISTS events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER NOT NULL, name TEXT NOT NULL, kind TEXT NOT NULL DEFAULT 'one_time',
        place TEXT DEFAULT '', who TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS event_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL, text TEXT NOT NULL, detail TEXT DEFAULT '',
        sort INTEGER NOT NULL DEFAULT 0)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS event_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, event_id INTEGER NOT NULL, run_date TEXT DEFAULT '', attendance TEXT DEFAULT '',
        spent TEXT DEFAULT '', went_well TEXT DEFAULT '', improve TEXT DEFAULT '', notes TEXT DEFAULT '',
        created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS event_costs (
        id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER NOT NULL, what TEXT NOT NULL, amount REAL NOT NULL DEFAULT 0,
        kind TEXT NOT NULL DEFAULT 'other', expense_id INTEGER)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS event_checks (
        run_id INTEGER NOT NULL, item_id INTEGER NOT NULL, PRIMARY KEY (run_id, item_id))""")
    conn.commit()
    conn.close()


# What kind of cost -> the category it lands in on the Financials page (the CPA can always change it there).
COST_KINDS = {
    "food": ("Food and drinks", {"agent": "Marketing", "lender": "Meals & Entertainment"}),
    "gifts": ("Giveaways and gifts", {"agent": "Gifts", "lender": "Referral Partner Gifts & Events"}),
    "supplies": ("Signs, printing and supplies", {"agent": "Marketing", "lender": "Marketing & Lead Generation"}),
    "other": ("Something else", {"agent": "Other", "lender": "Other"}),
}
_EXP = {"agent": ("agent_expenses", "agent_user_id"), "lender": ("lender_expenses", "lender_user_id")}


def _user():
    u = _H["get_current_user"]()
    return u if u and u.get("role") in ("agent", "lender") else None


def _guard():
    u = _user()
    if not u:
        flash("Please sign in to see your events.", "error")
        return None, redirect(url_for("login", role="agent"))
    return u, None


def _clean(s, n=2000):
    return (s or "").strip()[:n]


def _valid_date(s):
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def nice_date(s):
    try:
        d = datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
        return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"
    except ValueError:
        return "No date yet"


def when_text(s):
    try:
        days = (datetime.strptime((s or "")[:10], "%Y-%m-%d").date() - date.today()).days
    except ValueError:
        return ""
    if days == 0:
        return "Today"
    if days == 1:
        return "Tomorrow"
    if days > 1:
        return f"In {days} days"
    return ""


def _own_event(conn, event_id, user_id):
    return conn.execute("SELECT * FROM events WHERE id = ? AND user_id = ?", (event_id, user_id)).fetchone()


def _same_day_next_year(iso):
    try:
        d = datetime.strptime(iso[:10], "%Y-%m-%d").date()
    except ValueError:
        return ""
    try:
        return d.replace(year=d.year + 1).isoformat()
    except ValueError:  # Feb 29
        return d.replace(year=d.year + 1, day=28).isoformat()


def _drop_cost(conn, u, cost_id):
    """Remove an event cost and the Financials expense it created."""
    c = conn.execute("SELECT expense_id FROM event_costs WHERE id = ?", (cost_id,)).fetchone()
    if c and c["expense_id"]:
        table, col = _EXP[u["role"]]
        conn.execute(f"DELETE FROM {table} WHERE id = ? AND {col} = ?", (c["expense_id"], u["id"]))
    conn.execute("DELETE FROM event_costs WHERE id = ?", (cost_id,))


def _back(event_id, run_id=None):
    return redirect(url_for("events.event_page", event_id=event_id, run=run_id) if run_id else url_for("events.event_page", event_id=event_id))


@bp.route("/events")
def events_page():
    u, bad = _guard()
    if bad:
        return bad
    conn = _db()
    try:
        rows = conn.execute(
            """SELECT e.*, (SELECT COUNT(*) FROM event_runs r WHERE r.event_id = e.id) AS run_count,
                      (SELECT COUNT(*) FROM event_items i WHERE i.event_id = e.id) AS item_count,
                      (SELECT MAX(run_date) FROM event_runs r WHERE r.event_id = e.id) AS latest
               FROM events e WHERE e.user_id = ? ORDER BY e.name COLLATE NOCASE""", (u["id"],)).fetchall()
    finally:
        conn.close()
    today = date.today().isoformat()
    upcoming, past = [], []
    for r in rows:
        r = dict(r)
        r["latest_nice"], r["when"] = nice_date(r["latest"]), when_text(r["latest"])
        (upcoming if (r["latest"] or "") >= today else past).append(r)
    upcoming.sort(key=lambda r: r["latest"] or "9999")
    past.sort(key=lambda r: r["latest"] or "", reverse=True)
    return render_template(f"{u['role']}/events.html", upcoming=upcoming, past=past, all_events=upcoming + past, role=u["role"])


@bp.route("/events/new", methods=["POST"])
def event_new():
    u, bad = _guard()
    if bad:
        return bad
    name = _clean(request.form.get("name"), 120)
    if not name:
        flash("Give your event a name first.", "error")
        return redirect(url_for("events.events_page"))
    kind = "yearly" if request.form.get("kind") == "yearly" else "one_time"
    conn = _db()
    try:
        cur = conn.execute("INSERT INTO events (user_id, name, kind, place, who) VALUES (?,?,?,?,?)",
                           (u["id"], name, kind, _clean(request.form.get("place"), 200), _clean(request.form.get("who"), 200)))
        eid = cur.lastrowid
        run = conn.execute("INSERT INTO event_runs (event_id, run_date) VALUES (?,?)", (eid, _valid_date(request.form.get("event_date")))).lastrowid
        src = request.form.get("copy_from", type=int)
        if src and _own_event(conn, src, u["id"]):
            for i in conn.execute("SELECT text, detail, sort FROM event_items WHERE event_id = ? ORDER BY sort, id", (src,)).fetchall():
                conn.execute("INSERT INTO event_items (event_id, text, detail, sort) VALUES (?,?,?,?)", (eid, i["text"], i["detail"], i["sort"]))
        conn.commit()
    finally:
        conn.close()
    flash("Event created. Add what you need to bring below.", "success")
    return _back(eid, run)


def _load(conn, event_id, user_id, run_id):
    ev = _own_event(conn, event_id, user_id)
    if not ev:
        return None
    runs = [dict(r) for r in conn.execute("SELECT * FROM event_runs WHERE event_id = ? ORDER BY run_date DESC, id DESC", (event_id,)).fetchall()]
    if not runs:
        rid = conn.execute("INSERT INTO event_runs (event_id, run_date) VALUES (?, '')", (event_id,)).lastrowid
        conn.commit()
        runs = [dict(r) for r in conn.execute("SELECT * FROM event_runs WHERE event_id = ?", (event_id,)).fetchall()]
    cur = next((r for r in runs if r["id"] == run_id), runs[0])
    items = [dict(i) for i in conn.execute("SELECT * FROM event_items WHERE event_id = ? ORDER BY sort, id", (event_id,)).fetchall()]
    ticked = {r["item_id"] for r in conn.execute("SELECT item_id FROM event_checks WHERE run_id = ?", (cur["id"],)).fetchall()}
    for i in items:
        i["done"] = i["id"] in ticked
    costs = [dict(c) for c in conn.execute("SELECT * FROM event_costs WHERE run_id = ? ORDER BY id", (cur["id"],)).fetchall()]
    for c in costs:
        c["kind_label"] = COST_KINDS.get(c["kind"], COST_KINDS["other"])[0]
    older = [r for r in runs if r["id"] != cur["id"] and (r["run_date"] or "") < (cur["run_date"] or "9999") ]
    last = next((r for r in older if r["improve"] or r["went_well"] or r["notes"]), None)
    return dict(ev=dict(ev), runs=runs, cur=cur, items=items, costs=costs, total_cost=sum(c["amount"] for c in costs), last=last, packed=sum(1 for i in items if i["done"]))


@bp.route("/events/<int:event_id>")
def event_page(event_id):
    u, bad = _guard()
    if bad:
        return bad
    conn = _db()
    try:
        d = _load(conn, event_id, u["id"], request.args.get("run", type=int))
    finally:
        conn.close()
    if not d:
        flash("That event was not found.", "error")
        return redirect(url_for("events.events_page"))
    for r in d["runs"]:
        r["nice"] = nice_date(r["run_date"])
    d["cur"]["nice"], d["cur"]["when"] = nice_date(d["cur"]["run_date"]), when_text(d["cur"]["run_date"])
    if d["last"]:
        d["last"]["nice"] = nice_date(d["last"]["run_date"])
    d["is_latest"] = d["cur"]["id"] == d["runs"][0]["id"]
    return render_template(f"{u['role']}/event.html", role=u["role"], cost_kinds=COST_KINDS, **d)


@bp.route("/events/<int:event_id>/edit", methods=["POST"])
def event_edit(event_id):
    u, bad = _guard()
    if bad:
        return bad
    conn = _db()
    try:
        if not _own_event(conn, event_id, u["id"]):
            return redirect(url_for("events.events_page"))
        name = _clean(request.form.get("name"), 120)
        if name:
            conn.execute("UPDATE events SET name=?, kind=?, place=?, who=? WHERE id=? AND user_id=?",
                         (name, "yearly" if request.form.get("kind") == "yearly" else "one_time",
                          _clean(request.form.get("place"), 200), _clean(request.form.get("who"), 200), event_id, u["id"]))
            conn.commit()
            flash("Saved.", "success")
    finally:
        conn.close()
    return _back(event_id, request.form.get("run_id", type=int))


@bp.route("/events/<int:event_id>/delete", methods=["POST"])
def event_delete(event_id):
    u, bad = _guard()
    if bad:
        return bad
    conn = _db()
    try:
        if _own_event(conn, event_id, u["id"]):
            run_ids = [r["id"] for r in conn.execute("SELECT id FROM event_runs WHERE event_id = ?", (event_id,)).fetchall()]
            for rid in run_ids:
                for c in conn.execute("SELECT id FROM event_costs WHERE run_id = ?", (rid,)).fetchall():
                    _drop_cost(conn, u, c["id"])
                conn.execute("DELETE FROM event_checks WHERE run_id = ?", (rid,))
            conn.execute("DELETE FROM event_runs WHERE event_id = ?", (event_id,))
            conn.execute("DELETE FROM event_items WHERE event_id = ?", (event_id,))
            conn.execute("DELETE FROM events WHERE id = ? AND user_id = ?", (event_id, u["id"]))
            conn.commit()
            flash("Event deleted.", "success")
    finally:
        conn.close()
    return redirect(url_for("events.events_page"))


@bp.route("/events/<int:event_id>/items/add", methods=["POST"])
def item_add(event_id):
    u, bad = _guard()
    if bad:
        return bad
    conn = _db()
    try:
        if _own_event(conn, event_id, u["id"]):
            # one per line, so a whole list can be pasted in at once
            lines = [l.strip() for l in (request.form.get("text") or "").replace("\r", "").split("\n") if l.strip()][:60]
            detail = _clean(request.form.get("detail"), 200) if len(lines) == 1 else ""
            nxt = (conn.execute("SELECT COALESCE(MAX(sort), 0) + 1 FROM event_items WHERE event_id = ?", (event_id,)).fetchone()[0])
            for n, line in enumerate(lines):
                conn.execute("INSERT INTO event_items (event_id, text, detail, sort) VALUES (?,?,?,?)", (event_id, line[:160], detail, nxt + n))
            conn.commit()
    finally:
        conn.close()
    return _back(event_id, request.form.get("run_id", type=int))


@bp.route("/events/<int:event_id>/items/<int:item_id>/delete", methods=["POST"])
def item_delete(event_id, item_id):
    u, bad = _guard()
    if bad:
        return bad
    conn = _db()
    try:
        if _own_event(conn, event_id, u["id"]):
            conn.execute("DELETE FROM event_checks WHERE item_id = ?", (item_id,))
            conn.execute("DELETE FROM event_items WHERE id = ? AND event_id = ?", (item_id, event_id))
            conn.commit()
    finally:
        conn.close()
    return _back(event_id, request.form.get("run_id", type=int))


@bp.route("/events/<int:event_id>/items/<int:item_id>/tick", methods=["POST"])
def item_tick(event_id, item_id):
    u, bad = _guard()
    if bad:
        return bad
    run_id = request.form.get("run_id", type=int)
    conn = _db()
    done = False
    try:
        ev = _own_event(conn, event_id, u["id"])
        run = conn.execute("SELECT id FROM event_runs WHERE id = ? AND event_id = ?", (run_id, event_id)).fetchone() if ev else None
        item = conn.execute("SELECT id FROM event_items WHERE id = ? AND event_id = ?", (item_id, event_id)).fetchone() if ev else None
        if run and item:
            if conn.execute("SELECT 1 FROM event_checks WHERE run_id = ? AND item_id = ?", (run_id, item_id)).fetchone():
                conn.execute("DELETE FROM event_checks WHERE run_id = ? AND item_id = ?", (run_id, item_id))
            else:
                conn.execute("INSERT INTO event_checks (run_id, item_id) VALUES (?,?)", (run_id, item_id))
                done = True
            conn.commit()
        total = packed = 0
        if run:
            total = conn.execute("SELECT COUNT(*) FROM event_items WHERE event_id = ?", (event_id,)).fetchone()[0]
            packed = conn.execute("SELECT COUNT(*) FROM event_checks c JOIN event_items i ON i.id = c.item_id WHERE c.run_id = ?", (run_id,)).fetchone()[0]
    finally:
        conn.close()
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(done=done, packed=packed, total=total)
    return _back(event_id, run_id)


@bp.route("/events/<int:event_id>/run", methods=["POST"])
def run_save(event_id):
    u, bad = _guard()
    if bad:
        return bad
    run_id = request.form.get("run_id", type=int)
    conn = _db()
    try:
        if _own_event(conn, event_id, u["id"]) and conn.execute("SELECT 1 FROM event_runs WHERE id=? AND event_id=?", (run_id, event_id)).fetchone():
            conn.execute("""UPDATE event_runs SET run_date=?, attendance=?, spent=?, went_well=?, improve=?, notes=? WHERE id=? AND event_id=?""",
                         (_valid_date(request.form.get("run_date")), _clean(request.form.get("attendance"), 100), _clean(request.form.get("spent"), 100),
                          _clean(request.form.get("went_well")), _clean(request.form.get("improve")), _clean(request.form.get("notes"), 6000), run_id, event_id))
            new_date = _valid_date(request.form.get("run_date"))
            if new_date:  # keep the money lines on the same day as the event
                table, col = _EXP[u["role"]]
                for c in conn.execute("SELECT expense_id FROM event_costs WHERE run_id = ? AND expense_id IS NOT NULL", (run_id,)).fetchall():
                    conn.execute(f"UPDATE {table} SET expense_date = ? WHERE id = ? AND {col} = ?", (new_date, c["expense_id"], u["id"]))
            conn.commit()
            flash("Notes saved.", "success")
    finally:
        conn.close()
    return _back(event_id, run_id)


@bp.route("/events/<int:event_id>/costs/add", methods=["POST"])
def cost_add(event_id):
    """Record what the event cost. It also lands in Financials as a business expense, so it is ready for the CPA."""
    u, bad = _guard()
    if bad:
        return bad
    run_id = request.form.get("run_id", type=int)
    what = _clean(request.form.get("what"), 120)
    try:
        amount = round(float((request.form.get("amount") or "0").replace("$", "").replace(",", "")), 2)
    except ValueError:
        amount = 0
    kind = request.form.get("kind") if request.form.get("kind") in COST_KINDS else "other"
    if not what or amount <= 0:
        flash("Add what it was and how much it cost.", "error")
        return _back(event_id, run_id)
    conn = _db()
    try:
        ev = _own_event(conn, event_id, u["id"])
        run = conn.execute("SELECT * FROM event_runs WHERE id = ? AND event_id = ?", (run_id, event_id)).fetchone() if ev else None
        if run:
            table, col = _EXP[u["role"]]
            when = run["run_date"] or date.today().isoformat()
            eid = conn.execute(
                f"INSERT INTO {table} ({col}, expense_date, category, description, amount, notes) VALUES (?,?,?,?,?,?)",
                (u["id"], when, COST_KINDS[kind][1][u["role"]], f"{ev['name']}: {what}", amount, "Added from Events")).lastrowid
            conn.execute("INSERT INTO event_costs (run_id, what, amount, kind, expense_id) VALUES (?,?,?,?,?)", (run_id, what, amount, kind, eid))
            conn.commit()
            flash("Cost saved and added to your Financials for taxes.", "success")
    finally:
        conn.close()
    return _back(event_id, run_id)


@bp.route("/events/<int:event_id>/costs/<int:cost_id>/delete", methods=["POST"])
def cost_delete(event_id, cost_id):
    u, bad = _guard()
    if bad:
        return bad
    run_id = request.form.get("run_id", type=int)
    conn = _db()
    try:
        owned = conn.execute("""SELECT c.id FROM event_costs c JOIN event_runs r ON r.id = c.run_id JOIN events e ON e.id = r.event_id
                                WHERE c.id = ? AND e.id = ? AND e.user_id = ?""", (cost_id, event_id, u["id"])).fetchone()
        if owned:
            _drop_cost(conn, u, cost_id)
            conn.commit()
            flash("Cost removed, and taken out of Financials too.", "success")
    finally:
        conn.close()
    return _back(event_id, run_id)


@bp.route("/events/<int:event_id>/next", methods=["POST"])
def run_next(event_id):
    """Start the next time you hold this event: same checklist, nothing ticked, and last time's lessons shown up top."""
    u, bad = _guard()
    if bad:
        return bad
    conn = _db()
    try:
        if not _own_event(conn, event_id, u["id"]):
            return redirect(url_for("events.events_page"))
        latest = conn.execute("SELECT run_date FROM event_runs WHERE event_id = ? ORDER BY run_date DESC, id DESC LIMIT 1", (event_id,)).fetchone()
        when = _valid_date(request.form.get("run_date")) or _same_day_next_year(latest["run_date"] if latest else "")
        rid = conn.execute("INSERT INTO event_runs (event_id, run_date) VALUES (?,?)", (event_id, when)).lastrowid
        conn.commit()
    finally:
        conn.close()
    flash("Next one is ready. Your checklist carried over and last time's notes are at the top.", "success")
    return _back(event_id, rid)


def init_app(app, get_current_user):
    _H.update(get_current_user=get_current_user)
    ensure_tables()
    app.register_blueprint(bp)
