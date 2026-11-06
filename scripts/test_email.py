"""Send ONE real test email through the same code the site uses, and say what went wrong if it fails.

PowerShell (from the project folder):
    $env:BREVO_API_KEY = "paste-your-brevo-key"
    $env:MAIL_FROM = "Your Life Your Home <your-verified-sender@yourdomain.com>"
    python scripts/test_email.py you@gmail.com

Use RESEND_API_KEY instead of BREVO_API_KEY if you chose Resend. With neither, it tries
MAIL_SERVER / MAIL_USERNAME / MAIL_PASSWORD over SMTP (which Railway's Hobby plan blocks).
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

if len(sys.argv) < 2 or "@" not in sys.argv[1]:
    sys.exit('Give the address to send to:  python scripts/test_email.py you@gmail.com')

import app  # noqa: E402  (the site's own sender)

to = sys.argv[1]
if os.environ.get("RESEND_API_KEY"):
    route = "Resend (HTTPS)"
elif os.environ.get("BREVO_API_KEY"):
    route = "Brevo (HTTPS)"
elif app.EMAIL_USER and app.EMAIL_PASS:
    route = f"SMTP via {app.EMAIL_HOST}:{app.EMAIL_PORT}"
else:
    sys.exit("No email settings found. Set BREVO_API_KEY (or RESEND_API_KEY) and MAIL_FROM first.")
if not (os.environ.get("MAIL_FROM") or app.EMAIL_USER):
    sys.exit('MAIL_FROM is not set. Example:  $env:MAIL_FROM = "Your Life Your Home <you@yourdomain.com>"')

print(f"Sending through: {route}")
print(f"From: {os.environ.get('MAIL_FROM') or app.EMAIL_USER}")
ok = app.send_reminder_email(
    to,
    "Test email from Your Life, Your Home",
    "If you can read this, your site can send email.\n\nThis one was sent as 'Test Agent via Your Life Your Home' "
    "so you can check how a client sees an agent's message. Hit Reply and the reply should go to the address below.",
    from_name="Test Agent via Your Life Your Home",
    reply_to=to,
)
print()
if ok:
    print(f"Sent. Check the inbox for {to} (and the spam folder) within a minute or two.")
else:
    print("It did NOT send. Read the line above that starts with 'Failed' or '[WARNING]'. Common causes:")
    print("  - Brevo: the MAIL_FROM address is not verified under Senders in Brevo (error says sender not valid).")
    print("  - Brevo or Resend: the API key was copied incompletely or has been deleted.")
    print("  - Resend: the domain is not verified yet, or you are sending to someone other than your own account.")
    print("  - SMTP: your host blocks the port (Railway Hobby does). Use BREVO_API_KEY or RESEND_API_KEY instead.")
    sys.exit(1)
