# AI Concierge Quick Setup Guide

## 1. Install OpenAI Package

```bash
pip install openai
```

## 2. Database Setup

The database tables are automatically created when you first run the app. The schema includes:

- `concierge_vendors` - Subscription-based vendors
- `concierge_homeowners` - Homeowner contacts
- `concierge_conversations` - Chat sessions
- `concierge_messages` - Message history
- `concierge_leads` - Qualified leads
- `concierge_settings` - White-label configuration

## 3. First-Time Configuration

### As an Agent:

1. **Login to your agent account**
   
2. **Navigate to AI Concierge**
   - Click "🤖 AI Concierge" in the navigation bar

3. **Configure Settings** (`/agent/concierge/settings`)
   - Add your OpenAI API key ([Get one here](https://platform.openai.com/api-keys))
   - Customize branding:
     - Concierge name (e.g., "Luxury Home Concierge")
     - Tagline
     - Colors
     - Welcome message
   - Toggle "AI Concierge Active" to ON

4. **Add Your First Vendor** (`/agent/concierge/vendors`)
   - Click "Add Vendor"
   - Fill in:
     - Business name
     - Category (HVAC, Plumbing, etc.)
     - Contact info
     - Service area zip codes
     - Monthly fee (default $400)
   - Submit

5. **Get Your Concierge URL**
   - Back on dashboard: `/agent/concierge`
   - Copy your unique URL
   - Share via:
     - QR code
     - Website embed
     - Social media
     - Email signature

## 4. Test the System

1. **Open your concierge URL** in an incognito window
2. **Start a conversation**:
   - "My HVAC isn't working properly"
   - Answer questions naturally
   - Provide contact info when prompted
3. **Check your dashboard**:
   - See the conversation logged
   - View the qualified lead
   - See vendor assignment

## 5. URLs Reference

### Public Facing:
- **Landing Page**: `/concierge/<your_agent_id>`
- **Chat API**: `/concierge/<your_agent_id>/chat` (POST)

### Agent Dashboard:
- **Main Dashboard**: `/agent/concierge`
- **Settings**: `/agent/concierge/settings`
- **Vendors**: `/agent/concierge/vendors`
- **Leads**: `/agent/concierge/leads`
- **Conversations**: `/agent/concierge/conversations`

## 6. OpenAI API Key Setup

### Option 1: Per-Agent (Recommended)
- Each agent adds their own API key in settings
- Keeps billing separate
- Easy to transfer

### Option 2: Global (Environment Variable)
- Set `OPENAI_API_KEY` environment variable
- All agents use same key
- Simpler for single-agent setups

## 7. Vendor Onboarding Process

1. **Identify potential vendors** in your area
2. **Pitch the value**:
   - Only receive qualified leads
   - Pre-screened homeowners
   - Context and urgency provided
   - $400-750/month subscription
3. **Add to system** via vendor management
4. **Set to active** to start receiving leads
5. **Monitor performance** monthly

## 8. Revenue Tracking

The dashboard automatically calculates:
- Monthly Recurring Revenue (MRR)
- Active vendor count
- Lead volume by urgency
- Vendor performance metrics

## 9. White-Label Transfer

To hand off to another agent:

1. **Update settings** with new branding
2. **Change OpenAI API key** (optional)
3. **Transfer vendor relationships**
4. **Update billing information**
5. **Provide new concierge URL**

Done! System continues running autonomously.

## 10. Troubleshooting

### "AI not responding"
- Check OpenAI API key is valid
- Verify key has available credits
- Check conversation detail for error messages

### "No leads being routed"
- Verify vendors are status = "active"
- Check service area zip codes match
- Ensure category names match exactly

### "Can't access landing page"
- Verify agent ID in URL is correct
- Check "AI Concierge Active" is ON in settings
- Try incognito/private browsing mode

## 11. Next Steps (Optional)

### Phase 2 Enhancements:
- **Vendor Portal**: Self-service lead management
- **Payment Integration**: Stripe auto-billing
- **Advanced Analytics**: Conversion funnels
- **Appointment Scheduling**: Calendar integration

See `AI_CONCIERGE_DOCUMENTATION.md` for complete details.

---

**Ready to Go!**

Your AI Concierge system is fully operational. Start by configuring your settings and adding vendors, then share your URL to start receiving qualified leads automatically.
