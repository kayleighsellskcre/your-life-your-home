import os, sys, tempfile, io, contextlib, re
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ.pop("YLH_SECRET_KEY", None)
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)

agent = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
home = D.create_user("Hal Homeowner", "hal@x.com", gp("password123"), "homeowner", agent_id=agent)
def who(uid, role):
    c = A.app.test_client()
    with c.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return c
ca, ch = who(agent, "agent"), who(home, "homeowner")

# secret key
ok(A.app.secret_key not in ("change-this-secret-key", "", None) and len(A.app.secret_key) >= 32, "with no secret set, the app makes a random key instead of a public one")

# AI endpoints
r = ch.post("/api/ai/crm/draft-email", json={})
ok(r.status_code == 403, "a homeowner account cannot use the agent AI tools")
r = A.app.test_client().post("/api/ai/crm/draft-email", json={})
ok(r.status_code in (401, 302, 403), "signed-out visitors cannot either")
codes = []
for _ in range(85):
    with contextlib.redirect_stdout(io.StringIO()):
        codes.append(ca.post("/api/ai/crm/lead-score", json={}).status_code)
ok(429 in codes and codes.index(429) >= 80, "one account is held back after a few dozen AI requests in ten minutes")

# delete via link no longer possible
ok(ch.get("/homeowner/home-timeline/delete/1").status_code == 405, "a timeline event cannot be deleted just by opening a link")

# public site map
sm = A.app.test_client().get("/sitemap.xml").get_data(as_text=True)
ok(all(p in sm for p in ("/for-agents", "/for-lenders", "/for-homeowners", "/pricing", "/home-value", "/privacy", "/terms")), "the sitemap lists every public page")

# nothing secret-looking in the public source
src = open("app.py", encoding="utf-8").read()
ok("YLH-GOLD-LAUNCH" not in src, "no promo codes are written in the source code")
for f in ("templates/agent/subscription.html", "templates/lender/subscription.html"):
    ok("YLH-GOLD-LAUNCH" not in open(f, encoding="utf-8").read(), f"{f} does not show a real promo code as the example")
ok("Kayleigh" not in open("templates/shared/_signature_body.html", encoding="utf-8").read(), "the signature box example is not one person's real details")

# packages the code imports are all declared
req = open("requirements.txt", encoding="utf-8").read().lower()
ok(all(p in req for p in ("pypdf", "requests", "python-dateutil")), "pypdf, requests and dateutil are declared so contract reading works after a fresh deploy")
ok(all(re.search(r"^(flask|gunicorn|apscheduler|pandas|openai)[^\n]*<", req, re.M) for _ in [0]) and "apscheduler>=3.10,<4" in req, "packages that could break on a new major version have an upper limit")

# form fields that screen readers need names for
page = ca.get("/agent/crm").get_data(as_text=True)
ok('aria-label="Sort people by"' in page and 'aria-label="What to do with the selected people"' in page, "CRM selects have names for screen readers")

# off-site backups
import gzip as _gz
class FakeR2:
    def __init__(self): self.up, self.deleted, self.keys = [], [], [f"ylh-db/ylh-2026010{i}-030000.db.gz" for i in range(1, 10)] + [f"ylh-db/ylh-2026011{i}-030000.db.gz" for i in range(0, 9)]
    def upload_file(self, path, bucket, key, ExtraArgs=None):
        self.up.append((bucket, key, _gz.open(path, "rb").read(16)))
    def list_objects_v2(self, Bucket, Prefix): return {"Contents": [{"Key": k} for k in self.keys + [self.up[-1][1]]]}
    def delete_object(self, Bucket, Key): self.deleted.append(Key)
snap = os.path.join(tempfile.mkdtemp(), "ylh-20261117-030000.db")
import sqlite3 as _sq
_c = _sq.connect(snap); _c.execute("create table t(x)"); _c.commit(); _c.close()
os.environ.pop("YLH_BACKUP_BUCKET", None); os.environ.pop("R2_BACKUP_BUCKET", None)
fake = FakeR2(); A.R2_CLIENT = fake
ok(A.offsite_backup(snap) is False and not fake.up, "with no backup bucket set, nothing is uploaded and nothing breaks")
os.environ["R2_BUCKET"] = "photos"; os.environ["R2_BACKUP_BUCKET"] = "photos"
ok(A.offsite_backup(snap) is False and not fake.up, "it refuses to use the photo bucket, which may be public")
os.environ["R2_BACKUP_BUCKET"] = "private-backups"
ok(A.offsite_backup(snap) is True and fake.up and fake.up[0][0] == "private-backups" and fake.up[0][1].startswith("ylh-db/") and fake.up[0][2].startswith(b"SQLite format 3"), "a compressed, valid database copy goes to the private backup bucket")
ok(len(fake.deleted) == 18 - 13 and fake.deleted[0] == "ylh-db/ylh-20260101-030000.db.gz", "only the newest 14 off-site copies are kept")
class Boom(FakeR2):
    def upload_file(self, *a, **k): raise RuntimeError("storage down")
A.R2_CLIENT = Boom()
ok(A.offsite_backup(snap) is False, "if the storage is down the nightly job carries on instead of crashing")
A.R2_CLIENT = None
