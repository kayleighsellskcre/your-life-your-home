"""
Impersonation System - Safe "View As" Support Mode
Allows admins to view the platform as another user
"""

from database import get_connection
from flask import session, request
from audit import audit_log, AuditAction

def start_impersonation(admin_id, target_user_id, reason=None):
    """
    Start impersonating a user
    
    Returns:
        session_id: ID of impersonation session
    """
    conn = get_connection()
    cur = conn.cursor()
    
    # Create impersonation session
    cur.execute("""
        INSERT INTO impersonation_sessions (
            admin_id, target_user_id, reason, ip_address
        ) VALUES (?, ?, ?, ?)
    """, (admin_id, target_user_id, reason, request.remote_addr))
    
    conn.commit()
    session_id = cur.lastrowid
    
    # Get admin and target user info
    cur.execute("SELECT name, email FROM users WHERE id = ?", (admin_id,))
    admin_data = dict(cur.fetchone())
    
    cur.execute("SELECT * FROM users WHERE id = ?", (target_user_id,))
    target_user = dict(cur.fetchone())
    
    conn.close()
    
    # Log impersonation start
    audit_log(
        admin_id,
        AuditAction.IMPERSONATION_STARTED,
        'users',
        target_user_id,
        f"Admin {admin_data['name']} started viewing as {target_user['name']}"
    )
    
    return session_id, target_user

def end_impersonation(session_id, admin_id):
    """End impersonation session"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Get session details for logging
    cur.execute("""
        SELECT target_user_id, started_at
        FROM impersonation_sessions
        WHERE id = ? AND admin_id = ?
    """, (session_id, admin_id))
    
    imp_session = cur.fetchone()
    if not imp_session:
        conn.close()
        return False
    
    # Update session end time
    cur.execute("""
        UPDATE impersonation_sessions
        SET ended_at = datetime('now')
        WHERE id = ?
    """, (session_id,))
    
    conn.commit()
    conn.close()
    
    # Log impersonation end
    duration = "Unknown"
    if imp_session['started_at']:
        # Calculate duration
        from datetime import datetime
        start = datetime.fromisoformat(imp_session['started_at'])
        end = datetime.now()
        duration = str(end - start)
    
    audit_log(
        admin_id,
        AuditAction.IMPERSONATION_ENDED,
        'users',
        imp_session['target_user_id'],
        f"Session duration: {duration}"
    )
    
    return True

def get_active_impersonation_sessions(admin_id=None):
    """Get all active impersonation sessions"""
    conn = get_connection()
    cur = conn.cursor()
    
    query = """
        SELECT 
            imp.*,
            admin.name as admin_name,
            admin.email as admin_email,
            target.name as target_name,
            target.email as target_email
        FROM impersonation_sessions imp
        JOIN users admin ON imp.admin_id = admin.id
        JOIN users target ON imp.target_user_id = target.id
        WHERE imp.ended_at IS NULL
    """
    
    params = []
    if admin_id:
        query += " AND imp.admin_id = ?"
        params.append(admin_id)
    
    query += " ORDER BY imp.started_at DESC"
    
    cur.execute(query, params)
    sessions = [dict(row) for row in cur.fetchall()]
    conn.close()
    
    return sessions

def is_impersonating():
    """Check if current session is an impersonation session"""
    return 'impersonation' in session

def get_real_user():
    """Get the actual logged-in user (even during impersonation)"""
    if is_impersonating():
        return session['impersonation'].get('original_user')
    return session.get('user')

def get_displayed_user():
    """Get the user being displayed (may be impersonated)"""
    return session.get('user')

# Export
__all__ = [
    'start_impersonation',
    'end_impersonation',
    'get_active_impersonation_sessions',
    'is_impersonating',
    'get_real_user',
    'get_displayed_user',
]
