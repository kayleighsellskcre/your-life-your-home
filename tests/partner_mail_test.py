import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, transaction_helpers as TH
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
ln = D.create_user("Lou Lender", "lou@x.com", gp("password123"), "lender")
tx = TH.create_transaction(ag, "9 Oak Lane", "Pat Client", "buyer")
sent = []
def fake_send(to, subject, body, **kw):
    sent.append((to, subject, body)); return True
A.send_reminder_email = fake_send
A._bg = lambda fn, *a: fn(*a)
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ag; s["role"] = "agent"
c.post(f"/agent/transactions/{tx}/participants/add", data={"participant_role": "lender", "participant_name": "Lou Lender", "participant_email": "lou@x.com"})
ok(len(sent) == 1 and sent[0][0] == "lou@x.com" and "9 Oak Lane" in sent[0][1] and "/lender" in sent[0][2], "lender on the platform is told the deal is on their dashboard")
c.post(f"/agent/transactions/{tx}/participants/add", data={"participant_role": "lender", "participant_name": "New Lender", "participant_email": "new@lend.com"})
ok(len(sent) == 2 and "signup?role=lender" in sent[1][2], "lender not on the platform gets an invitation to join")
c.post(f"/agent/transactions/{tx}/participants/add", data={"participant_role": "title_company", "participant_name": "Tia Title", "participant_email": "tia@title.com"})
ok(len(sent) == 3 and "title company" in sent[2][2] and "amy@x.com" in sent[2][2], "title company gets a welcome with the agent's contact")
c.post(f"/agent/transactions/{tx}/participants/add", data={"participant_role": "transaction_coordinator", "participant_name": "No Email"})
ok(len(sent) == 3, "no email, no message")
c.post(f"/agent/transactions/{tx}/participants/add", data={"participant_role": "client", "participant_name": "Pat Two", "participant_email": "pat2@x.com"})
ok(len(sent) == 3, "clients are not sent partner emails")
r = c.post(f"/agent/transactions/{tx}/participants/add", data={"participant_role": "inspector", "participant_name": "Ian Inspector", "participant_email": "ian@insp.com"}, headers={"X-Requested-With": "XMLHttpRequest"})
ok(r.status_code == 200 and len(sent) == 4, "works for the pop-up (AJAX) add too")
