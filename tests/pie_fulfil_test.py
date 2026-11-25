import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

amy = D.create_user("Amy Agent", "amy@example.test", gp("password123"), "agent")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = amy; s["role"] = "agent"


def q(sql, *a):
    conn = D.get_connection()
    try:
        return conn.execute(sql, a).fetchall()
    finally:
        conn.close()


form = {"title": "Holiday pies", "pie_types": "Apple\nPecan", "order_by": "2099-01-01", "slot_date": ["2030-12-20"], "slot_start": ["10:00"],
        "slot_end": ["12:00"], "slot_location": ["My office"], "slot_capacity": [""], "slot_id": [""],
        "offer_delivery": "1", "home_address": "12 Oak Lane, Shawnee, KS 66203"}
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/pies/new", data=form)
ev = q("SELECT * FROM pie_events")[0]
tok = ev["token"]
slot = q("SELECT id FROM pie_slots")[0]["id"]

page = A.app.test_client().get(f"/pies/r/{tok}").get_data(as_text=True)
ok("can't make" not in page.lower() and "cant_make" not in page, "the sign-up page no longer has the can't make it choice")
ok('value="delivery"' in page and 'value="home"' in page and "Please deliver my pie" in page, "delivery and home pickup sit beside the pickup times")
ok("How would you like to get it?" in page and "Pickup day, time and place" in page, "it asks how, and the usual pickup times are still there")


def order(name, email, **extra):
    g = A.app.test_client()
    data = {"choice": "pickup", "pie_type": "Apple", "name": name, "email": email, "phone": "9135550100"}
    data.update(extra)
    with contextlib.redirect_stdout(io.StringIO()):
        return g.post(f"/pies/r/{tok}", data=data, follow_redirects=True)


order("Pat Pickup", "pat@example.test", fulfillment="pickup", slot_id=str(slot))
order("Dee Deliver", "dee@example.test", fulfillment="delivery", delivery_address="9 Elm Street, Lenexa, KS")
order("Hal Home", "hal@example.test", fulfillment="home", want_date="2030-12-21", want_time="14:30")
rows = {r["name"]: r for r in q("SELECT * FROM pie_responses")}
ok(rows["Pat Pickup"]["choice"] == "pickup" and not rows["Pat Pickup"]["fulfillment"] and rows["Pat Pickup"]["slot_id"] == slot, "a pickup-time order is saved as before")
ok(rows["Dee Deliver"]["choice"] == "pickup" and rows["Dee Deliver"]["fulfillment"] == "delivery" and "Elm Street" in rows["Dee Deliver"]["address"], "a delivery order is a yes with a delivery address")
ok(rows["Hal Home"]["choice"] == "pickup" and rows["Hal Home"]["fulfillment"] == "home" and rows["Hal Home"]["want_date"] == "2030-12-21", "a home pickup order keeps its day and time")

# the old third answer is gone, but an older open page still works
order("Old Page", "old@example.test", choice="cant_make", fulfillment="delivery", delivery_address="1 Old Road, Olathe, KS")
ok(q("SELECT choice, fulfillment FROM pie_responses WHERE name='Old Page'")[0]["choice"] == "pickup", "an older open page that sends the old answer is treated as a yes with delivery")
bad = order("No Way", "nw@example.test", choice="cant_make")
ok(not q("SELECT * FROM pie_responses WHERE name='No Way'"), "the old answer alone is no longer accepted")

# mistakes are caught kindly
order("No Address", "na@example.test", fulfillment="delivery", delivery_address="")
order("No Day", "nd@example.test", fulfillment="home")
ok(not q("SELECT * FROM pie_responses WHERE name IN ('No Address','No Day')"), "delivery needs an address and home pickup needs a day and time")

# the host's page and the downloads show it plainly
d = c.get(f"/pies/{ev['id']}").get_data(as_text=True)
ok("Deliver" in d and "Home pickup" in d and "need another time" not in d, "the host sees deliveries and home pickups, with no 'need another time' tile")
csv = c.get(f"/pies/{ev['id']}/export.csv").get_data(as_text=True)
ok("Yes, delivery" in csv and "Yes, pickup at home" in csv and "needs another time" not in csv, "the spreadsheet names each way plainly")
x = c.get(f"/pies/{ev['id']}/export.xlsx")
ok(x.status_code == 200 and len(x.data) > 1000, "the Excel download still works")

# confirmation emails
sent = []
A.send_reminder_email = lambda to, subject, body, *a, **kw: (sent.append((to, body)), True)[1]
import pies as P
P._H["send_email"] = A.send_reminder_email
P._H["bg"] = lambda fn, *a, **kw: fn(*a, **kw)
order("Eve Email", "eve@example.test", fulfillment="delivery", delivery_address="5 Pine Court, Overland Park, KS")
body = next((b for t, b in sent if t == "eve@example.test"), "")
ok("delivered" in body and "5 Pine Court" in body and "text or email you" in body, "the delivery confirmation tells her what to expect")

# a host with neither extra turned on sees the simple form
with contextlib.redirect_stdout(io.StringIO()):
    c.post(f"/pies/{ev['id']}/edit", data={**{k: v for k, v in form.items() if k not in ("offer_delivery", "home_address")}, "slot_id": [str(slot)]})
page2 = A.app.test_client().get(f"/pies/r/{tok}").get_data(as_text=True)
ok("How would you like to get it?" not in page2 and "Pickup day, time and place" in page2, "with delivery and home pickup off, guests just choose a pickup time")

# the page a guest sees right after ordering says the right thing for each way
def thanks_text(**extra):
    g = A.app.test_client()
    data = {"choice": "pickup", "pie_type": "Apple", "name": "Tess Thanks", "email": "tess%d@example.test" % len(sent), "phone": "9135550100"}
    data.update(extra)
    with contextlib.redirect_stdout(io.StringIO()):
        return g.post(f"/pies/r/{tok}", data=data, follow_redirects=True).get_data(as_text=True)

with contextlib.redirect_stdout(io.StringIO()):
    c.post(f"/pies/{ev['id']}/edit", data={**form, "slot_id": [str(slot)]})
t1 = thanks_text(fulfillment="delivery", delivery_address="7 Birch Way, Lenexa, KS")
ok("as soon as they can" in t1 and "Birch Way" in t1, "after ordering delivery she is told it will be brought when possible")
t2 = thanks_text(fulfillment="home", want_date="2030-12-22", want_time="10:00")
ok("12 Oak Lane" in t2 and "Get directions" in t2, "after choosing home pickup she gets the address and directions")
t3 = thanks_text(fulfillment="pickup", slot_id=str(slot))
ok("Pickup:" in t3 and "Thank you" in t3, "after choosing a pickup time she sees the time and place")
