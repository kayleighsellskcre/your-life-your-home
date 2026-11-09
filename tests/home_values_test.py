import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ["YLH_ADMIN_EMAILS"] = "owner@x.com"
os.environ["RENTCAST_API_KEY"] = "test-key-not-real"
os.environ["RENTCAST_MONTHLY_CAP"] = "2"
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, valuation as V
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
owner = D.create_user("Owner", "owner@x.com", gp("password123"), "agent")
other = D.create_user("Regular", "reg@x.com", gp("password123"), "agent")
answers = []
calls = []
def fake_get(url, headers, timeout=15):
    calls.append((url, headers)); return answers.pop(0)
V._http_get = fake_get
co = A.app.test_client()
with co.session_transaction() as s: s["user_id"] = owner; s["role"] = "agent"
cr = A.app.test_client()
with cr.session_transaction() as s: s["user_id"] = other; s["role"] = "agent"
ok("/login" in cr.get("/admin/home-values", follow_redirects=True).request.path, "regular accounts cannot open the page")
ok("/login" in cr.post("/admin/home-values", data={"address": "1 A St"}, follow_redirects=True).request.path and not calls, "regular accounts cannot run a lookup")
t = co.get("/admin/home-values").get_data(as_text=True); ok("RentCast key found" in t and "0 of 2" in t, "owner sees the page with the key detected and usage")
answers.append((200, {"price": 412000, "priceRangeLow": 390000, "priceRangeHigh": 435000}))
t = co.post("/admin/home-values", data={"address": "123 Main St, Overland Park, KS 66204"}).get_data(as_text=True)
ok("Connected" in t and "412,000" in t and "390,000" in t and "435,000" in t, "good answer shows value and range")
ok(calls and calls[0][1].get("X-Api-Key") == "test-key-not-real" and "address=123+Main+St" in calls[0][0] and "api.rentcast.io/v1/avm/value" in calls[0][0], "calls RentCast's value endpoint with the key header")
ok("test-key-not-real" not in t, "the key is never shown on the page")
answers.append((401, None))
t = co.post("/admin/home-values", data={"address": "123 Main St, Overland Park, KS 66204"}).get_data(as_text=True)
ok("did not accept the key" in t, "bad key explained in plain English")
answers.append((404, None))
t = co.post("/admin/home-values", data={"address": "999 Nowhere Rd, Nowhere, KS 00000"}).get_data(as_text=True)
ok("could not find a value" in t, "address not found explained")
t = co.post("/admin/home-values", data={"address": "456 Another St, Lenexa, KS 66215"}).get_data(as_text=True)
ok("monthly limit of 2" in t and len(calls) == 3, "stops at the monthly cap without calling RentCast")
ok("2 of 2" in co.get("/admin/home-values").get_data(as_text=True), "usage counter updates")
ok("Test lookup" in co.get("/admin/home-values").get_data(as_text=True) and "worked" in co.get("/admin/home-values").get_data(as_text=True), "recent lookups listed")
ok("Type a full address" in co.post("/admin/home-values", data={"address": "x"}).get_data(as_text=True), "short address is refused before any lookup")
ok("Home Values" in co.get("/admin/dashboard").get_data(as_text=True), "link on the admin dashboard")
# ---- key cleaning and RentCast's own words ----
for raw, want in (("  abc123\n", "abc123"), ('"abc123"', "abc123"), ("'abc123'", "abc123"), ("X-Api-Key: abc123", "abc123"), ("Bearer abc123", "abc123")):
    os.environ["RENTCAST_API_KEY"] = raw
    ok(V.api_key() == want, f"key pasted as {raw!r} is cleaned")
os.environ["RENTCAST_API_KEY"] = "  spaced-key \n"
os.environ["RENTCAST_MONTHLY_CAP"] = "50"
answers.append((401, {"message": "Invalid API key"}))
t = co.post("/admin/home-values", data={"address": "4632 Woodstock St, Shawnee, KS 66226"}).get_data(as_text=True)
ok("RentCast answered 401: Invalid API key" in t, "page shows what RentCast actually said")
ok(calls[-1][1].get("X-Api-Key") == "spaced-key", "the cleaned key is what gets sent")
# rejected-key and network failures do not use up the monthly allowance
conn = D.get_connection()
before = V.settings_summary()["used"]
answers.append((401, None)); co.post("/admin/home-values", data={"address": "1 Test St, Shawnee, KS 66226"})
answers.append((0, None)); co.post("/admin/home-values", data={"address": "2 Test St, Shawnee, KS 66226"})
ok(V.settings_summary()["used"] == before, "failed key or network attempts do not count against the monthly limit")
# ---- refresh now, and failed attempts never block a retry ----
os.environ["RENTCAST_API_KEY"] = "good-key"; os.environ["RENTCAST_MONTHLY_CAP"] = "50"
hoa = D.create_user("Home A", "ha@x.com", gp("password123"), "homeowner", agent_id=owner)
pa = D.add_property(hoa, "10 First St, Shawnee, KS 66226", 250000.0, "primary")
c2 = D.get_connection()
c2.execute("INSERT INTO homeowner_snapshots (user_id, property_id, value_estimate, loan_balance) VALUES (?,?,?,?)", (hoa, pa, 250000, 100000))
c2.execute("INSERT INTO avm_calls (property_id, status) VALUES (?, '403')", (pa,)); c2.commit()
answers.append((200, {"price": 301500, "priceRangeLow": 290000, "priceRangeHigh": 312000}))
r = co.post("/admin/home-values/refresh-now", follow_redirects=True); t = r.get_data(as_text=True)
v = c2.execute("select value_estimate, value_refresh_source, value_low from homeowner_snapshots where user_id=?", (hoa,)).fetchone()
ok(v and v[0] == 301500 and v[1] == "RentCast" and v[2] == 290000, "Update now fetches a real value even after earlier rejected-key attempts")
ok("Checked" in t and "10 First St" in t, "page confirms and lists the lookup")
before = len(calls)
r = co.post("/admin/home-values/refresh-now", follow_redirects=True)
ok(len(calls) == before, "a home just refreshed is not looked up again until its time")
ok("/login" in cr.post("/admin/home-values/refresh-now", follow_redirects=True).request.path, "regular accounts cannot run it")
