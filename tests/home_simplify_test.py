import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

sent = []
A._bg = lambda fn, *a, **k: fn(*a, **k)
import home_value as HV
HV._ns["_bg"] = A._bg
HV._ns["send_reminder_email"] = lambda to, subject, body, **k: sent.append((to, subject, body, k)) or True

c = A.app.test_client()
t = c.get("/").get_data(as_text=True)
ok(t.count("Learn more") == 3, "the three cards each have one Learn more button")
ok("Agent Sign In" not in t and "Lender Sign In" not in t, "Agent Sign In and Lender Sign In are gone from the home page")
for s in ("A calm place to keep track of the house you love.", "Stay close to every client, without the extra work.", "Keep in touch long after closing.",
          "Know your home's value, care for it, and plan your next move, all in one calm place."):
    ok(s in t or s.replace("'", "&#39;") in t, "home page says: " + s[:40])
ok("Loan Officer" not in t and "loan officer" not in t.lower(), "no Loan Officers wording on the home page")
for p in ("/homeowners", "/agents", "/lenders"):
    ok(f'href="{p}"' in t, f"a card links to {p}")
ok("cloudcma" not in t and "/home-value" in t, "Discover Your Home's Worth stays on the site")
import re
ok(chr(8212) not in re.sub(r"(?s)<(style|script).*?</(style|script)>", "", t), "no em dashes on the home page")

default = D.get_or_create_default_agent()
agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
home = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=agent)
ok(c.get("/home-value").status_code == 200, "the home value form opens for visitors")
r = c.post("/home-value", data={"address": "", "name": "Z", "email": "bad"})
ok(r.status_code == 400 and not sent, "an incomplete request is not sent")
r = c.post("/home-value", data={"address": "1 Oak St, Kansas City", "name": "Vi Visitor", "email": "vi@x.com"})
ok(r.status_code == 200 and sent and sent[-1][0] == "kayleighsellskcre@gmail.com", "a visitor with no agent goes to the default agent")
ok(sent[-1][3].get("reply_to") == "vi@x.com", "replying goes to the visitor")
h = A.app.test_client()
with h.session_transaction() as s: s["user_id"] = home; s["role"] = "homeowner"; s["name"] = "Hal"
r = h.post("/home-value", data={"address": "2 Elm St", "name": "Hal", "email": "hal@x.com", "note": "line\nbreak"})
ok(sent[-1][0] == "amy@x.com", "a homeowner's request goes to their own agent")
ok(h.get("/home-value").get_data(as_text=True).count("hal@x.com") >= 1, "a signed in homeowner's name and email are filled in")
conn = D.get_connection()
n = conn.execute("SELECT COUNT(*) FROM home_value_requests").fetchone()[0]
conn.close()
ok(n == 2, "both requests are saved")

a = A.app.test_client()
with a.session_transaction() as s: s["user_id"] = agent; s["role"] = "agent"; s["name"] = "Amy"
t = a.get("/agent/my-clients").get_data(as_text=True)
ok("Home value requests (1)" in t and "2 Elm St" in t and "1 Oak St" not in t, "an agent sees only the home value requests sent to them")
ok("Stay close to every client, without the extra work." in c.get("/agents").get_data(as_text=True), "the For Agents page matches its card")
ok("Keep in touch long after closing." in c.get("/lenders").get_data(as_text=True), "the For Lenders page matches its card")
