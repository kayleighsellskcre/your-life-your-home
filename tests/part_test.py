import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from transaction_helpers import create_transaction
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
tx = create_transaction(ag, "1 Elm St", "Pat Client", "pat@x.com")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ag; s["role"] = "agent"
for role, nm in (("lender", "Lola Lender"), ("title_company", "Tia Title"), ("transaction_coordinator", "Tom TC"), ("other_agent", "Coop Carl")):
    c.post(f"/agent/transactions/{tx}/participants/add", data={"participant_role": role, "participant_name": nm, "participant_email": nm[:3].lower()+"@x.com"})
t = c.get(f"/agent/transactions/{tx}").get_data(as_text=True)
ok(all(n in t for n in ("Lola Lender", "Tia Title", "Tom TC", "Coop Carl")), "all four deal partners are listed")
ok("Title Company" in t and "Transaction Coordinator" in t and "Lender" in t, "each shows its own role badge")
pid = D.get_connection().execute("SELECT id FROM transaction_participants WHERE name='Tia Title'").fetchone()[0]
r = c.post(f"/agent/transactions/{tx}/participants/{pid}/remove")
ok(r.status_code == 302, "remove from the page goes back to the deal")
ok('tx-p-name">Tia Title' not in c.get(f"/agent/transactions/{tx}").get_data(as_text=True), "removed partner leaves the participants list")
r = c.post(f"/agent/transactions/{tx}/participants/add", data={"participant_role": "hacker", "participant_name": "Zed"})
ok(D.get_connection().execute("SELECT participant_type FROM transaction_participants WHERE name='Zed'").fetchone()[0] == "client", "unknown role falls back safely")
import io as _io
r = c.post(f"/agent/transactions/{tx}/documents/upload", data={"document_type": "title_report", "file": (_io.BytesIO(b"hello title"), "Title Report.pdf")}, content_type="multipart/form-data")
t = c.get(f"/agent/transactions/{tx}").get_data(as_text=True)
print("DBG", r.status_code, "Title_Report.pdf" in t, "Title Report" in t); ok(r.status_code == 302 and ("Title_Report.pdf" in t), "uploaded document appears on the deal")
did = D.get_connection().execute("SELECT id FROM transaction_documents").fetchone()[0]
r = c.get(f"/agent/transactions/{tx}/documents/{did}/view"); ok(r.status_code == 200 and r.data == b"hello title", "agent can open it")
other = D.create_user("Bob", "bob@x.com", gp("password123"), "agent")
c2 = A.app.test_client()
with c2.session_transaction() as s: s["user_id"] = other; s["role"] = "agent"
r = c2.get(f"/agent/transactions/{tx}/documents/{did}/view"); ok(r.status_code == 302, "another agent cannot open it")
r = c2.post(f"/agent/transactions/{tx}/participants/add", data={"participant_name": "Sneak"}); ok(D.get_connection().execute("SELECT count(*) FROM transaction_participants WHERE name='Sneak'").fetchone()[0] == 0, "another agent cannot add people to my deal")
lend = D.create_user("Lola Lender", "lola@x.com", gp("password123"), "lender")
c.post(f"/agent/transactions/{tx}/participants/add", data={"participant_role": "lender", "participant_name": "Lola Lender", "participant_email": "lola@x.com"})
ok(D.get_connection().execute("select lender_user_id from transactions where id=?", (tx,)).fetchone()[0] == lend, "adding a lender on the platform links them to the deal automatically")
