"""Help Board: agents and lenders ask each other for a hand.

An agent can post "Need someone to host my open house" or "Need a showing covered", and a lender can post a request too.
The poster chooses who may see it: people on the same MLS, people at the same brokerage, or only people they invite by email.
Someone taps "I will take it" and both people get each other's contact details. Posts hold only an address, a time and a
short note; client names and phone numbers are never part of a post, and the app never handles money."""
import re
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

bp = Blueprint("helpboard", __name__)
_H = {}
NL = chr(10)
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
KINDS = {
    "open_house": ("Host my open house", "Open house"),
    "showing": ("Cover a showing", "Showing"),
    "other": ("Something else", "Other help"),
}
# Suggestions only; anyone can type their own.
MLS_SUGGESTIONS = [
    "Heartland MLS", "Canopy MLS", "CRMLS", "Bright MLS", "Stellar MLS", "NTREIS", "HAR (Houston)", "REcolorado",
    "Northwest MLS", "MLS PIN", "Beaches MLS", "Triangle MLS", "FMLS (Georgia)", "Midwest Real Estate Data (MRED)",
    "Regional MLS", "SmartMLS", "Hudson Gateway MLS", "Greater Las Vegas MLS", "ARMLS (Arizona)", "UtahRealEstate.com",
    "ACTRIS (Austin)", "Alaska MLS", "BAREIS (Bay Area)", "Cape Cod and Islands MLS", "Central Virginia Regional MLS (CVR MLS)",
    "Charleston Trident MLS", "CincyMLS (Cincinnati)", "Coastal Carolinas MLS", "Columbus REALTORS MLS", "Des Moines Area MLS (DMAAR)",
    "Georgia MLS (GAMLS)", "Greater Greenville MLS", "GSMLS (Garden State)", "Gulf South Real Estate Information Network (GSREIN)",
    "HiCentral MLS (Hawaii)", "Intermountain MLS (Idaho)", "Indiana Regional MLS (IRMLS)", "IRES (Northern Colorado)",
    "Maine Listings", "MetroList (Sacramento)", "Metro MLS (Milwaukee)", "MFRMLS (My Florida Regional)", "MIBOR (Indianapolis)",
    "Miami MLS", "MLS Grand Rapids", "MLSListings (Silicon Valley)", "MLSOK (Oklahoma)", "Montana Regional MLS",
    "NEREN (New England)", "NJMLS", "North Florida MLS", "NorthstarMLS (Minnesota)", "Northern Nevada Regional MLS",
    "NYSAMLS (New York State)", "OneKey MLS (New York)", "Pikes Peak MLS", "Realcomp (Detroit)", "RealTracs (Nashville)",
    "RMLS (Portland)", "SABOR (San Antonio)", "Sandicor (San Diego)", "Southwest Florida MLS", "Southwest MLS (New Mexico)",
    "South Central Wisconsin MLS", "Willamette Valley MLS", "Central Oregon MLS", "West Penn MLS (Pittsburgh)", "MLS of Memphis (MAAR)",
    "Mid America Regional Information Systems (MARIS, St. Louis)", "Great Plains Regional MLS (Nebraska)", "MLS Now (Northeast Ohio)",
]
_COMPANY_WORDS = {"realty", "real", "estate", "group", "inc", "llc", "co", "company", "brokerage", "the", "and", "of", "associates", "properties"}


def _db():
    from database import get_connection
    return get_connection()


def _mls_options():
    """Our list plus any MLS an agent here has already typed in, so the list grows by itself."""
    seen = {norm_mls(x) for x in MLS_SUGGESTIONS}
    extra = []
    try:
        conn = _db()
        rows = conn.execute("SELECT DISTINCT mls_name FROM user_profiles WHERE mls_name IS NOT NULL AND TRIM(mls_name) <> ''").fetchall()
        conn.close()
        for r in rows:
            name = (r[0] or "").strip()
            if name and norm_mls(name) not in seen:
                seen.add(norm_mls(name))
                extra.append(name)
    except Exception:
        pass
    return MLS_SUGGESTIONS + sorted(extra, key=str.lower)


def norm_mls(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def norm_brokerage(s):
    words = [w for w in re.sub(r"[^a-z0-9 ]", " ", (s or "").lower()).split() if w not in _COMPANY_WORDS]
    return "".join(words)


def ensure_tables():
    conn = _db()
    conn.execute("""CREATE TABLE IF NOT EXISTS help_posts (
        id INTEGER PRIMARY KEY AUTOINCREMENT, author_id INTEGER NOT NULL, kind TEXT NOT NULL DEFAULT 'other',
        title TEXT NOT NULL DEFAULT '', address TEXT DEFAULT '', post_date TEXT NOT NULL DEFAULT '', start_time TEXT DEFAULT '',
        end_time TEXT DEFAULT '', details TEXT DEFAULT '', audience TEXT NOT NULL DEFAULT 'custom',
        mls_norm TEXT DEFAULT '', brokerage_norm TEXT DEFAULT '', audience_label TEXT DEFAULT '',
        status TEXT NOT NULL DEFAULT 'open', claimed_by INTEGER, claimed_at TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_help_posts_open ON help_posts (status, post_date)")
    conn.execute("""CREATE TABLE IF NOT EXISTS help_invites (
        post_id INTEGER NOT NULL, user_id INTEGER NOT NULL, PRIMARY KEY (post_id, user_id))""")
    for ddl in ("ALTER TABLE user_profiles ADD COLUMN mls_name TEXT", "ALTER TABLE help_posts ADD COLUMN reminded INTEGER DEFAULT 0",
                "ALTER TABLE help_posts ADD COLUMN thanked_at TEXT", "ALTER TABLE help_posts ADD COLUMN thanks_note TEXT"):
        try:
            conn.execute(ddl)
        except Exception:
            pass
    conn.commit()
    conn.close()


def _user():
    u = _H["get_current_user"]()
    return u if u and u.get("role") in ("agent", "lender") else None


def _clean(s, n=1000):
    return re.sub(r"[\r\x00]", "", (s or "")).strip()[:n]


def _valid_date(s):
    try:
        return datetime.strptime((s or "")[:10], "%Y-%m-%d").date().isoformat()
    except ValueError:
        return ""


def nice_date(s):
    try:
        d = datetime.strptime((s or "")[:10], "%Y-%m-%d").date()
    except ValueError:
        return ""
    days = (d - date.today()).days
    base = f"{MONTHS[d.month - 1][:3]} {d.day}"
    return "Today, " + base if days == 0 else ("Tomorrow, " + base if days == 1 else base)


def time_range(a, b):
    a, b = (a or "").strip(), (b or "").strip()
    return f"{a} to {b}" if a and b else (a or b)


def profile_bits(uid):
    """This person's MLS and brokerage, plus the matching keys used to decide who sees what."""
    conn = _db()
    try:
        r = conn.execute("SELECT mls_name, brokerage_name FROM user_profiles WHERE user_id = ?", (uid,)).fetchone()
    finally:
        conn.close()
    mls = ((r["mls_name"] if r else "") or "").strip()
    brok = ((r["brokerage_name"] if r else "") or "").strip()
    return {"mls": mls, "mls_norm": norm_mls(mls), "brokerage": brok, "brokerage_norm": norm_brokerage(brok)}


def save_mls(uid, role, text):
    text = _clean(text, 80)
    conn = _db()
    try:
        cur = conn.execute("UPDATE user_profiles SET mls_name = ? WHERE user_id = ?", (text, uid))
        conn.commit()
        missing = cur.rowcount == 0
    finally:
        conn.close()
    if missing:
        from database import create_or_update_user_profile
        create_or_update_user_profile(user_id=uid, role=role)
        conn = _db()
        conn.execute("UPDATE user_profiles SET mls_name = ? WHERE user_id = ?", (text, uid))
        conn.commit()
        conn.close()


def _audience_sql(me, uid):
    """A SQL condition (and its values) matching posts this person was meant to see."""
    parts, vals = ["(p.audience = 'custom' AND EXISTS (SELECT 1 FROM help_invites i WHERE i.post_id = p.id AND i.user_id = ?))"], [uid]
    if me["mls_norm"]:
        parts.append("(p.audience = 'mls' AND p.mls_norm = ?)")
        vals.append(me["mls_norm"])
    if me["brokerage_norm"]:
        parts.append("(p.audience = 'brokerage' AND p.brokerage_norm = ?)")
        vals.append(me["brokerage_norm"])
    return "(" + " OR ".join(parts) + ")", vals


def _can_see(conn, post, uid, me):
    if post["author_id"] == uid or post["claimed_by"] == uid:
        return True
    clause, vals = _audience_sql(me, uid)
    row = conn.execute(f"SELECT 1 FROM help_posts p WHERE p.id = ? AND {clause}", [post["id"]] + vals).fetchone()
    return bool(row)


def _decorate(r):
    r = dict(r)
    r["kind_label"] = KINDS.get(r["kind"], KINDS["other"])[1]
    r["when"] = nice_date(r["post_date"])
    r["time"] = time_range(r.get("start_time"), r.get("end_time"))
    r["past"] = bool(r["post_date"]) and r["post_date"] < date.today().isoformat()
    return r


def board_for(uid):
    """(open requests for me, my own posts, ones I said yes to)."""
    me = profile_bits(uid)
    today = date.today().isoformat()
    clause, vals = _audience_sql(me, uid)
    conn = _db()
    try:
        base = """SELECT p.*, au.name AS author_name, au.email AS author_email, cu.name AS claimer_name, cu.email AS claimer_email,
                         ap.phone AS author_phone, cp.phone AS claimer_phone, ap.brokerage_name AS author_brokerage,
                         (SELECT COUNT(*) FROM help_invites i WHERE i.post_id = p.id) AS invited
                  FROM help_posts p
                  JOIN users au ON au.id = p.author_id
                  LEFT JOIN users cu ON cu.id = p.claimed_by
                  LEFT JOIN user_profiles ap ON ap.user_id = p.author_id
                  LEFT JOIN user_profiles cp ON cp.user_id = p.claimed_by """
        openr = conn.execute(base + f"WHERE p.status = 'open' AND p.author_id != ? AND p.post_date >= ? AND {clause} ORDER BY p.post_date, p.start_time LIMIT 200",
                             [uid, today] + vals).fetchall()
        mine = conn.execute(base + "WHERE p.author_id = ? AND p.status != 'cancelled' AND p.post_date >= ? ORDER BY p.post_date, p.start_time LIMIT 200",
                            (uid, (date.today() - timedelta(days=14)).isoformat())).fetchall()
        taking = conn.execute(base + "WHERE p.claimed_by = ? AND p.status = 'claimed' AND p.post_date >= ? ORDER BY p.post_date, p.start_time LIMIT 200",
                              (uid, today)).fetchall()
    finally:
        conn.close()
    return [_decorate(r) for r in openr], [_decorate(r) for r in mine], [_decorate(r) for r in taking], me


def thanks_for(uid):
    """(how many colleagues this person has helped, recent thank-you notes they received)."""
    conn = _db()
    try:
        helped = conn.execute("SELECT COUNT(*) FROM help_posts WHERE claimed_by = ? AND status = 'claimed' AND post_date <= ?",
                              (uid, date.today().isoformat())).fetchone()[0]
        rows = conn.execute(
            """SELECT p.title, p.post_date, p.thanks_note, au.name AS author_name FROM help_posts p JOIN users au ON au.id = p.author_id
               WHERE p.claimed_by = ? AND p.thanked_at IS NOT NULL ORDER BY p.thanked_at DESC LIMIT 5""", (uid,)).fetchall()
    finally:
        conn.close()
    return helped, [dict(r) for r in rows]


def open_count(uid):
    """How many open requests this person could take; used for the small number on the dashboard."""
    try:
        return len(board_for(uid)[0])
    except Exception:
        return 0


def _notify(sender, recipient_id, subject, text):
    ns = _H["ns"]
    try:
        from database import get_user_by_id
        r = get_user_by_id(recipient_id)
        r = dict(r) if r else {}
        if not r.get("email"):
            return
        first = (r.get("name") or "there").split()[0]
        link = ns["_site_url"]().rstrip("/") + url_for("helpboard.board_page")
        body = f"Hi {first},\n\n{text}\n\nSee it on the Help Board: {link}\n"
        kw = ns["pro_sender"](sender["id"])
        kw.pop("signature", None)
        ns["_bg"](ns["send_reminder_email"], r["email"], subject, body, **kw)
    except Exception as e:
        print(f"[WARNING] help board notice skipped: {e}")


def _summary(p):
    bits = [p["title"]]
    if p.get("address"):
        bits.append(p["address"])
    when = nice_date(p["post_date"]) + (", " + time_range(p.get("start_time"), p.get("end_time")) if time_range(p.get("start_time"), p.get("end_time")) else "")
    bits.append(when)
    return " - ".join(b for b in bits if b)


@bp.route("/helpboard")
def board_page():
    u = _user()
    if not u:
        return redirect(url_for("login"))
    openr, mine, taking, me = board_for(u["id"])
    helped, thanks = thanks_for(u["id"])
    return render_template(f"{u['role']}/helpboard.html", role=u["role"], open_posts=openr, mine=mine, taking=taking, me=me, helped=helped, thanks=thanks, today_iso=date.today().isoformat(),
                           mls_options=_mls_options(), kinds=KINDS)


@bp.route("/helpboard/mls", methods=["POST"])
def save_mls_route():
    u = _user()
    if not u or u["role"] != "agent":
        return redirect(url_for("login"))
    save_mls(u["id"], "agent", request.form.get("mls_name"))
    flash("Saved. You will now see requests meant for your MLS." if _clean(request.form.get("mls_name")) else "Your MLS was cleared.", "success")
    return redirect(url_for("helpboard.board_page"))


@bp.route("/helpboard/new", methods=["GET", "POST"])
def new_post():
    u = _user()
    if not u:
        return redirect(url_for("login"))
    me = profile_bits(u["id"])
    audiences = ["mls", "brokerage", "custom"] if u["role"] == "agent" else ["brokerage", "custom"]
    form = request.form if request.method == "POST" else {}
    if request.method == "POST":
        kind = form.get("kind") if form.get("kind") in KINDS else "other"
        title = _clean(form.get("title"), 120) or KINDS[kind][0]
        when = _valid_date(form.get("post_date"))
        audience = form.get("audience") if form.get("audience") in audiences else ""
        problem = None
        if not when:
            problem = "Please choose the date you need help."
        elif when < date.today().isoformat():
            problem = "That date has already passed."
        elif not audience:
            problem = "Please choose who should see this."
        elif audience == "mls" and not me["mls_norm"]:
            problem = "Add your MLS first (on the Help Board page), so I know who is on it with you."
        elif audience == "brokerage" and not me["brokerage_norm"]:
            problem = "Add your brokerage name in Settings first, so I know who works with you."
        invitees, unknown = [], 0
        if not problem and audience == "custom":
            wanted = {e.lower() for e in re.findall(r"[^\s,;<>]+@[^\s,;<>]+", form.get("invite", ""))}
            conn = _db()
            try:
                for e in sorted(wanted)[:40]:
                    r = conn.execute("SELECT id FROM users WHERE LOWER(email) = ? AND role IN ('agent','lender') AND id != ?", (e, u["id"])).fetchone()
                    if r:
                        invitees.append(r["id"])
                    else:
                        unknown += 1
            finally:
                conn.close()
            if not invitees:
                problem = "Add at least one email of someone on Your Life, Your Home." if wanted else "Add the email of at least one person to invite."
        if problem:
            flash(problem, "error")
        else:
            label = {"mls": me["mls"], "brokerage": me["brokerage"], "custom": ""}[audience]
            conn = _db()
            try:
                cur = conn.execute(
                    """INSERT INTO help_posts (author_id, kind, title, address, post_date, start_time, end_time, details, audience, mls_norm, brokerage_norm, audience_label)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (u["id"], kind, title, _clean(form.get("address"), 160), when, _clean(form.get("start_time"), 30), _clean(form.get("end_time"), 30),
                     _clean(form.get("details"), 800), audience, me["mls_norm"] if audience == "mls" else "",
                     me["brokerage_norm"] if audience == "brokerage" else "", label))
                pid = cur.lastrowid
                for i in invitees:
                    conn.execute("INSERT OR IGNORE INTO help_invites (post_id, user_id) VALUES (?, ?)", (pid, i))
                conn.commit()
            finally:
                conn.close()
            post = {"title": title, "address": _clean(form.get("address"), 160), "post_date": when,
                    "start_time": _clean(form.get("start_time"), 30), "end_time": _clean(form.get("end_time"), 30)}
            for i in invitees:   # only people the poster named get an email; everyone else sees it on the board
                _notify(u, i, f"{u.get('name') or 'A colleague'} asked for your help",
                        f"{u.get('name') or 'A colleague'} would love a hand with this:\n\n{_summary(post)}\n\n{_clean(form.get('details'), 800)}")
            extra = f" {unknown} email{'s were' if unknown != 1 else ' was'} not found on the site, so I left {'them' if unknown != 1 else 'it'} out." if unknown else ""
            flash("Posted. I will let you know the moment someone says yes." + extra, "success")
            return redirect(url_for("helpboard.board_page"))
    return render_template(f"{u['role']}/helpboard_new.html", role=u["role"], me=me, audiences=audiences, kinds=KINDS, form=form,
                           today=date.today().isoformat())


@bp.route("/helpboard/<int:post_id>/<action>", methods=["POST"])
def post_act(post_id, action):
    u = _user()
    if not u:
        return redirect(url_for("login"))
    me = profile_bits(u["id"])
    conn = _db()
    try:
        row = conn.execute("SELECT * FROM help_posts WHERE id = ?", (post_id,)).fetchone()
        if not row or not _can_see(conn, row, u["id"], me):
            flash("That request is no longer available.", "error")
            return redirect(url_for("helpboard.board_page"))
        post = dict(row)
        if action == "claim":
            if post["author_id"] == u["id"]:
                flash("That one is your own request.", "error")
            else:
                cur = conn.execute("UPDATE help_posts SET status='claimed', claimed_by=?, claimed_at=CURRENT_TIMESTAMP WHERE id=? AND status='open' AND post_date >= ?",
                                   (u["id"], post_id, date.today().isoformat()))
                conn.commit()
                if cur.rowcount == 0:
                    flash("Someone just took that one, or the date has passed.", "error")
                else:
                    flash("You are on it. Their contact details are on your Help Board, and I let them know.", "success")
                    _notify(u, post["author_id"], f"{u.get('name') or 'A colleague'} said yes",
                            f"Good news: {u.get('name') or 'a colleague'} will help with:\n\n{_summary(post)}\n\nTheir email is {u.get('email')}. You can thank them there.")
        elif action == "release":
            if post["claimed_by"] != u["id"] or post["status"] != "claimed":
                flash("That is not one you took.", "error")
            else:
                conn.execute("UPDATE help_posts SET status='open', claimed_by=NULL, claimed_at=NULL WHERE id=? AND claimed_by=?", (post_id, u["id"]))
                conn.commit()
                flash("Released. It is open again for others, and I let them know.", "success")
                _notify(u, post["author_id"], "Your request is open again",
                        f"{u.get('name') or 'Your helper'} can no longer make it, so this is open again:\n\n{_summary(post)}")
        elif action == "thank":
            if post["author_id"] != u["id"] or post["status"] != "claimed" or not post["claimed_by"]:
                flash("There is no helper to thank on that one.", "error")
            elif post["post_date"] > date.today().isoformat():
                flash("You can say thank you once the day has come.", "error")
            elif post.get("thanked_at"):
                flash("You already thanked them. That was kind.", "success")
            else:
                note = _clean(request.form.get("note"), 500)
                conn.execute("UPDATE help_posts SET thanked_at = CURRENT_TIMESTAMP, thanks_note = ? WHERE id = ? AND author_id = ?", (note, post_id, u["id"]))
                conn.commit()
                flash("Your thank you is on its way. That will mean a lot.", "success")
                _notify(u, post["claimed_by"], f"Thank you from {u.get('name') or 'a colleague'}",
                        NL.join(["Thank you for helping with:", "", _summary(post), "", note or "It truly made a difference.", "", "With gratitude,", u.get("name") or ""]))
        elif action == "cancel":
            if post["author_id"] != u["id"] or post["status"] == "cancelled":
                flash("That is not one of your requests.", "error")
            else:
                conn.execute("UPDATE help_posts SET status='cancelled' WHERE id=? AND author_id=?", (post_id, u["id"]))
                conn.commit()
                flash("Cancelled.", "success")
                if post["status"] == "claimed" and post["claimed_by"]:
                    _notify(u, post["claimed_by"], "Request cancelled", f"{u.get('name') or 'The poster'} cancelled:\n\n{_summary(post)}\n\nThank you for offering.")
        else:
            flash("That action is not available.", "error")
    finally:
        conn.close()
    return redirect(url_for("helpboard.board_page"))


def strip_for(uid):
    """What the dashboard strip shows: requests this person could take, and what they promised to help with soon."""
    try:
        openr, _mine, taking, _me = board_for(uid)
    except Exception:
        return {}
    soon = (date.today() + timedelta(days=7)).isoformat()
    coming = [p for p in taking if p["post_date"] <= soon]
    if not openr and not coming:
        return {}
    return {"open": len(openr), "coming": coming[:3]}


def send_reminders(today=None):
    """The day before, one friendly note to the helper and one to the person who asked. Sent once per request."""
    ns = _H.get("ns") or {}
    send = ns.get("send_reminder_email")
    if not send:
        return 0
    tomorrow = ((today or date.today()) + timedelta(days=1)).isoformat()
    conn = _db()
    try:
        rows = conn.execute(
            """SELECT p.*, au.name AS author_name, au.email AS author_email, cu.name AS claimer_name, cu.email AS claimer_email
               FROM help_posts p JOIN users au ON au.id = p.author_id JOIN users cu ON cu.id = p.claimed_by
               WHERE p.status = 'claimed' AND p.post_date = ? AND COALESCE(p.reminded, 0) = 0""", (tomorrow,)).fetchall()
        sent = 0
        for r in rows:
            p = dict(r)
            conn.execute("UPDATE help_posts SET reminded = 1 WHERE id = ?", (p["id"],))
            conn.commit()
            what = _summary(p)
            if p["claimer_email"]:
                send(p["claimer_email"], "Tomorrow: you are helping a colleague",
                     NL.join(["Hi " + (p["claimer_name"] or "there").split()[0] + ",", "",
                              "A friendly reminder that you are helping " + p["author_name"] + " tomorrow:", "", what, "",
                              "You can reach them at " + p["author_email"] + ". Thank you for being a good colleague.", ""]))
                sent += 1
            if p["author_email"]:
                send(p["author_email"], "Tomorrow: your helper is set",
                     NL.join(["Hi " + (p["author_name"] or "there").split()[0] + ",", "",
                              "A friendly reminder that " + p["claimer_name"] + " is helping you tomorrow:", "", what, "",
                              "You can reach them at " + p["claimer_email"] + ".", ""]))
                sent += 1
    finally:
        conn.close()
    return sent


def init_app(app, get_current_user, ns):
    _H.update(get_current_user=get_current_user, ns=ns)
    ensure_tables()
    app.register_blueprint(bp)

    @app.context_processor
    def _helpboard_strip():
        from flask import request as _rq
        if _rq.endpoint in ("agent_dashboard", "lender_dashboard"):
            u = get_current_user()
            if u and u.get("role") in ("agent", "lender"):
                return {"helpboard_strip": strip_for(u["id"])}
        return {}
