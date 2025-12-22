# OpenAI API Key Options for Agents & Lenders

## Current Setup (Shared Key)

**Right now:** All agents and lenders share ONE OpenAI API key that you set in the `.env` file or Railway environment variables.

### How It Works:
- ✅ Simple setup - one key for everyone
- ✅ You control the costs
- ✅ Easy to manage
- ❌ You pay for all usage
- ❌ No per-user tracking
- ❌ If one user abuses it, affects everyone

### Cost Implications:
- All API costs are billed to YOUR OpenAI account
- You can't track which agent/lender used how much
- You can set usage limits in OpenAI dashboard to protect yourself

---

## Option 1: Keep Shared Key (Recommended for Now)

**Best if:**
- You want simplicity
- You're okay paying for all usage
- You trust your agents/lenders
- You want to control costs centrally

**Setup:**
- Just use the `.env` file or Railway variable
- Set usage limits in OpenAI dashboard: https://platform.openai.com/account/limits

---

## Option 2: Per-User API Keys (More Control)

**Best if:**
- You want users to pay their own costs
- You want to track usage per user
- You want more control/security

**How it works:**
- Each agent/lender enters their own OpenAI API key in their settings
- Their key is stored securely in the database
- They pay for their own usage
- You can see who has keys set up

**Implementation needed:**
- Add `openai_api_key` column to `user_profiles` table
- Add settings page for users to enter their key
- Update refinement function to check user's key first, then fall back to shared key

---

## Option 3: Hybrid Approach (Best of Both)

**How it works:**
- Users can optionally add their own API key in settings
- If they don't have one, it uses your shared key
- You can see who's using shared vs. their own key

**Benefits:**
- Default: uses your shared key (simple)
- Power users: can add their own key (more control)
- You can track who's using what

---

## Recommendation

**Start with Option 1 (Shared Key)** because:
1. Simplest to set up
2. You can always upgrade later
3. Costs are very low (~$0.0015 per refinement)
4. You can set spending limits in OpenAI

**Upgrade to Option 3 (Hybrid)** if:
- Usage gets high
- You want users to pay their own way
- You want better tracking

---

## Setting Usage Limits (Protect Yourself)

Even with a shared key, you can protect yourself:

1. Go to: https://platform.openai.com/account/limits
2. Set **Hard Limit**: Maximum you're willing to spend per month
3. Set **Soft Limit**: Get notified when you hit this amount
4. Set **Rate Limits**: Max requests per minute/day

Example limits:
- Hard Limit: $10/month (covers ~6,600 refinements!)
- Soft Limit: $5/month (get notified)
- Rate Limit: 100 requests/minute

---

## Want Per-User Keys?

I can implement Option 2 or 3 for you! It would involve:
1. Adding API key field to user settings
2. Secure storage (encrypted)
3. UI for users to enter their key
4. Fallback logic (user key → shared key → simple refinement)

Let me know if you want me to set this up!

