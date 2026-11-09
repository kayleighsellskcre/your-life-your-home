import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
other = D.create_user("Bob", "bob@x.com", gp("password123"), "agent")
ho = D.create_user("Portal Pat", "pat@x.com", gp("password123"), "homeowner", agent_id=ag)
conn = D.get_connection()
conn.executemany("INSERT INTO agent_contacts (agent_user_id,name,email,phone,stage,tags,birthday) VALUES (?,?,?,?,?,?,?)",
    [(ag, f"Person {i:03d}", f"p{i}@x.com", f"555000{i:04d}", "active" if i % 2 else "new", "sphere" if i % 3 == 0 else "", "03/15" if i == 7 else None) for i in range(130)])
conn.execute("INSERT INTO agent_contacts (agent_user_id,name,email,stage) VALUES (?,?,?,?)", (ag, "Portal Pat", "pat@x.com", "active"))
conn.execute("INSERT INTO agent_contacts (agent_user_id,name,email,stage) VALUES (?,?,?,?)", (other, "Secret Sam", "sam@x.com", "active"))
conn.commit()
cid = conn.execute("SELECT id FROM agent_contacts WHERE name='Person 001'").fetchone()[0]
D.add_crm_task(cid, "agent_contact", ag, "Call about listing")
D.add_crm_interaction(cid, "agent_contact", ag, "call", "Talked about spring", "") if hasattr(D, "add_crm_interaction") else None
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ag; s["role"] = "agent"
t = c.get("/agent/crm").get_data(as_text=True)
ok(t.count('class="c-row') <= 60 and "Page 1 of 3" in t, "first page shows 50 of 131 with page controls")
ok("Secret Sam" not in t, "another agent's contacts never show")
t2 = c.get("/agent/crm?page=3").get_data(as_text=True)
ok("Page 3 of 3" in t2 and "Previous" in t2, "last page works")
t9 = c.get("/agent/crm?page=999").get_data(as_text=True); ok("Page 3 of 3" in t9, "page past the end is clamped")
ok(c.get("/agent/crm?page=abc").status_code == 200, "bad page number is safe")
ts = c.get("/agent/crm?search=Person 120").get_data(as_text=True)
ok("Person 120" in ts and "Person 005" not in ts, "search finds a contact that is not on page one")
ok("Call about listing" in t, "open task shows for the contact")
ok("Portal Pat" in t2 or "Portal Pat" in t, "contact with a portal account is listed")
r = c.get("/agent/crm/export.csv"); body = r.get_data(as_text=True)
ok(r.status_code == 200 and body.count("\n") >= 132 and "Secret Sam" not in body and "Person 129" in body, "CSV export has everyone, only mine")
ok("03/15" in c.get("/agent/crm").get_data(as_text=True), "birthday list data is included")
r = c.post("/agent/crm", data={"action": "add", "name": "Brand New", "email": "p5@x.com"}); n = D.get_connection().execute("select count(*) from agent_contacts where agent_user_id=?", (ag,)).fetchone()[0]
ok(n == 131, "duplicate email is refused")
r = c.post("/agent/crm", data={"action": "add", "name": "Brand New", "phone": "(555) 000-0042"}); n = D.get_connection().execute("select count(*) from agent_contacts where agent_user_id=?", (ag,)).fetchone()[0]
ok(n == 131, "duplicate phone (different format) is refused")
r = c.post("/agent/crm", data={"action": "add", "name": "Person 003"}); n = D.get_connection().execute("select count(*) from agent_contacts where agent_user_id=?", (ag,)).fetchone()[0]
ok(n == 131, "duplicate name is refused")
r = c.post("/agent/crm", data={"action": "add", "name": "Fresh Face", "email": "fresh@x.com", "phone": "5559990000"}); n = D.get_connection().execute("select count(*) from agent_contacts where agent_user_id=?", (ag,)).fetchone()[0]
ok(n == 132, "a genuinely new contact is added")
