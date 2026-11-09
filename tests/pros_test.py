import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
agent = D.create_user("Agent Amy", "amy@x.com", gp("password123"), "agent")
other = D.create_user("Agent Bob", "bob@x.com", gp("password123"), "agent")
tok = D.create_referral_link(agent_id=agent)
ho = D.create_user("Hannah H", "h@x.com", gp("password123"), "homeowner", agent_id=agent)
D.create_client_relationship(ho, agent, "agent", tok)
D.create_trusted_vendor(agent_id=agent, name="Best Plumbing", category="Plumber", contact_name="Pat", phone="555-111-2222", email="p@x.com", website="bestplumb.com", address=None, notes="Fast and fair")
D.create_trusted_vendor(agent_id=other, name="Secret Roofing", category="Roofer", contact_name=None, phone="555", email=None, website=None, address=None, notes=None)
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ho; s["role"] = "homeowner"
t = c.get("/homeowner/pros").get_data(as_text=True)
ok("Best Plumbing" in t and "tel:555-111-2222" in t and "https://bestplumb.com" in t, "homeowner sees their agent's vendors")
ok("Secret Roofing" not in t, "other agents' vendors are hidden")
lone = D.create_user("Lone", "l@x.com", gp("password123"), "homeowner", agent_id=other)
c2 = A.app.test_client()
with c2.session_transaction() as s: s["user_id"] = lone; s["role"] = "homeowner"
r = c2.get("/homeowner/pros"); ok(r.status_code == 200 and "Best Plumbing" not in r.get_data(as_text=True), "unconnected homeowner gets a friendly empty page")
ok(b"Trusted Pros" in c.get("/homeowner").data, "menu links to it")
