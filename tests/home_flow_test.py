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
def who(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c
ca, cl = who(agent, "agent"), who(lender, "lender")

# Dashboard is the home page
brand = lambda t: re.search(r'<a id="ylhBrand" href="([^"]*)"', t).group(1)
with contextlib.redirect_stdout(io.StringIO()):
    page = ca.get("/agent/my-clients").get_data(as_text=True)
    lpage = cl.get("/lender/clients").get_data(as_text=True)
ok(brand(page) == "/agent" and brand(lpage) == "/lender", "the logo takes agents and lenders to the Dashboard")
m = re.search(r'<div class="ylh-ham-menu".*?</div>\s*</div>', page, re.S)
menu = page[page.index('id="ylhHamMenu"'):]
ok(menu.index(">Dashboard<") < menu.index(">My Clients<") < menu.index("<summary>More"), "the menu opens with Dashboard, then My Clients, before More")
ok(menu.count(">Dashboard<") == 1, "the menu names Dashboard once, not twice")
lmenu = lpage[lpage.index('id="ylhHamMenu"'):]
ok(lmenu.index(">Dashboard<") < lmenu.index(">My Clients<") and lmenu.count(">Dashboard<") == 1, "the lender menu opens with Dashboard once")
r = ca.get("/homeowner/my-home")
ok(r.headers["Location"].endswith("/agent"), "an agent in the wrong area is sent to the Dashboard")

# My Clients explains how it relates to the CRM
c = D.get_connection()
for n in ("A One", "B Two", "C Three"):
    c.execute("INSERT INTO agent_contacts (agent_user_id, name, stage) VALUES (?,?,?)", (agent, n, "new"))
c.commit()
with contextlib.redirect_stdout(io.StringIO()):
    page = ca.get("/agent/my-clients").get_data(as_text=True)
ok("<strong>0</strong> of the <strong>3</strong> people in your" in page and "everyone you know" in page, "My Clients says how many CRM people have joined, and that the CRM is everyone")

# Review request: one thank-you per deal, never twice to the same person in half a year
ok(A.schedule_review_request(agent, 11, "Cora Client", "cora@x.com") is True, "closing a deal schedules a thank-you")
ok(A.schedule_review_request(agent, 11, "Cora Client", "cora@x.com") is False, "closing the same deal again does not schedule a second one")
ok(A.schedule_review_request(agent, 12, "Cora Client", "CORA@x.com") is False, "the same person is not asked twice in six months")
ok(A.schedule_review_request(agent, 13, "Dan Client", "dan@x.com") is True, "a different client still gets one")
ok(A.schedule_review_request(agent, 14, "No Email", "") is False, "no email, nothing scheduled")
