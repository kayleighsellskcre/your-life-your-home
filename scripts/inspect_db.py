import sqlite3
from pathlib import Path
DB = Path(__file__).resolve().parents[1] / 'ylh.db'
print('DB path:', DB)
conn = sqlite3.connect(DB)
cur = conn.cursor()
try:
    cur.execute("SELECT * FROM homeowner_notes ORDER BY created_at DESC")
    cols = [c[0] for c in cur.description]
    rows = cur.fetchall()
    print('columns:', cols)
    print('rows count:', len(rows))
    for r in rows[:20]:
        d = dict(zip(cols, r))
        print(d)
except Exception as e:
    print('ERROR querying homeowner_notes:', e)
finally:
    conn.close()
