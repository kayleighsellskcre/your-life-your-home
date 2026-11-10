import os, sys, tempfile, io, contextlib
from datetime import timedelta
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
import booking as B
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

A.app.config["TESTING"] = True
sent = []
B._H["send_email"] = lambda to, subj, body, *a, **kw: (sent.append((to, subj, body, kw.get("html"))) or True)
B._H["html_ok"] = True

ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
c = A.app.test_client()
with c.session_transaction() as s:
    s["user_id"] = ag; s["role"] = "agent"

today = B.now_local("America/Chicago").date()
d1 = today + timedelta(days=7)
while d1.weekday() > 4:
    d1 += timedelta(days=1)
d2 = d1 + timedelta(days=1)
while d2.weekday() > 4:
    d2 += timedelta(days=1)
form = {"enabled": "1", "start_time": "09:00", "end_time": "17:00", "minutes": "30", "notice_hours": "4",
        "tz": "America/Chicago", "title": "Let's chat", "place": "Phone call. I will call you at the number you give me.",
        **{"day_" + k: "1" for k in ["mon", "tue", "wed", "thu", "fri"]}}
with contextlib.redirect_stdout(io.StringIO()):
    page = c.get("/agent/booking")
ok(page.status_code == 200 and b"How to set this up" in page.data, "the setup steps show on Booking & Calendar")

# days off
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/booking/save", data={**form, "block_from": d1.isoformat()})
s = B.get_settings(ag); s["user_id"] = ag
ok(d1.isoformat() in s["blocked"], "a single day off is saved")
ok(B.open_times(s, d1) == [], "no times are offered on a day off")
ok(B.open_times(s, d2) != [], "the next working day is still open")
ok(d1.isoformat() not in B.open_days(s, limit=60), "the day off is not listed for clients")
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/booking/save", data={**form, "blocked": d1.isoformat(), "block_from": d2.isoformat(), "block_to": (d2 + timedelta(days=2)).isoformat()})
s = B.get_settings(ag)
ok(d1.isoformat() in s["blocked"] and d2.isoformat() in s["blocked"] and len(s["blocked"]) == 4, "a stretch of days off adds every day and keeps the old one")
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/booking/save", data={**form, "blocked": d1.isoformat()})
s = B.get_settings(ag)
ok(s["blocked"] == [d1.isoformat()], "unticking days opens them back up")
with contextlib.redirect_stdout(io.StringIO()):
    r = c.post("/booking/save", data={**form, "block_from": d2.isoformat(), "block_to": d1.isoformat()}, follow_redirects=True)
ok(b"last day needs to come on or after" in r.data, "a backwards stretch of days off is refused kindly")

# phone required when meeting by phone
s = B.get_settings(ag)
ok(s["needs_phone"], "a phone-call meeting asks for a phone number")
token = s["token"]
pub = c.get(f"/book/{token}?d={d2.isoformat()}")
ok(b'name="phone"' in pub.data and b"(optional)</span></label><input class=\"pie-input\" type=\"tel\"" not in pub.data, "the phone box is not marked optional")
t = B.open_times({**s, "user_id": ag}, d2)[0]
book = {"name": "Pat Client", "email": "pat@x.com", "day": d2.isoformat(), "time": t}
with contextlib.redirect_stdout(io.StringIO()):
    r1 = c.post(f"/book/{token}", data=book)
ok(r1.status_code == 400 and b"phone number" in r1.data, "booking without a phone number is stopped with a kind note")
with contextlib.redirect_stdout(io.StringIO()):
    r2 = c.post(f"/book/{token}", data={**book, "phone": "913-555-1234"})
ok(r2.status_code == 302, "booking with a phone number goes through")

# emails
client = [m for m in sent if m[0] == "pat@x.com"]
host = [m for m in sent if m[0] == "amy@x.com"]
ok(len(client) == 1 and len(host) == 1, "the client and the host each get one email")
cbody, chtml = client[0][2], client[0][3] or ""
ok("calendar.google.com" not in cbody and "/b/" in cbody, "the plain email has one short link, not a long calendar address")
ok("Add to Google Calendar</a>" in chtml and "Add to Apple or Outlook</a>" in chtml and "Change or cancel</a>" in chtml,
   "the HTML email has labeled buttons")
ok("—" not in cbody + chtml + host[0][2] + (host[0][3] or ""), "no em dashes in the emails")
ok("913-555-1234" in host[0][2] and "See my bookings</a>" in (host[0][3] or ""), "the host note shows the phone and a bookings button")
btok = cbody.split("/b/")[1].split()[0]
ok(c.get(f"/b/{btok}").status_code == 200, "the short link opens the booking")

# a video meeting keeps phone optional
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/booking/save", data={**form, "place": "Zoom. I will send you the link."})
ok(not B.get_settings(ag)["needs_phone"], "a video meeting keeps the phone number optional")
