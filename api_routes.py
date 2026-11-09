"""API endpoints (AI helpers for agents, lenders and homeowners, plus the Homebot and lead-intake webhooks).

Moved out of app.py. Loaded by install(), which runs these views in app.py's own namespace (see route_loader.py), so every
helper they use is looked up there, exactly as before. This file is not meant to be run or linted on its own. Route names
(endpoints) are unchanged, so url_for(...) keeps working.
"""
from route_loader import Registry

_registry = Registry()
route = _registry.route
install = _registry.install


@route("/api/homebot/webhook", methods=["POST"])
def homebot_webhook():
    """
    Webhook endpoint for Homebot to send homeowner data updates.
    When a homeowner links their account in Homebot, this endpoint receives
    their loan and property information and updates the YLYH database.
    """
    from database import (
        get_user_by_email, 
        get_primary_property,
        get_user_properties,
        get_property_by_id,
        upsert_homeowner_snapshot_for_property,
        add_property,
        get_connection
    )
    
    try:
        # Get JSON data from Homebot
        data = request.get_json()
        
        if not data:
            return jsonify({"error": "No data received"}), 400
        
        # Homebot typically sends: email, address, loan_balance, loan_rate, 
        # loan_payment, home_value, etc.
        email = data.get("email") or data.get("homeowner_email")
        if not email:
            return jsonify({"error": "Email is required"}), 400
        
        # Find homeowner by email
        homeowner = get_user_by_email(email.lower().strip())
        if not homeowner:
            # Homeowner doesn't exist in YLYH yet - log for manual review
            print(f"HOMEBOT WEBHOOK: Homeowner with email {email} not found in YLYH")
            return jsonify({
                "error": "Homeowner not found",
                "message": "Homeowner must have a YLYH account first"
            }), 404
        
        if homeowner.get("role") != "homeowner":
            return jsonify({"error": "User is not a homeowner"}), 400
        
        homeowner_id = homeowner["id"]
        
        # Get or create property
        property_address = data.get("address") or data.get("property_address") or "My Home"
        properties = get_user_properties(homeowner_id)
        current_property = get_primary_property(homeowner_id)
        
        if not current_property:
            # Create property if it doesn't exist
            property_id = add_property(homeowner_id, property_address, None, "primary")
            current_property = get_property_by_id(property_id)
        else:
            property_id = current_property["id"]
        
        # Extract loan and property data from Homebot
        # Homebot field names may vary, so we check multiple possibilities
        home_value = (
            data.get("home_value") or 
            data.get("current_value") or 
            data.get("property_value") or
            data.get("estimated_value")
        )
        
        loan_balance = (
            data.get("loan_balance") or 
            data.get("mortgage_balance") or
            data.get("outstanding_balance")
        )
        
        loan_rate = (
            data.get("loan_rate") or 
            data.get("interest_rate") or
            data.get("mortgage_rate")
        )
        
        loan_payment = (
            data.get("loan_payment") or 
            data.get("monthly_payment") or
            data.get("mortgage_payment")
        )
        
        loan_term_years = data.get("loan_term_years") or data.get("term_years")
        loan_start_date = data.get("loan_start_date") or data.get("origination_date")
        
        # Convert string numbers to floats
        def safe_float(val):
            if val is None or val == "":
                return None
            try:
                return float(str(val).replace(",", "").replace("$", ""))
            except (ValueError, TypeError):
                return None
        
        # Update homeowner snapshot with Homebot data
        from datetime import datetime
        import time
        
        # Mark data as synced from Homebot
        upsert_homeowner_snapshot_for_property(
            user_id=homeowner_id,
            property_id=property_id,
            value_estimate=safe_float(home_value),
            loan_balance=safe_float(loan_balance),
            loan_rate=safe_float(loan_rate),
            loan_payment=safe_float(loan_payment),
            loan_term_years=safe_float(loan_term_years),
            loan_start_date=loan_start_date,
        )
        
        # Mark data source as Homebot
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """UPDATE homeowner_snapshots 
               SET value_refresh_source = 'Homebot',
                   last_value_refresh = ?
               WHERE user_id = ? AND property_id = ?""",
            (datetime.now().isoformat(), homeowner_id, property_id)
        )
        conn.commit()
        conn.close()
        
        # Update property estimated value if provided
        if home_value:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute(
                "UPDATE properties SET estimated_value = ? WHERE id = ?",
                (safe_float(home_value), property_id),
            )
            conn.commit()
            conn.close()
        
        print(f"HOMEBOT WEBHOOK: Successfully updated homeowner {homeowner_id} (email: {email})")
        
        return jsonify({
            "success": True,
            "message": "Homeowner data updated successfully",
            "homeowner_id": homeowner_id,
            "property_id": property_id
        }), 200
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"HOMEBOT WEBHOOK ERROR: {str(e)}")
        print(error_trace)
        return jsonify({
            "error": "Internal server error",
            "message": str(e)
        }), 500


@route("/api/agent/dashboard-metrics", methods=["GET"])
def api_agent_dashboard_metrics_refresh():
    """Return live KPI metrics for the agent dashboard without a full page reload."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    try:
        metrics = get_agent_dashboard_metrics(user["id"])
        txns = get_agent_transactions(user["id"]) or []
        resp = jsonify({
            "new_leads":      metrics.get("new_leads", 0),
            "active_deals":   len(txns),
            "followups_today": metrics.get("followups_today", 0),
        })
        resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        return resp
    except Exception as e:
        print(f"[dashboard-metrics] Error: {e}")
        return jsonify({"new_leads": 0, "active_deals": 0, "followups_today": 0})


@route("/api/ai/dashboard-briefing", methods=["POST"])
def ai_dashboard_briefing_endpoint():
    """Return a personalized morning briefing for the agent dashboard."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    from ai_platform import ai_dashboard_briefing
    from database import get_user_profile, get_contacts_needing_followup
    profile = get_user_profile(user["id"]) or {}
    profile_d = dict(profile) if profile else {}
    agent_name = (profile_d.get("full_name") or user.get("name") or "there").split()[0]
    metrics = get_agent_dashboard_metrics(user["id"]) if user.get("role") == "agent" else {}
    followup_contacts = get_contacts_needing_followup(user["id"], days_threshold=14)
    followup_names = [c.get("name","") for c in followup_contacts[:5] if c.get("name")]
    briefing = ai_dashboard_briefing(agent_name, metrics, followup_names, [])
    resp = jsonify({"briefing": briefing})
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@route("/api/ai/dashboard-priorities", methods=["POST"])
def ai_dashboard_priorities_endpoint():
    """Return 3 AI-prioritized action items, rotating each call, based on real contact data."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    import random as _random, re as _re, json as _json
    from ai_platform import ai_complete
    from database import get_user_profile, get_contacts_needing_followup
    profile = get_user_profile(user["id"]) or {}
    profile_d = dict(profile) if profile else {}
    agent_name = (profile_d.get("full_name") or user.get("name") or "there").split()[0]
    metrics = get_agent_dashboard_metrics(user["id"]) if user.get("role") == "agent" else {}

    # Pull contacts not touched in 30 days and separately 60 days for richer context
    overdue_30  = get_contacts_needing_followup(user["id"], days_threshold=30)
    overdue_60  = get_contacts_needing_followup(user["id"], days_threshold=60)

    # Build named lists (shuffle so each refresh surfaces different names)
    names_30 = [c.get("name", "") for c in overdue_30 if c.get("name")]
    names_60 = [c.get("name", "") for c in overdue_60 if c.get("name")]
    _random.shuffle(names_30)
    _random.shuffle(names_60)

    # Pick a rotating window of contacts to highlight (up to 4 from each bucket)
    highlight_30 = names_30[:4]
    highlight_60 = names_60[:4]

    followup_str = ", ".join(highlight_30) if highlight_30 else "none"
    lapsed_str   = ", ".join(highlight_60) if highlight_60 else "none"

    # Randomize the angle / focus so each refresh feels fresh
    focus_options = [
        "Focus on re-engaging lapsed contacts and booking calls.",
        "Focus on moving active deals forward and closing pipeline gaps.",
        "Focus on lead nurturing and adding value to warm contacts.",
        "Focus on relationship-building touches that generate referrals.",
        "Focus on proactive outreach to contacts who haven't heard from you recently.",
    ]
    focus = _random.choice(focus_options)

    prompt = (
        f"You are a real estate business coach generating a fresh daily priority list for {agent_name}. "
        f"Pipeline snapshot: {metrics.get('new_leads', 0)} new leads, "
        f"{metrics.get('active_transactions', 0)} active deals, "
        f"{metrics.get('followups_today', 0)} follow-ups overdue. "
        + (f"Contacts with NO touch in 30+ days (prioritize these): {followup_str}. " if followup_str != "none" else "")
        + (f"Contacts with NO touch in 60+ days (urgent re-engagement needed): {lapsed_str}. " if lapsed_str != "none" else "")
        + f"{focus} "
        f"Generate exactly 3 specific, actionable priorities for today. "
        f"If real contact names are provided above, use them directly in the actions (e.g. 'Call Carr to reconnect'). "
        f"Each priority must start with a strong action verb and be under 14 words. "
        f"Vary the priorities from common patterns, surprise with fresh angles. "
        f"Output ONLY a JSON array: [\"priority 1\", \"priority 2\", \"priority 3\"]. No extra text."
    )
    result = ai_complete(
        prompt,
        system="You are a sharp, encouraging real estate productivity coach. Be specific, use real names when given, and vary your suggestions each time.",
        max_tokens=150,
        temperature=0.82
    )
    result = _re.sub(r"^```[a-z]*\n?", "", result.strip())
    result = _re.sub(r"\n?```$", "", result.strip())
    try:
        priorities = _json.loads(result)
        if not isinstance(priorities, list):
            raise ValueError
        priorities = [str(p) for p in priorities[:3]]
    except Exception:
        # Meaningful fallback using real names when available
        fallback = []
        if highlight_30:
            fallback.append(f"Reach out to {highlight_30[0]}, no contact in over a month")
        elif highlight_60:
            fallback.append(f"Re-engage {highlight_60[0]}, they haven't heard from you in 60+ days")
        else:
            fallback.append("Call your top lead and schedule a showing")
        fallback.append("Review active transactions and confirm next steps with each client")
        fallback.append("Add 2 new contacts to your CRM before end of day")
        priorities = fallback

    resp = jsonify({"priorities": priorities})
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@route("/api/ai/clients/insights", methods=["POST"])
def ai_clients_insights_endpoint():
    """Return an AI portfolio intelligence summary for the clients page."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    from database import get_agent_clients, get_user_profile, get_contacts_needing_followup
    from ai_platform import ai_client_portfolio_insight
    profile = get_user_profile(user["id"]) or {}
    profile_d = dict(profile) if profile else {}
    agent_name = (profile_d.get("full_name") or user.get("name") or "there").split()[0]
    clients = get_agent_clients(user["id"]) or []
    clients_list = [dict(c) for c in clients]
    total = len(clients_list)
    with_data = sum(1 for c in clients_list if c.get("value_estimate"))
    inactive = sum(1 for c in clients_list if not c.get("doc_count") and not c.get("project_count"))
    followup_contacts = get_contacts_needing_followup(user["id"], days_threshold=21)
    followup_names = [c.get("name", "") for c in followup_contacts[:4] if c.get("name")]
    insight = ai_client_portfolio_insight(agent_name, total, with_data, followup_names, inactive)
    if not insight:
        insight = (
            f"You have {total} clients, {with_data} with home data on file. "
            + (f"Priority follow-ups: {', '.join(followup_names)}." if followup_names else "Stay consistent with monthly check-ins.")
        )
    resp = jsonify({"insight": insight})
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@route("/api/ai/transactions/coordinator", methods=["POST"])
def ai_transactions_coordinator_endpoint():
    """Return an AI transaction coordinator summary for the transactions page."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    from database import get_user_profile
    from transaction_helpers import get_agent_transactions as _real_transactions
    from ai_platform import ai_transaction_coordinator_summary
    profile = get_user_profile(user["id"]) or {}
    profile_d = dict(profile) if profile else {}
    agent_name = (profile_d.get("full_name") or user.get("name") or "there").split()[0]
    raw_txns = _real_transactions(user["id"]) or []
    txns = []
    for t in raw_txns[:8]:
        td = dict(t) if not isinstance(t, dict) else t
        txns.append({
            "address": td.get("property_address") or "Unknown",
            "stage": (td.get("current_stage") or "").replace("_", " "),
            "client_name": td.get("client_name") or "",
            "close_date": td.get("target_close_date") or "",
            "side": td.get("side") or "buyer",
        })
    summary = ai_transaction_coordinator_summary(agent_name, txns)
    if not summary:
        open_count = len(txns)
        summary = (
            f"You have {open_count} active transaction{'s' if open_count != 1 else ''}. "
            "Review each for upcoming deadlines and make sure all parties are aligned."
        ) if open_count else "No active transactions. A great time to prospect and grow your pipeline."
    resp = jsonify({"summary": summary})
    resp.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    resp.headers["Pragma"] = "no-cache"
    return resp


@route("/api/ai/crm/draft-email", methods=["POST"])
def ai_crm_draft_email():
    """Draft a personalized email for a CRM contact."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    contact_id = data.get("contact_id")
    context = data.get("context", "")
    if not contact_id:
        return jsonify({"error": "contact_id required"}), 400
    from database import get_agent_contact, get_user_profile, list_crm_interactions
    contact = get_agent_contact(int(contact_id), user["id"])
    if not contact:
        return jsonify({"error": "Contact not found"}), 404
    contact = dict(contact)
    interactions = list_crm_interactions(int(contact_id), "agent_contact", user["id"], limit=5)
    contact["all_interactions"] = [dict(i) for i in interactions]
    profile = get_user_profile(user["id"]) or {}
    profile_d = dict(profile) if profile else {}
    agent_name = profile_d.get("full_name") or user.get("name") or "Your Agent"
    agent_phone = profile_d.get("phone") or ""
    from ai_platform import ai_draft_email
    draft = ai_draft_email(
        contact_name=contact.get("name",""),
        contact_stage=contact.get("stage","new"),
        contact_notes=contact.get("notes",""),
        recent_interactions=contact.get("all_interactions") or [],
        agent_name=agent_name,
        agent_phone=agent_phone,
        context=context
    )
    return jsonify({"draft": draft})


@route("/api/ai/crm/next-action", methods=["POST"])
def ai_crm_next_action():
    """Suggest the best next action for a CRM contact."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    contact_id = data.get("contact_id")
    if not contact_id:
        return jsonify({"error": "contact_id required"}), 400
    from database import get_agent_contact, list_crm_interactions
    from datetime import date, datetime as _dt
    contact = get_agent_contact(int(contact_id), user["id"])
    if not contact:
        return jsonify({"error": "Contact not found"}), 404
    contact = dict(contact)
    interactions = list_crm_interactions(int(contact_id), "agent_contact", user["id"], limit=5)
    interactions_list = [dict(i) for i in interactions]
    last_touch = contact.get("last_touch") or contact.get("created_at","")
    days_since = 30
    if last_touch:
        try:
            lt = _dt.fromisoformat(str(last_touch)[:10])
            days_since = (date.today() - lt.date()).days
        except Exception:
            pass
    from ai_platform import ai_next_action
    result = ai_next_action(
        contact_name=contact.get("name",""),
        contact_stage=contact.get("stage","new"),
        contact_notes=contact.get("notes",""),
        recent_interactions=interactions_list,
        days_since_contact=days_since
    )
    return jsonify(result)


@route("/api/ai/crm/lead-score", methods=["POST"])
def ai_crm_lead_score():
    """Score a lead and explain the reasoning."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    contact_id = data.get("contact_id")
    if not contact_id:
        return jsonify({"error": "contact_id required"}), 400
    from database import get_agent_contact, list_crm_interactions
    from datetime import date, datetime as _dt
    contact = get_agent_contact(int(contact_id), user["id"])
    if not contact:
        return jsonify({"error": "Contact not found"}), 404
    contact = dict(contact)
    interactions = list_crm_interactions(int(contact_id), "agent_contact", user["id"], limit=20)
    created = contact.get("created_at","")
    days_since = 0
    if created:
        try:
            days_since = (date.today() - _dt.fromisoformat(str(created)[:10]).date()).days
        except Exception:
            pass
    from ai_platform import ai_lead_score
    result = ai_lead_score(
        contact_name=contact.get("name",""),
        contact_stage=contact.get("stage","new"),
        lead_source=contact.get("lead_source",""),
        days_since_added=days_since,
        interaction_count=len(interactions),
        has_email=bool(contact.get("email")),
        has_phone=bool(contact.get("phone")),
        notes=contact.get("notes","")
    )
    return jsonify(result)


@route("/api/ai/communications/personalize", methods=["POST"])
def ai_communications_personalize():
    """Personalize a communication template for a specific contact."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    template_text = data.get("template_text","")
    contact_name = data.get("contact_name","")
    contact_stage = data.get("contact_stage","new")
    context = data.get("context","")
    if not template_text:
        return jsonify({"error": "template_text required"}), 400
    from database import get_user_profile
    profile = get_user_profile(user["id"]) or {}
    agent_name = dict(profile).get("full_name") or user.get("name") or "Your Agent"
    from ai_platform import ai_personalize_template
    result = ai_personalize_template(template_text, contact_name, contact_stage, agent_name, context)
    return jsonify({"personalized": result})


@route("/api/ai/transaction/suggest-tasks", methods=["POST"])
def ai_transaction_suggest_tasks():
    """Suggest tasks for a transaction at its current stage."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    tx_id = data.get("transaction_id")
    if not tx_id:
        return jsonify({"error": "transaction_id required"}), 400
    tx = get_transaction_detail(int(tx_id))
    if not tx or tx.get("agent_id") != user["id"]:
        return jsonify({"error": "Transaction not found"}), 404
    from ai_platform import ai_transaction_tasks
    tasks = ai_transaction_tasks(
        property_address=tx.get("property_address",""),
        client_name=tx.get("client_name",""),
        side=tx.get("side","buyer"),
        stage=tx.get("current_stage","pre_contract"),
        close_date=str(tx.get("target_close_date",""))
    )
    return jsonify({"tasks": tasks})


@route("/api/ai/marketing/listing-description", methods=["POST"])
def ai_marketing_listing_description():
    """Generate a listing description from property details."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    from ai_platform import ai_listing_description
    description = ai_listing_description(
        address=data.get("address",""),
        bedrooms=int(data.get("bedrooms",0) or 0),
        bathrooms=float(data.get("bathrooms",0) or 0),
        sqft=int(data.get("sqft",0) or 0),
        highlights=data.get("highlights",""),
        price=float(data.get("price",0)) if data.get("price") else 0,
        neighborhood=data.get("neighborhood","")
    )
    return jsonify({"description": description})


@route("/api/ai/homeowner/equity-insight", methods=["POST"])
def ai_homeowner_equity_insight_endpoint():
    """Generate a personalized equity insight for a homeowner.
    Auto-loads the homeowner's snapshot from DB when body is empty."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    from ai_platform import ai_homeowner_equity_insight

    home_value     = float(data.get("home_value") or 0)
    original_price = float(data.get("original_price") or 0)
    loan_balance   = float(data.get("loan_balance") or 0)
    equity         = float(data.get("equity") or 0)
    appreciation   = float(data.get("appreciation_pct") or 0)
    owner_name     = data.get("owner_name") or (
        (user.get("first_name","") + " " + user.get("last_name","")).strip()
        or user.get("name","Homeowner")
    )
    agent_name = data.get("agent_name") or "your agent"

    if not home_value:
        try:
            snap = get_homeowner_snapshot_for_user(user["id"])
            if snap:
                home_value     = float(snap.get("value_estimate") or 0)
                original_price = float(snap.get("original_price") or 0)
                loan_balance   = float(snap.get("loan_balance") or 0)
                equity_raw     = snap.get("equity_estimate") or (
                    home_value - loan_balance if home_value and loan_balance else 0)
                equity = float(equity_raw or 0)
                if home_value and original_price:
                    appreciation = round((home_value - original_price) / original_price * 100, 1)
        except Exception:
            pass

    insight = ai_homeowner_equity_insight(
        home_value=home_value,
        original_price=original_price,
        loan_balance=loan_balance,
        equity=equity,
        appreciation_pct=appreciation,
        owner_name=owner_name,
        agent_name=agent_name
    )
    return jsonify({"insight": insight})


@route("/api/ai/transaction/vendor-recommendation", methods=["POST"])
def ai_transaction_vendor_recommendation():
    """Suggest vendor types for the current transaction stage."""
    user = get_current_user()
    if not user:
        return jsonify({"error": "Unauthorized"}), 401
    data = request.get_json() or {}
    from ai_platform import ai_vendor_recommendation
    suggestion = ai_vendor_recommendation(
        transaction_stage=data.get("stage","pre_contract"),
        property_type=data.get("property_type","residential"),
        side=data.get("side","buyer")
    )
    return jsonify({"suggestion": suggestion})


@route("/api/lead-intake/<agent_token>", methods=["POST"])
def lead_intake_webhook(agent_token):
    """
    External lead intake endpoint. Accepts leads from website forms, Zapier,
    or any HTTP POST source and automatically creates a CRM contact.
    """
    from database import get_connection, add_agent_contact

    # Resolve agent by referral token or a dedicated webhook token stored in user_profiles
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT u.id, u.email, up.full_name
        FROM users u
        JOIN user_profiles up ON up.user_id = u.id
        WHERE u.role = 'agent'
          AND (up.referral_code = ? OR up.webhook_token = ?)
        LIMIT 1
    """, (agent_token, agent_token))
    row = cur.fetchone()
    conn.close()

    if not row:
        return {"success": False, "error": "Invalid token"}, 401

    agent_id = row["id"]

    # Parse incoming data (JSON or form)
    if request.is_json:
        data = request.get_json(force=True) or {}
    else:
        data = request.form.to_dict()

    name = (data.get("name") or data.get("full_name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    phone = (data.get("phone") or data.get("phone_number") or "").strip()
    source = (data.get("source") or data.get("lead_source") or "website").strip()
    message = (data.get("message") or data.get("notes") or "").strip()

    if not name and not email:
        return {"success": False, "error": "Name or email is required"}, 400

    # Prevent duplicates
    from database import list_agent_contacts
    existing = list_agent_contacts(agent_id)
    for ex in existing:
        if email and ex.get("email") and ex["email"].strip().lower() == email:
            # Update lead source and note if contact already exists
            from database import update_agent_contact
            ex_id = ex.get("id")
            if ex_id:
                update_agent_contact(ex_id, agent_id,
                                     notes=((ex.get("notes") or "") + f"\n[Web form] {message}").strip())
            return {"success": True, "status": "existing", "contact_id": ex_id}, 200

    notes = f"[From: {source}] {message}".strip(" []") if message else f"Lead from {source}"
    try:
        contact_id = add_agent_contact(
            agent_user_id=agent_id,
            name=name or email,
            email=email,
            phone=phone,
            stage="new",
            notes=notes,
            lead_source=source,
        )
        # Schedule drip follow-up
        if email:
            try:
                schedule_new_lead_drip(agent_id, contact_id, email)
            except Exception:
                pass
        # AI lead score — run in background thread so webhook responds instantly
        try:
            import threading
            def _ai_score():
                try:
                    from ai_platform import ai_lead_score
                    from database import get_connection as _gc2
                    result = ai_lead_score(
                        contact_name=name or email,
                        contact_stage="new",
                        lead_source=source,
                        days_since_added=0,
                        interaction_count=0,
                        has_email=bool(email),
                        has_phone=bool(phone),
                        notes=notes
                    )
                    # Store score in contact notes as a tag line
                    if result and result.get("score"):
                        _c = _gc2()
                        _cr = _c.cursor()
                        score_note = f"[AI Score: {result['score']}/10 {result.get('label','')}] {result.get('reason','')}"
                        _cr.execute("UPDATE agent_contacts SET notes = notes || ? WHERE id = ?",
                                    ("\n" + score_note, contact_id))
                        _c.commit(); _c.close()
                except Exception:
                    pass
            threading.Thread(target=_ai_score, daemon=True).start()
        except Exception:
            pass
        # Notify agent by email
        try:
            from database import get_connection as _gc
            _conn = _gc()
            _cur = _conn.cursor()
            _cur.execute("SELECT email FROM users WHERE id = ?", (agent_id,))
            _agent = _cur.fetchone()
            _conn.close()
            if _agent:
                send_reminder_email(
                    _agent["email"],
                    f"Good news: {name or email} wants to connect",
                    f"Good news, a new lead just came in from your website.\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nSource: {source}\nTheir message: {message}\n\nA quick, friendly reply goes a long way. You can follow up from your CRM."
                )
        except Exception:
            pass
        return {"success": True, "status": "created", "contact_id": contact_id}, 201
    except Exception as e:
        print(f"[WEBHOOK] Error creating contact: {e}")
        return {"success": False, "error": "Could not create contact"}, 500


@route("/api/ai/financials/agent-coach", methods=["POST"])
def agent_financials_ai_coach():
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(force=True) or {}
        context = data.get("context", "")
        prompt = f"""You are a top real estate financial coach. Analyze this agent's financial data and give 3-5 specific, actionable coaching tips to help them increase their income, reduce expenses, and hit their goals. Be encouraging but direct. Use specific numbers when given. Keep it under 250 words.

Agent Data:
{context}"""
        from ai_platform import call_ai
        response = call_ai(prompt)
        return jsonify({"coach_response": response})
    except Exception as e:
        return jsonify({"coach_response": "Unable to generate coaching tips right now. Please try again shortly."})


@route("/api/ai/financials/agent-insights", methods=["POST"])
def agent_financials_ai_insights():
    """Auto-load 3 smart observations about the agent's financials."""
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(force=True) or {}
        ctx = data.get("context", "")
        prompt = f"""You are an elite real estate financial advisor. Analyze this agent's financial snapshot and return EXACTLY 3 sharp, specific insights in JSON format.

Each insight must be:
- Concrete (use the numbers given)
- Actionable (tell them what to do)
- Brief (max 2 sentences each)

Return ONLY valid JSON like this:
{{
  "insights": [
    {{"icon": "trend", "title": "Income Pace", "body": "...", "type": "positive|warning|info"}},
    {{"icon": "expense", "title": "Expense Alert", "body": "...", "type": "positive|warning|info"}},
    {{"icon": "goal", "title": "Goal Progress", "body": "...", "type": "positive|warning|info"}}
  ]
}}

Agent Data:
{ctx}"""
        from ai_platform import ai_complete
        raw = ai_complete(prompt, system="You are a financial data analyst. Return only valid JSON.", max_tokens=400, temperature=0.5)
        import json as _json
        # Strip markdown code fences if present
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = _json.loads(clean.strip())
        return jsonify(parsed)
    except Exception as e:
        return jsonify({"insights": [
            {"icon": "trend", "title": "Keep Going", "body": "Your coach is ready when you are. Add a few transactions and you will see helpful insights here.", "type": "info"}
        ]})


@route("/api/ai/financials/agent-forecast", methods=["POST"])
def agent_financials_ai_forecast():
    """Project year-end income based on current pace."""
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(force=True) or {}
        ctx = data.get("context", "")
        prompt = f"""You are a top real estate financial forecaster. Based on this agent's YTD data, project their full-year income.

Return ONLY valid JSON:
{{
  "projected_gci": 125000,
  "projected_net": 95000,
  "projected_transactions": 18,
  "confidence": "high|medium|low",
  "headline": "One compelling sentence about their trajectory",
  "action": "The single most impactful action they can take right now"
}}

Use realistic projections based on their current month (extrapolate from YTD). Be specific with dollar amounts.

Agent Data:
{ctx}"""
        from ai_platform import ai_complete
        raw = ai_complete(prompt, system="You are a financial forecasting expert. Return only valid JSON.", max_tokens=300, temperature=0.4)
        import json as _json
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = _json.loads(clean.strip())
        return jsonify(parsed)
    except Exception as e:
        return jsonify({"headline": "Add a little more data and your forecast will appear here.", "action": "Log your first commission to get started.", "confidence": "low"})


@route("/api/ai/financials/agent-tax-optimizer", methods=["POST"])
def agent_financials_ai_tax_optimizer():
    """Identify tax deduction opportunities for the agent."""
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(force=True) or {}
        ctx = data.get("context", "")
        prompt = f"""You are a CPA specializing in real estate agent taxes. Analyze this agent's expense profile and identify deduction opportunities.

Return ONLY valid JSON:
{{
  "estimated_tax_savings": 4200,
  "tips": [
    {{"title": "Home Office Deduction", "detail": "If you work from home, you may deduct...", "potential_savings": 1800}},
    {{"title": "Vehicle Expenses", "detail": "Based on your mileage...", "potential_savings": 1400}},
    {{"title": "Marketing Write-Offs", "detail": "...", "potential_savings": 1000}}
  ],
  "disclaimer": "Consult a licensed CPA before filing."
}}

Provide 3-4 specific, actionable tips. Use actual numbers from their data.

Agent Data:
{ctx}"""
        from ai_platform import ai_complete
        raw = ai_complete(prompt, system="You are a tax advisor for real estate professionals. Return only valid JSON.", max_tokens=500, temperature=0.4)
        import json as _json
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = _json.loads(clean.strip())
        return jsonify(parsed)
    except Exception as e:
        return jsonify({"tips": [{"title": "Track Everything", "detail": "Log all expenses to maximize your deductions at tax time.", "potential_savings": 0}], "estimated_tax_savings": 0, "disclaimer": "Consult a licensed CPA before filing."})


@route("/api/ai/financials/lender-coach", methods=["POST"])
def lender_financials_ai_coach():
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(force=True) or {}
        context = data.get("context", "")
        prompt = f"""You are a top mortgage lending financial coach. Analyze this lender's financial data and give 3-5 specific, actionable coaching tips to help them fund more loans, increase revenue, control expenses, and hit their annual goals. Be encouraging but direct. Use specific numbers when given. Keep it under 250 words.

Lender Data:
{context}"""
        from ai_platform import call_ai
        response = call_ai(prompt)
        return jsonify({"coach_response": response})
    except Exception as e:
        return jsonify({"coach_response": "Unable to generate coaching tips right now. Please try again shortly."})


@route("/api/ai/financials/lender-insights", methods=["POST"])
def lender_financials_ai_insights():
    """Auto-load 3 smart observations about the lender's financials."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(force=True) or {}
        ctx = data.get("context", "")
        prompt = f"""You are an elite mortgage lending financial advisor. Analyze this lender's financial snapshot and return EXACTLY 3 sharp, specific insights in JSON format.

Each insight must be concrete (use actual numbers), actionable, and brief (max 2 sentences).

Return ONLY valid JSON:
{{
  "insights": [
    {{"icon": "trend", "title": "Revenue Pace", "body": "...", "type": "positive|warning|info"}},
    {{"icon": "pipeline", "title": "Pipeline Health", "body": "...", "type": "positive|warning|info"}},
    {{"icon": "goal", "title": "Goal Progress", "body": "...", "type": "positive|warning|info"}}
  ]
}}

Lender Data:
{ctx}"""
        from ai_platform import ai_complete
        raw = ai_complete(prompt, system="You are a financial data analyst. Return only valid JSON.", max_tokens=400, temperature=0.5)
        import json as _json
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = _json.loads(clean.strip())
        return jsonify(parsed)
    except Exception as e:
        return jsonify({"insights": [
            {"icon": "trend", "title": "Ready to Analyze", "body": "Add a few loans and expenses and you will see helpful insights for your business here.", "type": "info"}
        ]})


@route("/api/ai/financials/lender-forecast", methods=["POST"])
def lender_financials_ai_forecast():
    """Project year-end revenue based on current pipeline and pace."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(force=True) or {}
        ctx = data.get("context", "")
        prompt = f"""You are a top mortgage lending financial forecaster. Based on this lender's YTD data, project their full-year revenue.

Return ONLY valid JSON:
{{
  "projected_revenue": 180000,
  "projected_loan_count": 52,
  "projected_loan_volume": 18000000,
  "confidence": "high|medium|low",
  "headline": "One compelling sentence about their trajectory",
  "action": "The single most impactful action they can take right now to hit their goals"
}}

Use realistic projections extrapolated from their current YTD pace. Be specific.

Lender Data:
{ctx}"""
        from ai_platform import ai_complete
        raw = ai_complete(prompt, system="You are a financial forecasting expert. Return only valid JSON.", max_tokens=300, temperature=0.4)
        import json as _json
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = _json.loads(clean.strip())
        return jsonify(parsed)
    except Exception as e:
        return jsonify({"headline": "Add your pipeline and your forecast will appear here.", "action": "Add your first loan to get started.", "confidence": "low"})


@route("/api/ai/financials/lender-pipeline", methods=["POST"])
def lender_financials_ai_pipeline():
    """Analyze pipeline health and identify at-risk loans."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return jsonify({"error": "Unauthorized"}), 401
    try:
        data = request.get_json(force=True) or {}
        ctx = data.get("context", "")
        prompt = f"""You are a mortgage operations expert. Analyze this lender's pipeline and provide a health assessment.

Return ONLY valid JSON:
{{
  "pipeline_score": 78,
  "pull_through_rate": "72%",
  "at_risk_revenue": 12000,
  "recommendations": [
    {{"priority": "high", "title": "Follow Up on Stale Files", "detail": "..."}},
    {{"priority": "medium", "title": "Diversify Loan Types", "detail": "..."}},
    {{"priority": "low", "title": "Referral Partner Outreach", "detail": "..."}}
  ],
  "summary": "One sentence overall pipeline health assessment"
}}

Be specific using the data provided. pipeline_score is 0-100.

Lender Data:
{ctx}"""
        from ai_platform import ai_complete
        raw = ai_complete(prompt, system="You are a mortgage pipeline expert. Return only valid JSON.", max_tokens=500, temperature=0.4)
        import json as _json
        clean = raw.strip()
        if clean.startswith("```"):
            clean = clean.split("```")[1]
            if clean.startswith("json"):
                clean = clean[4:]
        parsed = _json.loads(clean.strip())
        return jsonify(parsed)
    except Exception as e:
        return jsonify({"pipeline_score": 0, "summary": "Add loans to your pipeline to get an AI health assessment.", "recommendations": []})
