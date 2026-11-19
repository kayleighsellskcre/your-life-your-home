"""Isolation test: rows owned by agent A1, lender L1 and homeowner H1 are planted in every table with an owner column; then a different agent, lender, homeowner and a signed-out visitor hit every route (GET and POST). Nobody may see or change what is not theirs."""
import os, sys, tempfile, io, contextlib, re, json, sqlite3, collections
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, os.getcwd())
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp

pw = gp("password123")
a1 = D.create_user("Amy One", "a1@x.com", pw, "agent")
a2 = D.create_user("Ben Two", "a2@x.com", pw, "agent")
l1 = D.create_user("Lou One", "l1@x.com", pw, "lender")
l2 = D.create_user("Liz Two", "l2@x.com", pw, "lender")
h1 = D.create_user("Hal One", "h1@x.com", pw, "homeowner", agent_id=a1, lender_id=l1)
h2 = D.create_user("Hope Two", "h2@x.com", pw, "homeowner", agent_id=a2, lender_id=l2)

conn = D.get_connection()
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()]
OWN_AGENT = {"agent_id", "agent_user_id", "pro_id", "professional_user_id", "owner_id", "agent_user"}
OWN_LENDER = {"lender_id", "lender_user_id"}
OWN_USER = {"user_id", "homeowner_id", "homeowner_user_id", "client_id", "created_by", "sender_id", "recipient_id"}
planted = {}   # table -> rowids
for t in tables:
    if t in ("users", "audit_logs"):
        continue
    info = conn.execute(f"PRAGMA table_info({t})").fetchall()
    cols = [r[1] for r in info]
    if not (set(cols) & (OWN_AGENT | OWN_LENDER | OWN_USER)):
        continue
    ids = []
    for variant, (agent, lender, user) in enumerate(((a1, l1, a1), (a1, l1, h1)), 1):
        for n in range(3):
            vals = {}
            for r in info:
                cid, name, typ, notnull, dflt, pk = r
                if pk and "INT" in (typ or "").upper() and name not in (OWN_AGENT | OWN_LENDER | OWN_USER):
                    continue
                if name in OWN_AGENT: vals[name] = agent
                elif name in OWN_LENDER: vals[name] = lender
                elif name in OWN_USER: vals[name] = user
                elif (typ or "").upper().startswith(("INT", "BOOL")): vals[name] = 1
                elif (typ or "").upper() in ("REAL", "FLOAT", "NUMERIC", "DOUBLE"): vals[name] = 1.0
                elif "TIMESTAMP" in (typ or "").upper() or "DATE" in (typ or "").upper(): vals[name] = "2026-01-01"
                else: vals[name] = "ZZMARK"
            try:
                cur = conn.execute(f"INSERT INTO {t} ({','.join(vals)}) VALUES ({','.join('?' * len(vals))})", list(vals.values()))
                ids.append(cur.lastrowid)
            except Exception:
                pass
    if ids:
        planted[t] = ids
conn.commit(); conn.close()
print("planted rows in", len(planted), "tables")

def snapshot():
    c = D.get_connection(); out = {}
    for t, ids in planted.items():
        for rid in ids:
            r = c.execute(f"SELECT * FROM {t} WHERE rowid=?", (rid,)).fetchone()
            out[(t, rid)] = tuple(r) if r else None
    c.close(); return out

def client(uid=None, role=None):
    cl = A.app.test_client()
    if uid:
        with cl.session_transaction() as s: s["user_id"] = uid; s["role"] = role; s["name"] = "X"
    return cl

owners = {"agent": (a1, "agent"), "lender": (l1, "lender"), "homeowner": (h1, "homeowner")}
strangers = {"agent2": (a2, "agent"), "lender2": (l2, "lender"), "homeowner2": (h2, "homeowner"), "visitor": (None, None)}
SKIP = re.compile(r"^/(logout|static)|webhook|stripe/", re.I)
rules = []
for rule in sorted(A.app.url_map.iter_rules(), key=lambda r: r.rule):
    if SKIP.search(rule.rule): continue
    rules.append(rule)

def fill(rule, i):
    p = re.sub(r"<(?:int:)?[a-z_]*(?:id|_id)>", str(i), rule)
    p = re.sub(r"<int:[a-z_]+>", str(i), p)
    p = re.sub(r"<path:[a-z_]+>", "x", p)
    p = re.sub(r"<[a-z_:]+>", "x", p)
    return p

FORM = {k: "HACKED" for k in ("name", "title", "status", "stage", "note", "notes", "description", "message", "body", "email", "phone", "address", "amount", "date", "category", "action", "label", "result", "days")}
FORM["email"] = "hacker@x.com"
FORM["amount"] = "1"
leaks, breaks, errors = collections.defaultdict(set), collections.defaultdict(set), collections.defaultdict(set)
base = snapshot()
nreq = 0
for sname, (uid, role) in strangers.items():
    for rule in rules:
        for i in (1, 2, 3):
            path = fill(rule.rule, i)
            for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
                cl = client(uid, role)
                before = snapshot() if method != "GET" else None
                try:
                    with contextlib.redirect_stdout(io.StringIO()):
                        r = cl.get(path) if method == "GET" else cl.post(path, data=FORM)
                except Exception as e:
                    errors[sname].add(f"{method} {rule.rule} EXC {str(e)[:60]}"); continue
                nreq += 1
                if r.status_code >= 500: errors[sname].add(f"{method} {rule.rule} {r.status_code}")
                if method == "GET":
                    if b"ZZMARK" in r.data: leaks[sname].add(f"{rule.rule}")
                else:
                    if snapshot() != before: breaks[sname].add(f"{method} {rule.rule}")
            if "<" not in rule.rule: break
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ok(nreq > 2000, f"{nreq} hostile requests were made by other agents, lenders, homeowners and signed-out visitors")
ok(not any(leaks.values()), "no stranger ever saw another account's data on any page" + (" LEAKS: " + str({k: sorted(v)[:5] for k, v in leaks.items() if v}) if any(leaks.values()) else ""))
ok(not any(breaks.values()), "no stranger could change or delete another account's data through any route" + (" BREAKS: " + str({k: sorted(v)[:5] for k, v in breaks.items() if v}) if any(breaks.values()) else ""))
seen = 0
for oname, (uid, role) in owners.items():
    cl = client(uid, role)
    for rule in rules:
        if "GET" in rule.methods:
            with contextlib.redirect_stdout(io.StringIO()):
                r = cl.get(fill(rule.rule, 1))
            if b"ZZMARK" in r.data: seen += 1
ok(seen > 20, "the check really can see data: the owners see their own planted rows on %d pages" % seen)
