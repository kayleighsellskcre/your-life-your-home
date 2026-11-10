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

# ── the host's own calendar hides busy times ──
import urllib.request as _ur
d3 = d2 + timedelta(days=7)
while d3.weekday() > 4:
    d3 += timedelta(days=1)
ymd = lambda d: d.strftime("%Y%m%d")
ICS = f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Apple Inc.//iOS//EN
BEGIN:VTIMEZONE
TZID:America/Chicago
BEGIN:STANDARD
DTSTART:19701101T020000
RRULE:FREQ=YEARLY;BYMONTH=11;BYDAY=1SU
TZOFFSETFROM:-0500
TZOFFSETTO:-0600
END:STANDARD
BEGIN:DAYLIGHT
DTSTART:19700308T020000
RRULE:FREQ=YEARLY;BYMONTH=3;BYDAY=2SU
TZOFFSETFROM:-0600
TZOFFSETTO:-0500
END:DAYLIGHT
END:VTIMEZONE
BEGIN:VEVENT
UID:showing-1
DTSTART;TZID=America/Chicago:{ymd(d3)}T140000
DTEND;TZID=America/Chicago:{ymd(d3)}T150000
SUMMARY:Showing at 123 Main
END:VEVENT
BEGIN:VEVENT
UID:weekly-1
DTSTART;TZID=America/Chicago:{ymd(d3 - timedelta(days=14))}T100000
DTEND;TZID=America/Chicago:{ymd(d3 - timedelta(days=14))}T103000
RRULE:FREQ=WEEKLY
SUMMARY:Team meeting
END:VEVENT
BEGIN:VEVENT
UID:free-1
DTSTART;TZID=America/Chicago:{ymd(d3)}T120000
DTEND;TZID=America/Chicago:{ymd(d3)}T130000
TRANSP:TRANSPARENT
SUMMARY:Maybe lunch
END:VEVENT
BEGIN:VEVENT
UID:allday-1
DTSTART;VALUE=DATE:{ymd(d3)}
DTEND;VALUE=DATE:{ymd(d3 + timedelta(days=1))}
SUMMARY:Mom's birthday
END:VEVENT
END:VCALENDAR
""".replace("\n", "\r\n").encode()

class _Resp(io.BytesIO):
    status = 200
    def __enter__(self): return self
    def __exit__(self, *a): pass
fetched = []
_real = _ur.urlopen
def _fake(req, timeout=None):
    url = req.full_url if hasattr(req, "full_url") else req
    fetched.append(url)
    if "icloud.com" in url:
        return _Resp(ICS)
    raise OSError("HTTP Error 404: Not Found")
_ur.urlopen = _fake

ok(B.clean_cal_link("webcal://p12-caldav.icloud.com/published/2/abc") == "https://p12-caldav.icloud.com/published/2/abc", "a webcal iPhone link is accepted")
ok(B.clean_cal_link("https://evil.example.com/cal.ics") == "" and B.clean_cal_link("http://localhost/x") == "", "links to other sites are refused")
with contextlib.redirect_stdout(io.StringIO()):
    r = c.post("/booking/save", data={**form, "busy_new": "https://evil.example.com/cal.ics"}, follow_redirects=True)
ok(b"did not look right" in r.data and B.get_settings(ag)["busy_list"] == [], "a bad calendar link is refused kindly and not saved")
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/booking/save", data={**form, "busy_new": "webcal://p12-caldav.icloud.com/published/2/abc"})
s = B.get_settings(ag); s["user_id"] = ag
ok(s["busy_list"] == ["https://p12-caldav.icloud.com/published/2/abc"], "the iPhone calendar link is saved")
times = B.open_times(s, d3)
ok("14:00" not in times and "14:30" not in times, "a showing at 2 PM hides 2:00 and 2:30")
ok("13:30" in times and "15:00" in times, "the times right before and after the showing stay open")
ok("10:00" not in times, "a weekly repeating meeting hides its time")
ok("12:00" in times and "09:00" in times, "free events and all-day events do not block times")
nxt = d3 + timedelta(days=7)
ok("10:00" not in B.open_times(s, nxt) and "14:00" in B.open_times(s, nxt), "the weekly meeting repeats, the one-time showing does not")
with contextlib.redirect_stdout(io.StringIO()):
    page = c.get("/agent/booking")
ok(b"iPhone (iCloud) calendar" in page.data and b"busy time" in page.data and b"Showing at 123 Main" not in page.data,
   "the setup page shows the calendar is connected, without event names")
pub = c.get(f"/book/{token}?d={d3.isoformat()}")
ok(b"Showing at 123 Main" not in pub.data and b"Team meeting" not in pub.data, "clients never see event names")
with contextlib.redirect_stdout(io.StringIO()):
    rb = c.post(f"/book/{token}", data={"name": "Sam", "email": "sam@x.com", "phone": "9135551234", "day": d3.isoformat(), "time": "14:00"})
ok(rb.status_code == 400, "a busy time cannot be booked even by sending the form directly")
n = len(fetched)
B.open_times(s, d3); B.open_times(s, nxt)
ok(len(fetched) == n, "the calendar is read once and reused for a few minutes")
B._busy_cache.clear()
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/booking/save", data={**form, "busy_url": "https://p12-caldav.icloud.com/published/2/abc",
                                  "busy_new": "https://calendar.google.com/calendar/ical/x/private-y/basic.ics"})
s = B.get_settings(ag); s["user_id"] = ag
ok(len(s["busy_list"]) == 2, "a second calendar can be added")
ok("14:00" not in B.open_times(s, d3), "one calendar failing does not stop the other from hiding times")
chk = B.busy_check(s)
ok(any(not x["ok"] and "could not read" in x["text"] for x in chk), "a calendar that cannot be read is flagged on the setup page")
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/booking/save", data={**form})
ok(B.get_settings(ag)["busy_list"] == [], "unticking calendars disconnects them")
_ur.urlopen = _real
