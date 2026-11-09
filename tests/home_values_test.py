import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ["YLH_ADMIN_EMAILS"] = "owner@x.com"
os.environ["RENTCAST_API_KEY"] = "test-key-not-real"
os.environ["RENTCAST_MONTHLY_CAP"] = "3"
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
t = co.get("/admin/home-values").get_data(as_text=True); ok("RentCast key found" in t and "0 of 3" in t, "owner sees the page with the key detected and usage")
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
ok("monthly limit of 3" in t and len(calls) == 3, "stops at the monthly cap without calling RentCast")
ok("3 of 3" in co.get("/admin/home-values").get_data(as_text=True), "usage counter updates")
ok("Test lookup" in co.get("/admin/home-values").get_data(as_text=True) and "worked" in co.get("/admin/home-values").get_data(as_text=True), "recent lookups listed")
ok("Type a full address" in co.post("/admin/home-values", data={"address": "x"}).get_data(as_text=True), "short address is refused before any lookup")
ok("Home Values" in co.get("/admin/dashboard").get_data(as_text=True), "link on the admin dashboard")
