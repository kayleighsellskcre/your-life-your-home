import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

amy = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
other = D.create_user("Other Agent", "oa@x.com", gp("password123"), "agent")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = amy; s["role"] = "agent"
co = A.app.test_client()
with co.session_transaction() as s: s["user_id"] = other; s["role"] = "agent"


def q(sql, *a):
    conn = D.get_connection()
    try:
        return conn.execute(sql, a).fetchall()
    finally:
        conn.close()


form = {"title": "Holiday pies", "pie_types": "Apple\nPecan", "order_by": "2099-01-01", "slot_date": ["2030-12-20"], "slot_start": ["10:00"],
        "slot_end": ["12:00"], "slot_location": ["My office"], "slot_capacity": [""], "slot_id": [""]}
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/pies/new", data=form)
r1 = q("SELECT * FROM pie_events")[0]
tok = r1["token"]


def order(name, email, pie="Apple", slot="1"):
    g = A.app.test_client()
    with contextlib.redirect_stdout(io.StringIO()):
        return g.post(f"/pies/r/{tok}", data={"choice": "pickup", "slot_id": slot, "pie_type": pie, "quantity": "1", "name": name, "email": email, "phone": "9135550100", "fulfillment": "pickup"}, follow_redirects=True)


order("Gina Guest", "gina@x.com")
ok(len(q("SELECT * FROM pie_responses WHERE event_id = ?", r1["id"])) == 1, "a first-round order is saved")

# round 1 closes, round 2 is set up
with contextlib.redirect_stdout(io.StringIO()):
    c.post(f"/pies/{r1['id']}/edit", data={**form, "order_by": "2020-01-01", "closed_message": "Round one is full."})
    r = c.post(f"/pies/{r1['id']}/new-round", follow_redirects=True)
r2 = q("SELECT * FROM pie_events WHERE id != ?", r1["id"])[0]
ok(r2["round_no"] == 2 and r2["title"] == "Holiday pies - Round 2" and r2["is_active"] == 1 and r2["token"] != tok and r2["pie_types"] == r1["pie_types"] and not r2["order_by"], "round 2 is created open, with the same pies and a blank reply-by date")
ok(q("SELECT next_id FROM pie_events WHERE id = ?", r1["id"])[0]["next_id"] == r2["id"], "round 1 points to round 2")
ok([(s["location"], s["start_time"]) for s in q("SELECT * FROM pie_slots WHERE event_id = ?", r2["id"])] == [("My office", "10:00")], "round 2 copies the pickup times from round 1")
t = A.app.test_client().get(f"/pies/r/{tok}").get_data(as_text=True)
ok("Round 2" in t and "pieform" in t and "Round one is full." not in t, "the same link and QR code switch to round 2 right away")
ok(c.post(f"/pies/{r1['id']}/new-round").status_code == 302 and len(q("SELECT id FROM pie_events")) == 2, "pressing start again does not make a third round")

s2 = q("SELECT id FROM pie_slots WHERE event_id = ?", r2["id"])[0]["id"]
# the same person orders again in round 2: it must not overwrite her round 1 order
order("Gina Guest", "gina@x.com", pie="Pecan", slot=str(s2))
rows1 = q("SELECT * FROM pie_responses WHERE event_id = ?", r1["id"])
rows2 = q("SELECT * FROM pie_responses WHERE event_id = ?", r2["id"])
ok(len(rows1) == 1 and rows1[0]["pie_type"] == "Apple", "a round 2 order does not change the same person's round 1 order")
ok(len(rows2) == 1 and rows2[0]["pie_type"] == "Pecan", "the round 2 order lands in round 2's own list")
t1, t2 = c.get(f"/pies/{r1['id']}").get_data(as_text=True), c.get(f"/pies/{r2['id']}").get_data(as_text=True)
ok("Gina Guest" in t1 and "Gina Guest" in t2 and "Round 2" in t2 and "See the earlier round" in t2, "each round has its own page and links to the other")
ok(c.get(f"/pies/{r1['id']}/export.xlsx").status_code == 200 and c.get(f"/pies/{r2['id']}/export.xlsx").status_code == 200, "each round exports on its own")
ok(f"/pies/r/{tok}" in t2 and r2["token"] not in t2, "round 2's page shows the original link and QR code, not a new one")
# her first-round email link still works (and is closed)
old_edit = rows1[0]["edit_token"]
t = A.app.test_client().get(f"/pies/r/{tok}/mine/{old_edit}").get_data(as_text=True)
ok("Round one is full." in t, "a first-round confirmation link still opens round 1")

# privacy and cleanup
ok(co.post(f"/pies/{r1['id']}/new-round").status_code in (302, 403, 404) and len(q("SELECT id FROM pie_events")) == 2, "another host cannot start a round on your event")
with contextlib.redirect_stdout(io.StringIO()):
    c.post(f"/pies/{r2['id']}/delete")
ok(q("SELECT next_id FROM pie_events WHERE id = ?", r1["id"])[0]["next_id"] is None, "deleting round 2 unlinks it from round 1")
ok("Round one is full." in A.app.test_client().get(f"/pies/r/{tok}").get_data(as_text=True), "the link then shows round 1 again")
