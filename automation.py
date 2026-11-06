"""
Connective automation between homeowners, agents and lenders.

Every function here is safe to call from a request handler: it never raises,
and it receives the email sender as an argument so it can be tested without SMTP.
"""
import traceback

from database import get_connection

STAGE_LABELS = {
    "pre_contract": "Getting started",
    "under_contract": "Under contract",
    "in_escrow": "In escrow",
    "clear_to_close": "Clear to close",
    "closed": "Closed",
    "cancelled": "Cancelled",
}

STAGE_BLURBS = {
    "pre_contract": "We're getting everything lined up.",
    "under_contract": "Congratulations, the contract is in place. Next come inspections, appraisal and loan steps.",
    "in_escrow": "Your file is moving through inspections, appraisal and underwriting.",
    "clear_to_close": "Great news: you're clear to close. Your agent will confirm signing details.",
    "closed": "Congratulations on closing! Your home is now set up in your Your Life, Your Home dashboard.",
    "cancelled": "This transaction was cancelled. Please reach out to your agent with any questions.",
}

LOAN_WORDS = ("loan", "mortgage", "rate", "refinanc", "refi", "afford", "payment", "preapprov", "pre-approv", "heloc", "equity")


def _log(msg):
    print(f"[AUTOMATION] {msg}")


def _row(conn, sql, args=()):
    try:
        r = conn.execute(sql, args).fetchone()
        return dict(r) if r else None
    except Exception:
        return None


def _user_by_email(conn, email):
    if not email:
        return None
    return _row(conn, "SELECT id, name, email, role, agent_id, lender_id FROM users WHERE lower(email) = lower(?)", (email.strip(),))


def _user(conn, uid):
    if not uid:
        return None
    return _row(conn, "SELECT id, name, email, role, agent_id, lender_id, phone FROM users WHERE id = ?", (uid,))


def _transaction(conn, tx_id):
    return _row(conn, "SELECT * FROM transactions WHERE id = ?", (tx_id,))


def link_transaction_parties(tx_id):
    """Attach the client's homeowner account (and their lender) to a transaction by matching email."""
    try:
        conn = get_connection()
        try:
            tx = _transaction(conn, tx_id)
            if not tx:
                return False
            home = _user_by_email(conn, tx.get("client_email"))
            if not home or home.get("role") != "homeowner":
                return False
            lender_id = tx.get("lender_user_id") or home.get("lender_id")
            conn.execute(
                "UPDATE transactions SET homeowner_user_id = ?, lender_user_id = COALESCE(lender_user_id, ?) WHERE id = ?",
                (home["id"], lender_id, tx_id),
            )
            conn.commit()
            _log(f"linked transaction {tx_id} to homeowner {home['id']} (lender {lender_id})")
            return True
        finally:
            conn.close()
    except Exception:
        _log("link_transaction_parties failed:\n" + traceback.format_exc())
        return False


def _signup_link(base_url, agent_id):
    try:
        from database import get_or_create_referral_code
        code = get_or_create_referral_code(agent_id, "agent")
        return f"{base_url}/r/{code}" if code else f"{base_url}/signup?role=homeowner"
    except Exception:
        return f"{base_url}/signup?role=homeowner"


def notify_stage_change(tx_id, new_stage, send_email, base_url):
    """Tell the client (and their lender) when the agent moves a transaction to a new stage."""
    try:
        conn = get_connection()
        try:
            tx = _transaction(conn, tx_id)
            if not tx:
                return []
            agent = _user(conn, tx.get("agent_id")) or {}
            lender = _user(conn, tx.get("lender_user_id"))
        finally:
            conn.close()
        label = STAGE_LABELS.get(new_stage, new_stage.replace("_", " ").title())
        addr = tx.get("property_address") or "your property"
        sent = []
        agent_line = f"Your agent: {agent.get('name', '')}" + (f" ({agent.get('email')})" if agent.get("email") else "")
        client_email = (tx.get("client_email") or "").strip()
        if client_email:
            body = (
                f"Hi {tx.get('client_name') or 'there'},\n\n"
                f"Quick update on {addr}: it is now \"{label}\".\n"
                f"{STAGE_BLURBS.get(new_stage, '')}\n\n"
                f"{agent_line}\n"
                f"Track everything in your dashboard: {base_url}/homeowner\n"
            )
            if new_stage == "closed" and not tx.get("homeowner_user_id"):
                body += f"\nCreate your free homeowner account to track your home's value and care: {_signup_link(base_url, tx.get('agent_id'))}\n"
            if send_email(client_email, f"Update on {addr}: {label}", body):
                sent.append(client_email)
        if lender and lender.get("email"):
            body = (
                f"Hi {lender.get('name') or 'there'},\n\n"
                f"{tx.get('client_name') or 'Your client'}'s transaction at {addr} moved to \"{label}\".\n"
                f"{agent_line}\n"
                f"Open your dashboard: {base_url}/lender\n"
            )
            if send_email(lender["email"], f"Client update: {addr} is now {label}", body):
                sent.append(lender["email"])
        return sent
    except Exception:
        _log("notify_stage_change failed:\n" + traceback.format_exc())
        return []


def on_transaction_closed(tx_id):
    """When a deal closes, put the property on the homeowner's dashboard automatically."""
    try:
        conn = get_connection()
        try:
            tx = _transaction(conn, tx_id)
            if not tx or not tx.get("homeowner_user_id") or not tx.get("property_address"):
                return False
            uid = tx["homeowner_user_id"]
            addr = tx["property_address"].strip()
            exists = _row(conn, "SELECT id FROM properties WHERE user_id = ? AND lower(address) = lower(?)", (uid, addr))
            if exists:
                return False
            has_primary = _row(conn, "SELECT id FROM properties WHERE user_id = ? AND is_primary = 1", (uid,))
            value = None
            try:
                value = float(str(tx.get("purchase_price") or "").replace(",", "").replace("$", "")) or None
            except ValueError:
                value = None
            conn.execute(
                "INSERT INTO properties (user_id, address, estimated_value, is_primary) VALUES (?, ?, ?, ?)",
                (uid, addr, value, 0 if has_primary else 1),
            )
            conn.commit()
            _log(f"added {addr} to homeowner {uid}'s properties after closing")
            return True
        finally:
            conn.close()
    except Exception:
        _log("on_transaction_closed failed:\n" + traceback.format_exc())
        return False


def route_homeowner_question(user_id, topic, question, send_email, base_url):
    """Send a homeowner's question to their agent (and lender, if it's about money), and track it in the CRM."""
    try:
        conn = get_connection()
        try:
            home = _user(conn, user_id)
            if not home:
                return []
            agent = _user(conn, home.get("agent_id"))
            lender = _user(conn, home.get("lender_id"))
            contact = None
            if agent:
                contact = _row(conn, "SELECT id FROM agent_contacts WHERE agent_user_id = ? AND lower(email) = lower(?)", (agent["id"], home.get("email")))
        finally:
            conn.close()
        text = f"{topic or 'General'} {question}".lower()
        about_money = any(w in text for w in LOAN_WORDS)
        recipients = []
        if agent:
            recipients.append(("agent", agent))
        if lender and (about_money or not agent):
            recipients.append(("lender", lender))
        sent = []
        for kind, pro in recipients:
            if not pro.get("email"):
                continue
            body = (
                f"{home.get('name') or 'A homeowner'} sent you a question through Your Life, Your Home.\n\n"
                f"Topic: {topic or 'General'}\n\n{question}\n\n"
                f"Reply to them directly: {home.get('email')}"
                + (f" or {home.get('phone')}" if home.get("phone") else "")
                + f"\nOpen your dashboard: {base_url}/{kind}\n"
            )
            if send_email(pro["email"], f"Question from {home.get('name') or 'a homeowner'}: {topic or 'General'}", body):
                sent.append(pro["email"])
        if agent and contact:
            from database import add_crm_task, add_crm_interaction
            from datetime import date, timedelta
            add_crm_interaction(contact["id"], "agent_contact", agent["id"], "note",
                                f"Question: {topic or 'General'}", question, "email")
            add_crm_task(contact["id"], "agent_contact", agent["id"],
                         f"Reply to {home.get('name') or 'homeowner'}'s question",
                         question[:300], (date.today() + timedelta(days=1)).isoformat(), "high", None)
        return sent
    except Exception:
        _log("route_homeowner_question failed:\n" + traceback.format_exc())
        return []
