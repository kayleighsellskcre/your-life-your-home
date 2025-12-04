import sqlite3, pathlib, json
DB = pathlib.Path(__file__).resolve().parents[1] / 'ylh.db'
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("INSERT INTO homeowner_notes (user_id, project_name, title, tags, details, photos, files) VALUES (?,?,?,?,?,?,?)", (1,'AutoTest','AutoTestTitle','tag','details', json.dumps(['uploads/design_boards/a.jpg']), json.dumps([])))
conn.commit()
cur.execute("SELECT id, user_id, project_name, title, tags, details, photos, created_at FROM homeowner_notes ORDER BY created_at DESC")
rows = cur.fetchall()
print('Inserted rows:')
for r in rows[:10]:
    print(r)
conn.close()
