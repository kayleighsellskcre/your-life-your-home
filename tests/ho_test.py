import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
agent = D.create_user("Agent Amy", "amy@x.com", gp("password123"), "agent")
conn = D.get_connection(); conn.execute("INSERT OR REPLACE INTO user_profiles (user_id, role, phone) VALUES (?,?,?)", (agent, "agent", "555-222-3333")); conn.commit()
tok = D.create_referral_link(agent_id=agent)
ho = D.create_user("Hannah Homeowner", "h@x.com", gp("password123"), "homeowner", agent_id=agent)
D.create_client_relationship(ho, agent, "agent", tok)
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ho; s["role"] = "homeowner"
def text(r):
    t = r.get_data(as_text=True); t = re.sub(r"<style.*?</style>|<script.*?</script>", "", t, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
r = c.get("/homeowner"); t = text(r)
ok(r.status_code == 200 and "What brings you here?" in t and "Welcome home, Hannah" in t, "new homeowner is asked what brings them here")
ok("Your next steps" in t and t.count("Start") <= 3 + 1, "only a few next steps are shown")
r = c.post("/homeowner/goal", data={"goal": "buyer"}); r = c.get("/homeowner"); t = text(r)
ok("what you can comfortably afford" in t and "Add your home" not in t, "someone who wants to own one day sees buying steps, not home-setup steps")
r = c.post("/homeowner/goal", data={"goal": "investor"}); r = c.get("/homeowner"); t = text(r)
ok("Add your home" in t, "an investor starts by adding their properties")
# add two properties
pid1 = D.add_property(ho, "1 Maple Ln, Shawnee, KS", 300000.0, "primary"); pid2 = D.add_property(ho, "2 Oak St, Olathe, KS", 250000.0, "rental")
conn = D.get_connection()
for pid, val, bal, pay in ((pid1, 300000, 200000, 1500), (pid2, 250000, 180000, 1200)):
    conn.execute("INSERT INTO homeowner_snapshots (user_id, property_id, value_estimate, loan_balance, loan_payment) VALUES (?,?,?,?,?)", (ho, pid, val, bal, pay))
conn.commit()
r = c.post(f"/homeowner/property/{pid2}/rental", data={"monthly_rent": "2,000", "monthly_expenses": "150"});
r = c.get("/homeowner"); t = text(r)
ok("Your properties" in t and "$550,000" in t and "$170,000" in t, "portfolio totals value and equity across properties")
ok("$650" in t, "cash flow = rent - payment - costs (2000-1200-150 = 650): %s" % re.findall(r"Cash flow / mo|\$650", t)[:2])
r = c.post(f"/homeowner/property/{pid1}/rental", data={"monthly_rent": "abc"}); ok(r.status_code == 302, "bad numbers are ignored safely")
other = D.create_user("Other Owner", "o@x.com", gp("password123"), "homeowner", agent_id=agent)
co = A.app.test_client()
with co.session_transaction() as s: s["user_id"] = other; s["role"] = "homeowner"
co.post(f"/homeowner/property/{pid2}/rental", data={"monthly_rent": "9999"})
rent = D.get_connection().execute("SELECT monthly_rent FROM properties WHERE id=?", (pid2,)).fetchone()[0]
ok(rent == 2000, "one homeowner cannot change another's rental numbers")
r = c.post("/homeowner/goal", data={"goal": "seller"}); t = text(c.get("/homeowner"))
ok("what you could walk away with" in t.lower(), "seller steps appear")
r = c.get("/homeowner/support/get-help"); t = text(r)
ok(r.status_code == 200 and "Agent Amy" in t and "Scheduling Coming Soon" not in t and "Call or text" in t, "Get Help now shows the homeowner's agent with call/text, no 'coming soon'")
r = c.get("/homeowner/care/energy-savings"); t = text(r); ok(r.status_code == 200 and "ENERGY STAR" in t and "once integrated" not in t, "energy page has real content")
r = c.get("/homeowner/value/equity-overview"); t = text(r); ok(r.status_code == 200 and "once configured" not in t, "value page has no placeholder text")
r = c.get("/homeowner/reno/planner"); ok(b"Which projects pay back" in r.data, "renovation planner links to cost estimator and ROI guide")
t = c.get("/homeowner").get_data(as_text=True)
ok(t.count('<details class="ylh-ham-more">') == 3 and "My Buyer Profile" in t and "Cost Estimator" not in t and "ylh-ham-scrim" in t, "menu is three tidy groups with the slide-in panel")

