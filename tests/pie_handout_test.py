import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

amy = D.create_user("Amy Agent", "amy@example.test", gp("password123"), "agent")
bob = D.create_user("Bob Other", "bob@example.test", gp("password123"), "agent")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = amy; s["role"] = "agent"
H = {"Origin": "http://localhost", "Referer": "http://localhost/pies"}


def q(sql, *a):
    conn = D.get_connection()
    try:
        return conn.execute(sql, a).fetchall()
    finally:
        conn.close()


form = {"title": "Holiday Pie Pickup", "pie_types": "Apple\nPecan\nPumpkin", "order_by": "2099-01-01",
        "slot_date": ["2030-12-20", "2030-12-21"], "slot_start": ["10:00", "09:00"], "slot_end": ["12:00", "11:00"],
        "slot_location": ["12 Oak Lane, Shawnee", "Main Street Office"], "slot_capacity": ["", ""], "slot_id": ["", ""],
        "offer_delivery": "1", "home_address": "99 Home Road, Shawnee, KS"}
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/pies/new", data=form)
r1 = q("SELECT * FROM pie_events")[0]
tok = r1["token"]
slots = [s["id"] for s in q("SELECT id FROM pie_slots ORDER BY slot_date")]


def order(name, pie, token=None, **extra):
    g = A.app.test_client()
    data = {"choice": "pickup", "pie_type": pie, "name": name, "email": name.split()[0].lower() + "@example.test", "phone": "9135550100"}
    data.update(extra)
    with contextlib.redirect_stdout(io.StringIO()):
        return g.post(f"/pies/r/{token or tok}", data=data, follow_redirects=True)


order("Ann Apple", "Apple", fulfillment="pickup", slot_id=str(slots[0]))
order("Ben Apple", "Apple", fulfillment="pickup", slot_id=str(slots[0]))
order("Cat Pecan", "Pecan", fulfillment="pickup", slot_id=str(slots[1]))
order("Dan Deliver", "Pumpkin", fulfillment="delivery", delivery_address="9 Elm Street, Lenexa, KS")
order("Hal Home", "Pecan", fulfillment="home", want_date="2030-12-22", want_time="14:30")
order("Nora No", "Apple", choice="no")

h = c.get(f"/pies/{r1['id']}/handout").get_data(as_text=True)
ok("handout day" in h and "12 Oak Lane, Shawnee" in h and "Main Street Office" in h, "the handout sheet groups people by pickup time and place")
ok("Deliveries" in h and "Elm Street" in h and "at the house" in h and "2:30" in h, "deliveries and home pickups have their own sections")
ok("<b>5</b><span>pies in all" in h and "<b>5</b><span>people" in h, "it totals the pies and the people")
ok("2 Apple" in h and "2 Pecan" in h and "1 Pumpkin" in h, "it says how many of each pie to bake")
ok("Nora No" not in h, "people who said no are not on the handout sheet")
ok(h.find("Dec 20") < h.find("Dec 21") < h.find("Deliveries"), "pickup days come in order, then home pickups and deliveries")

# a day filter keeps that day's pickups, and deliveries (no set day)
hd = c.get(f"/pies/{r1['id']}/handout?day=2030-12-21").get_data(as_text=True)
ok("Main Street Office" in hd and "12 Oak Lane, Shawnee" not in hd and "Deliveries" in hd, "choosing a day shows that day's pickups and the deliveries")

# ticking someone off from the sheet sends the host back to the sheet
ann = q("SELECT id FROM pie_responses WHERE name='Ann Apple'")[0]["id"]
with contextlib.redirect_stdout(io.StringIO()):
    r = c.post(f"/pies/{r1['id']}/picked-up/{ann}", data={"next": f"/pies/{r1['id']}/handout?all=1"}, headers=H)
ok(r.status_code == 302 and r.headers["Location"].endswith(f"/pies/{r1['id']}/handout?all=1"), "ticking a person off returns to the handout sheet")
ok(q("SELECT picked_up FROM pie_responses WHERE id=?", ann)[0]["picked_up"] == 1, "and marks them handed out")
ben = q("SELECT id FROM pie_responses WHERE name='Ben Apple'")[0]["id"]
with contextlib.redirect_stdout(io.StringIO()):
    r = c.post(f"/pies/{r1['id']}/picked-up/{ben}", data={"next": "https://evil.example/x"}, headers=H)
ok("evil.example" not in r.headers.get("Location", ""), "a made-up return address is ignored")
h2 = c.get(f"/pies/{r1['id']}/handout").get_data(as_text=True)
ok("<b>2 of 5</b>" in h2, "the sheet shows how many have been handed out so far")

# round 2: same link, its own orders, and the sheet can put both together
with contextlib.redirect_stdout(io.StringIO()):
    c.post(f"/pies/{r1['id']}/new-round", headers=H)
r2 = q("SELECT * FROM pie_events WHERE id != ?", r1["id"])[0]
s2 = [s["id"] for s in q("SELECT id FROM pie_slots WHERE event_id=? ORDER BY slot_date", r2["id"])]
order("Rae Round2", "Pumpkin", token=r2["token"], fulfillment="pickup", slot_id=str(s2[0]))
order("Dee Deliver2", "Apple", token=r2["token"], fulfillment="delivery", delivery_address="3 Pine Court, Olathe, KS")
only2 = c.get(f"/pies/{r2['id']}/handout?all=0").get_data(as_text=True)
ok("Rae Round2" in only2 and "Ann Apple" not in only2, "one round alone shows only that round")
both = c.get(f"/pies/{r2['id']}/handout").get_data(as_text=True)
ok("Rae Round2" in both and "Ann Apple" in both and "Round 1" in both and "Round 2" in both, "all rounds together puts everyone on one sheet, marked by round")
ok("<b>7</b><span>pies in all" in both, "the pie total adds up across rounds")
ok("All rounds together" in both and "only" in both, "the sheet offers both views")
r1only = c.get(f"/pies/{r1['id']}/handout?all=0").get_data(as_text=True)
ok("Rae Round2" not in r1only, "round 1 alone does not show round 2")

# the event page links to it
d = c.get(f"/pies/{r2['id']}").get_data(as_text=True)
ok("Handout day sheet" in d and "Download Excel, all rounds" in d, "the event page links to the sheet and the all-rounds Excel")

# Excel: the combined workbook has a handout sheet
from openpyxl import load_workbook
x = c.get(f"/pies/{r2['id']}/export.xlsx?all=1")
wb = load_workbook(io.BytesIO(x.data))
ok("Handout day" in wb.sheetnames and "Responses" in wb.sheetnames, "the Excel file has a Handout day sheet")
resp = [[cell.value for cell in row] for row in wb["Responses"].iter_rows()]
ok(resp[0][0] == "Round" and sum(1 for row in resp[1:] if row[1] and row[1] != "Total pies") >= 7, "all rounds are in the Responses sheet, with a Round column")
hand = "\n".join(str(cell.value) for row in wb["Handout day"].iter_rows() for cell in row if cell.value)
ok("Rae Round2" in hand and "Ann Apple" in hand and "Elm Street" in hand, "the handout sheet in Excel lists everyone")
x1 = c.get(f"/pies/{r1['id']}/export.xlsx")
wb1 = load_workbook(io.BytesIO(x1.data))
ok(wb1["Responses"]["A1"].value == "Name", "a single-round download is unchanged")

# privacy: another host cannot open this sheet
cb = A.app.test_client()
with cb.session_transaction() as s: s["user_id"] = bob; s["role"] = "agent"
ok(cb.get(f"/pies/{r1['id']}/handout").status_code in (302, 404), "another host cannot see the handout sheet")
ok(A.app.test_client().get(f"/pies/{r1['id']}/handout").status_code in (302, 404), "a signed-out visitor cannot either")

# an event with no orders says so kindly
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/pies/new", data={**form, "title": "Empty event"})
e3 = q("SELECT id FROM pie_events WHERE title='Empty event'")[0]["id"]
ok("No pie orders to hand out yet" in c.get(f"/pies/{e3}/handout").get_data(as_text=True), "with no orders it explains what will appear")

# the printed flyer says delivery and home pickup are available (without giving out the home address)
fl = c.get(f"/pies/{r1['id']}/flyer").get_data(as_text=True)
ok("Also available" in fl and "Delivery, or pickup at" in fl and "99 Home Road" not in fl, "the flyer mentions delivery and home pickup without the home address")
