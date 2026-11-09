import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from datetime import date, timedelta
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
ho = D.create_user("Full Owner", "full@x.com", gp("password123"), "homeowner", agent_id=ag)
empty = D.create_user("Fresh Owner", "fresh@x.com", gp("password123"), "homeowner", agent_id=ag)
p = D.add_property(ho, "1 Maple Ln, Shawnee, KS", 300000.0, "primary")
conn = D.get_connection()
conn.execute("INSERT INTO homeowner_snapshots (user_id, property_id, value_estimate, equity_estimate, loan_balance, loan_payment, loan_rate, loan_term_years, loan_start_date, initial_purchase_value) VALUES (?,?,?,?,?,?,?,?,?,?)",
             (ho, p, 380000, 160000, 220000, 1500, 7.0, 30, (date.today() - timedelta(days=365 * 4)).isoformat(), 300000))
conn.execute("INSERT INTO homeowner_timeline_events (user_id, event_date, title, category, cost) VALUES (?,?,?,?,?)", (ho, date.today().isoformat(), "Replaced water heater", "Plumbing", 1200))
conn.execute("INSERT INTO homeowner_projects (user_id, name, status, budget) VALUES (?,?,?,?)", (ho, "Kitchen refresh", "planned", 15000))
conn.execute("INSERT INTO homeowner_warranty_log (user_id, item_name, category, warranty_expiry) VALUES (?,?,?,?)", (ho, "Dishwasher", "Appliance", (date.today() + timedelta(days=30)).isoformat()))
conn.commit()
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ho; s["role"] = "homeowner"
r = c.get("/homeowner/value/refinance"); t = r.get_data(as_text=True)
ok(r.status_code == 200 and 'value="220000"' in t and 'value="7.0"' in t and 'value="1500"' in t and 'value="26"' in t, "refinance page is filled from the home profile (balance, rate, payment, years left)")
ok('id="nrate"' in t and 'value="6.0"' in t, "suggests a rate one point lower")
t = c.get("/homeowner/report").get_data(as_text=True)
ok("1 Maple Ln" in t and "380,000" in t and "+$80,000" in t and "Replaced water heater" in t and "Kitchen refresh" in t and "Dishwasher" in t, "report shows value, growth, care, projects, warranties")
ok("1 warranty ends in the next 90 days" in t, "report flags a warranty ending soon")
ce = A.app.test_client()
with ce.session_transaction() as s: s["user_id"] = empty; s["role"] = "homeowner"
for u in ("/homeowner/value/refinance", "/homeowner/report"):
    r = ce.get(u); ok(r.status_code == 200 and "Traceback" not in r.get_data(as_text=True), f"{u} works with no loan or home details")
t = ce.get("/homeowner/report").get_data(as_text=True); ok("Nothing logged yet" in t and "No projects yet" in t, "friendly empty states")
ok("Full Owner" not in ce.get("/homeowner/report").get_data(as_text=True) and "1 Maple" not in ce.get("/homeowner/report").get_data(as_text=True), "another homeowner's report is private")
cs = A.app.test_client()
ok("/login" in cs.get("/homeowner/report", follow_redirects=True).request.path, "signed-out visitors go to login")
m = c.get("/homeowner").get_data(as_text=True); ok("Refinance &amp; Payoff" in m and "Home Report" in m, "both pages are in the menu")
