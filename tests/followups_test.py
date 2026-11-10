import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from datetime import date, timedelta
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
other = D.create_user("Other Agent", "oa@x.com", gp("password123"), "agent")
conn = D.get_connection()
today = date.today()
iso = lambda n: (today + timedelta(days=n)).isoformat()


def mk(owner, name, due="", note="", touch="", phone="", stage="lead"):
    cid = D.add_agent_contact(owner, name, phone=phone, email=name.split()[0].lower() + "@x.com", stage=stage, last_touch=touch,
                              next_action_date=due, next_action_note=note)
    return cid


late = mk(ag, "Lara Late", iso(-4), "Call about listing", touch=iso(-30), phone="9135550101")
now = mk(ag, "Dora Today", iso(0), "Send comps", touch=iso(-3))
future = mk(ag, "Fern Future", iso(5), "Later", touch=iso(-3))
never = mk(ag, "Nina Never")
closed = mk(ag, "Cleo Closed", iso(-2), "x", stage="closed")
foreign = mk(other, "Fox Foreign", iso(-1), "not yours")


def client(uid, role):
    cl = A.app.test_client()
    with cl.session_transaction() as s: s["user_id"] = uid; s["role"] = role
    return cl


ca = client(ag, "agent")
r = ca.get("/agent/followups"); t = r.get_data(as_text=True)
ok(r.status_code == 200, "page loads")
ok("Lara Late" in t and "Dora Today" in t and "Nina Never" in t, "shows overdue, due-today and never-contacted people")
ok("Fern Future" not in t and "Cleo Closed" not in t and "Fox Foreign" not in t, "not future, closed or another agent's people")
ok(t.index("Lara Late") < t.index("Dora Today") < t.index("Nina Never"), "oldest overdue first, never-contacted last")
ok("4 days late" in t and "Due today" in t and "Never contacted" in t, "plain status labels")
ok("tel:9135550101" in t and "sms:9135550101" in t, "call and tap-to-text buttons")
count = A.get_agent_dashboard_metrics(ag)["followups_today"]
ok(count == 3, "the page lists exactly what the dashboard counts (%d)" % count)
ok("/agent/followups" in ca.get("/agent").get_data(as_text=True), "dashboard Follow-ups card links to the page")

# done
r = ca.post(f"/agent/followups/{late}/done"); row = conn.execute("SELECT next_action_date, next_action_note, last_touch FROM agent_contacts WHERE id=?", (late,)).fetchone()
ok(r.status_code == 302 and row["next_action_date"] == "" and row["next_action_note"] == "" and row["last_touch"] == iso(0), "Done clears the reminder and records today as the last touch")
ok("<b>Lara Late</b>" not in ca.get("/agent/followups").get_data(as_text=True), "done people leave the list")

# snooze
ca.post(f"/agent/followups/{now}/snooze", data={"days": "3"})
row = conn.execute("SELECT next_action_date, next_action_note FROM agent_contacts WHERE id=?", (now,)).fetchone()
ok(row["next_action_date"] == iso(3) and row["next_action_note"] == "Send comps", "Snooze moves the date and keeps the note")
ok("<b>Dora Today</b>" not in ca.get("/agent/followups").get_data(as_text=True), "snoozed people leave the list until their new date")
ca.post(f"/agent/followups/{never}/snooze", data={"days": "7"})
ok(conn.execute("SELECT next_action_date FROM agent_contacts WHERE id=?", (never,)).fetchone()[0] == iso(7), "a never-contacted person can be snoozed too")
ca.post(f"/agent/followups/{future}/snooze", data={"days": "999"})
ok(conn.execute("SELECT next_action_date FROM agent_contacts WHERE id=?", (future,)).fetchone()[0] == iso(1), "an odd snooze value falls back to tomorrow")
ok(A.get_agent_dashboard_metrics(ag)["followups_today"] == 0, "dashboard count drops as people are handled")

# safety
ca.post(f"/agent/followups/{foreign}/done")
ok(conn.execute("SELECT next_action_date FROM agent_contacts WHERE id=?", (foreign,)).fetchone()[0] == iso(-1), "cannot act on another agent's contact")
ok(ca.post(f"/agent/followups/{closed}/explode").status_code == 302 and conn.execute("SELECT next_action_date FROM agent_contacts WHERE id=?", (closed,)).fetchone()[0] == iso(-2), "unknown actions do nothing")
ok(client(other, "agent").get("/agent/followups").status_code == 200 and "Lara" not in client(other, "agent").get("/agent/followups").get_data(as_text=True), "another agent sees only their own")
ho = D.create_user("Hal", "hal@x.com", gp("password123"), "homeowner", agent_id=ag)
ok(client(ho, "homeowner").get("/agent/followups").status_code == 302, "homeowners cannot open it")
ok(A.app.test_client().get("/agent/followups").status_code == 302, "signed-out visitors go to login")
ok("Follow-ups" in ca.get("/agent").get_data(as_text=True), "agent menu has the link")
