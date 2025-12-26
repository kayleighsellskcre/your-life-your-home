#!/usr/bin/env python3
"""Test profile photo/logo upload and retrieval"""

from database import get_user_profile, get_connection

conn = get_connection()
cur = conn.cursor()

# Get agent
cur.execute("SELECT id, name, email FROM users WHERE role='agent' LIMIT 1")
agent = cur.fetchone()

if agent:
    agent_id = agent[0]
    print(f"\nAgent: {agent[1]} (ID: {agent_id})")
    
    # Get profile
    profile = get_user_profile(agent_id)
    
    if profile:
        profile_dict = dict(profile)
        print(f"\nProfile ID: {profile_dict.get('id')}")
        print(f"User ID: {profile_dict.get('user_id')}")
        
        # Check photo and logo
        photo = profile_dict.get('professional_photo')
        logo = profile_dict.get('brokerage_logo')
        
        print(f"\nProfessional Photo:")
        if photo:
            if photo.startswith('data:image'):
                print(f"  TYPE: Base64 Data URL")
                print(f"  SIZE: {len(photo)} characters")
                print(f"  PREVIEW: {photo[:80]}...")
            else:
                print(f"  TYPE: URL")
                print(f"  VALUE: {photo}")
        else:
            print(f"  STATUS: NOT SET")
        
        print(f"\nBrokerage Logo:")
        if logo:
            if logo.startswith('data:image'):
                print(f"  TYPE: Base64 Data URL")
                print(f"  SIZE: {len(logo)} characters")
                print(f"  PREVIEW: {logo[:80]}...")
            else:
                print(f"  TYPE: URL")
                print(f"  VALUE: {logo}")
        else:
            print(f"  STATUS: NOT SET")
        
        # Check table structure
        print(f"\n" + "="*60)
        print("CHECKING TABLE STRUCTURE:")
        cur.execute("PRAGMA table_info(user_profiles)")
        columns = cur.fetchall()
        
        photo_col = [c for c in columns if c[1] == 'professional_photo']
        logo_col = [c for c in columns if c[1] == 'brokerage_logo']
        
        if photo_col:
            print(f"  professional_photo: Type={photo_col[0][2]}, NotNull={photo_col[0][3]}, Default={photo_col[0][4]}")
        else:
            print(f"  professional_photo: COLUMN MISSING!")
            
        if logo_col:
            print(f"  brokerage_logo: Type={logo_col[0][2]}, NotNull={logo_col[0][3]}, Default={logo_col[0][4]}")
        else:
            print(f"  brokerage_logo: COLUMN MISSING!")
    else:
        print(f"\nNO PROFILE for agent {agent_id}")
else:
    print("\nNO AGENT FOUND")

conn.close()

