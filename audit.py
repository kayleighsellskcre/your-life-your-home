"""
Audit Logging System
Track all important actions for compliance and security
"""

from database import get_connection
from flask import request, has_request_context
from datetime import datetime

def audit_log(user_id, action, resource, resource_id=None, details=None):
    """
    Log an action to the audit trail
    
    Args:
        user_id: ID of user performing action
        action: Action type (e.g., 'login', 'impersonation_started', 'permission_denied')
        resource: Resource type (e.g., 'users', 'properties', 'access_control')
        resource_id: ID of specific resource (optional)
        details: Additional details (optional)
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Get request context if available
    ip_address = None
    user_agent = None
    
    if has_request_context():
        ip_address = request.remote_addr
        user_agent = request.user_agent.string if request.user_agent else None
    
    cur.execute("""
        INSERT INTO audit_logs (
            user_id, action, resource, resource_id, 
            details, ip_address, user_agent, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
    """, (
        user_id,
        action,
        resource,
        resource_id,
        details,
        ip_address,
        user_agent
    ))
    
    conn.commit()
    conn.close()

def get_audit_logs(user_id=None, action=None, resource=None, limit=100):
    """
    Retrieve audit logs with optional filtering
    """
    conn = get_connection()
    cur = conn.cursor()
    
    query = "SELECT * FROM audit_logs WHERE 1=1"
    params = []
    
    if user_id:
        query += " AND user_id = ?"
        params.append(user_id)
    
    if action:
        query += " AND action = ?"
        params.append(action)
    
    if resource:
        query += " AND resource = ?"
        params.append(resource)
    
    query += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    
    cur.execute(query, params)
    logs = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return logs

def get_user_activity_summary(user_id, days=30):
    """Get summary of user activity for last N days"""
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            action,
            COUNT(*) as count,
            MAX(created_at) as last_occurrence
        FROM audit_logs
        WHERE user_id = ?
        AND created_at > datetime('now', '-' || ? || ' days')
        GROUP BY action
        ORDER BY count DESC
    """, (user_id, days))
    
    summary = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return summary

# Common audit actions (for consistency)
class AuditAction:
    # Authentication
    LOGIN_SUCCESS = 'login_success'
    LOGIN_FAILED = 'login_failed'
    LOGOUT = 'logout'
    MFA_ENABLED = 'mfa_enabled'
    MFA_DISABLED = 'mfa_disabled'
    MFA_VERIFIED = 'mfa_verified'
    MFA_FAILED = 'mfa_failed'
    
    # Access Control
    PERMISSION_DENIED = 'permission_denied'
    ROLE_CHECK_FAILED = 'role_check_failed'
    ROLE_ASSIGNED = 'role_assigned'
    ROLE_REVOKED = 'role_revoked'
    
    # Impersonation
    IMPERSONATION_STARTED = 'impersonation_started'
    IMPERSONATION_ENDED = 'impersonation_ended'
    
    # Data Access
    DATA_VIEWED = 'data_viewed'
    DATA_EXPORTED = 'data_exported'
    SENSITIVE_DATA_REVEALED = 'sensitive_data_revealed'
    
    # CRUD Operations
    CREATED = 'created'
    UPDATED = 'updated'
    DELETED = 'deleted'
    
    # Security
    PASSWORD_CHANGED = 'password_changed'
    PASSWORD_RESET_REQUESTED = 'password_reset_requested'
    ACCOUNT_LOCKED = 'account_locked'
    ACCOUNT_UNLOCKED = 'account_unlocked'

# Export
__all__ = [
    'audit_log',
    'get_audit_logs',
    'get_user_activity_summary',
    'AuditAction'
]
