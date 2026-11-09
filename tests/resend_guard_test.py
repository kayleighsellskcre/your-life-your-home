import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ.pop("EMAIL_USER", None); os.environ.pop("MAIL_USERNAME", None)
os.environ["RESEND_API_KEY"] = "re_test"
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from datetime import date
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
today = date.today()
for fmt in (today.strftime("%m/%d"), today.strftime("%m/%d/%Y")):
    pass
D.add_agent_contact(ag, "Bea Birthday", email="bea@x.com", birthday=today.strftime("%Y-%m-%d"))
sent = []
A.send_reminder_email = lambda to, subj, body, **kw: (sent.append((to, subj)) or True)
ok(A._email_ready() and A.EMAIL_USER is None, "email counts as ready with only a Resend key")
with contextlib.redirect_stdout(io.StringIO()):
    A.send_birthday_emails()
ok(any(s[0] == "bea@x.com" for s in sent), "daily birthday job sends with Resend only (%s)" % sent)
n1 = len(sent)
with contextlib.redirect_stdout(io.StringIO()):
    A.send_birthday_emails()
ok(len(sent) == n1, "running the job again the same day does not email anyone twice")
D.add_agent_contact(ag, "Slash Sam", email="sam@x.com", birthday=today.strftime("%m/%d"))
D.add_agent_contact(ag, "Annie Anniv", email="annie@x.com", home_anniversary=today.strftime("%Y-%m-%d"))
with contextlib.redirect_stdout(io.StringIO()):
    A.send_birthday_emails(); A.send_anniversary_emails(); A.send_anniversary_emails()
ok(any(s[0] == "sam@x.com" for s in sent), "MM/DD birthdays still work")
ok(sum(1 for s in sent if s[0] == "annie@x.com") == 1, "ISO-format anniversary is sent once")
