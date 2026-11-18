import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from datetime import date
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
lender = D.create_user("Lou Lender", "lou@x.com", gp("password123"), "lender")
home = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=agent)
def who(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c
ca, cl = who(agent, "agent"), who(lender, "lender")

t = ca.get("/agent/automatic-emails").get_data(as_text=True)
ok("Automatic Emails" in t and "Birthday email" in t and "Home anniversary email" in t and "Thank-you and review request" in t, "agent page lists all three emails")
ok("Happy birthday, Sam!" in t and "With warmth,\nAmy Agent" in t, "it shows the exact words with the agent's own name")
ok("Thank-you and review request" not in cl.get("/lender/automatic-emails").get_data(as_text=True) and "Birthday email" in cl.get("/lender/automatic-emails").get_data(as_text=True), "lenders see birthday and anniversary only")
ok(ca.get("/lender/automatic-emails").status_code == 302 and who(home, "homeowner").get("/agent/automatic-emails").status_code == 302, "only the right person can open each page")
ok(">Automatic Emails<" in ca.get("/agent").get_data(as_text=True) and ">Automatic Emails<" in cl.get("/lender").get_data(as_text=True), "both menus link to it")

ok(A.auto_email_enabled(agent, "birthday") is True, "everything is on until someone switches it off")
ca.post("/agent/automatic-emails", data={"on_anniversary": "1"})
ok(A.auto_email_enabled(agent, "birthday") is False and A.auto_email_enabled(agent, "anniversary") is True and A.auto_email_enabled(agent, "review") is False, "saving applies exactly the boxes ticked")
ok(A.auto_email_enabled(lender, "birthday") is True, "one person's choice never changes another's")

# the senders respect the switch
td = date.today()
c = D.get_connection()
c.execute("INSERT INTO agent_contacts (agent_user_id, name, email, birthday, home_anniversary, auto_birthday, auto_anniversary) VALUES (?,?,?,?,?,1,1)",
          (agent, "Bea Bday", "bea@x.com", td.strftime("1985-%m-%d"), td.strftime("2020-%m-%d")))
c.execute("INSERT INTO lender_borrowers (lender_user_id, name, email, birthday, auto_birthday) VALUES (?,?,?,?,1)", (lender, "Bo Bday", "bo@x.com", td.strftime("1980-%m-%d")))
c.commit()
names = [x["name"] for x in A.get_birthday_contacts()]
ok("Bea Bday" not in names and "Bo Bday" in names, "birthday emails skip an agent who turned them off and still go for others")
ok("Bea Bday" in [x["name"] for x in A.get_anniversary_contacts()], "anniversary emails still go when that one is on")
ca.post("/agent/automatic-emails", data={})
ok("Bea Bday" not in [x["name"] for x in A.get_anniversary_contacts()], "turning anniversary off stops them too")

# review request skipped when off
ok(A.schedule_review_request(agent, 1, "Cora Client", "cora@x.com") is True, "a thank-you is scheduled")
c = D.get_connection(); c.execute("UPDATE review_requests SET scheduled_date = '2000-01-01'"); c.commit()
sent = []
A.send_reminder_email = lambda *a, **k: sent.append(a) or True
A.send_review_requests()
st = D.get_connection().execute("SELECT status FROM review_requests").fetchone()[0]
ok(not sent and st == "skipped", "with the thank-you switched off nothing is sent and it is marked skipped")
ca.post("/agent/automatic-emails", data={"on_review": "1"})
ok(A.schedule_review_request(agent, 2, "Dan Client", "dan@x.com") is True, "switched back on, a new one is scheduled")
c = D.get_connection(); c.execute("UPDATE review_requests SET scheduled_date = '2000-01-01' WHERE status = 'pending'"); c.commit()
A.send_review_requests()
ok(len(sent) == 1 and sent[0][0] == "dan@x.com", "and it is sent")
