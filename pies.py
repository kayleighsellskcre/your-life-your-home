"""Holiday pie pickup (and any other client giveaway/pickup event).

Agents and lenders create an event with pickup slots (day, time, location), a list of pie
types and an optional flyer. Clients answer from a public link, no login needed:
  * yes, pick up at one of the slots
  * yes, but I can't make those times (they say what would work)
  * no thank you
Owners see every answer, totals per pie and per slot, can mark pies as picked up, export CSV,
and print a branded flyer with a QR code to the sign-up link.
"""
import base64
import csv
import io
import json
import os
import secrets
from datetime import date, datetime

from flask import (Blueprint, Response, abort, current_app, flash, redirect,
                   render_template, request, session, url_for)

bp = Blueprint("pies", __name__)

CHOICES = ("pickup", "cant_make", "no")
DEFAULT_CANT_MAKE = ("No problem at all! I would still love to get you a pie. "
                     "Choose below whether you would like it delivered or would rather pick it up at my home.")
DEFAULT_PIES = "Pumpkin\nApple\nPecan\nCherry"


# ───────────────────────── helpers ─────────────────────────
def _db():
    from database import get_connection
    return get_connection()


def ensure_tables():
    conn = _db()
    cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS pie_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        owner_id INTEGER NOT NULL,
        owner_role TEXT NOT NULL,
        token TEXT UNIQUE NOT NULL,
        title TEXT NOT NULL,
        message TEXT,
        order_by TEXT,
        pie_types TEXT,
        price_note TEXT,
        cant_make_prompt TEXT,
        flyer_image TEXT,
        art_image TEXT,
        is_active INTEGER DEFAULT 1,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS pie_slots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        slot_date TEXT,
        start_time TEXT,
        end_time TEXT,
        location TEXT,
        capacity INTEGER,
        FOREIGN KEY (event_id) REFERENCES pie_events(id) ON DELETE CASCADE
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS pie_responses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        phone TEXT,
        email TEXT,
        choice TEXT NOT NULL,
        slot_id INTEGER,
        slot_label TEXT,
        pie_type TEXT,
        quantity INTEGER DEFAULT 1,
        notes TEXT,
        picked_up INTEGER DEFAULT 0,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (event_id) REFERENCES pie_events(id) ON DELETE CASCADE
    )""")
    # later additions (safe to run every start)
    def _add(table, col, ddl):
        have = {r[1] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()}
        if col not in have:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    _add("pie_events", "home_address", "TEXT")
    _add("pie_events", "offer_delivery", "INTEGER DEFAULT 1")
    _add("pie_events", "home_from", "TEXT")
    _add("pie_events", "home_to", "TEXT")
    _add("pie_responses", "fulfillment", "TEXT")
    _add("pie_responses", "address", "TEXT")
    _add("pie_responses", "want_date", "TEXT")
    _add("pie_responses", "want_time", "TEXT")
    _add("pie_responses", "reminded", "INTEGER DEFAULT 0")
    _add("pie_responses", "edit_token", "TEXT")
    conn.commit()
    conn.close()


def maps_url(place):
    """Google Maps directions link (opens the Maps app on phones)."""
    from urllib.parse import quote
    return "https://www.google.com/maps/dir/?api=1&destination=" + quote(place or "")


def apple_maps_url(place):
    from urllib.parse import quote
    return "https://maps.apple.com/?daddr=" + quote(place or "")


def _cal_times(d, start, end, default_minutes=60):
    """Return (start_dt, end_dt) or (date, None) for an all-day entry."""
    from datetime import timedelta
    try:
        day = datetime.strptime(d, "%Y-%m-%d")
    except (TypeError, ValueError):
        return None, None
    try:
        s = datetime.strptime(f"{d} {start}", "%Y-%m-%d %H:%M")
    except (TypeError, ValueError):
        return day.date(), None
    try:
        e = datetime.strptime(f"{d} {end}", "%Y-%m-%d %H:%M")
        if e <= s:
            e = s + timedelta(minutes=default_minutes)
    except (TypeError, ValueError):
        e = s + timedelta(minutes=default_minutes)
    return s, e


def google_cal_url(cal):
    from datetime import timedelta
    from urllib.parse import urlencode
    s, e = _cal_times(cal.get("date"), cal.get("start"), cal.get("end"), cal.get("minutes", 60))
    if s is None:
        return ""
    if e is None:
        dates = f"{s.strftime('%Y%m%d')}/{(s + timedelta(days=1)).strftime('%Y%m%d')}"
    else:
        dates = f"{s.strftime('%Y%m%dT%H%M%S')}/{e.strftime('%Y%m%dT%H%M%S')}"
    q = {"action": "TEMPLATE", "text": cal.get("title", ""), "dates": dates,
         "details": cal.get("details", ""), "location": cal.get("location", "")}
    return "https://calendar.google.com/calendar/render?" + urlencode(q)


def build_ics(cal):
    from datetime import timedelta
    s, e = _cal_times(cal.get("date"), cal.get("start"), cal.get("end"), cal.get("minutes", 60))
    if s is None:
        return None

    def esc(v):
        return (str(v or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
                .replace("\r", "").replace("\n", "\\n"))
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Your Life Your Home//Pie pickup//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "BEGIN:VEVENT", f"UID:{secrets.token_hex(8)}@yourlifeyourhome",
             "DTSTAMP:" + datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")]
    if e is None:
        lines += [f"DTSTART;VALUE=DATE:{s.strftime('%Y%m%d')}", f"DTEND;VALUE=DATE:{(s + timedelta(days=1)).strftime('%Y%m%d')}"]
    else:
        lines += [f"DTSTART:{s.strftime('%Y%m%dT%H%M%S')}", f"DTEND:{e.strftime('%Y%m%dT%H%M%S')}"]
    lines += [f"SUMMARY:{esc(cal.get('title'))}", f"LOCATION:{esc(cal.get('location'))}",
              f"DESCRIPTION:{esc(cal.get('details'))}",
              "BEGIN:VALARM", "TRIGGER:-PT1H", "ACTION:DISPLAY", "DESCRIPTION:Pie pickup in one hour", "END:VALARM",
              "END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines) + "\r\n"


def fmt_time(t):
    if not t:
        return ""
    try:
        return datetime.strptime(t, "%H:%M").strftime("%I:%M %p").lstrip("0")
    except ValueError:
        return t


def fmt_date(d):
    if not d:
        return ""
    try:
        dt = datetime.strptime(d, "%Y-%m-%d")
        return f"{dt.strftime('%a, %b')} {dt.day}"
    except ValueError:
        return d


def slot_label(s):
    s = dict(s)
    when = fmt_date(s.get("slot_date"))
    start, end = fmt_time(s.get("start_time")), fmt_time(s.get("end_time"))
    times = f"{start} to {end}" if start and end else start
    parts = [p for p in (when, times) if p]
    label = ", ".join(parts)
    if s.get("location"):
        label += f" at {s['location']}"
    return label


def _owner():
    user = _H["get_current_user"]()
    if not user or user.get("role") not in ("agent", "lender"):
        return None
    return user


def _owned_event(event_id):
    user = _owner()
    if not user:
        return None, None
    conn = _db()
    ev = conn.execute("SELECT * FROM pie_events WHERE id=? AND owner_id=?", (event_id, user["id"])).fetchone()
    conn.close()
    return user, ev


def _need_owner():
    return redirect(url_for("login"))


def _image_to_data_url(file_storage, max_width=1600, min_width=500):
    """Re-encode an uploaded photo/flyer as a modest JPEG data URL. Returns (url, error)."""
    from PIL import Image, ImageOps
    try:
        img = ImageOps.exif_transpose(Image.open(file_storage.stream))
        if img.mode in ("RGBA", "LA", "P"):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[-1])
            img = bg
        else:
            img = img.convert("RGB")
    except Exception:
        return None, "We couldn't read that file. Please upload a JPG or PNG image (for a PDF flyer, save it as an image first)."
    if img.width < min_width:
        return None, "That image is too small. Please use one at least 800 pixels wide."
    if img.width > max_width:
        img = img.resize((max_width, round(img.height * max_width / img.width)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode(), None


def _branding(owner_id):
    from database import get_user_by_id, get_user_profile
    u = get_user_by_id(owner_id)
    u = dict(u) if u else {}
    p = get_user_profile(owner_id) or {}
    p = dict(p)
    return {
        "name": u.get("name") or "",
        "role": u.get("role") or "agent",
        "email": u.get("email") or "",
        "phone": p.get("phone") or "",
        "brokerage": p.get("brokerage_name") or p.get("team_name") or "",
        "photo": p.get("professional_photo") or "",
        "logo": p.get("brokerage_logo") or "",
    }


def _slot_rows(conn, event_id):
    rows = conn.execute("SELECT * FROM pie_slots WHERE event_id=? ORDER BY slot_date, start_time, id", (event_id,)).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["label"] = slot_label(d)
        taken = conn.execute(
            "SELECT COALESCE(SUM(quantity),0) FROM pie_responses WHERE event_id=? AND slot_id=? AND choice='pickup'",
            (event_id, d["id"])).fetchone()[0]
        d["taken"] = taken
        d["full"] = bool(d.get("capacity")) and taken >= d["capacity"]
        out.append(d)
    return out


def _pie_list(ev):
    return [p.strip() for p in (ev["pie_types"] or "").splitlines() if p.strip()]


def _is_closed(ev):
    if not ev["is_active"]:
        return True
    ob = ev["order_by"]
    if ob:
        try:
            return date.today() > datetime.strptime(ob, "%Y-%m-%d").date()
        except ValueError:
            return False
    return False


def _public_url(ev):
    return url_for("pies.public_event", token=ev["token"], _external=True)


def _qr_data_url(text):
    try:
        import qrcode
        img = qrcode.make(text, box_size=8, border=2)
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception:
        return None


def _csv_safe(v):
    v = "" if v is None else str(v)
    return "'" + v if v[:1] in ("=", "+", "-", "@") else v


# ───────────────────────── owner pages ─────────────────────────
@bp.route("/pies")
def manage_list():
    user = _owner()
    if not user:
        return _need_owner()
    conn = _db()
    events = []
    for r in conn.execute("SELECT * FROM pie_events WHERE owner_id=? ORDER BY id DESC", (user["id"],)).fetchall():
        e = dict(r)
        counts = conn.execute(
            "SELECT choice, COUNT(*), COALESCE(SUM(quantity),0) FROM pie_responses WHERE event_id=? GROUP BY choice",
            (e["id"],)).fetchall()
        c = {row[0]: (row[1], row[2]) for row in counts}
        e["pies"] = c.get("pickup", (0, 0))[1] + c.get("cant_make", (0, 0))[1]
        e["people"] = sum(v[0] for v in c.values())
        e["closed"] = _is_closed(r)
        events.append(e)
    conn.close()
    return render_template("pies/manage_list.html", events=events, role=user["role"])


@bp.route("/pies/new", methods=["GET", "POST"])
@bp.route("/pies/<int:event_id>/edit", methods=["GET", "POST"])
def edit_event(event_id=None):
    user = _owner()
    if not user:
        return _need_owner()
    ev, slots = None, []
    if event_id:
        _, ev = _owned_event(event_id)
        if not ev:
            abort(404)
        conn = _db()
        slots = _slot_rows(conn, ev["id"])
        conn.close()

    if request.method == "POST":
        f = request.form
        title = (f.get("title") or "").strip()[:120]
        if not title:
            flash("Please give your event a name.", "error")
            return redirect(request.url)
        message = (f.get("message") or "").strip()[:1500]
        order_by = (f.get("order_by") or "").strip()
        pie_types = "\n".join(p.strip()[:60] for p in (f.get("pie_types") or "").splitlines() if p.strip())[:1200]
        price_note = (f.get("price_note") or "").strip()[:200]
        cant_make_prompt = (f.get("cant_make_prompt") or "").strip()[:500] or DEFAULT_CANT_MAKE
        home_address = (f.get("home_address") or "").strip()[:250]
        offer_delivery = 1 if f.get("offer_delivery") else 0
        home_from = (f.get("home_from") or "").strip()
        home_to = (f.get("home_to") or "").strip()
        try:
            datetime.strptime(home_from, "%Y-%m-%d")
        except ValueError:
            home_from = ""
        try:
            datetime.strptime(home_to, "%Y-%m-%d")
        except ValueError:
            home_to = ""
        if home_from and home_to and home_to < home_from:
            home_from, home_to = home_to, home_from
        flyer_image = ev["flyer_image"] if ev else None
        if f.get("remove_flyer"):
            flyer_image = None
        up = request.files.get("flyer")
        if up and up.filename:
            url, err = _image_to_data_url(up)
            if err:
                flash(err, "error")
                return redirect(request.url)
            flyer_image = url

        conn = _db()
        cur = conn.cursor()
        if ev:
            cur.execute("""UPDATE pie_events SET title=?, message=?, order_by=?, pie_types=?, price_note=?,
                           cant_make_prompt=?, flyer_image=?, home_address=?, offer_delivery=?,
                           home_from=?, home_to=? WHERE id=?""",
                        (title, message, order_by, pie_types, price_note, cant_make_prompt, flyer_image,
                         home_address, offer_delivery, home_from, home_to, ev["id"]))
            eid = ev["id"]
        else:
            token = secrets.token_urlsafe(9)
            cur.execute("""INSERT INTO pie_events (owner_id, owner_role, token, title, message, order_by, pie_types,
                           price_note, cant_make_prompt, flyer_image, home_address, offer_delivery, home_from, home_to)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (user["id"], user["role"], token, title, message, order_by, pie_types, price_note,
                         cant_make_prompt, flyer_image, home_address, offer_delivery, home_from, home_to))
            eid = cur.lastrowid

        # pickup slots: update existing, add new, remove the ones taken off the form
        ids = f.getlist("slot_id")
        dates, starts, ends = f.getlist("slot_date"), f.getlist("slot_start"), f.getlist("slot_end")
        locs, caps = f.getlist("slot_location"), f.getlist("slot_capacity")
        keep = []
        for i in range(len(dates)):
            d, s, e, loc = dates[i].strip(), starts[i].strip(), ends[i].strip(), locs[i].strip()[:200]
            if not (d or loc):
                continue
            try:
                cap = int(caps[i]) if caps[i].strip() else None
                cap = cap if cap and cap > 0 else None
            except ValueError:
                cap = None
            sid = ids[i].strip() if i < len(ids) else ""
            if sid.isdigit() and cur.execute("SELECT 1 FROM pie_slots WHERE id=? AND event_id=?", (int(sid), eid)).fetchone():
                cur.execute("UPDATE pie_slots SET slot_date=?, start_time=?, end_time=?, location=?, capacity=? WHERE id=?",
                            (d, s, e, loc, cap, int(sid)))
                keep.append(int(sid))
            else:
                cur.execute("INSERT INTO pie_slots (event_id, slot_date, start_time, end_time, location, capacity) VALUES (?,?,?,?,?,?)",
                            (eid, d, s, e, loc, cap))
                keep.append(cur.lastrowid)
        if keep:
            cur.execute(f"DELETE FROM pie_slots WHERE event_id=? AND id NOT IN ({','.join('?' * len(keep))})", (eid, *keep))
        else:
            cur.execute("DELETE FROM pie_slots WHERE event_id=?", (eid,))
        conn.commit()
        conn.close()
        flash("Saved. Your sign-up link is ready to share.", "success")
        return redirect(url_for("pies.event_detail", event_id=eid))

    defaults = {"pie_types": DEFAULT_PIES, "cant_make_prompt": DEFAULT_CANT_MAKE, "title": "Holiday Pie Pickup",
                "offer_delivery": 1, "home_address": "", "home_from": "", "home_to": ""}
    return render_template("pies/edit.html", ev=dict(ev) if ev else defaults, slots=slots, is_new=ev is None,
                           role=user["role"])


@bp.route("/pies/<int:event_id>")
def event_detail(event_id):
    user, ev = _owned_event(event_id)
    if not user:
        return _need_owner()
    if not ev:
        abort(404)
    conn = _db()
    slots = _slot_rows(conn, ev["id"])
    responses = [dict(r) for r in conn.execute(
        "SELECT * FROM pie_responses WHERE event_id=? ORDER BY created_at DESC, id DESC", (ev["id"],)).fetchall()]
    conn.close()
    pie_totals = {}
    for r in responses:
        if r["choice"] in ("pickup", "cant_make"):
            key = r["pie_type"] or "No preference"
            pie_totals[key] = pie_totals.get(key, 0) + (r["quantity"] or 1)
    stats = {
        "pickup": sum(1 for r in responses if r["choice"] == "pickup"),
        "cant_make": sum(1 for r in responses if r["choice"] == "cant_make"),
        "no": sum(1 for r in responses if r["choice"] == "no"),
        "pies": sum(pie_totals.values()),
        "picked_up": sum(1 for r in responses if r["picked_up"]),
    }
    return render_template("pies/detail.html", ev=dict(ev), slots=slots, responses=responses, stats=stats,
                           pie_totals=pie_totals, public_url=_public_url(ev), closed=_is_closed(ev),
                           has_ai=bool(os.environ.get("OPENAI_API_KEY")), role=user["role"])


@bp.route("/pies/<int:event_id>/toggle", methods=["POST"])
def toggle_event(event_id):
    user, ev = _owned_event(event_id)
    if not ev:
        return _need_owner()
    conn = _db()
    conn.execute("UPDATE pie_events SET is_active=? WHERE id=?", (0 if ev["is_active"] else 1, ev["id"]))
    conn.commit()
    conn.close()
    flash("Sign-ups closed." if ev["is_active"] else "Sign-ups reopened.", "success")
    return redirect(url_for("pies.event_detail", event_id=ev["id"]))


@bp.route("/pies/<int:event_id>/delete", methods=["POST"])
def delete_event(event_id):
    user, ev = _owned_event(event_id)
    if not ev:
        return _need_owner()
    conn = _db()
    conn.execute("DELETE FROM pie_responses WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM pie_slots WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM pie_events WHERE id=?", (ev["id"],))
    conn.commit()
    conn.close()
    flash("Event deleted.", "success")
    return redirect(url_for("pies.manage_list"))


@bp.route("/pies/<int:event_id>/picked-up/<int:response_id>", methods=["POST"])
def mark_picked_up(event_id, response_id):
    user, ev = _owned_event(event_id)
    if not ev:
        return _need_owner()
    conn = _db()
    conn.execute("UPDATE pie_responses SET picked_up = 1 - COALESCE(picked_up,0) WHERE id=? AND event_id=?",
                 (response_id, ev["id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("pies.event_detail", event_id=ev["id"]) + "#responses")


@bp.route("/pies/<int:event_id>/export.csv")
def export_csv(event_id):
    user, ev = _owned_event(event_id)
    if not ev:
        return _need_owner()
    conn = _db()
    rows = conn.execute("SELECT * FROM pie_responses WHERE event_id=? ORDER BY slot_label, name", (ev["id"],)).fetchall()
    conn.close()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Name", "Phone", "Email", "Answer", "Pickup", "Pie", "Quantity", "Notes", "Picked up", "Submitted"])
    names = {"pickup": "Yes, pickup", "cant_make": "Yes, needs another time", "no": "No thank you"}
    for r in rows:
        w.writerow([_csv_safe(r["name"]), _csv_safe(r["phone"]), _csv_safe(r["email"]), names.get(r["choice"], r["choice"]),
                    _csv_safe(r["slot_label"]), _csv_safe(r["pie_type"]), r["quantity"] if r["choice"] != "no" else "",
                    _csv_safe(r["notes"]), "Yes" if r["picked_up"] else "", r["created_at"]])
    return Response(out.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename=pie-responses-{ev['id']}.csv"})


@bp.route("/pies/<int:event_id>/export.xlsx")
def export_xlsx(event_id):
    """Excel workbook: every response on one sheet, plus a bake list and pickup totals."""
    user, ev = _owned_event(event_id)
    if not ev:
        return _need_owner()
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter
    conn = _db()
    rows = conn.execute("SELECT * FROM pie_responses WHERE event_id=? ORDER BY slot_label, name", (ev["id"],)).fetchall()
    conn.close()
    names = {"pickup": "Yes, pickup", "cant_make": "Yes, needs another time", "no": "No thank you"}
    head_fill = PatternFill("solid", fgColor="364A2B")
    head_font = Font(bold=True, color="FFFFFF")

    def style_header(ws, widths):
        for i, w in enumerate(widths, 1):
            c = ws.cell(row=1, column=i)
            c.fill, c.font = head_fill, head_font
            c.alignment = Alignment(vertical="center")
            ws.column_dimensions[get_column_letter(i)].width = w
        ws.freeze_panes = "A2"

    wb = Workbook()
    ws = wb.active
    ws.title = "Responses"
    ws.append(["Name", "Phone", "Email", "Answer", "Pickup", "Pie", "Notes", "Picked up", "Submitted"])
    for r in rows:
        ws.append([_csv_safe(r["name"]), _csv_safe(r["phone"]), _csv_safe(r["email"]), names.get(r["choice"], r["choice"]),
                   _csv_safe(r["slot_label"]), _csv_safe(r["pie_type"]), _csv_safe(r["notes"]),
                   "Yes" if r["picked_up"] else "", r["created_at"]])
    style_header(ws, [24, 16, 30, 24, 46, 16, 40, 12, 20])
    ws.auto_filter.ref = ws.dimensions
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")

    bl = wb.create_sheet("Bake list")
    bl.append(["Pie", "How many"])
    totals = {}
    for r in rows:
        if r["choice"] in ("pickup", "cant_make"):
            k = r["pie_type"] or "No preference"
            totals[k] = totals.get(k, 0) + 1
    for k, v in sorted(totals.items()):
        bl.append([_csv_safe(k), v])
    bl.append(["Total", sum(totals.values())])
    bl.cell(row=bl.max_row, column=1).font = Font(bold=True)
    bl.cell(row=bl.max_row, column=2).font = Font(bold=True)
    style_header(bl, [28, 12])

    pk = wb.create_sheet("By pickup")
    pk.append(["Pickup", "Pies"])
    by = {}
    for r in rows:
        if r["choice"] == "pickup":
            by[r["slot_label"]] = by.get(r["slot_label"], 0) + 1
    for k, v in sorted(by.items()):
        pk.append([_csv_safe(k), v])
    style_header(pk, [60, 10])

    buf = io.BytesIO()
    wb.save(buf)
    return Response(buf.getvalue(), mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f"attachment; filename=pie-responses-{ev['id']}.xlsx"})


@bp.route("/pies/<int:event_id>/flyer")
def flyer(event_id):
    user, ev = _owned_event(event_id)
    if not ev:
        return _need_owner()
    conn = _db()
    slots = _slot_rows(conn, ev["id"])
    conn.close()
    url = _public_url(ev)
    return render_template("pies/flyer.html", ev=dict(ev), slots=slots, pies=_pie_list(ev), brand=_branding(user["id"]),
                           public_url=url, qr=_qr_data_url(url))


@bp.route("/pies/<int:event_id>/qr.png")
def qr_png(event_id):
    """The sign-up link as a QR code image you can save, text or email. ?download=1 saves it."""
    user, ev = _owned_event(event_id)
    if not ev:
        return _need_owner()
    import qrcode
    img = qrcode.make(_public_url(ev), box_size=14, border=4)
    buf = io.BytesIO()
    img.save(buf, "PNG")
    headers = {}
    if request.args.get("download"):
        headers["Content-Disposition"] = "attachment; filename=pie-signup-qr-code.png"
    return Response(buf.getvalue(), mimetype="image/png", headers=headers)


@bp.route("/pies/<int:event_id>/ai-art", methods=["POST"])
def ai_art(event_id):
    """Optional: ask OpenAI for flyer artwork (no text in the picture). Needs OPENAI_API_KEY."""
    user, ev = _owned_event(event_id)
    if not ev:
        return _need_owner()
    back = redirect(url_for("pies.event_detail", event_id=ev["id"]))
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        flash("AI artwork needs an OpenAI key. Ask the site admin to add OPENAI_API_KEY.", "error")
        return back
    if request.form.get("action") == "remove":
        conn = _db()
        conn.execute("UPDATE pie_events SET art_image=NULL WHERE id=?", (ev["id"],))
        conn.commit()
        conn.close()
        flash("AI artwork removed.", "success")
        return back
    style = (request.form.get("style") or "").strip()[:200]
    prompt = ("Warm, elegant illustration of freshly baked holiday pies on a rustic wooden table with soft natural light, "
              "cozy and inviting, cream, olive green and golden brown color palette, wide composition with calm empty space "
              "near the top for a headline. Absolutely no text, letters or numbers anywhere in the image. "
              + (f"Extra direction: {style}" if style else ""))
    import time
    import requests
    deadline = time.time() + 105  # stay inside the server's 120 second limit
    wanted = os.environ.get("OPENAI_IMAGE_MODEL", "").strip()
    prefs = [m for m in (wanted, "gpt-image-1.5", "gpt-image-1", "gpt-image-1-mini", "dall-e-3") if m]
    models = []
    try:  # use only what this OpenAI account can actually use
        lr = requests.get("https://api.openai.com/v1/models", headers={"Authorization": f"Bearer {key}"}, timeout=12)
        ids = {m.get("id") for m in lr.json().get("data", [])} if lr.status_code == 200 else set()
    except Exception:
        ids = set()
    if ids:
        models = [m for m in prefs if m in ids] + sorted((i for i in ids if i and i.startswith("gpt-image") and i not in prefs), reverse=True)
    models = list(dict.fromkeys(models or prefs))[:4]
    art, first_status, first_msg = None, None, ""
    for model in models:
        left = deadline - time.time()
        if left < 8:
            break
        body = {"model": model, "prompt": prompt, "n": 1}
        if model.startswith("dall-e-3"):
            body.update(size="1792x1024", response_format="b64_json")
        elif model.startswith("dall-e"):
            body.update(size="1024x1024", response_format="b64_json")
        else:
            body.update(size="1536x1024")
        try:
            r = requests.post("https://api.openai.com/v1/images/generations",
                              headers={"Authorization": f"Bearer {key}"}, json=body, timeout=min(95, left))
            if r.status_code != 200:
                try:
                    msg = r.json().get("error", {}).get("message", "")
                except Exception:
                    msg = r.text[:200]
                current_app.logger.warning("pie ai art %s -> %s %s", model, r.status_code, msg)
                if first_status is None:
                    first_status, first_msg = r.status_code, msg
                continue
            item = r.json()["data"][0]
            raw = base64.b64decode(item["b64_json"]) if item.get("b64_json") else requests.get(item["url"], timeout=40).content
            from PIL import Image
            img = Image.open(io.BytesIO(raw)).convert("RGB")
            if img.width > 1400:
                img = img.resize((1400, round(img.height * 1400 / img.width)), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, "JPEG", quality=82, optimize=True)
            art = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
            break
        except Exception as exc:
            current_app.logger.warning("pie ai art failed (%s): %s", model, exc)
            if first_status is None:
                first_status, first_msg = 0, "We could not reach OpenAI."
    if not art:
        low = (first_msg or "").lower()
        if first_status == 401:
            problem = "The OpenAI key on the site is not being accepted. Please check OPENAI_API_KEY in Railway."
        elif first_status == 429 or "billing" in low or "quota" in low or "credit" in low:
            problem = "Your OpenAI account is out of credit or at its limit. Please check billing at platform.openai.com."
        elif first_status == 403 or "verif" in low:
            problem = "OpenAI needs your organization verified before it will make images. You can do that at platform.openai.com."
        elif first_msg:
            problem = f"OpenAI said: {first_msg[:220]}"
        else:
            problem = "OpenAI could not make the picture just now."
        flash(f"We couldn't create the AI picture yet. {problem} In the meantime you can upload your own flyer, and the built-in printable flyer still works.", "error")
        return back
    conn = _db()
    conn.execute("UPDATE pie_events SET art_image=? WHERE id=?", (art, ev["id"]))
    conn.commit()
    conn.close()
    flash("New artwork added to your flyer.", "success")
    return redirect(url_for("pies.flyer", event_id=ev["id"]))


# ───────────────────────── public (clients) ─────────────────────────
def _event_by_token(token):
    conn = _db()
    ev = conn.execute("SELECT * FROM pie_events WHERE token=?", (token,)).fetchone()
    conn.close()
    return ev


def _response_by_edit_token(ev, edit_token):
    if not edit_token:
        return None
    conn = _db()
    r = conn.execute("SELECT * FROM pie_responses WHERE event_id=? AND edit_token=?", (ev["id"], edit_token)).fetchone()
    conn.close()
    return r


def _edit_link(token, edit_token):
    return url_for("pies.public_event", token=token, edit_token=edit_token, _external=True)


def _form_from_response(r):
    return {"choice": r["choice"], "slot_id": str(r["slot_id"] or ""), "fulfillment": r["fulfillment"] or "",
            "delivery_address": r["address"] or "", "want_date": r["want_date"] or "", "want_time": r["want_time"] or "",
            "pie_type": r["pie_type"] or "", "notes": r["notes"] or "", "name": r["name"] or "",
            "phone": r["phone"] or "", "email": r["email"] or ""}


@bp.route("/pies/r/<token>/mine/<edit_token>/delete", methods=["POST"])
def public_delete(token, edit_token):
    ev = _event_by_token(token)
    if not ev:
        abort(404)
    r = _response_by_edit_token(ev, edit_token)
    if not r:
        abort(404)
    conn = _db()
    conn.execute("DELETE FROM pie_responses WHERE id=?", (r["id"],))
    conn.commit()
    conn.close()
    session.pop(f"pie_{token}", None)
    flash("Your response has been cancelled. You can fill the form out again any time.", "success")
    return redirect(url_for("pies.public_event", token=token))


@bp.route("/pies/<int:event_id>/response/<int:response_id>/delete", methods=["POST"])
def owner_delete_response(event_id, response_id):
    user, ev = _owned_event(event_id)
    if not ev:
        return _need_owner()
    conn = _db()
    conn.execute("DELETE FROM pie_responses WHERE id=? AND event_id=?", (response_id, ev["id"]))
    conn.commit()
    conn.close()
    flash("Response deleted.", "success")
    return redirect(url_for("pies.event_detail", event_id=ev["id"]) + "#responses")


@bp.route("/pies/<int:event_id>/response/<int:response_id>/edit")
def owner_edit_response(event_id, response_id):
    """Opens the public form pre-filled with this person's answer, so the owner can change it for them."""
    user, ev = _owned_event(event_id)
    if not ev:
        return _need_owner()
    conn = _db()
    r = conn.execute("SELECT * FROM pie_responses WHERE id=? AND event_id=?", (response_id, ev["id"])).fetchone()
    if not r:
        conn.close()
        abort(404)
    tok = r["edit_token"]
    if not tok:
        tok = secrets.token_urlsafe(16)
        conn.execute("UPDATE pie_responses SET edit_token=? WHERE id=?", (tok, r["id"]))
        conn.commit()
    conn.close()
    return redirect(url_for("pies.public_event", token=ev["token"], edit_token=tok))


@bp.route("/pies/r/<token>", methods=["GET", "POST"])
@bp.route("/pies/r/<token>/mine/<edit_token>", methods=["GET", "POST"])
def public_event(token, edit_token=None):
    ev = _event_by_token(token)
    if not ev:
        abort(404)
    editing_row = _response_by_edit_token(ev, edit_token) if edit_token else None
    if edit_token and not editing_row:
        flash("That link is no longer valid. You can fill the form out again below.", "error")
        return redirect(url_for("pies.public_event", token=token))
    conn = _db()
    slots = _slot_rows(conn, ev["id"])
    conn.close()
    if editing_row and editing_row["choice"] == "pickup" and editing_row["slot_id"]:
        # their own spot should not count against them when they re-save
        for s in slots:
            if s["id"] == editing_row["slot_id"]:
                s["taken"] -= (editing_row["quantity"] or 0)
                s["full"] = False
    brand = _branding(ev["owner_id"])
    closed = _is_closed(ev) and not editing_row
    ctx = dict(ev=dict(ev), slots=slots, pies=_pie_list(ev), brand=brand, closed=closed,
               editing=edit_token if editing_row else "",
               fmt_order_by=fmt_date(ev["order_by"]), form=_form_from_response(editing_row) if editing_row else {},
               today=date.today().isoformat(),
               home_min=max([x for x in (date.today().isoformat(), ev["home_from"] or "") if x]),
               home_max=ev["home_to"] or "", home_range=" to ".join(x for x in (fmt_date(ev["home_from"]), fmt_date(ev["home_to"])) if x))

    if request.method == "POST":
        f = request.form
        ctx["form"] = f
        if f.get("website"):  # honeypot
            return redirect(url_for("pies.public_thanks", token=token))
        if closed:
            flash("Sorry, sign-ups for this event are closed.", "error")
            return render_template("pies/public.html", **ctx)
        choice = f.get("choice")
        name = (f.get("name") or "").strip()[:100]
        phone = (f.get("phone") or "").strip()[:40]
        email = (f.get("email") or "").strip().lower()[:150]
        notes = (f.get("notes") or "").strip()[:800]
        err = None
        slot_id, slot_lbl, pie_type, qty = None, "", "", 1
        fulfil, address, want_date, want_time, cal, where = "", "", "", "", None, ""
        can_deliver, has_home = bool(ev["offer_delivery"]), bool((ev["home_address"] or "").strip())
        if choice not in CHOICES:
            err = "Please choose one of the three answers."
        elif not name:
            err = "Please enter your name."
        elif choice != "no":
            if not phone or not email:
                err = "Please enter your phone number and email so we can reach you."
            elif "@" not in email or "." not in email.split("@")[-1]:
                err = "That email address doesn't look right."
            else:
                pies = _pie_list(ev)
                pie_type = (f.get("pie_type") or "").strip()[:60]
                if pies and pie_type not in pies:
                    err = "Please choose a type of pie."
                qty = 1  # one pie per household
                if choice == "pickup" and not err:
                    sid = f.get("slot_id", "")
                    match = next((s for s in slots if str(s["id"]) == sid), None)
                    if not match:
                        err = "Please choose a pickup day, time and place."
                    elif match["capacity"] and match["taken"] + qty > match["capacity"]:
                        err = "That time is full. Please choose another."
                    else:
                        slot_id, slot_lbl = match["id"], match["label"]
                        where = match.get("location") or ""
                        cal = {"date": match["slot_date"], "start": match["start_time"], "end": match["end_time"],
                               "location": where}
                if choice == "cant_make" and not err:
                    if can_deliver or has_home:
                        fulfil = f.get("fulfillment", "")
                        if fulfil == "delivery" and can_deliver:
                            address = (f.get("delivery_address") or "").strip()[:250]
                            if len(address) < 6:
                                err = "Please enter the address where we should deliver your pie."
                            else:
                                slot_lbl = f"Delivery to {address}"
                                where = address
                        elif fulfil == "home" and has_home:
                            want_date = (f.get("want_date") or "").strip()
                            want_time = (f.get("want_time") or "").strip()
                            try:
                                d_ok = datetime.strptime(want_date, "%Y-%m-%d").date() >= date.today()
                                datetime.strptime(want_time, "%H:%M")
                            except ValueError:
                                d_ok = None
                            if d_ok is None:
                                err = "Please choose the day and time you would like to pick up."
                            elif not d_ok:
                                err = "Please choose a day that has not passed yet."
                            elif (ev["home_from"] and want_date < ev["home_from"]) or (ev["home_to"] and want_date > ev["home_to"]):
                                rng = " to ".join(x for x in (fmt_date(ev["home_from"]), fmt_date(ev["home_to"])) if x)
                                err = f"Please choose a day between {rng}."
                            else:
                                where = ev["home_address"].strip()
                                slot_lbl = f"Home pickup, {fmt_date(want_date)} at {fmt_time(want_time)}"
                                cal = {"date": want_date, "start": want_time, "end": "", "location": where, "minutes": 30}
                        else:
                            err = "Please choose delivery or pickup at the host's home."
                    elif not notes:
                        err = "Please tell us what would work for you."
        elif email and "@" not in email:
            err = "That email address doesn't look right."
        if err:
            flash(err, "error")
            return render_template("pies/public.html", **ctx)

        conn = _db()
        cur = conn.cursor()
        existing = None
        if editing_row:
            existing = {"id": editing_row["id"], "edit_token": editing_row["edit_token"]}
        elif email:
            existing = cur.execute("SELECT id, edit_token FROM pie_responses WHERE event_id=? AND lower(email)=?",
                                   (ev["id"], email)).fetchone()
        my_token = (existing["edit_token"] if existing else None) or secrets.token_urlsafe(16)
        vals = (name, phone, email, choice, slot_id, slot_lbl, pie_type, qty if choice != "no" else 0, notes,
                fulfil, address, want_date, want_time)
        if existing:
            cur.execute("""UPDATE pie_responses SET name=?, phone=?, email=?, choice=?, slot_id=?, slot_label=?,
                           pie_type=?, quantity=?, notes=?, fulfillment=?, address=?, want_date=?, want_time=?,
                           edit_token=?, reminded=0, created_at=CURRENT_TIMESTAMP WHERE id=?""",
                        (*vals, my_token, existing["id"]))
        else:
            cur.execute("""INSERT INTO pie_responses (event_id, name, phone, email, choice, slot_id, slot_label,
                           pie_type, quantity, notes, fulfillment, address, want_date, want_time, edit_token)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (ev["id"], *vals, my_token))
        conn.commit()
        conn.close()
        if cal:
            cal["title"] = f"{ev['title']}: pie pickup"
            cal["details"] = (f"{pie_type or 'Pie'} from {brand['name']}." if brand["name"] else f"{pie_type or 'Pie'} pickup.")
            if brand["phone"]:
                cal["details"] += f" Questions? {brand['phone']}"
        _notify(dict(ev), brand, name, phone, email, choice, slot_lbl, pie_type, qty, notes, bool(existing),
                fulfil=fulfil, where=where, cal=cal, edit_link=_edit_link(token, my_token))
        session[f"pie_{token}"] = {"choice": choice, "slot": slot_lbl, "pie": pie_type, "qty": qty, "name": name,
                                   "fulfil": fulfil, "where": where, "cal": cal, "edit_token": my_token}
        return redirect(url_for("pies.public_thanks", token=token))

    return render_template("pies/public.html", **ctx)


@bp.route("/pies/r/<token>/thanks")
def public_thanks(token):
    ev = _event_by_token(token)
    if not ev:
        abort(404)
    answer = session.get(f"pie_{token}") or {}
    cal = answer.get("cal")
    return render_template("pies/thanks.html", ev=dict(ev), brand=_branding(ev["owner_id"]), answer=answer,
                           gcal=google_cal_url(cal) if cal else "",
                           ics_url=url_for("pies.public_calendar", token=token) if cal and _cal_times(cal.get("date"), cal.get("start"), cal.get("end"))[0] else "")


@bp.route("/pies/r/<token>/calendar.ics")
def public_calendar(token):
    """The visitor's own confirmed pickup as a calendar file (works with Apple, Outlook and Google)."""
    ev = _event_by_token(token)
    if not ev:
        abort(404)
    cal = (session.get(f"pie_{token}") or {}).get("cal")
    data = build_ics(cal) if cal else None
    if not data:
        abort(404)
    return Response(data, mimetype="text/calendar",
                    headers={"Content-Disposition": "attachment; filename=pie-pickup.ics"})


def _notify(ev, brand, name, phone, email, choice, slot_lbl, pie_type, qty, notes, updated, fulfil="", where="", cal=None,
            edit_link=""):
    """Confirmation to the client and a heads-up to the agent/lender. Never blocks the response."""
    _bg, send_reminder_email = _H["bg"], _H["send_email"]
    owner_first = (brand["name"] or "your host").split(" ")[0]
    extras = ""
    if where and fulfil != "delivery":
        extras += f"Directions: {maps_url(where)}\n"
    if cal and google_cal_url(cal):
        extras += f"Add to your calendar: {google_cal_url(cal)}\n"
    if edit_link:
        extras += f"Change or cancel your response: {edit_link}\n"
    if extras:
        extras = "\n" + extras
    if choice == "pickup":
        line = f"{qty} x {pie_type or 'pie'} for pickup: {slot_lbl}"
        client_body = (f"Hi {name.split(' ')[0]},\n\nThank you! You're all set.\n\n{line}\n{extras}\n"
                       f"If anything changes, just fill out the form again with the same email or reply to this message.\n\n"
                       f"Warmly,\n{brand['name']}")
    elif choice == "cant_make" and fulfil == "delivery":
        line = f"{qty} x {pie_type or 'pie'}, delivered to {where}"
        client_body = (f"Hi {name.split(' ')[0]},\n\nThank you! I'll bring your pie to you as soon as I can, and I'll text or email "
                       f"before I stop by.\n\n{line}\n{extras}\nWarmly,\n{brand['name']}")
    elif choice == "cant_make" and fulfil == "home":
        line = f"{qty} x {pie_type or 'pie'}, pickup at my home: {slot_lbl}\nAddress: {where}"
        client_body = (f"Hi {name.split(' ')[0]},\n\nThank you! I'll have your pie ready for you.\n\n{line}\n{extras}\n"
                       f"If your plans change, just reply to this message.\n\nWarmly,\n{brand['name']}")
    elif choice == "cant_make":
        line = f"{qty} x {pie_type or 'pie'}. Needs a different time: {notes}"
        client_body = (f"Hi {name.split(' ')[0]},\n\nThank you! I got your note and will reach out to arrange a time that works.\n\n"
                       f"{line}\n{extras}\nWarmly,\n{brand['name']}")
    else:
        line = "No pie needed this year"
        client_body = None
    if client_body and email:
        _bg(send_reminder_email, email, f"Your pie request: {ev['title']}", client_body, brand["name"] or None, brand["email"] or None)
    if brand["email"]:
        body = (f"{'Updated response' if updated else 'New response'} for {ev['title']}\n\n{name}\n{phone}\n{email}\n\n{line}\n"
                + (f"Notes: {notes}\n" if notes and choice != "cant_make" else "")
                + f"\nSee everyone: {url_for('pies.event_detail', event_id=ev['id'], _external=True)}")
        _bg(send_reminder_email, brand["email"], f"Pie RSVP: {name} ({'no thanks' if choice == 'no' else 'yes'})", body)


def send_reminders(today=None):
    """Friendly reminder the day before a confirmed pickup. Run once a day by the scheduler.
    Returns how many were sent."""
    from datetime import timedelta
    send = _H.get("send_email")
    if not send:
        return 0
    target = ((today or date.today()) + timedelta(days=1)).isoformat()
    conn = _db()
    rows = conn.execute("""SELECT r.*, e.title, e.owner_id, e.home_address, e.token, s.slot_date, s.start_time,
                                  s.end_time, s.location
                           FROM pie_responses r JOIN pie_events e ON e.id = r.event_id
                           LEFT JOIN pie_slots s ON s.id = r.slot_id
                           WHERE COALESCE(r.reminded,0)=0 AND COALESCE(r.picked_up,0)=0 AND r.email != ''
                             AND ((r.choice='pickup' AND s.slot_date=?) OR (r.choice='cant_make' AND r.fulfillment='home' AND r.want_date=?))""",
                        (target, target)).fetchall()
    sent = 0
    for r in rows:
        brand = _branding(r["owner_id"])
        if r["choice"] == "pickup":
            cal = {"date": r["slot_date"], "start": r["start_time"], "end": r["end_time"], "location": r["location"] or ""}
            when = slot_label({"slot_date": r["slot_date"], "start_time": r["start_time"], "end_time": r["end_time"], "location": r["location"]})
            where = r["location"] or ""
        else:
            where = (r["home_address"] or "").strip()
            cal = {"date": r["want_date"], "start": r["want_time"], "end": "", "location": where, "minutes": 30}
            when = f"{fmt_date(r['want_date'])} at {fmt_time(r['want_time'])}, {where}"
        cal["title"] = f"{r['title']}: pie pickup"
        cal["details"] = f"{r['pie_type'] or 'Pie'} from {brand['name']}" if brand["name"] else "Pie pickup"
        first = (r["name"] or "there").split(" ")[0]
        body = (f"Hi {first},\n\nJust a friendly reminder that your {(r['pie_type'] + ' pie') if r['pie_type'] else 'pie'} is ready for you tomorrow.\n\n"
                f"{when}\n")
        if where:
            body += f"\nDirections: {maps_url(where)}\n"
        if google_cal_url(cal):
            body += f"Add to your calendar: {google_cal_url(cal)}\n"
        body += f"\nIf your plans changed, just reply to this message and we will sort it out.\n\nWarmly,\n{brand['name']}"
        try:
            send(r["email"], f"See you tomorrow: {r['title']}", body, brand["name"] or None, brand["email"] or None)
            conn.execute("UPDATE pie_responses SET reminded=1 WHERE id=?", (r["id"],))
            conn.commit()
            sent += 1
        except Exception as exc:
            __import__("logging").getLogger(__name__).warning("pie reminder failed: %s", exc)
    conn.close()
    return sent


_H = {}


def init_app(app, get_current_user, bg, send_email):
    _H.update(get_current_user=get_current_user, bg=bg, send_email=send_email)
    ensure_tables()
    app.register_blueprint(bp)

    @app.template_filter("pie_time")
    def _pt(v):
        return fmt_time(v)

    @app.template_filter("no_emoji")
    def _ne(v):
        import re
        return re.sub(r"[🀀-🫿☀-➿️‍]+", "", v or "").strip()

    app.add_template_global(maps_url, "maps_url")
    app.add_template_global(apple_maps_url, "apple_maps_url")

    @app.template_filter("pie_date")
    def _pd(v):
        return fmt_date(v)
