import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
import tc as T
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

pw = gp("password123")
tcu = D.create_user("Tina Coordinator", "tina@x.com", pw, "agent")
other = D.create_user("Omar Other", "omar@x.com", pw, "agent")
home = D.create_user("Hana Home", "hana@x.com", pw, "homeowner", agent_id=other)
def who(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c
ct, co = who(tcu, "agent"), who(other, "agent")
db = lambda sql, *a: D.get_connection().execute(sql, a).fetchall()

# an own deal and a coordinated deal
ct.post("/agent/transactions", data={"property_address": "1 Own St", "client_name": "Own Client", "side": "buyer", "stage": "summary", "client_email": "own@x.com"})
r = ct.post("/agent/transactions", data={"deal_kind": "coordinating", "coordinating_for": "Sam Smith", "coordinating_email": "sam@x.com", "coordinating_notify": "1",
                                          "property_address": "2 Their Ave", "client_name": "Their Client", "client_email": "hana@x.com", "side": "buyer", "stage": "summary"})
ok(r.status_code in (301, 302, 303), "creating a coordinated deal works")
ct.post("/agent/transactions", data={"deal_kind": "coordinating", "coordinating_for": "", "property_address": "3 Nobody Ln", "client_name": "X", "side": "buyer", "stage": "summary"})
ok(not db("SELECT 1 FROM transactions WHERE property_address='3 Nobody Ln'"), "a coordinated deal needs the agent's name")

mine = ct.get("/agent/transactions").get_data(as_text=True)
others = ct.get("/agent/transactions?view=others").get_data(as_text=True)
ok("1 Own St" in mine and "2 Their Ave" not in mine, "my deals list shows only my own deals")
ok("2 Their Ave" in others and "For Sam Smith" in others and "1 Own St" not in others, "the coordinated list shows the other agent's deals, labelled")
ok("Deals I coordinate for others" in mine and "My deals" in mine, "both tabs are there")
from transaction_helpers import get_agent_transactions
ok(len(get_agent_transactions(tcu)) == 1 and len(get_agent_transactions(tcu, coordinated=True)) == 1 and len(get_agent_transactions(tcu, coordinated=None)) == 2, "everything else that counts deals sees only the agent's own")

txid = db("SELECT id, homeowner_user_id, lender_user_id FROM transactions WHERE property_address='2 Their Ave'")[0]
ok(txid["homeowner_user_id"] is None, "the other agent's client is never linked to the coordinator's account")
ok("2 Their Ave" not in co.get("/agent/transactions").get_data(as_text=True) and "2 Their Ave" not in co.get("/agent/transactions?view=others").get_data(as_text=True), "nobody else sees the deal")
ok(co.get(f"/agent/transactions/{txid['id']}").status_code == 302 and co.get(f"/agent/transactions/{txid['id']}/contract").status_code == 302, "another agent cannot open it")

# nothing goes to the client, nothing lands in income
sent = []
A.send_reminder_email = lambda *a, **k: sent.append(a) or True
import automation
ct.post(f"/agent/transactions/{txid['id']}/change-stage", data={"new_stage": "closed"})
ok(not db("SELECT 1 FROM review_requests WHERE transaction_id=?", txid["id"]), "closing it schedules no thank-you to the other agent's client")
ok(not [s for s in sent if "hana@x.com" in s], "the other agent's client is not emailed about stage changes")
ct.post(f"/agent/transactions/{txid['id']}/commission", data={"sale_price": "100000", "commission_rate": "3"})
ok(not db("SELECT 1 FROM agent_commissions WHERE transaction_id=?", txid["id"]), "a coordinated deal never counts as my commission")
det = ct.get(f"/agent/transactions/{txid['id']}").get_data(as_text=True)
ok("Coordinating for Sam Smith" in det and "Save to Financials" not in det and "Deals I coordinate" in det, "the deal page says whose deal it is, has no commission box, and links back to the coordinated list")

# an own deal still works the old way
own = db("SELECT id FROM transactions WHERE property_address='1 Own St'")[0]["id"]
ct.post(f"/agent/transactions/{own}/change-stage", data={"new_stage": "closed"})
ok(db("SELECT 1 FROM review_requests WHERE transaction_id=?", own), "my own deals still schedule the thank-you as before")

# contract form and sheets
form = ct.get(f"/agent/transactions/{txid['id']}/contract").get_data(as_text=True)
ok("Sam Smith" in form and "Tina Coordinator" in form, "the contract form starts with the other agent and me as coordinator already filled in")
ct.post(f"/agent/transactions/{txid['id']}/contract", data={"f_contract_date": "2026-12-01", "f_closing_date": "2027-01-15", "f_purchase_price": "300000", "f_buyer_agent": "Sam Smith", "f_buyer_agent_contact": "sam@x.com", "f_tc_name": "Tina Coordinator"})
sh = ct.get(f"/agent/transactions/{txid['id']}/sheet/shareable").get_data(as_text=True)
ok("Coordinated for Sam Smith by Tina Coordinator" in sh and "$300,000" in sh, "the sheet shows who it is coordinated for and by, with the contract details")
with A.app.test_request_context():
    _rc = T.card_context(txid["id"], dict(db("SELECT * FROM transactions WHERE id=?", txid["id"])[0]))["recipients"]
ok(_rc and _rc[0]["email"] == "sam@x.com", "the agent is the first person offered when sharing")
sent.clear()
ct.post(f"/agent/transactions/{txid['id']}/client-update")
ok(not sent, "the coordinator cannot email the other agent's client directly")

# deadline heads-up goes to the coordinator and, unless switched off, to the agent they coordinate for
from datetime import date, timedelta
due = (date.today() + timedelta(days=2)).isoformat()
ct.post(f"/agent/transactions/{txid['id']}/contract", data={"f_contract_date": "2026-12-01", "f_closing_date": "2027-01-15", "f_purchase_price": "300000", "f_earnest_amount": "3000", "f_earnest_due_date": due, "f_tc_name": "Tina Coordinator"})
mails = []
T._H["send_email"] = lambda to, sub, body, *a, **k: mails.append((to, sub, body)) or True
T.send_deadline_reminders()
ok({m[0] for m in mails} == {"tina@x.com", "sam@x.com"}, "the coordinator and the other agent each get the heads-up")
ok(any(m[0] == "sam@x.com" and "Tina Coordinator" in m[2] and "tina@x.com" in m[2] for m in mails), "the agent's note comes from the coordinator and says how to reach them")
mails.clear(); T.send_deadline_reminders()
ok(not mails, "it never repeats")
r2 = ct.post("/agent/transactions", data={"deal_kind": "coordinating", "coordinating_for": "Quiet Agent", "coordinating_email": "quiet@x.com", "property_address": "5 Quiet Rd", "client_name": "C", "side": "buyer", "stage": "summary"})
qid = db("SELECT id FROM transactions WHERE property_address='5 Quiet Rd'")[0]["id"]
ok(db("SELECT coordinating_notify FROM transactions WHERE id=?", qid)[0][0] == 0, "leaving the box unticked switches the agent's emails off for that deal")
