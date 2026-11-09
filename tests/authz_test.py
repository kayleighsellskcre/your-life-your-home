import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, transaction_helpers as TH
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
a = D.create_user("Owner Amy", "amy@x.com", gp("password123"), "agent")
b = D.create_user("Intruder Ian", "ian@x.com", gp("password123"), "agent")
tx = TH.create_transaction(a, "1 Private Rd", "Secret Client", "buyer", client_email="secret@x.com")
TH.add_transaction_participant(tx, "lender", "Lou", email="lou@x.com", added_by=a)
inv = D.create_invoice(a, client_name="Secret Client", client_email="secret@x.com", total=500)
con = D.add_agent_contact(a, "Secret Contact", email="sc@x.com", phone="5551112222", notes="private notes")
conn = D.get_connection()
pid = conn.execute("select id from transaction_participants where transaction_id=?", (tx,)).fetchone()[0]
ci = A.app.test_client()
with ci.session_transaction() as s: s["user_id"] = b; s["role"] = "agent"
def state():
    return (conn.execute("select count(*) from transactions").fetchone()[0], conn.execute("select current_stage from transactions where id=?", (tx,)).fetchone()[0],
            conn.execute("select count(*) from transaction_participants").fetchone()[0], conn.execute("select count(*) from agent_invoices").fetchone()[0] if conn.execute("select name from sqlite_master where name='agent_invoices'").fetchone() else -1,
            conn.execute("select notes from agent_contacts where id=?", (con,)).fetchone()[0])
before = state()
reads = [f"/agent/transactions/{tx}", f"/agent/transactions/{tx}/edit", f"/agent/transactions/{tx}/commission", f"/agent/transactions/{tx}/marketing-hub",
         f"/agent/transactions/{tx}/feature-spotlight-cards", f"/agent/invoices/{inv}/edit", f"/agent/invoices/{inv}/print", f"/agent/transactions/{tx}/documents/1/view"]
for u in reads:
    r = ci.get(u, follow_redirects=True); t = r.get_data(as_text=True)
    ok("Secret Client" not in t and "1 Private Rd" not in t and "secret@x.com" not in t, f"intruder cannot read {u}")
writes = [(f"/agent/transactions/{tx}/change-stage", {"stage": "closed", "new_stage": "closed"}), (f"/agent/transactions/{tx}/delete", {}),
          (f"/agent/transactions/{tx}/edit", {"property_address": "hacked", "client_name": "hacked"}),
          (f"/agent/transactions/{tx}/participants/add", {"participant_role": "lender", "participant_name": "Evil", "participant_email": "e@e.com"}),
          (f"/agent/transactions/{tx}/participants/{pid}/remove", {}), (f"/agent/invoices/{inv}/delete", {}), (f"/agent/invoices/{inv}/status", {"status": "paid"}),
          (f"/agent/invoices/{inv}/edit", {"client_name": "hacked"}), (f"/agent/crm/{con}/invite-to-portal", {}),
          (f"/agent/transactions/{tx}/add-client-to-crm", {}), (f"/agent/transactions/{tx}/commission", {"commission_amount": "999"})]
for u, d in writes:
    ci.post(u, data=d, follow_redirects=False)
ok(conn.execute("select property_address, client_name, current_stage from transactions where id=?", (tx,)).fetchone()[:] == ("1 Private Rd", "Secret Client", conn.execute("select current_stage from transactions where id=?", (tx,)).fetchone()[0]), "transaction untouched by intruder")
ok(conn.execute("select count(*) from transactions where id=?", (tx,)).fetchone()[0] == 1, "transaction not deleted")
ok(conn.execute("select count(*) from transaction_participants where transaction_id=?", (tx,)).fetchone()[0] == 1, "participants unchanged (none added or removed)")
row = conn.execute("select client_name, status from agent_invoices where id=?", (inv,)).fetchone() if conn.execute("select name from sqlite_master where name='agent_invoices'").fetchone() else None
ok(row is None or (row[0] == "Secret Client" and row[1] != "paid"), "invoice untouched")
lk = ci.get("/agent/crm/lookup?q=Secret").get_json(); ok(lk["contacts"] == [], "contact lookup is private")
ok("Secret Contact" not in ci.get("/agent/crm").get_data(as_text=True), "CRM list is private")
ok("Secret Contact" not in ci.get("/agent/crm/export.csv").get_data(as_text=True), "CSV export is private")
ok("Secret Client" not in ci.get("/planner").get_data(as_text=True), "planner is private")
ok("Secret" not in ci.get("/planner/people?q=Secret").get_data(as_text=True), "planner people search is private")
# other roles cannot use agent endpoints
lender = D.create_user("Lender Lou", "lou2@x.com", gp("password123"), "lender")
ho = D.create_user("Home Owner", "ho@x.com", gp("password123"), "homeowner", agent_id=a)
for who, role in ((lender, "lender"), (ho, "homeowner")):
    cc = A.app.test_client()
    with cc.session_transaction() as s: s["user_id"] = who; s["role"] = role
    for u in (f"/agent/transactions/{tx}", "/agent/crm", "/agent/crm/export.csv", "/agent/invoices", "/agent/crm/lookup?q=Secret"):
        r = cc.get(u, follow_redirects=True); t = r.get_data(as_text=True)
        ok("Secret" not in t and "1 Private Rd" not in t, f"{role} cannot read {u}")
# signed-out
cs = A.app.test_client()
for u in (f"/agent/transactions/{tx}", "/agent/crm", f"/agent/invoices/{inv}/print", "/lender/crm", "/homeowner", "/planner"):
    r = cs.get(u, follow_redirects=True); ok("Secret" not in r.get_data(as_text=True) and "/login" in r.request.path, f"signed-out blocked from {u}")
