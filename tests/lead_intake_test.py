import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
other = D.create_user("Other Agent", "oa@x.com", gp("password123"), "agent")
conn = D.get_connection()
conn.execute("INSERT OR REPLACE INTO user_profiles (user_id, role, webhook_token) VALUES (?, 'agent', 'tok-amy')", (ag,))
conn.execute("INSERT OR REPLACE INTO user_profiles (user_id, role, webhook_token) VALUES (?, 'agent', 'tok-other')", (other,))
conn.commit()
cl = A.app.test_client()
with contextlib.redirect_stdout(io.StringIO()):
    bad = cl.post("/api/lead-intake/not-a-token", json={"name": "X", "email": "x@x.com"})
    good = cl.post("/api/lead-intake/tok-amy", json={"name": "Lee Lead", "email": "lee@x.com", "phone": "5551230000", "source": "zapier"})
    empty = cl.post("/api/lead-intake/tok-amy", json={})
ok(bad.status_code == 401, "a wrong token is refused")
ok(good.status_code < 300, "a valid token accepts the lead (got %s)" % good.status_code)
ok(empty.status_code == 400, "a lead with no name or email is refused")
mine = [dict(c).get("email") for c in D.list_agent_contacts(ag)]
ok("lee@x.com" in mine, "the lead lands in that agent's CRM")
ok("lee@x.com" not in [dict(c).get("email") for c in D.list_agent_contacts(other)], "and not in another agent's CRM")
