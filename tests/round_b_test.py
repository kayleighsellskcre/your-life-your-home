import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
other = D.create_user("Olly Other", "olly@x.com", gp("password123"), "agent")
lender = D.create_user("Lou Lender", "lou@x.com", gp("password123"), "lender")
home = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=agent)
D.connect_homeowner_to_professional(home, lender, "lender", replace=True)
D.add_property(home, "10 First St, Shawnee, KS 66226", 250000.0, "primary")
A._bg = lambda fn, *a, **k: fn(*a, **k)
A.send_reminder_email = lambda *a, **k: True


def who(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c


a, o, l, h = who(agent, "agent"), who(other, "agent"), who(lender, "lender"), who(home, "homeowner")
dest = lambda r: r.headers.get("Location", "")

# one client list for agents
r = a.get("/agent/clients")
ok(r.status_code == 302 and dest(r).endswith("/agent/my-clients"), "the old /agent/clients list now opens My Clients")
t = a.get("/agent/my-clients").get_data(as_text=True)
ok(f"/agent/clients/{home}" in t and "Hal Homeowner" in t, "My Clients lists the client and opens their page")

# agent opens a client
t = a.get(f"/agent/clients/{home}").get_data(as_text=True)
ok("Hal Homeowner" in t and "Property &amp; Equity" in t or "Property & Equity" in t, "the client page shows the home and value")
ok(f"/messages/{home}" in t and "Message Hal" in t, "the client page has a Message button")
ok("homeowner_overview" not in t and f'href="/homeowner/{home}"' not in t and "View Full Portal" not in t and "View all in portal" not in t, "no link on the client page bounces")
ok("My Clients" in t and 'href="/agent/my-clients"' in t, "its back link goes to My Clients")
ok("No messages yet" in t, "with no messages it says so")
a.post(f"/messages/{home}", data={"body": "Welcome to your new home!"})
h.post(f"/homeowner/team/{agent}", data={"body": "Thank you so much"})
t = a.get(f"/agent/clients/{home}").get_data(as_text=True)
ok("Welcome to your new home!" in t and "Thank you so much" in t, "the client page shows recent messages")
ok(o.get(f"/agent/clients/{home}").status_code == 302, "another agent cannot open this client")
ok("Hal Homeowner" not in o.get(f"/agent/clients/{home}", follow_redirects=True).get_data(as_text=True), "another agent sees nothing of this client")

# old /homeowner/<id> links
r = a.get(f"/homeowner/{home}")
ok(r.status_code == 302 and dest(r).endswith(f"/agent/clients/{home}"), "an old /homeowner/<id> link takes an agent to that client's page")
r = l.get(f"/homeowner/{home}")
ok(r.status_code == 302 and dest(r).endswith(f"/lender/clients/{home}"), "and takes a lender to theirs")
ok(a.get("/homeowner/abc").status_code in (302, 404), "a junk link does not crash")

# lender
t = l.get(f"/lender/clients/{home}").get_data(as_text=True)
ok("Hal Homeowner" in t and "Message Hal" in t and f"/messages/{home}" in t, "the lender's client page has the home, value and a Message button")
ok("View Full Portal" not in t and "View all in portal" not in t and f'href="/homeowner/{home}"' not in t, "no lender link bounces")
ok('href="/lender/clients"' in t and "My Clients" in t, "its back link goes to My Clients")
l.post(f"/messages/{home}", data={"body": "Rates look good for you"})
ok("Rates look good for you" in l.get(f"/lender/clients/{home}").get_data(as_text=True), "the lender sees recent messages")
ok("Welcome to your new home!" not in l.get(f"/lender/clients/{home}").get_data(as_text=True), "a lender never sees the agent's messages")

# every link on My Clients and the client pages works
for c, page in ((a, "/agent/my-clients"), (l, "/lender/clients"), (a, f"/agent/clients/{home}"), (l, f"/lender/clients/{home}")):
    t = c.get(page).get_data(as_text=True)
    links = sorted(set(re.findall(r'href="(/[^"#]*)"', t)))
    bad = []
    for u in links:
        if u.startswith(("/static", "/logout")):
            continue
        r = c.get(u)
        if r.status_code >= 400:
            bad.append((u, r.status_code))
    ok(not bad, f"every link on {page} opens" + (f": {bad[:4]}" if bad else ""))
