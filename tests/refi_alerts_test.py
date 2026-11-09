import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, refi_alerts as R, automation as AU
from datetime import date, timedelta
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

# payment math: $300k at 6% for 30 years is about $1,798.65
ok(abs(R.monthly_payment(300000, 6.0) - 1798.65) < 0.5, "payment math is right")

ln = D.create_user("Lena Lender", "lena@x.com", gp("password123"), "lender")
other = D.create_user("Other Lender", "ol@x.com", gp("password123"), "lender")
conn = D.get_connection()
conn.execute("INSERT OR REPLACE INTO user_profiles (user_id, role, conventional_rate_30yr) VALUES (?, 'lender', 6.0)", (ln,)); conn.commit()


def mk(name, email, addr, value, loan, rate, lender, touch=None):
    h = D.create_user(name, email, gp("password123"), "homeowner", lender_id=lender)
    p = D.add_property(h, addr, float(value), "primary")
    conn.execute("INSERT INTO homeowner_snapshots (user_id, property_id, value_estimate, loan_balance, loan_rate) VALUES (?,?,?,?,?)", (h, p, value, loan, rate))
    conn.commit()
    if touch:
        conn.execute("INSERT INTO lender_borrowers (lender_user_id, name, email, user_id, last_touch) VALUES (?,?,?,?,?)", (ln, name, email, h, touch)); conn.commit()
    return h


hi = mk("Hank HighRate", "hank@x.com", "1 High St, Olathe, KS", 400000, 320000, 7.5, ln, (date.today() - timedelta(days=120)).isoformat())
eq = mk("Edie Equity", "edie@x.com", "2 Equity Rd, Lenexa, KS", 600000, 200000, 5.9, ln)
low = mk("Lou LowRate", "lou@x.com", "3 Low Ln, Shawnee, KS", 350000, 300000, 6.0, ln)
rival = mk("Not Mine", "nm@x.com", "4 Other Ave, Topeka, KS", 500000, 100000, 9.0, other)
conn.execute("INSERT INTO lender_borrowers (lender_user_id, name, email, loan_amount, loan_rate) VALUES (?,?,?,?,?)", (ln, "Crystal CRM", "crys@x.com", 250000, 7.25))
conn.execute("INSERT INTO lender_borrowers (lender_user_id, name, loan_amount, loan_rate) VALUES (?,?,?,?)", (other, "Rival Borrower", 250000, 9.0))
conn.commit()

rows, mkt = R.find(ln)
names = [r["name"] for r in rows]
ok(mkt == 6.0, "uses the lender's posted 30-year rate")
ok("Hank HighRate" in names and "Edie Equity" in names and "Crystal CRM" in names, "finds high-rate, high-equity and CRM-only borrowers")
ok("Lou LowRate" not in names, "a rate near today's is not listed")
ok("Not Mine" not in names and "Rival Borrower" not in names, "another lender's people never show")
ok(names.count("Hank HighRate") == 1, "a client who is also in the CRM is not listed twice")
hank = next(r for r in rows if r["name"] == "Hank HighRate")
ok(hank["tags"] == ["rate"] or "rate" in hank["tags"], "high rate is flagged")
ok(abs(hank["savings"] - (R.monthly_payment(320000, 7.5) - R.monthly_payment(320000, 6.0))) < 0.01 and hank["savings"] > 300, "monthly savings are computed")
edie = next(r for r in rows if r["name"] == "Edie Equity")
ok("equity" in edie["tags"] and edie["savings"] is None and edie["equity"] == 400000, "equity flagged, no savings claim when the rate is fine")
ok(names.index("Hank HighRate") < names.index("Edie Equity"), "biggest savings first")
rows2, _ = R.find(ln, market=7.0)
h2 = next(r for r in rows2 if r["name"] == "Hank HighRate")
ok("rate" not in h2["tags"] and h2["savings"] is None, "a what-if rate changes who gets the rate flag")

cl = A.app.test_client()
with cl.session_transaction() as s: s["user_id"] = ln; s["role"] = "lender"
r = cl.get("/lender/refinance-opportunities"); t = r.get_data(as_text=True)
ok(r.status_code == 200 and "Hank HighRate" in t and "7.50%" in t and "Rate could drop" in t and "Equity to tap" in t, "page shows the people and why")
ok("Not Mine" not in t and "Rival Borrower" not in t, "page never leaks another lender's clients")
ok("Nothing is sent" in t, "page promises nothing goes to clients")
for q in ("?sort=equity", "?sort=quiet", "?sort=name", "?sort=bogus", "?rate=7", "?rate=abc", "?rate=99"):
    ok(cl.get("/lender/refinance-opportunities" + q).status_code == 200, "page ok with " + q)
ok("(what-if)" in cl.get("/lender/refinance-opportunities?rate=7").get_data(as_text=True), "what-if is labeled")
t = cl.get("/lender").get_data(as_text=True); ok("Refinance Opportunities" in t, "lender menu has the link")
t = cl.get("/lender/power-suite").get_data(as_text=True); ok("Refinance Opportunities" in t and "Refinance opportunity alerts based on" not in t, "Power Suite lists it as live, not coming soon")

# other roles and signed-out
for role in ("agent", "homeowner"):
    u = D.create_user(role + "x", role + "x@x.com", gp("password123"), role, agent_id=None, lender_id=ln if role == "homeowner" else None)
    c2 = A.app.test_client()
    with c2.session_transaction() as s: s["user_id"] = u; s["role"] = role
    r = c2.get("/lender/refinance-opportunities"); ok(r.status_code == 302 and "Hank" not in r.get_data(as_text=True), role + " cannot open it")
ok(A.app.test_client().get("/lender/refinance-opportunities").status_code == 302, "signed-out visitors are sent to login")

# Monday digest uses the same logic
d = AU.build_digest(ln, "lender", force_weekly=True)
sec = dict(d["sections"]).get("Clients who may want a refinance conversation")
ok(sec and any("Hank HighRate" in s and "could save about" in s for s in sec), "Monday digest lists the same opportunities with savings")
