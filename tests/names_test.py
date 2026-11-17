"""Every menu label must be the exact title and heading of the page it opens, so people always know where they are."""
import os, sys, tempfile, io, contextlib, re, html
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
D.connect_homeowner_to_professional(home, lender, "lender", replace=True)
D.add_property(home, "10 First St, Shawnee, KS 66226", 250000.0, "primary")
text = lambda m: html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", m.group(1)))).strip() if m else ""
GREETING = "Dashboard"   # its heading is a greeting: "Good morning, <name>"
for role, uid, first in (("agent", agent, "/agent/my-clients"), ("lender", lender, "/lender/clients"), ("homeowner", home, "/homeowner/my-home")):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "Pat Example"
    t = c.get(first).get_data(as_text=True)
    menu = t[t.index('id="ylhHamMenu"'):]
    menu = menu[:menu.index("Sign Out")]
    items = {}
    for href, label in re.findall(r'<a class="ylh-ham-item" href="([^"]+)">(.*?)</a>', menu, flags=re.S):
        items.setdefault(href, html.unescape(re.sub(r"<[^>]+>", "", label)).strip())
    ok(len(items) >= 15, f"found the {role} menu items ({len(items)})")
    for href, label in items.items():
        with contextlib.redirect_stdout(io.StringIO()):
            body = c.get(href).get_data(as_text=True)
        title = text(re.search(r"<title>(.*?)</title>", body, flags=re.S)).split(" • ")[0].strip()
        h1 = text(re.search(r"<h1[^>]*>(.*?)</h1>", body, flags=re.S))
        if label == GREETING:
            ok(title == "Dashboard" and h1.startswith("Good ") and h1.endswith({"agent": "Amy", "lender": "Lou"}[role]), f"{role}: Dashboard has the title Dashboard and a greeting for the person")
            continue
        ok(title == label and h1 == label, f"{role}: '{label}' opens a page titled '{title}' with the heading '{h1}'")
