"""Home details, care alert preferences, and the Frost Alert.

Homeowners say what their home has (sprinkler system, outdoor faucets, ...) and which helpful alerts they want.
An agent or lender can then press one button: we check the National Weather Service forecast for each client's home,
show who would be affected, let the pro edit the message, and send only to the people they leave checked.
Nothing goes out on its own, and nobody is alerted twice in 12 hours.
"""
import json
import re
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

bp = Blueprint("care_alerts", __name__)
_H = {}

DEFAULT_THRESHOLD = 32
THRESHOLDS = (28, 30, 32, 34, 36)
MAX_CHECK = 150               # homes checked in one go
RESEND_HOURS = 12             # never alert the same person twice inside this window
_UA = {"User-Agent": "YourLifeYourHome-CareAlerts (itsyourlifeyourhome.com)", "Accept": "application/geo+json"}
_points_cache, _forecast_cache = {}, {}


def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    conn.execute("""CREATE TABLE IF NOT EXISTS home_details (
        user_id INTEGER PRIMARY KEY, sprinkler INTEGER NOT NULL DEFAULT 0, outdoor_faucets INTEGER NOT NULL DEFAULT 1,
        fireplace INTEGER NOT NULL DEFAULT 0, sump_pump INTEGER NOT NULL DEFAULT 0, move_in_date TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS care_prefs (
        user_id INTEGER PRIMARY KEY, frost_alerts INTEGER NOT NULL DEFAULT 1, seasonal_tips INTEGER NOT NULL DEFAULT 1)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS geo_cache (
        addr_key TEXT PRIMARY KEY, lat REAL, lon REAL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS frost_sends (
        id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER, person_key TEXT, low REAL, sent_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    conn.commit()
    conn.close()


# ───────────────────────── homeowner details and preferences ─────────────────────────
def get_details(user_id):
    d = dict(sprinkler=0, outdoor_faucets=1, fireplace=0, sump_pump=0, move_in_date="")
    try:
        conn = _db()
        r = conn.execute("SELECT * FROM home_details WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        if r:
            d.update({k: r[k] for k in d})
            d["move_in_date"] = d["move_in_date"] or ""
    except Exception:
        pass
    return d


def get_prefs(user_id):
    p = dict(frost_alerts=1, seasonal_tips=1)
    try:
        conn = _db()
        r = conn.execute("SELECT * FROM care_prefs WHERE user_id = ?", (user_id,)).fetchone()
        conn.close()
        if r:
            p.update({k: r[k] for k in p})
    except Exception:
        pass
    return p


def _flag(name):
    return 1 if request.form.get(name) == "on" else 0


@bp.route("/homeowner/care/preferences", methods=["GET", "POST"])
def care_preferences():
    u = _H["get_current_user"]()
    if not u or u.get("role") != "homeowner":
        return redirect(url_for("login", role="homeowner"))
    if request.method == "POST":
        move_in = (request.form.get("move_in_date") or "").strip()[:10]
        conn = _db()
        conn.execute("""INSERT INTO home_details (user_id, sprinkler, outdoor_faucets, fireplace, sump_pump, move_in_date)
                        VALUES (?,?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET sprinkler=excluded.sprinkler,
                        outdoor_faucets=excluded.outdoor_faucets, fireplace=excluded.fireplace, sump_pump=excluded.sump_pump,
                        move_in_date=excluded.move_in_date""",
                     (u["id"], _flag("sprinkler"), _flag("outdoor_faucets"), _flag("fireplace"), _flag("sump_pump"), move_in))
        conn.execute("""INSERT INTO care_prefs (user_id, frost_alerts, seasonal_tips) VALUES (?,?,?)
                        ON CONFLICT(user_id) DO UPDATE SET frost_alerts=excluded.frost_alerts, seasonal_tips=excluded.seasonal_tips""",
                     (u["id"], _flag("frost_alerts"), _flag("seasonal_tips")))
        conn.commit()
        conn.close()
        flash("Saved. Thank you, this helps us send only what is useful to you.", "success")
        return redirect(url_for("care_alerts.care_preferences"))
    return render_template("homeowner/care_preferences.html", d=get_details(u["id"]), p=get_prefs(u["id"]))


# ───────────────────────── forecast ─────────────────────────
def _http_get_json(url, headers=None, timeout=8):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _addr_key(address):
    return re.sub(r"\s+", " ", (address or "").strip().lower())


def geocode(address):
    """(lat, lon) for a street address using the free US Census geocoder, remembered so it is only looked up once."""
    key = _addr_key(address)
    if not key:
        return None
    conn = _db()
    try:
        r = conn.execute("SELECT lat, lon, created_at FROM geo_cache WHERE addr_key = ?", (key,)).fetchone()
        if r:
            if r["lat"] is not None:
                return float(r["lat"]), float(r["lon"])
            if r["created_at"] and r["created_at"] >= (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S"):
                return None          # a recent miss: do not hammer the service
    finally:
        conn.close()
    lat = lon = None
    try:
        url = ("https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?benchmark=Public_AR_Current&format=json&address="
               + urllib.parse.quote(address))
        data = _http_get_json(url, timeout=8)
        m = (data.get("result", {}).get("addressMatches") or [None])[0]
        if m:
            lon, lat = float(m["coordinates"]["x"]), float(m["coordinates"]["y"])
    except Exception:
        return None                  # service trouble: do not cache, try again next time
    conn = _db()
    try:
        conn.execute("INSERT OR REPLACE INTO geo_cache (addr_key, lat, lon) VALUES (?,?,?)", (key, lat, lon))
        conn.commit()
    finally:
        conn.close()
    return (lat, lon) if lat is not None else None


def _parse_time(s):
    try:
        return datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def forecast_low(lat, lon, hours=48):
    """Coldest forecast temperature in the next `hours` hours: {'low': 28, 'when': 'Tonight'}."""
    pkey = (round(lat, 2), round(lon, 2))
    furl = _points_cache.get(pkey)
    if not furl:
        pts = _http_get_json(f"https://api.weather.gov/points/{lat:.4f},{lon:.4f}", _UA)
        furl = pts["properties"]["forecast"]
        _points_cache[pkey] = furl
    now = datetime.now(timezone.utc)
    hit = _forecast_cache.get(furl)
    if hit and (now - hit[0]) < timedelta(minutes=30):
        periods = hit[1]
    else:
        periods = _http_get_json(furl, _UA)["properties"]["periods"]
        _forecast_cache[furl] = (now, periods)
    best = None
    for p in periods:
        start = _parse_time(p.get("startTime"))
        if start is None or start.tzinfo is None:
            start = (start or now).replace(tzinfo=timezone.utc)
        if start > now + timedelta(hours=hours):
            continue
        t = p.get("temperature")
        if t is None:
            continue
        t = float(t)
        if (p.get("temperatureUnit") or "F").upper() == "C":
            t = t * 9 / 5 + 32
        if best is None or t < best["low"]:
            best = {"low": round(t), "when": p.get("name") or "soon"}
    if best is None:
        raise ValueError("no forecast periods")
    return best


# ───────────────────────── people ─────────────────────────
def _clean_phone(p):
    return re.sub(r"\D", "", p or "")


def people_for(role, uid):
    """Everyone this agent or lender could alert: portal homeowners plus past clients and borrowers in the CRM who have a home address."""
    from database import (get_agent_clients, get_lender_clients, list_agent_contacts, list_lender_borrowers)
    people, seen_users, seen_emails = [], set(), set()
    conn = _db()
    try:
        homeowners = get_agent_clients(uid) if role == "agent" else get_lender_clients(uid)
        ids = [h["id"] for h in homeowners]
        phones, feats, prefs = {}, {}, {}
        if ids:
            marks = ",".join("?" * len(ids))
            phones = {r[0]: r[1] for r in conn.execute(f"SELECT id, phone FROM users WHERE id IN ({marks})", ids).fetchall()}
            feats = {r["user_id"]: r for r in conn.execute(f"SELECT * FROM home_details WHERE user_id IN ({marks})", ids).fetchall()}
            prefs = {r["user_id"]: r for r in conn.execute(f"SELECT * FROM care_prefs WHERE user_id IN ({marks})", ids).fetchall()}
    finally:
        conn.close()
    for h in homeowners:
        f, pr = feats.get(h["id"]), prefs.get(h["id"])
        seen_users.add(h["id"])
        if h.get("email"):
            seen_emails.add(h["email"].strip().lower())
        people.append(dict(
            key=f"u{h['id']}", name=h.get("name") or h.get("email") or "Client", email=h.get("email") or "",
            phone=_clean_phone(phones.get(h["id"])), address=h.get("property_address") or "", portal=True,
            ok=bool(pr["frost_alerts"]) if pr else True, sprinkler=bool(f and f["sprinkler"]),
            faucets=bool(f["outdoor_faucets"]) if f else True))
    contacts = list_agent_contacts(uid) if role == "agent" else list_lender_borrowers(uid)
    for c in contacts:
        c = dict(c)
        if c.get("user_id") in seen_users:
            continue
        email = (c.get("email") or "").strip()
        if email and email.lower() in seen_emails:
            continue
        addr = (c.get("property_address") or "").strip()
        if not addr and c.get("address"):
            addr = ", ".join(x for x in (c.get("address"), c.get("city"), c.get("state"), c.get("zip_code")) if x)
        if not addr or not (email or c.get("phone")):
            continue
        people.append(dict(
            key=f"c{c['id']}", name=c.get("name") or email or "Contact", email=email, phone=_clean_phone(c.get("phone")),
            address=addr, portal=False, ok=c.get("auto_seasonal") != 0, sprinkler=False, faucets=True))
    return people


def check_people(people, threshold):
    """Look up the forecast for each home. Adds low, when and state (freeze / mild / unknown) to each person."""
    todo = people[:MAX_CHECK]

    def one(p):
        if not p["address"]:
            return dict(state="unknown", why="No home address yet")
        ll = geocode(p["address"])
        if not ll:
            return dict(state="unknown", why="Could not find this address")
        try:
            f = forecast_low(*ll)
        except Exception:
            return dict(state="unknown", why="Forecast not available")
        return dict(state="freeze" if f["low"] <= threshold else "mild", low=f["low"], when=f["when"])

    with ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(one, todo))
    for p, r in zip(todo, results):
        p.update(r)
    for p in people[MAX_CHECK:]:
        p.update(state="unknown", why="Not checked this time (a lot of homes); try again")
    return people


def recently_alerted(sender_id):
    conn = _db()
    try:
        cutoff = (datetime.utcnow() - timedelta(hours=RESEND_HOURS)).strftime("%Y-%m-%d %H:%M:%S")
        return {r[0] for r in conn.execute("SELECT person_key FROM frost_sends WHERE sender_id = ? AND sent_at >= ?", (sender_id, cutoff)).fetchall()}
    finally:
        conn.close()


# ───────────────────────── messages ─────────────────────────
def draft_message(low=None, when=None):
    when_s = (when or "tonight").lower()          # "tonight", "wednesday night", ...
    temp = f" (down to about {int(low)}°F)" if low is not None else ""
    return (f"Hi {{first}},\n\nA quick heads-up: freezing temperatures are expected {when_s}{temp}.\n\n"
            "A few easy ways to protect your home:\n"
            "- Disconnect garden hoses from outdoor faucets and let the faucets drain\n"
            "- Put on an outdoor faucet cover if you have one\n"
            "- Open the cabinet doors under sinks on outside walls\n"
            "- If a pipe has frozen before, let one faucet drip overnight\n\n"
            "That is all. Stay warm!")


SPRINKLER_LINE = "\nIf you have a sprinkler system, make sure it has been drained or blown out for the winter."


def compose_email(base, person, pro_name, site_url):
    first = (person["name"] or "there").split()[0]
    body = base.replace("{first}", first)
    if person.get("sprinkler"):
        body += "\n" + SPRINKLER_LINE.strip()
    body += f"\n\n{pro_name}"
    if person.get("portal"):
        body += f"\n\nYou can choose which home alerts you get any time here: {site_url}/homeowner/care/preferences"
    else:
        body += "\n\nIf you would rather not get notes like this, just reply and let me know."
    return body


def sms_text(person, low, pro_name):
    first = (person["name"] or "there").split()[0]
    temp = f" (low near {int(low)}°F)" if low is not None else ""
    return f"Hi {first}, freezing temps are coming{temp}. Please disconnect garden hoses and let outdoor faucets drain. Stay warm! - {pro_name}"


def sms_link(phone, text):
    return f"sms:{phone}?&body={urllib.parse.quote(text)}" if phone else ""


# ───────────────────────── pages ─────────────────────────
def _pro():
    u = _H["get_current_user"]()
    return u if u and u.get("role") in ("agent", "lender") else None


def _render(u, **ctx):
    ctx.setdefault("thresholds", THRESHOLDS)
    ctx.setdefault("threshold", DEFAULT_THRESHOLD)
    conn = _db()
    try:
        last = conn.execute("SELECT MAX(sent_at) AS t, COUNT(*) AS n FROM frost_sends WHERE sender_id = ? AND sent_at >= datetime('now','-3 days')", (u["id"],)).fetchone()
    finally:
        conn.close()
    ctx["last_sent"] = last["t"] if last and last["t"] else None
    return render_template("agent/frost_alert.html" if u["role"] == "agent" else "lender/frost_alert.html", **ctx)


@bp.route("/frost-alert")
def frost_page():
    u = _pro()
    if not u:
        return redirect(url_for("login"))
    return _render(u, result=None)


@bp.route("/frost-alert/check", methods=["POST"])
def frost_check():
    u = _pro()
    if not u:
        return redirect(url_for("login"))
    try:
        th = int(request.form.get("threshold") or DEFAULT_THRESHOLD)
    except ValueError:
        th = DEFAULT_THRESHOLD
    th = th if th in THRESHOLDS else DEFAULT_THRESHOLD
    people = check_people(people_for(u["role"], u["id"]), th)
    done = recently_alerted(u["id"])
    pro_name = (u.get("name") or "").strip() or "Your Life, Your Home"
    freeze = [p for p in people if p.get("state") == "freeze"]
    low = min((p["low"] for p in freeze), default=None)
    when = next((p["when"] for p in sorted(freeze, key=lambda p: p["low"])), None)
    for p in people:
        p["recent"] = p["key"] in done
        p["preselect"] = bool(p.get("state") == "freeze" and p["ok"] and p["email"] and p["faucets"] and not p["recent"])
        p["sms"] = sms_link(p["phone"], sms_text(p, p.get("low"), pro_name)) if p["ok"] else ""
    people.sort(key=lambda p: (p.get("state") != "freeze", p.get("low", 999), p["name"].lower()))
    result = dict(people=people, freeze=len(freeze), total=len(people), low=low, when=when,
                  message=draft_message(low, when), subject="Freezing temperatures ahead: a quick heads-up for your home")
    return _render(u, result=result, threshold=th)


@bp.route("/frost-alert/send", methods=["POST"])
def frost_send():
    u = _pro()
    if not u:
        return redirect(url_for("login"))
    keys = set(request.form.getlist("who"))
    subject = (request.form.get("subject") or "").strip()[:200] or "Freezing temperatures ahead: a quick heads-up for your home"
    base = (request.form.get("message") or "").strip()
    if not keys or not base:
        flash("Choose at least one person and keep a message to send.", "error")
        return redirect(url_for("care_alerts.frost_page"))
    try:
        low = float(request.form.get("low")) if request.form.get("low") else None
    except ValueError:
        low = None
    ns = _H["ns"]
    pro_name = (u.get("name") or "").strip() or "Your Life, Your Home"
    sender = ns["pro_sender"](u["id"])
    pro_name = sender.pop("signature", None) or pro_name      # a saved signature replaces the plain name sign-off
    site = ns["_site_url"]()
    mine = {p["key"]: p for p in people_for(u["role"], u["id"])}     # only people who really belong to this pro
    done = recently_alerted(u["id"])
    sent = skipped = 0
    conn = _db()
    try:
        for k in keys:
            p = mine.get(k)
            if not p or not p["email"] or not p["ok"] or k in done:
                skipped += 1
                continue
            body = compose_email(base, p, pro_name, site)
            ns["_bg"](ns["send_reminder_email"], p["email"], subject, body, **sender)
            conn.execute("INSERT INTO frost_sends (sender_id, person_key, low) VALUES (?,?,?)", (u["id"], k, low))
            sent += 1
        conn.commit()
    finally:
        conn.close()
    msg = f"Frost alert sent to {sent} {'person' if sent == 1 else 'people'}."
    if skipped:
        msg += f" Skipped {skipped} (no email, opted out, or already alerted in the last {RESEND_HOURS} hours)."
    flash(msg, "success" if sent else "info")
    return redirect(url_for("care_alerts.frost_page"))


def init_app(app, get_current_user, ns):
    """ns is app.py's globals(), so sending uses the live send_reminder_email, _bg, pro_sender and _site_url."""
    _H.update(get_current_user=get_current_user, ns=ns)
    ensure_tables()
    app.register_blueprint(bp)
