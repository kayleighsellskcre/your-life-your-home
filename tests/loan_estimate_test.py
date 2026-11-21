import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from datetime import date
from werkzeug.security import generate_password_hash as gp
import loan_estimate as LE
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
H = {"Origin": "http://localhost", "Referer": "http://localhost/"}

e = LE.estimate(350000, 2019, 10, today=date(2026, 11, 21))
ok(e and 255000 < e["balance"] < 280000 and e["rate"] == 3.9 and e["term"] == 30, "a 2019 purchase gets a sensible balance and the typical rate for that year")
ok(LE.estimate(0, 2019) is None and LE.estimate(300000, 2099) is None and LE.estimate("abc", 2019) is None, "nonsense inputs are refused")
ok(LE.estimate(300000, 1995, 10, today=date(2026, 11, 21))["balance"] == 0, "a fully paid 30 year loan estimates to zero")

ag = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
ho = D.create_user("Est Owner", "est@x.com", gp("password123"), "homeowner", agent_id=ag)
nohome = D.create_user("No Home", "nohome@x.com", gp("password123"), "homeowner", agent_id=ag)
p = D.add_property(ho, "5 Oak St, Olathe, KS", 400000.0, "primary")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ho; s["role"] = "homeowner"
r = c.get("/homeowner/loan/estimate")
ok(r.status_code == 200 and "Estimate my loan" in r.get_data(as_text=True), "the estimate page opens")
r = c.post("/homeowner/loan/estimate", data={"price": "350000", "year": "2019", "down": "10"}, headers=H)
t = r.get_data(as_text=True)
ok(r.status_code == 200 and "probably about" in t and "Use this estimate" in t, "calculating shows the estimate without saving it yet")
conn = D.get_connection()
row = conn.execute("SELECT loan_balance FROM homeowner_snapshots WHERE user_id=?", (ho,)).fetchone()
ok(not row or not row[0], "nothing is saved until they accept it")
r = c.post("/homeowner/loan/estimate", data={"price": "350000", "year": "2019", "down": "10", "save": "1"}, headers=H)
ok(r.status_code == 302, "accepting the estimate saves it and returns to the dashboard")
row = dict(D.get_connection().execute("SELECT loan_balance, loan_rate, loan_is_estimate, initial_purchase_value FROM homeowner_snapshots WHERE user_id=?", (ho,)).fetchone())
ok(row["loan_balance"] > 200000 and row["loan_rate"] == 3.9 and row["loan_is_estimate"] == 1 and row["initial_purchase_value"] == 350000, "the loan is saved and marked as an estimate")
D.get_connection().execute("UPDATE homeowner_snapshots SET value_estimate=400000, equity_estimate=130000 WHERE user_id=?", (ho,)).connection.commit()
rep = c.get("/homeowner/report").get_data(as_text=True)
ok("estimated loan balance" in rep, "the Home Report labels the loan as estimated")
c2 = A.app.test_client()
with c2.session_transaction() as s: s["user_id"] = nohome; s["role"] = "homeowner"
r = c2.get("/homeowner/loan/estimate")
ok(r.status_code == 302, "someone with no home yet is sent to add it first")
r = c.post("/homeowner/loan/estimate", data={"price": "", "year": "", "down": "10"}, headers=H)
ok(r.status_code == 200 and "need what you paid" in r.get_data(as_text=True), "missing numbers get a kind message")
