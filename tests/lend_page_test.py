import os, sys, tempfile, io, contextlib, time
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ln = D.create_user("Lou", "lou@x.com", gp("password123"), "lender")
other = D.create_user("Olly", "olly@x.com", gp("password123"), "lender")
conn = D.get_connection()
conn.executemany("INSERT INTO lender_borrowers (lender_user_id,name,status,email,phone) VALUES (?,?,?,?,?)",
    [(ln, f"Borrower {i:03d}", "prospect" if i % 2 else "closed", f"b{i}@x.com", f"555{i:07d}") for i in range(130)])
conn.execute("INSERT INTO lender_borrowers (lender_user_id,name,status) VALUES (?,?,?)", (other, "Secret Sam", "prospect"))
conn.commit()
c = A.app.test_client()
with c.session_transaction() as s: s["user_id"] = ln; s["role"] = "lender"
t0 = time.time(); r = c.get("/lender/crm"); dt = time.time() - t0; t = r.get_data(as_text=True)
ok(r.status_code == 200 and t.count('class="borrower-card"') == 50 and "Page 1 of 3" in t, "page one shows 50 borrowers with pager (%d cards)" % t.count('class="borrower-card"'))
ok("Secret Sam" not in t, "other lender's borrowers never show")
ok(">130<" in t.replace(" ", "").replace("\n", ""), "stats count everyone, not just the page")
t3 = c.get("/lender/crm?page=3").get_data(as_text=True); ok("Page 3 of 3" in t3 and "Borrower 129" in t3, "last page works")
ok("Page 3 of 3" in c.get("/lender/crm?page=999").get_data(as_text=True), "page past the end is clamped")
ok(c.get("/lender/crm?page=abc").status_code == 200, "bad page number is safe")
ts = c.get("/lender/crm?q=Borrower 120").get_data(as_text=True); ok("Borrower 120" in ts and "Borrower 005" not in ts, "search finds a borrower from a later page")
tf = c.get("/lender/crm?status=closed").get_data(as_text=True); ok("Borrower 001" not in tf and "Borrower 000" in tf, "status filter still works")
ok(len(t) < 600000, "page size is small (%d KB)" % (len(t) // 1024))
print("time %.2fs" % dt)
