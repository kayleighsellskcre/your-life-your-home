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


def init_app(app, get_current_user):
    _H.update(get_current_user=get_current_user)
    ensure_tables()
    app.register_blueprint(bp)
