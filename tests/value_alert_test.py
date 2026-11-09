import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
os.environ["RENTCAST_API_KEY"] = "k"
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D, valuation as V
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
ho = D.create_user("Val Owner", "val@x.com", gp("password123"), "homeowner", agent_id=ag)
p = D.add_property(ho, "10 First St, Shawnee, KS 66226", 300000.0, "primary")
conn = D.get_connection()
conn.execute("INSERT INTO homeowner_snapshots (user_id, property_id, value_estimate, loan_balance) VALUES (?,?,?,?)", (ho, p, 300000, 200000)); conn.commit()
sent = []
A.send_reminder_email = lambda to, subj, body, **kw: (sent.append((to, subj, body)) or True)
A._bg = lambda fn, *a: fn(*a)
import client_values; client_values.set_on(ag, True)
answers = []
V._http_get = lambda url, headers, timeout=15: answers.pop(0)
def refresh(price):
    conn.execute("DELETE FROM avm_calls"); conn.commit()
    answers.append((200, {"price": price, "priceRangeLow": price * .95, "priceRangeHigh": price * 1.05}))
    return V.refresh_property_value(ho, p, min_days=0)
sent.clear(); conn.execute("DELETE FROM value_alerts"); conn.execute("UPDATE homeowner_snapshots SET value_estimate=300000"); conn.commit()
refresh(306000); ok(not sent, "a 2% rise stays quiet")
refresh(321000)  # 306000 -> 321000 = +4.9%
tos = sorted(s[0] for s in sent)
ok(tos == ["amy@x.com", "val@x.com"], f"a rise of 3 percent or more emails the homeowner and the agent ({tos})")
hm = next(s for s in sent if s[0] == "val@x.com"); am = next(s for s in sent if s[0] == "amy@x.com")
ok("$321,000" in hm[2] and "up 4.9%" in hm[2] and "not an appraisal" in hm[2] and "/homeowner" in hm[2], "homeowner email: value, change, honest disclaimer, link")
ok("Val Owner" in am[1] and "reach out" in am[2] and "/agent/clients" in am[2], "agent email: client name and a nudge to reach out")
n = len(sent)
refresh(340000); ok(len(sent) == n, "no second alert for the same home within 25 days")
conn.execute("UPDATE value_alerts SET created_at = datetime('now', '-30 days')"); conn.commit()
refresh(360000); ok(len(sent) == n + 2, "alerts resume after 25 days")
n = len(sent); conn.execute("UPDATE value_alerts SET created_at = datetime('now', '-30 days')"); conn.commit()
refresh(300000); ok(len(sent) == n, "drops are never announced")
