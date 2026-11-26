import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

ag = D.create_user("Ann Agent", "agent1@example.test", gp("password123"), "agent")
conn = D.get_connection()
conn.execute("INSERT INTO agent_contacts (agent_user_id, name, email, auto_seasonal, auto_equity, property_address, property_value, equity_estimate) "
             "VALUES (?, 'Cam Client', 'cam@example.test', 1, 1, '12 Oak St', 450000, 160000)", (ag,))
conn.execute("INSERT INTO agent_contacts (agent_user_id, name, email, auto_seasonal, auto_equity) VALUES (?, 'Quiet Quinn', 'quinn@example.test', 1, 0)", (ag,))
conn.commit(); conn.close()

# the note itself
c1 = {"name": "Cam Client", "type": "agent_contact", "address": "12 Oak St", "value": 450000, "equity": 160000, "care": True, "show_equity": True}
subj, body = A.season_email_text("fall", c1, "Ann Agent", "Ann")
ok(subj == "Your home this fall" and "$450,000" in body and "$160,000" in body, "the seasonal note shows value and equity")
ok(body.count("\n  - ") == 3 and "just hit reply" in body and "—" not in body, "three things to do, a warm close, no em dashes")
subj2, body2 = A.season_email_text("fall", dict(c1, show_equity=False, value=None, equity=None), "Ann Agent", "Ann")
ok("Estimated" not in body2, "no value lines when equity updates are off")

# send sends once, and not to a household emailed in the last week
sent = []
A._email_ready = lambda: True
A.send_reminder_email = lambda to, subject, body, **kw: (sent.append(to), True)[1]
A.SEASON_MONTHS = {m: "fall" for m in range(1, 13)}
A.send_seasonal_checklists()
ok(sorted(sent) == ["cam@example.test", "quinn@example.test"], "each person gets the seasonal note")
sent.clear(); A.send_seasonal_checklists()
ok(sent == [], "a second run the same season sends nothing")

# 7-day rule: a recent birthday email holds the seasonal note back, and it goes out once the week has passed
conn = D.get_connection()
conn.execute("DELETE FROM automated_email_logs WHERE email_type='seasonal'")
conn.commit(); conn.close()
D.log_automated_email(1, "agent_contact", ag, "birthday", "cam@example.test", "Happy birthday", "sent")
sent.clear(); A.send_seasonal_checklists()
ok(sent == ["quinn@example.test"], "a household emailed this week waits (%s)" % sent)
conn = D.get_connection()
conn.execute("UPDATE automated_email_logs SET sent_at = datetime('now', '-8 days') WHERE email_type='birthday'")
conn.commit(); conn.close()
sent.clear(); A.send_seasonal_checklists()
ok(sent == ["cam@example.test"], "and it goes out after the week is up")

# equity has no separate email any more
sent.clear(); A.send_equity_updates()
ok(sent == [], "no separate equity email")

# the Automatic emails page lists it with a sample
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ag; s["role"] = "agent"
t = c.get("/agent/automatic-emails").get_data(as_text=True)
ok("Your home this season" in t, "the Automatic emails page lists the seasonal note")

# review thank-yous respect the week, and are logged so later notes yield to them
conn = D.get_connection()
conn.execute("INSERT INTO review_requests (agent_user_id, transaction_id, client_email, client_name, scheduled_date, status) "
             "VALUES (?, 0, 'rev@example.test', 'Rae Review', date('now','-1 day'), 'pending')", (ag,))
conn.commit(); conn.close()
D.log_automated_email(2, "agent_contact", ag, "birthday", "rev@example.test", "Happy birthday", "sent")
sent.clear(); A.send_review_requests()
ok(sent == [], "a thank-you waits when the person was emailed this week")
conn = D.get_connection()
conn.execute("UPDATE automated_email_logs SET sent_at = datetime('now','-8 days') WHERE recipient_email='rev@example.test'")
conn.commit(); conn.close()
sent.clear(); A.send_review_requests()
ok(sent == ["rev@example.test"], "and goes out once the week has passed")
conn = D.get_connection()
n = conn.execute("SELECT COUNT(*) FROM automated_email_logs WHERE email_type='review' AND recipient_email='rev@example.test'").fetchone()[0]
conn.close()
ok(n == 1, "the thank-you is logged")

# welcome note a week after closing, with the agent's trusted vendors
conn = D.get_connection()
conn.execute("INSERT INTO trusted_vendors (agent_id, name, category, phone) VALUES (?, 'Oak Plumbing', 'Plumber', '555-0100')", (ag,))
conn.execute("INSERT INTO review_requests (agent_user_id, transaction_id, client_email, client_name, scheduled_date, status) "
             "VALUES (?, 7, 'wel@example.test', 'Wes Welcome', date('now','-4 day'), 'sent')", (ag,))
conn.commit(); conn.close()
bodies = []
A.send_reminder_email = lambda to, subject, body, **kw: (sent.append(to), bodies.append(body), True)[2]
sent.clear(); A.send_welcome_emails()
ok(sent == ["wel@example.test"] and "Oak Plumbing" in bodies[-1] and "—" not in bodies[-1], "a welcome note goes out a week after closing with the vendors")
sent.clear(); A.send_welcome_emails()
ok(sent == [], "and only once")
A.set_auto_email(ag, "welcome", False)
conn = D.get_connection()
conn.execute("INSERT INTO review_requests (agent_user_id, transaction_id, client_email, client_name, scheduled_date, status) "
             "VALUES (?, 8, 'off@example.test', 'Olive Off', date('now','-4 day'), 'sent')", (ag,))
conn.commit(); conn.close()
sent.clear(); A.send_welcome_emails()
ok(sent == [], "switched off means nothing is sent")
t = c.get("/agent/automatic-emails").get_data(as_text=True)
ok("Welcome home" in t, "the Automatic emails page lists the welcome note")

# freeze heads-up: only when a hard freeze is forecast, once, and only with the switch on
import datetime as _dt
class _D(_dt.datetime):
    @classmethod
    def now(cls, tz=None): return cls(2026, 12, 10, 8, 0)
_real_dt = _dt.datetime
conn = D.get_connection()
conn.execute("INSERT INTO agent_contacts (agent_user_id, name, email, zip_code, auto_seasonal) VALUES (?, 'Fay Frost', 'fay@example.test', '80202', 1)", (ag,))
conn.commit(); conn.close()
A.set_auto_email(ag, "freeze", True)
A.FREEZE_QUIET_MONTHS = ()
A._zip_coords = lambda z: (39.7, -104.9)
A._forecast_low = lambda la, lo: 40
sent.clear(); A.send_freeze_alerts()
ok(sent == [], "a mild forecast sends no freeze note")
A._forecast_low = lambda la, lo: 24
sent.clear(); A.send_freeze_alerts()
ok(sent == ["fay@example.test"] and "24 degrees" in bodies[-1] and "—" not in bodies[-1], "a hard freeze sends one caring heads-up")
sent.clear(); A.send_freeze_alerts()
ok(sent == [], "and only once a winter")
A.set_auto_email(ag, "freeze", False)
conn = D.get_connection()
conn.execute("DELETE FROM automated_email_logs WHERE email_type='freeze'"); conn.commit(); conn.close()
sent.clear(); A.send_freeze_alerts()
ok(sent == [], "switched off means nothing is sent")
t = c.get("/agent/automatic-emails").get_data(as_text=True)
ok("Freeze heads-up" in t, "the Automatic emails page lists the freeze note")

# every page names its form fields for screen readers (one shared enhancer in the base template)
t = c.get("/agent/crm").get_data(as_text=True)
ok("Give every form field a name a screen reader can announce" in t and "btn-close" in t, "pages carry the field-naming enhancer")

# someone already warned by hand on the Frost Alert page this week does not get the automatic freeze note too
import care_alerts as _CA
conn = D.get_connection()
conn.execute("CREATE TABLE IF NOT EXISTS frost_sends (id INTEGER PRIMARY KEY AUTOINCREMENT, sender_id INTEGER, person_key TEXT, low REAL, sent_at TEXT DEFAULT CURRENT_TIMESTAMP)")
fid = conn.execute("SELECT id FROM agent_contacts WHERE email='fay@example.test'").fetchone()[0]
conn.execute("DELETE FROM automated_email_logs WHERE email_type='freeze'")
conn.execute("INSERT INTO frost_sends (sender_id, person_key, low) VALUES (?, ?, 24)", (ag, "c%d" % fid))
conn.commit(); conn.close()
A.set_auto_email(ag, "freeze", True)
sent.clear(); A.send_freeze_alerts()
ok(sent == [], "a person warned by hand this week is not warned again automatically")
A.FREEZE_QUIET_MONTHS = ()
conn = D.get_connection()
conn.execute("DELETE FROM frost_sends"); conn.execute("DELETE FROM automated_email_logs WHERE email_type='freeze'")
conn.commit(); conn.close()
sent.clear(); A.send_freeze_alerts()
ok("c%d" % fid in _CA.recently_alerted(ag), "the Frost Alert page knows who the automatic note already reached")

# lenders' borrowers get the freeze heads-up too, with the zip taken from the home address
ld = D.create_user("Lee Lender", "lender1@example.test", gp("password123"), "lender")
conn = D.get_connection()
conn.execute("DELETE FROM frost_sends"); conn.execute("DELETE FROM automated_email_logs WHERE email_type='freeze'")
conn.execute("INSERT INTO lender_borrowers (lender_user_id, name, email, property_address, auto_seasonal) VALUES (?, 'Bo Borrower', 'bo@example.test', '5 Pine Rd, Denver, CO 80202', 1)", (ld,))
conn.execute("INSERT INTO lender_borrowers (lender_user_id, name, email, property_address, auto_seasonal) VALUES (?, 'No Zip', 'nozip@example.test', '5 Pine Rd', 1)", (ld,))
conn.commit(); conn.close()
A.set_auto_email(ag, "freeze", False)
A.set_auto_email(ld, "freeze", True)
sent.clear(); A.send_freeze_alerts()
ok(sent == ["bo@example.test"], "a lender's borrower with a zip in the address gets the freeze heads-up (%s)" % sent)
sent.clear(); A.send_freeze_alerts()
ok(sent == [], "and only once a winter")
cl = A.app.test_client()
with cl.session_transaction() as s: s["user_id"] = ld; s["role"] = "lender"
ok("Freeze heads-up" in cl.get("/lender/automatic-emails").get_data(as_text=True), "the lender's Automatic emails page lists the freeze note")
