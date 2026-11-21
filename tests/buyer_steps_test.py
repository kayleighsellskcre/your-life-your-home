import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
H = {"Origin": "http://localhost", "Referer": "http://localhost/"}
ag = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
ho = D.create_user("Buyer Owner", "buyer@x.com", gp("password123"), "homeowner", agent_id=ag)
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ho; s["role"] = "homeowner"
r = c.get("/homeowner/next/plan-my-move")
t = r.get_data(as_text=True)
ok(r.status_code == 200 and t.count('<form method="post" style="width: 100%; max-width: 100%;">') == 1 and 'id="bp-next"' in t and 'id="bp-save"' in t, "the Buyer Profile is still one form, now with step buttons")
ok(t.count('class="questionnaire-section"') == 5, "all five sections are still there so no answer is lost")
r = c.post("/homeowner/next/plan-my-move", data={"dealbreakers": "No busy road", "feeling": "Cozy"}, headers=H, follow_redirects=True)
ok(r.status_code == 200 and "No busy road" in r.get_data(as_text=True), "saving still keeps the answers")
