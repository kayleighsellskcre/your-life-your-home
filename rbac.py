"""
RBAC - Role-Based Access Control System
Professional-grade permission checking
"""

from functools import wraps
from flask import session, abort, flash, redirect, url_for
from database import get_connection

def get_user_permissions(user_id):
    """Get all permissions for a user through their roles"""
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
        AND (ur.expires_at IS NULL OR ur.expires_at > datetime('now'))
    """, (user_id,))
    
    if cur.fetchone():
        conn.close()
        return True
    
    conn.close()
    
    # Check specific permission
    permissions = get_user_permissions(user_id)
    return permission in permissions

def has_role(user_id, role_name):
    """Check if user has a specific role"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT 1 FROM user_roles ur
        JOIN roles r ON ur.role_id = r.id
        WHERE ur.user_id = ? AND r.name = ?
        AND (ur.expires_at IS NULL OR ur.expires_at > datetime('now'))
    """, (user_id, role_name))
    
    result = cur.fetchone() is not None
    conn.close()
    return result

def get_user_roles(user_id):
    """Get all roles for a user"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT r.name, r.description
        FROM roles r
        JOIN user_roles ur ON r.id = ur.role_id
        WHERE ur.user_id = ?
        AND (ur.expires_at IS NULL OR ur.expires_at > datetime('now'))
    """, (user_id,))
    
    roles = [dict(row) for row in cur.fetchall()]
    conn.close()
    return roles

# =============================================================================
# DECORATORS
# =============================================================================

def require_permission(permission):
    """Decorator to require a specific permission for a route"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from audit import audit_log
            
            user = session.get('user')
            if not user:
                flash("Please log in to access this page", "error")
                return redirect(url_for('login'))
            
            if not has_permission(user['id'], permission):
                # Log permission denial
                audit_log(
                    user['id'],
                    'permission_denied',
                    'access_control',
                    details=f"Attempted to access {permission}"
                )
                flash("You don't have permission to access this page", "error")
                abort(403)  # Forbidden
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_role(role_name):
    """Decorator to require a specific role for a route"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            from audit import audit_log
            
            user = session.get('user')
            if not user:
                flash("Please log in to access this page", "error")
                return redirect(url_for('login'))
            
            if not has_role(user['id'], role_name):
                # Log role check failure
                audit_log(
                    user['id'],
                    'role_check_failed',
                    'access_control',
                    details=f"Required role: {role_name}"
                )
                flash(f"You must be a {role_name} to access this page", "error")
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_any_permission(*permissions):
    """Decorator to require ANY of the specified permissions"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user:
                flash("Please log in to access this page", "error")
                return redirect(url_for('login'))
            
            # Check if user has ANY of the permissions
            has_any = any(has_permission(user['id'], perm) for perm in permissions)
            
            if not has_any:
                flash("You don't have permission to access this page", "error")
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

def require_all_permissions(*permissions):
    """Decorator to require ALL of the specified permissions"""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = session.get('user')
            if not user:
                flash("Please log in to access this page", "error")
                return redirect(url_for('login'))
            
            # Check if user has ALL permissions
            has_all = all(has_permission(user['id'], perm) for perm in permissions)
            
            if not has_all:
                flash("You don't have permission to access this page", "error")
                abort(403)
            
            return f(*args, **kwargs)
        return decorated_function
    return decorator

# =============================================================================
# ROLE MANAGEMENT
# =============================================================================

def assign_role(user_id, role_name, granted_by=None, expires_at=None):
    """Assign a role to a user"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get role ID
    cur.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
    role = cur.fetchone()
    if not role:
        conn.close()
        raise ValueError(f"Role '{role_name}' does not exist")
    
    # Assign role
    cur.execute("""
        INSERT OR REPLACE INTO user_roles (user_id, role_id, granted_by, expires_at)
        VALUES (?, ?, ?, ?)
    """, (user_id, role['id'], granted_by, expires_at))
    
    conn.commit()
    conn.close()
    
    # Log the assignment
    from audit import audit_log
    audit_log(
        granted_by or user_id,
        'role_assigned',
        'users',
        user_id,
        f"Assigned role: {role_name}"
    )

def revoke_role(user_id, role_name, revoked_by=None):
    """Revoke a role from a user"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        DELETE FROM user_roles
        WHERE user_id = ? AND role_id = (
            SELECT id FROM roles WHERE name = ?
        )
    """, (user_id, role_name))
    
    conn.commit()
    conn.close()
    
    # Log the revocation
    from audit import audit_log
    audit_log(
        revoked_by or user_id,
        'role_revoked',
        'users',
        user_id,
        f"Revoked role: {role_name}"
    )

# Export all
__all__ = [
    'get_user_permissions',
    'has_permission',
    'has_role',
    'get_user_roles',
    'require_permission',
    'require_role',
    'require_any_permission',
    'require_all_permissions',
    'assign_role',
    'revoke_role',
]
