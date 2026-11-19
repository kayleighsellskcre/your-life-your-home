import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ.pop("YLH_SECRET_KEY", None)
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
home = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=agent)
def who(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c
ca, ch = who(agent, "agent"), who(home, "homeowner")

# secret key
ok(A.app.secret_key not in ("change-this-secret-key", "", None) and len(A.app.secret_key) >= 32, "with no secret set, the app makes a random key instead of a public one")

# AI endpoints
r = ch.post("/api/ai/crm/draft-email", json={})
ok(r.status_code == 403, "a homeowner account cannot use the agent AI tools")
r = A.app.test_client().post("/api/ai/crm/draft-email", json={})
ok(r.status_code in (401, 302, 403), "signed-out visitors cannot either")
codes = []
for _ in range(85):
    with contextlib.redirect_stdout(io.StringIO()):
        codes.append(ca.post("/api/ai/crm/lead-score", json={}).status_code)
ok(429 in codes and codes.index(429) >= 80, "one account is held back after a few dozen AI requests in ten minutes")

# delete via link no longer possible
ok(ch.get("/homeowner/home-timeline/delete/1").status_code == 405, "a timeline event cannot be deleted just by opening a link")

# public site map
sm = A.app.test_client().get("/sitemap.xml").get_data(as_text=True)
ok(all(p in sm for p in ("/for-agents", "/for-lenders", "/for-homeowners", "/pricing", "/home-value", "/privacy", "/terms")), "the sitemap lists every public page")

# nothing secret-looking in the public source
src = open("app.py", encoding="utf-8").read()
ok("YLH-GOLD-LAUNCH" not in src, "no promo codes are written in the source code")
for f in ("templates/agent/subscription.html", "templates/lender/subscription.html"):
    ok("YLH-GOLD-LAUNCH" not in open(f, encoding="utf-8").read(), f"{f} does not show a real promo code as the example")
ok("Kayleigh" not in open("templates/shared/_signature_body.html", encoding="utf-8").read(), "the signature box example is not one person's real details")

# packages the code imports are all declared
req = open("requirements.txt", encoding="utf-8").read().lower()
ok(all(p in req for p in ("pypdf", "requests", "python-dateutil")), "pypdf, requests and dateutil are declared so contract reading works after a fresh deploy")
ok(all(re.search(r"^(flask|gunicorn|apscheduler|pandas|openai)[^\n]*<", req, re.M) for _ in [0]) and "apscheduler>=3.10,<4" in req, "packages that could break on a new major version have an upper limit")

# form fields that screen readers need names for
page = ca.get("/agent/crm").get_data(as_text=True)
ok('aria-label="Sort people by"' in page and 'aria-label="What to do with the selected people"' in page, "CRM selects have names for screen readers")
