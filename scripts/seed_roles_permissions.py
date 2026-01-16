"""
Seed roles and permissions
Run this after setup_rbac_tables.py
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection

# Define all roles
ROLES = [
    ('owner', 'Full system access - break-glass only'),
    ('admin', 'Manage users, content, settings (not security)'),
    ('support', 'Help users, view data, limited edits'),
    ('agent', 'Manage own clients and listings'),
    ('lender', 'Access to loan-related features'),
    ('client', 'View own data only'),
]

# Define all permissions
PERMISSIONS = [
    # Users
    ('users.view', 'users', 'view', 'View user profiles'),
    ('users.edit', 'users', 'edit', 'Edit user data'),
    ('users.create', 'users', 'create', 'Create new users'),
    ('users.delete', 'users', 'delete', 'Delete users'),
    ('users.impersonate', 'users', 'impersonate', 'Impersonate users'),
    
    # Properties
    ('properties.view', 'properties', 'view', 'View all properties'),
    ('properties.edit', 'properties', 'edit', 'Edit all properties'),
    ('properties.delete', 'properties', 'delete', 'Delete properties'),
    ('own_properties.view', 'properties', 'view_own', 'View own properties'),
    ('own_properties.edit', 'properties', 'edit_own', 'Edit own properties'),
    ('own_properties.create', 'properties', 'create_own', 'Create own properties'),
    
    # Content
    ('content.view', 'content', 'view', 'View all content'),
    ('content.edit', 'content', 'edit', 'Edit all content'),
    ('content.create', 'content', 'create', 'Create content'),
    ('content.delete', 'content', 'delete', 'Delete content'),
    
    # Reports
    ('reports.view', 'reports', 'view', 'View reports'),
    ('reports.export', 'reports', 'export', 'Export reports'),
    ('reports.view_financial', 'reports', 'view_financial', 'View financial reports'),
    
    # Security (Owner only)
    ('security.manage_roles', 'security', 'manage_roles', 'Manage roles and permissions'),
    ('security.view_audit', 'security', 'view_audit', 'View audit logs'),
    ('security.manage_mfa', 'security', 'manage_mfa', 'Manage MFA settings'),
    
    # Dashboard
    ('dashboard.view_all', 'dashboard', 'view_all', 'View all dashboards'),
    ('own_dashboard.view', 'dashboard', 'view_own', 'View own dashboard'),
    
    # Videos
    ('videos.create', 'videos', 'create', 'Create videos'),
    
    # Marketing
    ('marketing.use', 'marketing', 'use', 'Use marketing tools'),
    
    # Loans
    ('loans.view', 'loans', 'view', 'View loans'),
    ('loans.edit', 'loans', 'edit', 'Edit loans'),
    ('loans.create', 'loans', 'create', 'Create loans'),
    
    # Own data
    ('own_data.view', 'own_data', 'view', 'View own data'),
    ('own_transactions.view', 'transactions', 'view_own', 'View own transactions'),
    ('own_documents.view', 'documents', 'view_own', 'View own documents'),
]

# Map roles to permissions
ROLE_PERMISSIONS = {
    'owner': '*',  # ALL permissions
    'admin': [
        'users.view', 'users.edit', 'users.create',
        'content.view', 'content.edit', 'content.create', 'content.delete',
        'reports.view', 'reports.export',
        'properties.view', 'properties.edit',
        'dashboard.view_all',
        'videos.create',
    ],
    'support': [
        'users.view', 'users.impersonate',
        'properties.view',
        'reports.view',
    ],
    'agent': [
        'own_properties.view', 'own_properties.edit', 'own_properties.create',
        'own_dashboard.view',
        'videos.create',
        'marketing.use',
    ],
    'lender': [
        'loans.view', 'loans.edit', 'loans.create',
        'reports.view_financial',
    ],
    'client': [
        'own_data.view',
        'own_properties.view',
        'own_transactions.view',
        'own_documents.view',
    ],
}

def seed_data():
    """Seed roles and permissions"""
    conn = get_connection()
    cur = conn.cursor()
    
    print("🌱 Seeding Roles...")
    print("-" * 60)
    
    # Insert roles
    for name, description in ROLES:
        cur.execute("""
            INSERT OR IGNORE INTO roles (name, description)
            VALUES (?, ?)
        """, (name, description))
        print(f"✅ {name}: {description}")
    
    print("\n🌱 Seeding Permissions...")
    print("-" * 60)
    
    # Insert permissions
    for perm_name, resource, action, description in PERMISSIONS:
        cur.execute("""
            INSERT OR IGNORE INTO permissions (name, resource, action, description)
            VALUES (?, ?, ?, ?)
        """, (perm_name, resource, action, description))
        print(f"✅ {perm_name}")
    
    conn.commit()
    
    print("\n🔗 Linking Roles to Permissions...")
    print("-" * 60)
    
    # Get all permission IDs
    cur.execute("SELECT id, name FROM permissions")
    all_perms = {row['name']: row['id'] for row in cur.fetchall()}
    
    # Link roles to permissions
    for role_name, perms in ROLE_PERMISSIONS.items():
        cur.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
        role = cur.fetchone()
        if not role:
            continue
        
        role_id = role['id']
        
        if perms == '*':
            # Owner gets ALL permissions
            perm_ids = list(all_perms.values())
            print(f"✅ {role_name}: ALL {len(perm_ids)} permissions")
        else:
            # Other roles get specific permissions
            perm_ids = [all_perms[p] for p in perms if p in all_perms]
            print(f"✅ {role_name}: {len(perm_ids)} permissions")
        
        # Insert role-permission mappings
        for perm_id in perm_ids:
            cur.execute("""
                INSERT OR IGNORE INTO role_permissions (role_id, permission_id)
                VALUES (?, ?)
            """, (role_id, perm_id))
    
    conn.commit()
    
    # Assign owner role to user ID 1 (your admin account)
    print("\n👑 Assigning Owner Role...")
    print("-" * 60)
    
    cur.execute("SELECT id FROM roles WHERE name = 'owner'")
    owner_role = cur.fetchone()
    
    if owner_role:
        cur.execute("""
            INSERT OR IGNORE INTO user_roles (user_id, role_id, granted_by)
            VALUES (1, ?, 1)
        """, (owner_role['id'],))
        print("✅ User ID 1 is now OWNER (super admin)")
    
    conn.commit()
    conn.close()
    
    print("\n✅ All data seeded successfully!")

if __name__ == "__main__":
    print("=" * 60)
    print("🌱 SEED ROLES & PERMISSIONS")
    print("=" * 60)
    print()
    
    seed_data()
    
    print()
    print("=" * 60)
    print("✨ RBAC system ready!")
    print("=" * 60)
