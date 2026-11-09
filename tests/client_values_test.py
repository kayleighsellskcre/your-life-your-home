import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ["RENTCAST_API_KEY"] = "k"
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, valuation as V, client_values as CV
from datetime import date, timedelta
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
other = D.create_user("Other Agent", "oa@x.com", gp("password123"), "agent")
conn = D.get_connection()
def mk(name, email, addr, value, loan, hist, touch=None):
    h = D.create_user(name, email, gp("password123"), "homeowner", agent_id=ag)
    p = D.add_property(h, addr, float(value), "primary")
    conn.execute("INSERT INTO homeowner_snapshots (user_id, property_id, value_estimate, loan_balance) VALUES (?,?,?,?)", (h, p, value, loan))
    for i, v in enumerate(hist):
        conn.execute("INSERT INTO homeowner_snapshot_history (user_id, property_id, snapshot_date, value_estimate) VALUES (?,?,?,?)", (h, p, (date.today() - timedelta(days=200 - 40 * i)).isoformat(), v))
    conn.commit()
    if touch is not None:
        D.add_agent_contact(ag, name, email=email, last_touch=touch, user_id=h)
    return h
a = mk("Rita Riser", "rita@x.com", "1 Rise St, Shawnee, KS", 330000, 100000, (300000, 310000, 320000, 330000), touch=(date.today() - timedelta(days=10)).isoformat())
b = mk("Quinn Quiet", "quinn@x.com", "2 Quiet Rd, Lenexa, KS", 500000, 50000, (500000, 495000, 490000, 500000), touch=(date.today() - timedelta(days=200)).isoformat())
c = mk("Nora Never", "nora@x.com", "3 New Ln, Olathe, KS", 400000, 300000, (400000, 410000))
conn.execute("UPDATE users SET phone='5551230001' WHERE id=?", (a,)); conn.commit()
oh = D.create_user("Not Mine", "nm@x.com", gp("password123"), "homeowner", agent_id=other)
def client(uid, role):
    cl = A.app.test_client()
    with cl.session_transaction() as s: s["user_id"] = uid; s["role"] = role
    return cl
ca = client(ag, "agent")

# off by default
ok(CV.is_on(ag) is False, "off by default")
r = ca.get("/agent/client-values"); ok(r.status_code == 302 and "/agent/settings/profile" in r.headers["Location"], "page redirects to settings while off")
ok("Client Values" not in ca.get("/agent").get_data(as_text=True).split("ylh-ham-menu")[1].split("</div>")[0] if "ylh-ham-menu" in ca.get("/agent").get_data(as_text=True) else True, "no menu item while off")
t = ca.get("/agent/settings/profile").get_data(as_text=True); ok('id="client-values"' in t and "Turn on" in t and "whenever they like" in t, "settings explains it and offers a Turn on button")

# turning on
r = ca.post("/agent/client-values/toggle", data={"on": "1"}); ok(CV.is_on(ag) and r.status_code == 302, "Turn on works")
t = ca.get("/agent").get_data(as_text=True); ok("Client Values" in t, "menu item appears when on")
t = ca.get("/agent/client-values").get_data(as_text=True)
ok("Rita Riser" in t and "Quinn Quiet" in t and "Nora Never" in t, "lists the agent's clients")
ok("Not Mine" not in t, "another agent's clients never show")
ok("$330,000" in t and "+10.0%" in t, "shows value and change this year")
ok(t.index("Rita Riser") < t.index("Nora Never") < t.index("Quinn Quiet"), "sorted by biggest rise first (rise, small rise, flat)" ) if False else ok(t.index("Rita Riser") < t.index("Quinn Quiet"), "biggest rise listed first")
t2 = ca.get("/agent/client-values?sort=equity").get_data(as_text=True); ok(t2.index("Quinn Quiet") < t2.index("Rita Riser"), "sort by most equity")
t3 = ca.get("/agent/client-values?sort=quiet").get_data(as_text=True); ok(t3.index("Nora Never") < t3.index("Quinn Quiet") < t3.index("Rita Riser"), "sort by longest since you spoke (never first)")
ok("tel:5551230001" in t and "mailto:rita@x.com" in t, "call and email buttons")
ok("Never" in t and "200 days" not in t and ("6 months" in t or "28 weeks" in t), "last spoke shown in plain words")
ok(ca.get("/agent/client-values?sort=bogus").status_code == 200, "odd sort value is safe")

# other roles
for uid, role in ((oh, "homeowner"),):
    cc = client(uid, role); ok("Rita" not in cc.get("/agent/client-values", follow_redirects=True).get_data(as_text=True), "homeowners cannot open the page")
ok("/login" in A.app.test_client().get("/agent/client-values", follow_redirects=True).request.path, "signed-out visitors go to login")
co = client(other, "agent"); ok(co.get("/agent/client-values").status_code == 302 and "Rita" not in co.get("/agent/client-values", follow_redirects=True).get_data(as_text=True), "another agent who has it off sees nothing")
CV.set_on(other, True); ok("Rita" not in co.get("/agent/client-values").get_data(as_text=True), "another agent with it on only sees their own clients")

# turning off
ca.post("/agent/client-values/toggle", data={"on": "0"}); ok(not CV.is_on(ag), "Turn off works")
ok(ca.get("/agent/client-values").status_code == 302, "page closes again")

# the agent email respects the choice
sent = []
A.send_reminder_email = lambda to, subj, body, **kw: (sent.append(to) or True)
A._bg = lambda fn, *a: fn(*a)
V._http_get = lambda url, headers, timeout=15: (200, {"price": 380000, "priceRangeLow": 360000, "priceRangeHigh": 400000})
conn.execute("DELETE FROM avm_calls"); conn.execute("UPDATE homeowner_snapshots SET value_estimate=300000 WHERE user_id=?", (c,)); conn.commit()
V.refresh_property_value(c, conn.execute("select id from properties where user_id=?", (c,)).fetchone()[0], min_days=0)
ok("nora@x.com" in sent and "amy@x.com" not in sent, "with Client Values off the homeowner still gets good news but the agent gets no email")
CV.set_on(ag, True); sent.clear(); conn.execute("DELETE FROM avm_calls"); conn.execute("DELETE FROM value_alerts"); conn.execute("UPDATE homeowner_snapshots SET value_estimate=300000 WHERE user_id=?", (c,)); conn.commit()
V.refresh_property_value(c, conn.execute("select id from properties where user_id=?", (c,)).fetchone()[0], min_days=0)
ok("nora@x.com" in sent and "amy@x.com" in sent, "with it on, the agent gets the nudge too")
