import os, sys, tempfile, io, contextlib
from datetime import date, timedelta
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
import helpboard as H
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

pw = gp("password123")
amy = D.create_user("Amy One", "amy@x.com", pw, "agent")
bob = D.create_user("Bob Two", "bob@x.com", pw, "agent")
cat = D.create_user("Cat Three", "cat@x.com", pw, "agent")
dan = D.create_user("Dan Four", "dan@x.com", pw, "agent")
lou = D.create_user("Lou Lender", "lou@x.com", pw, "lender")
hal = D.create_user("Hal Home", "hal@x.com", pw, "homeowner", agent_id=amy)
conn = D.get_connection()
for uid, role, brok in ((amy, "agent", "Acme Realty"), (bob, "agent", "Acme Realty LLC"), (cat, "agent", "Other Homes"), (dan, "agent", "Other Homes"), (lou, "lender", "Acme Realty")):
    if not conn.execute("SELECT 1 FROM user_profiles WHERE user_id=?", (uid,)).fetchone():
        conn.execute("INSERT INTO user_profiles (user_id, role, brokerage_name) VALUES (?,?,?)", (uid, role, brok))
    else:
        conn.execute("UPDATE user_profiles SET brokerage_name=? WHERE user_id=?", (brok, uid))
conn.commit(); conn.close()

def who(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c
ca, cb, cc, cd, cl, ch = who(amy, "agent"), who(bob, "agent"), who(cat, "agent"), who(dan, "agent"), who(lou, "lender"), who(hal, "homeowner")
anon = A.app.test_client()
page = lambda c: c.get("/helpboard").get_data(as_text=True)
soon = (date.today() + timedelta(days=3)).isoformat()

# access
ok(anon.get("/helpboard").status_code in (301, 302, 303), "signed-out visitors are sent to sign in")
ok(ch.get("/helpboard").status_code in (301, 302, 303), "homeowners have no Help Board")
ok("Help Board" in page(ca) and "Help Board" in page(cl), "agents and lenders both open the Help Board")

# MLS
for c, name in ((ca, "Heartland MLS"), (cb, "heartland  mls"), (cc, "Canopy MLS")):
    c.post("/helpboard/mls", data={"mls_name": name})
ok(H.profile_bits(amy)["mls"] == "Heartland MLS" and H.profile_bits(bob)["mls_norm"] == "heartlandmls", "each agent can save their MLS and spelling differences still match")
ok(cl.post("/helpboard/mls", data={"mls_name": "X"}).status_code in (301, 302, 303) and H.profile_bits(lou)["mls"] == "", "lenders do not have an MLS")

# posting
r = ca.post("/helpboard/new", data={"kind": "open_house", "title": "Sunday open house", "address": "12 Oak St", "post_date": soon, "start_time": "1 PM", "end_time": "3 PM", "audience": "mls"})
ok(r.status_code in (301, 302, 303), "an agent can post an open house request for their MLS")
ok("Sunday open house" in page(cb) and "Sunday open house" not in page(cc), "same-MLS agent sees it and a different-MLS agent does not")
ok("Sunday open house" not in page(cl) and "Sunday open house" not in page(ca).split("Your requests")[0], "a lender without that MLS does not see it, and the author is not offered their own post")
r = ca.post("/helpboard/new", data={"kind": "showing", "title": "Saturday showing", "post_date": soon, "audience": "brokerage"})
ok("Saturday showing" in page(cb) and "Saturday showing" in page(cl) and "Saturday showing" not in page(cc), "brokerage audience reaches people at the same company, even across spellings, and not outsiders")
ca.post("/helpboard/new", data={"kind": "other", "title": "Invite only", "post_date": soon, "audience": "custom", "invite": "dan@x.com, nobody@nowhere.com, hal@x.com"})
ok("Invite only" in page(cd) and "Invite only" not in page(cb) and "Invite only" not in page(cc), "an invited person sees it and nobody else does")
ok("Invite only" not in page(ch), "a homeowner emailed as an invitee is ignored")

# bad input
n0 = len(H.board_for(amy)[1])
for data in ({"post_date": "2001-01-01", "audience": "mls"}, {"post_date": soon}, {"post_date": soon, "audience": "custom", "invite": ""}, {"post_date": "nope", "audience": "mls"}):
    ca.post("/helpboard/new", data=data)
ok(len(H.board_for(amy)[1]) == n0, "past dates, missing dates, no audience, or empty invites post nothing")
cc.post("/helpboard/new", data={"post_date": soon, "audience": "brokerage", "title": "T"})  # has brokerage
ok(cl.post("/helpboard/new", data={"post_date": soon, "audience": "mls", "title": "Hack"}).status_code in (200, 302, 303) and "Hack" not in page(cb), "a lender cannot post to an MLS")
cd.post("/helpboard/new", data={"post_date": soon, "audience": "mls", "title": "NoMLSset"})
ok("NoMLSset" not in page(cd) and not [p for p in H.board_for(dan)[1] if p["title"] == "NoMLSset"], "an audience that is not set up is refused")

# claiming
conn = D.get_connection()
pid = conn.execute("SELECT id FROM help_posts WHERE title='Sunday open house'").fetchone()[0]
conn.close()
ok("Sunday open house" in page(cb), "still open before claiming")
ok(cc.post(f"/helpboard/{pid}/claim").status_code in (301, 302, 303) and H.board_for(cat)[2] == [], "a person outside the audience cannot take it")
ok(ca.post(f"/helpboard/{pid}/claim").status_code in (301, 302, 303) and H.board_for(amy)[1][0]["status"] == "open", "you cannot take your own request")
cb.post(f"/helpboard/{pid}/claim")
conn = D.get_connection(); row = conn.execute("SELECT status, claimed_by FROM help_posts WHERE id=?", (pid,)).fetchone(); conn.close()
ok(row["status"] == "claimed" and row["claimed_by"] == bob, "claiming marks it taken by that person")
ok("Sunday open house" not in page(cb).split("You said yes to")[0], "once taken it leaves the open list")
ok("bob@x.com" in page(ca) and "amy@x.com" in page(cb), "after a yes, each person sees the other's contact details")
ok("amy@x.com" not in page(cc) and "bob@x.com" not in page(cc), "strangers never see contact details")
r = cd.post(f"/helpboard/{pid}/claim")
ok(H.board_for(dan)[2] == [], "a second person cannot take one that is already taken")
cb.post(f"/helpboard/{pid}/release")
conn = D.get_connection(); row = conn.execute("SELECT status, claimed_by FROM help_posts WHERE id=?", (pid,)).fetchone(); conn.close()
ok(row["status"] == "open" and row["claimed_by"] is None, "a helper can back out and it opens up again")
cc.post(f"/helpboard/{pid}/cancel"); cb.post(f"/helpboard/{pid}/cancel")
conn = D.get_connection(); row = conn.execute("SELECT status FROM help_posts WHERE id=?", (pid,)).fetchone(); conn.close()
ok(row["status"] == "open", "only the author can cancel")
ca.post(f"/helpboard/{pid}/cancel")
conn = D.get_connection(); row = conn.execute("SELECT status FROM help_posts WHERE id=?", (pid,)).fetchone(); conn.close()
ok(row["status"] == "cancelled" and "Sunday open house" not in page(cb), "the author can cancel and it disappears for others")
ok(anon.post(f"/helpboard/{pid}/claim").status_code in (301, 302, 303) and ch.post(f"/helpboard/{pid}/claim").status_code in (301, 302, 303), "visitors and homeowners cannot act on posts")
ok(ca.post("/helpboard/99999/claim").status_code in (301, 302, 303), "a missing post is handled calmly")

# script in a title is shown as text
ca.post("/helpboard/new", data={"title": "<script>alert(1)</script>", "post_date": soon, "audience": "brokerage"})
ok("<script>alert(1)</script>" not in page(cb), "titles are shown safely")

# dashboard strip
conn = D.get_connection()
conn.execute("UPDATE help_posts SET status='cancelled'")
conn.commit(); conn.close()
ca.post("/helpboard/new", data={"title": "Strip test", "post_date": soon, "audience": "mls", "address": "9 Elm"})
dash = cb.get("/agent").get_data(as_text=True)
ok("Help Board" in dash and "1 request could use you" in dash, "an agent's dashboard says how many requests could use them")
ok("could use you" not in cc.get("/agent").get_data(as_text=True), "an agent outside the audience sees no count")
ok("could use you" not in ca.get("/agent").get_data(as_text=True), "the poster is not told about their own request")
conn = D.get_connection(); pid2 = conn.execute("SELECT id FROM help_posts WHERE title='Strip test'").fetchone()[0]; conn.close()
cb.post(f"/helpboard/{pid2}/claim")
ok("You are helping: Strip test" in cb.get("/agent").get_data(as_text=True), "the helper sees what they promised on their dashboard")

# reminders
sent = []
A.send_reminder_email_orig = A.send_reminder_email
H._H["ns"] = dict(H._H["ns"], send_reminder_email=lambda to, sub, body, **k: sent.append((to, sub, body)) or True)
ok(H.send_reminders(date.today()) == 0, "nothing is sent when nothing is the next day")
n = H.send_reminders(date.today() + timedelta(days=2))
ok(n == 2 and {s[0] for s in sent} == {"amy@x.com", "bob@x.com"} and "Strip test" in sent[0][2], "the day before, the helper and the poster each get one note")
ok(H.send_reminders(date.today() + timedelta(days=2)) == 0, "a reminder is never sent twice")

# thank-you notes
sent.clear()
conn = D.get_connection()
conn.execute("UPDATE help_posts SET post_date = ? WHERE id = ?", (date.today().isoformat(), pid2))
conn.commit(); conn.close()
ok("Say thank you" in page(ca), "on the day, the poster is offered a way to say thank you")
cb.post(f"/helpboard/{pid2}/thank", data={"note": "x"})
ok(not sent, "only the poster can thank")
ca.post(f"/helpboard/{pid2}/thank", data={"note": "You were wonderful"})
ok(any(s[0] == "bob@x.com" and "You were wonderful" in s[2] for s in sent), "the helper gets the thank-you email")
ok("You have helped 1 colleague" in page(cb) and "You were wonderful" in page(cb), "the helper sees how many they have helped and the kind words")
n = len(sent); ca.post(f"/helpboard/{pid2}/thank", data={"note": "again"})
ok(len(sent) == n, "a thank-you is only sent once")

# lender thank-you after a loan closes
bor = D.add_lender_borrower(lou, "Pat Borrower", email="pat" + "@x.com")
cl.post("/lender/crm", data={"action": "update", "borrower_id": bor, "name": "Pat Borrower", "status": "closed"})
conn = D.get_connection(); rr = conn.execute("SELECT agent_user_id, client_name FROM review_requests").fetchall(); conn.close()
ok(len(rr) == 1 and rr[0][0] == lou, "closing a loan schedules one thank-you for that borrower")
cl.post("/lender/crm", data={"action": "update", "borrower_id": bor, "name": "Pat Borrower", "status": "closed"})
conn = D.get_connection(); n2 = conn.execute("SELECT COUNT(*) FROM review_requests").fetchone()[0]; conn.close()
ok(n2 == 1, "saving again does not schedule a second one")
sent.clear(); H._H["ns"]["send_reminder_email"]  # keep helper
conn = D.get_connection(); conn.execute("UPDATE review_requests SET scheduled_date='2000-01-01'"); conn.commit(); conn.close()
A.send_reminder_email = lambda to, sub, body, **k: sent.append((to, sub, body)) or True
A.send_review_requests()
ok(sent and "closing your loan" in sent[0][2] and "(your review link)" not in sent[0][2], "the loan thank-you goes out with lender wording and no leftover placeholder")

# the MLS suggestions are broad, and an MLS an agent typed in joins the list for everyone
ok(len(H.MLS_SUGGESTIONS) >= 60 and "ACTRIS (Austin)" in H._mls_options(), "the MLS list covers many regions")
H.save_mls(amy, "agent", "Prairie Test MLS")
ok("Prairie Test MLS" in H._mls_options() and H._mls_options().count("Heartland MLS") == 1, "an MLS typed by one agent shows up in the list, without duplicates")
