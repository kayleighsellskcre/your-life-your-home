import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
ot = D.create_user("Bob", "bob@x.com", gp("password123"), "agent")
conn = D.get_connection()
conn.executemany("INSERT INTO agent_contacts (agent_user_id,name,email,address) VALUES (?,?,?,?)", [(ag, f"Person {i:04d}", f"p{i}@x.com", f"{i} Main St") for i in range(3000)])
conn.execute("INSERT INTO agent_contacts (agent_user_id,name,email) VALUES (?,?,?)", (ot, "Secret Sam", "sam@x.com")); conn.commit()
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ag; s["role"] = "agent"
t = c.get("/agent/invoices/new").get_data(as_text=True)
ok(len(t) < 150000, "new invoice page is small with 3000 contacts (%d KB)" % (len(t) // 1024))
r = c.get("/agent/crm/lookup?q=Person 0042").get_json(); ok(r["ok"] and r["contacts"][0]["name"] == "Person 0042" and r["contacts"][0]["address"] == "42 Main St", "lookup finds a contact with address")
ok(c.get("/agent/crm/lookup?q=Secret").get_json()["contacts"] == [], "other agent's contacts never show")
ok(c.get("/agent/crm/lookup?q=P").get_json()["contacts"] == [], "one letter returns nothing")
ok(len(c.get("/agent/crm/lookup?q=Person").get_json()["contacts"]) == 8, "at most eight results")
cid = conn.execute("select id from agent_contacts where name='Person 0007'").fetchone()[0]
t = c.get(f"/agent/invoices/new?contact_id={cid}").get_data(as_text=True); ok('value="Person 0007"' in t and "7 Main St" in t, "pre-filled from a CRM contact")
bo = conn.execute("select id from agent_contacts where name='Secret Sam'").fetchone()[0]
t = c.get(f"/agent/invoices/new?contact_id={bo}").get_data(as_text=True); ok("Secret Sam" not in t, "cannot pre-fill another agent's contact")
ok(c.get("/agent/invoices").status_code == 200, "invoice list works")
ok(A.app.test_client().get("/agent/crm/lookup?q=Person").status_code in (302, 401), "lookup needs sign-in")
