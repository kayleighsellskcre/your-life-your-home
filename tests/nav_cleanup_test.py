import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
lender = D.create_user("Lou Lender", "lou@x.com", gp("password123"), "lender")
home = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=agent)
D.connect_homeowner_to_professional(home, lender, "lender", replace=True)
sent = []
A._bg = lambda fn, *a, **k: fn(*a, **k)
A.send_reminder_email = lambda to, subject, body, **k: sent.append((to, subject, body)) or True


def who(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c


a, l, h = who(agent, "agent"), who(lender, "lender"), who(home, "homeowner")
brand = lambda t: re.search(r'<a id="ylhBrand" href="([^"]*)"', t).group(1)
ok(brand(a.get("/agent/my-clients").get_data(as_text=True)) == "/agent/my-clients", "an agent's logo goes to My Clients")
ok(brand(l.get("/lender/clients").get_data(as_text=True)) == "/lender/clients", "a lender's logo goes to My Clients")
ok(brand(h.get("/homeowner/my-home").get_data(as_text=True)) == "/homeowner/my-home", "a homeowner's logo goes to My Home")
ok(brand(A.app.test_client().get("/").get_data(as_text=True)) == "/", "a visitor's logo goes to the public home page")
ok(A._AREA_HOME == {"agent": "portal.agent_my_clients", "lender": "lender_clients", "homeowner": "portal.my_home"}, "wrong-area redirects use the new landing pages")
ok(a.get("/homeowner/my-home").headers["Location"].endswith("/agent/my-clients"), "an agent opening a homeowner page lands on My Clients")
ok(h.get("/agent/my-clients").headers["Location"].endswith("/homeowner/my-home"), "a homeowner opening an agent page lands on My Home")

# lender My Clients matches the agent page
t = l.get("/lender/clients").get_data(as_text=True)
ok("Invite a homeowner" in t and "Your clients (" in t, "the lender page has an invite form and a client list")
ok(all(x not in t for x in ("live portal data", "CRM Status", "View Portal")), "the old wording is gone from the lender page")
r = l.post("/lender/my-clients/invite", data={"name": "Pat Buyer", "email": "pat@x.com", "phone": "5551234567", "send_email": "1"})
ok(r.status_code == 302 and "invited=" in r.headers["Location"], "a lender can invite a homeowner")
ok(sent and sent[-1][0] == "pat@x.com" and "ref=" in sent[-1][2], "the invite email carries the lender's personal link")
t = l.get(r.headers["Location"]).get_data(as_text=True)
ok("Copy link" in t and "Text it to them" in t and "Send Pat Buyer their link" in t, "the lender gets Copy link and Text it")
ok("Pat Buyer" in l.get("/lender/clients").get_data(as_text=True), "the invited person is listed as waiting")
ok(l.post(f"/lender/my-clients/{home}/move-in", data={"move_in_date": "2025-06-01"}).status_code == 302, "a lender can add a move-in date")
ok("Moved in 2025-06-01" in l.get("/lender/clients").get_data(as_text=True), "the move-in date shows")
ok(a.post("/lender/my-clients/invite", data={"name": "X", "email": "x@x.com"}).status_code == 302 and sent[-1][0] == "pat@x.com", "an agent cannot use the lender invite")
ok(l.get("/lender/messages").status_code == 200 and "email and text library" in l.get("/messages").get_data(as_text=True), "lender Messages links to the Email and Text Library")
ok("Communications" in a.get("/agent/send-update").get_data(as_text=True), "agent Send an Update links to Communications")

# menus
def menu(t):
    t = t[t.index('id="ylhHamMenu"'):]
    return t[:t.index("Sign Out")].replace("</a>", "<")
ma = menu(a.get("/agent/my-clients").get_data(as_text=True))
for head in ("Today", "Clients and deals", "Marketing", "Business", "Seasonal and extras"):
    ok(f'ylh-ham-head">{head}<' in ma, f"agent More has the heading {head}")
for gone in ("Invite Clients", "Client Portal", "Communications"):
    ok(f">{gone}<" not in ma, f"agent menu no longer lists {gone}")
ok("Invite a homeowner" in a.get("/agent/my-clients").get_data(as_text=True) and "Open the full client list" not in a.get("/agent/my-clients").get_data(as_text=True), "My Clients holds the invite form and is the one client list")
ml = menu(l.get("/lender/clients").get_data(as_text=True))
for head in ("Clients", "Keep in touch", "Marketing", "Business"):
    ok(f'ylh-ham-head">{head}<' in ml, f"lender More has the heading {head}")
ok(all(f">{g}<" not in ml for g in ("Invite Clients", "Email &amp; Text Library", "Power Suite", "Roles &amp; Partners")), "lender menu has no repeats or vague names")
mh = menu(h.get("/homeowner/my-home").get_data(as_text=True))
for head in ("My home records", "Care and projects", "Plan my next move"):
    ok(f'ylh-ham-head">{head}<' in mh, f"homeowner More has the heading {head}")
ok(">Full home overview<" not in mh and ">Get Help<" in mh and ">My Profile<" in mh, "homeowner menu: no overview, Get Help and My Profile present")

# My Profile
t = h.get("/homeowner/profile").get_data(as_text=True)
ok("My Profile" in t and "hal@x.com" in t and "Hal Homeowner" in t, "My Profile opens with the homeowner's details")
r = h.post("/homeowner/profile", data={"name": "Hal H", "phone": "5559990000", "frost_alerts": "on"})
t = h.get("/homeowner/profile").get_data(as_text=True)
ok(r.status_code == 302 and 'value="Hal H"' in t and "5559990000" in t, "name and phone save")
conn = D.get_connection()
row = conn.execute("SELECT frost_alerts, seasonal_tips FROM care_prefs WHERE user_id = ?", (home,)).fetchone()
dg = conn.execute("SELECT digest_enabled FROM users WHERE id = ?", (home,)).fetchone()[0]
conn.close()
ok(row and row[0] == 1 and row[1] == 0 and dg == 0, "unticked emails are turned off")
ok(h.post("/homeowner/profile", data={"name": ""}).status_code == 302 and 'value="Hal H"' in h.get("/homeowner/profile").get_data(as_text=True), "an empty name is refused")
ok(a.get("/homeowner/profile").status_code == 302, "only homeowners can open My Profile")
t = A.app.test_client().get("/privacy").get_data(as_text=True)
ok("kayleighsellskcre@gmail.com" in t and "kayleighsellskcre@gmail.com" in A.app.test_client().get("/terms").get_data(as_text=True), "Privacy and Terms show the contact email")
