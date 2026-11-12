import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

amy = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = amy; s["role"] = "agent"
base = {"title": "Holiday pies", "pie_types": "Apple\nPecan", "order_by": "2020-01-01", "slot_date": ["2030-12-20"], "slot_start": ["10:00"], "slot_end": ["12:00"],
        "slot_location": ["My office"], "slot_capacity": [""], "slot_id": [""]}
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/pies/new", data=base)
conn = D.get_connection()
ev = conn.execute("SELECT id, token FROM pie_events").fetchone()
conn.close()
pub = lambda: A.app.test_client().get(f"/pies/r/{ev['token']}").get_data(as_text=True)
ok("closed and orders are locked in" in pub(), "after the reply-by date guests see the standard closed message")
with contextlib.redirect_stdout(io.StringIO()):
    c.post(f"/pies/{ev['id']}/edit", data={**base, "closed_message": "First round is full! A second round opens December 1. Check back with this same link."})
t = pub()
ok("A second round opens December 1" in t and "locked in" not in t, "a custom closed message replaces it")
ok("A second round opens December 1" in c.get(f"/pies/{ev['id']}/edit").get_data(as_text=True), "the custom message shows in the edit form")
with contextlib.redirect_stdout(io.StringIO()):
    c.post(f"/pies/{ev['id']}/edit", data={**base, "order_by": "2099-01-01", "closed_message": "First round is full!"})
t = pub()
ok("Holiday pies" in t and "First round is full" not in t and "pieform" in t, "moving the reply-by date later reopens the same link for a second round")
ok(A.app.test_client().get(f"/pies/r/{ev['token']}").status_code == 200, "the link and QR code stay the same")
