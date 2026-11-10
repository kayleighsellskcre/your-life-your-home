import os, sys, tempfile, io, contextlib
os.environ["RAILWAY_VOLUME_MOUNT_PATH"] = tempfile.mkdtemp()
sys.path.insert(0, ".")
with contextlib.redirect_stdout(io.StringIO()):
    import app as A
import database as D
from werkzeug.security import generate_password_hash as gp
from openpyxl import load_workbook
ok = lambda c, m: print(("PASS " if c else "FAIL ") + m)
ag = D.create_user("Amy Agent", "amy@x.com", gp("password123"), "agent")
conn = D.get_connection()
conn.execute("INSERT INTO pie_events (owner_id, owner_role, token, title) VALUES (?,?,?,?)", (ag, "agent", "tok1", "Pie Pickup: A Little Holiday Thank You \U0001F967❤️"))
conn.commit()
eid = conn.execute("SELECT id FROM pie_events").fetchone()[0]
cl = A.app.test_client()
with cl.session_transaction() as s: s["user_id"] = ag; s["role"] = "agent"
r = cl.get(f"/pies/{eid}/export.xlsx")
ok(r.status_code == 200, "export downloads")
wb = load_workbook(io.BytesIO(r.data))
sm = wb["Summary"]
ok(sm["A1"].value == "Pie Pickup: A Little Holiday Thank You", "title has no emoji that Excel would show as a box")
ok("A1:D1" in [str(m) for m in sm.merged_cells.ranges], "title spans several columns so it is not cut off")
ok(sm.column_dimensions["A"].width >= 55, "first column is wide enough for pickup place names")
ok(wb.sheetnames == ["Summary", "Responses", "Bake list", "By pickup"], "all four sheets are there")
