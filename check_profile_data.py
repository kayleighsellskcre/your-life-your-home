#!/usr/bin/env python3
"""
Quick script to verify profile photos/logos are saved in the database
Run this to check if your data is actually being saved!
"""

import sqlite3
import os
from pathlib import Path

# Find the database
db_path = Path(__file__).parent / "ylh.db"

if not db_path.exists():
    print("❌ Database file not found!")
    print(f"   Looking for: {db_path}")
    exit(1)

print(f"✅ Database found: {db_path}")
print(f"   Size: {db_path.stat().st_size / 1024:.2f} KB\n")

# Connect and check
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

# Check if user_profiles table exists
cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_profiles'")
if not cur.fetchone():
    print("❌ user_profiles table doesn't exist!")
    exit(1)

# Get all agent profiles
cur.execute("SELECT id, user_id, role, professional_photo, brokerage_logo FROM user_profiles WHERE role='agent'")
profiles = cur.fetchall()

if not profiles:
    print("⚠️  No agent profiles found in database")
    print("   Have you created an agent account and saved your profile?")
    exit(0)

print(f"Found {len(profiles)} agent profile(s):\n")

for profile in profiles:
    print(f"Profile ID: {profile['id']} (User ID: {profile['user_id']})")
    print(f"  Role: {profile['role']}")
    
    if profile['professional_photo']:
        photo_len = len(profile['professional_photo'])
        is_base64 = profile['professional_photo'].startswith('data:image/')
        print(f"  ✅ Professional Photo: {photo_len} characters ({'base64 data URL' if is_base64 else 'INVALID FORMAT'})")
    else:
        print(f"  ❌ Professional Photo: NOT SET")
    
    if profile['brokerage_logo']:
        logo_len = len(profile['brokerage_logo'])
        is_base64 = profile['brokerage_logo'].startswith('data:image/')
        print(f"  ✅ Brokerage Logo: {logo_len} characters ({'base64 data URL' if is_base64 else 'INVALID FORMAT'})")
    else:
        print(f"  ❌ Brokerage Logo: NOT SET")
    
    print()

conn.close()

print("=" * 60)
print("INTERPRETATION:")
print("=" * 60)
print("✅ = Data IS saved in database (good!)")
print("❌ = Data NOT saved (needs to be uploaded)")
print()
print("If you see ✅ but photos still disappear after redeploy,")
print("then Railway needs a persistent volume configured!")
print("See: RAILWAY_PERSISTENT_STORAGE_SETUP.md")

