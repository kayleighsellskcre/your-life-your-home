"""
ai_platform.py — Central AI utility for Your Life Your Home

All AI features across the platform call ai_complete() from here.
This keeps model selection, error handling, and key management in one place.
"""

import os
from typing import Optional

_DEFAULT_MODEL = "gpt-4o-mini"
_FAST_MODEL    = "gpt-4o-mini"


def _get_key() -> Optional[str]:
    """Return the OpenAI API key from environment."""
    return os.environ.get("OPENAI_API_KEY")


def ai_complete(
    prompt: str,
    system: str = "You are a helpful real estate assistant.",
    model: str = _DEFAULT_MODEL,
    max_tokens: int = 600,
    temperature: float = 0.7,
) -> str:
    """
    Call OpenAI and return the text response.
    Returns an empty string on failure — callers handle graceful fallback.
    """
    key = _get_key()
    if not key:
        return ""
    try:
        from openai import OpenAI
        # 20-second hard timeout — prevents the server from hanging when OpenAI is slow
        client = OpenAI(api_key=key, timeout=20.0)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": prompt},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return (response.choices[0].message.content or "").strip()
    except Exception as e:
        print(f"[AI] Error: {e}")
        return ""


# Backwards-compat alias used by financials routes
call_ai = ai_complete


# ─────────────────────────────────────────────────────────────
# HIGH-LEVEL AI FUNCTIONS
# Each function is domain-specific and called from app.py routes
# ─────────────────────────────────────────────────────────────

def ai_dashboard_briefing(agent_name: str, metrics: dict, followups: list, tasks: list) -> str:
    """
    Generate a personalized morning briefing for the agent's dashboard.
    metrics: dict with new_leads, active, pending_tasks, etc.
    followups: list of contact names needing follow-up
    tasks: list of pending task titles
    """
    followup_str = ", ".join(followups[:5]) if followups else "none"
    prompt = (
        f"Write a short, electric motivational quote (max 18 words) to start {agent_name}'s real estate day. "
        f"Make it feel like a best friend cheering them on, not a corporate slogan. "
        f"It should feel personal, warm, and exciting. "
        f"Rules: no em dashes, no bullet points, no greeting, no exclamation mark at the very start, end with exactly one exclamation mark, no quotes around the text."
    )
    return ai_complete(prompt, system="You are an enthusiastic, warm, uplifting real estate coach. Never use em dashes, mdashes, or quotation marks around your response.", max_tokens=55, temperature=0.85)


def ai_draft_email(contact_name: str, contact_stage: str, contact_notes: str,
                    recent_interactions: list, agent_name: str, agent_phone: str,
                    context: str = "") -> str:
    """
    Draft a personalized email for a CRM contact.
    Returns the email body (plain text, ready to copy).
    """
    interactions_str = ""
    if recent_interactions:
        interactions_str = " | ".join([
            f"{i.get('interaction_type','note')}: {i.get('notes','')[:80]}"
            for i in recent_interactions[:3]
        ])
    prompt = (
        f"Draft a short, personalized, warm real estate email from {agent_name} to {contact_name}. "
        f"This contact is currently in the '{contact_stage}' stage of the pipeline. "
        f"Recent contact notes: {contact_notes[:200] if contact_notes else 'none'}. "
        f"Recent interactions: {interactions_str or 'none'}. "
        f"Additional context: {context or 'general check-in'}. "
        f"Write only the email body — no subject line, no 'Subject:' prefix. "
        f"Keep it to 3-4 sentences. Sound like a real person. End with a warm sign-off and include {agent_name}'s name. "
        f"Phone: {agent_phone}. Do not use em dashes."
    )
    return ai_complete(
        prompt,
        system="You are a warm, professional real estate agent writing a personal email. Keep it brief and human.",
        max_tokens=300,
        temperature=0.75
    )


def ai_next_action(contact_name: str, contact_stage: str, contact_notes: str,
                    recent_interactions: list, days_since_contact: int) -> dict:
    """
    Suggest the best next action for a CRM contact.
    Returns dict with: action (string), reason (string), urgency ('low'/'medium'/'high')
    """
    interactions_str = " | ".join([
        f"{i.get('interaction_type','')}: {i.get('notes','')[:60]}"
        for i in recent_interactions[:3]
    ]) if recent_interactions else "none"
    prompt = (
        f"A real estate agent has a contact named {contact_name} who is in the '{contact_stage}' pipeline stage. "
        f"It has been {days_since_contact} days since last contact. "
        f"Notes: {contact_notes[:150] if contact_notes else 'none'}. "
        f"Recent interactions: {interactions_str}. "
        f"Respond in this exact format:\n"
        f"ACTION: (one clear, specific action to take — call, text, email, or meet)\n"
        f"REASON: (one sentence explaining why this action makes sense right now)\n"
        f"URGENCY: (exactly one word: low, medium, or high)"
    )
    result = ai_complete(
        prompt,
        system="You are a real estate sales coach. Give direct, specific advice.",
        max_tokens=120,
        temperature=0.5
    )
    action, reason, urgency = "", "", "medium"
    for line in result.splitlines():
        if line.startswith("ACTION:"):
            action = line[7:].strip()
        elif line.startswith("REASON:"):
            reason = line[7:].strip()
        elif line.startswith("URGENCY:"):
            urgency = line[8:].strip().lower()
    return {"action": action, "reason": reason, "urgency": urgency}


def ai_personalize_template(template_text: str, contact_name: str, contact_stage: str,
                              agent_name: str, context: str = "") -> str:
    """
    Take a communication template and personalize it for a specific contact.
    Returns the personalized version ready to use.
    """
    prompt = (
        f"Personalize this real estate communication template for {contact_name}, who is in the '{contact_stage}' stage. "
        f"Agent name: {agent_name}. Context: {context or 'standard outreach'}. "
        f"Replace any generic placeholders with specific, natural language. Keep the same length and tone. "
        f"Do not add extra content or explanations. Output only the personalized message.\n\n"
        f"TEMPLATE:\n{template_text}"
    )
    return ai_complete(
        prompt,
        system="You are personalizing a real estate message template. Output only the message.",
        max_tokens=400,
        temperature=0.65
    )


def ai_transaction_tasks(property_address: str, client_name: str, side: str,
                          stage: str, close_date: str) -> list:
    """
    Generate a checklist of tasks for a transaction based on its current stage.
    Returns a list of task strings.
    """
    prompt = (
        f"A real estate agent is working on a {side} transaction at {property_address} for {client_name}. "
        f"The transaction just moved to stage: '{stage}'. Target close date: {close_date or 'TBD'}. "
        f"List 5-7 specific action items the agent should complete for this stage. "
        f"Each item should be a single clear sentence starting with a verb. "
        f"Output one task per line, no numbers or bullets."
    )
    result = ai_complete(
        prompt,
        system="You are a real estate transaction coordinator. Give specific, actionable tasks.",
        max_tokens=250,
        temperature=0.4
    )
    tasks = [line.strip() for line in result.splitlines() if line.strip()]
    return tasks[:7]


def ai_listing_description(address: str, bedrooms: int, bathrooms: float,
                             sqft: int, highlights: str, price: float,
                             neighborhood: str = "") -> str:
    """
    Generate a compelling property listing description.
    """
    prompt = (
        f"Write a compelling, professional real estate listing description for this property:\n"
        f"Address: {address}\n"
        f"Bedrooms: {bedrooms} | Bathrooms: {bathrooms} | Square feet: {sqft}\n"
        f"Price: {'${:,.0f}'.format(price) if price else 'contact for price'}\n"
        f"Neighborhood: {neighborhood or 'Kansas City area'}\n"
        f"Key highlights: {highlights}\n\n"
        f"Write 3 punchy paragraphs. First paragraph: lead with the best feature and create emotional appeal. "
        f"Second: key features and upgrades. Third: location, lifestyle, and call to action. "
        f"Keep it under 200 words. Do not use em dashes."
    )
    return ai_complete(
        prompt,
        system="You are an expert real estate copywriter. Write compelling, accurate listing descriptions.",
        max_tokens=350,
        temperature=0.7
    )


def ai_lead_score(contact_name: str, contact_stage: str, lead_source: str,
                   days_since_added: int, interaction_count: int, has_email: bool,
                   has_phone: bool, notes: str) -> dict:
    """
    Score a lead 1-10 and explain the reasoning.
    Returns dict with: score (int 1-10), label (string), reason (string)
    """
    prompt = (
        f"Score this real estate lead on a scale of 1-10 for conversion likelihood:\n"
        f"Name: {contact_name}\n"
        f"Stage: {contact_stage}\n"
        f"Source: {lead_source or 'unknown'}\n"
        f"Added {days_since_added} days ago | {interaction_count} interactions logged\n"
        f"Has email: {has_email} | Has phone: {has_phone}\n"
        f"Notes: {notes[:150] if notes else 'none'}\n\n"
        f"Respond in this exact format:\n"
        f"SCORE: (a number 1-10)\n"
        f"LABEL: (exactly one of: Cold, Warm, Hot, or Burning)\n"
        f"REASON: (one sentence)"
    )
    result = ai_complete(
        prompt,
        system="You are a real estate sales expert scoring leads. Be direct and accurate.",
        max_tokens=80,
        temperature=0.3
    )
    score, label, reason = 5, "Warm", ""
    for line in result.splitlines():
        if line.startswith("SCORE:"):
            try:
                score = int(line[6:].strip())
            except:
                pass
        elif line.startswith("LABEL:"):
            label = line[6:].strip()
        elif line.startswith("REASON:"):
            reason = line[7:].strip()
    return {"score": score, "label": label, "reason": reason}


def ai_homeowner_equity_insight(home_value: float, original_price: float,
                                 loan_balance: float, equity: float,
                                 appreciation_pct: float, owner_name: str,
                                 agent_name: str) -> str:
    """
    Generate a personalized equity insight paragraph for a homeowner.
    """
    prompt = (
        f"Write a short, warm, personalized home equity insight for {owner_name}. "
        f"Their home is currently valued at {'${:,.0f}'.format(home_value)}. "
        f"They bought it for {'${:,.0f}'.format(original_price)}. "
        f"Estimated loan balance: {'${:,.0f}'.format(loan_balance) if loan_balance else 'unknown'}. "
        f"Current equity: {'${:,.0f}'.format(equity)}. "
        f"Appreciation: {appreciation_pct:.1f}%. "
        f"Write 2-3 sentences. Be encouraging, specific, and human. "
        f"Mention their agent {agent_name} at the end as available to answer questions. "
        f"No bullet points. No em dashes."
    )
    return ai_complete(
        prompt,
        system="You are a friendly real estate expert explaining equity to a homeowner.",
        max_tokens=180,
        temperature=0.65
    )


def ai_vendor_recommendation(transaction_stage: str, property_type: str, side: str) -> str:
    """
    Suggest which types of vendors the agent should be connecting clients with
    based on where the transaction is.
    """
    prompt = (
        f"A real estate agent has a {side} transaction at stage '{transaction_stage}' on a {property_type} property. "
        f"In 2-3 sentences, tell the agent which vendor types they should be connecting their client with right now "
        f"and why it matters at this stage. Be specific and practical."
    )
    return ai_complete(
        prompt,
        system="You are a real estate transaction expert advising an agent.",
        max_tokens=150,
        temperature=0.5
    )


def ai_client_portfolio_insight(agent_name: str, total_clients: int, clients_with_data: int,
                                 clients_needing_followup: list, inactive_count: int) -> str:
    """
    Generate a concise portfolio intelligence summary for the clients page.
    Highlights who needs attention and what the agent should prioritize.
    """
    followup_str = ", ".join(clients_needing_followup[:4]) if clients_needing_followup else "none identified"
    prompt = (
        f"Write a 2-sentence portfolio intelligence summary for {agent_name}, a real estate agent. "
        f"Portfolio: {total_clients} total clients, {clients_with_data} with home data on file, "
        f"{len(clients_needing_followup)} needing follow-up, {inactive_count} with no recent activity. "
        f"Clients needing follow-up: {followup_str}. "
        f"Be direct and actionable. Mention who to prioritize if names are available. "
        f"Do not use em dashes or bullet points. No greeting."
    )
    return ai_complete(
        prompt,
        system="You are a real estate business coach giving a crisp portfolio summary.",
        max_tokens=140,
        temperature=0.6
    )


def ai_transaction_coordinator_summary(agent_name: str, transactions: list) -> str:
    """
    Generate a transaction coordinator summary highlighting urgent items.
    transactions: list of dicts with keys: address, stage, client_name, close_date, side
    Returns a 2-3 sentence summary of what needs attention.
    """
    if not transactions:
        return ""
    tx_lines = []
    for t in transactions[:6]:
        parts = [t.get("address", "Unknown address")]
        if t.get("stage"):
            parts.append(f"stage: {t['stage']}")
        if t.get("close_date"):
            parts.append(f"closes: {t['close_date']}")
        if t.get("client_name"):
            parts.append(f"client: {t['client_name']}")
        tx_lines.append(" | ".join(parts))
    tx_str = "; ".join(tx_lines)
    prompt = (
        f"You are a transaction coordinator for {agent_name}. "
        f"Active transactions: {tx_str}. "
        f"In 2-3 sentences, summarize what needs the most urgent attention today and flag any deals "
        f"that are close to closing or stuck in an early stage. Be specific. No bullet points. No em dashes."
    )
    return ai_complete(
        prompt,
        system="You are a detail-oriented real estate transaction coordinator.",
        max_tokens=160,
        temperature=0.55
    )
