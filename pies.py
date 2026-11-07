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
DEFAULT_CANT_MAKE = ("No problem. Tell us what would work, for example a different day or time, "
                     "or picking one up at my home, and we'll arrange it.")
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
    conn.commit()
    conn.close()


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
                           cant_make_prompt=?, flyer_image=? WHERE id=?""",
                        (title, message, order_by, pie_types, price_note, cant_make_prompt, flyer_image, ev["id"]))
            eid = ev["id"]
        else:
            token = secrets.token_urlsafe(9)
            cur.execute("""INSERT INTO pie_events (owner_id, owner_role, token, title, message, order_by, pie_types,
                           price_note, cant_make_prompt, flyer_image) VALUES (?,?,?,?,?,?,?,?,?,?)""",
                        (user["id"], user["role"], token, title, message, order_by, pie_types, price_note,
                         cant_make_prompt, flyer_image))
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

    defaults = {"pie_types": DEFAULT_PIES, "cant_make_prompt": DEFAULT_CANT_MAKE, "title": "Holiday Pie Pickup"}
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
    try:
        import requests
        r = requests.post("https://api.openai.com/v1/images/generations",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": os.environ.get("OPENAI_IMAGE_MODEL", "gpt-image-1"), "prompt": prompt,
                                "size": "1536x1024", "n": 1},
                          timeout=120)
        r.raise_for_status()
        item = r.json()["data"][0]
        if item.get("b64_json"):
            raw = base64.b64decode(item["b64_json"])
        else:
            raw = requests.get(item["url"], timeout=60).content
        from PIL import Image
        img = Image.open(io.BytesIO(raw)).convert("RGB")
        if img.width > 1400:
            img = img.resize((1400, round(img.height * 1400 / img.width)), Image.LANCZOS)
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=82, optimize=True)
        art = "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()
    except Exception as exc:
        current_app.logger.warning("pie ai art failed: %s", exc)
        flash("We couldn't create artwork just now. Please try again in a minute.", "error")
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


@bp.route("/pies/r/<token>", methods=["GET", "POST"])
def public_event(token):
    ev = _event_by_token(token)
    if not ev:
        abort(404)
    conn = _db()
    slots = _slot_rows(conn, ev["id"])
    conn.close()
    brand = _branding(ev["owner_id"])
    closed = _is_closed(ev)
    ctx = dict(ev=dict(ev), slots=slots, pies=_pie_list(ev), brand=brand, closed=closed,
               fmt_order_by=fmt_date(ev["order_by"]), form={})

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
                try:
                    qty = max(1, min(int(f.get("quantity") or 1), 10))
                except ValueError:
                    qty = 1
                if choice == "pickup" and not err:
                    sid = f.get("slot_id", "")
                    match = next((s for s in slots if str(s["id"]) == sid), None)
                    if not match:
                        err = "Please choose a pickup day, time and place."
                    elif match["capacity"] and match["taken"] + qty > match["capacity"]:
                        err = "That time is full. Please choose another."
                    else:
                        slot_id, slot_lbl = match["id"], match["label"]
                if choice == "cant_make" and not err and not notes:
                    err = "Please tell us what would work for you."
        elif email and "@" not in email:
            err = "That email address doesn't look right."
        if err:
            flash(err, "error")
            return render_template("pies/public.html", **ctx)

        conn = _db()
        cur = conn.cursor()
        existing = None
        if email:
            existing = cur.execute("SELECT id FROM pie_responses WHERE event_id=? AND lower(email)=?",
                                   (ev["id"], email)).fetchone()
        vals = (name, phone, email, choice, slot_id, slot_lbl, pie_type, qty if choice != "no" else 0, notes)
        if existing:
            cur.execute("""UPDATE pie_responses SET name=?, phone=?, email=?, choice=?, slot_id=?, slot_label=?,
                           pie_type=?, quantity=?, notes=?, created_at=CURRENT_TIMESTAMP WHERE id=?""", (*vals, existing["id"]))
        else:
            cur.execute("""INSERT INTO pie_responses (event_id, name, phone, email, choice, slot_id, slot_label,
                           pie_type, quantity, notes) VALUES (?,?,?,?,?,?,?,?,?,?)""", (ev["id"], *vals))
        conn.commit()
        conn.close()
        _notify(dict(ev), brand, name, phone, email, choice, slot_lbl, pie_type, qty, notes, bool(existing))
        session[f"pie_{token}"] = {"choice": choice, "slot": slot_lbl, "pie": pie_type, "qty": qty, "name": name}
        return redirect(url_for("pies.public_thanks", token=token))

    return render_template("pies/public.html", **ctx)


@bp.route("/pies/r/<token>/thanks")
def public_thanks(token):
    ev = _event_by_token(token)
    if not ev:
        abort(404)
    return render_template("pies/thanks.html", ev=dict(ev), brand=_branding(ev["owner_id"]),
                           answer=session.get(f"pie_{token}") or {})


def _notify(ev, brand, name, phone, email, choice, slot_lbl, pie_type, qty, notes, updated):
    """Confirmation to the client and a heads-up to the agent/lender. Never blocks the response."""
    _bg, send_reminder_email = _H["bg"], _H["send_email"]
    owner_first = (brand["name"] or "your host").split(" ")[0]
    if choice == "pickup":
        line = f"{qty} x {pie_type or 'pie'} for pickup: {slot_lbl}"
        client_body = (f"Hi {name.split(' ')[0]},\n\nThank you! You're all set.\n\n{line}\n\n"
                       f"If anything changes, just fill out the form again with the same email or reply to this message.\n\n"
                       f"Warmly,\n{brand['name']}")
    elif choice == "cant_make":
        line = f"{qty} x {pie_type or 'pie'}. Needs a different time: {notes}"
        client_body = (f"Hi {name.split(' ')[0]},\n\nThank you! I got your note and will reach out to arrange a time that works.\n\n"
                       f"{line}\n\nWarmly,\n{brand['name']}")
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


_H = {}


def init_app(app, get_current_user, bg, send_email):
    _H.update(get_current_user=get_current_user, bg=bg, send_email=send_email)
    ensure_tables()
    app.register_blueprint(bp)

    @app.template_filter("pie_time")
    def _pt(v):
        return fmt_time(v)

    @app.template_filter("pie_date")
    def _pd(v):
        return fmt_date(v)
