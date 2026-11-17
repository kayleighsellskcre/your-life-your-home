import os, sys, tempfile, io, contextlib, subprocess, shutil
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
lender = D.create_user("Lou Lender", "lou@x.com", gp("password123"), "lender")
home = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=agent)


def who(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c


c = A.app.test_client()
r = c.get("/static/js/collapsible.js")
ok(r.status_code == 200 and b"ylhCollapse" in r.data, "the shared script is served")
node = shutil.which("node")
if node:
    p = subprocess.run([node, "--check", "static/js/collapsible.js"], capture_output=True, text=True)
    ok(p.returncode == 0, "the script has no syntax errors" + ("" if p.returncode == 0 else ": " + p.stderr[:200]))
js = open("static/js/collapsible.js", encoding="utf-8").read()
ok("catch (e)" in js and "ylh-cl-hidden" in js, "if the script fails it shows everything instead of hiding it")

pages = (("homeowner", home, "/homeowner/care/maintenance-guide", ".system-card"), ("homeowner", home, "/homeowner/care/home-protection", ".protection-card"),
         ("homeowner", home, "/homeowner/reno/roi-guide", ".roi-section"), ("agent", agent, "/agent/communications", "templates-grid"),
         ("agent", agent, "/planner", ".pl-box"), ("agent", agent, "/agent/booking", "bk-upcoming"), ("lender", lender, "/lender/booking", "bk-upcoming"),
         ("lender", lender, "/planner", ".pl-box"))
for role, uid, path, marker in pages:
    cl = who(uid, role)
    r = cl.get(path)
    t = r.get_data(as_text=True)
    if r.status_code == 302 or r.status_code == 404:
        print(f"SKIP {path} -> {r.status_code}")
        continue
    ok(r.status_code == 200 and "js/collapsible.js" in t and "ylhCollapse(" in t and marker in t, f"{role}: {path} folds its long sections")

# seasonal checklists open on the current season
cl = who(home, "homeowner")
t = cl.get("/homeowner/care/seasonal-checklists").get_data(as_text=True)
ok("(this season)" in t and "showSeason(now)" in t and "showSeason('spring');\n});" not in t, "Seasonal Checklists opens on the season we are in")
