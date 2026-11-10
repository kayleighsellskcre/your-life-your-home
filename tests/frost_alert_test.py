import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, care_alerts as CA
from datetime import datetime, timedelta, timezone
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

calls = {"census": 0, "nws": 0}


def iso(h):
    return (datetime.now(timezone.utc) + timedelta(hours=h)).isoformat()


def fake_http(url, headers=None, timeout=8):
    if "geocoding.geo.census.gov" in url:
        calls["census"] += 1
        q = url.lower()
        if "nowhere" in q:
            return {"result": {"addressMatches": []}}
        lat = 38.90 if "cold" in q else 30.10
        return {"result": {"addressMatches": [{"coordinates": {"x": -94.80, "y": lat}}]}}
    if "api.weather.gov/points/" in url:
        calls["nws"] += 1
        lat = url.split("/points/")[1].split(",")[0]
        return {"properties": {"forecast": f"https://api.weather.gov/gridpoints/T/{lat}/forecast"}}
    cold = "/38.9" in url
    return {"properties": {"periods": [
        {"name": "Tonight", "startTime": iso(3), "temperature": 27 if cold else 48, "temperatureUnit": "F"},
        {"name": "Wednesday Night", "startTime": iso(27), "temperature": 35 if cold else 50, "temperatureUnit": "F"},
        {"name": "Friday Night", "startTime": iso(80), "temperature": 5, "temperatureUnit": "F"},   # outside two days: ignored
    ]}}


CA._http_get_json = fake_http
sent = []
A.send_reminder_email = lambda to, subj, body, **kw: (sent.append((to, subj, body)) or True)
A._bg = lambda fn, *a, **k: fn(*a, **k)

ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
other = D.create_user("Other Agent", "oa@x.com", gp("password123"), "agent")
conn = D.get_connection()


def ho(name, email, addr, agent, phone=None):
    h = D.create_user(name, email, gp("password123"), "homeowner", agent_id=agent)
    D.add_property(h, addr, 300000.0, "primary")
    if phone:
        conn.execute("UPDATE users SET phone=? WHERE id=?", (phone, h)); conn.commit()
    return h


a = ho("Cora Cold", "cora@x.com", "1 Cold St, Shawnee, KS 66203", ag, "(913) 555-0101")
b = ho("Mina Mild", "mina@x.com", "2 Warm Ave, Austin, TX 78701", ag)
c = ho("Opt Out", "opt@x.com", "3 Cold Rd, Olathe, KS 66061", ag)
f = ho("Not Mine", "nm@x.com", "4 Cold Ln, Lenexa, KS 66215", other)
nw = ho("Lost Lee", "lost@x.com", "5 Nowhere Blvd", ag)
conn.execute("INSERT INTO home_details (user_id, sprinkler, outdoor_faucets) VALUES (?,1,1)", (a,))
conn.execute("INSERT INTO care_prefs (user_id, frost_alerts, seasonal_tips) VALUES (?,0,1)", (c,))
conn.commit()
D.add_agent_contact(ag, "Dan Past", email="dan@x.com", property_address="6 Cold Ct, Overland Park, KS 66210")
D.add_agent_contact(ag, "Tex Only", phone="9135550199", property_address="7 Cold Way, Gardner, KS 66030")
D.add_agent_contact(ag, "No Place", email="np@x.com")
D.add_agent_contact(other, "Other Past", email="op@x.com", property_address="8 Cold Dr, Leawood, KS 66211")


def client(uid, role):
    cl = A.app.test_client()
    with cl.session_transaction() as s: s["user_id"] = uid; s["role"] = role
    return cl


ca = client(ag, "agent")

# forecast math
low = CA.forecast_low(38.90, -94.80)
ok(low["low"] == 27 and low["when"] == "Tonight", "coldest period in the next two days is found (and the one 3 days out is ignored)")
CA._forecast_cache.clear()
CA._http_get_json = lambda url, headers=None, timeout=8: fake_http(url, headers, timeout) if "/points/" in url else {"properties": {"periods": [{"name": "Tonight", "startTime": iso(2), "temperature": -2, "temperatureUnit": "C"}]}}
ok(CA.forecast_low(38.9, -94.8)["low"] == 28, "Celsius is converted to Fahrenheit")
CA._http_get_json = fake_http; CA._forecast_cache.clear()

# page and check
r = ca.get("/frost-alert"); t = r.get_data(as_text=True)
ok(r.status_code == 200 and "Check the forecast" in t and "Nothing goes out until you review it" in t, "page loads and promises review first")
r = ca.post("/frost-alert/check", data={"threshold": "32"}); t = r.get_data(as_text=True)
ok(r.status_code == 200 and "Cora Cold" in t and "Dan Past" in t and "Tex Only" in t, "lists homeowners and CRM past clients with addresses")
ok("Not Mine" not in t and "Other Past" not in t, "another agent's people never appear")
ok("No Place" not in t, "a contact with no home address is left out")
ok("27°F" in t and "Tonight" in t, "shows the forecast low and when")
ok("Could not find this address" in t, "an address we cannot find says so")
ok("Mina Mild" in t and "no freeze" in t, "a warm home is shown as no freeze")
ok("Has a sprinkler system" in t and "Opted out of alerts" in t, "shows sprinkler and opted-out notes")
ok("sms:9135550101?&amp;body=" in t or "sms:9135550101?&body=" in t, "tap-to-text link uses the person's phone and a prefilled message")
ok(re.search(r'value="u%d"[^>]*checked' % a, t) and not re.search(r'value="u%d"[^>]*checked' % b, t) and not re.search(r'value="u%d"[^>]*checked' % c, t),
   "affected homes are pre-checked; warm and opted-out ones are not")
ok("Text" in t and "from your real number" in t, "explains the text button")
n_before = calls["census"]
ca.post("/frost-alert/check", data={"threshold": "32"})
ok(calls["census"] == n_before, "addresses are remembered, even ones not found, so nothing is looked up twice (%d new lookups)" % (calls["census"] - n_before))
CA.THRESHOLDS = (20, 28, 32)
r = ca.post("/frost-alert/check", data={"threshold": "20"}); t = r.get_data(as_text=True)
ok("Nothing freezing" in t, "a colder threshold finds no freeze and says no alert needed")
CA.THRESHOLDS = (28, 30, 32, 34, 36)
ok(ca.post("/frost-alert/check", data={"threshold": "abc"}).status_code == 200, "odd threshold is safe")

# sending
dan = [p for p in CA.people_for("agent", ag) if p["name"] == "Dan Past"][0]["key"]
tex = [p for p in CA.people_for("agent", ag) if p["name"] == "Tex Only"][0]["key"]
foreign = f"u{f}"
r = ca.post("/frost-alert/send", data={"who": [f"u{a}", dan, f"u{c}", foreign, tex], "subject": "Freeze heads-up", "message": "Hi {first},\n\nFreeze tonight.", "low": "27"})
tos = [x[0] for x in sent]
ok(r.status_code == 302 and "cora@x.com" in tos and "dan@x.com" in tos, "emails go to the checked people")
ok("opt@x.com" not in tos, "an opted-out homeowner is never emailed, even if posted")
ok("nm@x.com" not in tos, "another agent's client is never emailed, even if posted")
ok("9135550199" not in " ".join(tos) and len(tos) == 2, "a phone-only contact gets no email")
cora = next(x for x in sent if x[0] == "cora@x.com")
ok("Hi Cora," in cora[2] and "sprinkler system" in cora[2] and "Amy Agent" in cora[2] and "/homeowner/care/preferences" in cora[2], "email uses first name, sprinkler line, signature and the preferences link")
danm = next(x for x in sent if x[0] == "dan@x.com")
ok("sprinkler" not in danm[2] and "just reply" in danm[2] and "Hi Dan," in danm[2], "CRM contact gets no sprinkler line and a reply-to-opt-out note")
sent.clear()
ca.post("/frost-alert/send", data={"who": [f"u{a}", dan], "message": "Hi {first}"})
ok(sent == [], "nobody is alerted twice within 12 hours")
t = ca.post("/frost-alert/check", data={"threshold": "32"}).get_data(as_text=True)
ok("Alerted in the last 12 hours" in t, "page shows who was already alerted")
ok(ca.post("/frost-alert/send", data={"who": []}).status_code == 302 and sent == [], "sending with nobody checked does nothing")

# homeowner preferences
hc = client(a, "homeowner")
t = hc.get("/homeowner/care/preferences").get_data(as_text=True)
ok("Sprinkler system" in t and "Freeze heads-ups" in t, "homeowner sees details and alert choices")
hc.post("/homeowner/care/preferences", data={"fireplace": "on", "move_in_date": "2020-05-01"})
d, p = CA.get_details(a), CA.get_prefs(a)
ok(d["fireplace"] == 1 and d["sprinkler"] == 0 and d["outdoor_faucets"] == 0 and d["move_in_date"] == "2020-05-01", "details are saved (unchecked boxes turn off)")
ok(p["frost_alerts"] == 0 and p["seasonal_tips"] == 0, "alerts are off when the boxes are unchecked")
ok(client(ag, "agent").get("/homeowner/care/preferences").status_code == 302, "agents cannot open the homeowner page")
ok(A.app.test_client().get("/frost-alert").status_code == 302, "signed-out visitors go to login")
ok(client(a, "homeowner").get("/frost-alert").status_code == 302, "homeowners cannot open the frost alert page")

# lender
ln = D.create_user("Lena Lender", "lena@x.com", gp("password123"), "lender")
lh = D.create_user("Lou Loan", "lou@x.com", gp("password123"), "homeowner", lender_id=ln)
D.add_property(lh, "9 Cold Pl, Shawnee, KS 66203", 250000.0, "primary")
lc = client(ln, "lender")
t = lc.post("/frost-alert/check", data={"threshold": "32"}).get_data(as_text=True)
ok("Lou Loan" in t and "Cora Cold" not in t, "lenders see only their own clients")
t = lc.get("/lender").get_data(as_text=True); ok("Frost Alert" in t, "lender menu has the link")
t = ca.get("/agent").get_data(as_text=True); ok("Frost Alert" in t, "agent menu has the link")
t = hc.get("/homeowner").get_data(as_text=True); ok("Home Details" in t, "homeowner menu has the link")
