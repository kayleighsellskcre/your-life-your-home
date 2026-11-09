import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ["RENTCAST_API_KEY"] = "k"
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, valuation as V
from datetime import date, timedelta
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
answers = []
V._http_get = lambda url, headers, timeout=15: answers.pop(0)
def client(uid):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = "homeowner"
    return c
conn = D.get_connection()

# 1. a home with a RentCast value and some history
h1 = D.create_user("Val Owner", "v@x.com", gp("password123"), "homeowner", agent_id=ag)
p1 = D.add_property(h1, "10 First St, Shawnee, KS 66226", 250000.0, "primary")
conn.execute("INSERT INTO homeowner_snapshots (user_id, property_id, value_estimate, equity_estimate, loan_balance, value_low, value_high, value_refresh_source, last_value_refresh) VALUES (?,?,?,?,?,?,?,?,?)",
             (h1, p1, 331000, 131000, 200000, 318000, 344000, "RentCast", date.today().isoformat()))
for i, v in enumerate((300000, 308000, 315000, 322000, 331000)):
    conn.execute("INSERT INTO homeowner_snapshot_history (user_id, property_id, snapshot_date, value_estimate) VALUES (?,?,?,?)", (h1, p1, (date.today() - timedelta(days=120 - 30 * i)).isoformat(), v))
conn.commit()
t = client(h1).get("/homeowner").get_data(as_text=True)
ok('id="home-value"' in t and "$331,000" in t, "overview leads with the home's value")
ok("$318,000 to $344,000" in t, "shows the likely range")
ok("$31,000" in t and "+10.3%" in t and "&#9650;" in t and "since " + (date.today() - timedelta(days=120)).strftime("%b") in t, "shows change since the first reading, with an up arrow")
ok("<svg" in t and 'd="M' in t, "draws a trend line")
ok("Your equity" in t and "$131,000" in t, "shows equity")
ok("Automated market estimate from RentCast" in t, "says where the number came from")
ok("Refresh my value" in t and "/homeowner/value/refresh" in t, "has a Refresh button")
ok("Does this look off?" in t, "has a way to question the number")
ok(t.index('id="home-value"') < t.index("Your home's numbers") if "Your home's numbers" in t else True, "value comes before the other numbers")

# 2. refresh button end to end
answers.append((200, {"price": 340000, "priceRangeLow": 326000, "priceRangeHigh": 352000}))
c = client(h1)
conn.execute("DELETE FROM avm_calls"); conn.commit()
r = c.post("/homeowner/value/refresh", data={"property_id": p1}, follow_redirects=True)
v = conn.execute("select value_estimate, value_high from homeowner_snapshots where user_id=?", (h1,)).fetchone()
ok(v[0] == 340000 and v[1] == 352000, "Refresh pulls a new RentCast value")
t = c.get("/homeowner").get_data(as_text=True); ok("$340,000" in t, "overview shows the new value")

# 3. no value yet, key on, address present -> 'finding' state; no address -> add address
h2 = D.create_user("New Owner", "n@x.com", gp("password123"), "homeowner", agent_id=ag)
D.add_property(h2, "22 Second St, Lenexa, KS 66215", None, "primary")
t = client(h2).get("/homeowner").get_data(as_text=True); ok("We're finding your home's value" in t and "Find my value" in t, "new home shows a friendly finding-your-value state")
h3 = D.create_user("No Address", "na@x.com", gp("password123"), "homeowner", agent_id=ag)
D.add_property(h3, "", None, "primary")
t = client(h3).get("/homeowner").get_data(as_text=True); ok("Add your home's address" in t and "Find my value" not in t, "no address asks for one, no refresh button")

# 4. buyers do not see it; other homeowners never see someone else's value
h4 = D.create_user("Buyer", "b@x.com", gp("password123"), "homeowner", agent_id=ag)
conn.execute("INSERT OR REPLACE INTO homeowner_prefs (user_id, goal) VALUES (?, 'buyer')", (h4,)); conn.commit()
ok('id="home-value"' not in client(h4).get("/homeowner").get_data(as_text=True), "buyers do not see a home value card")
ok("340,000" not in client(h2).get("/homeowner").get_data(as_text=True) and "331,000" not in client(h3).get("/homeowner").get_data(as_text=True), "values are private to each homeowner")

# 5. key off -> no refresh button, existing value still shown
os.environ.pop("RENTCAST_API_KEY")
t = client(h1).get("/homeowner").get_data(as_text=True); ok("$340,000" in t and "Refresh my value" not in t, "without a key the value stays and the refresh button hides")
