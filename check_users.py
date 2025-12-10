#!/usr/bin/env python3
"""Quick script to check user counts in the database."""

from database import get_connection, init_db
import sqlite3

# Initialize database to ensure tables exist
init_db()

# Get connection
conn = get_connection()
cur = conn.cursor()

# Total users
cur.execute('SELECT COUNT(*) FROM users')
total = cur.fetchone()[0]
print(f'\nUSER STATISTICS')
print(f'=' * 50)
print(f'Total users: {total}')

# Users by role
cur.execute('SELECT role, COUNT(*) FROM users GROUP BY role')
roles = cur.fetchall()
print(f'\nUsers by role:')
for role, count in roles:
    print(f'  - {role.title()}: {count}')

# Complete vs incomplete accounts
cur.execute('SELECT COUNT(*) FROM users WHERE password_hash IS NOT NULL AND password_hash != ""')
complete = cur.fetchone()[0]
cur.execute('SELECT COUNT(*) FROM users WHERE password_hash IS NULL OR password_hash = ""')
incomplete = cur.fetchone()[0]

print(f'\nAccount status:')
print(f'  - Complete accounts (with password): {complete}')
print(f'  - Incomplete accounts (no password): {incomplete}')

# Recent signups (last 30 days)
cur.execute("""
    SELECT COUNT(*) FROM users 
    WHERE created_at >= datetime('now', '-30 days')
""")
recent = cur.fetchone()[0]
print(f'  - New signups (last 30 days): {recent}')

conn.close()
print(f'\n' + '=' * 50)

