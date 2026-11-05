# AI Homeowner Concierge - System Architecture

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       AI HOMEOWNER CONCIERGE SYSTEM                          │
│                     Luxury • Autonomous • Transferable                       │
└─────────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                          PUBLIC HOMEOWNER SIDE                             │
└───────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────┐
    │   QR Code or    │
    │   Direct URL    │
    └────────┬────────┘
             │
             ▼
    ┌─────────────────────────────────┐
    │  /concierge/<agent_id>          │
    │                                  │
    │  ┌────────────────────────────┐ │
    │  │  Luxury Landing Page       │ │
    │  │  • Agent Branded           │ │
    │  │  • Custom Colors           │ │
    │  │  • Welcome Message         │ │
    │  │  • Real-time Chat UI       │ │
    │  └────────────────────────────┘ │
    └──────────────┬──────────────────┘
                   │
                   │ User types message
                   │
                   ▼
    ┌─────────────────────────────────┐
    │  POST /concierge/<agent_id>/chat│
    │                                  │
    │  Request:                        │
    │  {                               │
    │    "message": "My HVAC broke",  │
    │    "session_id": "uuid..."      │
    │  }                               │
    └──────────────┬──────────────────┘
                   │
                   │
                   ▼

┌───────────────────────────────────────────────────────────────────────────┐
│                         AI PROCESSING ENGINE                               │
└───────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────┐
    │  ai_concierge.py - ConciergeAI Class        │
    │                                              │
    │  ┌────────────────────────────────────────┐ │
    │  │ 1. Get/Create Conversation             │ │
    │  │    • Session tracking                  │ │
    │  │    • Message history                   │ │
    │  └────────────────────────────────────────┘ │
    │                                              │
    │  ┌────────────────────────────────────────┐ │
    │  │ 2. OpenAI GPT-4o-mini                  │ │
    │  │    • Luxury concierge persona          │ │
    │  │    • Natural conversation              │ │
    │  │    • Context awareness                 │ │
    │  └────────────────────────────────────────┘ │
    │                                              │
    │  ┌────────────────────────────────────────┐ │
    │  │ 3. Lead Qualification                  │ │
    │  │    • Homeowner verification            │ │
    │  │    • Category detection                │ │
    │  │    • Urgency assessment                │ │
    │  │    • Contact capture                   │ │
    │  │    • Location extraction               │ │
    │  └────────────────────────────────────────┘ │
    │                                              │
    │  ┌────────────────────────────────────────┐ │
    │  │ 4. Lead Scoring                        │ │
    │  │    🔥 Hot: Ready now (1-2 weeks)       │ │
    │  │    🟡 Warm: Exploring (1-3 months)     │ │
    │  │    🧊 Cold: Future (no timeline)       │ │
    │  └────────────────────────────────────────┘ │
    │                                              │
    │  ┌────────────────────────────────────────┐ │
    │  │ 5. Vendor Routing                      │ │
    │  │    • Match category                    │ │
    │  │    • Match zip code                    │ │
    │  │    • Check active status               │ │
    │  │    • Prioritize exclusive              │ │
    │  │    • Assign via FIFO                   │ │
    │  └────────────────────────────────────────┘ │
    └─────────────────────────────────────────────┘
                   │
                   │ AI Response
                   │
                   ▼
    ┌─────────────────────────────────┐
    │  Response to Homeowner:          │
    │  {                               │
    │    "response": "I can help...",  │
    │    "session_id": "uuid...",      │
    │    "metadata": {...}             │
    │  }                               │
    └─────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                            DATABASE LAYER                                  │
└───────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────┐
    │  SQLite Database (ylh.db)                                            │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐   │
    │  │ concierge_settings                                            │   │
    │  │ • agent_id                                                    │   │
    │  │ • branding_name, branding_tagline                            │   │
    │  │ • primary_color, secondary_color                             │   │
    │  │ • welcome_message                                            │   │
    │  │ • openai_api_key                                             │   │
    │  │ • is_active                                                  │   │
    │  └──────────────────────────────────────────────────────────────┘   │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐   │
    │  │ concierge_vendors                                             │   │
    │  │ • name, category, contact_name                               │   │
    │  │ • phone, email, website                                      │   │
    │  │ • service_area_zips                                          │   │
    │  │ • monthly_fee (default $400)                                 │   │
    │  │ • subscription_status (active/paused/cancelled)              │   │
    │  │ • is_exclusive, seats_limit                                  │   │
    │  └──────────────────────────────────────────────────────────────┘   │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐   │
    │  │ concierge_homeowners                                          │   │
    │  │ • name, email, phone, address, zip_code                      │   │
    │  │ • is_homeowner, ownership_length_years                       │   │
    │  │ • lead_score (hot/warm/cold)                                 │   │
    │  │ • first_contact_at, last_contact_at                          │   │
    │  └──────────────────────────────────────────────────────────────┘   │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐   │
    │  │ concierge_conversations                                       │   │
    │  │ • session_id (UUID)                                          │   │
    │  │ • homeowner_id (FK)                                          │   │
    │  │ • status (active/completed/abandoned)                        │   │
    │  │ • lead_captured (boolean)                                    │   │
    │  │ • started_at, last_message_at                                │   │
    │  └──────────────────────────────────────────────────────────────┘   │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐   │
    │  │ concierge_messages                                            │   │
    │  │ • conversation_id (FK)                                       │   │
    │  │ • role (user/assistant/system)                               │   │
    │  │ • content (full text)                                        │   │
    │  │ • metadata (JSON)                                            │   │
    │  │ • created_at                                                 │   │
    │  └──────────────────────────────────────────────────────────────┘   │
    │                                                                       │
    │  ┌──────────────────────────────────────────────────────────────┐   │
    │  │ concierge_leads                                               │   │
    │  │ • homeowner_id, vendor_id (FKs)                              │   │
    │  │ • category, urgency (ready_now/exploring/future)             │   │
    │  │ • description, timeline_weeks, zip_code                      │   │
    │  │ • status (new/sent_to_vendor/contacted/closed/lost)          │   │
    │  │ • routed_at, contacted_at, closed_at                         │   │
    │  └──────────────────────────────────────────────────────────────┘   │
    └───────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                        AGENT DASHBOARD SIDE                                │
└───────────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────┐
    │  /agent/concierge - Main Dashboard                                   │
    │                                                                       │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                 │
    │  │ Total Convs │  │    Leads    │  │     MRR     │                 │
    │  │    125      │  │     48      │  │   $5,400    │                 │
    │  │ 12 active   │  │  15 hot 🔥  │  │  9 vendors  │                 │
    │  └─────────────┘  └─────────────┘  └─────────────┘                 │
    │                                                                       │
    │  ┌─────────────────────────────────────────────────────────────┐    │
    │  │ Your Concierge URL                                           │    │
    │  │ https://yoursite.com/concierge/123                          │    │
    │  │ [Copy] [Preview]                                            │    │
    │  └─────────────────────────────────────────────────────────────┘    │
    │                                                                       │
    │  ┌─────────────────────────────────────────────────────────────┐    │
    │  │ Recent Leads                                                 │    │
    │  │ ─────────────────────────────────────────────────────────── │    │
    │  │ John D. | HVAC | 🔥 Ready Now | ABC Heating | New          │    │
    │  │ Sarah M. | Plumbing | 🟡 Exploring | XYZ Plumbing | Sent   │    │
    │  │ Mike K. | Roofing | 🧊 Future | - | New                    │    │
    │  └─────────────────────────────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────┐
    │  /agent/concierge/settings - Configuration                           │
    │                                                                       │
    │  Branding:                         Preview:                          │
    │  ┌──────────────────────┐         ┌──────────────────┐              │
    │  │ Name: [Your Home...] │         │  Your Home Con-  │              │
    │  │ Tagline: [Answers...] │         │     cierge      │              │
    │  │ Primary: [#1a1a1a]   │         │ Answers, guid-   │              │
    │  │ Secondary: [#f5f5f5] │         │ ance, and local  │              │
    │  │ Welcome: [How can..] │         │   connections    │              │
    │  └──────────────────────┘         └──────────────────┘              │
    │                                                                       │
    │  AI Configuration:                                                    │
    │  ┌──────────────────────────────────────┐                           │
    │  │ OpenAI API Key: [sk-...............]  │                           │
    │  │ ☑ AI Concierge Active                │                           │
    │  └──────────────────────────────────────┘                           │
    │                                                                       │
    │  [Save Settings]                                                      │
    └─────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────┐
    │  /agent/concierge/vendors - Vendor Management                        │
    │                                                                       │
    │  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐  │
    │  │ ABC Heating      │  │ XYZ Plumbing     │  │ Elite Roofing    │  │
    │  │ HVAC             │  │ Plumbing         │  │ Roofing          │  │
    │  │ ─────────────    │  │ ─────────────    │  │ ─────────────    │  │
    │  │ Status: ✅ Active│  │ Status: ✅ Active│  │ Status: ⏸ Paused │  │
    │  │ Fee: $600/mo     │  │ Fee: $500/mo     │  │ Fee: $650/mo     │  │
    │  │ ─────────────    │  │ ─────────────    │  │ ─────────────    │  │
    │  │ Leads: 18        │  │ Leads: 12        │  │ Leads: 8         │  │
    │  │ Closed: 7        │  │ Closed: 5        │  │ Closed: 3        │  │
    │  └──────────────────┘  └──────────────────┘  └──────────────────┘  │
    │                                                                       │
    │  [+ Add Vendor]                                                       │
    └─────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────┐
    │  /agent/concierge/leads - Lead Tracking                              │
    │                                                                       │
    │  Filters: [Urgency: All ▼] [Status: All ▼] [Clear]                  │
    │                                                                       │
    │  ┌─────────────────────────────────────────────────────────────┐    │
    │  │ Homeowner | Category | Urgency | Vendor | Status | Date     │    │
    │  │ ──────────────────────────────────────────────────────────── │    │
    │  │ John Doe  | HVAC     | 🔥 Hot  | ABC    | Sent  | 2/7/26   │    │
    │  │ Sarah M.  | Plumbing | 🟡 Warm | XYZ    | New   | 2/6/26   │    │
    │  │ Mike K.   | Roofing  | 🧊 Cold | -      | New   | 2/5/26   │    │
    │  └─────────────────────────────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────────────────┘

    ┌─────────────────────────────────────────────────────────────────────┐
    │  /agent/concierge/conversations - Conversation List                  │
    │                                                                       │
    │  ┌─────────────────────────────────────────────────────────────┐    │
    │  │ Homeowner | Status | Lead? | Started | Last Activity        │    │
    │  │ ──────────────────────────────────────────────────────────── │    │
    │  │ John Doe  | Active | ✅    | 2/7 9am | 2/7 9:15am          │    │
    │  │ Sarah M.  | Done   | ✅    | 2/6 3pm | 2/6 3:22pm          │    │
    │  │ Anonymous | Active | ❌    | 2/5 1pm | 2/5 1:05pm          │    │
    │  └─────────────────────────────────────────────────────────────┘    │
    └─────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                            DATA FLOW SUMMARY                               │
└───────────────────────────────────────────────────────────────────────────┘

1. HOMEOWNER VISITS
   → Landing page loads with agent branding
   → Session created

2. HOMEOWNER CHATS
   → Message sent to AI engine
   → OpenAI processes with context
   → Response returned
   → Message saved to database

3. AI QUALIFIES
   → Detects homeowner status
   → Identifies service category
   → Assesses urgency level
   → Captures contact info
   → Extracts location

4. LEAD CREATED
   → Lead record created
   → Vendor matched by category + zip
   → Lead assigned to vendor
   → Agent notified

5. AGENT MONITORS
   → Views lead in dashboard
   → Checks conversation transcript
   → Tracks vendor performance
   → Collects monthly fees

┌───────────────────────────────────────────────────────────────────────────┐
│                         REVENUE FLOW                                       │
└───────────────────────────────────────────────────────────────────────────┘

    Vendor 1 (HVAC)        → $600/mo
    Vendor 2 (Plumbing)    → $500/mo
    Vendor 3 (Electrical)  → $550/mo
    Vendor 4 (Roofing)     → $650/mo
    Vendor 5 (Landscaping) → $450/mo
                              ─────────
    Total MRR:             → $2,750/mo
    Annual Revenue:        → $33,000/yr

    All tracked automatically in dashboard ✅

┌───────────────────────────────────────────────────────────────────────────┐
│                           KEY FEATURES                                     │
└───────────────────────────────────────────────────────────────────────────┘

✅ Luxury Design - Premium homeowner experience
✅ White-Label - Fully branded per agent
✅ AI-Powered - Natural conversation flow
✅ Auto-Qualification - No manual screening
✅ Auto-Routing - Vendor matching by zip + category
✅ Lead Scoring - Hot/Warm/Cold classification
✅ MRR Tracking - Real-time revenue dashboard
✅ Performance Metrics - Vendor analytics
✅ Conversation History - Full transcripts
✅ Mobile Responsive - Works on all devices
✅ Session Tracking - Anonymous and identified users
✅ Transferable - White-label = easy handoff
✅ Scalable - Add unlimited vendors
✅ Autonomous - Runs 24/7 without supervision

┌───────────────────────────────────────────────────────────────────────────┐
│                        TECHNICAL STACK                                     │
└───────────────────────────────────────────────────────────────────────────┘

Backend:
  • Python 3.12+
  • Flask (web framework)
  • SQLite (database)
  • OpenAI API (AI engine)

Frontend:
  • HTML5
  • Vanilla JavaScript
  • CSS3 (responsive design)
  • No framework dependencies

Hosting:
  • Railway (or any Python host)
  • Persistent volume (database)
  • Environment variables (API keys)

┌───────────────────────────────────────────────────────────────────────────┐
│                         FILE STRUCTURE                                     │
└───────────────────────────────────────────────────────────────────────────┘

app.py
  └── 10 new routes (lines 9500+)

ai_concierge.py (NEW)
  ├── ConciergeAI class
  ├── chat() - Main conversation handler
  ├── get_concierge_stats() - Dashboard metrics
  ├── get_recent_leads() - Lead tracking
  └── get_vendor_performance() - Analytics

database.py
  └── 8 new tables (lines 266-500+)

templates/
  ├── concierge/
  │   └── landing.html (NEW)
  └── agent/
      ├── concierge_dashboard.html (NEW)
      ├── concierge_settings.html (NEW)
      ├── concierge_vendors.html (NEW)
      ├── concierge_leads.html (NEW)
      ├── concierge_conversations.html (NEW)
      └── concierge_conversation_detail.html (NEW)

Documentation/
  ├── AI_CONCIERGE_DOCUMENTATION.md (Complete guide)
  ├── AI_CONCIERGE_QUICK_SETUP.md (Getting started)
  ├── AI_CONCIERGE_SUMMARY.md (Feature overview)
  ├── AI_CONCIERGE_CHECKLIST.md (Pre-launch tasks)
  └── AI_CONCIERGE_ARCHITECTURE.md (This file)

┌───────────────────────────────────────────────────────────────────────────┐
│                            STATUS                                          │
└───────────────────────────────────────────────────────────────────────────┘

✅ Code Complete
✅ No Linter Errors
✅ Fully Tested
✅ Documentation Complete
✅ Production Ready

Ready for immediate deployment!
