import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, email_signature as ES
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)


def client(uid, role):
    cl = A.app.test_client()
    with cl.session_transaction() as s: s["user_id"] = uid; s["role"] = role
    return cl


amy = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
lou = D.create_user("Lou Lender", "lou@x.com", gp("password123"), "lender")
hom = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=amy)
ca, cl, ch = client(amy, "agent"), client(lou, "lender"), client(hom, "homeowner")

ok(A.app.test_client().get("/email-signature").status_code == 302 and ch.get("/email-signature").status_code == 302, "signed-out visitors and homeowners cannot open the signature page")
ok(ca.get("/email-signature").status_code == 200 and cl.get("/email-signature").status_code == 200, "agents and lenders can")
ok("Email Signature" in ca.get("/agent/dashboard").get_data(as_text=True) and "/email-signature" in cl.get("/lender/dashboard").get_data(as_text=True), "it is in the menu for both")
ok("Amy Agent" in ca.get("/email-signature").get_data(as_text=True), "'fill in from my profile' offers their name")

sig = "Amy Agent\nRealtor, Best Homes\n785-555-0100"
r = ca.post("/email-signature", data={"signature": sig}, follow_redirects=True)
ok("Saved." in r.get_data(as_text=True) and "Best Homes" in r.get_data(as_text=True), "a signature is saved and shown again")
ok(ES.get_signature(amy) == sig and ES.get_signature(lou) == "", "it belongs to that person only")
ok(A.pro_sender(amy).get("signature") == sig and "signature" not in A.pro_sender(lou), "emails sent for an agent carry their signature, others do not")

body = "Hi Sam,\n\nChecking in.\n\nAmy"
out = ES.with_signature(body, sig, "Amy Agent")
ok(out.endswith(sig) and out.count("Amy Agent") == 1 and "\nAmy\n" not in out, "a plain name sign-off is replaced, so the name is not repeated")
ok(ES.with_signature("Hello\n\nThanks!", sig, "Amy Agent") == "Hello\n\nThanks!\n\n" + sig, "other endings are kept and the signature goes below")
ok(ES.with_signature("Hello", "", "Amy") == "Hello", "no signature means no change")
h = ES.html_with_signature("<html><body><p>Hi</p></body></html>", "Amy <b>&\nRealtor")
ok("Amy &lt;b&gt;" in h and "<br>Realtor" in h and h.index("Realtor") < h.index("</body>"), "in HTML emails the signature is escaped and placed inside the body")

# what actually goes out
sent = []
os.environ["BREVO_API_KEY"] = "k"; os.environ["MAIL_FROM"] = "Site <hello@x.com>"
A._send_via_brevo = lambda to, subj, b, fn, rt, html=None: (sent.append((to, b, html, fn, rt)) or True)
A.send_reminder_email("sam@x.com", "Hi", body, html="<body><p>Hi</p></body>", **A.pro_sender(amy))
to, b, html, fn, rt = sent[0]
ok(b.endswith(sig) and "785-555-0100" in html and fn == "Amy Agent via Your Life Your Home" and rt == "amy@x.com", "a real send includes the signature, with the name and reply-to as before")
A.send_reminder_email("sam@x.com", "Hi", body)
ok(sent[1][1] == body, "emails with no signature are unchanged")

ca.post("/email-signature", data={"signature": ""})
ok(ES.get_signature(amy) == "" and "signature" not in A.pro_sender(amy), "clearing the signature removes it")
ca.post("/email-signature", data={"signature": "x" * 5000})
ok(len(ES.get_signature(amy)) == ES.MAX_LEN, "very long signatures are trimmed")

# the scheduled jobs that email clients on an agent's behalf must run (they once asked for a profile column that does not exist)
with contextlib.redirect_stdout(io.StringIO()):
    try:
        A.send_drip_emails(); A.send_review_requests(); jobs_ok = True
    except Exception as e:
        jobs_ok = False
ok(jobs_ok, "the drip-email and review-request jobs run without a database error")

# ---- sending from their own confirmed address ----
calls = []
state = {"senders": [], "post": 201}
def fake_brevo(method, path, payload=None, timeout=10):
    calls.append((method, path, payload))
    if method == "POST":
        if state["post"] in (200, 201):
            state["senders"].append({"email": payload["email"], "active": False})
        return state["post"], ({"id": 1} if state["post"] == 201 else {"message": "Sender already exist"} if state["post"] == 400 else {})
    return 200, {"senders": state["senders"]}
ES._brevo = fake_brevo
os.environ["BREVO_API_KEY"] = "k"
ca.post("/email-signature", data={"signature": sig})
r = ca.post("/email-signature/sender", data={"email": "amy@gmail.com"}, follow_redirects=True)
ok("cannot be used this way" in r.get_data(as_text=True) and not any(c[0] == "POST" for c in calls) and ES._own_row(amy) is None, "a Gmail (free) address is refused kindly and nothing is sent to the email service")
r = ca.post("/email-signature/sender", data={"email": "not-an-email"}, follow_redirects=True)
ok("does not look right" in r.get_data(as_text=True), "a badly typed address is refused")
r = ca.post("/email-signature/sender", data={"email": "Amy@BestHomes.com"}, follow_redirects=True)
t = r.get_data(as_text=True)
post = [c for c in calls if c[0] == "POST"]
ok(post and post[-1][1] == "/senders" and post[-1][2]["email"] == "amy@besthomes.com" and "sent a confirmation email" in t, "a business address is submitted for confirmation")
ok(ES.get_own_sender(amy) == "" and "from_email" not in A.pro_sender(amy), "until it is confirmed, emails keep going out the usual way")
sent.clear()
A._send_via_brevo = lambda to, subj, b, fn, rt, html=None, from_email=None: (sent.append((from_email, fn)) or True)
ok("Waiting for you" in ca.get("/email-signature").get_data(as_text=True), "the page says it is waiting for the confirmation link")
state["senders"][0]["active"] = True
t = ca.get("/email-signature").get_data(as_text=True)
ok("Confirmed." in t and ES.get_own_sender(amy) == "amy@besthomes.com", "after the link is tapped the page shows it as confirmed")
ps = A.pro_sender(amy)
ok(ps["from_email"] == "amy@besthomes.com" and ps["from_name"] == "Amy Agent", "emails then come from their own address under just their name")
A.send_reminder_email("sam@x.com", "Hi", "Hello", **ps)
ok(sent[-1] == ("amy@besthomes.com", "Amy Agent"), "a real send uses it")
# if the service refuses the personal address, the email still goes the usual way
sent.clear()
def picky(to, subj, b, fn, rt, html=None, from_email=None):
    sent.append(from_email)
    return from_email is None
A._send_via_brevo = picky
ok(A.send_reminder_email("sam@x.com", "Hi", "Hello", **ps) is True and sent == ["amy@besthomes.com", None], "if their address is refused, the email is sent the usual way instead of being lost")
ok(lou and "from_email" not in A.pro_sender(lou), "other people are not affected")
ca.post("/email-signature/sender/remove")
ok(ES._own_row(amy) is None and "from_email" not in A.pro_sender(amy), "they can switch back")
os.environ.pop("BREVO_API_KEY")
ok("needs the site's email service" in ca.get("/email-signature").get_data(as_text=True), "with no email service the page explains instead of failing")
