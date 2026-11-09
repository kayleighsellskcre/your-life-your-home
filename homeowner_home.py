"""Homeowner home base: what brings you here (own, sell, buy one day, rentals), the next few steps
for that goal, and a simple portfolio view with rent and cash flow for people who buy and hold."""
from flask import Blueprint, flash, jsonify, redirect, request, session, url_for

bp = Blueprint("homeowner_home", __name__)
_H = {}

GOALS = {
    "owner": ("I own my home", "Keep it healthy and watch my equity"),
    "seller": ("I'm thinking about selling", "Know my numbers and my timing"),
    "buyer": ("I want to own one day", "Get ready, step by step"),
    "investor": ("I own rentals", "Track my properties and cash flow"),
}


def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    conn.execute("CREATE TABLE IF NOT EXISTS homeowner_prefs (user_id INTEGER PRIMARY KEY, goal TEXT)")
    have = {r[1] for r in conn.execute("PRAGMA table_info(properties)").fetchall()}
    for col in ("monthly_rent", "monthly_expenses"):
        if have and col not in have:
            conn.execute(f"ALTER TABLE properties ADD COLUMN {col} REAL")
    conn.commit()
    conn.close()


def _user():
    u = _H["get_current_user"]()
    return u if u and u.get("role") == "homeowner" else None


def get_goal(user_id):
    conn = _db()
    r = conn.execute("SELECT goal FROM homeowner_prefs WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return r[0] if r and r[0] in GOALS else ""


def _count(conn, sql, args):
    try:
        return conn.execute(sql, args).fetchone()[0] or 0
    except Exception:
        return 0


def overview_extras(user_id):
    """Everything the overview needs beyond the basics: goal, next steps, and the property portfolio."""
    goal = get_goal(user_id)
    conn = _db()
    props = []
    for p in conn.execute("""SELECT p.id, p.address, p.property_type, p.is_primary, p.monthly_rent, p.monthly_expenses,
                                    s.value_estimate, s.loan_balance, s.loan_payment, s.property_tax_monthly,
                                    s.homeowners_insurance_monthly
                             FROM properties p LEFT JOIN homeowner_snapshots s ON s.property_id = p.id AND s.user_id = p.user_id
                             WHERE p.user_id=? ORDER BY p.is_primary DESC, p.id""", (user_id,)).fetchall():
        d = dict(p)
        v, lb = d.get("value_estimate") or 0, d.get("loan_balance") or 0
        d["equity"] = (v - lb) if v and d.get("loan_balance") is not None else None
        rent = d.get("monthly_rent") or 0
        if rent:
            costs = sum(d.get(k) or 0 for k in ("loan_payment", "property_tax_monthly", "homeowners_insurance_monthly", "monthly_expenses"))
            d["cash_flow"] = rent - costs
        else:
            d["cash_flow"] = None
        props.append(d)
    n_docs = _count(conn, "SELECT COUNT(*) FROM homeowner_documents WHERE user_id=?", (user_id,))
    n_warranty = _count(conn, "SELECT COUNT(*) FROM homeowner_warranty_log WHERE user_id=?", (user_id,))
    n_timeline = _count(conn, "SELECT COUNT(*) FROM homeowner_timeline_events WHERE user_id=?", (user_id,))
    conn.close()

    has_home = bool(props)
    has_loan = any(p.get("loan_balance") for p in props)
    steps = []

    def add(label, why, ep, done):
        steps.append(dict(label=label, why=why, url=url_for(ep), done=bool(done)))

    if goal == "buyer":
        add("See what you can comfortably afford", "A realistic budget makes every other step easier.", "homeowner_next_affordability", False)
        add("Tell us what you're looking for", "Your agent can start watching for the right home.", "homeowner_next_plan_move", False)
        add("Learn the loan options", "Know what a lender will look at before you apply.", "homeowner_next_loan_paths", False)
        add("Ask your agent or lender a question", "No question is too small this early.", "homeowner_support_get_help", False)
    else:
        add("Add your home", "We'll show what it's worth and how your equity is growing.", "homeowner_value_equity_overview", has_home)
        if goal == "investor":
            add("Add rent and costs for each rental", "See your monthly cash flow across every property.", "homeowner_overview",
                any(p.get("monthly_rent") for p in props))
        add("Add your loan details", "Your equity and payment need your balance and rate.", "homeowner_value_equity_overview", has_loan or not has_home)
        if goal == "seller":
            add("See what you could walk away with", "Try the refinance and equity what-ifs, then talk timing with your agent.", "homeowner_value_equity_overview", False)
            add("Plan the move", "A buyer profile and the sell guide keep you on track.", "homeowner_next_buy_sell_guidance", False)
        add("Save your key documents", "Deed, insurance and closing papers, safe in one place.", "homeowner_upload_documents", n_docs)
        add("Log your appliances and warranties", "We'll help you remember when coverage ends.", "homeowner_care_warranty_log", n_warranty)
        if goal in ("owner", "investor", ""):
            add("Log a repair or project", "Your home's history adds value when you sell.", "homeowner_home_timeline", n_timeline)
    pending = [s for s in steps if not s["done"]]
    total_value = sum(p.get("value_estimate") or 0 for p in props)
    total_equity = sum(p["equity"] for p in props if p["equity"] is not None)
    rents = [p for p in props if p.get("monthly_rent")]
    return dict(
        goal=goal, goals=GOALS, steps=pending[:3], steps_done=len(steps) - len(pending), steps_total=len(steps),
        props=props, show_portfolio=(goal == "investor" or len(props) > 1),
        total_value=total_value, total_equity=total_equity,
        total_rent=sum(p["monthly_rent"] for p in rents),
        total_cash_flow=sum(p["cash_flow"] for p in rents if p["cash_flow"] is not None) if rents else None,
    )


@bp.route("/homeowner/goal", methods=["POST"])
def set_goal():
    u = _user()
    if not u:
        return redirect(url_for("login"))
    goal = request.form.get("goal", "")
    conn = _db()
    if goal in GOALS:
        conn.execute("DELETE FROM homeowner_prefs WHERE user_id=?", (u["id"],))
        conn.execute("INSERT INTO homeowner_prefs (user_id, goal) VALUES (?,?)", (u["id"], goal))
    elif goal == "clear":
        conn.execute("DELETE FROM homeowner_prefs WHERE user_id=?", (u["id"],))
    conn.commit()
    conn.close()
    return redirect(url_for("homeowner_overview"))


@bp.route("/homeowner/property/<int:property_id>/rental", methods=["POST"])
def save_rental(property_id):
    u = _user()
    if not u:
        return redirect(url_for("login"))

    def money(name):
        raw = (request.form.get(name) or "").replace(",", "").replace("$", "").strip()
        try:
            return max(0.0, float(raw)) if raw else None
        except ValueError:
            return None
    conn = _db()
    conn.execute("UPDATE properties SET monthly_rent=?, monthly_expenses=? WHERE id=? AND user_id=?",
                 (money("monthly_rent"), money("monthly_expenses"), property_id, u["id"]))
    conn.commit()
    conn.close()
    flash("Saved.", "success")
    return redirect(url_for("homeowner_overview") + "#portfolio")


@bp.route("/homeowner/pros")
def trusted_pros():
    """The home-service pros the homeowner's agent recommends (plumbers, inspectors, painters...)."""
    from flask import render_template
    from database import get_homeowner_professionals, get_trusted_vendors
    u = _user()
    if not u:
        return redirect(url_for("login"))
    agent = next((p for p in get_homeowner_professionals(u["id"]) if p.get("professional_role") == "agent"), None)
    groups = {}
    if agent:
        for v in get_trusted_vendors(agent["professional_id"] if "professional_id" in agent else agent["user_id"]):
            groups.setdefault(v.get("category") or "Other", []).append(v)
    return render_template("homeowner/trusted_pros.html", agent=agent, groups=dict(sorted(groups.items())))


def _primary_snapshot(conn, user_id):
    """The snapshot for the primary property (or the newest one) as a dict, with the address."""
    row = conn.execute(
        """SELECT p.address, s.value_estimate, s.equity_estimate, s.loan_rate, s.loan_payment, s.loan_balance,
                  s.loan_term_years, s.loan_start_date, s.initial_purchase_value, s.last_value_refresh
           FROM homeowner_snapshots s LEFT JOIN properties p ON p.id = s.property_id
           WHERE s.user_id = ? ORDER BY COALESCE(p.is_primary, 0) DESC, s.updated_at DESC, s.id DESC LIMIT 1""",
        (user_id,)).fetchone()
    return dict(row) if row else {}


def _years_left(snap):
    from datetime import date, datetime
    term = snap.get("loan_term_years") or 30
    try:
        start = datetime.strptime(str(snap.get("loan_start_date") or "")[:10], "%Y-%m-%d").date()
        left = term - (date.today() - start).days / 365.25
        return max(1, min(40, round(left)))
    except ValueError:
        return min(40, int(term)) if snap.get("loan_term_years") else 25


@bp.route("/homeowner/value/refinance")
def refinance_page():
    """Refinance and extra-payment calculator, filled in from the homeowner's own loan details."""
    from flask import render_template
    u = _user()
    if not u:
        return redirect(url_for("login"))
    conn = _db()
    snap = _primary_snapshot(conn, u["id"])
    conn.close()
    bal = float(snap.get("loan_balance") or 0)
    rate = float(snap.get("loan_rate") or 0)
    loan = dict(
        balance=int(round(bal)) if bal else "",
        rate=rate if rate else "",
        payment=int(round(float(snap.get("loan_payment") or 0))) or "",
        years_left=_years_left(snap),
        new_rate=round(max(rate - 1, 0), 3) if rate else 6.0,
        closing=int(round(bal * 0.02 / 100.0) * 100) if bal else "",
    )
    return render_template("homeowner/refinance.html", loan=loan, has_loan=bool(bal))


@bp.route("/homeowner/report")
def home_report():
    """A printable year-in-review for the home: value, equity, care, projects, warranties."""
    from datetime import date, datetime, timedelta
    from flask import render_template
    u = _user()
    if not u:
        return redirect(url_for("login"))
    conn = _db()
    snap = _primary_snapshot(conn, u["id"])
    year_ago = (date.today() - timedelta(days=365)).isoformat()
    soon = (date.today() + timedelta(days=90)).isoformat()
    today = date.today().isoformat()
    def rows(sql, args):
        try:
            return [dict(r) for r in conn.execute(sql, args).fetchall()]
        except Exception:
            return []
    care = rows("SELECT event_date, title, category, cost FROM homeowner_timeline_events WHERE user_id=? AND event_date >= ? ORDER BY event_date DESC",
                (u["id"], year_ago))
    projects = rows("SELECT name, status, budget FROM homeowner_projects WHERE user_id=? ORDER BY id DESC", (u["id"],))
    warranties = rows("SELECT item_name, warranty_expiry FROM homeowner_warranty_log WHERE user_id=? ORDER BY warranty_expiry", (u["id"],))
    docs = _count(conn, "SELECT COUNT(*) FROM homeowner_documents WHERE user_id=?", (u["id"],))
    conn.close()
    def _num(v):
        try:
            return float(str(v).replace("$", "").replace(",", "")) if v not in (None, "") else 0.0
        except ValueError:
            return 0.0
    for c_ in care:
        c_["cost"] = _num(c_.get("cost"))
    for p_ in projects:
        p_["budget"] = _num(p_.get("budget"))
    for k_ in ("value_estimate", "equity_estimate", "loan_balance", "initial_purchase_value"):
        if k_ in snap:
            snap[k_] = _num(snap[k_]) if snap[k_] not in (None, "") else None
    value = float(snap.get("value_estimate") or 0)
    bought = float(snap.get("initial_purchase_value") or 0)
    equity = snap.get("equity_estimate")
    if equity is None and value:
        equity = value - float(snap.get("loan_balance") or 0)
    spent = sum(float(c.get("cost") or 0) for c in care)
    active_w = [w for w in warranties if (w.get("warranty_expiry") or "") >= today]
    ending = [w for w in active_w if (w.get("warranty_expiry") or "") <= soon]
    ideas = []
    if not care:
        ideas.append("Log your maintenance as you do it (filters, gutters, servicing). A complete history helps at resale.")
    if ending:
        ideas.append(f"{len(ending)} warranty {'ends' if len(ending) == 1 else 'end'} in the next 90 days. Use it or renew it.")
    if not docs:
        ideas.append("Upload your closing papers, insurance and manuals so everything lives in one place.")
    if snap.get("loan_rate"):
        ideas.append("Check whether a refinance or a little extra each month makes sense with the Refinance & Payoff tool.")
    ideas.append("Walk through the Seasonal Checklists each season. Small habits prevent expensive repairs.")
    return render_template("homeowner/report.html", user=u, snap=snap, value=value, bought=bought, growth=(value - bought) if (value and bought) else None,
                           equity=equity, care=care, spent=spent, projects=projects, active_w=active_w, ending=ending, docs=docs,
                           ideas=ideas, year=date.today().year, today=datetime.now().strftime("%B %d, %Y").replace(" 0", " "))


def init_app(app, get_current_user):
    _H.update(get_current_user=get_current_user)
    ensure_tables()
    app.register_blueprint(bp)
