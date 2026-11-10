import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ["YLH_ADMIN_EMAILS"] = "boss@x.com"
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)


def client(uid, role):
    cl = A.app.test_client()
    with cl.session_transaction() as s: s["user_id"] = uid; s["role"] = role
    return cl


boss = D.create_user("Boss", "boss@x.com", gp("password123"), "agent")
amy = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
conn = D.get_connection()
tier = lambda uid: conn.execute("SELECT subscription_tier FROM users WHERE id=?", (uid,)).fetchone()[0]
ca, cb = client(amy, "agent"), client(boss, "agent")
before = tier(amy)

ca.post("/agent/admin/toggle-premium", data={"action": "upgrade"})
ok(tier(amy) == before, "an ordinary agent cannot give themselves premium (tier is still %s)" % tier(amy))
r = ca.get("/agent/admin/settings"); ok(r.status_code == 302, "an ordinary agent cannot open the premium testing page")
r = ca.get("/agent/admin/toggle-premium"); ok(r.status_code == 302, "or the toggle page")
cb.post("/agent/admin/toggle-premium", data={"action": "upgrade"})
ok(tier(boss) == "premium", "the site admin can still use the premium testing tools")
ok(cb.get("/agent/admin/settings").status_code == 200, "and open the testing page")

ok(ca.get("/admin/promo-codes").status_code == 302, "an ordinary agent cannot see promo codes")
ok(cb.get("/admin/promo-codes").status_code == 200, "the site admin can see promo codes")
t = cb.get("/admin").get_data(as_text=True)
ok('href="/admin/roles"' not in t and 'href="/admin/settings"' not in t, "the admin dashboard has no buttons that lead to missing pages")
ok("/admin/promo-codes" in t, "the admin dashboard links to promo codes")
ok(A.app.test_client().post("/agent/admin/toggle-premium", data={"action": "upgrade"}).status_code == 302, "signed-out visitors are sent to login")
