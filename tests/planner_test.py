import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from datetime import date, timedelta
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
other = D.create_user("Bob", "bob@x.com", gp("password123"), "agent")
ln = D.create_user("Lou", "lou@x.com", gp("password123"), "lender")
a1 = D.add_agent_contact(ag, "Jane Seller", last_touch=(date.today() - timedelta(days=40)).isoformat())
a2 = D.add_agent_contact(ag, "Mark Buyer")
a3 = D.add_agent_contact(ag, "Recent Rita", last_touch=date.today().isoformat())
bo = D.add_agent_contact(other, "Bobs Client")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ag; s["role"] = "agent"
mon = (date.today() - timedelta(days=date.today().weekday())).isoformat()
day = min(date.today().weekday(), 5)
conn = D.get_connection()
def last(i): return conn.execute("select last_touch from agent_contacts where id=?", (i,)).fetchone()[0]

r = c.get("/planner/people").get_json()
names = [p["name"] for p in r["people"]]
ok(names[0] == "Mark Buyer" and names[1] == "Jane Seller" and names[-1] == "Recent Rita", "reach-out list: never-spoken first, then oldest, newest last: %s" % names)
ok(c.get("/planner/people?q=jan").get_json()["people"][0]["name"] == "Jane Seller", "name search finds Jane")
ok(all(p["name"] != "Bobs Client" for p in c.get("/planner/people?q=bob").get_json()["people"]), "other agent's contacts never show")

r = c.post("/planner/touch", json={"activity": "calls", "day": day, "week": mon, "name": "Jane Seller", "contact_id": a1, "note": "Wants to list in spring"}).get_json()
ok(r["ok"] and r["value"] == 1 and r["total"] == 1 and r["linked"], "logging a call counts it and links the contact")
ok(last(a1) == date.today().isoformat(), "contact's last_touch is now today")
n = conn.execute("select count(*) from crm_interactions where contact_id=? and notes like '%spring%'", (a1,)).fetchone()[0]
ok(n == 1, "call is also in the CRM history with the note")
r = c.post("/planner/touch", json={"activity": "calls", "day": day, "week": mon, "name": "jane seller"}).get_json()
ok(r["ok"] and r["value"] == 2 and r["name"] == "Jane Seller", "typed name matches existing contact (case-insensitive) and counts again")
r = c.post("/planner/touch", json={"activity": "calls", "day": day, "week": mon, "name": "Brand New Person", "add_to_crm": True}).get_json()
ok(r["ok"] and r["added"] and conn.execute("select count(*) from agent_contacts where agent_user_id=? and name='Brand New Person'", (ag,)).fetchone()[0] == 1, "new name can be added to the CRM")
r = c.post("/planner/touch", json={"activity": "face", "day": day, "week": mon, "name": "Walk In Wendy"}).get_json()
ok(r["ok"] and not r["linked"] and conn.execute("select count(*) from agent_contacts where name='Walk In Wendy'").fetchone()[0] == 0, "unlinked name is saved only to the log when not added to CRM")
r = c.post("/planner/touch", json={"activity": "calls", "day": day, "week": mon, "name": "Hacker", "contact_id": bo}).get_json()
ok(r["ok"] and conn.execute("select count(*) from crm_interactions where contact_id=?", (bo,)).fetchone()[0] == 0 and last(bo) in (None, ""), "another agent's contact id is ignored")
ok(c.post("/planner/touch", json={"activity": "calls", "day": day, "week": mon, "name": ""}).status_code == 400, "name is required")
ok(c.post("/planner/touch", json={"activity": "leads", "day": day, "week": mon, "name": "X"}).status_code == 400, "only people counters take names")

before = conn.execute("select count(*) from planner_touches where user_id=?", (ag,)).fetchone()[0]
r = c.post("/planner/save", json={"week": mon, "activity": "calls", "day": day, "value": 2, "undo_touch": True}).get_json()
after = conn.execute("select count(*) from planner_touches where user_id=?", (ag,)).fetchone()[0]
ok(r["ok"] and after == before - 1, "minus removes the latest name too")

t = c.get("/agent").get_data(as_text=True)
ok("Today&#39;s Plan" in t or "Today's Plan" in t, "dashboard shows Today's Plan")
ok("Reach out next" in t and "Mark Buyer" in t and "Never spoken to" in t, "dashboard lists who to reach out to next")
ok('data-who="calls"' in t and ">Jane Seller<" in t, "today's names show under Great phone calls")
t = c.get("/planner").get_data(as_text=True)
ok("Who you talked to this week" in t and "Jane Seller" in t and "Wants to list in spring" in t, "weekly planner lists who you talked to with notes")
ok("Reach out next" in t and "Log call" in t, "weekly planner has reach-out list")

lc = A.app.test_client()
with lc.session_transaction() as s: s["user_id"] = ln; s["role"] = "lender"
b1 = D.add_lender_borrower(ln, "Barb Borrower")
r = lc.post("/planner/touch", json={"activity": "calls", "day": day, "week": mon, "name": "Barb Borrower"}).get_json()
ok(r["ok"] and r["linked"] and conn.execute("select last_touch from lender_borrowers where id=?", (b1,)).fetchone()[0] == date.today().isoformat(), "lender side works too")
ok("Reach out next" in lc.get("/lender").get_data(as_text=True), "lender dashboard shows the list")
ok(A.app.test_client().post("/planner/touch", json={"activity": "calls", "day": 0, "name": "X"}).status_code == 401, "must be signed in")

# ---- edge cases ----
import planner as P
ok(P.ago("11/02/2026")[1] is not None and P.ago("2026-11-02T10:00:00")[1] is not None and P.ago("")[1] is None and P.ago("junk")[1] is None, "last-spoken dates in common formats are understood, junk reads as never")
r = c.post("/planner/touch", json={"activity": "notes", "day": 0, "week": (date.today() - timedelta(days=14)).isoformat(), "name": "<script>alert(1)</script> " + "x" * 200}).get_json()
ok(r["ok"] and len(r["name"]) <= 120, "very long name is trimmed")
conn2 = D.get_connection()
row = conn2.execute("select touched_on from planner_touches where name like '<script>%'").fetchone()
mon_prev = (date.today() - timedelta(days=14)); mon_prev = mon_prev - timedelta(days=mon_prev.weekday())
ok(row and row[0] == mon_prev.isoformat(), "touch on a past week lands on that week's Monday")
t = c.get("/planner?week=" + mon_prev.isoformat()).get_data(as_text=True)
ok("<script>alert(1)" not in t and "&lt;script&gt;alert(1)" in t, "names are escaped on the weekly page")
t = c.get("/agent").get_data(as_text=True)
ok("<script>alert(1)" not in t, "names are escaped on the dashboard")
ok(c.post("/planner/touch", data="notjson").status_code in (400, 401), "bad body is refused cleanly")
ok(c.get("/planner/people?q=%25%25").status_code == 200, "wildcard characters in search are harmless")
