"""Built-in booking and the private phone-calendar feed.

Agents and lenders choose their days and hours once. Clients pick a time on a public page, both people get a warm
confirmation, and the booking lands on the host's phone calendar through one private subscription link that also
carries transaction deadlines and pie pickups.
"""
import os
import re
import secrets
import sqlite3
from datetime import date, datetime, time, timedelta, timezone
from urllib.parse import quote, urlencode
from zoneinfo import ZoneInfo

from flask import (Blueprint, Response, abort, flash, redirect, render_template, request, url_for)

bp = Blueprint("booking", __name__)
_H = {}

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
ZONES = [("America/New_York", "Eastern"), ("America/Chicago", "Central"), ("America/Denver", "Mountain"),
         ("America/Phoenix", "Arizona"), ("America/Los_Angeles", "Pacific"), ("America/Anchorage", "Alaska"),
         ("Pacific/Honolulu", "Hawaii")]
LENGTHS = [15, 30, 45, 60, 90]
NOTICE = [(2, "2 hours"), (4, "4 hours"), (12, "12 hours"), (24, "1 day"), (48, "2 days")]
DAYS_AHEAD = 45
DEFAULTS = {"enabled": 0, "days": "mon,tue,wed,thu,fri", "start_time": "09:00", "end_time": "17:00", "minutes": 30,
            "notice_hours": 4, "tz": "America/Chicago", "title": "Let's chat about your home",
            "place": "Phone call. I will call you at the number you give me."}


# ───────────────────────── storage ─────────────────────────
def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS booking_settings (
        user_id INTEGER PRIMARY KEY,
        token TEXT UNIQUE,
        feed_token TEXT UNIQUE,
        enabled INTEGER DEFAULT 0,
        days TEXT, start_time TEXT, end_time TEXT, minutes INTEGER, notice_hours INTEGER,
        tz TEXT, title TEXT, place TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bookings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        name TEXT, email TEXT, phone TEXT, note TEXT,
        day TEXT NOT NULL, start_time TEXT NOT NULL, minutes INTEGER DEFAULT 30,
        title TEXT, place TEXT,
        status TEXT DEFAULT 'confirmed',
        token TEXT UNIQUE,
        reminded INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS ux_booking_slot ON bookings(user_id, day, start_time) WHERE status='confirmed'")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_booking_user_day ON bookings(user_id, day)")
    conn.commit()
    conn.close()


def get_settings(user_id, create=False):
    """The saved settings for a person (defaults filled in). With create=True the row and its two private links exist."""
    conn = _db()
    row = conn.execute("SELECT * FROM booking_settings WHERE user_id=?", (user_id,)).fetchone()
    if not row and create:
        conn.execute("INSERT INTO booking_settings (user_id, token, feed_token, enabled, days, start_time, end_time, minutes, "
                     "notice_hours, tz, title, place) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                     (user_id, secrets.token_urlsafe(8), secrets.token_urlsafe(24), 0, DEFAULTS["days"], DEFAULTS["start_time"],
                      DEFAULTS["end_time"], DEFAULTS["minutes"], DEFAULTS["notice_hours"], DEFAULTS["tz"], DEFAULTS["title"],
                      DEFAULTS["place"]))
        conn.commit()
        row = conn.execute("SELECT * FROM booking_settings WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    s = dict(DEFAULTS)
    s["token"], s["feed_token"] = "", ""
    if row:
        for k, v in dict(row).items():
            if v not in (None, "") or k in ("token", "feed_token"):
                s[k] = v
    s["day_list"] = [d for d in (s["days"] or "").split(",") if d in DAY_KEYS]
    return s


def _by_token(token):
    conn = _db()
    row = conn.execute("SELECT * FROM booking_settings WHERE token=?", (token,)).fetchone()
    conn.close()
    return dict(row) if row else None


def booking_link(user_id):
    """Public booking page for this person if it is switched on, else empty. Used by the client 'Book a time' buttons."""
    try:
        conn = _db()
        row = conn.execute("SELECT token FROM booking_settings WHERE user_id=? AND enabled=1", (user_id,)).fetchone()
        conn.close()
        return url_for("booking.public_page", token=row["token"]) if row else ""
    except Exception:
        return ""


# ───────────────────────── time helpers ─────────────────────────
def _zone(tz):
    try:
        return ZoneInfo(tz or DEFAULTS["tz"])
    except Exception:
        return ZoneInfo(DEFAULTS["tz"])


def zone_label(tz):
    for z, n in ZONES:
        if z == tz:
            return n + " Time"
    return "local time"


def _parse_day(v):
    try:
        return datetime.strptime(v or "", "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_time(v):
    try:
        return datetime.strptime(v or "", "%H:%M").time()
    except ValueError:
        return None


def now_local(tz):
    return datetime.now(_zone(tz)).replace(tzinfo=None)


def to_utc(day, hhmm, tz):
    d, t = _parse_day(day), _parse_time(hhmm)
    if not d or not t:
        return None
    return datetime.combine(d, t).replace(tzinfo=_zone(tz)).astimezone(timezone.utc)


def pretty_time(hhmm):
    t = _parse_time(hhmm)
    return t.strftime("%I:%M %p").lstrip("0") if t else hhmm or ""


def pretty_day(day, short=False):
    d = _parse_day(day)
    if not d:
        return day or ""
    return f"{d.strftime('%a, %b')} {d.day}" if short else f"{d.strftime('%A, %B')} {d.day}"


def when_text(b):
    end = (datetime.combine(date.today(), _parse_time(b["start_time"])) + timedelta(minutes=b["minutes"] or 30)).strftime("%H:%M")
    return f"{pretty_day(b['day'])}, {pretty_time(b['start_time'])} to {pretty_time(end)}"


# ───────────────────────── availability ─────────────────────────
def _taken(conn, user_id, day):
    rows = conn.execute("SELECT start_time, minutes FROM bookings WHERE user_id=? AND day=? AND status='confirmed'",
                        (user_id, day)).fetchall()
    out = []
    for r in rows:
        s = _parse_time(r["start_time"])
        if s:
            a = datetime.combine(date.today(), s)
            out.append((a, a + timedelta(minutes=r["minutes"] or 30)))
    return out


def open_times(s, day, conn=None):
    """Start times (HH:MM) still open on a date for this person's settings."""
    d = _parse_day(day) if isinstance(day, str) else day
    if not d or DAY_KEYS[d.weekday()] not in s["day_list"]:
        return []
    st, en = _parse_time(s["start_time"]), _parse_time(s["end_time"])
    mins = int(s["minutes"] or 30)
    if not st or not en or mins <= 0:
        return []
    own = conn is None
    conn = conn or _db()
    taken = _taken(conn, s["user_id"], d.isoformat())
    if own:
        conn.close()
    earliest = now_local(s["tz"]) + timedelta(hours=int(s["notice_hours"] or 0))
    cur = datetime.combine(d, st)
    last = datetime.combine(d, en)
    out = []
    while cur + timedelta(minutes=mins) <= last:
        a, b = cur, cur + timedelta(minutes=mins)
        base = datetime.combine(date.today(), cur.time())
        clash = any(base < t1 and base + timedelta(minutes=mins) > t0 for t0, t1 in taken)
        if a >= earliest and not clash:
            out.append(cur.strftime("%H:%M"))
        cur += timedelta(minutes=mins)
    return out


def open_days(s, limit=14):
    """The next dates that still have at least one open time."""
    conn = _db()
    out = []
    d = now_local(s["tz"]).date()
    for _ in range(DAYS_AHEAD):
        if open_times(s, d, conn):
            out.append(d.isoformat())
            if len(out) >= limit:
                break
        d += timedelta(days=1)
    conn.close()
    return out


# ───────────────────────── calendar bits ─────────────────────────
def _esc(v):
    return str(v or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r", "").replace("\n", "\\n")


def _stamp(dt):
    return dt.strftime("%Y%m%dT%H%M%SZ")


def _vevent_booking(b, tz, host_view):
    s = to_utc(b["day"], b["start_time"], tz)
    if not s:
        return []
    e = s + timedelta(minutes=b["minutes"] or 30)
    if host_view:
        desc = "\n".join(x for x in (f"Booked by {b['name']}", b.get("phone") and f"Phone: {b['phone']}",
                                      b.get("email") and f"Email: {b['email']}", b.get("note") and f"Note: {b['note']}") if x)
        summary = f"{b['title'] or 'Appointment'}: {b['name']}"
    else:
        desc = f"{b['title'] or 'Appointment'}\n{b.get('place') or ''}".strip()
        summary = b["title"] or "Appointment"
    return ["BEGIN:VEVENT", f"UID:booking-{b['id']}@yourlifeyourhome", "DTSTAMP:" + _stamp(datetime.now(timezone.utc)),
            "DTSTART:" + _stamp(s), "DTEND:" + _stamp(e), f"SUMMARY:{_esc(summary)}", f"LOCATION:{_esc(b.get('place'))}",
            f"DESCRIPTION:{_esc(desc)}", "BEGIN:VALARM", "TRIGGER:-PT30M", "ACTION:DISPLAY", "DESCRIPTION:Coming up in 30 minutes",
            "END:VALARM", "END:VEVENT"]


def booking_ics(b, tz, host_view=False):
    return "\r\n".join(["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Your Life Your Home//Booking//EN", "CALSCALE:GREGORIAN",
                        "METHOD:PUBLISH"] + _vevent_booking(b, tz, host_view) + ["END:VCALENDAR"]) + "\r\n"


def google_url(b, tz):
    s = to_utc(b["day"], b["start_time"], tz)
    if not s:
        return ""
    e = s + timedelta(minutes=b["minutes"] or 30)
    return "https://calendar.google.com/calendar/render?" + urlencode({
        "action": "TEMPLATE", "text": b["title"] or "Appointment", "dates": f"{_stamp(s)}/{_stamp(e)}",
        "details": f"With {b.get('host_name') or 'your host'}", "location": b.get("place") or ""})


def build_feed(user_id):
    """Everything dated for one person: bookings, transaction deadlines, pie pickups."""
    s = get_settings(user_id)
    tz = s["tz"]
    now = datetime.now(timezone.utc)
    stamp = _stamp(now)
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Your Life Your Home//Calendar//EN", "CALSCALE:GREGORIAN",
             "X-WR-CALNAME:Your Life, Your Home", "REFRESH-INTERVAL;VALUE=DURATION:PT1H", "X-PUBLISHED-TTL:PT1H"]
    conn = _db()
    since = (date.today() - timedelta(days=30)).isoformat()
    for r in conn.execute("SELECT * FROM bookings WHERE user_id=? AND status='confirmed' AND day>=?", (user_id, since)).fetchall():
        lines += _vevent_booking(dict(r), tz, True)
    try:
        rows = conn.execute("""SELECT d.*, t.property_address FROM transaction_deadlines d JOIN transactions t ON t.id = d.transaction_id
                               WHERE t.agent_id=? AND COALESCE(t.status,'active')='active' AND COALESCE(d.done,0)=0""",
                            (user_id,)).fetchall()
    except sqlite3.Error:
        rows = []
    for r in rows:
        dd = _parse_day(r["due_date"])
        if not dd:
            continue
        lines += ["BEGIN:VEVENT", f"UID:deadline-{r['transaction_id']}-{r['key']}@yourlifeyourhome", "DTSTAMP:" + stamp,
                  f"DTSTART;VALUE=DATE:{dd.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(dd + timedelta(days=1)).strftime('%Y%m%d')}",
                  f"SUMMARY:{_esc(r['label'] + ': ' + (r['property_address'] or ''))}", "BEGIN:VALARM", "TRIGGER:-P1D",
                  "ACTION:DISPLAY", "DESCRIPTION:Coming up tomorrow", "END:VALARM", "END:VEVENT"]
    try:
        slots = conn.execute("""SELECT s.*, e.title FROM pie_slots s JOIN pie_events e ON e.id = s.event_id
                                WHERE e.owner_id=? AND s.slot_date IS NOT NULL AND s.slot_date != ''""", (user_id,)).fetchall()
        homes = conn.execute("""SELECT r.*, e.title, e.home_address FROM pie_responses r JOIN pie_events e ON e.id = r.event_id
                                WHERE e.owner_id=? AND r.choice='cant_make' AND r.fulfillment='home' AND r.want_date != ''
                                  AND COALESCE(r.picked_up,0)=0""", (user_id,)).fetchall()
    except sqlite3.Error:
        slots, homes = [], []
    for r in slots:
        a = to_utc(r["slot_date"], r["start_time"] or "09:00", tz)
        if not a:
            continue
        z = to_utc(r["slot_date"], r["end_time"], tz) if r["end_time"] else a + timedelta(hours=1)
        lines += ["BEGIN:VEVENT", f"UID:pieslot-{r['id']}@yourlifeyourhome", "DTSTAMP:" + stamp, "DTSTART:" + _stamp(a),
                  "DTEND:" + _stamp(z or a + timedelta(hours=1)), f"SUMMARY:{_esc(r['title'] + ': pie pickups')}",
                  f"LOCATION:{_esc(r['location'])}", "END:VEVENT"]
    for r in homes:
        a = to_utc(r["want_date"], r["want_time"] or "12:00", tz)
        if not a:
            continue
        lines += ["BEGIN:VEVENT", f"UID:piehome-{r['id']}@yourlifeyourhome", "DTSTAMP:" + stamp, "DTSTART:" + _stamp(a),
                  "DTEND:" + _stamp(a + timedelta(minutes=30)), f"SUMMARY:{_esc('Pie pickup at home: ' + (r['name'] or ''))}",
                  f"LOCATION:{_esc(r['home_address'])}", "END:VEVENT"]
    conn.close()
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


# ───────────────────────── people and email ─────────────────────────
def _host(user_id):
    from database import get_user_by_id, get_user_profile
    u = get_user_by_id(user_id)
    u = dict(u) if u else {}
    p = dict(get_user_profile(user_id) or {})
    return {"name": u.get("name") or "", "email": u.get("email") or "", "phone": p.get("phone") or "",
            "brokerage": p.get("brokerage_name") or p.get("team_name") or "", "photo": p.get("professional_photo") or "",
            "logo": p.get("brokerage_logo") or "", "role": u.get("role") or "agent"}


def _first(name):
    return ((name or "").strip().split(" ") or ["there"])[0] or "there"


def _send(to, subject, body, host):
    fn = _H.get("send_email")
    if not fn or not to:
        return
    bg = _H.get("bg")
    args = (to, subject, body, host["name"] or None, host["email"] or None)
    try:
        bg(fn, *args) if bg else fn(*args)
    except Exception:
        pass


def _site(root=None):
    return (root or os.environ.get("YLH_SITE_URL") or "https://itsyourlifeyourhome.com").rstrip("/")


def email_booked(b, s, host, root):
    first = _first(b["name"])
    when = when_text(b)
    manage = f"{root}/book/c/{b['token']}"
    gcal = google_url({**b, "host_name": host["name"]}, s["tz"])
    body = (f"Hi {first},\n\nYou are all set! I am so looking forward to talking with you.\n\n{b['title']}\n{when} ({zone_label(s['tz'])})\n"
            f"{b['place']}\n\nAdd it to your calendar: {gcal}\nApple or Outlook calendar file: {root}/book/{s['token']}/{b['token']}.ics\n\n"
            f"Need a different time? You can change or cancel here, no worries at all: {manage}\n\nWarmly,\n{host['name']}")
    _send(b["email"], f"You are booked for {pretty_day(b['day'], True)} at {pretty_time(b['start_time'])}", body, host)
    note = f"\nTheir note: {b['note']}" if b.get("note") else ""
    hbody = (f"Hi {_first(host['name'])},\n\nGood news, you have a new booking!\n\n{b['name']}\n{when} ({zone_label(s['tz'])})\n"
             f"Phone: {b['phone'] or 'not given'}\nEmail: {b['email']}{note}\n\nIt is already on your phone calendar if you have turned on "
             f"your calendar link. You can see all of your bookings here: {root}/{host['role']}/booking\n\nYou are doing great!")
    fn = _H.get("send_email")
    if fn and host["email"]:
        try:
            (_H["bg"](fn, host["email"], f"New booking: {b['name']}, {pretty_day(b['day'], True)} {pretty_time(b['start_time'])}", hbody)
             if _H.get("bg") else fn(host["email"], "New booking", hbody))
        except Exception:
            pass


def email_cancelled(b, s, host, by_host):
    when = when_text(b)
    if by_host:
        body = (f"Hi {_first(b['name'])},\n\nI am so sorry, I need to cancel our time on {when}. I would love to find another time that "
                f"works for you. Just reply to this email or book a new time anytime.\n\nWarmly,\n{host['name']}")
        _send(b["email"], "A quick change to our time together", body, host)
    else:
        fn = _H.get("send_email")
        if fn and host["email"]:
            try:
                msg = f"Hi {_first(host['name'])},\n\n{b['name']} cancelled their time on {when}. That time is open again on your booking page."
                (_H["bg"](fn, host["email"], f"Cancelled: {b['name']}, {pretty_day(b['day'], True)}", msg) if _H.get("bg")
                 else fn(host["email"], "Cancelled booking", msg))
            except Exception:
                pass


def send_reminders(now=None):
    """Friendly reminder to the person who booked, once, the day before. Run daily by the scheduler."""
    send = _H.get("send_email")
    if not send:
        return 0
    conn = _db()
    sent = 0
    for r in conn.execute("SELECT b.*, s.tz, s.token AS page FROM bookings b JOIN booking_settings s ON s.user_id=b.user_id "
                          "WHERE b.status='confirmed' AND COALESCE(b.reminded,0)=0 AND b.email != ''").fetchall():
        b = dict(r)
        tomorrow = (now_local(b["tz"]) + timedelta(days=1)).date().isoformat()
        if b["day"] != tomorrow:
            continue
        host = _host(b["user_id"])
        root = _site()
        body = (f"Hi {_first(b['name'])},\n\nJust a friendly reminder that we are talking tomorrow.\n\n{b['title']}\n{when_text(b)} "
                f"({zone_label(b['tz'])})\n{b['place']}\n\nIf your plans changed, you can pick a new time here: {root}/book/c/{b['token']}\n\n"
                f"See you soon!\n{host['name']}")
        try:
            send(b["email"], f"See you tomorrow at {pretty_time(b['start_time'])}", body, host["name"] or None, host["email"] or None)
            conn.execute("UPDATE bookings SET reminded=1 WHERE id=?", (b["id"],))
            conn.commit()
            sent += 1
        except Exception:
            continue
    conn.close()
    return sent


# ───────────────────────── public pages ─────────────────────────
@bp.route("/book/<token>")
def public_page(token):
    s0 = _by_token(token)
    if not s0 or not s0["enabled"]:
        abort(404)
    s = get_settings(s0["user_id"])
    s["user_id"] = s0["user_id"]
    host = _host(s0["user_id"])
    days = open_days(s)
    chosen = request.args.get("d") if request.args.get("d") in days else (days[0] if days else None)
    conn = _db()
    times = open_times(s, chosen, conn) if chosen else []
    conn.close()
    return render_template("booking/public.html", s=s, host=host, days=days, chosen=chosen, times=times, form={},
                           pretty_day=pretty_day, pretty_time=pretty_time, zone=zone_label(s["tz"]))


@bp.route("/book/<token>", methods=["POST"])
def public_book(token):
    s0 = _by_token(token)
    if not s0 or not s0["enabled"]:
        abort(404)
    if request.form.get("website"):
        abort(400)
    s = get_settings(s0["user_id"])
    s["user_id"] = s0["user_id"]
    f = request.form
    name, email = f.get("name", "").strip()[:120], f.get("email", "").strip()[:200]
    phone, note = f.get("phone", "").strip()[:40], f.get("note", "").strip()[:600]
    day, start = f.get("day", ""), f.get("time", "")
    problem = ""
    if not name:
        problem = "Please tell me your name so I know who to look for."
    elif not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        problem = "That email does not look quite right. Could you check it for me?"
    elif not day or not start:
        problem = "Please tap the time that works best for you."
    elif start not in open_times(s, day):
        problem = "Oh no, someone just took that time. Please pick another one."
    if problem:
        flash(problem, "error")
        host = _host(s0["user_id"])
        days = open_days(s)
        chosen = day if day in days else (days[0] if days else None)
        conn = _db()
        times = open_times(s, chosen, conn) if chosen else []
        conn.close()
        return render_template("booking/public.html", s=s, host=host, days=days, chosen=chosen, times=times, form=f,
                               pretty_day=pretty_day, pretty_time=pretty_time, zone=zone_label(s["tz"])), 400
    btoken = secrets.token_urlsafe(10)
    conn = _db()
    try:
        cur = conn.execute("INSERT INTO bookings (user_id, name, email, phone, note, day, start_time, minutes, title, place, token) "
                           "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                           (s["user_id"], name, email, phone, note, day, start, int(s["minutes"]), s["title"], s["place"], btoken))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.close()
        flash("Oh no, someone just took that time. Please pick another one.", "error")
        return redirect(url_for("booking.public_page", token=token, d=day))
    b = dict(conn.execute("SELECT * FROM bookings WHERE id=?", (cur.lastrowid,)).fetchone())
    conn.close()
    email_booked(b, s, _host(s["user_id"]), request.url_root.rstrip("/"))
    return redirect(url_for("booking.done", token=token, btoken=btoken))


def _booking(btoken):
    conn = _db()
    row = conn.execute("SELECT * FROM bookings WHERE token=?", (btoken,)).fetchone()
    conn.close()
    return dict(row) if row else None


@bp.route("/book/<token>/done/<btoken>")
def done(token, btoken):
    s0, b = _by_token(token), _booking(btoken)
    if not s0 or not b or b["user_id"] != s0["user_id"]:
        abort(404)
    s = get_settings(b["user_id"])
    host = _host(b["user_id"])
    return render_template("booking/done.html", b=b, s=s, host=host, when=when_text(b), zone=zone_label(s["tz"]),
                           gcal=google_url({**b, "host_name": host["name"]}, s["tz"]), token=token)


@bp.route("/book/<token>/<btoken>.ics")
def guest_ics(token, btoken):
    s0, b = _by_token(token), _booking(btoken)
    if not s0 or not b or b["user_id"] != s0["user_id"] or b["status"] != "confirmed":
        abort(404)
    return Response(booking_ics(b, get_settings(b["user_id"])["tz"]), mimetype="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=appointment.ics"})


@bp.route("/book/c/<btoken>", methods=["GET", "POST"])
def cancel(btoken):
    b = _booking(btoken)
    if not b:
        abort(404)
    s = get_settings(b["user_id"])
    s["user_id"] = b["user_id"]
    host = _host(b["user_id"])
    page = get_settings(b["user_id"])["token"]
    if request.method == "POST" and b["status"] == "confirmed":
        conn = _db()
        conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (b["id"],))
        conn.commit()
        conn.close()
        email_cancelled(b, s, host, by_host=False)
        b["status"] = "cancelled"
    return render_template("booking/cancel.html", b=b, host=host, when=when_text(b), page=page)


@bp.route("/cal/<feed_token>.ics")
def feed(feed_token):
    conn = _db()
    row = conn.execute("SELECT user_id FROM booking_settings WHERE feed_token=?", (feed_token,)).fetchone()
    conn.close()
    if not row:
        abort(404)
    return Response(build_feed(row["user_id"]), mimetype="text/calendar",
                    headers={"Cache-Control": "private, max-age=300"})


# ───────────────────────── host side ─────────────────────────
def _me():
    u = _H["get_current_user"]()
    return u if u and u.get("role") in ("agent", "lender") else None


def _back(u):
    return redirect(url_for("agent_booking" if u.get("role") == "agent" else "lender_booking"))


@bp.route("/booking/save", methods=["POST"])
def save():
    u = _me()
    if not u:
        return redirect(url_for("login"))
    f = request.form
    days = ",".join(k for k in DAY_KEYS if f.get("day_" + k))
    st, en = f.get("start_time", ""), f.get("end_time", "")
    mins = int(f.get("minutes") or 30) if (f.get("minutes") or "30").isdigit() else 30
    tz = f.get("tz") if f.get("tz") in [z for z, _ in ZONES] else DEFAULTS["tz"]
    notice = int(f.get("notice_hours")) if (f.get("notice_hours") or "").isdigit() else 4
    if not _parse_time(st) or not _parse_time(en) or _parse_time(st) >= _parse_time(en):
        flash("Please pick a start time that comes before your end time.", "error")
        return _back(u)
    if not days:
        flash("Please choose at least one day you would like to take appointments.", "error")
        return _back(u)
    get_settings(u["id"], create=True)
    conn = _db()
    conn.execute("UPDATE booking_settings SET enabled=?, days=?, start_time=?, end_time=?, minutes=?, notice_hours=?, tz=?, "
                 "title=?, place=? WHERE user_id=?",
                 (1 if f.get("enabled") else 0, days, st, en, mins if mins in LENGTHS else 30, notice, tz,
                  (f.get("title") or DEFAULTS["title"]).strip()[:120], (f.get("place") or DEFAULTS["place"]).strip()[:250], u["id"]))
    conn.commit()
    conn.close()
    flash("Your booking page is " + ("live. Clients can book with you now!" if f.get("enabled") else "saved, and switched off for now."), "success")
    return _back(u)


@bp.route("/booking/<int:booking_id>/cancel", methods=["POST"])
def host_cancel(booking_id):
    u = _me()
    if not u:
        return redirect(url_for("login"))
    conn = _db()
    row = conn.execute("SELECT * FROM bookings WHERE id=? AND user_id=?", (booking_id, u["id"])).fetchone()
    if row and row["status"] == "confirmed":
        conn.execute("UPDATE bookings SET status='cancelled' WHERE id=?", (booking_id,))
        conn.commit()
        email_cancelled(dict(row), get_settings(u["id"]), _host(u["id"]), by_host=True)
        flash("That booking is cancelled and I let them know kindly.", "success")
    conn.close()
    return _back(u)


@bp.route("/booking/feed/new", methods=["POST"])
def new_feed():
    u = _me()
    if not u:
        return redirect(url_for("login"))
    get_settings(u["id"], create=True)
    conn = _db()
    conn.execute("UPDATE booking_settings SET feed_token=? WHERE user_id=?", (secrets.token_urlsafe(24), u["id"]))
    conn.commit()
    conn.close()
    flash("Done. Your old calendar link has stopped working. Add the new one to your phone.", "success")
    return _back(u)


def card_context(user_id):
    """Everything the setup card needs. Creating the row here means the private links always exist."""
    s = get_settings(user_id, create=True)
    s["user_id"] = user_id
    conn = _db()
    today = now_local(s["tz"]).date().isoformat()
    upcoming = [dict(r) for r in conn.execute(
        "SELECT * FROM bookings WHERE user_id=? AND status='confirmed' AND day>=? ORDER BY day, start_time LIMIT 20",
        (user_id, today)).fetchall()]
    conn.close()
    for b in upcoming:
        b["when"] = when_text(b)
    root = request.url_root.rstrip("/")
    host_only = root.split("://", 1)[-1]
    feed_https = f"{root}/cal/{s['feed_token']}.ics"
    return {"s": s, "upcoming": upcoming, "zones": ZONES, "lengths": LENGTHS, "notice": NOTICE,
            "day_keys": list(zip(DAY_KEYS, DAY_NAMES)), "page_url": f"{root}/book/{s['token']}",
            "feed_https": feed_https, "feed_webcal": f"webcal://{host_only}/cal/{s['feed_token']}.ics",
            "feed_google": "https://calendar.google.com/calendar/r?cid=" + quote(f"webcal://{host_only}/cal/{s['feed_token']}.ics", safe="")}


def init_app(app, get_current_user, bg, send_email):
    _H.update(get_current_user=get_current_user, bg=bg, send_email=send_email)
    ensure_tables()
    app.register_blueprint(bp)
    app.add_template_global(booking_link, "booking_link")
