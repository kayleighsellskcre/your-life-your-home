import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)


def client(uid, role):
    cl = A.app.test_client()
    with cl.session_transaction() as s: s["user_id"] = uid; s["role"] = role
    return cl


amy = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
lou = D.create_user("Lou Lender", "lou@x.com", gp("password123"), "lender")
hom = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=amy)
other = D.create_user("Other Agent", "oa@x.com", gp("password123"), "agent")
ca, cl, ch, co = client(amy, "agent"), client(lou, "lender"), client(hom, "homeowner"), client(other, "agent")


def one(sql, *a):
    c = D.get_connection()
    try:
        return c.execute(sql, a).fetchone()
    finally:
        c.close()


ok(A.app.test_client().get("/events").status_code == 302, "signed-out visitors are sent to login")
ok(ch.get("/events").status_code == 302, "homeowners do not get the events area")
r = ca.get("/events")
ok(r.status_code == 200 and "No events yet" in r.get_data(as_text=True), "an agent sees an empty events page at first")
ok(cl.get("/events").status_code == 200, "a lender can open events too")

# the Veterans Day example
r = ca.post("/events/new", data={"name": "Veterans Day assembly", "kind": "yearly", "event_date": "2026-11-11", "place": "Lincoln Elementary", "who": "Students and veterans"}, follow_redirects=True)
t = r.get_data(as_text=True)
ok("Veterans Day assembly" in t and "Lincoln Elementary" in t and "November 11, 2026" in t and "Yearly" in t, "a yearly event is created and shows its date and place")
eid = one("SELECT id FROM events WHERE user_id = ?", amy)["id"]
run1 = one("SELECT id FROM event_runs WHERE event_id = ?", eid)["id"]
ca.post(f"/events/{eid}/items/add", data={"run_id": run1, "text": "Donuts, 4 dozen\nCoffee, regular\nCoffee, decaf\nHot tea and cups\nChiefs jersey for the giveaway"})
t = ca.get(f"/events/{eid}").get_data(as_text=True)
ok(all(x in t for x in ("Donuts, 4 dozen", "Coffee, decaf", "Chiefs jersey for the giveaway")) and "0 of 5 packed" in t, "pasting a list adds one checklist item per line")
iid = one("SELECT id FROM event_items WHERE text LIKE 'Donuts%'")["id"]
r = ca.post(f"/events/{eid}/items/{iid}/tick", data={"run_id": run1}, headers={"X-Requested-With": "fetch"})
ok(r.get_json() == {"done": True, "packed": 1, "total": 5}, "ticking an item packs it and reports progress")
ok("1 of 5 packed" in ca.get(f"/events/{eid}").get_data(as_text=True), "the tick is remembered")
r = ca.post(f"/events/{eid}/items/{iid}/tick", data={"run_id": run1}, headers={"X-Requested-With": "fetch"})
ok(r.get_json()["done"] is False, "ticking again unpacks it")
ca.post(f"/events/{eid}/items/{iid}/tick", data={"run_id": run1})

# notes
ca.post(f"/events/{eid}/run", data={"run_id": run1, "run_date": "2026-11-11", "attendance": "200 students", "went_well": "Kids loved the jersey drawing",
                                    "improve": "Bring a second coffee carafe. Ask the school for a table by the door.", "notes": "Ask for Ms. Rivera at the front office"})
t = ca.get(f"/events/{eid}").get_data(as_text=True)
ok("Bring a second coffee carafe" in t and "200 students" in t and "Ms. Rivera" in t, "how it went is saved")

# costs flow into Financials
ca.post(f"/events/{eid}/costs/add", data={"run_id": run1, "what": "Donuts and coffee", "amount": "$86.40", "kind": "food"})
ca.post(f"/events/{eid}/costs/add", data={"run_id": run1, "what": "Chiefs jersey", "amount": "120", "kind": "gifts"})
rows = [dict(r) for r in D.get_connection().execute("SELECT * FROM agent_expenses WHERE agent_user_id = ? ORDER BY id", (amy,)).fetchall()]
ok(len(rows) == 2 and rows[0]["amount"] == 86.4 and rows[0]["category"] == "Marketing" and rows[1]["category"] == "Gifts"
   and rows[0]["expense_date"] == "2026-11-11" and rows[0]["description"] == "Veterans Day assembly: Donuts and coffee", "agent costs become Financials expenses in a sensible category on the event date")
ok("Total" in ca.get(f"/events/{eid}").get_data(as_text=True) and "$206.40" in ca.get(f"/events/{eid}").get_data(as_text=True), "the event page totals what it cost")
ok("Veterans Day assembly: Chiefs jersey" in ca.get("/agent/financials?year=2026").get_data(as_text=True) or "Chiefs jersey" in ca.get("/agent/financials").get_data(as_text=True), "the cost shows on the Financials page")
ca.post(f"/events/{eid}/costs/add", data={"run_id": run1, "what": "Nothing", "amount": "0"})
ca.post(f"/events/{eid}/costs/add", data={"run_id": run1, "what": "Bad", "amount": "abc"})
ok(D.get_connection().execute("SELECT COUNT(*) FROM agent_expenses WHERE agent_user_id = ?", (amy,)).fetchone()[0] == 2, "empty or invalid amounts are refused")
ca.post(f"/events/{eid}/run", data={"run_id": run1, "run_date": "2026-11-12"})
ok(one("SELECT expense_date FROM agent_expenses WHERE agent_user_id = ?", amy)["expense_date"] == "2026-11-12", "changing the event date moves its expenses too")
ca.post(f"/events/{eid}/run", data={"run_id": run1, "run_date": "2026-11-11", "improve": "Bring a second coffee carafe. Ask the school for a table by the door.", "went_well": "Kids loved the jersey drawing"})
cid = one("SELECT id FROM event_costs WHERE what = 'Chiefs jersey'")["id"]
ca.post(f"/events/{eid}/costs/{cid}/delete", data={"run_id": run1})
ok(D.get_connection().execute("SELECT COUNT(*) FROM agent_expenses WHERE agent_user_id = ?", (amy,)).fetchone()[0] == 1, "removing a cost removes it from Financials too")

# next year
r = ca.post(f"/events/{eid}/next", data={}, follow_redirects=True)
t = r.get_data(as_text=True)
ok("November 11, 2027" in t and "Lessons from last time" in t and "second coffee carafe" in t, "next year starts on the same date with last year's lessons at the top")
ok("0 of 5 packed" in t and "Donuts, 4 dozen" in t, "the checklist carries over with nothing ticked")
ok("November 11, 2026" in t, "last year stays available in the list of years")

# lender
ca2 = cl.post("/events/new", data={"name": "Realtor lunch", "kind": "one_time", "event_date": "2026-12-01", "copy_from": ""}, follow_redirects=True)
leid = one("SELECT id FROM events WHERE user_id = ?", lou)["id"]
lrun = one("SELECT id FROM event_runs WHERE event_id = ?", leid)["id"]
cl.post(f"/events/{leid}/costs/add", data={"run_id": lrun, "what": "Pizza", "amount": "95", "kind": "food"})
ok(one("SELECT category FROM lender_expenses WHERE lender_user_id = ?", lou)["category"] == "Meals & Entertainment", "a lender's costs go to the lender Financials with a lender category")

# copy a checklist
ca.post("/events/new", data={"name": "Veterans Day, second school", "kind": "yearly", "copy_from": str(eid)})
nid = one("SELECT id FROM events WHERE name = 'Veterans Day, second school'")["id"]
ok(one("SELECT COUNT(*) AS n FROM event_items WHERE event_id = ?", nid)["n"] == 5, "a new event can start from an earlier event's checklist")

# privacy
ok(co.get(f"/events/{eid}").status_code == 302, "another agent cannot open your event")
co.post(f"/events/{eid}/items/add", data={"run_id": run1, "text": "sneaky"})
co.post(f"/events/{eid}/costs/add", data={"run_id": run1, "what": "x", "amount": "5"})
co.post(f"/events/{eid}/delete")
ok(one("SELECT COUNT(*) AS n FROM event_items WHERE text = 'sneaky'")["n"] == 0 and one("SELECT COUNT(*) AS n FROM event_costs WHERE what = 'x'")["n"] == 0
   and one("SELECT COUNT(*) AS n FROM events WHERE id = ?", eid)["n"] == 1, "another agent cannot add to or delete your event")
cl.post(f"/events/{eid}/items/{iid}/tick", data={"run_id": run1})
ok(one("SELECT COUNT(*) AS n FROM event_checks WHERE run_id = ?", run1)["n"] == 1, "a lender cannot tick off an agent's checklist")

# delete cleans up the money
ca.post(f"/events/{eid}/delete")
ok(one("SELECT COUNT(*) AS n FROM events WHERE id = ?", eid)["n"] == 0 and one("SELECT COUNT(*) AS n FROM agent_expenses WHERE agent_user_id = ?", amy)["n"] == 0
   and one("SELECT COUNT(*) AS n FROM event_items WHERE event_id = ?", eid)["n"] == 0, "deleting an event removes its notes, list and Financials entries")
ok("Events" in ca.get("/agent/dashboard").get_data(as_text=True) and "/events" in cl.get("/lender/dashboard").get_data(as_text=True), "Events is in the menu for agents and lenders")
