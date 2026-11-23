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
