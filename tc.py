"""Transaction coordination: one contract form, automatic deadlines, two sheets, reminders.

Fill in the contract details once. From that single record the site makes:
  * a PRIVATE sheet for the agent (includes the buyers' phone numbers and emails, marked internal)
  * a SHAREABLE sheet for the other agent, title company and lender (never includes client contact details)
and it works out the deadlines, shares the sheet by secure link, and emails friendly reminders.
"""
import io
import json
import re
import secrets
from datetime import date, datetime, timedelta

from flask import (Blueprint, Response, abort, flash, redirect, render_template, request, session, url_for)

bp = Blueprint("tc", __name__)
_H = {}

# Fields that must never appear on the shareable sheet or share page.
PRIVATE_KEYS = ("buyer_phones", "buyer_emails", "internal_notes")

SECTIONS = [
    ("The deal", True, [
        ("contract_date", "Contract date", "date", ""),
        ("effective_date", "Effective date (only if different)", "date", ""),
        ("closing_date", "Closing date", "date", ""),
        ("closing_time", "Closing time", "text", "TBD"),
        ("possession", "Possession", "text", "At closing"),
        ("seller", "Seller", "text", ""),
        ("mls", "MLS number", "text", ""),
        ("county", "County", "text", ""),
    ]),
    ("Money and terms", True, [
        ("earnest_amount", "Earnest money amount", "text", "$2,700"),
        ("earnest_holder", "Held by", "text", "Chicago Title"),
        ("earnest_due_days", "Due, days after contract", "number", "3"),
        ("earnest_due_date", "Or the exact due date", "date", ""),
        ("seller_brokerage", "Seller-paid buyer brokerage", "text", "$8,100"),
        ("seller_costs", "Other seller-paid costs", "text", "$3,500"),
        ("warranty", "Home warranty", "text", "Seller up to $660"),
        ("contingency", "Sale contingency", "text", "None"),
    ]),
    ("Deadlines", True, [
        ("inspection_days", "Inspection, calendar days after effective date", "number", "10"),
        ("inspection_date", "Or the exact inspection date", "date", ""),
        ("resolution_terms", "Resolution terms", "text", "5 calendar days after seller receives notice"),
        ("appraisal_date", "Appraisal date (optional)", "date", ""),
        ("loan_commitment_date", "Loan commitment date (optional)", "date", ""),
        ("walkthrough_date", "Final walkthrough (blank means the day before closing)", "date", ""),
    ]),
    ("Buyers' contact details (private, never on the shared sheet)", False, [
        ("buyer_phones", "Buyer phone numbers", "text", ""),
        ("buyer_emails", "Buyer emails", "text", ""),
    ]),
    ("Title and lender", False, [
        ("buyer_title", "Buyers' title company", "text", "Name | Company"),
        ("buyer_title_contact", "Their phone and email", "text", ""),
        ("seller_title", "Seller's title company", "text", ""),
        ("seller_title_contact", "Their contacts (one per line)", "area", ""),
        ("lender", "Lender and loan officer", "text", "Name | Company"),
        ("loan_type", "Loan type", "text", "Conventional"),
        ("lender_contact", "Lender phone and email", "text", ""),
    ]),
    ("Agents and coordination", False, [
        ("buyer_agent", "Buyers' agent", "text", "Name | Brokerage"),
        ("buyer_agent_contact", "Phone and email", "text", ""),
        ("listing_agent", "Listing agent", "text", "Name | Brokerage"),
        ("listing_agent_contact", "Phone and email", "text", ""),
        ("tc_name", "Transaction coordinator", "text", ""),
        ("tc_contact", "Phone and email", "text", ""),
        ("comm_request", "Message for the other parties", "text", ""),
    ]),
    ("Private notes (never shared)", False, [
        ("internal_notes", "Only you see this", "area", ""),
    ]),
]
ALL_KEYS = [f[0] for s in SECTIONS for f in s[2]]
DATE_KEYS = {f[0] for s in SECTIONS for f in s[2] if f[2] == "date"}


# ───────────────────────── storage ─────────────────────────
def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS transaction_contract (
        transaction_id INTEGER PRIMARY KEY,
        data TEXT,
        token TEXT UNIQUE,
        updated_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS transaction_deadlines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        transaction_id INTEGER NOT NULL,
        key TEXT NOT NULL,
        label TEXT NOT NULL,
        due_date TEXT NOT NULL,
        done INTEGER DEFAULT 0,
        reminded TEXT DEFAULT '',
        UNIQUE(transaction_id, key)
    )""")
    conn.commit()
    conn.close()


def load(tx_id):
    conn = _db()
    row = conn.execute("SELECT * FROM transaction_contract WHERE transaction_id=?", (tx_id,)).fetchone()
    conn.close()
    if not row:
        return {}, None
    try:
        return json.loads(row["data"] or "{}"), row["token"]
    except ValueError:
        return {}, row["token"]


def save(tx_id, data):
    conn = _db()
    row = conn.execute("SELECT token FROM transaction_contract WHERE transaction_id=?", (tx_id,)).fetchone()
    token = row["token"] if row and row["token"] else secrets.token_urlsafe(14)
    conn.execute("""INSERT INTO transaction_contract (transaction_id, data, token, updated_at)
                    VALUES (?,?,?,CURRENT_TIMESTAMP)
                    ON CONFLICT(transaction_id) DO UPDATE SET data=excluded.data, token=excluded.token,
                    updated_at=CURRENT_TIMESTAMP""", (tx_id, json.dumps(data), token))
    conn.commit()
    conn.close()
    return token


# ───────────────────────── dates and deadlines ─────────────────────────
def _d(v):
    try:
        return datetime.strptime((v or "").strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _int(v):
    try:
        n = int(str(v).strip())
        return n if 0 <= n <= 365 else None
    except (TypeError, ValueError):
        return None


def long_date(d):
    d = _d(d) if isinstance(d, str) else d
    return f"{d.strftime('%B')} {d.day}, {d.year}" if d else ""


def short_date(d):
    d = _d(d) if isinstance(d, str) else d
    return f"{d.strftime('%a, %b')} {d.day}" if d else ""


def compute_deadlines(d):
    """[(key, label, date)] worked out from the contract record."""
    out = []
    contract = _d(d.get("contract_date"))
    effective = _d(d.get("effective_date")) or contract
    closing = _d(d.get("closing_date"))
    earn = _d(d.get("earnest_due_date"))
    if not earn and contract and (d.get("earnest_amount") or d.get("earnest_due_days")):
        earn = contract + timedelta(days=_int(d.get("earnest_due_days")) if _int(d.get("earnest_due_days")) is not None else 3)
    if earn:
        out.append(("earnest", "Earnest money due", earn))
    insp = _d(d.get("inspection_date"))
    if not insp and effective and _int(d.get("inspection_days")) is not None:
        insp = effective + timedelta(days=_int(d.get("inspection_days")))
    if insp:
        out.append(("inspection", "Inspection deadline", insp))
    for key, label, field in (("appraisal", "Appraisal", "appraisal_date"),
                              ("loan", "Loan commitment", "loan_commitment_date")):
        v = _d(d.get(field))
        if v:
            out.append((key, label, v))
    walk = _d(d.get("walkthrough_date")) or (closing - timedelta(days=1) if closing else None)
    if walk:
        out.append(("walkthrough", "Final walkthrough", walk))
    if closing:
        out.append(("closing", "Closing day", closing))
    return sorted(out, key=lambda x: x[2])


def sync_deadlines(tx_id, d):
    """Rebuild the deadline list, keeping what is already checked off and not re-sending reminders."""
    wanted = compute_deadlines(d)
    conn = _db()
    have = {r["key"]: r for r in conn.execute("SELECT * FROM transaction_deadlines WHERE transaction_id=?", (tx_id,)).fetchall()}
    for key, label, due in wanted:
        iso = due.isoformat()
        if key in have:
            changed = have[key]["due_date"] != iso
            conn.execute("UPDATE transaction_deadlines SET label=?, due_date=?, reminded=? WHERE id=?",
                         (label, iso, "" if changed else have[key]["reminded"], have[key]["id"]))
        else:
            conn.execute("INSERT INTO transaction_deadlines (transaction_id, key, label, due_date) VALUES (?,?,?,?)",
                         (tx_id, key, label, iso))
    keep = [k for k, _, _ in wanted]
    for key in have:
        if key not in keep:
            conn.execute("DELETE FROM transaction_deadlines WHERE transaction_id=? AND key=?", (tx_id, key))
    conn.commit()
    conn.close()


def deadlines(tx_id):
    conn = _db()
    rows = [dict(r) for r in conn.execute(
        "SELECT * FROM transaction_deadlines WHERE transaction_id=? ORDER BY due_date", (tx_id,)).fetchall()]
    conn.close()
    today = date.today()
    for r in rows:
        dd = _d(r["due_date"])
        r["pretty"] = short_date(dd)
        r["days"] = (dd - today).days if dd else None
        if r["done"]:
            r["when"] = "Done"
        elif r["days"] is None:
            r["when"] = ""
        elif r["days"] < 0:
            r["when"] = f"{-r['days']} day{'s' if r['days'] != -1 else ''} ago"
        elif r["days"] == 0:
            r["when"] = "Today"
        elif r["days"] == 1:
            r["when"] = "Tomorrow"
        else:
            r["when"] = f"In {r['days']} days"
    return rows


# ───────────────────────── sheet building ─────────────────────────
def money(v):
    v = (v or "").strip()
    if re.fullmatch(r"\d[\d,]*(\.\d+)?", v):
        try:
            return "${:,.0f}".format(float(v.replace(",", "")))
        except ValueError:
            return v
    return v


def _pair(*vals):
    return " | ".join(v.strip() for v in vals if v and v.strip())


def build_blocks(tx, d, kind):
    """Sections for a sheet. kind is 'private' or 'shareable'. Private-only fields are added only for 'private'."""
    price = tx.get("purchase_price")
    contract = long_date(d.get("contract_date"))
    closing = long_date(d.get("closing_date"))
    closing_line = _pair(closing, d.get("closing_time") or ("TBD" if closing else ""))
    earnest = _pair(money(d.get("earnest_amount")) + (f" to {d['earnest_holder']}" if d.get("earnest_holder") and d.get("earnest_amount") else ""))
    due = next((x for x in compute_deadlines(d) if x[0] == "earnest"), None)
    if earnest and due:
        earnest += f" | Due {long_date(due[2])}"
    insp = next((x for x in compute_deadlines(d) if x[0] == "inspection"), None)
    insp_line = ""
    if insp:
        insp_line = long_date(insp[2])
        if _int(d.get("inspection_days")) is not None and not d.get("inspection_date"):
            insp_line += f" | {d['inspection_days']} calendar days after effective date"

    deal = [("Purchase price", money(str(int(price))) if price else ""), ("Contract date", contract),
            ("Closing", closing_line), ("Possession", d.get("possession")), ("Earnest money", earnest),
            ("Inspection deadline", insp_line), ("Resolution", d.get("resolution_terms")),
            ("Appraisal", long_date(d.get("appraisal_date"))), ("Loan commitment", long_date(d.get("loan_commitment_date"))),
            ("Final walkthrough", long_date(next((x[2] for x in compute_deadlines(d) if x[0] == "walkthrough"), None))),
            ("Home warranty", d.get("warranty")), ("Sale contingency", d.get("contingency")),
            ("Seller-paid buyer brokerage", money(d.get("seller_brokerage"))),
            ("Other seller-paid costs", money(d.get("seller_costs")))]
    people = [("Buyers", tx.get("client_name")), ("Seller", d.get("seller"))]
    if kind == "private":
        people += [("Buyer phones", d.get("buyer_phones")), ("Buyer emails", d.get("buyer_emails"))]
    title = [("Buyers' title company", _pair(d.get("buyer_title")) + ("\n" + d["buyer_title_contact"] if d.get("buyer_title_contact") else "")),
             ("Seller's title company", _pair(d.get("seller_title")) + ("\n" + d["seller_title_contact"] if d.get("seller_title_contact") else "")),
             ("Lender", _pair(d.get("lender"), d.get("loan_type")) + ("\n" + d["lender_contact"] if d.get("lender_contact") else ""))]
    agents = [("Buyers' agent", _pair(d.get("buyer_agent")) + ("\n" + d["buyer_agent_contact"] if d.get("buyer_agent_contact") else "")),
              ("Listing agent", _pair(d.get("listing_agent")) + ("\n" + d["listing_agent_contact"] if d.get("listing_agent_contact") else "")),
              ("Transaction coordinator", _pair(d.get("tc_name")) + ("\n" + d["tc_contact"] if d.get("tc_contact") else ""))]
    blocks = [("Key dates and terms", deal), ("Buyers and seller", people), ("Title and financing", title),
              ("Agents and coordination", agents)]
    if d.get("comm_request"):
        blocks.append(("A request", [("", d["comm_request"])]))
    if kind == "private" and d.get("internal_notes"):
        blocks.append(("Private notes", [("", d["internal_notes"])]))
    out = []
    for head, rows in blocks:
        rows = [(a, b.strip()) for a, b in rows if b and str(b).strip()]
        if rows:
            out.append({"title": head, "rows": rows})
    return out


def _sheet_html(tx, d, kind, pdf=False, share_token=None, can_back=True):
    return render_template("tc/sheet.html", tx=tx, kind=kind, blocks=build_blocks(tx, d, kind), pdf=pdf,
                           share_token=share_token, can_back=can_back, address=tx.get("property_address") or "Transaction",
                           mls=d.get("mls"), county=d.get("county"))


def _respond(html, filename, want_pdf):
    if want_pdf:
        try:
            from weasyprint import HTML
            pdf = HTML(string=html).write_pdf()
            return Response(pdf, mimetype="application/pdf",
                            headers={"Content-Disposition": f'attachment; filename="{filename}.pdf"'})
        except Exception as exc:  # no PDF engine on this server: fall back to a print-ready page
            __import__("logging").getLogger(__name__).warning("pdf engine unavailable: %s", exc)
            html = html.replace("</body>", "<script>window.addEventListener('load',function(){window.print();});</script></body>")
    return Response(html, mimetype="text/html")


# ───────────────────────── access ─────────────────────────
def _agent():
    u = _H["get_current_user"]()
    return u if u and u.get("role") == "agent" else None


def _mine(tx_id):
    u = _agent()
    if not u:
        return None, None
    tx = _H["get_tx"](tx_id)
    if not tx or tx.get("agent_id") != u["id"]:
        return u, None
    return u, tx


def _slug(tx):
    return re.sub(r"[^A-Za-z0-9]+", "-", tx.get("property_address") or "transaction").strip("-")[:40]


def _first_emails(text):
    return re.findall(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text or "")


def defaults(tx, user):
    from database import get_user_profile
    p = dict(get_user_profile(user["id"]) or {})
    brokerage = p.get("brokerage_name") or p.get("team_name") or ""
    first = (user.get("name") or "").split(" ")[0]
    d = {"possession": "At closing", "earnest_due_days": "3", "inspection_days": "10",
         "resolution_terms": "5 calendar days after seller receives notice", "contingency": "None",
         "buyer_phones": tx.get("client_phone") or "", "buyer_emails": tx.get("client_email") or "",
         "closing_date": tx.get("target_close_date") or "", "closing_time": "TBD",
         "tc_name": _pair(user.get("name"), brokerage),
         "tc_contact": _pair(p.get("phone"), user.get("email")),
         "comm_request": f"Please copy {first} on transaction emails." if first else ""}
    if not _d(d["closing_date"]):
        d["closing_date"] = ""
    return d


# ───────────────────────── pages ─────────────────────────
@bp.route("/agent/transactions/<int:tx_id>/contract", methods=["GET", "POST"])
def contract(tx_id):
    user, tx = _mine(tx_id)
    if not user:
        return redirect(url_for("login", role="agent"))
    if not tx:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))
    data, token = load(tx_id)
    if request.method == "POST":
        new = {}
        for k in ALL_KEYS:
            v = (request.form.get("f_" + k) or "").strip()[:600]
            if k in DATE_KEYS and v and not _d(v):
                v = ""
            new[k] = v
        token = save(tx_id, new)
        sync_deadlines(tx_id, new)
        try:
            _H["log"](tx_id, "contract", "Contract details updated", user["id"])
        except Exception:
            pass
        flash("Saved. Your deadlines are set and both sheets are ready.", "success")
        return redirect(url_for("agent_transaction_detail", tx_id=tx_id))
    shown = {**defaults(tx, user), **{k: v for k, v in data.items() if v not in (None, "")}} if data else defaults(tx, user)
    return render_template("tc/contract_form.html", tx=tx, sections=SECTIONS, d=shown, has_saved=bool(data),
                           has_ai=bool(__import__("os").environ.get("OPENAI_API_KEY")))


@bp.route("/agent/transactions/<int:tx_id>/sheet/<kind>")
def sheet(tx_id, kind):
    user, tx = _mine(tx_id)
    if not user:
        return redirect(url_for("login", role="agent"))
    if not tx or kind not in ("private", "shareable"):
        abort(404)
    data, token = load(tx_id)
    if not data:
        flash("Add the contract details first and your sheets will be ready.", "error")
        return redirect(url_for("tc.contract", tx_id=tx_id))
    html = _sheet_html(tx, data, kind, pdf=bool(request.args.get("pdf")), share_token=token)
    return _respond(html, f"{kind}-{_slug(tx)}", bool(request.args.get("pdf")))


@bp.route("/tc/s/<token>")
def public_sheet(token):
    """The shareable sheet by secure link (for the other agent, title and lender). Never includes client contacts."""
    conn = _db()
    row = conn.execute("SELECT transaction_id FROM transaction_contract WHERE token=?", (token,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    tx = _H["get_tx"](row["transaction_id"])
    data, _ = load(row["transaction_id"])
    if not tx or not data:
        abort(404)
    html = _sheet_html(tx, data, "shareable", pdf=bool(request.args.get("pdf")), share_token=token, can_back=False)
    return _respond(html, f"transaction-info-{_slug(tx)}", bool(request.args.get("pdf")))


@bp.route("/agent/transactions/<int:tx_id>/deadline/<key>/done", methods=["POST"])
def deadline_done(tx_id, key):
    user, tx = _mine(tx_id)
    if not tx:
        return redirect(url_for("login", role="agent"))
    conn = _db()
    conn.execute("UPDATE transaction_deadlines SET done = 1 - COALESCE(done,0) WHERE transaction_id=? AND key=?", (tx_id, key))
    conn.commit()
    conn.close()
    return redirect(url_for("agent_transaction_detail", tx_id=tx_id) + "#contract-card")


@bp.route("/agent/transactions/<int:tx_id>/share", methods=["POST"])
def share(tx_id):
    """Email the secure link to the shareable sheet. Everyone gets their own email."""
    user, tx = _mine(tx_id)
    if not tx:
        return redirect(url_for("login", role="agent"))
    data, token = load(tx_id)
    back = redirect(url_for("agent_transaction_detail", tx_id=tx_id) + "#contract-card")
    if not data or not token:
        flash("Add the contract details first, then you can share the sheet.", "error")
        return back
    picked = [e.strip().lower() for e in request.form.getlist("to") if "@" in e]
    extra = [e.strip().lower() for e in re.split(r"[,\s;]+", request.form.get("extra") or "") if "@" in e]
    # only addresses that belong to this transaction, plus anything the agent typed on purpose
    allowed = set()
    for k in ("buyer_agent_contact", "listing_agent_contact", "buyer_title_contact", "seller_title_contact",
              "lender_contact", "tc_contact"):
        allowed.update(e.lower() for e in _first_emails(data.get(k)))
    recipients = []
    for e in picked:
        if e in allowed and e not in recipients:
            recipients.append(e)
    for e in extra[:5]:
        if e not in recipients and not re.search(r"\s", e):
            recipients.append(e)
    if not recipients:
        flash("Please choose at least one person to send it to.", "error")
        return back
    link = url_for("tc.public_sheet", token=token, _external=True)
    sender = user.get("name") or "Your agent"
    tc_first = (data.get("tc_name") or user.get("name") or "").split("|")[0].strip().split(" ")[0]
    subject = f"Transaction info: {tx.get('property_address')}"
    body = (f"Hello,\n\nHere is the transaction summary for {tx.get('property_address')}. "
            f"You can view it, print it or download it as a PDF here:\n\n{link}\n\n"
            f"{data.get('comm_request') or (f'Please copy {tc_first} on transaction emails.' if tc_first else '')}\n\n"
            f"Thank you so much,\n{sender}")
    send, bg = _H["send_email"], _H["bg"]
    for e in recipients:
        bg(send, e, subject, body, sender, user.get("email"))
    if user.get("email"):
        bg(send, user["email"], "Copy: " + subject, f"You sent this to: {', '.join(recipients)}\n\n" + body)
    try:
        _H["log"](tx_id, "contract", f"Shared the transaction sheet with {len(recipients)} {'person' if len(recipients) == 1 else 'people'}", user["id"])
    except Exception:
        pass
    flash(f"Sent to {len(recipients)} {'person' if len(recipients) == 1 else 'people'}. A copy is in your inbox.", "success")
    return back


@bp.route("/agent/transactions/<int:tx_id>/share/new-link", methods=["POST"])
def new_link(tx_id):
    """Replace the share link, which switches off any link sent before."""
    user, tx = _mine(tx_id)
    if not tx:
        return redirect(url_for("login", role="agent"))
    conn = _db()
    conn.execute("UPDATE transaction_contract SET token=? WHERE transaction_id=?", (secrets.token_urlsafe(14), tx_id))
    conn.commit()
    conn.close()
    flash("Done. The old share link no longer works. Send the new one when you are ready.", "success")
    return redirect(url_for("agent_transaction_detail", tx_id=tx_id) + "#contract-card")


# ───────────────────────── fill from the contract PDF ─────────────────────────
AI_FIELDS = {
    "contract_date": "contract/acceptance date, YYYY-MM-DD", "effective_date": "effective date if stated, YYYY-MM-DD",
    "closing_date": "closing date, YYYY-MM-DD", "closing_time": "closing time", "possession": "possession terms",
    "seller": "seller name(s)", "mls": "MLS number", "county": "county",
    "earnest_amount": "earnest money amount with $", "earnest_holder": "who holds earnest money",
    "earnest_due_days": "days after contract earnest money is due, number only",
    "seller_brokerage": "seller-paid buyer brokerage compensation with $", "seller_costs": "other seller-paid costs/concessions with $",
    "warranty": "home warranty terms", "contingency": "sale contingency or None",
    "inspection_days": "inspection period in calendar days, number only",
    "buyer_title": "buyer's title company name", "seller_title": "seller's title/escrow company name",
    "lender": "lender name", "loan_type": "loan type",
    "buyer_agent": "buyer's agent name | brokerage", "listing_agent": "listing agent name | brokerage",
}


@bp.route("/agent/transactions/<int:tx_id>/contract/upload", methods=["POST"])
def upload(tx_id):
    user, tx = _mine(tx_id)
    if not tx:
        return redirect(url_for("login", role="agent"))
    back = redirect(url_for("tc.contract", tx_id=tx_id))
    f = request.files.get("contract")
    if not f or not f.filename.lower().endswith(".pdf"):
        flash("Please choose the contract as a PDF.", "error")
        return back
    try:
        from pypdf import PdfReader
        text = "\n".join((p.extract_text() or "") for p in PdfReader(f.stream).pages)[:14000]
    except Exception:
        text = ""
    if len(text.strip()) < 200:
        flash("That PDF looks like a scan, so we could not read it. You can still fill the form in by hand.", "error")
        return back
    import os
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        flash("Auto-fill needs the site's AI key. You can fill the form in by hand for now.", "error")
        return back
    try:
        from openai import OpenAI
        client = OpenAI(api_key=key, timeout=60.0)
        spec = "\n".join(f"- {k}: {v}" for k, v in AI_FIELDS.items())
        r = client.chat.completions.create(
            model="gpt-4o-mini", temperature=0, max_tokens=900, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": "You read real estate purchase contracts and return JSON only. "
                       "Use an empty string for anything not clearly stated. Never guess."},
                      {"role": "user", "content": f"Return a JSON object with these keys:\n{spec}\n\nContract text:\n{text}"}])
        found = json.loads(r.choices[0].message.content or "{}")
    except Exception:
        flash("We could not read that contract just now. You can fill the form in by hand.", "error")
        return back
    data, _ = load(tx_id)
    base = {**defaults(tx, user), **{k: v for k, v in data.items() if v}}
    filled = 0
    for k in AI_FIELDS:
        v = str(found.get(k) or "").strip()[:300]
        if not v or base.get(k) not in (None, "") and data.get(k):
            continue
        if k in DATE_KEYS and not _d(v):
            continue
        if k.endswith("_days") and _int(re.sub(r"\D", "", v) or "x") is None:
            continue
        base[k] = re.sub(r"\D", "", v) if k.endswith("_days") else v
        filled += 1
    save(tx_id, {k: base.get(k, "") for k in ALL_KEYS})
    flash(f"We filled in {filled} details from your contract. Please check them before you share anything.", "success")
    return back


# ───────────────────────── detail page card ─────────────────────────
def card_context(tx_id):
    data, token = load(tx_id)
    dl = deadlines(tx_id) if data else []
    upcoming = [r for r in dl if not r["done"]][:4]
    missing = []
    if data:
        for k, label in (("contract_date", "contract date"), ("closing_date", "closing date"), ("earnest_amount", "earnest money"),
                         ("listing_agent", "listing agent"), ("buyer_title", "title company"), ("lender", "lender")):
            if not data.get(k) and not (k == "buyer_title" and data.get("seller_title")):
                missing.append(label)
    recipients = []
    if data:
        for key, label in (("listing_agent_contact", "Listing agent"), ("buyer_title_contact", "Buyers' title"),
                           ("seller_title_contact", "Seller's title"), ("lender_contact", "Lender")):
            for e in _first_emails(data.get(key)):
                if e.lower() not in [r["email"] for r in recipients]:
                    recipients.append({"email": e.lower(), "label": label})
    return {"has_data": bool(data), "upcoming": upcoming, "all": dl, "missing": missing, "recipients": recipients,
            "link": url_for("tc.public_sheet", token=token, _external=True) if token else ""}


# ───────────────────────── reminders ─────────────────────────
def send_deadline_reminders(today=None):
    """One friendly email per agent per day: deadlines in two days and deadlines today. Never repeats."""
    import os
    send = _H.get("send_email")
    if not send:
        return 0
    today = today or date.today()
    conn = _db()
    rows = conn.execute("""SELECT d.*, t.property_address, t.agent_id, u.email AS agent_email, u.name AS agent_name
                           FROM transaction_deadlines d JOIN transactions t ON t.id = d.transaction_id
                           JOIN users u ON u.id = t.agent_id
                           WHERE COALESCE(d.done,0)=0 AND COALESCE(t.status,'active')='active'
                             AND d.due_date IN (?,?)""",
                        (today.isoformat(), (today + timedelta(days=2)).isoformat())).fetchall()
    by_agent = {}
    for r in rows:
        stage = "0d" if r["due_date"] == today.isoformat() else "2d"
        if stage in (r["reminded"] or "").split(","):
            continue
        by_agent.setdefault((r["agent_id"], r["agent_email"], r["agent_name"]), []).append((r, stage))
    site = os.environ.get("YLH_SITE_URL", "https://itsyourlifeyourhome.com")
    sent = 0
    for (aid, email, name), items in by_agent.items():
        if not email:
            continue
        first = (name or "there").split(" ")[0]
        lines = []
        for r, stage in items:
            when = "TODAY" if stage == "0d" else "in 2 days"
            lines.append(f"{r['label']}, {when} ({short_date(r['due_date'])})\n{r['property_address']}\n{site}/agent/transactions/{r['transaction_id']}")
        body = (f"Hi {first},\n\nA gentle heads-up on what is coming up:\n\n" + "\n\n".join(lines)
                + "\n\nOnce something is done, tick it off on the transaction page and it will stop showing up.\n\nYou have got this!")
        try:
            send(email, f"Coming up: {items[0][0]['label']} at {items[0][0]['property_address']}"
                 + (f" (+{len(items) - 1} more)" if len(items) > 1 else ""), body)
        except Exception:
            continue
        for r, stage in items:
            conn.execute("UPDATE transaction_deadlines SET reminded=? WHERE id=?",
                         ((r["reminded"] + "," if r["reminded"] else "") + stage, r["id"]))
        conn.commit()
        sent += 1
    conn.close()
    return sent


def init_app(app, get_current_user, bg, send_email, get_tx, log_event):
    _H.update(get_current_user=get_current_user, bg=bg, send_email=send_email, get_tx=get_tx, log=log_event)
    ensure_tables()
    app.register_blueprint(bp)
