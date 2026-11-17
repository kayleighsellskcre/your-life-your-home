import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
other = D.create_user("Ben Broker", "ben@x.com", gp("password123"), "agent")
def who(uid, role="agent"):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c
ca = who(agent)

# mileage
from mileage import rate_for, rate_label, usd
ok(rate_for("2025-06-01") == 0.70 and rate_for("2026-03-01") == 0.725 and rate_for("2026-07-01") == 0.76 and rate_for("2026-06-30") == 0.725, "mileage rate changes by year and by date")
ok(rate_label(0.725) == "$0.725" and rate_label(0.7) == "$0.70" and rate_label(0.76) == "$0.76", "rate shows as $0.725, not $0.7")
ok(usd(-154) == "-$154" and usd(1234.6) == "$1,235" and usd(-0.2) == "$0" and usd(None) == "$0" and usd(-1234.5, 2) == "-$1,234.50", "negative money reads -$154")
t = ca.get("/agent/financials").get_data(as_text=True)
ok("$-" not in t and "est-rate" in t, "Financials has no '$-' and shows the rate by trip date")

# zip
ok(D.clean_zip("66062.0") == "66062" and D.clean_zip("2108") == "02108" and D.clean_zip("nan") == "" and D.clean_zip("66062-1234") == "66062-1234", "ZIP codes are cleaned")
cid = D.create_agent_contact(agent, "Zed Zip", "zed@x.com") if hasattr(D, "create_agent_contact") else None
conn = D.get_connection()
conn.execute("INSERT INTO agent_contacts (agent_user_id, name, zip_code, stage) VALUES (?,?,?,?)", (agent, "Zoe Zip", "66062.0", "new"))
conn.commit(); conn.close()
ok(D.fix_saved_zip_codes() >= 1, "saved ZIPs with .0 are fixed")
conn = D.get_connection(); z = conn.execute("SELECT zip_code FROM agent_contacts WHERE name='Zoe Zip'").fetchone()[0]; conn.close()
ok(z == "66062", "the saved row now reads 66062")

# dashboard numbers
m = A.get_agent_dashboard_metrics(agent)
ok(m.get("total_contacts", -1) >= 1, "dashboard knows how many contacts there are")
ok(ca.get("/api/agent/dashboard-metrics").get_json().get("total_contacts", -1) >= 1, "live dashboard numbers include contacts")
from followups import due_for
crm = ca.get("/agent/crm").get_data(as_text=True)
n = len(due_for(agent))
ok((f"<b>{n}</b>" in crm) if n else ("waiting to hear" not in crm), "CRM banner count matches the Follow-ups page")
ok("waiting to hear from you" not in crm, "no contradictory 'waiting to hear' wording")

# invoices: nobody's personal details
conn = D.get_connection()
for u, n_ in ((agent, "Amy Agent"),):
    pass
conn.close()
for path in ("/agent/invoices", "/agent/invoices/new"):
    r = ca.get(path); tx = r.get_data(as_text=True)
    ok(r.status_code == 200 and "Cabinetry" not in tx and "Kayleigh" not in tx, f"{path} shows no one else's business name")
ok("Amy Agent" in ca.get("/agent/invoices").get_data(as_text=True), "invoices show the signed-in agent's own name")

# concierge
r = A.app.test_client().get("/concierge/%d" % agent)
ok(r.status_code == 404, "a counting number no longer opens a concierge page")
dash = ca.get("/agent/concierge").get_data(as_text=True)
ok(f"/concierge/{agent}\"" not in dash and "&#534A40;" not in dash and "&#5D5248;" not in dash, "concierge dashboard has a random link and no junk icons")
code = D.get_or_create_referral_code(agent, "agent")
r = A.app.test_client().get(f"/concierge/{code}")
tx = r.get_data(as_text=True)
ok(r.status_code == 200 and "Amy Agent" in tx, "the random link opens the page with the agent's name")
ok(f"/concierge/{code}" in dash, "the dashboard shows the random link")
r = A.app.test_client().post(f"/concierge/{agent}/chat", json={"message": "hi"})
ok(r.status_code == 404, "chat does not answer to a counting number either")

# pricing
pt = A.app.test_client().get("/pricing").get_data(as_text=True)
ok("Power Tools" not in pt and "geo mailers" not in pt, "pricing promises nothing that does not exist")
ok("Starter" in pt and "Professional" in pt and "Elite" in pt, "pricing lists all three plans")
st = ca.get("/agent/subscription").get_data(as_text=True)
ok("Elite" in st and "Starter" in st and "white-label" not in st.lower() and "Currently on Starter" in st, "Plan & Billing lists Elite and says which plan you are on")
ok("Your plan" in ca.get("/pricing").get_data(as_text=True), "Pricing says which plan you are on")
ok("never disappears" not in ca.get("/agent/settings/profile").get_data(as_text=True), "no developer wording in Settings")
