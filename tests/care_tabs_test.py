import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
ho = D.create_user("Care Owner", "care@x.com", gp("password123"), "homeowner", agent_id=ag)
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ho; s["role"] = "homeowner"
pages = ("/homeowner/care/maintenance-guide", "/homeowner/care/seasonal-checklists", "/homeowner/care/home-protection", "/homeowner/care/energy-savings")
for u in pages:
    r = c.get(u)
    t = r.get_data(as_text=True)
    ok(r.status_code == 200 and 'class="care-tabs"' in t and t.count('href="/homeowner/care/') >= 4, f"{u} shows the shared Care tabs")
t = c.get("/homeowner/my-home").get_data(as_text=True)
menu = t[t.index('id="ylhHamMenu"'):]
ok(menu.count(">Care Guide<") == 1 and ">Seasonal Checklists<" not in menu and ">Energy Savings<" not in menu, "the menu has one Care Guide entry instead of four care pages")
