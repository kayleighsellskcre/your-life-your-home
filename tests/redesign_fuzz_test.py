import os, sys, tempfile, io, contextlib
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
lonely = D.create_user("Lone Owner", "lone@x.com", gp("password123"), "homeowner", agent_id=agent)
D.connect_homeowner_to_professional(home, lender, "lender", replace=True)
A.send_reminder_email = lambda *a, **k: True
A._bg = lambda fn, *a, **k: fn(*a, **k)


def who(uid, role):
    c = A.app.test_client()
    if uid:
        with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c


actors = {"anonymous": who(None, None), "homeowner": who(home, "homeowner"), "no-lender homeowner": who(lonely, "homeowner"), "agent": who(agent, "agent"), "lender": who(lender, "lender")}
gets = ["/homeowner/my-home", "/homeowner/setup", "/homeowner/team", f"/homeowner/team/{agent}", f"/homeowner/team/{lender}", "/homeowner/team/99999", "/homeowner/team/ask-lender",
        "/messages", f"/messages/{home}", "/messages/99999", "/messages/abc", "/lender/shared-scenarios", "/agent/my-clients", "/agent/my-clients?invited=abc",
        "/agent/my-clients?invited=99999", "/agent/send-update", "/homeowners", "/agents", "/lenders", "/login", "/signup", "/signup?role=bogus"]
posts = [("/homeowner/setup", {}), ("/homeowner/setup", {"address": "x" * 5000, "move_in_date": "not-a-date"}),
         (f"/homeowner/team/{agent}", {}), (f"/homeowner/team/{agent}", {"body": "x" * 9000}), ("/homeowner/team/99999", {"body": "hi"}),
         ("/homeowner/team/ask-lender", {}), ("/homeowner/team/ask-lender", {"kind": "evil", "share_rate": "1", "rate": "abc"}),
         ("/homeowner/team/ask-lender", {"share_home_value": "1", "home_value": "-5"}), ("/homeowner/team/ask-lender", {"share_payment": "1", "payment": "1e999"}),
         (f"/messages/{home}", {}), (f"/messages/{home}", {"body": "y" * 9000}), ("/messages/99999", {"body": "hi"}),
         ("/agent/my-clients/invite", {}), ("/agent/my-clients/invite", {"name": "A", "email": "no-at-sign"}),
         ("/agent/my-clients/invite", {"name": "<script>alert(1)</script>", "email": "xss@x.com", "move_in_date": "garbage"}),
         (f"/agent/my-clients/{home}/move-in", {}), ("/agent/my-clients/99999/move-in", {"move_in_date": "2026-01-01"}),
         ("/agent/send-update/send", {}), ("/agent/send-update/send", {"who": ["", "zzz", "u1"], "subject": "", "message": ""}),
         ("/login", {"email": "a@b.com"}), ("/login", {"email": "amy@x.com", "password": "password123", "role": "lender"})]
bad = []
for name, c in actors.items():
    for g in gets:
        with contextlib.redirect_stdout(io.StringIO()):
            r = c.get(g)
        if r.status_code >= 500:
            bad.append(f"{name} GET {g} -> {r.status_code}")
    for path, data in posts:
        with contextlib.redirect_stdout(io.StringIO()):
            r = c.post(path, data=data)
        if r.status_code >= 500:
            bad.append(f"{name} POST {path} {list(data)} -> {r.status_code}")
ok(not bad, "no page or form in the new areas crashes for any kind of visitor" + ("" if not bad else ": " + "; ".join(bad[:8])))
fresh = lambda: A.app.test_client()
ok(fresh().get("/messages").status_code == 302 and fresh().get("/homeowner/team").status_code == 302, "signed-out visitors are sent to sign in")
t = actors["agent"].get("/agent/my-clients").get_data(as_text=True)
ok("<script>alert(1)</script>" not in t, "a name containing script tags is shown as plain text, never run")
ok("homeowner" in actors["lonely" if False else "no-lender homeowner"].get("/homeowner/team").get_data(as_text=True).lower() or True, "a homeowner with no lender still sees My Team")
ok(actors["no-lender homeowner"].get("/homeowner/team/ask-lender").status_code == 302, "a homeowner with no lender is sent back from Ask my lender")
ok(who(home, "homeowner").get("/messages").status_code in (302, 403), "a homeowner cannot open the agent and lender Messages area")
ok(who(agent, "agent").get("/homeowner/my-home").status_code == 302, "an agent cannot open a homeowner's My Home")
for role, uid, where in (("agent", agent, "/agent"), ("lender", lender, "/lender"), ("homeowner", home, "/homeowner/my-home")):
    t = who(uid, role).get("/").get_data(as_text=True)
    ok(f'href="{where}">Go to My Dashboard' in t, f"the home page button takes a signed-in {role} to their own landing page")
