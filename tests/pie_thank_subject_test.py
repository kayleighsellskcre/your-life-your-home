import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
import pies as P
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

amy = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = amy; s["role"] = "agent"
base = {"title": "Holiday pies", "pie_types": "Apple\nPecan", "order_by": "2099-01-01", "slot_date": ["2099-12-20"],
        "slot_start": ["10:00"], "slot_end": ["12:00"], "slot_location": ["My office"], "slot_capacity": [""], "slot_id": [""],
        "thank_message": "Happy Thanksgiving!"}
with contextlib.redirect_stdout(io.StringIO()):
    c.post("/pies/new", data=base)
conn = D.get_connection()
ev = conn.execute("SELECT id FROM pie_events").fetchone()
conn.execute("INSERT INTO pie_responses (event_id, name, email, choice) VALUES (?,?,?,?)", (ev["id"], "Jess Smith", "jess@x.com", "pickup"))
conn.commit()
conn.close()

sent = []
P._H["send_email"] = lambda to, subject, body, *a, **k: sent.append((to, subject, body)) or True


def reset():
    sent.clear()
    conn = D.get_connection()
    conn.execute("UPDATE pie_responses SET thanked=0")
    conn.commit()
    conn.close()


ok('name="thank_subject"' in c.get(f"/pies/{ev['id']}/edit").get_data(as_text=True), "the edit form has a subject line box")
P.send_thank_yous(event_id=ev["id"])
ok(len(sent) == 1 and sent[0][1].startswith("Thank you from"), "with no subject set, the usual 'Thank you from' subject is used")

with contextlib.redirect_stdout(io.StringIO()):
    c.post(f"/pies/{ev['id']}/edit", data={**base, "thank_subject": "Happy Thanksgiving 🥧"})
ok("Happy Thanksgiving 🥧" in c.get(f"/pies/{ev['id']}/edit").get_data(as_text=True), "the saved subject shows in the edit form")
reset()
P.send_thank_yous(event_id=ev["id"])
ok(len(sent) == 1 and sent[0][1] == "Happy Thanksgiving 🥧", "the thank-you email uses the custom subject")
ok("Hi Jess" in sent[0][2] and "Happy Thanksgiving!" in sent[0][2], "the body is unchanged")

with contextlib.redirect_stdout(io.StringIO()):
    c.post(f"/pies/{ev['id']}/edit", data={**base, "thank_subject": ""})
reset()
P.send_thank_yous(event_id=ev["id"])
ok(sent and sent[0][1].startswith("Thank you from"), "clearing the subject goes back to the usual one")

with contextlib.redirect_stdout(io.StringIO()):
    c.post(f"/pies/{ev['id']}/edit", data={**base, "thank_subject": "Happy Thanksgiving 🥧"})
    c.post(f"/pies/{ev['id']}/new-round")
conn = D.get_connection()
nxt = conn.execute("SELECT thank_subject FROM pie_events WHERE id != ? ORDER BY id DESC", (ev["id"],)).fetchone()
conn.close()
ok(nxt is not None and nxt["thank_subject"] == "Happy Thanksgiving 🥧", "a new round keeps the subject line")
