import os, sys, tempfile, io, contextlib, json, urllib.request, urllib.error
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ["YLH_ADMIN_EMAILS"] = "boss@x.com"
for k in ("RESEND_API_KEY", "BREVO_API_KEY", "MAIL_FROM"):
    os.environ.pop(k, None)
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, email_check as EC
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)


def client(uid, role="agent"):
    cl = A.app.test_client()
    with cl.session_transaction() as s: s["user_id"] = uid; s["role"] = role
    return cl


boss = D.create_user("Boss", "boss@x.com", gp("password123"), "agent")
amy = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
cb, ca = client(boss), client(amy)

ok(ca.get("/admin/email-check").status_code == 302 and ca.post("/admin/email-check/send").status_code == 302, "an ordinary agent cannot open or use the email check")
ok(A.app.test_client().get("/admin/email-check").status_code == 302, "signed-out visitors are sent to login")
t = cb.get("/admin/email-check").get_data(as_text=True)
ok("None set up" in t and "No email service is set up" in t, "with nothing configured the page says so plainly")

# configured as Brevo
os.environ["BREVO_API_KEY"] = "SECRETKEY123"; os.environ["MAIL_FROM"] = "Your Life <hello@itsyourlifeyourhome.com>"
calls = []
def fake(senders, domains=None, err=None):
    def g(url, key, timeout=10):
        calls.append(url)
        if err: raise err
        return {"senders": senders} if url.endswith("/senders") else {"domains": domains or []}
    return g
EC._get_json = fake([{"email": "hello@itsyourlifeyourhome.com", "active": True}])
t = cb.get("/admin/email-check").get_data(as_text=True)
ok("Brevo" in t and "hello@itsyourlifeyourhome.com" in t and "is a verified sender in Brevo" in t, "a verified Brevo sender shows as ready")
ok("SECRETKEY123" not in t, "the API key is never shown on the page")
EC._get_json = fake([{"email": "hello@itsyourlifeyourhome.com", "active": False}])
ok("not verified yet" in cb.get("/admin/email-check").get_data(as_text=True), "an unverified sender is called out with what to do")
EC._get_json = fake([], [{"domain_name": "itsyourlifeyourhome.com", "authenticated": True}])
ok("authenticated domain" in cb.get("/admin/email-check").get_data(as_text=True), "an authenticated domain counts as verified")
EC._get_json = fake([], [])
ok("not a verified sender" in cb.get("/admin/email-check").get_data(as_text=True), "an address Brevo does not know is called out")
EC._get_json = fake([], err=urllib.error.HTTPError("u", 401, "no", {}, None))
ok("rejected the API key" in cb.get("/admin/email-check").get_data(as_text=True), "a rejected API key is called out")
EC._get_json = fake([], err=OSError("down"))
ok(cb.get("/admin/email-check").status_code == 200, "if Brevo cannot be reached the page still loads")
EC._get_json = fake([{"email": "hello@itsyourlifeyourhome.com", "active": True}])

# the test send goes only to the admin's own address
sent = []
A.send_reminder_email = lambda to, subj, body, **kw: (sent.append(to) or True)
r = cb.post("/admin/email-check/send", data={"to": "someone-else@x.com"}, follow_redirects=True)
ok(sent == ["boss@x.com"] and "Sent. Check the inbox for boss@x.com" in r.get_data(as_text=True), "the test goes only to the signed-in admin, never to an address from the form")

# a real failure path: Brevo refuses the sender, and we show Brevo's own words
def boom(req, timeout=15):
    raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(b'{"code":"invalid_parameter","message":"Sender is not valid"}'))
# put the real sending functions back (earlier lines replaced one with a stand-in)
import ast
tree = ast.parse(open("app.py", encoding="utf-8").read())
for n in tree.body:
    if isinstance(n, ast.FunctionDef) and n.name in ("send_reminder_email", "_send_via_brevo", "_send_via_resend", "_from_address", "_reply_to_address", "_clean_header"):
        exec(compile(ast.Module([n], []), "app.py", "exec"), A.__dict__)
A.send_reminder_email = A.__dict__["send_reminder_email"]
orig = urllib.request.urlopen
urllib.request.urlopen = boom
try:
    with contextlib.redirect_stdout(io.StringIO()):
        r = cb.post("/admin/email-check/send", follow_redirects=True)
finally:
    urllib.request.urlopen = orig
t = r.get_data(as_text=True)
ok("did not send" in t and "Sender is not valid" in t, "when Brevo refuses, the page shows Brevo's actual reason")
for k in ("BREVO_API_KEY", "MAIL_FROM"):
    os.environ.pop(k, None)
with contextlib.redirect_stdout(io.StringIO()):
    r = cb.post("/admin/email-check/send", follow_redirects=True)
ok("No email service is set up" in r.get_data(as_text=True), "with no service the failure explains what to add")
