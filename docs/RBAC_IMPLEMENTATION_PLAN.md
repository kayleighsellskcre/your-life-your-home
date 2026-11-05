# 🔐 RBAC & Security Implementation Plan

## ✅ Your Plan is EXCELLENT - Industry Standard!

This document outlines the professional implementation of Role-Based Access Control (RBAC) and security features.

---

## 📋 **Phase 1: Foundation (Week 1)**

### **1.1 Database Schema**

```sql
-- Roles table
CREATE TABLE IF NOT EXISTS roles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Permissions table  
CREATE TABLE IF NOT EXISTS permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE NOT NULL,
    resource TEXT NOT NULL,
    action TEXT NOT NULL,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Role-Permission mapping
CREATE TABLE IF NOT EXISTS role_permissions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    role_id INTEGER NOT NULL,
    permission_id INTEGER NOT NULL,
    granted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (role_id) REFERENCES roles(id),
    FOREIGN KEY (permission_id) REFERENCES permissions(id),
    UNIQUE(role_id, permission_id)
);

-- User-Role mapping (many-to-many)
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
);

-- Audit logs (non-negotiable!)
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
);

-- Impersonation sessions
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
);

-- MFA settings
CREATE TABLE IF NOT EXISTS mfa_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER UNIQUE NOT NULL,
    method TEXT NOT NULL,  -- 'totp', 'sms', etc.
    secret TEXT NOT NULL,
    backup_codes TEXT,
    enabled BOOLEAN DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

### **1.2 Define Roles & Permissions**

```python
# roles_and_permissions.py

ROLES = {
    'owner': {
        'name': 'Owner',
        'description': 'Full system access - break-glass only',
        'permissions': '*'  # ALL permissions
    },
    'admin': {
        'name': 'Administrator',
        'description': 'Manage users, content, settings (not security)',
        'permissions': [
            'users.view', 'users.edit', 'users.create',
            'content.view', 'content.edit', 'content.create', 'content.delete',
            'reports.view', 'reports.export',
            'properties.view', 'properties.edit',
            'dashboard.view_all'
        ]
    },
    'support': {
        'name': 'Support / Concierge',
        'description': 'Help users, view data, limited edits',
        'permissions': [
            'users.view', 'users.impersonate',
            'properties.view',
            'transactions.view',
            'reports.view',
            'support_tickets.manage'
        ]
    },
    'agent': {
        'name': 'Agent / Partner',
        'description': 'Manage own clients and listings',
        'permissions': [
            'own_clients.view', 'own_clients.edit',
            'own_properties.view', 'own_properties.edit', 'own_properties.create',
            'own_dashboard.view',
            'videos.create',
            'marketing.use'
        ]
    },
    'lender': {
        'name': 'Lender / Financial Partner',
        'description': 'Access to loan-related features',
        'permissions': [
            'loans.view', 'loans.edit', 'loans.create',
            'clients_shared.view',
            'reports.view_financial'
        ]
    },
    'client': {
        'name': 'Client (Homeowner)',
        'description': 'View own data only',
        'permissions': [
            'own_data.view',
            'own_properties.view',
            'own_transactions.view',
            'own_documents.view'
        ]
    }
}

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
]
```

---

## 📋 **Phase 2: Core RBAC (Week 2)**

### **2.1 Permission Checking Middleware**

```python
# rbac.py

from functools import wraps
from flask import session, abort
from database import get_connection

def get_user_permissions(user_id):
    """Get all permissions for a user"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all permissions through roles
    cur.execute("""
        SELECT DISTINCT p.name, p.resource, p.action
        FROM permissions p
        JOIN role_permissions rp ON p.id = rp.permission_id
        JOIN user_roles ur ON rp.role_id = ur.role_id
        WHERE ur.user_id = ?
        AND (ur.expires_at IS NULL OR ur.expires_at > datetime('now'))
    """, (user_id,))
    
    permissions = {row['name'] for row in cur.fetchall()}
    conn.close()
    
    return permissions

def has_permission(user_id, permission):
    """Check if user has a specific permission"""
    # Owner has ALL permissions
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.name FROM roles r
        JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = ? AND r.name = 'owner'
    """, (user_id,))
    
    if cur.fetchone():
        conn.close()
        return True
    
    conn.close()
    
    # Check specific permission
    permissions = get_user_permissions(user_id)
    return permission in permissions

def require_permission(permission):
    """Decorator to require a specific permission"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user:
                abort(401)  # Unauthorized
            
            if not has_permission(user['id'], permission):
                audit_log(
                    user['id'],
                    'permission_denied',
                    'access_control',
                    details=f"Attempted to access {permission}"
                )
                abort(403)  # Forbidden
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_role(role_name):
    """Decorator to require a specific role"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user:
                abort(401)
            
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                SELECT 1 FROM user_roles ur
                JOIN roles r ON ur.role_id = r.id
                WHERE ur.user_id = ? AND r.name = ?
            """, (user['id'], role_name))
            
            has_role = cur.fetchone() is not None
            conn.close()
            
            if not has_role:
                audit_log(
                    user['id'],
                    'role_check_failed',
                    'access_control',
                    details=f"Required role: {role_name}"
                )
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator
```

### **2.2 Audit Logging**

```python
# audit.py

from database import get_connection
from flask import request

def audit_log(user_id, action, resource, resource_id=None, details=None):
    """Log an action to audit trail"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        INSERT INTO audit_logs (
            user_id, action, resource, resource_id, 
            details, ip_address, user_agent
        ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (
        user_id,
        action,
        resource,
        resource_id,
        details,
        request.remote_addr if request else None,
        request.user_agent.string if request and request.user_agent else None
    ))
    
    conn.commit()
    conn.close()
```

---

## 📋 **Phase 3: Impersonation (Week 3)**

### **3.1 Impersonation Routes**

```python
# admin_routes.py

@app.route("/admin/impersonate/<int:user_id>", methods=["POST"])
@require_permission('users.impersonate')
def start_impersonation(user_id):
    """Start impersonating a user"""
    admin = get_current_user()
    
    # Log impersonation start
    audit_log(
        admin['id'],
        'impersonation_started',
        'users',
        user_id,
        f"Admin {admin['name']} started impersonating user {user_id}"
    )
    
    # Create impersonation session
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO impersonation_sessions (
            admin_id, target_user_id, reason, ip_address
        ) VALUES (?, ?, ?, ?)
    """, (admin['id'], user_id, request.form.get('reason'), request.remote_addr))
    conn.commit()
    session_id = cur.lastrowid
    conn.close()
    
    # Store in session
    session['impersonation'] = {
        'session_id': session_id,
        'admin_id': admin['id'],
        'admin_name': admin['name'],
        'original_user': session.get('user')
    }
    
    # Switch to target user
    target_user = get_user_by_id(user_id)
    session['user'] = target_user
    
    flash(f"🔍 Support Mode: Viewing as {target_user['name']}", "warning")
    return redirect(url_for('dashboard'))

@app.route("/admin/end-impersonation", methods=["POST"])
def end_impersonation():
    """End impersonation session"""
    if 'impersonation' not in session:
        return redirect(url_for('dashboard'))
    
    imp = session['impersonation']
    
    # Log end
    audit_log(
        imp['admin_id'],
        'impersonation_ended',
        'users',
        session['user']['id']
    )
    
    # Update session in DB
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE impersonation_sessions
        SET ended_at = datetime('now')
        WHERE id = ?
    """, (imp['session_id'],))
    conn.commit()
    conn.close()
    
    # Restore admin session
    session['user'] = imp['original_user']
    del session['impersonation']
    
    flash("✅ Exited Support Mode", "success")
    return redirect(url_for('admin_dashboard'))
```

---

## 📋 **Phase 4: MFA (Week 4)**

### **4.1 MFA Setup**

```python
# mfa.py

import pyotp
import qrcode
from io import BytesIO
import base64

def generate_mfa_secret(user_id, user_email):
    """Generate TOTP secret for user"""
    secret = pyotp.random_base32()
    
    # Store in database
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO mfa_settings (user_id, method, secret)
        VALUES (?, 'totp', ?)
    """, (user_id, secret))
    conn.commit()
    conn.close()
    
    # Generate QR code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=user_email,
        issuer_name="Your Life Your Home"
    )
    
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    qr_code = base64.b64encode(buffer.getvalue()).decode()
    
    return secret, qr_code

def verify_mfa_code(user_id, code):
    """Verify MFA code"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT secret FROM mfa_settings WHERE user_id = ? AND enabled = 1", (user_id,))
    row = cur.fetchone()
    conn.close()
    
    if not row:
        return False
    
    totp = pyotp.TOTP(row['secret'])
    return totp.verify(code, valid_window=1)
```

---

## 📋 **Phase 5: Admin Interface (Week 5)**

### **5.1 Separate Admin Routes**

```python
# Use blueprint for admin
admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.before_request
def require_admin():
    """Require admin role for all admin routes"""
    user = get_current_user()
    if not user:
        return redirect(url_for('login', role='admin'))
    
    if not has_permission(user['id'], 'dashboard.view_all'):
        abort(403)
```

---

## 🚀 **Implementation Order**

1. ✅ **TODAY**: Run reset script, create your admin account
2. **Week 1**: Create database tables, seed roles/permissions
3. **Week 2**: Implement RBAC middleware, update routes
4. **Week 3**: Add impersonation feature
5. **Week 4**: Implement MFA
6. **Week 5**: Build admin interface

---

## 📞 **Ready to Start?**

This is professional-grade security. Want me to implement it step-by-step?
