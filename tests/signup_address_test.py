import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
H = {"Origin": "http://localhost", "Referer": "http://localhost/"}
A.app.config["TESTING"] = True

def signup(email, role, **extra):
    c = A.app.test_client()
    c.get(f"/signup?role={role}")
    d = {"name": "Pat Doe", "email": email, "password": "longenough1", "role": role}
    d.update(extra)
    with contextlib.redirect_stdout(io.StringIO()):
        c.post("/signup", data=d, headers=H)
    u = D.get_user_by_email(email)
    return u["id"] if u else None

ok('name="home_address"' in A.app.test_client().get("/signup?role=homeowner").get_data(as_text=True), "the homeowner sign-up asks for the street address")
ok('name="home_address"' not in A.app.test_client().get("/signup?role=agent").get_data(as_text=True), "agents are not asked for one")
uid = signup("addr1@example.com", "homeowner", home_address="123 Maple Street, Shawnee, KS 66203")
p = D.get_primary_property(uid) if uid else None
ok(p and p["address"] == "123 Maple Street, Shawnee, KS 66203", "the address (zip code included) becomes their primary home")
uid2 = signup("addr2@example.com", "homeowner")
ok(uid2 and not D.get_primary_property(uid2), "leaving it blank still signs up with no placeholder home")
uid3 = signup("addr3@example.com", "homeowner", home_address="http://spam.example/buy")
ok(uid3 and not D.get_primary_property(uid3), "a link in the address field is ignored")
