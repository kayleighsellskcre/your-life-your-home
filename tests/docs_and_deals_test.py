import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, transaction_helpers as T
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)


def client(uid, role):
    cl = A.app.test_client()
    with cl.session_transaction() as s: s["user_id"] = uid; s["role"] = role
    return cl


ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
a = D.create_user("Alice Owner", "alice@x.com", gp("password123"), "homeowner", agent_id=ag)
b = D.create_user("Bob Owner", "bob@x.com", gp("password123"), "homeowner", agent_id=ag)
ca, cb = client(a, "homeowner"), client(b, "homeowner")
conn = D.get_connection()


def docs(uid):
    return [dict(r) for r in conn.execute("SELECT * FROM homeowner_documents WHERE user_id=?", (uid,)).fetchall()]


# upload one document each (local storage)
with contextlib.redirect_stdout(io.StringIO()):
    ca.post("/homeowner/upload-documents", data={"title": "Alice deed", "category": "deed", "file": (io.BytesIO(b"alice-v1"), "alice_deed.pdf")}, content_type="multipart/form-data")
    cb.post("/homeowner/upload-documents", data={"title": "Bob deed", "category": "deed", "file": (io.BytesIO(b"bob-v1"), "bob_deed.pdf")}, content_type="multipart/form-data")
da, db_ = docs(a), docs(b)
ok(len(da) == 1 and len(db_) == 1, "each homeowner has a document")
aid, bid = da[0]["id"], db_[0]["id"]

# another homeowner must not delete or overwrite it
with contextlib.redirect_stdout(io.StringIO()):
    cb.post("/homeowner/upload-documents", data={"delete_id": str(aid)})
ok(len(docs(a)) == 1, "one homeowner cannot delete another's document")
with contextlib.redirect_stdout(io.StringIO()):
    cb.post("/homeowner/upload-documents", data={"reattach_id": str(aid), "file": (io.BytesIO(b"evil"), "evil.pdf")}, content_type="multipart/form-data")
ok(docs(a)[0]["file_path"] == da[0]["file_path"], "one homeowner cannot overwrite another's document")

# viewing
r = ca.get(f"/homeowner/documents/{aid}/view")
ok(r.status_code == 200 and r.data == b"alice-v1", "a homeowner can open their own uploaded file")
ok(cb.get(f"/homeowner/documents/{aid}/view", follow_redirects=False).status_code == 302, "another homeowner cannot open it")

# replace page
t = ca.get(f"/homeowner/documents/{aid}/replace").get_data(as_text=True)
ok("Alice deed" in t, "replace page names the document")
with contextlib.redirect_stdout(io.StringIO()):
    r = ca.post(f"/homeowner/documents/{aid}/replace", data={"file": (io.BytesIO(b"alice-v2"), "alice_deed_v2.pdf")}, content_type="multipart/form-data")
ok(r.status_code == 302, "replacing a document works instead of crashing (got %s)" % r.status_code)
ok(ca.get(f"/homeowner/documents/{aid}/view").data == b"alice-v2", "the replaced file is what opens")
with contextlib.redirect_stdout(io.StringIO()):
    r = cb.post(f"/homeowner/documents/{aid}/replace", data={"file": (io.BytesIO(b"evil"), "evil.pdf")}, content_type="multipart/form-data")
ok(ca.get(f"/homeowner/documents/{aid}/view").data == b"alice-v2", "another homeowner cannot replace it")

# own delete still works
with contextlib.redirect_stdout(io.StringIO()):
    ca.post("/homeowner/upload-documents", data={"delete_id": str(aid)})
ok(docs(a) == [] and len(docs(b)) == 1, "a homeowner can delete their own document, and only theirs")

# deals: stage change and delete on a brand-new database
tx = T.create_transaction(ag, "1 Main St, Olathe, KS", "Cara Client", "buyer")
cag = client(ag, "agent")
with contextlib.redirect_stdout(io.StringIO()):
    r = cag.post(f"/agent/transactions/{tx}/change-stage", data={"new_stage": "under_contract"})
stage = conn.execute("SELECT current_stage FROM transactions WHERE id=?", (tx,)).fetchone()[0]
ok(stage == "under_contract", "changing a deal's stage works on a fresh database (stage is %s)" % stage)
with contextlib.redirect_stdout(io.StringIO()):
    r = cag.post(f"/agent/transactions/{tx}/delete")
ok(conn.execute("SELECT COUNT(*) FROM transactions WHERE id=?", (tx,)).fetchone()[0] == 0, "deleting a deal works on a fresh database")
