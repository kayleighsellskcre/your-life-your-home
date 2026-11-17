import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
import stripe_payments as SP
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

# prices
os.environ.pop("STRIPE_SECRET_KEY", None)
SP._PRICE_CACHE.update(at=0, data={})
t = SP.live_tiers()
ok(t["professional"]["price_display"] == "$29/mo" and t["elite"]["price_display"] == "$79/mo", "without Stripe the written prices are shown")


class FakeStripe:
    class Price:
        @staticmethod
        def retrieve(pid):
            return {"unit_amount": {"p1": 3900, "p2": 9950}[pid], "active": True, "recurring": {"interval": "month"}}


os.environ.update(STRIPE_SECRET_KEY="sk_test_x", STRIPE_PROFESSIONAL_PRICE_ID="p1", STRIPE_ELITE_PRICE_ID="p2")
SP.get_stripe = lambda: FakeStripe
SP._PRICE_CACHE.update(at=0, data={})
t = SP.live_tiers()
ok(t["professional"]["price_display"] == "$39/mo" and t["elite"]["price_display"] == "$99.50/mo", "prices come from Stripe when it answers")
SP._PRICE_CACHE.update(at=0, data={})
SP.get_stripe = lambda: (_ for _ in ()).throw(RuntimeError("down"))
with contextlib.redirect_stdout(io.StringIO()):
    t = SP.live_tiers()
ok(t["professional"]["price_display"] == "$29/mo", "if Stripe is down the written prices are shown")
SP.get_stripe = lambda: FakeStripe
SP._PRICE_CACHE.update(at=0, data={})
ok("$39/mo" in A.app.test_client().get("/pricing").get_data(as_text=True), "the Pricing page shows the Stripe price")

# test email
agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
home = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=agent)
sent = []
A.send_reminder_email = lambda to, subject, body, **k: sent.append((to, subject, body, k)) or True
import email_signature as ES
ES._H["ns"] = A.__dict__
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = agent; s["role"] = "agent"; s["name"] = "Amy"
ok("Send me a test email" in c.get("/email-signature").get_data(as_text=True), "the Email Signature page has the test button")
r = c.post("/email-signature/test")
ok(r.status_code == 302 and sent and sent[-1][0] == "amy@x.com", "the test goes only to the person's own address")
ok("via Your Life Your Home" in str(sent[-1][3].get("from_name", "")), "it is sent the same way client emails are")
n = len(sent)
c.post("/email-signature/test")
ok(len(sent) == n, "a second press within seconds is held back")
A.send_reminder_email = lambda *a, **k: False
with c.session_transaction() as s: s["sig_test_at"] = 0
A._EMAIL_LAST.update(ok=False, detail="MAIL_FROM is not set in Railway.")
c.post("/email-signature/test")
page = c.get("/email-signature").get_data(as_text=True)
ok("did not go out" in page and "MAIL_FROM" in page, "a failed test explains why")
h = A.app.test_client()
with h.session_transaction() as s: s["user_id"] = home; s["role"] = "homeowner"
n = len(sent)
ok(h.post("/email-signature/test").status_code == 302 and len(sent) == n, "homeowners cannot use it")
