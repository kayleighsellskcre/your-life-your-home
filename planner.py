"""Weekly Success Planner: a simple weekly activity tracker for agents and lenders.

One grid per week (Monday to Friday plus the weekend). Each row is an income-producing
habit (face-to-face time, great phone calls, thank-you notes and so on). Rows are either
counters (tap + and - for each day) or a theme-day check (one call block per weekday).
Weekly targets can be changed per person. The dashboard shows today's slice of the same data.
"""
import json
from datetime import date, datetime, timedelta

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

bp = Blueprint("planner", __name__)
_H = {}

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Weekend"]

# kind: "count" (a number per day) or "theme" (a done / not done check on the matching weekday)
_COMMON_TAIL = [
    dict(key="notes", group="Stay in touch", label="Handwritten thank-you notes", hint="Birthdays count too.", kind="count", target=10),
    dict(key="videos", group="Stay in touch", label="Videos shared", hint="Short and real beats polished.", kind="count", target=3),
    dict(key="leads", group="New business", label="New leads (not from the internet)", hint="Conversations, referrals, events.", kind="count", target=3),
]

PLANS = {
    "agent": {
        "title": "Weekly Success Planner",
        "sub": "Small, steady habits that fill your pipeline. Check them off as you go.",
        "themes": ["Top VIPs (call 15)", "Client updates", "Hot and old leads", "Past clients (call 30)", "New business partners (call 10)"],
        "activities": [
            dict(key="face", group="People time", label="Face-to-face meetings", hint="Up to 5 people this week.", kind="count", target=5),
            dict(key="bread", group="People time", label="Break bread", hint="Coffee or a meal, in addition to the meetings above.", kind="count", target=2),
            dict(key="events", group="People time", label="Events attended or hosted", hint="Six or more people.", kind="count", target=1),
            dict(key="calls", group="Conversations", label="Great phone calls", hint="Leads, referral partners, past and current clients. Ask for business or a referral.", kind="count", target=25),
            dict(key="theme", group="Conversations", label="Theme-day calls", hint="One focused call block each weekday.", kind="theme", target=5),
        ] + _COMMON_TAIL + [
            dict(key="listings", group="Results", label="Listing agreements signed", hint="", kind="count", target=1),
            dict(key="buyers", group="Results", label="Buyer agreements signed", hint="", kind="count", target=1),
        ],
    },
    "lender": {
        "title": "Weekly Success Planner",
        "sub": "Small, steady habits that keep referrals and applications coming in. Check them off as you go.",
        "themes": ["Top referral partners (call 15)", "Active loan updates", "Hot and old leads", "Past borrowers (call 30)", "New agent partners (call 10)"],
        "activities": [
            dict(key="face", group="People time", label="Face-to-face meetings", hint="Agents, builders and other referral partners.", kind="count", target=5),
            dict(key="bread", group="People time", label="Break bread", hint="Coffee or lunch with a referral partner, in addition to the meetings above.", kind="count", target=2),
            dict(key="events", group="People time", label="Events, lunch-and-learns or seminars", hint="Attended or hosted, six or more people.", kind="count", target=1),
            dict(key="calls", group="Conversations", label="Great phone calls", hint="Agents, past borrowers, leads and current borrowers. Ask for a referral.", kind="count", target=25),
            dict(key="theme", group="Conversations", label="Theme-day calls", hint="One focused call block each weekday.", kind="theme", target=5),
        ] + _COMMON_TAIL + [
            dict(key="preapprovals", group="Results", label="Pre-approvals issued", hint="", kind="count", target=2),
            dict(key="applications", group="Results", label="Applications taken", hint="", kind="count", target=1),
        ],
    },
}


# ───────────────────────── data ─────────────────────────
def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    conn.execute("""CREATE TABLE IF NOT EXISTS planner_entries (
        user_id INTEGER NOT NULL,
        week_start TEXT NOT NULL,
        activity TEXT NOT NULL,
        day INTEGER NOT NULL,
        value INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, week_start, activity, day)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS planner_targets (
        user_id INTEGER NOT NULL,
        activity TEXT NOT NULL,
        target INTEGER NOT NULL,
        PRIMARY KEY (user_id, activity)
    )""")
    conn.commit()
    conn.close()


def monday_of(d):
    return d - timedelta(days=d.weekday())


def _parse_week(s):
    try:
        return monday_of(datetime.strptime(s, "%Y-%m-%d").date())
    except (TypeError, ValueError):
        return monday_of(date.today())


def _user():
    u = _H["get_current_user"]()
    if not u or u.get("role") not in PLANS:
        return None
    return u


def _targets(conn, user_id, plan):
    custom = {r[0]: r[1] for r in conn.execute("SELECT activity, target FROM planner_targets WHERE user_id=?", (user_id,)).fetchall()}
    return {a["key"]: custom.get(a["key"], a["target"]) for a in plan["activities"]}


def _week_values(conn, user_id, week):
    vals = {}
    for r in conn.execute("SELECT activity, day, value FROM planner_entries WHERE user_id=? AND week_start=?",
                          (user_id, week.isoformat())).fetchall():
        vals.setdefault(r[0], {})[r[1]] = r[2]
    return vals


def _progress(plan, targets, vals):
    """Percent of the weekly plan done, each row capped at its target."""
    parts = []
    for a in plan["activities"]:
        tgt = max(1, targets[a["key"]])
        done = sum(vals.get(a["key"], {}).values())
        parts.append(min(done, tgt) / tgt)
    return round(100 * sum(parts) / len(parts)) if parts else 0


def week_view(user_id, role, week):
    plan = PLANS[role]
    conn = _db()
    targets = _targets(conn, user_id, plan)
    vals = _week_values(conn, user_id, week)
    conn.close()
    rows = []
    for a in plan["activities"]:
        days = [vals.get(a["key"], {}).get(i, 0) for i in range(6)]
        total = sum(days)
        tgt = targets[a["key"]]
        rows.append(dict(a, days=days, total=total, tgt=tgt, pct=min(100, round(100 * total / max(1, tgt)))))
    return dict(plan=plan, rows=rows, pct=_progress(plan, targets, vals))


def today_summary(user_id, role):
    """Today's slice of the planner, for the dashboard card."""
    if role not in PLANS:
        return None
    week = monday_of(date.today())
    view = week_view(user_id, role, week)
    idx = min(date.today().weekday(), 5)  # Sat and Sun both land in the "Weekend" column
    items = []
    keep = ("calls", "face", "notes")
    for r in view["rows"]:
        if r["kind"] == "theme":
            if idx <= 4:
                items.append(dict(key=r["key"], kind="theme", label=view["plan"]["themes"][idx], value=r["days"][idx], day=idx,
                                  week_total=r["total"], tgt=r["tgt"]))
        elif r["key"] in keep:
            items.append(dict(key=r["key"], kind="count", label=r["label"], value=r["days"][idx], day=idx,
                              week_total=r["total"], tgt=r["tgt"]))
    order = {"theme": 0, "calls": 1, "face": 2, "notes": 3}
    items.sort(key=lambda i: order.get(i["key"], 9))
    return dict(items=items, pct=view["pct"], week=week.isoformat(), day=idx, day_name=DAYS[idx] if idx <= 4 else "Weekend")


# ───────────────────────── routes ─────────────────────────
@bp.route("/planner")
def planner_page():
    user = _user()
    if not user:
        return redirect(url_for("login"))
    week = _parse_week(request.args.get("week"))
    view = week_view(user["id"], user["role"], week)
    today = date.today()
    end = week + timedelta(days=6)
    label = f"{week.strftime('%b')} {week.day} to {end.strftime('%b')} {end.day}"
    return render_template("planner/page.html", view=view, role=user["role"], days=DAYS,
                           week=week.isoformat(), week_label=label,
                           prev_week=(week - timedelta(days=7)).isoformat(), next_week=(week + timedelta(days=7)).isoformat(),
                           is_this_week=(week == monday_of(today)),
                           today_idx=(min(today.weekday(), 5) if week == monday_of(today) else -1))


@bp.route("/planner/save", methods=["POST"])
def planner_save():
    user = _user()
    if not user:
        return jsonify(ok=False), 401
    data = request.get_json(silent=True) or {}
    plan = PLANS[user["role"]]
    keys = {a["key"]: a for a in plan["activities"]}
    act = data.get("activity")
    if act not in keys:
        return jsonify(ok=False), 400
    try:
        day = int(data.get("day"))
        value = int(data.get("value"))
    except (TypeError, ValueError):
        return jsonify(ok=False), 400
    if not 0 <= day <= 5:
        return jsonify(ok=False), 400
    value = max(0, min(value, 1 if keys[act]["kind"] == "theme" else 99))
    week = _parse_week(data.get("week"))
    conn = _db()
    conn.execute("DELETE FROM planner_entries WHERE user_id=? AND week_start=? AND activity=? AND day=?",
                 (user["id"], week.isoformat(), act, day))
    if value:
        conn.execute("INSERT INTO planner_entries (user_id, week_start, activity, day, value) VALUES (?,?,?,?,?)",
                     (user["id"], week.isoformat(), act, day, value))
    conn.commit()
    targets = _targets(conn, user["id"], plan)
    vals = _week_values(conn, user["id"], week)
    conn.close()
    total = sum(vals.get(act, {}).values())
    return jsonify(ok=True, total=total, pct=_progress(plan, targets, vals),
                   row_pct=min(100, round(100 * total / max(1, targets[act]))))


@bp.route("/planner/target", methods=["POST"])
def planner_target():
    user = _user()
    if not user:
        return jsonify(ok=False), 401
    data = request.get_json(silent=True) or {}
    plan = PLANS[user["role"]]
    if data.get("activity") not in {a["key"] for a in plan["activities"]}:
        return jsonify(ok=False), 400
    try:
        target = max(1, min(int(data.get("target")), 500))
    except (TypeError, ValueError):
        return jsonify(ok=False), 400
    conn = _db()
    conn.execute("DELETE FROM planner_targets WHERE user_id=? AND activity=?", (user["id"], data["activity"]))
    conn.execute("INSERT INTO planner_targets (user_id, activity, target) VALUES (?,?,?)", (user["id"], data["activity"], target))
    conn.commit()
    conn.close()
    return jsonify(ok=True, target=target)


def init_app(app, get_current_user):
    _H.update(get_current_user=get_current_user)
    ensure_tables()
    app.register_blueprint(bp)

    def planner_today():
        u = _user()
        return today_summary(u["id"], u["role"]) if u else None

    app.add_template_global(planner_today, "planner_today")
