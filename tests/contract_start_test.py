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
amy = D.create_user("Amy Agent", "amy@x.com", pw, "agent")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = amy; s["role"] = "agent"; s["name"] = "X"
db = lambda sql, *a: D.get_connection().execute(sql, a).fetchall()
pdf = lambda: (io.BytesIO(b"%PDF-1.4 fake"), "contract.pdf")

FOUND = {"property_address": "42 Maple Dr, Olathe, KS 66061", "buyer_names": "Bo and Bea Buyer", "purchase_price": "315000",
         "contract_date": "2026-12-01", "closing_date": "2027-01-20", "earnest_amount": "$3,000", "earnest_holder": "Chicago Title",
         "earnest_due_days": "3 days", "inspection_days": "10", "buyer_title": "Chicago Title", "lender": "Lou Lender | Acme Mortgage",
         "seller": "Sally Seller", "county": "Johnson County", "contingency": "None", "bogus_date": "x"}
T.read_contract = lambda stream, extra=None: (dict(FOUND), None)

r = c.post("/agent/transactions", data={"contract": pdf(), "side": "buyer"}, content_type="multipart/form-data")
tx = db("SELECT * FROM transactions WHERE property_address LIKE '42 Maple%'")
ok(len(tx) == 1 and tx[0]["client_name"] == "Bo and Bea Buyer" and tx[0]["purchase_price"] == 315000, "a contract alone starts the deal with address, buyer and price")
ok(r.status_code in (301, 302, 303) and f"/agent/transactions/{tx[0]['id']}/contract" in r.headers["Location"], "then it opens the details to check")
data, token = T.load(tx[0]["id"])
ok(data["closing_date"] == "2027-01-20" and data["earnest_amount"] == "$3,000" and data["lender"].startswith("Lou") and data["earnest_due_days"] == "3", "the dates, money, title and lender are all filled in")
ok(tx[0]["current_stage"] == "under_contract" and tx[0]["target_close_date"] == "2027-01-20", "the deal moves to under contract with its closing date")
ok(len(db("SELECT 1 FROM transaction_deadlines WHERE transaction_id=?", tx[0]["id"])) >= 3, "the deadlines are created automatically")
ok(data["tc_name"].startswith("Amy"), "I am filled in as coordinator")

# coordinated version
T_found = dict(FOUND, property_address="7 Elm Ct, Lenexa, KS 66215", buyer_names="Cy Client")
T.read_contract = lambda stream, extra=None: (dict(T_found), None)
c.post("/agent/transactions", data={"contract": pdf(), "deal_kind": "coordinating", "coordinating_for": "Sam Smith", "coordinating_email": "sam@x.com", "coordinating_notify": "1", "side": "buyer"}, content_type="multipart/form-data")
t2 = db("SELECT * FROM transactions WHERE property_address LIKE '7 Elm%'")[0]
d2, _ = T.load(t2["id"])
ok(t2["coordinating_for"] == "Sam Smith" and d2["buyer_agent"] == "Sam Smith", "a contract can start a deal coordinated for another agent")
c.post("/agent/transactions", data={"contract": pdf(), "deal_kind": "coordinating", "coordinating_for": "", "side": "buyer"}, content_type="multipart/form-data")
ok(len(db("SELECT 1 FROM transactions")) == 2, "coordinating still needs the agent's name")

# unreadable contract
T.read_contract = lambda stream, extra=None: (None, "That PDF looks like a scan, so I could not read it this time.")
r = c.post("/agent/transactions", data={"contract": pdf(), "side": "buyer"}, content_type="multipart/form-data")
ok(len(db("SELECT 1 FROM transactions")) == 2 and "add=1" in r.headers["Location"], "an unreadable scan creates nothing and sends you back to type it in")
c.post("/agent/transactions", data={"contract": pdf(), "property_address": "9 Typed St", "client_name": "Typed Client", "side": "buyer", "stage": "summary"}, content_type="multipart/form-data")
ok(len(db("SELECT 1 FROM transactions WHERE property_address='9 Typed St'")) == 1, "an unreadable scan still starts the deal from what was typed")
ok(not db("SELECT 1 FROM transactions WHERE property_address=''"), "no blank deals")

# uploading onto an existing deal never overwrites what was typed
T.read_contract = lambda stream, extra=None: ({"closing_date": "2027-03-01", "county": "Other County", "seller": "New Seller"}, None)
c.post(f"/agent/transactions/{tx[0]['id']}/contract/upload", data={"contract": pdf()}, content_type="multipart/form-data")
d3, _ = T.load(tx[0]["id"])
ok(d3["closing_date"] == "2027-01-20" and d3["county"] == "Johnson County", "reading a contract onto an existing deal keeps what is already filled in")
