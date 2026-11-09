import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
h1 = D.create_user("Owner One", "o1@x.com", gp("password123"), "homeowner", agent_id=ag)
h2 = D.create_user("Owner Two", "o2@x.com", gp("password123"), "homeowner", agent_id=ag)
l1 = D.create_user("Lender One", "l1@x.com", gp("password123"), "lender")
l2 = D.create_user("Lender Two", "l2@x.com", gp("password123"), "lender")
conn = D.get_connection()
def cols(t): return [r[1] for r in conn.execute(f"pragma table_info({t})")]
def ins(t, **kw):
    c = [k for k in kw if k in cols(t)]
    cur = conn.execute(f"insert into {t} ({','.join(c)}) values ({','.join('?'*len(c))})", [kw[k] for k in c]); conn.commit(); return cur.lastrowid
doc = ins("homeowner_documents", user_id=h1, document_name="Secret Deed", file_path="x.pdf", filename="x.pdf", original_filename="Secret Deed.pdf")
proj = ins("homeowner_projects", user_id=h1, name="Secret Kitchen", title="Secret Kitchen", project_name="Secret Kitchen")
ev = ins("homeowner_timeline_events", user_id=h1, title="Secret Event", event_title="Secret Event")
note = ins("simple_notes", user_id=h1, board_name="b", content="Secret Note", note_text="Secret Note", title="Secret Note")
bor = D.add_lender_borrower(l1, "Secret Borrower", email="sb@x.com")
rev = ins("lender_loan_revenue", lender_user_id=l1, borrower_name="Secret Borrower", loan_amount=300000, status="pending")
c2 = A.app.test_client()
with c2.session_transaction() as s: s["user_id"] = h2; s["role"] = "homeowner"
def cnt(t, where): return conn.execute(f"select count(*) from {t} where {where}").fetchone()[0]
for u in (f"/homeowner/documents/{doc}/view", f"/homeowner/reno/planner/project/{proj}/edit", f"/homeowner/design-boards/note/{note}/edit", f"/homeowner/{h1}"):
    t = c2.get(u, follow_redirects=True).get_data(as_text=True); ok("Secret" not in t and "o1@x.com" not in t, f"other homeowner cannot read {u}")
for u in (f"/homeowner/documents/{doc}/replace", f"/homeowner/reno/planner/project/{proj}/delete", f"/homeowner/reno/planner/project/{proj}/edit", f"/homeowner/home-timeline/delete/{ev}", f"/homeowner/design-boards/note/{note}/delete", f"/homeowner/design-boards/note/{note}/edit"):
    c2.post(u, data={"name": "hacked", "title": "hacked", "content": "hacked"}, follow_redirects=False)
ok(cnt("homeowner_documents", f"id={doc}") == 1 and cnt("homeowner_projects", f"id={proj} and name='Secret Kitchen'") == 1, "documents and projects untouched")
ok(cnt("homeowner_timeline_events", f"id={ev}") == 1 and cnt("simple_notes", f"id={note}") == 1, "timeline and notes untouched")
c3 = A.app.test_client()
with c3.session_transaction() as s: s["user_id"] = l2; s["role"] = "lender"
for u in (f"/lender/borrowers/{bor}/marketing-hub", "/lender/crm", "/lender/financials", f"/lender/clients/{h1}"):
    t = c3.get(u, follow_redirects=True).get_data(as_text=True); ok("Secret" not in t and "sb@x.com" not in t, f"other lender cannot read {u}")
for u in (f"/lender/financials/revenue/{rev}/delete", f"/lender/financials/revenue/{rev}/mark-funded", f"/lender/borrowers/{bor}/marketing-hub/create"):
    c3.post(u, data={}, follow_redirects=False)
ok(cnt("lender_loan_revenue", f"id={rev} and status='pending'") == 1, "revenue row untouched")
c4 = A.app.test_client()
with c4.session_transaction() as s: s["user_id"] = ag; s["role"] = "agent"
t = c4.get(f"/agent/clients/{h1}", follow_redirects=True).get_data(as_text=True); ok(c4.get(f"/agent/clients/{h1}").status_code == 200, "agent sees own client")
a2 = D.create_user("Agent Two", "a2@x.com", gp("password123"), "agent")
c5 = A.app.test_client()
with c5.session_transaction() as s: s["user_id"] = a2; s["role"] = "agent"
t = c5.get(f"/agent/clients/{h1}", follow_redirects=True).get_data(as_text=True); ok("Owner One" not in t and "o1@x.com" not in t, "another agent cannot open someone else's client")
