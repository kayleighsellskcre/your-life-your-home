"""
Reset database and create super admin account
DANGER: This deletes ALL users and creates a fresh admin account
"""

import sys
import os

# Fix encoding for Windows
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection
from werkzeug.security import generate_password_hash
import getpass

def reset_database():
    """Delete all users and start fresh"""
    conn = get_connection()
    cur = conn.cursor()
    
    print("🚨 WARNING: This will DELETE ALL users!")
    confirm = input("Type 'DELETE ALL' to confirm: ")
    
    if confirm != "DELETE ALL":
        print("❌ Cancelled. No changes made.")
        return False
    
    # Delete all users
    cur.execute("DELETE FROM users")
    conn.commit()
    
    count = cur.rowcount
    print(f"✅ Deleted {count} users")
    
    conn.close()
    return True

def create_super_admin():
    """Create the owner/super admin account"""
    print("\n👑 Creating Super Admin Account")
    print("-" * 50)
    
    name = input("Your full name: ").strip()
    email = input("Your email: ").strip()
    phone = input("Your phone (optional): ").strip()
    password = getpass.getpass("Password: ")
    password_confirm = getpass.getpass("Confirm password: ")
    
    if password != password_confirm:
        print("❌ Passwords don't match!")
        return False
    
    if len(password) < 8:
        print("❌ Password must be at least 8 characters!")
        return False
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Create super admin with special role
    hashed_pw = generate_password_hash(password)
    
    # Insert into users table (no phone column - it's in user_profiles)
    cur.execute("""
        INSERT INTO users (
            name, email, password_hash, 
            role, subscription_tier,
            created_at
        ) VALUES (?, ?, ?, ?, ?, datetime('now'))
    """, (
        name,
        email,
        hashed_pw,
        'agent',  # Agent role for super admin
        'pro'  # Highest subscription tier
    ))
    
    conn.commit()
    user_id = cur.lastrowid
    
    # Create user profile with phone if provided
    if phone:
        cur.execute("""
            INSERT INTO user_profiles (
                user_id, role, phone,
                created_at, updated_at
            ) VALUES (?, ?, ?, datetime('now'), datetime('now'))
        """, (
            user_id,
            'agent',
            phone
        ))
        conn.commit()
    
    print(f"\n✅ Super Admin Created!")
    print(f"ID: {user_id}")
    print(f"Name: {name}")
    print(f"Email: {email}")
    print(f"Role: AGENT (Super Admin)")
    print(f"Subscription: PRO")
    print(f"\n🔐 You can now login at: /login?role=agent")
    
    conn.close()
    return True

if __name__ == "__main__":
    print("="  * 60)
    print("🔧 DATABASE RESET & ADMIN CREATION")
    print("="  * 60)
    
    # Step 1: Reset
    if not reset_database():
        sys.exit(1)
    
    # Step 2: Create admin
    if not create_super_admin():
        sys.exit(1)
    
    print("\n" + "="  * 60)
    print("✨ Setup Complete! Your platform is ready.")
    print("="  * 60)
