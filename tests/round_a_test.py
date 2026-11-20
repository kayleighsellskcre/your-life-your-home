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


def who(uid, role):
    c = A.app.test_client()
    if uid:
        with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c


D.add_property(home, "10 First St, Shawnee, KS 66226", 250000.0, "primary")
a, l, h, v = who(agent, "agent"), who(lender, "lender"), who(home, "homeowner"), who(None, None)
fresh = lambda: A.app.test_client()
dest = lambda r: r.headers.get("Location", "")

# 2. signed-in people skip login and sign-up
for name, c, where in (("agent", a, "/agent"), ("lender", l, "/lender"), ("homeowner", h, "/homeowner/my-home")):
    for p in ("/login", "/signup", "/signup?role=agent"):
        r = c.get(p)
        ok(r.status_code == 302 and dest(r).endswith(where), f"a signed-in {name} opening {p} goes to {where}")
ok(v.get("/login").status_code == 200 and v.get("/signup").status_code == 200, "visitors still see login and sign-up")
r = v.post("/login", data={"email": "hal@x.com", "password": "password123"})
ok(r.status_code == 302 and dest(r).endswith("/homeowner/my-home"), "signing in still works")

# 3. pricing
t = a.get("/pricing").get_data(as_text=True)
ok("Start as an agent" not in t and ("Switch to Starter" in t or "This is your plan" in t), "a signed-in agent sees plan buttons, not sign-up buttons")
_lp = l.get("/pricing").get_data(as_text=True)
ok(("Switch to Starter" in _lp or "This is your plan" in _lp) and "Start as a lender" not in _lp.split("Are you a lender")[0], "a signed-in lender sees plan buttons")
ok("Start free" in fresh().get("/pricing").get_data(as_text=True), "visitors see a Start free button on the plan card")
t = h.get("/pricing").get_data(as_text=True)
ok("Start as an agent" not in t and "Change my plan" not in t, "a homeowner is not pushed to sign up as a pro")

# 4. account security back link
back = lambda c: re.search(r'<a class="back" href="([^"]*)"', c.get("/account/security").get_data(as_text=True))
ok(back(a) and back(a).group(1) == "/agent" and back(l).group(1) == "/lender" and back(h).group(1) == "/homeowner/my-home", "Account security Back goes to each person's own home page")

# 5. Full home overview retired
r = h.get("/homeowner")
ok(r.status_code == 302 and dest(r).endswith("/homeowner/my-home"), "/homeowner sends a homeowner to My Home")
t = h.get("/homeowner/my-home").get_data(as_text=True)
ok("Full home overview" not in t, "My Home no longer links to Full home overview")
ok("What brings you here?" in t and "Next up for your home" in t and "Saved home details" in t, "My Home keeps next up and details and now holds the focus chooser")
ok("Your home's value" in t, "My Home shows the home value card")
menu = t[t.index('id="ylhHamMenu"'):]
menu = menu[:menu.index("Sign Out")]
ok("Full home overview" not in menu, "the menu does not list it")
ok(h.post("/homeowner/goal", data={"goal": "investor"}).status_code == 302, "choosing a focus still works")
t = h.get("/homeowner/my-home").get_data(as_text=True)
ok("Your properties" in t or "Your home's numbers" in t, "an investor sees properties on My Home")
