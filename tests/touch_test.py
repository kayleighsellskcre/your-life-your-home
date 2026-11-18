import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
lender = D.create_user("Lou Lender", "lou@x.com", gp("password123"), "lender")
c = D.get_connection()
c.execute("INSERT INTO agent_contacts (agent_user_id, name, stage, last_touch) VALUES (?,?,?,?)", (agent, "Old Olga", "active", "2025-01-02"))
olga = c.execute("SELECT max(id) FROM agent_contacts").fetchone()[0]
c.execute("INSERT INTO lender_borrowers (lender_user_id, name, status, last_touch) VALUES (?,?,?,?)", (lender, "Old Otto", "preapproval", "2025-01-02"))
otto = c.execute("SELECT max(id) FROM lender_borrowers").fetchone()[0]
c.commit()
D.update_agent_contact(olga, agent, tags="VIP")
D.update_lender_borrower(otto, lender, tags="VIP")
ok(D.get_connection().execute("SELECT last_touch FROM agent_contacts WHERE id=?", (olga,)).fetchone()[0] == "2025-01-02", "tagging or editing a contact does not pretend you talked to them")
ok(D.get_connection().execute("SELECT last_touch FROM lender_borrowers WHERE id=?", (otto,)).fetchone()[0] == "2025-01-02", "editing a borrower does not reset when you last talked")
def who(uid, role):
    cl = A.app.test_client()
    with cl.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return cl
lc = who(lender, "lender")
with contextlib.redirect_stdout(io.StringIO()):
    page = lc.get("/lender/crm").get_data(as_text=True)
ok('name="next_action_date"' in page and "Follow up on" in page, "the borrower form has a Follow up on date")
with contextlib.redirect_stdout(io.StringIO()):
    lc.post("/lender/crm", data={"action": "update", "borrower_id": str(otto), "name": "Old Otto", "next_action_date": "2030-03-01", "next_action_note": "Send rates"})
row = D.get_connection().execute("SELECT next_action_date, next_action_note, last_touch FROM lender_borrowers WHERE id=?", (otto,)).fetchone()
ok(tuple(row) == ("2030-03-01", "Send rates", "2025-01-02"), "setting a follow-up date saves it without touching Last Touch")
with contextlib.redirect_stdout(io.StringIO()):
    lc.post("/lender/crm", data={"action": "update", "borrower_id": str(otto), "name": "Old Otto", "next_action_date": "", "next_action_note": ""})
ok(D.get_connection().execute("SELECT COALESCE(next_action_date,'') FROM lender_borrowers WHERE id=?", (otto,)).fetchone()[0] == "", "clearing the date removes the reminder")
D.update_agent_contact(olga, agent, last_touch="2026-05-01")
ok(D.get_connection().execute("SELECT last_touch FROM agent_contacts WHERE id=?", (olga,)).fetchone()[0] == "2026-05-01", "setting Last Touch on purpose still works")
