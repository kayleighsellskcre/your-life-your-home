import os, sys, tempfile, io, contextlib, random, time
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from datetime import date, timedelta
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy", "amy@x.com", gp("password123"), "agent")
ln = D.create_user("Lou", "lou@x.com", gp("password123"), "lender")
random.seed(3); today = date.today().isoformat()
rows = []
for i in range(5000):
    rows.append((ag, f"P{i}", random.choice(["new", "active", "closed", "Hold", "past", "", None]),
                 random.choice([None, "", today, "2020-01-01", "2099-01-01"]), random.choice([None, "", "2026-01-01"])))
conn = D.get_connection()
conn.executemany("INSERT INTO agent_contacts (agent_user_id,name,stage,next_action_date,last_touch) VALUES (?,?,?,?,?)", rows)
conn.executemany("INSERT INTO lender_borrowers (lender_user_id,name,status) VALUES (?,?,?)", [(ln, f"B{i}", random.choice(["prospect", "preapproval", "closed"])) for i in range(300)])
conn.commit()
# old logic
nl = fu = 0
for _, _, st, nad, lt in rows:
    nl += (st or "") == "new"
    if (st or "").lower() in ("closed", "hold", "past"): continue
    nad = nad or ""; lt = lt or ""
    if nad and nad <= today: fu += 1
    elif not nad and not lt: fu += 1
t0 = time.time(); m = A.get_agent_dashboard_metrics(ag); dt = time.time() - t0
ok(m["new_leads"] == nl and m["followups_today"] == fu, "agent numbers match the old calculation (%d leads, %d follow-ups) in %.3fs" % (nl, fu, dt))
lm = A.get_lender_dashboard_metrics(ln)
pre = conn.execute("select count(*) from lender_borrowers where lender_user_id=? and status='preapproval'", (ln,)).fetchone()[0]
ok(lm["new_applications"] == pre and lm["nurture_contacts"] == 150, "lender numbers right")
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ag; s["role"] = "agent"
t0 = time.time(); r = c.get("/agent"); print("dashboard %.2fs" % (time.time() - t0)); ok(r.status_code == 200, "agent dashboard loads")
