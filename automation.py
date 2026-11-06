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


def link_transaction_parties(tx_id, lender_email=None):
    """Attach the client's homeowner account and a lender (given email, else the client's own lender) to a transaction."""
    try:
        conn = get_connection()
        try:
            tx = _transaction(conn, tx_id)
            if not tx:
                return False
            named_lender = _user_by_email(conn, lender_email)
            named_lender_id = named_lender["id"] if named_lender and named_lender.get("role") == "lender" else None
            home = _user_by_email(conn, tx.get("client_email"))
            if home and home.get("role") != "homeowner":
                home = None
            if not home and not named_lender_id:
                return False
            lender_id = named_lender_id or tx.get("lender_user_id") or (home or {}).get("lender_id")
            conn.execute(
                "UPDATE transactions SET homeowner_user_id = COALESCE(?, homeowner_user_id), lender_user_id = COALESCE(?, lender_user_id) WHERE id = ?",
                ((home or {}).get("id"), lender_id, tx_id),
            )
            conn.commit()
            _log(f"linked transaction {tx_id} to homeowner {(home or {}).get('id')} (lender {lender_id})")
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


def invite_client_if_needed(tx_id, send_email, base_url):
    """If the client has no account yet, email them an invitation to the agent's portal."""
    try:
        conn = get_connection()
        try:
            tx = _transaction(conn, tx_id)
            if not tx:
                return False
            email = (tx.get("client_email") or "").strip()
            if not email or _user_by_email(conn, email):
                return False
            agent = _user(conn, tx.get("agent_id")) or {}
        finally:
            conn.close()
        link = _signup_link(base_url, tx.get("agent_id"))
        body = (
            f"Hi {tx.get('client_name') or 'there'},\n\n"
            f"{agent.get('name') or 'Your agent'} set up a free homeowner portal for you on Your Life, Your Home. "
            f"Track {tx.get('property_address') or 'your transaction'} step by step, keep your documents in one place, "
            f"and watch your home's value and equity after closing.\n\n"
            f"Create your account here: {link}\n\n"
            f"Use this email address ({email}) so everything connects automatically."
        )
        ok = send_email(email, f"{agent.get('name') or 'Your agent'} invited you to your home portal", body)
        _log(f"invited {email} for transaction {tx_id}: {ok}")
        return bool(ok)
    except Exception:
        _log("invite_client_if_needed failed:\n" + traceback.format_exc())
        return False


def lender_shared_deals(lender_id, limit=8):
    """Active transactions an agent has shared with this lender."""
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT t.id, t.property_address, t.client_name, t.current_stage, t.target_close_date,
                          t.purchase_price, u.name AS agent_name
                   FROM transactions t LEFT JOIN users u ON u.id = t.agent_id
                   WHERE t.lender_user_id = ? AND t.status = 'active' AND t.current_stage NOT IN ('closed', 'cancelled')
                   ORDER BY t.target_close_date IS NULL, t.target_close_date, t.created_at DESC LIMIT ?""",
                (lender_id, limit),
            ).fetchall()
            out = []
            for r in rows:
                d = dict(r)
                d["stage_label"] = STAGE_LABELS.get(d.get("current_stage"), d.get("current_stage"))
                out.append(d)
            return out
        finally:
            conn.close()
    except Exception:
        _log("lender_shared_deals failed:\n" + traceback.format_exc())
        return []


STATUS_LABELS = {
    "prospect": "Getting started",
    "preapproval": "Pre-approval",
    "processing": "Processing",
    "underwriting": "Underwriting",
    "in_process": "In process",
    "clear_to_close": "Clear to close",
    "closed": "Closed",
}


def _lender_signup_link(base_url, lender_id):
    try:
        from database import get_or_create_referral_code
        code = get_or_create_referral_code(lender_id, "lender")
        return f"{base_url}/r/{code}" if code else f"{base_url}/signup?role=homeowner"
    except Exception:
        return f"{base_url}/signup?role=homeowner"


def on_loan_created(lender_id, borrower_name, borrower_email, send_email, base_url):
    """New loan with a borrower email: add them to the lender CRM, connect their account, or invite them."""
    try:
        email = (borrower_email or "").strip()
        if not email:
            return "no-email"
        conn = get_connection()
        try:
            lender = _user(conn, lender_id) or {}
            if not _row(conn, "SELECT id FROM lender_borrowers WHERE lender_user_id = ? AND lower(email) = lower(?)", (lender_id, email)):
                conn.execute(
                    "INSERT INTO lender_borrowers (lender_user_id, name, status, email) VALUES (?, ?, 'preapproval', ?)",
                    (lender_id, borrower_name, email),
                )
            acct = _user_by_email(conn, email)
            if acct and acct.get("role") == "homeowner":
                conn.execute("UPDATE users SET lender_id = ? WHERE id = ? AND lender_id IS NULL", (lender_id, acct["id"]))
                conn.commit()
                return "linked"
            conn.commit()
        finally:
            conn.close()
        link = _lender_signup_link(base_url, lender_id)
        body = (
            f"Hi {borrower_name or 'there'},\n\n"
            f"{lender.get('name') or 'Your lender'} set up a free homeowner portal for you on Your Life, Your Home. "
            f"Follow your loan, keep your documents in one place, and watch your home's value and equity.\n\n"
            f"Create your account here: {link}\n\n"
            f"Use this email address ({email}) so everything connects automatically."
        )
        send_email(email, f"{lender.get('name') or 'Your lender'} invited you to your home portal", body)
        return "invited"
    except Exception:
        _log("on_loan_created failed:\n" + traceback.format_exc())
        return "error"


def notify_borrower_status(lender_id, borrower_name, borrower_email, new_status, send_email, base_url):
    """Loan status moved: tell the borrower, and the borrower's agent when we know who that is."""
    try:
        label = STATUS_LABELS.get(new_status, (new_status or "").replace("_", " ").title())
        email = (borrower_email or "").strip()
        if not email or not label:
            return []
        conn = get_connection()
        try:
            lender = _user(conn, lender_id) or {}
            acct = _user_by_email(conn, email)
            agent = _user(conn, acct.get("agent_id")) if acct else None
        finally:
            conn.close()
        sent = []
        lender_line = f"Your lender: {lender.get('name', '')}" + (f" ({lender.get('email')})" if lender.get("email") else "")
        body = (
            f"Hi {borrower_name or 'there'},\n\n"
            f"Good news on your loan: it is now \"{label}\".\n\n{lender_line}\n"
            f"Track everything in your portal: {base_url}/homeowner\n"
        )
        if send_email(email, f"Loan update: {label}", body):
            sent.append(email)
        if agent and agent.get("email"):
            body = (
                f"Hi {agent.get('name') or 'there'},\n\n"
                f"{borrower_name or 'Your client'}'s loan with {lender.get('name') or 'their lender'} moved to \"{label}\".\n"
                f"Open your dashboard: {base_url}/agent\n"
            )
            if send_email(agent["email"], f"Client loan update: {borrower_name} is now {label}", body):
                sent.append(agent["email"])
        return sent
    except Exception:
        _log("notify_borrower_status failed:\n" + traceback.format_exc())
        return []


ACTIVITY_TYPES = [
    ("transaction", "Your transaction"),
    ("document", "Documents"),
    ("renovation", "Renovation"),
    ("care", "Home care"),
    ("home", "Home timeline"),
    ("design", "Design boards"),
    ("question", "Questions"),
    ("value", "Value & equity"),
]
_TYPE_LABEL = dict(ACTIVITY_TYPES)


def _when(ts):
    from datetime import datetime, date
    try:
        d = datetime.strptime(str(ts)[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        try:
            d = datetime.strptime(str(ts)[:10], "%Y-%m-%d")
        except ValueError:
            return str(ts or "")
    delta = (date.today() - d.date()).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if 1 < delta < 7:
        return f"{delta} days ago"
    return d.strftime("%b %d, %Y").replace(" 0", " ")


def homeowner_activity(user_id, q=None, type_=None, range_=None, from_date=None, to_date=None, limit=60):
    """One feed of everything happening on a homeowner's account, newest first."""
    from datetime import datetime, timedelta
    sources = [
        ("transaction", "SELECT tt.description AS title, t.property_address AS summary, tt.created_at AS ts FROM transaction_timeline tt JOIN transactions t ON t.id = tt.transaction_id WHERE t.homeowner_user_id = ? AND tt.event_type IN ('stage_changed', 'created')", "homeowner_overview"),
        ("document", "SELECT 'Document added: ' || COALESCE(name, 'Untitled') AS title, COALESCE(category, '') AS summary, created_at AS ts FROM homeowner_documents WHERE user_id = ?", "homeowner_upload_documents"),
        ("renovation", "SELECT 'Renovation project: ' || COALESCE(name, 'Untitled') AS title, COALESCE(status, '') AS summary, created_at AS ts FROM homeowner_projects WHERE user_id = ?", "homeowner_reno_planner"),
        ("care", "SELECT 'Warranty tracked: ' || COALESCE(item_name, 'Item') AS title, COALESCE(warranty_provider, '') AS summary, created_at AS ts FROM homeowner_warranty_log WHERE user_id = ?", "homeowner_care_warranty_log"),
        ("home", "SELECT COALESCE(title, 'Home update') AS title, COALESCE(category, '') AS summary, created_at AS ts FROM homeowner_timeline_events WHERE user_id = ?", "homeowner_home_timeline"),
        ("design", "SELECT 'Design board: ' || COALESCE(title, 'Untitled') AS title, COALESCE(project_name, '') AS summary, created_at AS ts FROM homeowner_notes WHERE user_id = ?", "homeowner_saved_notes"),
        ("question", "SELECT 'You asked: ' || COALESCE(topic, 'General') AS title, COALESCE(question, '') AS summary, created_at AS ts FROM homeowner_questions WHERE user_id = ?", "homeowner_support_get_help"),
        ("value", "SELECT 'Home value updated' AS title, 'Estimated value $' || CAST(CAST(value_estimate AS INTEGER) AS TEXT) AS summary, created_at AS ts FROM homeowner_snapshot_history WHERE user_id = ? AND value_estimate IS NOT NULL", "homeowner_value_equity_overview"),
    ]
    want = type_ if type_ in _TYPE_LABEL else None
    items = []
    conn = get_connection()
    try:
        for kind, sql, endpoint in sources:
            if want and kind != want:
                continue
            try:
                for r in conn.execute(sql, (user_id,)).fetchall():
                    items.append({"type": kind, "type_label": _TYPE_LABEL[kind], "title": r["title"], "summary": r["summary"], "ts": r["ts"] or "", "endpoint": endpoint})
            except Exception:
                continue
    finally:
        conn.close()
    cutoff = None
    if range_ == "today":
        cutoff = datetime.now().strftime("%Y-%m-%d")
    elif range_ and str(range_).isdigit():
        cutoff = (datetime.now() - timedelta(days=int(range_))).strftime("%Y-%m-%d")
    needle = (q or "").strip().lower()
    out = []
    for it in sorted(items, key=lambda x: x["ts"], reverse=True):
        day = it["ts"][:10]
        if cutoff and day < cutoff:
            continue
        if from_date and day < from_date:
            continue
        if to_date and day > to_date:
            continue
        if needle and needle not in f"{it['title']} {it['summary']}".lower():
            continue
        it["date_display"] = _when(it["ts"])
        out.append(it)
        if len(out) >= limit:
            break
    return out
