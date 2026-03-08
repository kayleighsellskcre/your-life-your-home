"""
AI Homeowner Concierge System
Luxury-grade, automated lead qualification and vendor routing
"""

import os
import json
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
from database import get_connection, row_to_dict, rows_to_dicts

# OpenAI integration will be handled per-agent using their stored API keys
try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


class ConciergeAI:
    """
    AI Concierge that handles homeowner conversations with luxury feel.
    Qualifies leads, routes to vendors, captures contact info naturally.
    """
    
    SYSTEM_PROMPT = """You are a luxury homeowner concierge assistant. Your role is to:

1. Help homeowners with questions about home maintenance, upgrades, and planning
2. Naturally gather qualifying information through conversation (never interrogate)
3. Match them with trusted local professionals when they express a need
4. Maintain a calm, helpful, premium tone - never pushy or salesy

QUALIFICATION PROCESS (gather naturally):
- Confirm they are a homeowner (vs renter)
- Understand their need/project
- Assess urgency (immediate, next few weeks, exploring for later)
- Get basic location (zip code is enough)
- Capture contact info when appropriate (only when they're ready to connect with someone)

LEAD SCORING:
- HOT 🔥: Ready now, timeline within 2 weeks, budget confirmed or implied
- WARM 🟡: Exploring actively, timeline 1-3 months, gathering quotes
- COLD 🧊: Just learning, no timeline, future consideration

TONE RULES:
- Conversational and warm, not robotic
- No bullet points or formal language
- Use "you" and "your" - make it personal
- Keep responses concise (2-3 sentences max usually)
- Never say "I'm an AI" - you're a concierge

NEVER:
- Ask multiple questions at once
- Use forms or bullet points
- Pressure for contact info
- Make promises about vendors
- Discuss pricing (vendors will handle that)

When a homeowner expresses interest in connecting with a professional, ask for their contact info naturally and confirm you'll have someone reach out shortly."""

    def __init__(self, agent_id: int):
        self.agent_id = agent_id
        self.api_key = self._get_api_key()
        
    def _get_api_key(self) -> Optional[str]:
        """Get agent's OpenAI API key from settings"""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT openai_api_key FROM concierge_settings WHERE agent_id = ?", (self.agent_id,))
        row = cur.fetchone()
        conn.close()
        
        if row and row['openai_api_key']:
            return row['openai_api_key']
        
        # Fallback to environment variable
        return os.environ.get('OPENAI_API_KEY')
    
    def get_or_create_conversation(self, session_id: str, visitor_ip: Optional[str] = None) -> int:
        """Get existing conversation or create new one"""
        conn = get_connection()
        cur = conn.cursor()
        
        # Check if conversation exists
        cur.execute(
            "SELECT id FROM concierge_conversations WHERE session_id = ? AND agent_id = ?",
            (session_id, self.agent_id)
        )
        row = cur.fetchone()
        
        if row:
            # Update last message time
            cur.execute(
                "UPDATE concierge_conversations SET last_message_at = ? WHERE id = ?",
                (datetime.now().isoformat(), row['id'])
            )
            conn.commit()
            conversation_id = row['id']
        else:
            # Create new conversation
            cur.execute(
                """INSERT INTO concierge_conversations 
                (agent_id, session_id, visitor_ip, started_at, last_message_at)
                VALUES (?, ?, ?, ?, ?)""",
                (self.agent_id, session_id, visitor_ip, 
                 datetime.now().isoformat(), datetime.now().isoformat())
            )
            conn.commit()
            conversation_id = cur.lastrowid
        
        conn.close()
        return conversation_id
    
    def get_conversation_history(self, conversation_id: int, limit: int = 20) -> List[Dict]:
        """Get recent messages from conversation"""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """SELECT role, content, created_at FROM concierge_messages 
            WHERE conversation_id = ? 
            ORDER BY id DESC LIMIT ?""",
            (conversation_id, limit)
        )
        messages = rows_to_dicts(cur.fetchall())
        conn.close()
        
        # Reverse so oldest first
        return list(reversed(messages))
    
    def save_message(self, conversation_id: int, role: str, content: str, metadata: Optional[Dict] = None):
        """Save a message to the conversation"""
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """INSERT INTO concierge_messages 
            (conversation_id, role, content, metadata, created_at)
            VALUES (?, ?, ?, ?, ?)""",
            (conversation_id, role, content, 
             json.dumps(metadata) if metadata else None,
             datetime.now().isoformat())
        )
        conn.commit()
        conn.close()
    
    def chat(self, session_id: str, user_message: str, visitor_ip: Optional[str] = None) -> Tuple[str, Dict]:
        """
        Process a user message and return AI response + metadata
        Returns: (response_text, metadata_dict)
        """
        if not OPENAI_AVAILABLE or not self.api_key:
            return (
                "I'm here to help! However, the AI service needs to be configured. Please contact your administrator.",
                {"error": "openai_not_configured"}
            )
        
        # Get or create conversation
        conversation_id = self.get_or_create_conversation(session_id, visitor_ip)
        
        # Save user message
        self.save_message(conversation_id, "user", user_message)
        
        # Get conversation history
        history = self.get_conversation_history(conversation_id)
        
        # Build messages for OpenAI
        messages = [{"role": "system", "content": self.SYSTEM_PROMPT}]
        
        for msg in history:
            if msg['role'] in ['user', 'assistant']:
                messages.append({
                    "role": msg['role'],
                    "content": msg['content']
                })
        
        try:
            # Call OpenAI
            print(f"[AI CONCIERGE] Calling OpenAI API...")
            client = openai.OpenAI(api_key=self.api_key)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=300
            )
            
            assistant_message = response.choices[0].message.content
            print(f"[AI CONCIERGE] Got response from OpenAI: {assistant_message[:100]}...")
            
            # Save assistant response
            self.save_message(conversation_id, "assistant", assistant_message)
            
            # Analyze for qualification signals
            metadata = self._analyze_conversation(conversation_id, user_message, assistant_message)
            
            return (assistant_message, metadata)
            
        except Exception as e:
            print(f"[AI CONCIERGE ERROR] {type(e).__name__}: {str(e)}")
            import traceback
            traceback.print_exc()
            error_msg = "I apologize, but I'm having trouble processing your request right now. Please try again in a moment."
            return (error_msg, {"error": str(e)})
    
    def _analyze_conversation(self, conversation_id: int, user_message: str, assistant_message: str) -> Dict:
        """
        Analyze conversation for qualification signals and lead scoring.
        Returns metadata about the conversation state.
        """
        metadata = {
            "conversation_id": conversation_id,
            "timestamp": datetime.now().isoformat()
        }
        
        # Simple keyword detection for qualification (can be enhanced with AI later)
        user_lower = user_message.lower()
        
        # Detect need/urgency keywords
        urgent_keywords = ['asap', 'urgent', 'emergency', 'broken', 'not working', 'right away', 'immediately']
        exploring_keywords = ['thinking about', 'considering', 'looking into', 'might need', 'eventually']
        
        if any(word in user_lower for word in urgent_keywords):
            metadata['urgency_signal'] = 'high'
        elif any(word in user_lower for word in exploring_keywords):
            metadata['urgency_signal'] = 'low'
        
        # Detect service categories
        categories = {
            'hvac': ['hvac', 'heating', 'cooling', 'furnace', 'air conditioning', 'ac unit'],
            'plumbing': ['plumbing', 'plumber', 'leak', 'pipes', 'water heater', 'drain'],
            'electrical': ['electrical', 'electrician', 'wiring', 'outlet', 'circuit breaker'],
            'roofing': ['roof', 'roofing', 'shingles', 'gutters'],
            'landscaping': ['landscaping', 'lawn', 'yard', 'garden', 'trees'],
            'painting': ['painting', 'painter', 'paint'],
            'flooring': ['flooring', 'floors', 'carpet', 'hardwood', 'tile'],
            'remodeling': ['remodel', 'renovation', 'kitchen', 'bathroom', 'addition'],
        }
        
        detected_categories = []
        for category, keywords in categories.items():
            if any(word in user_lower for word in keywords):
                detected_categories.append(category)
        
        if detected_categories:
            metadata['detected_categories'] = detected_categories
        
        # Detect contact info sharing
        if '@' in user_message or any(char.isdigit() for char in user_message if user_message.count(char) >= 3):
            metadata['contact_info_shared'] = True
        
        return metadata
    
    def create_lead(
        self, 
        homeowner_id: int, 
        conversation_id: int,
        category: str,
        urgency: str = 'exploring',
        description: str = '',
        zip_code: Optional[str] = None,
        timeline_weeks: Optional[int] = None
    ) -> int:
        """Create a qualified lead and attempt to route to a vendor"""
        conn = get_connection()
        cur = conn.cursor()
        
        # Create the lead
        cur.execute(
            """INSERT INTO concierge_leads
            (agent_id, homeowner_id, conversation_id, category, urgency, 
             description, zip_code, timeline_weeks, routed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (self.agent_id, homeowner_id, conversation_id, category, urgency,
             description, zip_code, timeline_weeks, datetime.now().isoformat())
        )
        lead_id = cur.lastrowid
        
        # Try to route to a vendor
        vendor_id = self._find_matching_vendor(category, zip_code)
        if vendor_id:
            cur.execute(
                "UPDATE concierge_leads SET vendor_id = ?, status = 'sent_to_vendor' WHERE id = ?",
                (vendor_id, lead_id)
            )
        
        conn.commit()
        conn.close()
        
        return lead_id
    
    def _find_matching_vendor(self, category: str, zip_code: Optional[str] = None) -> Optional[int]:
        """Find best matching vendor for a lead"""
        conn = get_connection()
        cur = conn.cursor()
        
        # Find active vendors in this category
        query = """
            SELECT id, service_area_zips FROM concierge_vendors
            WHERE agent_id = ? AND category = ? AND subscription_status = 'active'
            ORDER BY is_exclusive DESC, onboarded_at ASC
        """
        cur.execute(query, (self.agent_id, category))
        vendors = rows_to_dicts(cur.fetchall())
        conn.close()
        
        if not vendors:
            return None
        
        # If zip code provided, try to match service area
        if zip_code:
            for vendor in vendors:
                if vendor['service_area_zips']:
                    zips = vendor['service_area_zips'].split(',')
                    if zip_code in [z.strip() for z in zips]:
                        return vendor['id']
        
        # Default to first active vendor
        return vendors[0]['id']


# Helper functions for agent dashboard

def get_concierge_stats(agent_id: int) -> Dict:
    """Get overview statistics for the AI concierge system"""
    conn = get_connection()
    cur = conn.cursor()
    
    # Total conversations
    cur.execute(
        "SELECT COUNT(*) as count FROM concierge_conversations WHERE agent_id = ?",
        (agent_id,)
    )
    total_conversations = cur.fetchone()['count']
    
    # Active conversations (last 24 hours)
    yesterday = (datetime.now() - timedelta(days=1)).isoformat()
    cur.execute(
        "SELECT COUNT(*) as count FROM concierge_conversations WHERE agent_id = ? AND last_message_at > ?",
        (agent_id, yesterday)
    )
    active_conversations = cur.fetchone()['count']
    
    # Total leads
    cur.execute(
        "SELECT COUNT(*) as count FROM concierge_leads WHERE agent_id = ?",
        (agent_id,)
    )
    total_leads = cur.fetchone()['count']
    
    # Hot leads
    cur.execute(
        "SELECT COUNT(*) as count FROM concierge_leads WHERE agent_id = ? AND urgency = 'ready_now'",
        (agent_id,)
    )
    hot_leads = cur.fetchone()['count']
    
    # Active vendors
    cur.execute(
        "SELECT COUNT(*) as count FROM concierge_vendors WHERE agent_id = ? AND subscription_status = 'active'",
        (agent_id,)
    )
    active_vendors = cur.fetchone()['count']
    
    # Monthly recurring revenue
    cur.execute(
        "SELECT SUM(monthly_fee) as mrr FROM concierge_vendors WHERE agent_id = ? AND subscription_status = 'active'",
        (agent_id,)
    )
    row = cur.fetchone()
    mrr = row['mrr'] or 0
    
    conn.close()
    
    return {
        'total_conversations': total_conversations,
        'active_conversations': active_conversations,
        'total_leads': total_leads,
        'hot_leads': hot_leads,
        'active_vendors': active_vendors,
        'monthly_revenue': mrr
    }


def get_recent_leads(agent_id: int, limit: int = 10) -> List[Dict]:
    """Get recent leads with homeowner and vendor details"""
    conn = get_connection()
    cur = conn.cursor()
    
    query = """
        SELECT 
            l.*,
            h.name as homeowner_name,
            h.email as homeowner_email,
            h.phone as homeowner_phone,
            v.name as vendor_name,
            v.contact_name as vendor_contact
        FROM concierge_leads l
        LEFT JOIN concierge_homeowners h ON l.homeowner_id = h.id
        LEFT JOIN concierge_vendors v ON l.vendor_id = v.id
        WHERE l.agent_id = ?
        ORDER BY l.routed_at DESC
        LIMIT ?
    """
    cur.execute(query, (agent_id, limit))
    leads = rows_to_dicts(cur.fetchall())
    conn.close()
    
    return leads


def get_vendor_performance(agent_id: int) -> List[Dict]:
    """Get performance metrics for each vendor"""
    conn = get_connection()
    cur = conn.cursor()
    
    query = """
        SELECT 
            v.id,
            v.name,
            v.category,
            v.monthly_fee,
            v.subscription_status,
            COUNT(l.id) as leads_received,
            SUM(CASE WHEN l.status = 'closed' THEN 1 ELSE 0 END) as leads_closed
        FROM concierge_vendors v
        LEFT JOIN concierge_leads l ON v.id = l.vendor_id
        WHERE v.agent_id = ?
        GROUP BY v.id
        ORDER BY v.category, v.name
    """
    cur.execute(query, (agent_id,))
    vendors = rows_to_dicts(cur.fetchall())
    conn.close()
    
    return vendors
