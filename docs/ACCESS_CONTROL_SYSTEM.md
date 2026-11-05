# Access Control & Multi-User System

## Overview
Complete access control system linking homeowners, agents, and lenders with subscription management, client relationships, and collaborative transactions.

## Key Features

### 1. Homeowner Guest Mode
- **Access**: Homeowners can use dashboard WITHOUT creating an account
- **Data Storage**: Progress stored in `guest_sessions` table
- **Conversion**: Guest data automatically transferred when they sign up
- **Referral Tracking**: If they come via agent/lender link (`?ref=CODE`), relationship is preserved

**Example Flow:**
1. Agent shares link: `https://itsyourlifeyourhome.com/homeowner?ref=ABC123`
2. Homeowner uses dashboard as guest
3. When ready, clicks "Save My Progress" → creates account
4. Guest data transfers to their account
5. Automatically linked to agent who shared the link

### 2. Agent/Lender Subscription System
- **Requirement**: Agents and lenders MUST have active subscription to access their dashboards
- **Free Trial**: 14-day trial automatically created on signup
- **Subscription Types**: 'trial', 'active', 'inactive', 'cancelled'
- **Enforcement**: `@subscription_required` decorator blocks access without subscription

**Tables:**
- `subscriptions` - Track subscription status, start/end dates, Stripe integration ready
- `users.has_active_subscription` - Quick lookup flag

### 3. Client Relationship Management
- **Unique Referral Links**: Each agent/lender gets unique code
- **Auto-Linking**: Homeowners who signup via link automatically become clients
- **Client List**: Agents/lenders see all their clients in dashboard

**Tables:**
- `client_relationships` - Links professional to homeowner
- Tracks: `professional_id`, `client_id`, `referral_code`, `status`

### 4. Transaction Collaboration System
- **Multi-Party Transactions**: Multiple agents, lenders, coordinators on same deal
- **Invite Anyone**: Send invites to agents, lenders, title companies, inspectors, custom roles
- **Shared Access**: All parties see transaction details based on permissions

**Tables:**
- `transaction_participants` - All parties involved in a transaction
- `invitations` - Pending invites with expiration
- Supports: 'agent', 'lender', 'homeowner', 'other_agent', 'transaction_coordinator', 'title_company', 'custom'

### 5. Invitation System
**Features:**
- Generate unique invite codes
- Email-based invitations
- 30-day expiration
- Custom roles supported
- Personal messages
- Accept/decline tracking

**Routes:**
- `/invite` - Send invitation form
- `/accept-invite?code=XXX` - Accept invitation link
- `/process-invitation` - Process after login/signup

## New Routes

### Authentication & Access
- `GET /subscription-required` - Landing page for subscription requirement
- `GET /homeowner?ref=CODE` - Homeowner dashboard with optional referral tracking
- Guest mode enabled (no login required)

### Invitations
- `GET/POST /invite` - Send invitation form
- `GET /accept-invite?code=CODE` - Accept invitation link
- `GET /process-invitation` - Process pending invitation

### Dashboards
- `GET /agent` - Agent dashboard (requires login + subscription)
  - Shows referral link
  - Lists clients
  - Metrics
- `GET /lender` - Lender dashboard (requires login + subscription)
  - Shows referral link
  - Lists clients
  - Metrics

## Database Schema

### New Tables
```sql
subscriptions
├── id, user_id, subscription_type, status
├── start_date, end_date, trial_ends_at
└── stripe_subscription_id

client_relationships
├── id, professional_id, professional_type
├── client_id, client_email, referral_code
└── status, created_at

transaction_participants
├── id, transaction_id, user_id, email
├── role, custom_role_name, permissions
└── invited_by, status, created_at

invitations
├── id, transaction_id, invited_by
├── invited_email, invited_role, invite_code
├── message, status, expires_at
└── accepted_at, created_at

guest_sessions
├── id, session_id, referral_code
├── data (JSON), email
└── last_activity, created_at
```

### Modified Tables
```sql
users
├── ... (existing columns)
├── referral_code (unique)
└── has_active_subscription
```

## Usage Examples

### Agent Inviting Client
```python
# 1. Agent gets their referral link
referral_code = get_or_create_referral_code(agent_user_id)
link = f"https://itsyourlifeyourhome.com/homeowner?ref={referral_code}"

# 2. Agent shares link with homeowner
# 3. Homeowner clicks link, uses dashboard (guest mode)
# 4. When homeowner signs up, automatically linked
```

### Agent Inviting Another Agent to Transaction
```python
# 1. Agent clicks "Invite" button on transaction
# 2. Fills form:
#    - Email: otheragent@example.com
#    - Role: "Other Agent (Buyer's/Seller's)"
#    - Transaction ID: "abc-123"
# 3. System generates invite code
# 4. Invite link: /accept-invite?code=INVITE123
# 5. Other agent clicks link, signs up/logs in
# 6. Automatically added to transaction
```

### Lender + Agent Collaboration
```python
# Scenario: Agent has client, wants to add lender

# 1. Agent goes to transaction detail page
# 2. Clicks "Invite Lender"
# 3. Enters lender email, role="lender"
# 4. Lender receives invite, accepts
# 5. Both agent and lender see:
#    - Shared client
#    - Transaction details
#    - Can both invite others (title, coordinator, etc.)
```

## Helper Functions

### Access Control
```python
has_active_subscription(user_id)
subscription_required  # decorator
get_or_create_referral_code(user_id)
```

### Client Management
```python
link_client_to_professional(professional_id, type, email, code)
get_client_relationships(professional_id)
```

### Guest Sessions
```python
save_guest_session_data(session_id, data, referral_code)
get_guest_session_data(session_id)
```

## Security & Permissions

### Homeowners
- ✅ Can use dashboard without account (guest mode)
- ✅ Guest data isolated by session_id
- ✅ Data transfers securely on signup
- ✅ No subscription required

### Agents & Lenders
- ✅ MUST have active subscription
- ✅ 14-day free trial on signup
- ✅ Blocked from dashboard if subscription inactive
- ✅ Can invite unlimited clients
- ✅ Can see only THEIR clients
- ✅ Can collaborate on shared transactions

### Transaction Participants
- ✅ See only transactions they're invited to
- ✅ Permissions: 'view', 'edit', 'admin'
- ✅ Can invite others if they have permission
- ✅ Email-based before they signup

## Testing Checklist

### Guest Mode
- [ ] Visit /homeowner without login
- [ ] Enter home value, loan info
- [ ] See guest mode banner
- [ ] Click "Save My Progress"
- [ ] Signup, verify data transfers

### Referral Links
- [ ] Agent gets referral link
- [ ] Homeowner clicks link (guest)
- [ ] Homeowner signs up
- [ ] Verify agent sees them in client list

### Subscription Enforcement
- [ ] Agent without subscription tries to access dashboard
- [ ] Gets redirected to /subscription-required
- [ ] Signup creates 14-day trial
- [ ] Can access dashboard

### Invitations
- [ ] Send invitation to non-user
- [ ] Click invite link
- [ ] Signup via invitation
- [ ] Verify added to transaction/relationship

### Collaboration
- [ ] Agent invites lender to transaction
- [ ] Lender accepts
- [ ] Both see shared transaction
- [ ] Both can invite others

## Future Enhancements
- [ ] Stripe payment integration
- [ ] Email notifications for invitations
- [ ] Transaction document sharing
- [ ] Real-time collaboration features
- [ ] Mobile app with same access control
- [ ] Analytics dashboard for professionals
- [ ] Client communication history
- [ ] Automated subscription renewal
- [ ] Team accounts for brokerages
- [ ] White-label options

## Migration
Run: `python scripts/migrate_access_control.py`

Creates:
- subscriptions table
- client_relationships table
- transaction_participants table
- invitations table
- guest_sessions table
- Adds referral_code to users
- Adds has_active_subscription to users
