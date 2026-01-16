"""
MFA (Multi-Factor Authentication) System
TOTP-based (Google Authenticator, Authy, etc.)
"""

import pyotp
import qrcode
from io import BytesIO
import base64
import secrets
from database import get_connection
from audit import audit_log, AuditAction

def generate_mfa_secret(user_id, user_email, issuer_name="Your Life Your Home"):
    """
    Generate TOTP secret for user and create QR code
    
    Returns:
        (secret, qr_code_base64, backup_codes)
    """
    # Generate secret
    secret = pyotp.random_base32()
    
    # Generate backup codes (10 codes, 8 characters each)
    backup_codes = [secrets.token_hex(4).upper() for _ in range(10)]
    backup_codes_str = ','.join(backup_codes)
    
    # Store in database
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO mfa_settings (user_id, method, secret, backup_codes, enabled)
        VALUES (?, 'totp', ?, ?, 0)
    """, (user_id, secret, backup_codes_str))
    conn.commit()
    conn.close()
    
    # Generate QR code
    totp = pyotp.TOTP(secret)
    provisioning_uri = totp.provisioning_uri(
        name=user_email,
        issuer_name=issuer_name
    )
    
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    qr_code = base64.b64encode(buffer.getvalue()).decode()
    
    # Log MFA setup
    audit_log(user_id, AuditAction.MFA_ENABLED, 'security', user_id, 'MFA secret generated')
    
    return secret, qr_code, backup_codes

def verify_mfa_code(user_id, code):
    """
    Verify MFA code or backup code
    
    Returns:
        (success, used_backup_code)
    """
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT secret, backup_codes, enabled 
        FROM mfa_settings 
        WHERE user_id = ?
    """, (user_id,))
    row = cur.fetchone()
    
    if not row or not row['enabled']:
        conn.close()
        return False, False
    
    # Try TOTP verification
    totp = pyotp.TOTP(row['secret'])
    if totp.verify(code, valid_window=1):
        conn.close()
        audit_log(user_id, AuditAction.MFA_VERIFIED, 'security', user_id, 'TOTP code verified')
        return True, False
    
    # Try backup codes
    if row['backup_codes']:
        backup_codes = row['backup_codes'].split(',')
        if code.upper() in backup_codes:
            # Remove used backup code
            backup_codes.remove(code.upper())
            new_backup_codes = ','.join(backup_codes)
            
            cur.execute("""
                UPDATE mfa_settings
                SET backup_codes = ?
                WHERE user_id = ?
            """, (new_backup_codes, user_id))
            conn.commit()
            conn.close()
            
            audit_log(user_id, AuditAction.MFA_VERIFIED, 'security', user_id, 'Backup code used')
            return True, True
    
    conn.close()
    audit_log(user_id, AuditAction.MFA_FAILED, 'security', user_id, 'Invalid MFA code')
    return False, False

def enable_mfa(user_id):
    """Enable MFA for user (after they've verified it works)"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE mfa_settings
        SET enabled = 1
        WHERE user_id = ?
    """, (user_id,))
    conn.commit()
    conn.close()
    
    audit_log(user_id, AuditAction.MFA_ENABLED, 'security', user_id, 'MFA enabled')

def disable_mfa(user_id, disabled_by=None):
    """Disable MFA for user"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        UPDATE mfa_settings
        SET enabled = 0
        WHERE user_id = ?
    """, (user_id,))
    conn.commit()
    conn.close()
    
    audit_log(
        disabled_by or user_id,
        AuditAction.MFA_DISABLED,
        'security',
        user_id,
        f'MFA disabled by user {disabled_by or user_id}'
    )

def is_mfa_enabled(user_id):
    """Check if MFA is enabled for user"""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT enabled FROM mfa_settings WHERE user_id = ?
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    
    return row and row['enabled']

def require_mfa_for_role(role_name):
    """Check if a role requires MFA"""
    # Owner and Admin MUST have MFA
    return role_name in ['owner', 'admin']

# Export
__all__ = [
    'generate_mfa_secret',
    'verify_mfa_code',
    'enable_mfa',
    'disable_mfa',
    'is_mfa_enabled',
    'require_mfa_for_role',
]
