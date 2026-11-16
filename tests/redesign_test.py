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
ok("<select" not in page and 'name="role"' not in page and 'id="role"' not in page, "the Sign In page no longer has a role dropdown")
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

# ---- 3. public pages ----
EM = "—"
anon = A.app.test_client()
for path, role, label in (("/homeowners", "homeowner", "Create my free account"), ("/agents", "agent", "Start my account"), ("/lenders", "lender", "Start my account")):
    r = anon.get(path)
    t = r.get_data(as_text=True)
    ok(r.status_code == 200, f"{path} opens (it used to say Page not found)")
    main = t[t.index('class="fg-w"'):t.index("</main>")]
    ok(main.count('class="fg-btn"') == 1 and f"/signup?role={role}" in main and label in main, f"{path} has exactly one button, '{label}', that goes to the {role} sign-up")
    ok(EM not in main and "–" not in main, f"{path} has no dashes used as punctuation")
ok(anon.get("/for-agents").status_code == 200 and anon.get("/for-lenders").status_code == 200, "the longer addresses work too")
home_t = anon.get("/").get_data(as_text=True)
for label in ("For Homeowners", "For Agents", "For Lenders"):
    ok(home_t.count(label) >= 2, f"'{label}' is in the menu and in the footer")
ok(home_t.count('>Sign In</a>') >= 1 and home_t.count('class="main-nav"') == 1, "the header keeps its Sign In button")
for role, word in (("agent", "Start Your Agent Account"), ("lender", "Start Your Lender Account"), ("homeowner", "Create Your Free Account")):
    t = anon.get(f"/signup?role={role}").get_data(as_text=True)
    ok(word in t and "I am signing up as" not in t and f'name="role" value="{role}"' in t, f"the {role} sign-up page says what it is, with no role dropdown")
# a real agent and lender can sign up from those pages
for role, email in (("agent", "newagent@x.com"), ("lender", "newlender@x.com")):
    c = A.app.test_client()
    with contextlib.redirect_stdout(io.StringIO()):
        c.post(f"/signup?role={role}", data={"name": "New Person", "email": email, "password": "password123", "role": role})
    u = D.get_user_by_email(email)
    ok(u and dict(u)["role"] == role, f"signing up from the {role} page creates a {role} account")
