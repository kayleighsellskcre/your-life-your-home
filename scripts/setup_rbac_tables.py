"""
Create RBAC database tables
Run this after creating your admin account
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import get_connection

def create_rbac_tables():
    """Create all RBAC-related tables"""
    conn = get_connection()
    cur = conn.cursor()
    
    print("📋 Creating RBAC Tables...")
    print("-" * 60)
    
    # Roles table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✅ Created: roles")
    
    # Permissions table
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            resource TEXT NOT NULL,
            action TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("✅ Created: permissions")
    
    # Role-Permission mapping
    cur.execute("""
        CREATE TABLE IF NOT EXISTS role_permissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            role_id INTEGER NOT NULL,
            permission_id INTEGER NOT NULL,
            granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (role_id) REFERENCES roles(id),
            FOREIGN KEY (permission_id) REFERENCES permissions(id),
            UNIQUE(role_id, permission_id)
        )
    """)
    print("✅ Created: role_permissions")
    
    # User-Role mapping
    cur.execute("""
        CREATE TABLE IF NOT EXISTS user_roles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            role_id INTEGER NOT NULL,
            granted_by INTEGER,
            granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            expires_at TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (role_id) REFERENCES roles(id),
            FOREIGN KEY (granted_by) REFERENCES users(id),
            UNIQUE(user_id, role_id)
        )
    """)
    print("✅ Created: user_roles")
    
    # Audit logs
    cur.execute("""
        CREATE TABLE IF NOT EXISTS audit_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            action TEXT NOT NULL,
            resource TEXT,
            resource_id INTEGER,
            details TEXT,
            ip_address TEXT,
            user_agent TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    print("✅ Created: audit_logs")
    
    # Impersonation sessions
    cur.execute("""
        CREATE TABLE IF NOT EXISTS impersonation_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_id INTEGER NOT NULL,
            target_user_id INTEGER NOT NULL,
            reason TEXT,
            consent_given BOOLEAN DEFAULT 0,
            started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            ended_at TIMESTAMP,
            ip_address TEXT,
            FOREIGN KEY (admin_id) REFERENCES users(id),
            FOREIGN KEY (target_user_id) REFERENCES users(id)
        )
    """)
    print("✅ Created: impersonation_sessions")
    
    # MFA settings
    cur.execute("""
        CREATE TABLE IF NOT EXISTS mfa_settings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER UNIQUE NOT NULL,
            method TEXT NOT NULL,
            secret TEXT NOT NULL,
            backup_codes TEXT,
            enabled BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    print("✅ Created: mfa_settings")
    
    conn.commit()
    conn.close()
    
    print("\n✅ All RBAC tables created successfully!")

if __name__ == "__main__":
    print("=" * 60)
    print("🔧 RBAC DATABASE SETUP")
    print("=" * 60)
    print()
    
    create_rbac_tables()
    
    print()
    print("=" * 60)
    print("✨ Database ready for RBAC!")
    print("=" * 60)
