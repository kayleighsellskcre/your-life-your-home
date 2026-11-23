import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
H = {"Origin": "http://localhost", "Referer": "http://localhost/"}

ln = D.create_user("Lena Lender", "lender1@example.test", gp("password123"), "lender")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ln; s["role"] = "lender"

t = c.get("/lender/loans").get_data(as_text=True)
ok('type="text" id="borrower_name"' in t and 'type="text" id="loan_type"' in t and 'type="text" id="target_payment"' in t, "Add a Loan fields carry the normal input style")
ok('name="status"' not in t and t.count('name="stage"') == 1, "one Stage dropdown, no separate Status")
r = c.post("/lender/loans", data={"borrower_name": "Bo Borrower", "stage": "uw_approval", "loan_type": "FHA"}, headers=H)
row = D.get_connection().execute("SELECT status, loan_stage FROM lender_borrowers WHERE name='Bo Borrower'").fetchone()
ok(row and row[0] == "underwriting" and row[1] == "uw_approval", "the stage sets the status behind the scenes")

r = c.get("/lender/roles")
ok(r.status_code == 302, "Key Contacts redirects away until it is built")
ok(">Key Contacts<" not in c.get("/lender/clients").get_data(as_text=True), "Key Contacts is out of the lender menu")

c2 = A.app.test_client()
ln2 = D.create_user("New Lender", "lender2@example.test", gp("password123"), "lender")
with c2.session_transaction() as s: s["user_id"] = ln2; s["role"] = "lender"
f = c2.get("/lender/financials").get_data(as_text=True)
ok("$0k" not in f and "$0</div>" in f, "no loans reads $0, not $0k")
ok("loadInsights();" not in f.split("// Auto-load insights")[-1] and "Add your first loan" in f, "empty Financials shows a short message, no endless spinner")
ok('maintainAspectRatio: false' in f and "precision: 0" in f, "the revenue chart fills its card with a whole-dollar axis")
d = c2.get("/lender").get_data(as_text=True)
ok("✦" in d and "⚙" in d, "Marketing Tools and Settings have icons")

# CRM: a "Joined the app" filter and marker for borrowers who have an account
ho = D.create_user("Jo Owner", "owner1@example.test", gp("password123"), "homeowner", lender_id=ln)
conn = D.get_connection()
conn.execute("INSERT INTO lender_borrowers (lender_user_id, name, status, user_id) VALUES (?, 'Joined Jo', 'prospect', ?)", (ln, ho))
conn.execute("INSERT INTO lender_borrowers (lender_user_id, name, status) VALUES (?, 'Not Yet Ned', 'prospect')", (ln,))
conn.commit(); conn.close()
t = c.get("/lender/crm?status=joined").get_data(as_text=True)
ok("Joined Jo" in t and "Not Yet Ned" not in t, "the Joined the app filter shows only people with an account")
t = c.get("/lender/crm").get_data(as_text=True)
ok("Joined the app</a>" in t and "&#10003; Joined the app" in t, "the CRM has the filter chip and marks who joined")

# A closed loan links to Financials with the form prefilled
conn = D.get_connection()
conn.execute("INSERT INTO lender_borrowers (lender_user_id, name, status, loan_stage) VALUES (?, 'Closed Cora', 'closed', 'closed')", (ln,))
conn.commit(); conn.close()
t = c.get("/lender/loans").get_data(as_text=True)
ok("log=Closed+Cora" in t and "Log it in Financials" in t, "a closed loan offers to log itself in Financials")
f = c.get("/lender/financials?log=Closed+Cora").get_data(as_text=True)
ok("URLSearchParams(location.search)" in f and "modal-revenue" in f, "Financials opens the funded loan form from that link")
conn = D.get_connection()
conn.execute("UPDATE lender_borrowers SET loan_amount=425000 WHERE name='Closed Cora'")
conn.commit(); conn.close()
ok("amount=425000" in c.get("/lender/loans").get_data(as_text=True), "the closed loan's amount travels to the Financials form")

# The lender CRM lists people in a table like the agent CRM, with details one click away
t = c.get("/lender/crm").get_data(as_text=True)
ok('class="b-table"' in t and 'id="bexp-' in t and "toggleBorrowerRow" in t, "the lender CRM is a table with expandable rows")
ok(t.count('class="borrower-checkbox"') >= 2 and "openEditModal(" in t, "the table keeps the checkboxes and the Edit button")
