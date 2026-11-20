"""The simple, three-tab front door for each kind of account.

Homeowner: My Home, Home Value, My Team.   Agent: My Clients, Send an Update, Messages.   Lender: My Clients, Shared Scenarios, Messages.
Everything else stays available under "More" in the menu. This module holds the pages that did not exist before (My Home, My Clients,
Send an Update, home set-up) and the tab bar that shows on every signed-in page."""
import secrets
from datetime import date, datetime

from flask import Blueprint, flash, redirect, render_template, request, url_for

bp = Blueprint("portal", __name__)
_H = {}


def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    conn.execute("""CREATE TABLE IF NOT EXISTS client_invites (
        id INTEGER PRIMARY KEY AUTOINCREMENT, pro_id INTEGER NOT NULL, pro_role TEXT NOT NULL, name TEXT NOT NULL, email TEXT NOT NULL,
        phone TEXT DEFAULT '', address TEXT DEFAULT '', move_in_date TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()


def _me(role):
    u = _H["get_current_user"]()
    return u if u and u.get("role") == role else None


def _need(role):
    flash("Please sign in first.", "error")
    return redirect(url_for("login"))


def _valid_date(s):
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def team_blurb(agent_id=None, lender_id=None):
    """'Jane Doe at Acme Realty and Sam Lee at Best Mortgage', for friendly messages."""
    from database import get_user_by_id, get_user_profile
    bits = []
    for pid in (agent_id, lender_id):
        if not pid:
            continue
        u = get_user_by_id(pid)
        if not u:
            continue
        u = dict(u)
        p = get_user_profile(pid)
        p = dict(p) if p else {}
        org = p.get("brokerage_name") or p.get("team_name") or ""
        bits.append(f"{u.get('name')} at {org}" if org else (u.get("name") or ""))
    return " and ".join(b for b in bits if b)


# ───────────────────────── tab bar ─────────────────────────
def tab_context():
    from flask import request as rq
    from team_messages import unread_count
    u = _H["get_current_user"]()
    ep = rq.endpoint or ""
    if not u or ep in _H["ns"]["PUBLIC_PAGES"] or u.get("role") not in ("homeowner", "agent", "lender"):
        return {"tabs": [], "unread_messages": 0}
    role, unread = u["role"], unread_count(u)
    if role == "homeowner":
        value = ep.startswith("homeowner_value") or ep.startswith("homeowner_next_") or ep == "homeowner_home.refinance_page"
        team = ep.startswith("team.") or ep == "homeowner_support_get_help"
        tabs = [("My Home", url_for("portal.my_home"), not value and not team, 0),
                ("Home Value", url_for("homeowner_value_equity_overview"), value, 0),
                ("My Team", url_for("team.my_team"), team, unread)]
    elif role == "agent":
        tabs = [("My Clients", url_for("portal.agent_my_clients"), ep in {"portal.agent_my_clients", "agent_clients", "agent_client_detail", "agent_referrals"}, 0),
                ("Send an Update", url_for("portal.send_update"), ep == "portal.send_update" or ep.startswith("care_alerts.frost"), 0),
                ("Messages", url_for("team.pro_messages"), ep.startswith("team."), unread)]
    else:
        tabs = [("My Clients", url_for("lender_clients"), ep in {"lender_clients", "lender_crm"}, 0),
                ("Shared Scenarios", url_for("team.shared_scenarios"), ep == "team.shared_scenarios", 0),
                ("Messages", url_for("team.pro_messages"), ep in {"team.pro_messages", "team.pro_thread"}, unread)]
    if role in ("agent", "lender"):
        tabs = []  # agents and lenders use the grouped menu; the same links in a second bar were just noise
    # Deeper pages (CRM, Financials, Marketing Hub and so on) get one plain way back to the day's main page.
    back_home = None
    if True:
        if role == "agent" and ep != "agent_dashboard":
            back_home = ("Dashboard", url_for("agent_dashboard"))
        elif role == "lender" and ep != "lender_dashboard":
            back_home = ("Dashboard", url_for("lender_dashboard"))
        elif role == "homeowner" and ep != "portal.my_home":
            back_home = ("My Home", url_for("portal.my_home"))
    return {"tabs": tabs, "unread_messages": unread, "back_home": back_home}


# ───────────────────────── homeowner: My Home ─────────────────────────
def next_up(details, today=None):
    """The next few things this house needs, picked for the season and for what the homeowner told us about the home."""
    m = (today or date.today()).month
    out = []
    if m in (10, 11, 12, 1, 2, 3):
        if details.get("outdoor_faucets"):
            out.append(("Disconnect garden hoses and drain outdoor faucets", "A hard freeze can burst a pipe that still has water in it."))
        if details.get("sprinkler") and m in (10, 11, 12):
            out.append(("Have your sprinkler system drained or blown out", "This keeps the lines from freezing and cracking."))
        if details.get("fireplace"):
            out.append(("Have the chimney checked before heavy use", "A yearly sweep keeps your fireplace safe."))
        out.append(("Change your furnace filter", "A clean filter helps your home heat evenly and saves energy."))
    elif m in (4, 5, 6):
        if details.get("sump_pump"):
            out.append(("Test your sump pump", "Pour a bucket of water in the pit and make sure it kicks on."))
        out.append(("Clean your gutters and check the roof", "Spring storms are easier on a home with clear gutters."))
        out.append(("Have your air conditioner serviced", "A tune-up now beats a breakdown on the first hot day."))
    elif m in (7, 8):
        out.append(("Change your air filter", "Summer is the hardest season on your system."))
        out.append(("Clean the dryer vent", "Lint buildup is a common cause of house fires."))
        out.append(("Check around windows and doors for gaps", "Sealing gaps keeps the cool air in."))
    else:
        if details.get("sprinkler"):
            out.append(("Plan to winterize your sprinkler system", "Do it before the first hard freeze."))
        out.append(("Clean your gutters before the leaves finish falling", "Clogged gutters are a top cause of water damage."))
        out.append(("Schedule a furnace tune-up", "Fall is the easiest time to get on a technician's calendar."))
    return out[:3]


MORE_HOME_LINKS = [
    ("Home timeline", "homeowner_home_timeline"), ("Home report", "homeowner_home.home_report"),
    ("Warranties and appliances", "homeowner_care_warranty_log"), ("Renovation planner", "homeowner_reno_planner"),
    ("Design boards", "homeowner_saved_notes"), ("Care guide", "homeowner_care_maintenance_guide"),
    ("Seasonal checklists", "homeowner_care_seasonal_checklists"), ("Safety and protection", "homeowner_care_home_protection"),
    ("Energy savings", "homeowner_care_energy_savings"), ("Trusted pros", "homeowner_home.trusted_pros"),
    ("Buy and sell guide", "homeowner_next_buy_sell_guidance"), ("Affordability", "homeowner_next_affordability"),
    ("Loan paths", "homeowner_next_loan_paths"), ("Refinance and payoff", "homeowner_home.refinance_page"),
    ("My buyer profile", "homeowner_next_plan_move"), ("Get help", "homeowner_support_get_help"),
]


def _overview_data(u):
    """The useful parts of the old Full home overview: value card, focus and steps, transaction, properties, recent activity."""
    uid = u["id"]
    extras = snapshot = active = None
    recent = []
    try:
        from homeowner_home import overview_extras
        extras = overview_extras(uid)
    except Exception as e:
        print(f"[My Home] extras skipped: {e}")
    try:
        from database import get_primary_property, get_homeowner_snapshot_for_property
        prop = get_primary_property(uid)
        snapshot = get_homeowner_snapshot_for_property(uid, prop.get("id")) if prop else None
        if snapshot and snapshot.get("value_estimate") and snapshot.get("loan_balance"):
            snapshot["equity_estimate"] = snapshot["value_estimate"] - snapshot["loan_balance"]
    except Exception as e:
        print(f"[My Home] snapshot skipped: {e}")
    try:
        em = (u.get("email") or "").lower().strip()
        conn = _db()
        try:
            row = conn.execute("""SELECT *, current_stage AS stage, target_close_date AS close_date FROM transactions
                   WHERE (homeowner_user_id = ? OR (? <> '' AND lower(client_email) = ?)) AND status = 'active'
                     AND current_stage NOT IN ('closed','cancelled') ORDER BY created_at DESC LIMIT 1""", (uid, em, em)).fetchone()
        finally:
            conn.close()
        active = dict(row) if row else None
    except Exception as e:
        print(f"[My Home] transaction skipped: {e}")
    try:
        import automation
        recent = automation.homeowner_activity(uid, limit=5)
        for a in recent:
            a["link_url"] = url_for(a["endpoint"])
    except Exception as e:
        print(f"[My Home] activity skipped: {e}")
    return extras, snapshot, active, recent


@bp.route("/homeowner/my-home")
def my_home():
    u = _me("homeowner")
    if not u:
        return _need("homeowner")
    from database import get_primary_property, list_homeowner_documents
    from care_alerts import get_details
    from team_messages import pros_for
    d = get_details(u["id"])
    try:
        prop = get_primary_property(u["id"])
    except Exception:
        prop = None
    try:
        docs = [dict(x) for x in list_homeowner_documents(u["id"])][:5]
    except Exception:
        docs = []
    d["move_in_nice"] = ""
    if d.get("move_in_date"):
        try:
            dd = datetime.strptime(d["move_in_date"][:10], "%Y-%m-%d").date()
            d["move_in_nice"] = f"{dd.strftime('%B')} {dd.day}, {dd.year}"
        except ValueError:
            pass
    more = [(label, url_for(ep)) for label, ep in MORE_HOME_LINKS]
    extras, snapshot, active_transaction, recent_items = _overview_data(u)
    return render_template("homeowner/my_home.html", d=d, address=(prop or {}).get("address") if prop else "", docs=docs, nexts=next_up(d),
                           team=pros_for(u["id"]), more=more, extras=extras, snapshot=snapshot, active_transaction=active_transaction,
                           recent_items=recent_items, homeowner=u)


# ───────────────────────── homeowner: set up my home (the closing link lands here) ─────────────────────────
def _invite_for(homeowner):
    """Whatever the agent or lender already filled in for this person when they invited them."""
    from team_messages import pros_for
    ids = [p["id"] for p in pros_for(homeowner["id"]).values()]
    if not ids or not homeowner.get("email"):
        return {}
    conn = _db()
    try:
        marks = ",".join("?" * len(ids))
        r = conn.execute(f"SELECT * FROM client_invites WHERE pro_id IN ({marks}) AND lower(email) = ? ORDER BY id DESC LIMIT 1",
                         (*ids, homeowner["email"].strip().lower())).fetchone()
    finally:
        conn.close()
    return dict(r) if r else {}


@bp.route("/homeowner/setup", methods=["GET", "POST"])
def setup():
    u = _me("homeowner")
    if not u:
        return _need("homeowner")
    from database import add_property, get_primary_property
    from care_alerts import get_details
    from team_messages import pros_for
    team = pros_for(u["id"])
    try:
        prop = get_primary_property(u["id"])
    except Exception:
        prop = None
    if request.method == "POST":
        address = (request.form.get("address") or "").strip()[:250]
        move_in = _valid_date(request.form.get("move_in_date"))
        flag = lambda n: 1 if request.form.get(n) == "on" else 0
        conn = _db()
        try:
            conn.execute("""INSERT INTO home_details (user_id, sprinkler, outdoor_faucets, fireplace, sump_pump, move_in_date) VALUES (?,?,?,?,?,?)
                            ON CONFLICT(user_id) DO UPDATE SET sprinkler=excluded.sprinkler, outdoor_faucets=excluded.outdoor_faucets,
                            fireplace=excluded.fireplace, sump_pump=excluded.sump_pump, move_in_date=excluded.move_in_date""",
                         (u["id"], flag("sprinkler"), flag("outdoor_faucets"), flag("fireplace"), flag("sump_pump"), move_in))
            if address:
                if prop:
                    conn.execute("UPDATE properties SET address = ? WHERE id = ? AND user_id = ?", (address, prop["id"], u["id"]))
            conn.commit()
        finally:
            conn.close()
        if address and not prop:
            add_property(u["id"], address)
        flash("Your home is set up. Welcome!", "success")
        return redirect(url_for("portal.my_home"))
    inv = _invite_for(u)
    d = get_details(u["id"])
    return render_template("homeowner/setup.html", team=team, d=d,
                           address=(prop or {}).get("address") if prop else inv.get("address", ""),
                           move_in=d.get("move_in_date") or inv.get("move_in_date", ""))


# ───────────────────────── homeowner: My Profile ─────────────────────────
@bp.route("/homeowner/profile", methods=["GET", "POST"])
def my_profile():
    u = _me("homeowner")
    if not u:
        return _need("homeowner")
    from flask import session
    conn = _db()
    try:
        if request.method == "POST":
            f = request.form
            name = " ".join((f.get("name") or "").split())[:120]
            phone = (f.get("phone") or "").strip()[:40]
            if not name:
                flash("Please add your name.", "error")
                return redirect(url_for("portal.my_profile"))
            flag = lambda k: 1 if f.get(k) == "on" else 0
            conn.execute("UPDATE users SET name = ?, phone = ?, digest_enabled = ? WHERE id = ?", (name, phone, flag("digest_enabled"), u["id"]))
            conn.execute("""INSERT INTO care_prefs (user_id, frost_alerts, seasonal_tips) VALUES (?,?,?)
                            ON CONFLICT(user_id) DO UPDATE SET frost_alerts=excluded.frost_alerts, seasonal_tips=excluded.seasonal_tips""",
                         (u["id"], flag("frost_alerts"), flag("seasonal_tips")))
            conn.commit()
            session["name"] = name
            flash("Your profile is saved.", "success")
            return redirect(url_for("portal.my_profile"))
        row = conn.execute("SELECT name, email, phone, digest_enabled FROM users WHERE id = ?", (u["id"],)).fetchone()
    finally:
        conn.close()
    from care_alerts import get_prefs
    p = get_prefs(u["id"])
    me = {"name": row["name"] or "", "email": row["email"] or "", "phone": row["phone"] or "",
          "digest_enabled": 1 if row["digest_enabled"] in (None, 1) else 0}
    return render_template("homeowner/my_profile.html", me=me, p=p)


# ───────────────────────── agent: My Clients ─────────────────────────
def _personal_link(pro_id, role="agent"):
    from database import create_referral_link, get_referral_links_for_agent, get_referral_links_for_lender
    get = get_referral_links_for_lender if role == "lender" else get_referral_links_for_agent
    links = get(pro_id)
    if not links:
        create_referral_link(**({"lender_id": pro_id} if role == "lender" else {"agent_id": pro_id}))
        links = get(pro_id)
    token = dict(links[0])["token"] if links else ""
    return request.url_root.rstrip("/") + f"/signup?role=homeowner&ref={token}" if token else ""


@bp.route("/agent/my-clients")
def agent_my_clients():
    return _clients_view("agent")


def lender_my_clients():
    return _clients_view("lender")


def _clients_view(role):
    u = _me(role)
    if not u:
        return _need(role)
    from database import get_agent_clients, get_lender_clients
    from care_alerts import _clean_phone, sms_link
    clients = [dict(c) for c in (get_lender_clients if role == "lender" else get_agent_clients)(u["id"])]
    conn = _db()
    try:
        ids = [c["id"] for c in clients]
        marks = ",".join("?" * len(ids))
        moves = {r["user_id"]: r["move_in_date"] for r in conn.execute(f"SELECT user_id, move_in_date FROM home_details WHERE user_id IN ({marks})", ids).fetchall()} if ids else {}
        phones = {r["id"]: r["phone"] for r in conn.execute(f"SELECT id, phone FROM users WHERE id IN ({marks})", ids).fetchall()} if ids else {}
        emails = {c["email"].strip().lower() for c in clients if c.get("email")}
        pending = [dict(r) for r in conn.execute("SELECT * FROM client_invites WHERE pro_id = ? AND pro_role = ? ORDER BY id DESC LIMIT 50", (u["id"], role)).fetchall()
                   if (r["email"] or "").strip().lower() not in emails]
    finally:
        conn.close()
    for c in clients:
        c["move_in"] = moves.get(c["id"]) or ""
        c["phone"] = _clean_phone(phones.get(c["id"]))
        c["sms"] = sms_link(c["phone"], f"Hi {(c.get('name') or '').split(' ')[0] or 'there'}, it's {u.get('name')}. ") if c["phone"] else ""
    conn = _db()
    try:
        conn.execute("""CREATE TABLE IF NOT EXISTS home_value_requests (id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER, user_id INTEGER,
            name TEXT, email TEXT, phone TEXT, address TEXT, note TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
        values = [dict(r) for r in conn.execute("SELECT * FROM home_value_requests WHERE agent_id = ? ORDER BY id DESC LIMIT 20", (u["id"],)).fetchall()] if role == "agent" else []
    finally:
        conn.close()
    link = _personal_link(u["id"], role)
    inv_id = request.args.get("invited", type=int)
    just = next((p for p in pending if p["id"] == inv_id), None)
    if just:
        first = (just["name"] or "").split(" ")[0] or "there"
        just["text"] = (f"Hi {first}, it's {u.get('name')}. Congratulations on your new home! Here is your personal link to set up your home "
                        f"dashboard. It takes about a minute: {link}")
        just["sms"] = sms_link(_clean_phone(just["phone"]), just["text"]) if just.get("phone") else ""
    conn = _db()
    try:
        crm_total = conn.execute("SELECT COUNT(*) FROM " + ("lender_borrowers WHERE lender_user_id" if role == "lender" else "agent_contacts WHERE agent_user_id") + " = ?", (u["id"],)).fetchone()[0]
    finally:
        conn.close()
    return render_template(f"{role}/my_clients.html", clients=clients, pending=pending, link=link, just=just, value_requests=values, role=role, crm_total=crm_total)


def _back(role, **kw):
    return redirect(url_for("lender_clients" if role == "lender" else "portal.agent_my_clients", **kw))


@bp.route("/agent/my-clients/invite", methods=["POST"])
def agent_invite():
    return _invite("agent")


@bp.route("/lender/my-clients/invite", methods=["POST"])
def lender_invite():
    return _invite("lender")


def _invite(role):
    u = _me(role)
    if not u:
        return _need(role)
    f = request.form
    name, email = (f.get("name") or "").strip()[:120], (f.get("email") or "").strip().lower()[:200]
    if not name or "@" not in email:
        flash("Add their name and a valid email so we can set them up.", "error")
        return _back(role)
    phone, address, move_in = (f.get("phone") or "").strip()[:40], (f.get("address") or "").strip()[:250], _valid_date(f.get("move_in_date"))
    conn = _db()
    try:
        iid = conn.execute("INSERT INTO client_invites (pro_id, pro_role, name, email, phone, address, move_in_date) VALUES (?,?,?,?,?,?,?)",
                           (u["id"], role, name, email, phone, address, move_in)).lastrowid
        conn.commit()
    finally:
        conn.close()
    try:   # keep the CRM in step: the move-in date becomes their home anniversary
        if role != "agent":
            raise RuntimeError("agents only")
        from database import add_agent_contact, list_agent_contacts
        if not any((dict(c).get("email") or "").strip().lower() == email for c in list_agent_contacts(u["id"])):
            add_agent_contact(agent_user_id=u["id"], name=name, email=email, phone=phone, stage="new", property_address=address,
                              home_anniversary=move_in, notes="Invited from My Clients", tags="invite")
    except Exception as e:
        if role == "agent":
            print(f"[WARNING] invite CRM add skipped: {e}")
    link = _personal_link(u["id"], role)
    if f.get("send_email"):
        ns = _H["ns"]
        body = (f"Hi {name.split(' ')[0]},\n\nCongratulations on your new home! I set up a free home dashboard for you. It keeps your home "
                f"details, documents and care reminders in one place, and you can message me right there.\n\nSet it up here (it takes about a minute):\n{link}\n")
        ns["_bg"](ns["send_reminder_email"], email, f"{u.get('name')} set up your home dashboard", body, **ns["pro_sender"](u["id"]))
    flash(f"Invite ready for {name}." + (" We also emailed it to them." if f.get("send_email") else ""), "success")
    return _back(role, invited=iid)


@bp.route("/agent/my-clients/<int:client_id>/move-in", methods=["POST"])
def agent_move_in(client_id):
    return _move_in("agent", client_id)


@bp.route("/lender/my-clients/<int:client_id>/move-in", methods=["POST"])
def lender_move_in(client_id):
    return _move_in("lender", client_id)


def _move_in(role, client_id):
    u = _me(role)
    if not u:
        return _need(role)
    from database import get_agent_clients, get_lender_clients
    if client_id not in {c["id"] for c in (get_lender_clients if role == "lender" else get_agent_clients)(u["id"])}:
        flash("That client is not connected to your account.", "error")
        return _back(role)
    move_in = _valid_date(request.form.get("move_in_date"))
    if not move_in:
        flash("Pick a move-in date first.", "error")
        return _back(role)
    conn = _db()
    try:
        conn.execute("""INSERT INTO home_details (user_id, move_in_date) VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE SET move_in_date = excluded.move_in_date""",
                     (client_id, move_in))
        if role == "agent":
            conn.execute("UPDATE agent_contacts SET home_anniversary = ? WHERE user_id = ? AND agent_user_id = ?", (move_in, client_id, u["id"]))
        conn.commit()
    finally:
        conn.close()
    flash("Move-in date saved.", "success")
    return _back(role)


# ───────────────────────── agent: Send an Update ─────────────────────────
UPDATES = {
    "freeze": ("Freeze reminder", "Freezing temperatures ahead: a quick heads-up for your home", None),
    "fall": ("Fall check-in", "A quick fall check-in for your home",
             "Hi {first},\n\nFall is the easiest time to get your home ready for winter. A few quick things to do:\n"
             "- Clean the gutters once the leaves are down\n- Change your furnace filter\n- Disconnect garden hoses and drain outdoor faucets\n"
             "- Test your smoke and carbon monoxide alarms\n\nIf you need a name for a plumber, roofer or HVAC company, just ask. I am happy to help."),
    "thanks": ("Thank you", "Thinking of you",
               "Hi {first},\n\nI was thinking of you and wanted to say thank you for letting me be part of your home story. It means a lot.\n\n"
               "If there is anything I can do for you or your home, I am only a message away."),
    "checkin": ("Just checking in", "Just checking in",
                "Hi {first},\n\nI wanted to check in and see how the house is treating you. If anything needs attention, or you have questions "
                "about your home's value, I would love to help.\n\nNo need to reply unless you want to."),
}


def _update_text(key):
    from care_alerts import draft_message
    label, subject, body = UPDATES[key]
    return subject, (body if body is not None else draft_message())


def _left_out(agent_id):
    """CRM contacts who have an email but are not on the list, with the plain reason why (so nobody wonders where they went)."""
    from care_alerts import people_for
    from database import list_agent_contacts
    listed = {p["email"].strip().lower() for p in people_for("agent", agent_id) if p["email"]}
    out, seen = [], set()
    for c in list_agent_contacts(agent_id):
        c = dict(c)
        email = (c.get("email") or "").strip()
        if not email or email.lower() in listed or email.lower() in seen:
            continue
        seen.add(email.lower())
        out.append({"name": c.get("name") or email, "email": email, "reason": "No home address saved yet"})
    return out[:200]


@bp.route("/agent/send-update")
def send_update():
    u = _me("agent")
    if not u:
        return _need("agent")
    from care_alerts import people_for
    people = [p for p in people_for("agent", u["id"]) if p["email"]]
    options = {k: {"label": v[0], "subject": _update_text(k)[0], "body": _update_text(k)[1]} for k, v in UPDATES.items()}
    first = options["freeze"]
    return render_template("agent/send_update.html", people=people, options=options, subject=first["subject"], body=first["body"],
                           left_out=_left_out(u["id"]))


@bp.route("/agent/send-update/send", methods=["POST"])
def send_update_go():
    u = _me("agent")
    if not u:
        return _need("agent")
    from care_alerts import people_for
    keys = set(request.form.getlist("who"))
    subject = (request.form.get("subject") or "").strip()[:200]
    base = (request.form.get("message") or "").strip()[:5000]
    if not keys or not base or not subject:
        flash("Choose at least one person, and keep a subject and a message.", "error")
        return redirect(url_for("portal.send_update"))
    ns = _H["ns"]
    mine = {p["key"]: p for p in people_for("agent", u["id"])}      # only people who really belong to this agent
    sender = ns["pro_sender"](u["id"])
    has_sig = bool(sender.get("signature"))
    site = ns["_site_url"]().rstrip("/")
    sent = skipped = 0
    for k in list(keys)[:300]:
        p = mine.get(k)
        if not p or not p["email"] or not p["ok"]:
            skipped += 1
            continue
        body = base.replace("{first}", (p["name"] or "there").split(" ")[0])
        if not has_sig:
            body += f"\n\n{u.get('name') or ''}"
        body += (f"\n\nYou can choose which home notes you get any time here: {site}/homeowner/care/preferences" if p.get("portal")
                 else "\n\nIf you would rather not get notes like this, just reply and let me know.")
        ns["_bg"](ns["send_reminder_email"], p["email"], subject, body, **sender)
        sent += 1
    flash(f"Sent to {sent} {'person' if sent == 1 else 'people'}." + (f" Skipped {skipped} who opted out or have no email." if skipped else ""), "success")
    return redirect(url_for("portal.send_update"))


def init_app(app, get_current_user, ns):
    _H.update(get_current_user=get_current_user, ns=ns)
    ensure_tables()
    app.register_blueprint(bp)
    app.context_processor(tab_context)
