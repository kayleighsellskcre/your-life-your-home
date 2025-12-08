"""
Transaction Coordinator Helper Functions
Handles transaction CRUD, document uploads, auto-progression, and participant management
"""

import sqlite3
import secrets
from datetime import datetime
from typing import Optional, List, Dict, Any

def get_db():
    """Get database connection"""
    conn = sqlite3.connect('ylh.db', check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================================
# TRANSACTION MANAGEMENT
# ============================================================================

def create_transaction(agent_id: int, property_address: str, client_name: str,
                      side: str, current_stage: str = 'pre_contract',
                      target_close_date: str = None, **kwargs) -> int:
    """Create a new transaction and log timeline event"""
    transaction_id = None
    print(f"[DEBUG] Creating transaction for agent_id={agent_id}, property_address={property_address}, client_name={client_name}, side={side}, current_stage={current_stage}, target_close_date={target_close_date}")
    with get_db() as conn:
        with conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO transactions 
                (agent_id, property_address, client_name, client_email, client_phone,
                 side, current_stage, purchase_price, target_close_date, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                agent_id, property_address, client_name,
                kwargs.get('client_email', ''), kwargs.get('client_phone', ''),
                side, current_stage,
                kwargs.get('purchase_price', None), target_close_date,
                kwargs.get('notes', '')
            ))
            transaction_id = cursor.lastrowid
    # Log creation event (outside the with block to avoid nested DB writes)
    log_timeline_event(
        transaction_id, 'created',
        f"Transaction created for {property_address}",
        agent_id
    )
    return transaction_id

def get_agent_transactions(agent_id: int, status: str = 'active') -> List[Dict]:
    """Get all transactions for an agent"""
    with get_db() as conn:
        cursor = conn.cursor()
    
    cursor.execute("""
        SELECT t.*,
               COUNT(DISTINCT td.id) as document_count,
               COUNT(DISTINCT tp.id) as participant_count
        FROM transactions t
        LEFT JOIN transaction_documents td ON t.id = td.transaction_id
        LEFT JOIN transaction_participants tp ON t.id = tp.transaction_id
        WHERE t.agent_id = ? AND t.status = ?
        GROUP BY t.id
        ORDER BY t.created_at DESC
    """, (agent_id, status))
    
    transactions = [dict(row) for row in cursor.fetchall()]
    print(f"[DEBUG] get_agent_transactions(agent_id={agent_id}, status={status}) found {len(transactions)} transactions")
    return transactions

def get_transactions_by_stage(agent_id: int, stage: str) -> List[Dict]:
    """Get transactions in a specific stage"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM transactions
            WHERE agent_id = ? AND current_stage = ? AND status = 'active'
            ORDER BY target_close_date ASC
        """, (agent_id, stage))
        transactions = [dict(row) for row in cursor.fetchall()]
        return transactions

def get_transaction_detail(transaction_id: int) -> Optional[Dict]:
    """Get full transaction details"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM transactions WHERE id = ?", (transaction_id,))
        transaction = cursor.fetchone()
        if not transaction:
            return None
        result = dict(transaction)
        # Get documents
        cursor.execute("SELECT * FROM transaction_documents WHERE transaction_id = ?", (transaction_id,))
        docs = cursor.fetchall()
        result["documents"] = [dict(d) for d in docs]
        # Get participants
        cursor.execute("SELECT * FROM transaction_participants WHERE transaction_id = ?", (transaction_id,))
        participants = cursor.fetchall()
        result["participants"] = [dict(p) for p in participants]
        # Get timeline
        cursor.execute("SELECT * FROM transaction_timeline WHERE transaction_id = ? ORDER BY created_at ASC", (transaction_id,))
        timeline = cursor.fetchall()
        result["timeline"] = [dict(t) for t in timeline]
        return result

def update_transaction_stage(transaction_id: int, new_stage: str,
                            changed_by: int, auto_changed: bool = False,
                            trigger_document_id: int = None) -> bool:
    """Update transaction stage and log the change"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Get current stage
        cursor.execute("SELECT current_stage FROM transactions WHERE id = ?", (transaction_id,))
        row = cursor.fetchone()
        if not row:
            return False
        old_stage = row[0]
        # Update stage
        cursor.execute("""
            UPDATE transactions
            SET current_stage = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (new_stage, transaction_id))
        # Log stage history
        cursor.execute("""
            INSERT INTO transaction_stage_history
            (transaction_id, from_stage, to_stage, changed_by, auto_changed, trigger_document_id)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (transaction_id, old_stage, new_stage, changed_by, auto_changed, trigger_document_id))
        conn.commit()
    # Log timeline event (outside the with block to avoid nested DB writes)
    prefix = "🤖 Auto-moved" if auto_changed else "Stage changed"
    log_timeline_event(
        transaction_id, 'stage_changed',
        f"{prefix} from {old_stage.replace('_', ' ').title()} to {new_stage.replace('_', ' ').title()}",
        changed_by
    )
    return True

# ============================================================================
# DOCUMENT MANAGEMENT
# ============================================================================

def upload_transaction_document(transaction_id: int, document_type: str,
                                document_name: str, file_path: str,
                                uploaded_by: int, file_size: int = None) -> int:
    """Upload document and trigger auto-progression if applicable"""
    conn = get_db()
    cursor = conn.cursor()
    
    # Check if this document type triggers a stage change
    cursor.execute("""
        SELECT triggers_stage_change FROM document_checklists
        WHERE document_type = ? AND triggers_stage_change IS NOT NULL
        LIMIT 1
    """, (document_type,))
    
    trigger_row = cursor.fetchone()
    triggers_stage = trigger_row[0] if trigger_row else None
    
    # Insert document
    cursor.execute("""
        INSERT INTO transaction_documents
        (transaction_id, document_type, document_name, file_path, file_size,
         uploaded_by, triggers_stage_change)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (transaction_id, document_type, document_name, file_path, file_size,
          uploaded_by, triggers_stage))
    
    document_id = cursor.lastrowid
    
    # Log timeline event
    log_timeline_event(
        transaction_id, 'document_uploaded',
        f"📄 {document_name} uploaded",
        uploaded_by
    )
    
    # Auto-progress stage if applicable
    if triggers_stage:
        update_transaction_stage(
            transaction_id, triggers_stage, uploaded_by,
            auto_changed=True, trigger_document_id=document_id
        )
    
    conn.commit()
    conn.close()
    
    return document_id

def get_transaction_documents(transaction_id: int) -> List[Dict]:
    """Get all documents for a transaction"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT td.*, u.name as uploader_name
        FROM transaction_documents td
        LEFT JOIN users u ON td.uploaded_by = u.id
        WHERE td.transaction_id = ?
        ORDER BY td.uploaded_at DESC
    """, (transaction_id,))
    
    documents = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return documents

def get_document_checklist(stage: str) -> List[Dict]:
    """Get required documents for a stage"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM document_checklists
        WHERE stage = ?
        ORDER BY display_order
    """, (stage,))
    
    checklist = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return checklist

def get_transaction_document_status(transaction_id: int) -> Dict:
    """Get checklist with completion status"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Get current stage
        cursor.execute("SELECT current_stage FROM transactions WHERE id = ?", (transaction_id,))
        stage = cursor.fetchone()[0]
        # Get checklist for stage
        checklist = get_document_checklist(stage)
        # Get uploaded documents
        cursor.execute("""
            SELECT document_type FROM transaction_documents
            WHERE transaction_id = ?
        """, (transaction_id,))
        uploaded_types = {row[0] for row in cursor.fetchall()}
    # Mark completed items
    for item in checklist:
        item['completed'] = item['document_type'] in uploaded_types
    completed_count = sum(1 for item in checklist if item['completed'])
    total_count = len(checklist)
    return {
        'checklist': checklist,
        'completed': completed_count,
        'total': total_count,
        'progress_percentage': (completed_count / total_count * 100) if total_count > 0 else 0
    }

# ============================================================================
# PARTICIPANT MANAGEMENT
# ============================================================================

def add_transaction_participant(transaction_id: int, participant_type: str,
                                name: str, email: str = None, phone: str = None,
                                permissions: str = 'view_only', user_id: int = None,
                                added_by: int = None) -> int:
    """Add a participant to a transaction"""
    # Generate invitation token
    invitation_token = secrets.token_urlsafe(32)
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transaction_participants
            (transaction_id, participant_type, user_id, name, email, phone,
             permissions, invitation_token, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """, (transaction_id, participant_type, user_id, name, email, phone,
              permissions, invitation_token))
        participant_id = cursor.lastrowid
        conn.commit()
    # Log timeline event (outside the with block to avoid nested DB writes)
    log_timeline_event(
        transaction_id, 'participant_added',
        f"👥 {name} added as {participant_type.replace('_', ' ').title()}",
        added_by
    )
    return participant_id

def get_transaction_participants(transaction_id: int) -> List[Dict]:
    """Get all participants for a transaction"""
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT tp.*, u.email as user_email
        FROM transaction_participants tp
        LEFT JOIN users u ON tp.user_id = u.id
        WHERE tp.transaction_id = ? AND tp.status != 'removed'
        ORDER BY tp.added_at DESC
    """, (transaction_id,))
    
    participants = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return participants

def accept_transaction_invitation(invitation_token: str, user_id: int) -> Optional[int]:
    """Accept an invitation to join a transaction"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE transaction_participants
            SET user_id = ?, status = 'active', invitation_accepted_at = CURRENT_TIMESTAMP
            WHERE invitation_token = ?
        """, (user_id, invitation_token))
        if cursor.rowcount == 0:
            return None
        cursor.execute("""
            SELECT transaction_id FROM transaction_participants
            WHERE invitation_token = ?
        """, (invitation_token,))
        transaction_id = cursor.fetchone()[0]
        conn.commit()
        return transaction_id

# ============================================================================
# TIMELINE & ACTIVITY
# ============================================================================

def log_timeline_event(transaction_id: int, event_type: str,
                       description: str, created_by: int = None,
                       metadata: str = None):
    """Log an event to transaction timeline"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO transaction_timeline
            (transaction_id, event_type, description, created_by, metadata)
            VALUES (?, ?, ?, ?, ?)
        """, (transaction_id, event_type, description, created_by, metadata))
        conn.commit()

def get_transaction_timeline(transaction_id: int, limit: int = 50) -> List[Dict]:
    """Get timeline events for a transaction"""
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT tt.*, u.name as created_by_name
            FROM transaction_timeline tt
            LEFT JOIN users u ON tt.created_by = u.id
            WHERE tt.transaction_id = ?
            ORDER BY tt.created_at DESC
            LIMIT ?
        """, (transaction_id, limit))
    
    timeline = [dict(row) for row in cursor.fetchall()]
    conn.close()
    
    return timeline

# ============================================================================
# DASHBOARD METRICS
# ============================================================================

def get_agent_transaction_metrics(agent_id: int) -> Dict:
    """Get transaction metrics for agent dashboard"""
    with get_db() as conn:
        cursor = conn.cursor()
        # Total active transactions
        cursor.execute("""
            SELECT COUNT(*) FROM transactions
            WHERE agent_id = ? AND status = 'active'
        """, (agent_id,))
        active_count = cursor.fetchone()[0]
        # By stage
        cursor.execute("""
            SELECT current_stage, COUNT(*) as count
            FROM transactions
            WHERE agent_id = ? AND status = 'active'
            GROUP BY current_stage
        """, (agent_id,))
        by_stage = {row[0]: row[1] for row in cursor.fetchall()}
        # Closing soon (within 30 days)
        cursor.execute("""
            SELECT COUNT(*) FROM transactions
            WHERE agent_id = ? AND status = 'active'
            AND target_close_date <= date('now', '+30 days')
        """, (agent_id,))
        closing_soon = cursor.fetchone()[0]
        return {
            'active_transactions': active_count,
            'by_stage': by_stage,
            'closing_soon': closing_soon,
            'pre_contract': by_stage.get('pre_contract', 0),
            'under_contract': by_stage.get('under_contract', 0),
            'in_escrow': by_stage.get('in_escrow', 0),
            'clear_to_close': by_stage.get('clear_to_close', 0),
            'closed_this_month': by_stage.get('closed', 0)
        }

def handle_document_upload_and_auto_progression(transaction_id, document_type):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM transaction_participants
            WHERE transaction_id = ?
            ORDER BY participant_type, name
        """, (transaction_id,))
        participants = [dict(row) for row in cursor.fetchall()]
        return participants
    if document_type in progression_map:
        next_stage = progression_map[document_type]
        db.execute("UPDATE transactions SET stage = ? WHERE id = ?", (next_stage, transaction_id))
        db.commit()
        # Optionally, add to timeline
        db.execute(
            "INSERT INTO transaction_timeline (transaction_id, event, timestamp) VALUES (?, ?, datetime('now'))",
            (transaction_id, f"Stage auto-progressed to {next_stage} via {document_type}")
        )
        db.commit()

def delete_transaction(transaction_id, agent_id):
    db = get_db()
    # Ensure agent owns the transaction
    tx = db.execute("SELECT * FROM transactions WHERE id = ? AND agent_id = ?", (transaction_id, agent_id)).fetchone()
    if not tx:
        return False
    # Delete related documents, participants, timeline, then transaction
    db.execute("DELETE FROM transaction_documents WHERE transaction_id = ?", (transaction_id,))
    db.execute("DELETE FROM transaction_participants WHERE transaction_id = ?", (transaction_id,))
    db.execute("DELETE FROM transaction_timeline WHERE transaction_id = ?", (transaction_id,))
    db.execute("DELETE FROM transactions WHERE id = ?", (transaction_id,))
    db.commit()
    return True
