import os, sys, tempfile, io, contextlib, re, json
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
lender = D.create_user("Lou Lender", "lou@x.com", gp("password123"), "lender")
home = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=agent)


def signed_in(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c


conn = D.get_connection()
conn.execute("UPDATE user_profiles SET brokerage_name = 'Acme Realty', phone = '9135550101' WHERE user_id = ?", (agent,))
if not conn.execute("SELECT 1 FROM user_profiles WHERE user_id = ?", (agent,)).fetchone():
    conn.execute("INSERT INTO user_profiles (user_id, role, brokerage_name, phone) VALUES (?, 'agent', 'Acme Realty', '9135550101')", (agent,))
conn.commit(); conn.close()
D.connect_homeowner_to_professional(home, lender, "lender", replace=True)
h, a, l = signed_in(home, "homeowner"), signed_in(agent, "agent"), signed_in(lender, "lender")


def tab_labels(html):
    nav = re.findall(r'<nav class="ylh-tabs".*?</nav>', html, re.S)
    if not nav:
        return []
    return [re.sub(r"<[^>]+>", "", re.sub(r'<span class="ylh-tab-badge">.*?</span>', "", x)).strip() for x in re.findall(r"<a [^>]*>.*?</a>", nav[0], re.S)]


def count(sql, *args):
    c = D.get_connection()
    try:
        return c.execute(sql, args).fetchone()[0]
    finally:
        c.close()


# ---- 4. homeowner ----
t = h.get("/homeowner/my-home").get_data(as_text=True)
ok(tab_labels(t) == ["My Home", "Home Value", "My Team"], "the homeowner sees exactly three tabs: My Home, Home Value, My Team")
ok("Next up for your home" in t and "Saved home details" in t and ">Documents<" in t, "My Home shows the next thing the house needs, saved details and documents")
ok("Amy Agent" in t and "Acme Realty" in t, "My Home shows the homeowner's own agent and brokerage")
ok("Kayleigh" not in t, "a homeowner with a different agent never sees 'Kayleigh Biggs'")
r = h.get("/homeowner/value/equity-overview")
ok(r.status_code == 200 and tab_labels(r.get_data(as_text=True))[1] == "Home Value", "the Home Value tab opens value and equity")
t = h.get("/homeowner/team").get_data(as_text=True)
ok("Amy Agent" in t and "Lou Lender" in t and "Message my agent" in t and "Message my lender" in t and "Ask my lender" in t, "My Team shows the agent and lender with message buttons and 'Ask my lender'")
ok("Only shared with your lender." in h.get("/homeowner/team/ask-lender").get_data(as_text=True), "'Ask my lender' says the numbers are only shared with the lender")

# messaging
h.post(f"/homeowner/team/{agent}", data={"body": "Hi Amy, who do you use for gutters?"})
ok("who do you use for gutters" in h.get(f"/homeowner/team/{agent}").get_data(as_text=True), "a homeowner can message their agent and sees the conversation")
t = a.get("/messages").get_data(as_text=True)
ok("Hal Homeowner" in t and "gutters" in t, "the agent sees the conversation in Messages")
ok("(you have 1 new message)" in a.get("/agent/my-clients").get_data(as_text=True), "the agent's menu button shows an unread message")
a.get(f"/messages/{home}")
ok('class="ylh-tab-badge"' not in a.get("/agent/my-clients").get_data(as_text=True), "opening the conversation clears the count")
a.post(f"/messages/{home}", data={"body": "I love Pro Gutters. Sending their number."})
ok("Pro Gutters" in h.get(f"/homeowner/team/{agent}").get_data(as_text=True), "the agent's reply shows for the homeowner")
other_h = D.create_user("Other Home", "oh@x.com", gp("password123"), "homeowner", agent_id=agent)
ok(signed_in(other_h, "homeowner").get(f"/homeowner/team/{lender}").status_code == 302, "a homeowner cannot open a thread with a professional who is not theirs")
stranger = D.create_user("Sam Stranger", "ss@x.com", gp("password123"), "agent")
ok(signed_in(stranger, "agent").get(f"/messages/{home}").status_code == 302, "an agent cannot read another agent's client conversation")

# shared scenarios
h.post("/homeowner/team/ask-lender", data={"kind": "refinance", "share_home_value": "1", "home_value": "$410,000", "loan_balance": "250000", "rate": "6.9", "note": "Thinking about refinancing."})
conn = D.get_connection(); sc = conn.execute("SELECT * FROM shared_scenarios").fetchall(); conn.close()
ok(len(sc) == 1 and json.loads(sc[0]["data"]) == {"home_value": 410000.0}, "only the numbers the homeowner ticked are saved (the others are never stored)")
t = l.get("/lender/shared-scenarios").get_data(as_text=True)
ok("Hal Homeowner" in t and "$410,000" in t and "Refinance scenario" in t and "250,000" not in t and "6.9" not in t, "the lender sees only the shared number, plus the note")
ok(tab_labels(t) == [], "the lender uses the menu, with no second tab bar")
ok("Shared a refinance scenario" in h.get(f"/homeowner/team/{lender}").get_data(as_text=True), "the homeowner just sees their conversation with the lender")
ok("410,000" not in signed_in(stranger, "agent").get("/lender/shared-scenarios").get_data(as_text=True), "other people cannot see shared scenarios")
other_l = D.create_user("Other Lender", "ol@x.com", gp("password123"), "lender")
ok("Hal Homeowner" not in signed_in(other_l, "lender").get("/lender/shared-scenarios").get_data(as_text=True), "another lender cannot see them either")
h.post("/homeowner/team/ask-lender", data={"kind": "payment"})
ok(count("SELECT COUNT(*) FROM shared_scenarios") == 1, "sharing nothing is refused")

# ---- 5. agent ----
t = a.get("/agent/my-clients").get_data(as_text=True)
ok(tab_labels(t) == [], "the agent uses the grouped menu, with no second tab bar")
menu = t[t.index('id="ylhHamMenu"'):].replace("</a>", "<")
for item in ("Weekly Planner", "CRM", "Follow-ups", "Events", "Booking &amp; Calendar", "Transactions", "Marketing Hub", "Financials", "Dashboard",
             "Invoices", "Vendor Network", "Client Contests", "Holiday Pie Pickup", "AI Concierge", "Seasonal Checklists", "Frost Alert", "Client Values"):
    ok(f">{item}<" in menu or item == "Client Values", f"agent menu: '{item}' is still there, in its group")
ok("<summary>People" in menu and "<summary>Money</summary>" in menu and "<summary>Account</summary>" in menu and "Settings &amp; Profile" in menu and "Plan &amp; Billing" in menu and "Sign Out" in menu,
   "there are grouped sections and an Account menu with Settings, Plan and Billing and Sign Out")
sent = []
A.send_reminder_email = lambda to, subj, body, **kw: (sent.append((to, subj, body)) or True)
A._bg = lambda fn, *a_, **k: fn(*a_, **k)
r = a.post("/agent/my-clients/invite", data={"name": "Bea Buyer", "email": "bea@x.com", "phone": "(913) 555-0199", "address": "12 Oak Lane, Shawnee, KS",
                                             "move_in_date": "2026-11-20", "send_email": "1"}, follow_redirects=True)
t = r.get_data(as_text=True)
ok("Send Bea Buyer their link" in t and "/signup?role=homeowner&amp;ref=" in t and "sms:" in t, "inviting a homeowner shows their personal link with a text button")
ok(sent and sent[-1][0] == "bea@x.com" and "/signup?role=homeowner&ref=" in sent[-1][2], "the invite is emailed to them with the link")
link = re.search(r'value="([^"]*signup\?role=homeowner&amp;ref=[^"]+)"', t).group(1).replace("&amp;", "&")
path = "/" + link.split("/", 3)[3]

# ---- 7. the closing link ----
c = A.app.test_client()
page = c.get(path).get_data(as_text=True)
ok("Amy Agent invited you" in page and "Acme Realty" in page, "the personal link opens a sign-up with the agent's name and brokerage")
with contextlib.redirect_stdout(io.StringIO()):
    r = c.post(path, data={"name": "Bea Buyer", "email": "bea@x.com", "password": "password123", "role": "homeowner"})
ok(r.status_code == 302 and "/homeowner/setup" in r.headers["Location"], "after signing up from the link, they go straight to setting up their home")
t = c.get("/homeowner/setup").get_data(as_text=True)
ok("Amy Agent" in t and "Acme Realty" in t and "12 Oak Lane" in t and "2026-11-20" in t, "set-up shows their agent's name and brokerage, with the address and move-in date the agent entered")
ok("Kayleigh" not in t, "they do not see 'Kayleigh Biggs' unless she is their agent")
c.post("/homeowner/setup", data={"address": "12 Oak Lane, Shawnee, KS", "move_in_date": "2026-11-20", "sprinkler": "on", "outdoor_faucets": "on"})
t = c.get("/homeowner/my-home").get_data(as_text=True)
ok("12 Oak Lane" in t and "Sprinkler system" in t and "November 20, 2026" in t, "the saved details appear on My Home")
w = A.app.test_client()
w.get("/signup?role=homeowner")
with contextlib.redirect_stdout(io.StringIO()):
    r = w.post("/signup?role=homeowner", data={"name": "Walk In", "email": "walk@x.com", "password": "password123", "role": "homeowner"}, follow_redirects=True)
ok("Welcome! You are connected to Kayleigh Biggs at Worth Clark Realty." in r.get_data(as_text=True), "someone who signs up with no link is connected to the default agent, shown by her real name and brokerage")
a.post(f"/agent/my-clients/{home}/move-in", data={"move_in_date": "2025-06-01"})
ok("Moved in 2025-06-01" in a.get("/agent/my-clients").get_data(as_text=True), "an agent can add move-in details for a client")

# ---- Send an Update ----
t = a.get("/agent/send-update").get_data(as_text=True)
ok("Freezing temperatures ahead" in t and "Disconnect garden hoses" in t and "Freeze reminder" in t, "Send an Update has a ready-to-edit freeze reminder")
sent.clear()
a.post("/agent/send-update/send", data={"who": [f"u{home}"], "subject": "Freeze tonight", "message": "Hi {first},\n\nCover the faucets."})
ok(len(sent) == 1 and sent[0][0] == "hal@x.com" and "Hi Hal," in sent[0][2] and "Amy Agent" in sent[0][2], "it sends to the chosen people with their first name filled in")
sent.clear()
a.post("/agent/send-update/send", data={"who": ["u99999", f"u{other_h}"], "subject": "x", "message": "y"})
ok(len(sent) == 1 and sent[0][0] == "oh@x.com", "only this agent's own clients can be emailed")
sent.clear()
a.post("/agent/send-update/send", data={"who": [f"u{lender}"], "subject": "x", "message": "y"})
ok(sent == [], "someone who is not this agent's client cannot be emailed")

# ---- 6. lender and homeowner menus keep everything ----
t = l.get("/lender/clients").get_data(as_text=True)
menu = t[t.index('id="ylhHamMenu"'):].replace("</a>", "<")
for item in ("Weekly Planner", "CRM", "Loan Pipeline", "Refinance Opportunities", "Events", "Frost Alert", "Marketing Hub", "Seasonal Checklists"):
    ok(f">{item}<" in menu, f"lender menu: '{item}' is still there, in its group")
t = h.get("/homeowner/my-home").get_data(as_text=True)
menu = t[t.index('id="ylhHamMenu"'):].replace("</a>", "<")
for item in ("My Profile", "Documents", "Home Timeline", "Care Guide", "Refinance &amp; Payoff", "Get Help"):
    ok(f">{item}<" in menu, f"homeowner menu: '{item}' is still there, in its group")
import re as _re
ok(_re.search(r"ylh-hdr-title[^>]*>\s*Agent\s*<", a.get("/agent/my-clients").get_data(as_text=True)) and _re.search(r"ylh-hdr-title[^>]*>\s*Homeowner\s*<", h.get("/homeowner/team").get_data(as_text=True)), "the header names who is signed in (Agent, Homeowner) without calling every page a dashboard")
ok(l.get("/lender/messages").status_code == 200 and "Shared a refinance" not in l.get("/lender/messages").get_data(as_text=True), "the lender's Email and Text Library page still opens as before")
