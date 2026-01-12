"""
Quick script to upgrade your account to premium tier
Run this to test the 3D Property Tour feature
"""

import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection

def upgrade_user_to_premium(email=None, user_id=None):
    """Upgrade a user to premium tier"""
    conn = get_connection()
    cur = conn.cursor()
    
    if email:
        cur.execute("UPDATE users SET subscription_tier = 'premium' WHERE email = ?", (email,))
        cur.execute("SELECT id, name, email, subscription_tier FROM users WHERE email = ?", (email,))
    elif user_id:
        cur.execute("UPDATE users SET subscription_tier = 'premium' WHERE id = ?", (user_id,))
        cur.execute("SELECT id, name, email, subscription_tier FROM users WHERE id = ?", (user_id,))
    else:
        print("❌ Please provide either email or user_id")
        conn.close()
        return
    
    user = cur.fetchone()
    
    if user:
        conn.commit()
        print(f"\n✅ Successfully upgraded user to Premium!")
        print(f"   ID: {user[0]}")
        print(f"   Name: {user[1]}")
        print(f"   Email: {user[2]}")
        print(f"   Tier: {user[3]}")
        print(f"\n🎉 You can now create 3D Property Tour videos!")
        print(f"   Visit: http://localhost:5000/agent/video-studio\n")
    else:
        print("❌ User not found")
    
    conn.close()

def list_all_users():
    """List all users in the system"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT id, name, email, role, subscription_tier FROM users ORDER BY id")
    users = cur.fetchall()
    
    print("\n" + "="*80)
    print("ALL USERS IN SYSTEM:")
    print("="*80)
    print(f"{'ID':<5} {'Name':<20} {'Email':<30} {'Role':<12} {'Tier':<10}")
    print("-"*80)
    
    for user in users:
        user_id, name, email, role, tier = user
        tier = tier or 'free'
        print(f"{user_id:<5} {name:<20} {email:<30} {role:<12} {tier:<10}")
    
    print("="*80 + "\n")
    conn.close()

if __name__ == "__main__":
    print("\n🎬 3D Property Tour - Premium Upgrade Script\n")
    
    # List all users first
    list_all_users()
    
    # Ask for upgrade
    print("Who would you like to upgrade to Premium?")
    print("1. Enter email address")
    print("2. Enter user ID")
    choice = input("\nYour choice (1 or 2): ").strip()
    
    if choice == "1":
        email = input("Enter email address: ").strip()
        upgrade_user_to_premium(email=email)
    elif choice == "2":
        user_id = input("Enter user ID: ").strip()
        try:
            user_id = int(user_id)
            upgrade_user_to_premium(user_id=user_id)
        except ValueError:
            print("❌ Invalid user ID")
    else:
        print("❌ Invalid choice")
