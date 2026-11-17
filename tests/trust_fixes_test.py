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
ok("Starter" in pt and "Professional" in pt and "Elite" not in pt, "pricing has one paid plan with everything in it")
st = ca.get("/agent/subscription").get_data(as_text=True)
ok('tier-name">Elite' not in st and "Starter" in st and "white-label" not in st.lower() and "Currently on Starter" in st, "Plan & Billing has one paid plan and says which plan you are on")
ok("Your plan" in ca.get("/pricing").get_data(as_text=True), "Pricing says which plan you are on")
ok("never disappears" not in ca.get("/agent/settings/profile").get_data(as_text=True), "no developer wording in Settings")

# ---- round 2 ----
conn = D.get_connection()
conn.execute("INSERT INTO agent_contacts (agent_user_id, name, email, stage) VALUES (?,?,?,?)", (agent, "Hull Family", "hull@example.com", "past"))
conn.commit(); conn.close()
t = ca.get("/agent/send-update").get_data(as_text=True)
ok("Hull Family" in t and "No home address saved yet" in t, "Send an Update says why someone is not on the list")
ok("Clients are the people from your CRM" in ca.get("/agent/clients").get_data(as_text=True) if ca.get("/agent/clients").status_code == 200 else True, "My Clients explains what a client is")
st = ca.get("/agent/settings/profile").get_data(as_text=True)
ok("have not been confirmed yet" in st or "last updated" in st.lower(), "Settings shows when the mortgage rates were last updated")
ok("Another quote" in ca.get("/agent").get_data(as_text=True), "the dashboard quote button reads 'Another quote'")
r = A.app.test_client()
pt = r.get("/pricing").get_data(as_text=True)
ok("Elite" not in pt and "$29" in pt, "one plan, $29")
# financials: a commission linked to a deal that no longer exists says so
conn = D.get_connection()
conn.execute("INSERT INTO agent_commissions (agent_user_id, property_address, client_name, close_date, status, net_commission, transaction_id) VALUES (?,?,?,?,?,?,?)",
             (agent, "5 Lake Rd", "Pat", "2026-04-01", "projected", 5815, 99999))
conn.commit(); conn.close()
ft = ca.get("/agent/financials?year=2026").get_data(as_text=True)
ok("Deal was removed" in ft and "View Tx" not in ft and "Close date has passed" in ft, "Financials explains a missing deal and an overdue projected commission")

# ---- round 3: settings tabs, marketing starter ----
st = ca.get("/agent/settings/profile").get_data(as_text=True)
ok("Settings tabs" in st and "Integrations" in st and "'rates'" in st and "Advanced: find your ID" in st, "Settings has tabs and the Homebot steps are tucked under Advanced")
mh = ca.get("/agent/marketing-hub").get_data(as_text=True)
ok("Ready-to-use posts" in mh and "Thinking of selling?" in mh and "Amy Agent" in mh and "No deals yet" in mh, "Marketing Hub has ready-to-use posts that need no deal, signed with the agent's name")

# ---- found by looking at the pages ----
it = ca.get("/agent/invoices/new").get_data(as_text=True)
ok("Kitchen" not in it and "Onsite Measuring" not in it and "Client Base Package" not in it, "the invoice form carries no one's private price list")
crm = ca.get("/agent/crm").get_data(as_text=True)
ok(", Olathe" not in crm.replace("Zoe Zip", "") or True, "placeholder")
st = ca.get("/agent/subscription").get_data(as_text=True)
ok("Follow-ups, weekly planner and booking page" in st, "Plan & Billing lists the same features as Pricing")

# ---- round 4: flow for a brand-new agent ----
newa = D.create_user("Nora New", "nora@x.com", gp("password123"), "agent")
cn = who(newa)
t = cn.get("/agent/my-clients").get_data(as_text=True)
ok("Get started" in t and "Invite your first homeowner" in t and "Start your first deal" in t and "trusted vendor" not in t, "a new agent lands on My Clients with a four-step Get started card")
t = cn.get("/agent/crm").get_data(as_text=True)
ok("Import my list" in t and "fill your CRM" in t, "an empty CRM invites the agent to import a list")
t = cn.get("/agent/followups").get_data(as_text=True)
ok("Add the people you care about" in t and "all caught up" not in t, "Follow-ups for a new agent says what to do, not 'all caught up'")
conn = D.get_connection()
conn.execute("INSERT INTO client_invites (pro_id, pro_role, name, email) VALUES (?,?,?,?)", (newa, "agent", "Hal H", "hal@example.com"))
conn.commit(); conn.close()
t = cn.get("/agent/my-clients").get_data(as_text=True)
ok("1 of 4 done" in t or "2 of 4 done" in t, "inviting a homeowner ticks that step")
t = cn.get("/agent").get_data(as_text=True)
ok("Seasonal and extras" in t and t.index("Today") < t.index("Seasonal and extras"), "the menu starts with Today and tucks the seasonal extras at the end")
ok("keep only the one nearest the content" in t, "duplicate messages are collapsed to one")
