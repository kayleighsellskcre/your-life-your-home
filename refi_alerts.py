"""Refinance Opportunities: a lender page that shows which clients could benefit from a conversation right now.

Two plain signals, nothing sent to clients:
  - rate: their current rate is at least `drop` points above today's rate (the lender's own posted 30-year rate)
  - equity: they have a lot of equity (loan is 80 percent of the value or less, and at least $75,000 of equity)
Covers homeowners connected to the lender plus borrowers the lender keeps in their CRM.
"""
from flask import Blueprint, redirect, render_template, request, session, url_for

bp = Blueprint("refi_alerts", __name__)
_H = {}

DEFAULT_RATE = 6.1
DEFAULT_DROP = 0.75
MIN_SAVINGS = 50
MIN_EQUITY = 75000
SORTS = {"savings": "Biggest savings", "equity": "Most equity", "quiet": "Longest since we spoke", "name": "Name"}


def monthly_payment(balance, rate_pct, years=30):
    """Principal and interest per month."""
    balance = float(balance)
    n = years * 12
    r = float(rate_pct) / 100 / 12
    if r <= 0:
        return balance / n
    return balance * r / (1 - (1 + r) ** -n)


def _market_rate(lender_id):
    try:
        from database import get_user_profile
        p = get_user_profile(lender_id)
        p = dict(p) if p and hasattr(p, "keys") else (p or {})
        v = p.get("conventional_rate_30yr")
        return float(v) if v else None
    except Exception:
        return None


def _num(x):
    try:
        return float(x) if x not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _phones(ids):
    if not ids:
        return {}
    try:
        from database import get_connection
        conn = get_connection()
        try:
            marks = ",".join("?" * len(ids))
            return {r[0]: r[1] for r in conn.execute(f"SELECT id, phone FROM users WHERE id IN ({marks})", list(ids)).fetchall()}
        finally:
            conn.close()
    except Exception:
        return {}


def _score(base, market, drop):
    """Add the signals to a row. Returns the row if it has at least one, else None."""
    bal, rate, val = base["balance"], base["rate"], base["value"]
    tags = []
    base["savings"] = None
    if bal and rate and bal > 0 and rate - market >= drop:
        sv = monthly_payment(bal, rate) - monthly_payment(bal, market)
        if sv >= MIN_SAVINGS:
            base["savings"] = sv
            tags.append("rate")
    eq = base["equity"]
    if eq is None and val and bal is not None:
        eq = val - bal
    base["equity"] = eq
    if val and bal is not None and eq is not None and eq >= MIN_EQUITY and bal <= 0.8 * val:
        tags.append("equity")
    base["tags"] = tags
    return base if tags else None


def find(lender_id, market=None, drop=DEFAULT_DROP, sort="savings"):
    """Clients worth a conversation. Returns (rows, market_rate_used)."""
    from database import get_lender_clients, get_connection
    from planner import ago
    if market is None:
        market = _market_rate(lender_id) or DEFAULT_RATE
    rows, seen_users = [], set()
    clients = get_lender_clients(lender_id)
    phones = _phones([c["id"] for c in clients])
    for c in clients:
        seen_users.add(c["id"])
        label, days = ago(c.get("last_touch"))
        r = _score(dict(
            name=c.get("name") or c.get("email") or "Client", email=c.get("email") or "", phone=phones.get(c["id"]) or "",
            address=c.get("property_address") or "", rate=_num(c.get("loan_rate")), balance=_num(c.get("loan_balance")),
            value=_num(c.get("value_estimate")), equity=_num(c.get("equity_estimate")), last=label, days=days,
            contact_id=c.get("crm_borrower_id"), source="client"), market, drop)
        if r:
            rows.append(r)
    conn = get_connection()
    try:
        crm = conn.execute(
            """SELECT id, name, email, phone, property_address, address, loan_amount, loan_rate, last_touch, user_id
               FROM lender_borrowers WHERE lender_user_id = ? AND loan_rate IS NOT NULL AND loan_amount IS NOT NULL""",
            (lender_id,)).fetchall()
    finally:
        conn.close()
    for b in crm:
        if b["user_id"] and b["user_id"] in seen_users:
            continue
        label, days = ago(b["last_touch"])
        r = _score(dict(
            name=b["name"] or b["email"] or "Borrower", email=b["email"] or "", phone=b["phone"] or "",
            address=b["property_address"] or b["address"] or "", rate=_num(b["loan_rate"]), balance=_num(b["loan_amount"]),
            value=None, equity=None, last=label, days=days, contact_id=b["id"], source="crm"), market, drop)
        if r:
            rows.append(r)
    if sort == "equity":
        rows.sort(key=lambda r: (r["equity"] is None, -(r["equity"] or 0)))
    elif sort == "quiet":
        rows.sort(key=lambda r: (r["days"] is not None, -(r["days"] or 0)))
    elif sort == "name":
        rows.sort(key=lambda r: r["name"].lower())
    else:
        rows.sort(key=lambda r: (r["savings"] is None, -(r["savings"] or 0), -(r["equity"] or 0)))
    return rows, market


def _lender():
    u = _H["get_current_user"]()
    return u if u and u.get("role") == "lender" else None


@bp.route("/lender/refinance-opportunities")
def refi_page():
    u = _lender()
    if not u:
        return redirect(url_for("login", role="lender"))
    sort = request.args.get("sort") if request.args.get("sort") in SORTS else "savings"
    market = _num(request.args.get("rate"))
    if market is not None and not (1 <= market <= 15):
        market = None
    own = _market_rate(u["id"])
    rows, used = find(u["id"], market=market, sort=sort)
    return render_template("lender/refi_alerts.html", rows=rows, sort=sort, sorts=SORTS, rate=used,
                           posted=own, custom=market is not None, drop=DEFAULT_DROP)


def init_app(app, get_current_user):
    _H.update(get_current_user=get_current_user)
    app.register_blueprint(bp)
