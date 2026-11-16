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


def signed_in(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c


# ---- 1. sign in has no role picker and sends people to their own dashboard ----
page = A.app.test_client().get("/login").get_data(as_text=True)
ok("I am a" not in page and 'name="role"' not in page and 'id="role"' not in page, "the Sign In page no longer asks 'I am a'")
for email, where in (("hal@x.com", "/homeowner"), ("amy@x.com", "/agent"), ("lou@x.com", "/lender")):
    r = A.app.test_client().post("/login", data={"email": email, "password": "password123"})
    ok(r.status_code == 302 and where in r.headers["Location"], f"{email} signs in with just email and password and lands on their own dashboard")
r = A.app.test_client().post("/login", data={"email": "amy@x.com", "password": "wrong"}, follow_redirects=True)
ok("could not find a match" in r.get_data(as_text=True), "a wrong password is refused kindly")
r = A.app.test_client().post("/login", data={"email": "", "password": ""}, follow_redirects=True)
ok("enter your email and password" in r.get_data(as_text=True), "empty fields are refused kindly")
r = A.app.test_client().post("/login", data={"email": "amy@x.com", "password": "password123", "role": "homeowner"})
ok("/agent" in r.headers["Location"], "an old form that still sends a role does not send anyone to the wrong place")

# ---- 2. header title under the logo ----
a = signed_in(agent, "agent")
ok("<span class=\"ylh-hdr-title\"" not in A.app.test_client().get("/").get_data(as_text=True), "signed-out visitors see nothing under the logo")
for path in ("/", "/login", "/signup"):
    ok("<span class=\"ylh-hdr-title\"" not in a.get(path).get_data(as_text=True), f"a signed-in agent sees nothing under the logo on public page {path}")
ok("Agent Dashboard" in a.get("/agent/dashboard").get_data(as_text=True), "a signed-in agent sees 'Agent Dashboard' on their dashboard")
