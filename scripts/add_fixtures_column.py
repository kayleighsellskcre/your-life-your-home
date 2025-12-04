import sqlite3

conn = sqlite3.connect('homeowner_data.db')
cur = conn.cursor()

try:
    cur.execute('ALTER TABLE homeowner_notes ADD COLUMN fixtures TEXT')
    conn.commit()
    print('✓ fixtures column added successfully')
except Exception as e:
    print(f'Info: {e}')
    # Column may already exist

conn.close()
print('Done.')
