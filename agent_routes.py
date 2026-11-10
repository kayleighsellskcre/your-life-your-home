"""Agent pages (dashboard, CRM, deals and transactions, clients, marketing, referrals, financials, settings, billing).

These views used to sit in app.py. They are loaded by install(), which runs them in app.py's own namespace (see
route_loader.py), so every helper they use is looked up there, exactly as before. That is also why this file is not meant
to be run or linted on its own. Route names (endpoints) are unchanged, so url_for('agent_...') keeps working.
"""
from route_loader import Registry

_registry = Registry()
route = _registry.route
install = _registry.install


@route("/agent/transactions/<int:tx_id>/documents/upload", methods=["POST"])
def agent_transaction_document_upload(tx_id):
    """Attach a document (contract, inspection, title report...) to a deal."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))
    back = redirect(url_for("agent_transaction_detail", tx_id=tx_id))
    f = request.files.get("file")
    if not f or not f.filename:
        flash("Please choose a file to upload.", "error")
        return back
    safe = secure_filename(f.filename) or "document"
    stored = f"{uuid4().hex[:10]}_{safe}"
    try:
        path = _tx_docs_dir(tx_id) / stored
        f.save(path)
        from transaction_helpers import upload_transaction_document
        doc_type = (request.form.get("document_type") or "other").strip().lower().replace(" ", "_")[:60]
        upload_transaction_document(tx_id, doc_type, safe, stored, user["id"], path.stat().st_size)
        flash("Uploaded. It is saved to this deal.", "success")
    except Exception as e:
        app.logger.warning(f"tx document upload failed: {e}")
        flash("We could not upload that file. Please try again in a moment.", "error")
    return back


@route("/agent/transactions/<int:tx_id>/documents/<int:doc_id>/view")
def agent_transaction_document_view(tx_id, doc_id):
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        return redirect(url_for("agent_transactions"))
    from transaction_helpers import get_transaction_documents
    doc = next((d for d in get_transaction_documents(tx_id) if d.get("id") == doc_id), None)
    if not doc or not doc.get("file_path"):
        flash("We could not find that document.", "error")
        return redirect(url_for("agent_transaction_detail", tx_id=tx_id))
    folder = _tx_docs_dir(tx_id)
    name = Path(doc["file_path"]).name
    if not (folder / name).exists():
        flash("That file is no longer available.", "error")
        return redirect(url_for("agent_transaction_detail", tx_id=tx_id))
    return send_from_directory(folder, name, download_name=doc.get("document_name") or name)


@route("/agent/transactions/<int:tx_id>/participants/add", methods=["POST"])
def agent_add_participant(tx_id):
    """Add a participant to an agent transaction."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        if request.is_json or request.content_type == 'application/json':
            return jsonify({"success": False, "error": "Unauthorized"}), 401
        return redirect(url_for("login", role="agent"))
    
    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        if request.is_json or request.content_type == 'application/json':
            return jsonify({"success": False, "error": "Transaction not found"}), 404
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))
    
    name = request.form.get("participant_name", "").strip()
    email = request.form.get("participant_email", "").strip()
    phone = request.form.get("participant_phone", "").strip()
    role = request.form.get("participant_role", "client").strip()

    if not name:
        if request.is_json or request.content_type == 'application/json':
            return jsonify({"success": False, "error": "Name is required"}), 400
        flash("Please add the participant's name.", "error")
        return redirect(url_for("agent_transaction_detail", tx_id=tx_id))

    try:
        from transaction_helpers import add_transaction_participant
        participant_id = add_transaction_participant(
            transaction_id=tx_id,
            participant_type=role if role in PARTICIPANT_ROLES else 'client',
            name=name,
            email=email or None,
            phone=phone or None,
            permissions='view_only',
            user_id=None,
            added_by=user["id"]
        )
        
        try:
            import automation
            if role == "lender" and email:
                automation.link_transaction_parties(tx_id, email)  # a lender on the platform sees the deal on their own dashboard
            if email and role != "client":
                _bg(automation.notify_partner_added, tx_id, name, email, role, send_reminder_email, _site_url())  # a warm welcome to the new partner
        except Exception:
            pass

        # Always return JSON for AJAX requests (check if it's a fetch request)
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or request.content_type == 'application/json':
            return jsonify({"success": True, "message": "Client added successfully", "participant_id": participant_id}), 200

        flash("Participant added!" + (" We emailed them a welcome." if email and role != "client" else ""), "success")
    except Exception as e:
        import traceback
        print(f"Error adding participant: {traceback.format_exc()}")
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.is_json or request.content_type == 'application/json':
            return jsonify({"success": False, "error": str(e)}), 500
        flash("We could not add that participant. Please try again in a moment.", "error")

    return redirect(url_for("agent_transaction_detail", tx_id=tx_id))


@route("/agent/transactions/<int:tx_id>/participants/<int:participant_id>/remove", methods=["POST"])
def agent_remove_participant(tx_id, participant_id):
    """Remove a participant from a transaction."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        return jsonify({"success": False, "error": "Transaction not found"}), 404
    
    try:
        from transaction_helpers import get_db
        with get_db() as conn:
            cursor = conn.cursor()
            # Verify participant belongs to this transaction
            cursor.execute("SELECT id FROM transaction_participants WHERE id = ? AND transaction_id = ?", (participant_id, tx_id))
            if not cursor.fetchone():
                return jsonify({"success": False, "error": "Participant not found"}), 404
            
            # Mark as removed instead of deleting
            cursor.execute("UPDATE transaction_participants SET status = 'removed' WHERE id = ?", (participant_id,))
            conn.commit()
        
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            flash("Removed from this deal.", "success")
            return redirect(url_for("agent_transaction_detail", tx_id=tx_id))
        return jsonify({"success": True, "message": "Client removed successfully"}), 200
    except Exception as e:
        import traceback
        print(f"Error removing participant: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@route("/agent", methods=["GET"])
def agent_dashboard():
    """Agent dashboard view."""
    user = get_current_user()
    
    if not user:
        flash("Please sign in to see your dashboard.", "error")
        return redirect(url_for("login", role="agent"))
    
    # Check role - normalize for comparison
    user_role = str(user.get("role") or "").strip().lower()
    if user_role != "agent":
        flash("This page is for agents only.", "error")
        return redirect(url_for("login", role=user.get("role", "homeowner")))

    try:
        metrics = get_agent_dashboard_metrics(user["id"])
        transactions = get_agent_transactions(user["id"])
        
        # Ensure transactions are dicts (get_agent_transactions should already return dicts)
        if transactions:
            transactions_list = []
            for tx in transactions:
                if hasattr(tx, 'keys') and not isinstance(tx, dict):
                    transactions_list.append(dict(tx))
                else:
                    transactions_list.append(tx)
            transactions = transactions_list
    except Exception as e:
        import traceback
        print(f"Error in agent_dashboard: {traceback.format_exc()}")
        flash("We could not load your dashboard. Please try again in a moment.", "error")
        metrics = {"new_leads": 0, "active_transactions": 0, "followups_today": 0}
        transactions = []

    from datetime import datetime as _dt
    _now = _dt.now()
    try:
        today_label = _now.strftime("%A, %B %-d")   # Linux/Mac
    except ValueError:
        today_label = f"{_now.strftime('%A, %B')} {_now.day}"
    except Exception:
        today_label = _now.strftime("%A, %B %d").lstrip("0").replace(" 0", " ")

    try:
        import automation
        today_digest = automation.build_digest(user["id"], "agent")
    except Exception as _e:
        print(f"[DIGEST] dashboard digest skipped: {_e}")
        today_digest = None
    return render_template(
        "agent/dashboard.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        metrics=metrics,
        transactions=transactions,
        today_date=today_label,
        today_digest=today_digest,
    )


@route("/agent/crm", methods=["GET", "POST"])
def agent_crm():
    """Agent CRM - comprehensive contact management with automated emails."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "agent":
            return redirect(url_for("login", role="agent"))
    except Exception as e:
        import traceback
        print(f"Error in agent_crm (user check): {traceback.format_exc()}")
        return f"Error: {e}", 500

    if request.method == "POST":
        action = request.form.get("action", "").strip()
        print(f"\n=== POST REQUEST RECEIVED ===")
        print(f"Action: '{action}'")
        print(f"Form data keys: {list(request.form.keys())}")
        print(f"User ID: {user.get('id')}")
        
        if action == "add":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            stage = request.form.get("stage", "new").strip().lower()
            birthday = request.form.get("birthday", "").strip()
            home_anniversary = request.form.get("home_anniversary", "").strip()
            address = request.form.get("address", "").strip()
            notes = request.form.get("notes", "").strip()
            tags = request.form.get("tags", "").strip()
            property_address = request.form.get("property_address", "").strip()
            property_value = request.form.get("property_value", "").strip()
            equity_estimate = request.form.get("equity_estimate", "").strip()
            
            print(f"Name: '{name}'")
            print(f"Email: '{email}'")
            print(f"Phone: '{phone}'")
            print(f"Stage: '{stage}'")
            
            if not name:
                print("ERROR: Name is required but empty")
                flash("Please add a name.", "error")
                return redirect(url_for("agent_crm"))
            else:
                try:
                    # Prevent duplicates: check if contact already exists (by email, phone, or name)
                    _dc = get_db_connection()
                    try:
                        if email and _dc.execute("SELECT 1 FROM agent_contacts WHERE agent_user_id=? AND LOWER(TRIM(email))=? LIMIT 1", (user["id"], email.lower())).fetchone():
                            flash("You already have a contact with that email. Open them to make changes.", "error")
                            return redirect(url_for("agent_crm"))
                        if phone:
                            _pn = _normalize_phone(phone)
                            if _pn and any(_normalize_phone(str(r["phone"] or "")) == _pn for r in _dc.execute("SELECT phone FROM agent_contacts WHERE agent_user_id=? AND phone LIKE ?", (user["id"], "%" + _pn[-4:] + "%")).fetchall()):
                                flash("You already have a contact with that phone. Open them to make changes.", "error")
                                return redirect(url_for("agent_crm"))
                        _first = (name.split()[0] if name.split() else name)
                        for r in _dc.execute("SELECT name FROM agent_contacts WHERE agent_user_id=? AND LOWER(name) LIKE ?", (user["id"], "%" + _first.lower() + "%")).fetchall():
                            if _names_match(name, r["name"] or ""):
                                flash(f"You already have a contact named {name}. Open them to make changes.", "error")
                                return redirect(url_for("agent_crm"))
                    finally:
                        _dc.close()
                    prop_val = float(property_value) if property_value else None
                    equity_val = float(equity_estimate) if equity_estimate else None
                    lead_source = request.form.get("lead_source", "").strip()
                    next_action_date = request.form.get("next_action_date", "").strip()
                    next_action_note = request.form.get("next_action_note", "").strip()
                    print(f"Calling add_agent_contact with user_id={user['id']}, name='{name}'")
                    contact_id = add_agent_contact(
                        user["id"], name, email, phone, stage, email or phone, "",
                        birthday, home_anniversary, address, notes, tags,
                        property_address, prop_val, equity_val,
                        lead_source=lead_source,
                        next_action_date=next_action_date,
                        next_action_note=next_action_note
                    )
                    print(f"SUCCESS: Contact added with ID {contact_id}")

                    # Schedule new-lead follow-up drip if stage is 'new'
                    if stage == 'new' and email:
                        try:
                            schedule_new_lead_drip(user["id"], contact_id, email)
                            print(f"[DRIP] Scheduled drip sequence for contact {contact_id}")
                        except Exception as drip_err:
                            print(f"[DRIP] Could not schedule drip: {drip_err}")

                    # If email provided, try to link to existing homeowner account
                    if email:
                        from database import get_user_by_email, create_client_relationship, get_or_create_referral_code
                        homeowner = get_user_by_email(email)
                        from database import get_active_professional_id as _gap
                        if homeowner and homeowner.get("role") == "homeowner" and _gap(homeowner["id"], "agent") not in (None, user["id"]):
                            flash("Contact added. That email already has a homeowner account connected to another agent, so "
                                  "send them your invite link and they can choose to connect with you.", "success")
                        elif homeowner and homeowner.get("role") == "homeowner":
                            # Create relationship
                            referral_code = get_or_create_referral_code(user["id"], "agent")
                            create_client_relationship(
                                homeowner_id=homeowner["id"],
                                professional_id=user["id"],
                                professional_role="agent",
                                referral_code=referral_code
                            )
                            flash(f"Contact added and linked to homeowner account ({email})!", "success")
                        else:
                            flash("Contact added!", "success")
                    else:
                        flash("Contact added!", "success")
                    return redirect(url_for("agent_crm"))
                except Exception as e:
                    import traceback
                    error_trace = traceback.format_exc()
                    print(f"ERROR adding contact: {error_trace}")
                    flash("We could not add that contact. Please try again in a moment.", "error")
                    return redirect(url_for("agent_crm"))
        
        elif action == "update":
            contact_id = request.form.get("contact_id")
            if contact_id:
                updates = {}
                for field in ['name', 'email', 'phone', 'stage', 'birthday',
                            'home_anniversary', 'address', 'notes', 'tags',
                            'property_address', 'property_value', 'equity_estimate',
                            'city', 'state', 'zip_code',
                            'auto_birthday', 'auto_anniversary',
                            'auto_seasonal', 'auto_equity', 'auto_holidays',
                            'equity_frequency',
                            'lead_source', 'next_action_date', 'next_action_note']:
                    val = request.form.get(field, "").strip()
                    if val or field in ['auto_birthday', 'auto_anniversary', 
                                       'auto_seasonal', 'auto_equity', 'auto_holidays']:
                        if field in ['auto_birthday', 'auto_anniversary', 
                                    'auto_seasonal', 'auto_equity', 'auto_holidays']:
                            updates[field] = 1 if request.form.get(field) else 0
                        elif field in ['property_value', 'equity_estimate']:
                            try:
                                updates[field] = float(val) if val else None
                            except Exception:
                                pass
                        elif field == 'stage':
                            updates[field] = val.lower() if val else None
                        else:
                            updates[field] = val if val else None
                
                try:
                    update_agent_contact(int(contact_id), user["id"], **updates)
                    flash("Contact updated!", "success")
                except Exception as e:
                    flash("We could not update that contact. Please try again in a moment.", "error")
                    import traceback
                    print(f"Error updating contact: {traceback.format_exc()}")
        
        elif action == "add_interaction":
            contact_id = request.form.get("contact_id")
            interaction_type = request.form.get("interaction_type", "").strip()
            subject = request.form.get("subject", "").strip()
            notes = request.form.get("notes", "").strip()
            channel = request.form.get("channel", "email").strip()
            
            if contact_id and interaction_type:
                try:
                    add_crm_interaction(
                        int(contact_id), "agent_contact", user["id"],
                        interaction_type, subject, notes, channel
                    )
                    flash("Interaction logged!", "success")
                except Exception as e:
                    flash("We could not log that note. Please try again in a moment.", "error")
        
        elif action == "add_task":
            contact_id = request.form.get("contact_id")
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            due_date = request.form.get("due_date", "").strip()
            priority = request.form.get("priority", "medium").strip()
            reminder_date = request.form.get("reminder_date", "").strip() or None
            
            if contact_id and title:
                try:
                    add_crm_task(
                        int(contact_id), "agent_contact", user["id"],
                        title, description, due_date or None, priority, reminder_date
                    )
                    flash("Task added!", "success")
                except Exception as e:
                    flash("We could not add that task. Please try again in a moment.", "error")
        
        elif action == "update_task":
            task_id = request.form.get("task_id")
            status = request.form.get("status", "").strip()
            if task_id and status:
                try:
                    updates = {"status": status}
                    if status == "completed":
                        updates["completed_at"] = datetime.now().isoformat()
                    update_crm_task(int(task_id), user["id"], **updates)
                    flash("Task updated!", "success")
                except Exception as e:
                    flash("We could not update that task. Please try again in a moment.", "error")
        
        elif action == "delete_task":
            task_id = request.form.get("task_id")
            if task_id:
                try:
                    delete_crm_task(int(task_id), user["id"])
                    flash("Task deleted!", "success")
                except Exception as e:
                    flash("We could not delete that task. Please try again in a moment.", "error")
        
        elif action == "add_deal":
            contact_id = request.form.get("contact_id")
            deal_name = request.form.get("deal_name", "").strip()
            deal_type = request.form.get("deal_type", "other").strip()
            property_address = request.form.get("property_address", "").strip()
            deal_value = request.form.get("deal_value", "").strip()
            commission_rate = request.form.get("commission_rate", "").strip()
            stage = request.form.get("stage", "prospect").strip()
            probability = request.form.get("probability", "0").strip()
            expected_close_date = request.form.get("expected_close_date", "").strip()
            notes = request.form.get("notes", "").strip()
            
            if contact_id and deal_name:
                try:
                    deal_val = float(deal_value) if deal_value else None
                    comm_rate = float(commission_rate) if commission_rate else None
                    prob = int(probability) if probability else 0
                    add_crm_deal(
                        int(contact_id), "agent_contact", user["id"],
                        deal_name, deal_type, property_address, deal_val, comm_rate,
                        stage, prob, expected_close_date or None, notes
                    )
                    flash("Deal added!", "success")
                except Exception as e:
                    flash("We could not add that deal. Please try again in a moment.", "error")
        
        elif action == "update_deal":
            deal_id = request.form.get("deal_id")
            if deal_id:
                try:
                    updates = {}
                    for field in ['deal_name', 'deal_type', 'property_address', 'stage',
                                'expected_close_date', 'actual_close_date', 'notes']:
                        val = request.form.get(field, "").strip()
                        if val:
                            updates[field] = val if val else None
                    
                    for field in ['deal_value', 'commission_rate', 'probability']:
                        val = request.form.get(field, "").strip()
                        if val:
                            try:
                                updates[field] = float(val) if field != 'probability' else int(val)
                            except Exception:
                                pass
                    
                    if updates:
                        update_crm_deal(int(deal_id), user["id"], **updates)
                        flash("Deal updated!", "success")
                except Exception as e:
                    flash("We could not update that deal. Please try again in a moment.", "error")
        
        elif action == "delete_deal":
            deal_id = request.form.get("deal_id")
            if deal_id:
                try:
                    delete_crm_deal(int(deal_id), user["id"])
                    flash("Deal deleted!", "success")
                except Exception as e:
                    flash("We could not delete that deal. Please try again in a moment.", "error")
        
        elif action == "remove_duplicates":
            try:
                from database import remove_duplicate_agent_contacts
                removed = remove_duplicate_agent_contacts(user["id"])
                flash(f"Removed {removed} duplicate contact(s).", "success")
            except Exception as e:
                flash("We could not remove the duplicates. Please try again in a moment.", "error")
            return redirect(url_for("agent_crm"))
        
        elif action == "delete":
            contact_id = request.form.get("contact_id")
            if contact_id:
                try:
                    from database import delete_agent_contact
                    if delete_agent_contact(int(contact_id), user["id"]):
                        flash("Contact deleted!", "success")
                    else:
                        flash("We could not delete that contact. Please try again.", "error")
                except Exception as e:
                    flash("We could not delete that contact. Please try again in a moment.", "error")
            return redirect(url_for("agent_crm"))
        
        elif action == "add_relationship":
            contact_id_1 = request.form.get("contact_id_1")
            contact_id_2 = request.form.get("contact_id_2")
            relationship_type = request.form.get("relationship_type", "other").strip()
            notes = request.form.get("notes", "").strip()
            
            if contact_id_1 and contact_id_2:
                try:
                    result = add_crm_relationship(
                        int(contact_id_1), int(contact_id_2), "agent_contact",
                        user["id"], relationship_type, notes
                    )
                    if result:
                        flash("Relationship added!", "success")
                    else:
                        flash("Those two are already connected.", "error")
                except Exception as e:
                    flash("We could not add that connection. Please try again in a moment.", "error")
        
        elif action == "bulk_action":
            contact_ids = request.form.getlist("contact_ids")
            bulk_action_type = request.form.get("bulk_action_type", "").strip()
            
            if contact_ids and bulk_action_type:
                try:
                    for contact_id in contact_ids:
                        if bulk_action_type == "add_tag":
                            tag = request.form.get("bulk_tag", "").strip()
                            contact = get_agent_contact(int(contact_id), user["id"])
                            if contact:
                                contact_dict = dict(contact) if hasattr(contact, 'keys') else contact
                                existing_tags = (contact_dict.get("tags") or "").split(",")
                                existing_tags = [t.strip() for t in existing_tags if t.strip()]
                                if tag and tag not in existing_tags:
                                    existing_tags.append(tag)
                                    update_agent_contact(int(contact_id), user["id"], tags=", ".join(existing_tags))
                        elif bulk_action_type == "change_stage":
                            stage = request.form.get("bulk_stage", "").strip()
                            if stage:
                                update_agent_contact(int(contact_id), user["id"], stage=stage)
                    flash(f"Bulk action completed for {len(contact_ids)} contact(s)!", "success")
                except Exception as e:
                    flash("We could not complete that bulk action. Please try again in a moment.", "error")

    stage_filter = request.args.get("stage")
    search_query = request.args.get("search", "").strip()
    tag_filter = request.args.get("tag", "").strip()
    sort_by = request.args.get("sort", "name")  # name, stage, last_touch, created_at
    
    try:
        contacts = list_agent_contacts(user["id"], stage_filter)
        print(f"AGENT CRM: Found {len(contacts)} contacts from database")
        
        # DEBUG: Log all contacts found
        for idx, contact in enumerate(contacts[:5]):  # Log first 5
            contact_dict = dict(contact) if hasattr(contact, 'keys') and not isinstance(contact, dict) else contact
            print(f"  Contact {idx+1}: {contact_dict.get('name')} ({contact_dict.get('email')}) - Stage: {contact_dict.get('stage')}")
        
        if len(contacts) > 5:
            print(f"  ... and {len(contacts) - 5} more contacts")
        # Convert contacts to dicts for JSON serialization in template
        # Handle None values and ensure all fields exist
        contacts_list = []
        for contact in contacts:
            try:
                # Convert sqlite3.Row to dict, handling missing columns gracefully
                # sqlite3.Row objects need to be converted to dict explicitly
                import sqlite3
                if isinstance(contact, sqlite3.Row):
                    contact_dict = {key: contact[key] for key in contact.keys()}
                elif hasattr(contact, 'keys') and not isinstance(contact, dict):
                    # It's a Row-like object
                    contact_dict = {key: contact[key] for key in contact.keys()}
                elif isinstance(contact, dict):
                    contact_dict = contact.copy()
                else:
                    # Fallback: try to convert
                    try:
                        contact_dict = dict(contact)
                    except Exception:
                        contact_dict = {key: getattr(contact, key, None) for key in dir(contact) if not key.startswith('_')}
                
                # Ensure all expected fields exist with defaults
                expected_fields = {
                    'id': None, 'created_at': '', 'name': '', 'email': '', 'phone': '',
                    'stage': 'new', 'best_contact': '', 'last_touch': '', 'birthday': '',
                    'home_anniversary': '', 'address': '', 'notes': '', 'tags': '',
                    'property_address': '', 'property_value': None, 'equity_estimate': None,
                    'auto_birthday': 1, 'auto_anniversary': 1, 'auto_seasonal': 1,
                    'auto_equity': 1, 'auto_holidays': 1, 'equity_frequency': 'monthly',
                    'lead_source': '', 'pipeline_stage': '', 'next_action_date': '',
                    'next_action_note': '', 'city': '', 'state': '', 'zip_code': ''
                }
                for field, default in expected_fields.items():
                    if field not in contact_dict:
                        contact_dict[field] = default
                
                # Apply search filter
                if search_query:
                    search_lower = search_query.lower()
                    matches = (
                        search_lower in (contact_dict.get('name') or '').lower() or
                        search_lower in (contact_dict.get('email') or '').lower() or
                        search_lower in (contact_dict.get('phone') or '').lower() or
                        search_lower in (contact_dict.get('property_address') or '').lower() or
                        search_lower in (contact_dict.get('notes') or '').lower() or
                        search_lower in (contact_dict.get('tags') or '').lower()
                    )
                    if not matches:
                        continue
                
                # Apply tag filter
                if tag_filter:
                    contact_tags = (contact_dict.get('tags') or '').lower()
                    if tag_filter.lower() not in contact_tags:
                        continue
                
                contacts_list.append(contact_dict)
            except Exception as e:
                import traceback
                print(f"Error converting contact: {traceback.format_exc()}")
                continue
        
        # Ensure all contacts are dicts before sorting/stats
        contacts_list_dicts = []
        for c in contacts_list:
            if isinstance(c, dict):
                contacts_list_dicts.append(c)
            elif hasattr(c, 'keys'):
                try:
                    import sqlite3
                    if isinstance(c, sqlite3.Row):
                        contacts_list_dicts.append({key: c[key] for key in c.keys()})
                    else:
                        contacts_list_dicts.append(dict(c))
                except Exception as e:
                    print(f"Error converting contact to dict: {e}")
                    continue
            else:
                print(f"Skipping invalid contact: {type(c)}")
                continue
        
        # Sort contacts
        if sort_by == "name":
            contacts_list_dicts.sort(key=lambda x: (x.get('name') or '').lower() if isinstance(x, dict) else '')
        elif sort_by == "stage":
            stage_order = {
                'new': 0, 'attempted': 1, 'contacted': 2, 'appt_set': 3,
                'appt_done': 4, 'active': 5, 'under_contract': 6,
                'closed': 7, 'past': 8, 'nurture': 9, 'sphere': 10, 'hold': 11
            }
            contacts_list_dicts.sort(key=lambda x: stage_order.get(x.get('stage', 'new') if isinstance(x, dict) else 'new', 5))
        elif sort_by == "last_touch":
            contacts_list_dicts.sort(key=lambda x: (x.get('last_touch') or '') if isinstance(x, dict) else '', reverse=True)
        elif sort_by == "created_at":
            contacts_list_dicts.sort(key=lambda x: (x.get('created_at') or '') if isinstance(x, dict) else '', reverse=True)
        
        # One page at a time: stats, search, tags and birthdays cover everyone, but the heavy
        # per-contact lookups (history, tasks, deals, relationships) only run for the 50 on screen.
        PER_PAGE = 50
        try:
            page = max(1, int(request.args.get("page", 1)))
        except ValueError:
            page = 1
        filtered_total = len(contacts_list_dicts)
        pages = max(1, -(-filtered_total // PER_PAGE))
        page = min(page, pages)
        all_filtered = contacts_list_dicts
        bday_data = [
            {"name": c.get("name"), "birthday": c.get("birthday"),
             "addr": ", ".join(x for x in (c.get("address"), c.get("city"), c.get("state"), c.get("zip_code")) if x)}
            for c in all_filtered if c.get("birthday")
        ]
        contacts_list_dicts = all_filtered[(page - 1) * PER_PAGE: page * PER_PAGE]
        _page_emails = list({(c.get("email") or "").lower().strip() for c in contacts_list_dicts if c.get("email")})
        _portal_map = {}
        if _page_emails:
            _pc = get_db_connection()
            try:
                for _r in _pc.execute(
                        "SELECT id, LOWER(email) AS em FROM users WHERE role='homeowner' AND LOWER(email) IN (%s)"
                        % ",".join("?" * len(_page_emails)), _page_emails).fetchall():
                    _portal_map[_r["em"]] = _r["id"]
            finally:
                _pc.close()
        from database import crm_page_bundle
        _bundle = crm_page_bundle(user["id"], [c["id"] for c in contacts_list_dicts])
        for contact_dict in contacts_list_dicts:
            try:
                _cid = contact_dict['id']
                _ints = _bundle["interactions"].get(_cid, [])
                contact_dict['interaction_count'] = len(_ints)
                contact_dict['recent_interactions'] = _ints[:3]
                contact_dict['all_interactions'] = _ints
                _tasks = _bundle["tasks"].get(_cid, [])
                contact_dict['pending_tasks'] = _tasks
                contact_dict['task_count'] = len(_tasks)
                _deals = _bundle["deals"].get(_cid, [])
                contact_dict['deals'] = _deals
                contact_dict['deal_count'] = len(_deals)
                contact_dict['total_pipeline_value'] = sum((d.get('deal_value') or 0) for d in _deals)
                contact_dict['relationships'] = _bundle["relationships"].get(_cid, [])

                # Does this contact already have a homeowner portal account? (prefetched in one query)
                _em = (contact_dict.get('email') or '').lower().strip()
                _pid = _portal_map.get(_em) if _em else None
                contact_dict['has_portal'] = _pid is not None
                contact_dict['portal_user_id'] = _pid
            except Exception as e:
                print(f"Error enriching contact: {e}")
        contacts_list_dicts_all = all_filtered

        # Calculate stats (over everyone who matches, not just this page)
        _all = contacts_list_dicts_all
        total_contacts = len(_all)
        all_tasks = list_crm_tasks(user["id"], status="pending")
        all_deals_raw = list_crm_deals(user["id"])
        
        # Convert all_deals to dicts
        all_deals = []
        for d in all_deals_raw:
            if hasattr(d, 'keys'):
                all_deals.append(dict(d))
            else:
                all_deals.append(d)
        
        # Get follow-up threshold from user settings
        from database import get_user_by_id
        user_details = get_user_by_id(user["id"])
        if user_details and hasattr(user_details, 'keys'):
            user_details = dict(user_details)
        follow_up_days = user_details.get('follow_up_days', 30) if user_details and isinstance(user_details, dict) else 30
        
        # Get contacts needing follow-up
        try:
            from database import get_contacts_needing_followup
            contacts_needing_followup = get_contacts_needing_followup(user["id"], follow_up_days)
            needs_followup_count = len(contacts_needing_followup)
        except Exception as e:
            print(f"Error getting contacts needing followup: {e}")
            needs_followup_count = 0
        
        stats = {
            'total': total_contacts,
            'new': len([c for c in _all if c.get('stage') == 'new']),
            'active': len([c for c in _all if c.get('stage') == 'active']),
            'past': len([c for c in _all if c.get('stage') == 'past']),
            'with_automation': len([c for c in _all if any([
                c.get('auto_birthday'), c.get('auto_anniversary'),
                c.get('auto_seasonal'), c.get('auto_equity'), c.get('auto_holidays')
            ])]),
            'total_equity': sum([c.get('equity_estimate') or 0 for c in _all]),
            'pending_tasks': len(all_tasks),
            'total_deals': len(all_deals),
            'pipeline_value': sum([(d.get('deal_value') if isinstance(d, dict) else 0) or 0 for d in all_deals]),
            'expected_commission': sum([(d.get('expected_commission') if isinstance(d, dict) else 0) or 0 for d in all_deals]),
            'needs_followup': needs_followup_count,
            'follow_up_days': follow_up_days,
        }
        
        # Get all unique tags
        all_tags = set()
        for contact in _all:
            tags = contact.get('tags', '') or '' if isinstance(contact, dict) else ''
            if tags:
                all_tags.update([t.strip() for t in tags.split(',') if t.strip()])
        all_tags = sorted(list(all_tags))
        
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error loading contacts: {error_trace}")
        flash("We could not load your contacts. Please try again in a moment.", "error")
        contacts_list = []
        contacts_list_dicts = []  # Ensure this is defined even on error
        bday_data = []
        page = pages = 1
        filtered_total = 0
        stats = {'total': 0, 'new': 0, 'active': 0, 'past': 0, 'with_automation': 0, 'total_equity': 0, 'pending_tasks': 0, 'total_deals': 0, 'pipeline_value': 0, 'expected_commission': 0, 'needs_followup': 0, 'follow_up_days': 30}
        all_tags = []
    
    # Get all pending tasks for dashboard
    try:
        all_pending_tasks = list_crm_tasks(user["id"], status="pending")
        upcoming_tasks = []
        for t in all_pending_tasks[:10]:
            if hasattr(t, 'keys'):
                upcoming_tasks.append(dict(t))
            else:
                upcoming_tasks.append(t)
    except Exception as e:
        print(f"Error fetching upcoming tasks: {e}")
        upcoming_tasks = []
    
    # Get email templates for quick actions
    try:
        email_templates = list_message_templates(user["id"], "agent", "email")
    except Exception:
        email_templates = []
    
    try:
        return render_template(
            "agent/crm.html",
            brand_name=FRONT_BRAND_NAME,
            user=user,
            contacts=contacts_list_dicts,  # Use the converted dicts list
            stage_filter=stage_filter,
            search_query=search_query,
            tag_filter=tag_filter,
            sort_by=sort_by,
            stats=stats,
            all_tags=all_tags,
            upcoming_tasks=upcoming_tasks,
            email_templates=email_templates,
            page=page, pages=pages, per_page=50, filtered_total=filtered_total, bday_data=bday_data,
        )
    except Exception as e:
        import traceback
        error_msg = traceback.format_exc()
        print(f"Error rendering template: {error_msg}")
        return f"Template Error: {e}<br><pre>{error_msg}</pre>", 500


@route("/agent/crm/export.csv")
def agent_crm_export():
    """Download every contact as a spreadsheet (CSV)."""
    import csv
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["Name", "Email", "Phone", "Stage", "Lead Source", "Next Action Date", "Birthday", "Anniversary",
                "Address", "City", "State", "ZIP", "Property", "Equity", "Tags", "Notes"])
    for c in list_agent_contacts(user["id"]):
        w.writerow([c.get(k) or "" for k in ("name", "email", "phone", "stage", "lead_source", "next_action_date", "birthday",
                    "home_anniversary", "address", "city", "state", "zip_code", "property_address", "equity_estimate", "tags", "notes")])
    resp = Response(out.getvalue(), mimetype="text/csv")
    resp.headers["Content-Disposition"] = "attachment; filename=contacts_%s.csv" % datetime.now().strftime("%Y-%m-%d")
    return resp


@route("/agent/crm/address-labels")
def agent_address_labels():
    """Print address labels for agent CRM contacts (30 per page, 3x10 grid)."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    contact_id = request.args.get("contact_id", type=int)
    single_sheet = request.args.get("single_sheet") == "1"
    contacts = list_agent_contacts(user["id"], stage_filter=None)
    labels = []
    if single_sheet and contact_id:
        c = next((x for x in contacts if x.get("id") == contact_id), None)
        if c:
            name = (c.get("name") or "").strip()
            addr = _build_full_address(c) or "(No address on file)"
            city = (c.get("city") or "").strip()
            state = (c.get("state") or "").strip()
            street = (c.get("address") or "").strip()
            missing_csz = bool(street and not (city and state))
            labels = [{"id": c.get("id"), "name": name, "address": addr, "missing_csz": missing_csz}] * 30
    if not labels:
        for c in contacts:
            name = (c.get("name") or "").strip()
            addr = _build_full_address(c)
            street = (c.get("address") or "").strip()
            city = (c.get("city") or "").strip()
            state = (c.get("state") or "").strip()
            missing_csz = bool(street and not (city and state))
            if name and addr:
                labels.append({"id": c.get("id"), "name": name, "address": addr, "missing_csz": missing_csz})
            elif name:
                labels.append({"id": c.get("id"), "name": name, "address": "(No address on file)", "missing_csz": True})
    if not labels:
        labels = [{"name": "", "address": ""}] * 30
    return render_template(
        "shared/address_labels.html",
        labels=labels,
        back_url=url_for("agent_crm"),
        back_label="Back to CRM",
        role="agent",
        contacts=contacts,
        single_sheet=bool(single_sheet and contact_id),
        labels_base_url=url_for("agent_address_labels"),
    )


@route("/agent/crm/quick-update", methods=["POST"])
def agent_crm_quick_update():
    """Inline quick-save for CRM fields (e.g. last_touch)."""
    from database import get_connection as _gc
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return jsonify({"error": "Unauthorized"}), 401
    contact_id = request.form.get("contact_id", "").strip()
    field = request.form.get("field", "").strip()
    value = request.form.get("value", "").strip()
    allowed = {"last_touch"}
    if field not in allowed:
        return jsonify({"error": "Field not editable here"}), 400
    if not contact_id:
        return jsonify({"error": "Missing contact_id"}), 400
    conn = _gc()
    cur = conn.cursor()
    cur.execute(
        f"UPDATE agent_contacts SET {field} = ? WHERE id = ? AND agent_user_id = ?",
        (value, contact_id, user["id"])
    )
    conn.commit()
    conn.close()
    return jsonify({"success": True, "value": value})


@route("/agent/crm/<int:contact_id>/invite-to-portal", methods=["POST"])
def agent_crm_invite_to_portal(contact_id):
    """Send a homeowner portal invite email to a CRM contact."""
    from database import get_agent_contact, get_referral_links_for_agent, create_referral_link
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    contact = get_agent_contact(contact_id, user["id"])
    if not contact:
        flash("We could not find that contact.", "error")
        return redirect(url_for("agent_crm"))
    email = contact.get("email", "").strip()
    if not email:
        flash("This contact does not have an email address yet. Add one and try again.", "error")
        return redirect(url_for("agent_crm"))
    # Get or create referral link for this agent
    links = get_referral_links_for_agent(user["id"])
    if links:
        token = links[0]["token"]
    else:
        token = create_referral_link(agent_id=user["id"])
    referral_url = url_for("referral_landing", referral_code=token, _external=True)
    agent_name = user.get("name", "Your Agent")
    client_first = contact.get("name", "").split()[0] if contact.get("name") else "there"
    subject = f" {agent_name} invited you to your free homeowner portal"
    body = f"""Hi {client_first},

{agent_name} has set up a personal homeowner portal for you through Your Life, Your Home, and it's completely free.

Your portal gives you:
-  Home value and equity tracking
-  Home care reminders & seasonal checklists
-  Secure document storage
-  Helpful insights about your home's finances
-  Direct connection with {agent_name}

Click the link below to create your account. It only takes 2 minutes:

{referral_url}

This link is personalized for you and automatically connects your account to {agent_name}.

Looking forward to supporting you,

{agent_name}
"""
    if send_reminder_email(email, subject, body, **pro_sender(user["id"])):
        flash(f" Portal invite sent to {email}!", "success")
    else:
        flash(f" We could not send that email. Please check your email settings and try again.", "error")
    return redirect(url_for("agent_crm"))


@route("/agent/crm/import", methods=["GET", "POST"])
def agent_crm_import():
    """Agent CRM bulk import from Excel/CSV."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "agent":
            return redirect(url_for("login", role="agent"))
    except Exception as e:
        return f"Error: {e}", 500

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "upload":
            # Handle file upload
            if 'file' not in request.files:
                flash("Please choose a file to upload.", "error")
                return redirect(url_for("agent_crm_import"))
            
            file = request.files['file']
            if file.filename == '':
                flash("Please choose a file to upload.", "error")
                return redirect(url_for("agent_crm_import"))
            
            # Check file extension
            filename = file.filename.lower()
            if not (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
                flash("Please upload an Excel (.xlsx, .xls) or CSV file and we will take it from there.", "error")
                return redirect(url_for("agent_crm_import"))
            
            try:
                # Read file into pandas
                if filename.endswith('.csv'):
                    df = pd.read_csv(file)
                else:
                    df = pd.read_excel(file)
                
                # Convert to list of dicts for preview
                data = df.to_dict('records')
                
                # Get column names for mapping
                columns = list(df.columns)
                
                # Store in session for import step
                session['crm_import_data'] = json.dumps(data, default=str)
                session['crm_import_columns'] = columns
                
                return render_template(
                    "agent/crm_import_preview.html",
                    brand_name=FRONT_BRAND_NAME,
                    user=user,
                    data=data[:10],  # Preview first 10 rows
                    total_rows=len(data),
                    columns=columns,
                    sample_data=data[0] if data else {},
                )
            except Exception as e:
                import traceback
                flash("We could not read that file. Please try again in a moment.", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("agent_crm_import"))
        
        elif action == "import":
            # Actually import the data
            print("\n" + "="*60, flush=True)
            print("IMPORT ACTION TRIGGERED", flush=True)
            print("="*60, flush=True)
            
            import_data_json = session.get('crm_import_data')
            if not import_data_json:
                flash("We lost track of that import. Please upload your file again.", "error")
                return redirect(url_for("agent_crm_import"))
            
            try:
                data = json.loads(import_data_json)
                
                # Get column mappings from form
                mappings = {
                    'name': request.form.get('map_name', '').strip(),
                    'last_name': request.form.get('map_last_name', '').strip(),
                    'email': request.form.get('map_email', '').strip(),
                    'phone': request.form.get('map_phone', '').strip(),
                    'stage': request.form.get('map_stage', '').strip(),
                    'birthday': request.form.get('map_birthday', '').strip(),
                    'home_anniversary': request.form.get('map_anniversary', '').strip(),
                    'address': request.form.get('map_address', '').strip(),
                    'property_address': request.form.get('map_property_address', '').strip(),
                    'city': request.form.get('map_city', '').strip(),
                    'state': request.form.get('map_state', '').strip(),
                    'zip_code': request.form.get('map_zip', '').strip(),
                    'property_value': request.form.get('map_property_value', '').strip(),
                    'equity_estimate': request.form.get('map_equity', '').strip(),
                    'notes': request.form.get('map_notes', '').strip(),
                    'tags': request.form.get('map_tags', '').strip(),
                }
                
                _dbg(f"\n=== IMPORT DEBUG ===", flush=True)
                print(f"Mappings: {mappings}", flush=True)
                print(f"First row sample: {data[0] if data else 'No data'}", flush=True)
                print(f"First row keys: {list(data[0].keys()) if data else 'No data'}", flush=True)
                
                # Default stage if not mapped
                default_stage = request.form.get('default_stage', 'new').strip()
                
                # Smart sync: match -> update, no match -> add. No duplicates.
                imported = 0
                updated = 0
                errors = []
                existing_contacts_cache = []
                
                # Helper function to safely get and convert values, handling NaN (defined once)
                def safe_get(value):
                    if value is None:
                        return ''
                    val_str = str(value).strip()
                    # Check for various NaN representations
                    if val_str.lower() in ['nan', 'none', 'null', '']:
                        return ''
                    return val_str
                
                for idx, row in enumerate(data):
                    try:
                        # Debug first row
                        if idx == 0:
                            print(f"\nFirst row processing:")
                            print(f"  Name column mapped to: '{mappings['name']}'")
                            print(f"  Raw value: {repr(row.get(mappings['name']))}")
                            print(f"  After safe_get: '{safe_get(row.get(mappings['name'], ''))}'")
                        
                        # Map columns to fields using the column names from mappings
                        first_part = safe_get(row.get(mappings['name'])) if mappings['name'] else ''
                        last_part = safe_get(row.get(mappings['last_name'])) if mappings.get('last_name') else ''
                        name = f"{first_part} {last_part}".strip() if (first_part or last_part) else ''
                        email = safe_get(row.get(mappings['email'])) if mappings['email'] else ''
                        phone = safe_get(row.get(mappings['phone'])) if mappings['phone'] else ''
                        stage_value = safe_get(row.get(mappings['stage'])) if mappings['stage'] else ''
                        stage = (stage_value if stage_value else default_stage).strip().lower()
                        birthday = safe_get(row.get(mappings['birthday'])) if mappings['birthday'] else ''
                        home_anniversary = safe_get(row.get(mappings['home_anniversary'])) if mappings['home_anniversary'] else ''
                        address = safe_get(row.get(mappings['address'])) if mappings['address'] else ''
                        property_address = safe_get(row.get(mappings['property_address'])) if mappings['property_address'] else ''
                        city = safe_get(row.get(mappings['city'])) if mappings.get('city') else ''
                        state = safe_get(row.get(mappings['state'])) if mappings.get('state') else ''
                        zip_code = safe_get(row.get(mappings['zip_code'])) if mappings.get('zip_code') else ''
                        # If address has "Street, City, ST 12345" but city/state/zip unmapped, parse it
                        if not (city or state or zip_code) and (address or property_address):
                            addr_str = address or property_address
                            pstreet, pc, ps, pz = _parse_address_city_state_zip(addr_str)
                            if pc:
                                if address:
                                    address = pstreet or address
                                else:
                                    property_address = pstreet or property_address
                                city, state, zip_code = pc, ps or state, pz or zip_code
                        notes = safe_get(row.get(mappings['notes'])) if mappings['notes'] else ''
                        tags = safe_get(row.get(mappings['tags'])) if mappings['tags'] else ''
                        
                        # Parse numeric values
                        property_value = None
                        if mappings['property_value']:
                            prop_val_str = safe_get(row.get(mappings['property_value']))
                            if prop_val_str:
                                try:
                                    property_value = float(prop_val_str.replace(',', '').replace('$', ''))
                                except Exception:
                                    property_value = None
                        
                        equity_estimate = None
                        if mappings['equity_estimate']:
                            equity_str = safe_get(row.get(mappings['equity_estimate']))
                            if equity_str:
                                try:
                                    equity_estimate = float(equity_str.replace(',', '').replace('$', ''))
                                except Exception:
                                    equity_estimate = None
                        
                        if not name:
                            errors.append(f"Row {idx + 1}: Missing name")
                            continue
                        
                        # Find existing contact: email > phone > name (flexible)
                        if not existing_contacts_cache:
                            existing_contacts_cache = list_agent_contacts(user["id"])
                        existing_contacts = existing_contacts_cache
                        matched_existing = None
                        for existing in existing_contacts:
                            if email and existing.get('email') and existing['email'].lower() == email.lower():
                                matched_existing = existing
                                break
                            if phone and existing.get('phone') and str(existing['phone']).strip() == str(phone).strip():
                                matched_existing = existing
                                break
                            if name and _names_match(name, existing.get("name") or ""):
                                matched_existing = existing
                                break
                        
                        if matched_existing:
                            # Update existing contact with all mapped fields (only when we have values)
                            updates = {}
                            if name:
                                updates["name"] = name
                            if email:
                                updates["email"] = email
                            if phone:
                                updates["phone"] = phone
                            if stage:
                                updates["stage"] = stage
                            if birthday:
                                updates["birthday"] = birthday
                            if home_anniversary:
                                updates["home_anniversary"] = home_anniversary
                            if address:
                                updates["address"] = address
                            if property_address:
                                updates["property_address"] = property_address
                            if city:
                                updates["city"] = city
                            if state:
                                updates["state"] = state
                            if zip_code:
                                updates["zip_code"] = zip_code
                            if notes:
                                updates["notes"] = notes
                            if tags:
                                updates["tags"] = tags
                            if property_value is not None:
                                updates["property_value"] = property_value
                            if equity_estimate is not None:
                                updates["equity_estimate"] = equity_estimate
                            if updates:
                                update_agent_contact(matched_existing["id"], user["id"], **updates)
                                updated += 1
                            continue
                        
                        # Add contact
                        add_agent_contact(
                            user["id"], name, email, phone, stage, email or phone, "",
                            birthday, home_anniversary, address, notes, tags,
                            property_address, property_value, equity_estimate,
                            city=city, state=state, zip_code=zip_code
                        )
                        imported += 1
                        # Refresh cache so next rows can match this contact (prevent same-file duplicates)
                        existing_contacts_cache = list_agent_contacts(user["id"])
                    except Exception as e:
                        errors.append(f"Row {idx + 1}: {str(e)}")
                
                # Clear session
                session.pop('crm_import_data', None)
                session.pop('crm_import_columns', None)
                
                msg = f"Sync complete: {imported} added, {updated} updated"
                if errors:
                    msg += f", {len(errors)} errors"
                msg += "."
                flash(msg, "success")
                if errors:
                    flash(f"Errors: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''}", "error")
                
                return redirect(url_for("agent_crm"))
            except Exception as e:
                import traceback
                flash("We ran into trouble with that import. Please check your file and try again.", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("agent_crm_import"))
    
    # GET request - show upload form
    return render_template(
        "agent/crm_import.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@route("/agent/transactions", methods=["GET", "POST"])
def agent_transactions():
    """Agent transactions - list and create transactions."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if request.method == "POST":
        property_address = request.form.get("property_address", "").strip()
        client_name = request.form.get("client_name", "").strip()
        side = request.form.get("side", "buyer").strip()
        stage = request.form.get("stage", "pre_contract").strip()
        close_date = request.form.get("close_date", "").strip() or None

        # Map form stage values to database stage values
        # Database allows: 'pre_contract', 'under_contract', 'in_escrow', 'clear_to_close', 'closed', 'cancelled'
        stage_mapping = {
            'summary': 'pre_contract',
            'showings': 'pre_contract',
            'under_contract': 'under_contract',
            'earnest_money': 'under_contract',
            'inspection': 'in_escrow',
            'appraisal': 'in_escrow',
            'loan_commitment': 'in_escrow',
            'final_walkthrough': 'clear_to_close',
            'closing': 'clear_to_close',
            'pre_contract': 'pre_contract',
            'in_escrow': 'in_escrow',
            'clear_to_close': 'clear_to_close',
            'closed': 'closed',
            'cancelled': 'cancelled'
        }
        
        # Convert form stage to database stage, default to 'pre_contract' if not found
        db_stage = stage_mapping.get(stage, 'pre_contract')

        if property_address and client_name:
            try:
                new_tx_id = create_transaction(
                    agent_id=user["id"],
                    property_address=property_address,
                    client_name=client_name,
                    side=side,
                    current_stage=db_stage,
                    target_close_date=close_date,
                    client_email=request.form.get("client_email", "").strip(),
                    client_phone=request.form.get("client_phone", "").strip(),
                    purchase_price=request.form.get("purchase_price", "").strip() or None,
                    notes=request.form.get("notes", "").strip(),
                )
                import automation
                automation.link_transaction_parties(new_tx_id, request.form.get("lender_email", "").strip())
                _bg(automation.invite_client_if_needed, new_tx_id, send_reminder_email, _site_url())
                flash("Transaction created!", "success")
                if db_stage != "pre_contract":
                    flash("Let us add the contract details next, so your deadlines and sheets are ready.", "success")
                    return redirect(url_for("tc.contract", tx_id=new_tx_id))
            except Exception as e:
                flash("We could not create that transaction. Please try again in a moment.", "error")

    # Get contact info if coming from CRM
    contact_id = request.args.get("contact_id")
    contact_info = None
    if contact_id:
        try:
            contact = get_agent_contact(int(contact_id), user["id"])
            if contact:
                contact_dict = dict(contact) if hasattr(contact, 'keys') else contact
                contact_info = {
                    'name': contact_dict.get('name', '') if isinstance(contact_dict, dict) else (contact_dict['name'] if 'name' in contact_dict else ''),
                    'email': contact_dict.get('email', '') if isinstance(contact_dict, dict) else (contact_dict['email'] if 'email' in contact_dict else ''),
                    'phone': contact_dict.get('phone', '') if isinstance(contact_dict, dict) else (contact_dict['phone'] if 'phone' in contact_dict else ''),
                    'property_address': contact_dict.get('property_address', '') if isinstance(contact_dict, dict) else (contact_dict['property_address'] if 'property_address' in contact_dict else ''),
                }
        except Exception:
            pass
    
    transactions = get_agent_transactions(user["id"])
    return render_template(
        "agent/transactions.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        transactions=transactions,
        contact_info=contact_info,
        tc_up=_tc.upcoming_for_agent(user["id"]),
    )


@route("/agent/transactions/<int:tx_id>", methods=["GET"])
def agent_transaction_detail(tx_id):
    """View transaction details."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))

    try:
        documents = get_transaction_documents(tx_id)
    except Exception as _e:
        app.logger.warning(f"get_transaction_documents({tx_id}) failed: {_e}")
        documents = []

    try:
        participants = get_transaction_participants(tx_id)
    except Exception as _e:
        app.logger.warning(f"get_transaction_participants({tx_id}) failed: {_e}")
        participants = []

    try:
        timeline = get_transaction_timeline(tx_id)
    except Exception as _e:
        app.logger.warning(f"get_transaction_timeline({tx_id}) failed: {_e}")
        timeline = []

    try:
        doc_status = get_transaction_document_status(tx_id)
    except Exception as _e:
        app.logger.warning(f"get_transaction_document_status({tx_id}) failed: {_e}")
        doc_status = {"checklist": [], "completed": 0, "total": 0, "progress_percentage": 0}

    # Agent-only: load any existing commission record for this transaction
    tx_commission = None
    try:
        conn = get_db_connection()
        row = conn.execute(
            "SELECT * FROM agent_commissions WHERE transaction_id=? AND agent_user_id=?",
            (tx_id, user["id"])
        ).fetchone()
        conn.close()
        if row:
            tx_commission = dict(row)
    except Exception:
        pass

    return render_template(
        "agent/transaction_detail.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        transaction=transaction,
        tx=transaction,
        documents=documents,
        participants=participants,
        timeline=timeline,
        doc_status=doc_status,
        tx_commission=tx_commission,
        tc=_tc.card_context(tx_id),
    )


@route("/agent/transactions/<int:tx_id>/commission", methods=["POST"])
def agent_transaction_commission_save(tx_id):
    """Save agent commission details for a transaction. Agent-only, never visible to client."""
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))

    f = request.form
    sale_price   = float(f.get("sale_price") or transaction.get("purchase_price") or 0)
    comm_rate    = float(f.get("commission_rate") or 3.0)
    split_pct    = float(f.get("brokerage_split_pct") or 0)
    gross        = round(sale_price * comm_rate / 100, 2)
    split_amt    = round(gross * split_pct / 100, 2)
    net          = round(gross - split_amt, 2)
    status       = f.get("status", "projected")
    close_date   = f.get("close_date") or transaction.get("target_close_date") or ""
    notes        = f.get("notes", "")
    tx_side      = f.get("transaction_side") or transaction.get("side") or "buyer"
    client_name  = transaction.get("client_name") or ""
    prop_addr    = transaction.get("property_address") or ""

    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id FROM agent_commissions WHERE transaction_id=? AND agent_user_id=?",
        (tx_id, user["id"])
    ).fetchone()

    if existing:
        conn.execute("""
            UPDATE agent_commissions SET
              property_address=?, client_name=?, close_date=?, transaction_side=?,
              sale_price=?, commission_rate=?, gross_commission=?, brokerage_split_pct=?,
              brokerage_split_amt=?, net_commission=?, status=?, notes=?
            WHERE id=?
        """, (prop_addr, client_name, close_date, tx_side,
              sale_price, comm_rate, gross, split_pct, split_amt, net, status, notes,
              existing["id"]))
    else:
        conn.execute("""
            INSERT INTO agent_commissions
            (agent_user_id, transaction_id, property_address, client_name, close_date,
             transaction_side, sale_price, commission_rate, gross_commission,
             brokerage_split_pct, brokerage_split_amt, net_commission, status, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (user["id"], tx_id, prop_addr, client_name, close_date,
              tx_side, sale_price, comm_rate, gross, split_pct, split_amt, net, status, notes))

    conn.commit()
    conn.close()
    flash("Commission details saved to Financials Hub.", "success")
    return redirect(url_for("agent_transaction_detail", tx_id=tx_id))


@route("/agent/transactions/<int:tx_id>/add-client-to-crm", methods=["POST"])
def agent_transaction_add_client_to_crm(tx_id):
    """Add transaction client to CRM."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return jsonify({"success": False, "error": "Unauthorized"}), 401

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        return jsonify({"success": False, "error": "Transaction not found"}), 404

    try:
        # Get client info from form data or transaction
        if request.is_json:
            data = request.get_json()
            client_name = data.get("client_name", "").strip()
            client_email = data.get("client_email", "").strip()
            client_phone = data.get("client_phone", "").strip()
        else:
            client_name = request.form.get("client_name", "").strip()
            client_email = request.form.get("client_email", "").strip()
            client_phone = request.form.get("client_phone", "").strip()
        
        # Fallback to transaction data if not provided
        if not client_name:
            client_name = transaction.get("client_name") or ""
        if not client_email:
            client_email = transaction.get("client_email") or ""
        if not client_phone:
            client_phone = transaction.get("client_phone") or ""
        
        property_address = transaction.get("property_address") or ""
        
        if not client_name:
            return jsonify({"success": False, "error": "Client name is required"}), 400
        
        # Check if contact already exists
        from database import list_agent_contacts
        contacts = list_agent_contacts(user["id"])
        existing = None
        for contact in contacts:
            contact_dict = dict(contact) if hasattr(contact, 'keys') else contact
            if (contact_dict.get('name', '').lower() == client_name.lower() or
                (client_email and contact_dict.get('email', '').lower() == client_email.lower()) or
                (client_phone and contact_dict.get('phone', '') == client_phone)):
                existing = contact_dict
                break
        
        if existing:
            return jsonify({"success": True, "message": "Client already exists in CRM", "contact_id": existing.get('id')}), 200
        
        # Add to CRM
        from database import add_agent_contact
        contact_id = add_agent_contact(
            agent_user_id=user["id"],
            name=client_name,
            email=client_email,
            phone=client_phone,
            stage="active",
            property_address=property_address
        )
        
        return jsonify({"success": True, "message": "Client added to CRM successfully", "contact_id": contact_id}), 200
    except Exception as e:
        import traceback
        print(f"Error adding client to CRM: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@route("/agent/transactions/<int:tx_id>/edit", methods=["GET", "POST"])
def agent_transaction_edit(tx_id):
    """Edit transaction details."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))

    if request.method == "POST":
        # Map form stage values to database stage values
        stage_mapping = {
            'summary': 'pre_contract',
            'showings': 'pre_contract',
            'under_contract': 'under_contract',
            'earnest_money': 'under_contract',
            'inspection': 'in_escrow',
            'appraisal': 'in_escrow',
            'loan_commitment': 'in_escrow',
            'final_walkthrough': 'clear_to_close',
            'closing': 'clear_to_close',
            'pre_contract': 'pre_contract',
            'in_escrow': 'in_escrow',
            'clear_to_close': 'clear_to_close',
            'closed': 'closed',
            'cancelled': 'cancelled'
        }
        
        stage = request.form.get("stage", "").strip()
        db_stage = stage_mapping.get(stage, transaction.get('current_stage', 'pre_contract'))
        
        close_date = request.form.get("close_date", "").strip() or None
        purchase_price = request.form.get("purchase_price", "").strip()
        
        update_data = {
            'property_address': request.form.get("property_address", "").strip(),
            'client_name': request.form.get("client_name", "").strip(),
            'client_email': request.form.get("client_email", "").strip(),
            'client_phone': request.form.get("client_phone", "").strip(),
            'side': request.form.get("side", "").strip(),
            'current_stage': db_stage,
            'purchase_price': float(purchase_price) if purchase_price else None,
            'target_close_date': close_date,
            'notes': request.form.get("notes", "").strip(),
        }
        
        if update_transaction(tx_id, user["id"], **update_data):
            flash("Transaction updated!", "success")
            # Schedule review request if stage was just set to closed
            if db_stage == 'closed':
                try:
                    c_email = update_data.get("client_email") or transaction.get("client_email") or ""
                    c_name = update_data.get("client_name") or transaction.get("client_name") or ""
                    if c_email:
                        schedule_review_request(user["id"], tx_id, c_name, c_email)
                except Exception:
                    pass
            return redirect(url_for("agent_transaction_detail", tx_id=tx_id))
        else:
            flash("We could not update that transaction. Please try again in a moment.", "error")

    # Get participants for displaying additional clients
    participants = get_transaction_participants(tx_id)
    transaction['participants'] = participants
    
    return render_template(
        "agent/transaction_edit.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        transaction=transaction,
    )


@route("/agent/transactions/<int:tx_id>/change-stage", methods=["POST"])
def agent_transaction_change_stage(tx_id):
    """Change transaction stage."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))

    new_stage = request.form.get("new_stage", "").strip()
    sub_stage = request.form.get("sub_stage", "").strip()
    
    # Handle custom format (pre_contract:summary or pre_contract:showings)
    if ':' in new_stage:
        parts = new_stage.split(':')
        new_stage = parts[0]
        sub_stage = parts[1] if len(parts) > 1 else sub_stage
    
    if not new_stage:
        flash("Please choose a stage.", "error")
        return redirect(url_for("agent_transaction_detail", tx_id=tx_id))

    # Validate stage
    valid_stages = ['pre_contract', 'under_contract', 'in_escrow', 'clear_to_close', 'closed', 'cancelled']
    if new_stage not in valid_stages:
        flash("That stage is not one we recognize. Please pick one from the list.", "error")
        return redirect(url_for("agent_transaction_detail", tx_id=tx_id))

    try:
        from transaction_helpers import update_transaction_stage
        if update_transaction_stage(tx_id, new_stage, user["id"], auto_changed=False):
            # Store sub-stage in notes if needed (for Summary vs Showings distinction)
            if sub_stage and new_stage == 'pre_contract':
                pass
            flash("Transaction stage updated.", "success")
            try:
                import automation
                automation.link_transaction_parties(tx_id)
                if new_stage == "closed":
                    automation.on_transaction_closed(tx_id)
                _bg(automation.notify_stage_change, tx_id, new_stage, send_reminder_email, _site_url())
            except Exception as _auto_err:
                print(f"[AUTOMATION] stage hook failed: {_auto_err}")
            # AI: Auto-generate recommended tasks for the new stage (background thread)
            try:
                import threading as _thr
                _tx_snap = dict(transaction)
                _uid = user["id"]
                def _ai_gen_tasks():
                    try:
                        from ai_platform import ai_transaction_tasks
                        from database import add_task, get_connection as _gc3
                        tasks = ai_transaction_tasks(
                            property_address=_tx_snap.get("property_address",""),
                            client_name=_tx_snap.get("client_name",""),
                            side=_tx_snap.get("transaction_type","buyer"),
                            stage=new_stage,
                            close_date=str(_tx_snap.get("target_close_date",""))
                        )
                        for t in tasks:
                            try:
                                add_task(_uid, title=t, related_transaction_id=tx_id,
                                         status="pending", priority="medium")
                            except Exception:
                                pass
                    except Exception:
                        pass
                _thr.Thread(target=_ai_gen_tasks, daemon=True).start()
                flash(" AI is generating recommended tasks for this stage.", "info")
            except Exception:
                pass
            # When a transaction closes, schedule a review request
            if new_stage == 'closed':
                try:
                    client_email = transaction.get("client_email") or ""
                    client_name = transaction.get("client_name") or ""
                    if client_email:
                        schedule_review_request(user["id"], tx_id, client_name, client_email)
                        print(f"[REVIEW] Scheduled review request for {client_email}")
                except Exception as rev_err:
                    print(f"[REVIEW] Could not schedule review request: {rev_err}")
        else:
            flash("We could not update that stage. Please try again.", "error")
    except Exception as e:
        import traceback
        print(f"Error changing stage: {traceback.format_exc()}")
        flash("We could not update that stage. Please try again in a moment.", "error")

    return redirect(url_for("agent_transaction_detail", tx_id=tx_id))


@route("/agent/transactions/<int:tx_id>/delete", methods=["POST"])
def agent_transaction_delete(tx_id):
    """Delete a transaction."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if delete_transaction(tx_id, user["id"]):
        flash("Transaction deleted.", "success")
    else:
        flash("We could not delete that transaction. Please try again.", "error")

    return redirect(url_for("agent_transactions"))


@route("/agent/transactions/<int:tx_id>/feature-spotlight-cards")
def agent_feature_spotlight_cards(tx_id):
    """Feature Spotlight Cards generator page."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))
    
    # Get saved card sets for this transaction
    from database import get_spotlight_card_sets
    saved_sets = get_spotlight_card_sets(user["id"], tx_id)
    
    # Get agent profile for branding
    from database import get_user_profile
    agent_profile = None
    brokerage_logo = None
    
    try:
        agent_profile = get_user_profile(user["id"])
        if agent_profile:
            # Convert Row to dict if needed
            if hasattr(agent_profile, 'keys') and not isinstance(agent_profile, dict):
                agent_profile = dict(agent_profile)
            brokerage_logo = agent_profile.get("brokerage_logo")
            print(f"[SPOTLIGHT CARDS] Agent profile loaded: logo={brokerage_logo[:50] if brokerage_logo else 'None'}...")
    except Exception as e:
        import traceback
        print(f"[SPOTLIGHT CARDS] Error getting agent profile: {e}")
        print(traceback.format_exc())
    
    # Use fallback if no logo
    if not brokerage_logo:
        print(f"[SPOTLIGHT CARDS] No logo found, using fallback")
        brokerage_logo = "https://i.postimg.cc/zB5B38Bq/KCRE-Logo.png"

    return render_template(
        "agent/feature_spotlight_cards.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        tx_id=tx_id,
        transaction=transaction,
        saved_sets=saved_sets,
        brokerage_logo=brokerage_logo,
        agent_name=user.get("name", ""),
    )


@route("/agent/feature-spotlight/refine", methods=["POST"])
def agent_feature_spotlight_refine():
    """Refine a single feature's text using AI."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    try:
        data = request.get_json()
        feature = {
            'title': data.get('title', ''),
            'room': data.get('room', ''),
            'description': data.get('description', '')
        }
        
        refined = refine_feature_text(feature)
        
        return jsonify({
            "success": True,
            "refined": refined
        })
    except Exception as e:
        import traceback
        print(f"Error refining feature: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@route("/agent/spotlight-cards/generate-from-notes", methods=["POST"])
def agent_spotlight_cards_generate_from_notes():
    """Generate spotlight cards from walkthrough notes using AI."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    try:
        data = request.get_json()
        notes = data.get('notes', '').strip()
        
        if not notes:
            return jsonify({"success": False, "error": "No notes provided"}), 400
        
        # Use AI to extract features from notes
        features = extract_features_from_notes(notes)
        
        if not features:
            return jsonify({"success": False, "error": "Could not extract features from notes"}), 400
        
        return jsonify({
            "success": True,
            "features": features
        })
    except Exception as e:
        import traceback
        print(f"Error generating from notes: {traceback.format_exc()}")
        return jsonify({"success": False, "error": str(e)}), 500


@route("/agent/transactions/<int:tx_id>/feature-spotlight-cards/generate", methods=["POST"])
def agent_feature_spotlight_cards_generate(tx_id):
    """Generate Feature Spotlight Cards PDF."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))

    # Parse features from form data
    features = []
    import re
    
    # Get all form keys
    form_data = request.form.to_dict(flat=False)
    
    # Find all feature indices
    feature_indices = set()
    for key in form_data.keys():
        match = re.search(r'features\[(\d+)\]\[(\w+)\]', key)
        if match:
            feature_indices.add(int(match.group(1)))
    
    # Build features list
    for idx in sorted(feature_indices):
        title_key = f'features[{idx}][title]'
        room_key = f'features[{idx}][room]'
        desc_key = f'features[{idx}][description]'
        
        title = request.form.get(title_key, '').strip()
        room = request.form.get(room_key, '').strip()
        desc = request.form.get(desc_key, '').strip()
        
        if title and room and desc:
            features.append({
                'title': title,
                'room': room,
                'description': desc
            })
    
    if not features:
        flash("Please add at least one feature to get started.", "error")
        return redirect(url_for("agent_feature_spotlight_cards", tx_id=tx_id))

    from datetime import datetime

    # Save the card set automatically
    set_name = request.form.get('set_name', '').strip()
    if not set_name:
        set_name = f"Cards - {datetime.now().strftime('%b %d, %Y %I:%M %p')}"

    try:
        from database import save_spotlight_card_set
        save_spotlight_card_set(
            user["id"], tx_id, set_name,
            transaction.get('property_address', ''), features
        )
    except Exception as e:
        import traceback
        print(f"Error saving card set: {traceback.format_exc()}")

    # Get agent branding
    agent_name = user.get("name", "Your Agent")
    brokerage_logo = "https://i.postimg.cc/zB5B38Bq/KCRE-Logo.png"
    try:
        from database import get_user_profile
        agent_profile = get_user_profile(user["id"])
        if agent_profile and agent_profile.get("brokerage_logo"):
            brokerage_logo = agent_profile["brokerage_logo"]
    except Exception:
        pass

    # Render HTML print page directly — no WeasyPrint, no AI refinement per card
    try:
        html_preview = render_template(
            "agent/feature_spotlight_pdf.html",
            features=features,
            property_address=transaction.get('property_address', 'Property'),
            agent_name=agent_name,
            brokerage_logo=brokerage_logo,
            auto_print=True,
        )
        return html_preview
    except Exception as e:
        import traceback
        print(f"Error rendering spotlight cards: {traceback.format_exc()}")
        flash("We could not create those cards just now. Please try Preview Cards instead.", "error")
        return redirect(url_for("agent_feature_spotlight_cards", tx_id=tx_id))


@route("/agent/spotlight-cards/<int:set_id>/load")
def agent_spotlight_cards_load(set_id):
    """Load a saved spotlight card set."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    from database import get_spotlight_card_set
    card_set = get_spotlight_card_set(set_id, user["id"])
    
    if not card_set:
        return jsonify({"success": False, "error": "Card set not found"}), 404
    
    return jsonify({
        "success": True,
        "card_set": card_set
    })


@route("/agent/spotlight-cards/<int:set_id>/update", methods=["POST"])
def agent_spotlight_cards_update(set_id):
    """Update a saved spotlight card set."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    from database import update_spotlight_card_set
    
    data = request.get_json()
    set_name = data.get('set_name', '').strip()
    property_address = data.get('property_address', '').strip()
    features = data.get('features', [])
    
    if not set_name or not features:
        return jsonify({"success": False, "error": "Missing required fields"}), 400
    
    success = update_spotlight_card_set(set_id, user["id"], set_name, property_address, features)
    
    if success:
        return jsonify({"success": True, "message": "Card set updated successfully"})
    else:
        return jsonify({"success": False, "error": "Failed to update card set"}), 500


@route("/agent/spotlight-cards/<int:set_id>/delete", methods=["POST"])
def agent_spotlight_cards_delete(set_id):
    """Delete a saved spotlight card set."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    from database import delete_spotlight_card_set
    
    success = delete_spotlight_card_set(set_id, user["id"])
    
    if success:
        return jsonify({"success": True, "message": "Card set deleted successfully"})
    else:
        return jsonify({"success": False, "error": "Failed to delete card set"}), 500


@route("/agent/transactions/<int:tx_id>/marketing-hub")
def agent_marketing_hub(tx_id):
    """Marketing Hub - Generate luxury marketing assets for this transaction."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))
    
    # Get agent profile for branding
    from database import get_user_profile
    agent_profile = None
    try:
        agent_profile = get_user_profile(user["id"])
        if agent_profile and hasattr(agent_profile, 'keys'):
            agent_profile = dict(agent_profile)
    except Exception as e:
        print(f"Error getting agent profile: {e}")
    
    return render_template(
        "agent/marketing_hub.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        tx_id=tx_id,
        transaction=transaction,
        agent_profile=agent_profile,
    )


@route("/agent/marketing-hub")
def agent_marketing_hub_global():
    """Global Marketing Hub - Create marketing without a specific transaction."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    # Get all transactions for selection
    transactions = get_agent_transactions(user["id"])
    
    # Get agent profile for branding
    from database import get_user_profile
    agent_profile = None
    try:
        agent_profile = get_user_profile(user["id"])
        if agent_profile and hasattr(agent_profile, 'keys'):
            agent_profile = dict(agent_profile)
    except Exception as e:
        print(f"Error getting agent profile: {e}")
    
    return render_template(
        "agent/marketing_hub_global.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        transactions=transactions,
        agent_profile=agent_profile,
    )


@route("/agent/transactions/<int:tx_id>/marketing-hub/create")
def agent_marketing_create(tx_id):
    """Create a marketing asset with customization."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))
    
    # Get category and asset type from query params
    category = request.args.get('category', 'just-listed')
    asset_type = request.args.get('type', 'flyer')
    
    # Get agent profile for branding
    from database import get_user_profile
    agent_profile = None
    try:
        agent_profile = get_user_profile(user["id"])
        if agent_profile and hasattr(agent_profile, 'keys'):
            agent_profile = dict(agent_profile)
    except Exception as e:
        print(f"Error getting agent profile: {e}")
    
    return render_template(
        "agent/marketing_create.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        tx_id=tx_id,
        transaction=transaction,
        agent_profile=agent_profile,
        category=category,
        asset_type=asset_type,
    )


@route("/agent/transactions/<int:tx_id>/marketing-hub/generate", methods=["POST"])
def agent_marketing_generate(tx_id):
    """Generate the final marketing asset HTML for printing."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    transaction = get_transaction_detail(tx_id)
    if not transaction or transaction.get("agent_id") != user["id"]:
        flash("We could not find that transaction.", "error")
        return redirect(url_for("agent_transactions"))
    
    try:
        # Get form data
        category = request.form.get('category', '')
        asset_type = request.form.get('asset_type', '')
        headline = request.form.get('headline', '')
        subtext = request.form.get('subtext', '')
        price = request.form.get('price', '')
        property_address = request.form.get('property_address', '')
        custom_text = request.form.get('custom_text', '')
        color_scheme = request.form.get('color_scheme', 'classic')
        layout_style = request.form.get('layout_style', 'classic')
        include_photo = request.form.get('include_photo') == 'on'
        include_logo = request.form.get('include_logo') == 'on'
        include_lender = request.form.get('include_lender') == 'on'
        
        # Handle property photo uploads
        property_photos = []
        if 'property_photos' in request.files:
            files = request.files.getlist('property_photos')
            for file in files[:3]:  # Limit to 3 photos
                if file and file.filename:
                    try:
                        # Read file and convert to base64 for embedding
                        import base64
                        file_data = file.read()
                        
                        # Detect image type from magic bytes
                        img_type = None
                        if file_data.startswith(b'\xFF\xD8\xFF'):
                            img_type = 'jpeg'
                        elif file_data.startswith(b'\x89PNG\r\n\x1a\n'):
                            img_type = 'png'
                        elif file_data.startswith(b'GIF87a') or file_data.startswith(b'GIF89a'):
                            img_type = 'gif'
                        elif file_data.startswith(b'RIFF') and file_data[8:12] == b'WEBP':
                            img_type = 'webp'
                        else:
                            img_type = 'jpeg'  # Default fallback
                        
                        # Convert to base64 data URL
                        base64_data = base64.b64encode(file_data).decode('utf-8')
                        data_url = f"data:image/{img_type};base64,{base64_data}"
                        property_photos.append(data_url)
                    except Exception as e:
                        print(f"Error processing property photo: {e}")
                        continue
        
        # Get agent profile for branding
        from database import get_user_profile
        agent_profile = get_user_profile(user["id"])
        if agent_profile and hasattr(agent_profile, 'keys'):
            agent_profile = dict(agent_profile)
        
        # Render the marketing asset template
        html_content = render_template(
            f"agent/marketing_templates/{category}_{asset_type}.html",
            transaction=transaction,
            agent_profile=agent_profile,
            user=user,
            headline=headline,
            subtext=subtext,
            price=price,
            property_address=property_address,
            custom_text=custom_text,
            color_scheme=color_scheme,
            layout_style=layout_style,
            property_photos=property_photos,
            include_photo=include_photo,
            include_logo=include_logo,
            include_lender=include_lender,
        )
        
        # Return HTML with print button for browser-based PDF generation
        return html_content
            
    except Exception as e:
        import traceback
        print(f"Error generating marketing asset: {traceback.format_exc()}")
        flash("We could not create that. Please try again in a moment.", "error")
        return redirect(url_for('agent_marketing_hub', tx_id=tx_id))


@route("/agent/marketing/refine-text", methods=["POST"])
def agent_marketing_refine_text():
    """Refine marketing text using AI to sound professional but natural."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return jsonify({"success": False, "error": "Unauthorized"}), 401
    
    try:
        data = request.get_json()
        text = data.get('text', '').strip()
        field = data.get('field', 'text')
        
        if not text:
            return jsonify({"success": False, "error": "No text provided"}), 400
        
        # Use OpenAI to refine the text
        openai_api_key = os.environ.get('OPENAI_API_KEY')
        if not openai_api_key:
            return jsonify({"success": False, "error": "AI service not configured"}), 500
        
        from openai import OpenAI
        client = OpenAI(api_key=openai_api_key)
        
        prompt = f"""You are a luxury real estate marketing expert. Refine this {field} to be:
- Professional and sophisticated
- Natural and human-sounding (NOT robotic or overly formal)
- Compelling and elegant
- Concise and impactful
- Appropriate for high-end real estate marketing

Original {field}: {text}

Return ONLY the refined text, nothing else. Keep it roughly the same length."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a luxury real estate marketing copywriter who creates elegant, natural-sounding copy."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.7
        )
        
        from ai_platform import humanize as _humanize
        refined_text = _humanize(response.choices[0].message.content.strip())
        # Remove quotes if AI added them
        refined_text = refined_text.strip('"').strip("'")
        
        return jsonify({
            "success": True,
            "refined_text": refined_text
        })
        
    except Exception as e:
        import traceback
        print(f"Error refining marketing text: {traceback.format_exc()}")
        return jsonify({"success": False, "error": "Failed to refine text"}), 500


@route("/agent/communications", methods=["GET", "POST"])
def agent_communications():
    """Agent communications - message templates."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if request.method == "POST":
        label = request.form.get("label", "").strip()
        body = request.form.get("body", "").strip()
        if label and body:
            try:
                add_message_template(
                    user["id"], "agent", label,
                    request.form.get("category", "General").strip(),
                    request.form.get("channel", "email").strip(),
                    request.form.get("subject", "").strip(), body,
                )
                flash("Template saved!", "success")
            except Exception as e:
                print(f"[TEMPLATES] save failed: {e}")
                flash("We could not save that template. Please try again.", "error")
        else:
            flash("Please give the template a name and a message.", "error")
        return redirect(url_for("agent_communications"))

    templates = list_message_templates("agent", user["id"])
    return render_template(
        "agent/communications.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        templates=templates,
    )


@route("/agent/marketing", methods=["GET", "POST"])
def agent_marketing():
    """Agent marketing - marketing templates and campaigns."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    if request.method == "POST":
        template_name = request.form.get("template_name", "").strip()
        template_content = request.form.get("template_content", "").strip()
        template_type = request.form.get("template_type", "social").strip()

        if template_name and template_content:
            try:
                add_marketing_template(user["id"], template_name, template_content, template_type)
                flash("Marketing template saved!", "success")
            except Exception as e:
                flash("We could not save that template. Please try again in a moment.", "error")

    templates = list_marketing_templates(user["id"])
    return render_template(
        "agent/marketing.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        templates=templates,
    )


@route("/agent/power-tools", methods=["GET"])
def agent_power_tools():
    """Agent power tools - advanced agent features."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    # Power Tools only ever held two links (Invoices and Seasonal Checklists), which now sit in the menu.
    return redirect(url_for("agent_invoices"))


@route("/agent/invoices", methods=["GET"])
def agent_invoices():
    """Invoice dashboard, list all invoices."""
    from database import list_invoices, list_agent_contacts
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    status_filter = request.args.get("status", "").strip()
    invoices = list_invoices(user["id"], status_filter if status_filter else None)
    # totals summary
    all_inv = list_invoices(user["id"])
    total_outstanding = sum(i["total"] for i in all_inv if i["status"] in ("sent", "overdue"))
    total_paid = sum((i["paid_amount"] or i["total"]) for i in all_inv if i["status"] == "paid")
    total_draft = sum(i["total"] for i in all_inv if i["status"] == "draft")
    contacts = []
    return render_template(
        "agent/invoices.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        invoices=invoices,
        status_filter=status_filter,
        total_outstanding=total_outstanding,
        total_paid=total_paid,
        total_draft=total_draft,
        contacts=contacts,
    )


@route("/agent/crm/lookup")
def agent_crm_lookup():
    """Type-ahead over the signed-in agent's own contacts (name, email or phone), eight at a time."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return jsonify(ok=False), 401
    q = (request.args.get("q") or "").strip().replace("%", "").replace("_", "")
    if len(q) < 2:
        return jsonify(ok=True, contacts=[])
    conn = get_connection()
    rows = conn.execute(
        """SELECT id, name, email, address, city, state, zip_code FROM agent_contacts
           WHERE agent_user_id = ? AND (name LIKE ? OR email LIKE ? OR phone LIKE ?)
           ORDER BY name LIMIT 8""", (user["id"], "%" + q + "%", "%" + q + "%", "%" + q + "%")).fetchall()
    conn.close()
    return jsonify(ok=True, contacts=[dict(r) for r in rows])


@route("/agent/invoices/new", methods=["GET", "POST"])
def agent_invoice_new():
    """Create a new invoice."""
    from database import (create_invoice, set_invoice_items, update_invoice,
                          list_agent_contacts, get_invoice, get_invoice_items)
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    contacts = []  # the form searches the CRM as you type, so the page never carries every contact
    prefill_contact_id = request.args.get("contact_id", type=int)
    prefill_contact = None
    if prefill_contact_id:
        from database import get_agent_contact
        _pc = get_agent_contact(prefill_contact_id, user["id"])
        prefill_contact = dict(_pc) if _pc else None

    if request.method == "POST":
        # Gather client info
        contact_id = request.form.get("contact_id", "").strip() or None
        client_name = request.form.get("client_name", "").strip()
        client_email = request.form.get("client_email", "").strip()
        client_address = request.form.get("client_address", "").strip()
        client_city = request.form.get("client_city", "").strip()
        client_state = request.form.get("client_state", "").strip()
        client_zip = request.form.get("client_zip", "").strip()
        issue_date = request.form.get("issue_date", "").strip()
        due_date = request.form.get("due_date", "").strip()
        notes = request.form.get("notes", "").strip()
        terms = request.form.get("terms", "Payment due within 30 days of invoice date.").strip()
        tax_rate = float(request.form.get("tax_rate", "0") or 0)
        discount_amount = float(request.form.get("discount_amount", "0") or 0)

        # Line items
        descs = request.form.getlist("item_desc[]")
        qtys = request.form.getlist("item_qty[]")
        prices = request.form.getlist("item_price[]")
        items = []
        for desc, qty, price in zip(descs, qtys, prices):
            desc = desc.strip()
            if not desc:
                continue
            try:
                qty_f = float(qty or 1)
                price_f = float(price or 0)
            except ValueError:
                qty_f, price_f = 1.0, 0.0
            items.append({"description": desc, "quantity": qty_f, "unit_price": price_f})

        subtotal = sum(i["quantity"] * i["unit_price"] for i in items)
        tax_amount = round(subtotal * (tax_rate / 100), 2)
        total = round(subtotal + tax_amount - discount_amount, 2)

        inv_id = create_invoice(
            user["id"],
            contact_id=int(contact_id) if contact_id else None,
            client_name=client_name, client_email=client_email,
            client_address=client_address, client_city=client_city,
            client_state=client_state, client_zip=client_zip,
            issue_date=issue_date, due_date=due_date,
            notes=notes, terms=terms,
            status="draft",
            subtotal=round(subtotal, 2),
            tax_rate=tax_rate, tax_amount=tax_amount,
            discount_amount=discount_amount, total=total,
        )
        if items:
            set_invoice_items(inv_id, items)

        action = request.form.get("save_action", "save")
        if action == "send":
            update_invoice(inv_id, user["id"], status="sent")
            flash("Invoice created and marked as Sent!", "success")
        else:
            flash("Invoice saved as Draft!", "success")
        return redirect(url_for("agent_invoices"))

    from datetime import date, timedelta
    today = date.today().isoformat()
    due = (date.today() + timedelta(days=30)).isoformat()
    return render_template(
        "agent/invoice_form.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        contacts=contacts,
        prefill_contact=prefill_contact,
        invoice=None,
        items=[],
        today=today,
        due_date_default=due,
        mode="new",
    )


@route("/agent/invoices/<int:inv_id>/edit", methods=["GET", "POST"])
def agent_invoice_edit(inv_id):
    """Edit an existing invoice."""
    from database import (get_invoice, get_invoice_items, update_invoice,
                          set_invoice_items, list_agent_contacts)
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    invoice = get_invoice(inv_id, user["id"])
    if not invoice:
        flash("We could not find that invoice.", "error")
        return redirect(url_for("agent_invoices"))

    contacts = []

    if request.method == "POST":
        contact_id = request.form.get("contact_id", "").strip() or None
        client_name = request.form.get("client_name", "").strip()
        client_email = request.form.get("client_email", "").strip()
        client_address = request.form.get("client_address", "").strip()
        client_city = request.form.get("client_city", "").strip()
        client_state = request.form.get("client_state", "").strip()
        client_zip = request.form.get("client_zip", "").strip()
        issue_date = request.form.get("issue_date", "").strip()
        due_date = request.form.get("due_date", "").strip()
        notes = request.form.get("notes", "").strip()
        terms = request.form.get("terms", "").strip()
        tax_rate = float(request.form.get("tax_rate", "0") or 0)
        discount_amount = float(request.form.get("discount_amount", "0") or 0)

        descs = request.form.getlist("item_desc[]")
        qtys = request.form.getlist("item_qty[]")
        prices = request.form.getlist("item_price[]")
        items = []
        for desc, qty, price in zip(descs, qtys, prices):
            desc = desc.strip()
            if not desc:
                continue
            try:
                qty_f = float(qty or 1)
                price_f = float(price or 0)
            except ValueError:
                qty_f, price_f = 1.0, 0.0
            items.append({"description": desc, "quantity": qty_f, "unit_price": price_f})

        subtotal = sum(i["quantity"] * i["unit_price"] for i in items)
        tax_amount = round(subtotal * (tax_rate / 100), 2)
        total = round(subtotal + tax_amount - discount_amount, 2)

        update_invoice(
            inv_id, user["id"],
            contact_id=int(contact_id) if contact_id else None,
            client_name=client_name, client_email=client_email,
            client_address=client_address, client_city=client_city,
            client_state=client_state, client_zip=client_zip,
            issue_date=issue_date, due_date=due_date,
            notes=notes, terms=terms,
            subtotal=round(subtotal, 2), tax_rate=tax_rate,
            tax_amount=tax_amount, discount_amount=discount_amount, total=total,
        )
        set_invoice_items(inv_id, items)

        action = request.form.get("save_action", "save")
        if action == "send":
            update_invoice(inv_id, user["id"], status="sent")
            flash("Invoice updated and marked as Sent!", "success")
        elif action == "paid":
            update_invoice(inv_id, user["id"], status="paid",
                           paid_date=__import__("datetime").date.today().isoformat(),
                           paid_amount=total)
            flash("Invoice marked as Paid!", "success")
        else:
            flash("Invoice updated!", "success")
        return redirect(url_for("agent_invoices"))

    items = get_invoice_items(inv_id)
    from datetime import date, timedelta
    today = date.today().isoformat()
    return render_template(
        "agent/invoice_form.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        contacts=contacts,
        prefill_contact=None,
        invoice=invoice,
        items=items,
        today=today,
        due_date_default=invoice.get("due_date") or today,
        mode="edit",
    )


@route("/agent/invoices/<int:inv_id>/status", methods=["POST"])
def agent_invoice_status(inv_id):
    """Quick-update invoice status."""
    from database import update_invoice
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return jsonify({"error": "Unauthorized"}), 401
    new_status = request.form.get("status", "").strip()
    if new_status not in ("draft", "sent", "paid", "overdue"):
        return jsonify({"error": "Invalid status"}), 400
    kwargs = {"status": new_status}
    if new_status == "paid":
        from database import get_invoice
        inv = get_invoice(inv_id, user["id"])
        if inv:
            kwargs["paid_amount"] = inv["total"]
            kwargs["paid_date"] = __import__("datetime").date.today().isoformat()
    update_invoice(inv_id, user["id"], **kwargs)
    return jsonify({"success": True, "status": new_status})


@route("/agent/invoices/<int:inv_id>/delete", methods=["POST"])
def agent_invoice_delete(inv_id):
    """Delete an invoice."""
    from database import delete_invoice
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    delete_invoice(inv_id, user["id"])
    flash("Invoice deleted.", "success")
    return redirect(url_for("agent_invoices"))


@route("/agent/invoices/<int:inv_id>/print")
def agent_invoice_print(inv_id):
    """Print-ready invoice view."""
    from database import get_invoice, get_invoice_items
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    invoice = get_invoice(inv_id, user["id"])
    if not invoice:
        flash("We could not find that invoice.", "error")
        return redirect(url_for("agent_invoices"))
    items = get_invoice_items(inv_id)
    return render_template(
        "agent/invoice_print.html",
        invoice=invoice,
        items=items,
        user=user,
    )


@route("/agent/seasonal-checklists")
def agent_seasonal_checklists():
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    previews = [_get_checklist_data(s, "agent") for s in SEASONS]
    return render_template("shared/seasonal_checklists.html",
                           brand_name=FRONT_BRAND_NAME, user=user,
                           role="agent", previews=previews,
                           back_url=url_for("agent_dashboard"), back_label="Back to Dashboard")


@route("/agent/seasonal-checklists/<season>")
def agent_checklist_print(season):
    if season not in SEASONS:
        return redirect(url_for("agent_seasonal_checklists"))
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    from database import get_user_profile
    profile = get_user_profile(user["id"]) or {}
    data = _get_checklist_data(season, "agent")
    is_kayleigh = user.get("email", "").lower() == "kayleighsellskcre@gmail.com"
    return render_template("shared/checklist_print.html",
                           checklist=data, user=user, profile=profile,
                           is_kayleigh=is_kayleigh,
                           back_url=url_for("agent_seasonal_checklists"))


@route("/agent/clients")
def agent_clients():
    """Agent client portal, list of all linked homeowner clients with live data."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    from database import get_agent_clients
    clients = get_agent_clients(user["id"])
    
    return render_template("agent/clients.html", clients=clients)


@route("/agent/clients/<int:homeowner_id>")
def agent_client_detail(homeowner_id):
    """Agent view of a specific homeowner client's full portal data."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    from database import (
        can_access_homeowner, get_user_by_id, get_homeowner_full_profile,
        get_homeowner_recent_activity, get_homeowner_professionals
    )
    
    if not can_access_homeowner(user["id"], "agent", homeowner_id):
        flash("That client is not connected to your account.", "error")
        return redirect(url_for("agent_clients"))
    
    homeowner = get_user_by_id(homeowner_id)
    if not homeowner or homeowner.get("role") != "homeowner":
        flash("We could not find that client.", "error")
        return redirect(url_for("agent_clients"))
    
    profile = get_homeowner_full_profile(homeowner_id)
    recent_activity = get_homeowner_recent_activity(homeowner_id, limit=15)
    professionals = get_homeowner_professionals(homeowner_id)
    
    # Load homeowner documents
    from database import get_connection as _gc
    _conn = _gc()
    docs = [dict(r) for r in _conn.execute(
        "SELECT id, name, category, created_at FROM homeowner_documents WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (homeowner_id,)
    ).fetchall()]
    projects = [dict(r) for r in _conn.execute(
        "SELECT id, name, category, status, budget FROM homeowner_projects WHERE user_id = ? ORDER BY created_at DESC LIMIT 10",
        (homeowner_id,)
    ).fetchall()]
    warranties = [dict(r) for r in _conn.execute(
        "SELECT id, item_name, category, warranty_expiry FROM homeowner_warranty_log WHERE user_id = ? ORDER BY warranty_expiry ASC LIMIT 10",
        (homeowner_id,)
    ).fetchall()]
    snapshot_history = [dict(r) for r in _conn.execute(
        "SELECT snapshot_date, value_estimate, equity_estimate, loan_balance FROM homeowner_snapshot_history WHERE user_id = ? ORDER BY snapshot_date DESC LIMIT 12",
        (homeowner_id,)
    ).fetchall()]
    _conn.close()
    
    # Find this agent's CRM contact for this homeowner
    from database import list_agent_contacts
    crm_contact = None
    for c in list_agent_contacts(user["id"]):
        if c.get("user_id") == homeowner_id or (c.get("email") and homeowner and c.get("email").lower() == dict(homeowner).get("email", "").lower()):
            crm_contact = c
            break
    
    return render_template(
        "agent/client_detail.html",
        homeowner=dict(homeowner),
        profile=profile,
        recent_activity=recent_activity,
        professionals=professionals,
        docs=docs,
        projects=projects,
        warranties=warranties,
        snapshot_history=snapshot_history,
        crm_contact=crm_contact,
    )


@route("/agent/referrals", methods=["GET", "POST"])
def agent_referrals():
    """Agent referral link management."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    try:
        from database import (
            get_referral_links_for_agent,
            create_referral_link,
            get_referral_stats,
            get_accessible_homeowners
        )
        
        # Handle POST - create new referral link
        if request.method == "POST":
            try:
                token = create_referral_link(agent_id=user["id"])
                flash("New referral link created!", "success")
                return redirect(url_for("agent_referrals"))
            except Exception as e:
                flash("We could not create that referral link. Please try again in a moment.", "error")
        
        # Get all referral links for this agent
        referral_links = get_referral_links_for_agent(user["id"])
        
        # If no links exist, create one automatically
        if not referral_links:
            try:
                token = create_referral_link(agent_id=user["id"])
                referral_links = get_referral_links_for_agent(user["id"])
            except Exception as e:
                print(f"Error auto-creating referral link: {e}")
        
        # Get stats
        try:
            stats = get_referral_stats(user["id"])
        except Exception as e:
            print(f"Error getting stats: {e}")
            stats = {'total_clients': 0, 'clients_this_month': 0}
        
        # Build referral URLs
        base_url = request.url_root.rstrip('/')
        referral_links_with_urls = []
        for link in referral_links:
            link_dict = dict(link) if hasattr(link, 'keys') else link
            link_dict['url'] = f"{base_url}/signup?role=homeowner&ref={link_dict['token']}"
            referral_links_with_urls.append(link_dict)
        
        # Use the first link as primary (for backward compatibility)
        primary_link = referral_links_with_urls[0] if referral_links_with_urls else None
        referral_url = primary_link['url'] if primary_link else None
        referral_code = primary_link['token'] if primary_link else None
        
        return render_template(
            "agent/referrals.html",
            brand_name=FRONT_BRAND_NAME,
            user=user,
            referral_code=referral_code,
            referral_url=referral_url,
            referral_links=referral_links_with_urls,
            stats=stats,
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"Error in agent_referrals: {error_trace}")
        flash("We could not load your referral page. Please try again in a moment.", "error")
        return redirect(url_for("agent_dashboard"))


@route("/agent/vendors", methods=["GET", "POST"])
def agent_vendors():
    """Agent trusted vendors management."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    from database import (
        create_trusted_vendor,
        get_trusted_vendors,
        update_trusted_vendor,
        delete_trusted_vendor
    )
    
    if request.method == "POST":
        action = request.form.get("action", "").strip()
        
        if action == "create":
            name = request.form.get("name", "").strip()
            category = request.form.get("category", "").strip()
            contact_name = request.form.get("contact_name", "").strip() or None
            phone = request.form.get("phone", "").strip() or None
            email = request.form.get("email", "").strip().lower() or None
            website = request.form.get("website", "").strip() or None
            address = request.form.get("address", "").strip() or None
            notes = request.form.get("notes", "").strip() or None
            
            if not name or not category:
                flash("Please add a name and a category.", "error")
            else:
                try:
                    vendor_id = create_trusted_vendor(
                        agent_id=user["id"],
                        name=name,
                        category=category,
                        contact_name=contact_name,
                        phone=phone,
                        email=email,
                        website=website,
                        address=address,
                        notes=notes
                    )
                    flash(f"Vendor '{name}' added!", "success")
                except Exception as e:
                    flash("We could not add that vendor. Please try again in a moment.", "error")
        
        elif action == "update":
            vendor_id = request.form.get("vendor_id")
            if vendor_id:
                try:
                    vendor_id = int(vendor_id)
                    name = request.form.get("name", "").strip()
                    category = request.form.get("category", "").strip()
                    contact_name = request.form.get("contact_name", "").strip() or None
                    phone = request.form.get("phone", "").strip() or None
                    email = request.form.get("email", "").strip().lower() or None
                    website = request.form.get("website", "").strip() or None
                    address = request.form.get("address", "").strip() or None
                    notes = request.form.get("notes", "").strip() or None
                    
                    if update_trusted_vendor(
                        vendor_id=vendor_id,
                        name=name,
                        category=category,
                        contact_name=contact_name,
                        phone=phone,
                        email=email,
                        website=website,
                        address=address,
                        notes=notes,
                        agent_id=user["id"],
                    ):
                        flash("Vendor updated!", "success")
                    else:
                        flash("We could not update that vendor. Please try again in a moment.", "error")
                except (ValueError, Exception) as e:
                    flash("We could not update that vendor. Please try again in a moment.", "error")
        
        elif action == "delete":
            vendor_id = request.form.get("vendor_id")
            if vendor_id:
                try:
                    vendor_id = int(vendor_id)
                    if delete_trusted_vendor(vendor_id, user["id"]):
                        flash("Vendor removed.", "success")
                    else:
                        flash("We could not remove that vendor. Please try again in a moment.", "error")
                except (ValueError, Exception) as e:
                    flash("We could not remove that vendor. Please try again in a moment.", "error")
        
        return redirect(url_for("agent_vendors"))
    
    # Get all vendors
    vendors_raw = get_trusted_vendors(user["id"])
    vendors = []
    for vendor in vendors_raw:
        if hasattr(vendor, 'keys'):
            vendors.append(dict(vendor))
        else:
            vendors.append(vendor)
    
    # Group by category
    vendors_by_category = {}
    categories = set()
    for vendor in vendors:
        cat = vendor.get("category", "Other")
        categories.add(cat)
        if cat not in vendors_by_category:
            vendors_by_category[cat] = []
        vendors_by_category[cat].append(vendor)
    
    return render_template(
        "agent/vendors.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        vendors=vendors,
        vendors_by_category=vendors_by_category,
        categories=sorted(categories),
    )


@route("/agent/booking")
def agent_booking():
    """Calendar and booking integration page."""
    if "user_id" not in session or session.get("role") != "agent":
        return redirect(url_for("login"))
    user = get_user_by_id(session["user_id"])
    if not user:
        return redirect(url_for("login"))
    from database import get_user_profile
    profile = get_user_profile(user["id"])
    profile_dict = dict(profile) if profile else {}
    return render_template("agent/booking.html", user=user, profile=profile_dict)


@route("/agent/admin/toggle-premium", methods=["GET", "POST"])
def admin_toggle_premium():
    """Admin page to toggle premium features for testing. Site admins only: it changes the signed-in account's plan."""
    user = _admin_session_user()
    if not user:
        flash("That area is just for site administrators.", "error")
        return redirect(url_for("login", role="agent"))
    
    if request.method == "POST":
        action = request.form.get("action")
        conn = get_connection()
        cur = conn.cursor()
        
        if action == "upgrade":
            cur.execute(
                "UPDATE users SET subscription_tier = ? WHERE id = ?",
                ("premium", user["id"])
            )
            conn.commit()
            conn.close()
            flash("Your premium features are ready. Enjoy!", "success")
        elif action == "downgrade":
            cur.execute(
                "UPDATE users SET subscription_tier = ? WHERE id = ?",
                ("free", user["id"])
            )
            conn.commit()
            conn.close()
            flash("You are all set on the free plan", "success")
        
        return redirect(url_for("admin_toggle_premium"))
    
    # Refresh user data
    conn = get_connection()
    user_data = conn.execute("SELECT * FROM users WHERE id = ?", (user["id"],)).fetchone()
    conn.close()
    
    return render_template(
        "agent/admin_toggle.html",
        brand_name=FRONT_BRAND_NAME,
        user=dict(user_data) if user_data else user
    )


@route("/agent/admin/settings")
def admin_settings():
    """Admin settings page for premium feature testing. Site admins only."""
    user = _admin_session_user()
    if not user:
        flash("That area is just for site administrators.", "error")
        return redirect(url_for("login", role="agent"))
    
    return render_template(
        "agent/admin_settings.html",
        brand_name=FRONT_BRAND_NAME,
        user=user
    )


@route("/agent/subscription")
def agent_subscription():
    """Agent subscription management page."""
    if "user_id" not in session or session.get("role") != "agent":
        return redirect(url_for("login"))
    user = get_user_by_id(session["user_id"])
    if not user:
        return redirect(url_for("login"))
    user_dict = dict(user) if hasattr(user, "keys") and not isinstance(user, dict) else user
    from database import get_user_profile
    profile = get_user_profile(session["user_id"])
    current_tier = user_dict.get("subscription_tier", "free") or "free"
    stripe_configured = bool(os.environ.get("STRIPE_SECRET_KEY"))
    return render_template(
        "agent/subscription.html",
        user=user_dict,
        profile=profile,
        current_tier=current_tier,
        tiers=SUBSCRIPTION_TIERS,
        stripe_configured=stripe_configured,
    )


@route("/agent/subscription/checkout/<tier>", methods=["POST"])
def agent_subscription_checkout(tier):
    """Start Stripe checkout for agent subscription."""
    if "user_id" not in session or session.get("role") != "agent":
        return redirect(url_for("login"))
    if tier not in ("professional", "elite"):
        flash("We could not find that plan. Please choose one from the list.", "error")
        return redirect(url_for("agent_subscription"))

    user = get_user_by_id(session["user_id"])
    if not user:
        return redirect(url_for("login"))
    user_dict = dict(user) if hasattr(user, "keys") and not isinstance(user, dict) else user

    base_url = request.host_url.rstrip("/")
    checkout_url, error = create_checkout_session(
        user_id=user_dict["id"],
        user_email=user_dict["email"],
        user_name=user_dict.get("name", ""),
        tier=tier,
        role="agent",
        success_url=f"{base_url}/agent/subscription/success",
        cancel_url=f"{base_url}/agent/subscription",
    )

    if error:
        flash("We could not start checkout. Please try again in a moment.", "error")
        return redirect(url_for("agent_subscription"))

    return redirect(checkout_url)


@route("/agent/subscription/success")
def agent_subscription_success():
    """Subscription success landing page for agents."""
    if "user_id" not in session or session.get("role") != "agent":
        return redirect(url_for("login"))
    user = get_user_by_id(session["user_id"])
    user_dict = dict(user) if hasattr(user, "keys") and not isinstance(user, dict) else user
    return render_template("shared/subscription_success.html", user=user_dict, role="agent",
                           dashboard_url=url_for("agent_dashboard"))


@route("/agent/subscription/portal", methods=["POST"])
def agent_subscription_portal():
    """Redirect agent to Stripe customer portal to manage billing."""
    if "user_id" not in session or session.get("role") != "agent":
        return redirect(url_for("login"))
    user = get_user_by_id(session["user_id"])
    user_dict = dict(user) if hasattr(user, "keys") and not isinstance(user, dict) else user

    stripe_customer_id = user_dict.get("stripe_customer_id")
    if not stripe_customer_id:
        flash("No active subscription found. Please subscribe first.", "error")
        return redirect(url_for("agent_subscription"))

    base_url = request.host_url.rstrip("/")
    portal_url, error = create_customer_portal_session(
        stripe_customer_id,
        return_url=f"{base_url}/agent/subscription"
    )

    if error:
        flash("We could not open billing portal. Please try again in a moment.", "error")
        return redirect(url_for("agent_subscription"))

    return redirect(portal_url)


@route("/agent/settings/profile", methods=["GET", "POST"])
def agent_settings_profile():
    """Agent settings and profile."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))

    from database import get_user_profile, create_or_update_user_profile

    # Handle POST - update profile
    if request.method == "POST":
        try:
            print(f"\n{'='*60}")
            print(f"AGENT PROFILE SAVE: Starting profile update for user {user['id']}")
            print(f"FORM FILES: {list(request.files.keys())}")
            print(f"FORM DATA KEYS: {list(request.form.keys())}")
            
            # Check if files are in request
            if 'professional_photo' in request.files:
                photo_file = request.files['professional_photo']
                print(f"PHOTO FILE: filename={photo_file.filename}, size={len(photo_file.read()) if photo_file.filename else 0}")
                photo_file.seek(0)  # Reset file pointer after reading
            else:
                print(f"PHOTO FILE: NOT IN REQUEST")
                
            if 'brokerage_logo' in request.files:
                logo_file = request.files['brokerage_logo']
                print(f"LOGO FILE: filename={logo_file.filename}, size={len(logo_file.read()) if logo_file.filename else 0}")
                logo_file.seek(0)  # Reset file pointer after reading
            else:
                print(f"LOGO FILE: NOT IN REQUEST")
            
            print(f"{'='*60}\n")
            
            # Handle file uploads using consolidated helper
            professional_photo = handle_profile_file_upload("professional_photo", folder="profiles", role_prefix="AGENT ")
            brokerage_logo = handle_profile_file_upload("brokerage_logo", folder="profiles", role_prefix="AGENT ")
            
            # Preserve existing photos/logos if not uploading new ones
            professional_photo, brokerage_logo = preserve_existing_profile_media(
                user["id"], professional_photo, brokerage_logo
            )
            
            print(f"AGENT PROFILE: About to save - photo={professional_photo[:50] if professional_photo else None}, logo={brokerage_logo[:50] if brokerage_logo else None}")
            
            profile_id = create_or_update_user_profile(
                user_id=user["id"],
                role="agent",
                professional_photo=professional_photo,
                brokerage_logo=brokerage_logo,
                team_name=request.form.get("team_name", "").strip() or None,
                brokerage_name=request.form.get("brokerage_name", "").strip() or None,
                website_url=request.form.get("website_url", "").strip() or None,
                facebook_url=request.form.get("facebook_url", "").strip() or None,
                instagram_url=request.form.get("instagram_url", "").strip() or None,
                linkedin_url=request.form.get("linkedin_url", "").strip() or None,
                twitter_url=request.form.get("twitter_url", "").strip() or None,
                youtube_url=request.form.get("youtube_url", "").strip() or None,
                phone=request.form.get("phone", "").strip() or None,
                call_button_enabled=1 if request.form.get("call_button_enabled") == "on" else 0,
                schedule_button_enabled=1 if request.form.get("schedule_button_enabled") == "on" else 0,
                schedule_url=request.form.get("schedule_url", "").strip() or None,
                bio=request.form.get("bio", "").strip() or None,
                specialties=request.form.get("specialties", "").strip() or None,
                years_experience=int(request.form.get("years_experience")) if request.form.get("years_experience") else None,
                languages=request.form.get("languages", "").strip() or None,
                service_areas=request.form.get("service_areas", "").strip() or None,
                license_number=request.form.get("license_number", "").strip() or None,
                company_address=request.form.get("company_address", "").strip() or None,
                company_city=request.form.get("company_city", "").strip() or None,
                company_state=request.form.get("company_state", "").strip() or None,
                company_zip=request.form.get("company_zip", "").strip() or None,
                homebot_widget_id=request.form.get("homebot_widget_id", "").strip() or None,
                va_rate_30yr=float(request.form.get("va_rate_30yr")) if request.form.get("va_rate_30yr") else None,
                fha_rate_30yr=float(request.form.get("fha_rate_30yr")) if request.form.get("fha_rate_30yr") else None,
                conventional_rate_30yr=float(request.form.get("conventional_rate_30yr")) if request.form.get("conventional_rate_30yr") else None,
                google_review_link=request.form.get("google_review_link", "").strip() or None,
            )

            # Auto-generate webhook token if agent doesn't have one yet
            from database import get_connection as _gwc, get_user_profile as _gwp
            _existing_profile = _gwp(user["id"])
            if _existing_profile and not _existing_profile.get("webhook_token"):
                import secrets
                _token = secrets.token_urlsafe(16)
                _conn = _gwc()
                _cur = _conn.cursor()
                _cur.execute("UPDATE user_profiles SET webhook_token = ? WHERE user_id = ?",
                             (_token, user["id"]))
                _conn.commit()
                _conn.close()

            # Success message with specific photo/logo confirmation
            success_parts = ["Profile updated successfully!"]
            if professional_photo:
                success_parts.append("[OK] Professional photo saved")
            if brokerage_logo:
                success_parts.append("[OK] Brokerage logo saved")
            
            print(f"AGENT PROFILE: Profile saved successfully with ID {profile_id}")
            print(f"{'='*60}\n")
            flash(" | ".join(success_parts), "success")
            return redirect(url_for("agent_settings_profile"))
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"\n{'='*60}")
            print(f"AGENT PROFILE ERROR: {str(e)}")
            print(f"{'='*60}")
            print(error_trace)
            print(f"{'='*60}\n")
            flash("We could not update your profile. Please try again in a moment.", "error")
            # Continue to render the form so user can see the error and try again
    
    # GET - load profile
    profile = get_user_profile(user["id"])
    profile_dict = dict(profile) if profile and hasattr(profile, 'keys') else (profile if profile else {})

    # Referral link
    from database import get_referral_links_for_agent, create_referral_link as _create_ref
    try:
        ref_links = get_referral_links_for_agent(user["id"])
        if not ref_links:
            _create_ref(agent_id=user["id"])
            ref_links = get_referral_links_for_agent(user["id"])
        referral_url = url_for("referral_landing", referral_code=ref_links[0]["token"], _external=True) if ref_links else None
    except Exception:
        referral_url = None

    return render_template(
        "agent/settings_profile.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        profile=profile_dict,
        referral_url=referral_url,
    )


@route("/agent/concierge")
def agent_concierge_dashboard():
    """Agent's AI concierge control panel"""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    from ai_concierge import get_concierge_stats, get_recent_leads
    
    stats = get_concierge_stats(user['id'])
    recent_leads = get_recent_leads(user['id'], limit=10)
    
    # Get agent's concierge URL
    concierge_url = request.host_url.rstrip('/') + url_for('concierge_landing', agent_token=user['id'])
    
    return render_template(
        'agent/concierge_dashboard.html',
        brand_name=FRONT_BRAND_NAME,
        user=user,
        stats=stats,
        recent_leads=recent_leads,
        concierge_url=concierge_url
    )


@route("/agent/concierge/settings", methods=["GET", "POST"])
def agent_concierge_settings():
    """Configure AI concierge branding and settings"""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    conn = get_connection()
    cur = conn.cursor()
    
    if request.method == "POST":
        # Save settings
        branding_name = request.form.get('branding_name', 'Your Home Concierge')
        branding_tagline = request.form.get('branding_tagline', '')
        primary_color = request.form.get('primary_color', '#1a1a1a')
        secondary_color = request.form.get('secondary_color', '#f5f5f5')
        welcome_message = request.form.get('welcome_message', '')
        openai_api_key = request.form.get('openai_api_key', '')
        is_active = 1 if request.form.get('is_active') == 'on' else 0
        
        # Upsert settings
        cur.execute(
            """INSERT INTO concierge_settings 
            (agent_id, branding_name, branding_tagline, primary_color, 
             secondary_color, welcome_message, openai_api_key, is_active, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(agent_id) DO UPDATE SET
                branding_name = excluded.branding_name,
                branding_tagline = excluded.branding_tagline,
                primary_color = excluded.primary_color,
                secondary_color = excluded.secondary_color,
                welcome_message = excluded.welcome_message,
                openai_api_key = excluded.openai_api_key,
                is_active = excluded.is_active,
                updated_at = excluded.updated_at
            """,
            (user['id'], branding_name, branding_tagline, primary_color,
             secondary_color, welcome_message, openai_api_key, is_active,
             datetime.now().isoformat())
        )
        conn.commit()
        flash("Concierge settings saved!", "success")
        return redirect(url_for('agent_concierge_settings'))
    
    # GET - load current settings
    cur.execute("SELECT * FROM concierge_settings WHERE agent_id = ?", (user['id'],))
    settings = row_to_dict(cur.fetchone())
    conn.close()
    
    return render_template(
        'agent/concierge_settings.html',
        brand_name=FRONT_BRAND_NAME,
        user=user,
        settings=settings or {}
    )


@route("/agent/concierge/vendors", methods=["GET", "POST"])
def agent_concierge_vendors():
    """Manage subscription-based vendors for AI concierge"""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    conn = get_connection()
    cur = conn.cursor()
    
    if request.method == "POST":
        # Add new vendor
        name = request.form.get('name', '').strip()
        category = request.form.get('category', '').strip()
        contact_name = request.form.get('contact_name', '').strip()
        phone = request.form.get('phone', '').strip()
        email = request.form.get('email', '').strip()
        website = request.form.get('website', '').strip()
        address = request.form.get('address', '').strip()
        service_area_zips = request.form.get('service_area_zips', '').strip()
        monthly_fee = float(request.form.get('monthly_fee', 400))
        is_exclusive = 1 if request.form.get('is_exclusive') == 'on' else 0
        notes = request.form.get('notes', '').strip()
        
        if name and category and contact_name and phone and email:
            cur.execute(
                """INSERT INTO concierge_vendors
                (agent_id, name, category, contact_name, phone, email, website,
                 address, service_area_zips, monthly_fee, is_exclusive, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (user['id'], name, category, contact_name, phone, email, website,
                 address, service_area_zips, monthly_fee, is_exclusive, notes)
            )
            conn.commit()
            flash(f"Vendor {name} added!", "success")
        else:
            flash("Please fill in the required fields so we can save this.", "error")
        
        return redirect(url_for('agent_concierge_vendors'))
    
    # GET - load vendors
    from ai_concierge import get_vendor_performance
    vendors = get_vendor_performance(user['id'])
    conn.close()
    
    # Available categories
    categories = [
        'HVAC', 'Plumbing', 'Electrical', 'Roofing', 'Landscaping',
        'Painting', 'Flooring', 'Remodeling', 'Cleaning', 'Pest Control',
        'Windows & Doors', 'Appliance Repair', 'Pool & Spa', 'Other'
    ]
    
    return render_template(
        'agent/concierge_vendors.html',
        brand_name=FRONT_BRAND_NAME,
        user=user,
        vendors=vendors,
        categories=categories
    )


@route("/agent/concierge/vendors/<int:vendor_id>/update", methods=["POST"])
def agent_concierge_vendor_update(vendor_id):
    """Update vendor subscription status"""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Verify vendor belongs to this agent
    cur.execute("SELECT id FROM concierge_vendors WHERE id = ? AND agent_id = ?", 
                (vendor_id, user['id']))
    if not cur.fetchone():
        conn.close()
        abort(404)
    
    # Update status
    new_status = request.form.get('status')
    if new_status in ['active', 'paused', 'cancelled']:
        cur.execute(
            "UPDATE concierge_vendors SET subscription_status = ? WHERE id = ?",
            (new_status, vendor_id)
        )
        conn.commit()
        flash("Vendor status updated", "success")
    
    conn.close()
    return redirect(url_for('agent_concierge_vendors'))


@route("/agent/concierge/leads")
def agent_concierge_leads():
    """View all leads from AI concierge"""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    from ai_concierge import get_recent_leads
    
    # Get filter
    urgency_filter = request.args.get('urgency')
    status_filter = request.args.get('status')
    
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
    """
    params = [user['id']]
    
    if urgency_filter:
        query += " AND l.urgency = ?"
        params.append(urgency_filter)
    
    if status_filter:
        query += " AND l.status = ?"
        params.append(status_filter)
    
    query += " ORDER BY l.routed_at DESC LIMIT 100"
    
    cur.execute(query, params)
    leads = rows_to_dicts(cur.fetchall())
    conn.close()
    
    return render_template(
        'agent/concierge_leads.html',
        brand_name=FRONT_BRAND_NAME,
        user=user,
        leads=leads,
        urgency_filter=urgency_filter,
        status_filter=status_filter
    )


@route("/agent/concierge/conversations")
def agent_concierge_conversations():
    """View all AI concierge conversations"""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    conn = get_connection()
    cur = conn.cursor()
    
    cur.execute(
        """SELECT c.*, h.name as homeowner_name, h.email as homeowner_email
        FROM concierge_conversations c
        LEFT JOIN concierge_homeowners h ON c.homeowner_id = h.id
        WHERE c.agent_id = ?
        ORDER BY c.last_message_at DESC
        LIMIT 50""",
        (user['id'],)
    )
    conversations = rows_to_dicts(cur.fetchall())
    conn.close()
    
    return render_template(
        'agent/concierge_conversations.html',
        brand_name=FRONT_BRAND_NAME,
        user=user,
        conversations=conversations
    )


@route("/agent/concierge/conversations/<int:conversation_id>")
def agent_concierge_conversation_detail(conversation_id):
    """View conversation transcript"""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    
    from ai_concierge import ConciergeAI
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get conversation
    cur.execute(
        """SELECT c.*, h.name as homeowner_name, h.email as homeowner_email
        FROM concierge_conversations c
        LEFT JOIN concierge_homeowners h ON c.homeowner_id = h.id
        WHERE c.id = ? AND c.agent_id = ?""",
        (conversation_id, user['id'])
    )
    conversation = row_to_dict(cur.fetchone())
    
    if not conversation:
        conn.close()
        abort(404)
    
    # Get messages
    ai = ConciergeAI(user['id'])
    messages = ai.get_conversation_history(conversation_id, limit=100)
    conn.close()
    
    return render_template(
        'agent/concierge_conversation_detail.html',
        brand_name=FRONT_BRAND_NAME,
        user=user,
        conversation=conversation,
        messages=messages
    )


@route("/agent/contests", methods=["GET"])
def agent_contests():
    """List all bracket contests for this agent."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    contests = _list_db_contests(user["id"])
    return render_template("agent/contests.html", contests=contests)


@route("/agent/contests/new", methods=["GET", "POST"])
def agent_contest_new():
    """Create a new bracket contest."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    if request.method == "POST":
        import datetime
        conn = get_db_connection()
        conn.execute(
            """INSERT INTO agent_contests
               (agent_user_id, contest_type, season_year, contest_name,
                cbs_group_link, cbs_group_code, prize_description,
                invite_date, deadline_date, notes)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                user["id"],
                request.form.get("contest_type", "ncaa_tournament"),
                int(request.form.get("season_year", datetime.date.today().year)),
                request.form.get("contest_name", "").strip(),
                request.form.get("cbs_group_link", "").strip(),
                request.form.get("cbs_group_code", "").strip(),
                request.form.get("prize_description", "$25 Amazon Gift Card").strip(),
                request.form.get("invite_date", "").strip(),
                request.form.get("deadline_date", "").strip(),
                request.form.get("notes", "").strip(),
            )
        )
        conn.commit()
        conn.close()
        flash("Contest created! Invites will go out automatically on your invite date.", "success")
        return redirect(url_for("agent_contests"))
    import datetime
    return render_template("agent/contest_new.html", today_year=datetime.date.today().year)


@route("/agent/contests/<int:cid>/edit", methods=["GET", "POST"])
def agent_contest_edit(cid):
    """Edit a contest."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    contest = _get_db_contest(cid, user["id"])
    if not contest:
        flash("We could not find that contest.", "error")
        return redirect(url_for("agent_contests"))
    if request.method == "POST":
        conn = get_db_connection()
        conn.execute(
            """UPDATE agent_contests SET
               contest_type=?, season_year=?, contest_name=?,
               cbs_group_link=?, cbs_group_code=?, prize_description=?,
               invite_date=?, deadline_date=?, notes=?
               WHERE id=? AND agent_user_id=?""",
            (
                request.form.get("contest_type"),
                int(request.form.get("season_year", contest["season_year"])),
                request.form.get("contest_name", "").strip(),
                request.form.get("cbs_group_link", "").strip(),
                request.form.get("cbs_group_code", "").strip(),
                request.form.get("prize_description", "$25 Amazon Gift Card").strip(),
                request.form.get("invite_date", "").strip(),
                request.form.get("deadline_date", "").strip(),
                request.form.get("notes", "").strip(),
                cid, user["id"]
            )
        )
        conn.commit()
        conn.close()
        flash("Contest updated.", "success")
        return redirect(url_for("agent_contests"))
    return render_template("agent/contest_new.html", contest=contest, today_year=contest["season_year"])


@route("/agent/contests/<int:cid>/delete", methods=["POST"])
def agent_contest_delete(cid):
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    conn = get_db_connection()
    conn.execute("DELETE FROM agent_contests WHERE id=? AND agent_user_id=?", (cid, user["id"]))
    conn.commit()
    conn.close()
    flash("Contest deleted.", "success")
    return redirect(url_for("agent_contests"))


@route("/agent/contests/<int:cid>/send-invites", methods=["POST"])
def agent_contest_send_invites(cid):
    """Manually send invite emails to all CRM contacts right now."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    contest = _get_db_contest(cid, user["id"])
    if not contest:
        flash("We could not find that contest.", "error")
        return redirect(url_for("agent_contests"))
    count = _send_contest_invites_for(contest, user)
    flash(f" Invites sent to {count} clients!", "success")
    return redirect(url_for("agent_contests"))


@route("/agent/contests/<int:cid>/reset-invites", methods=["POST"])
def agent_contest_reset_invites(cid):
    """Clear invite_sent_at so invites can be resent."""
    user = get_current_user()
    if not user or user.get("role") != "agent":
        return redirect(url_for("login", role="agent"))
    conn = get_db_connection()
    conn.execute(
        "UPDATE agent_contests SET invite_sent_at=NULL WHERE id=? AND agent_user_id=?",
        (cid, user["id"])
    )
    conn.commit()
    conn.close()
    flash("Invite status reset. You can now resend invites.", "success")
    return redirect(url_for("agent_contests"))


@route("/agent/financials", methods=["GET"])
def agent_financials():
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return redirect(url_for("login", role="agent"))
    uid = user["id"]

    # Year filter
    year = request.args.get("year", str(datetime.now().year))
    try:
        year = int(year)
    except Exception:
        year = datetime.now().year

    try:
        conn = get_db_connection()

        # Commissions
        commissions = [dict(r) for r in conn.execute(
            "SELECT * FROM agent_commissions WHERE agent_user_id=? AND (close_date LIKE ? OR close_date='') ORDER BY close_date DESC",
            (uid, f"{year}%")
        ).fetchall()]

        # Expenses
        expenses = [dict(r) for r in conn.execute(
            "SELECT * FROM agent_expenses WHERE agent_user_id=? AND expense_date LIKE ? ORDER BY expense_date DESC",
            (uid, f"{year}%")
        ).fetchall()]

        # Mileage
        mileage_logs = [dict(r) for r in conn.execute(
            "SELECT * FROM agent_mileage WHERE agent_user_id=? AND trip_date LIKE ? ORDER BY trip_date DESC",
            (uid, f"{year}%")
        ).fetchall()]

        # Goals
        goals = [dict(r) for r in conn.execute(
            "SELECT * FROM agent_financial_goals WHERE agent_user_id=? AND goal_year=?",
            (uid, year)
        ).fetchall()]

        conn.close()
    except Exception as db_err:
        app.logger.error(f"agent_financials DB error: {db_err}")
        commissions, expenses, mileage_logs, goals = [], [], [], []

    # Computed summaries
    ytd_gci = sum(c.get("net_commission", 0) or 0 for c in commissions if c.get("status") == "paid")
    ytd_projected = sum(c.get("net_commission", 0) or 0 for c in commissions if c.get("status") == "projected")
    ytd_expenses = sum(e.get("amount", 0) or 0 for e in expenses)
    ytd_miles = sum(m.get("miles", 0) or 0 for m in mileage_logs)
    irs_rate = 0.70
    mileage_deduction = round(ytd_miles * irs_rate, 2)
    net_income = ytd_gci - ytd_expenses

    # Monthly GCI for chart
    monthly_gci = {}
    for c in commissions:
        if c.get("status") == "paid" and c.get("close_date"):
            try:
                mo = int(c["close_date"].split("-")[1])
                monthly_gci[mo] = monthly_gci.get(mo, 0) + (c.get("net_commission", 0) or 0)
            except Exception:
                pass
    monthly_gci_list = [monthly_gci.get(m, 0) for m in range(1, 13)]

    # Expense categories breakdown
    expense_by_cat = {}
    for e in expenses:
        cat = e.get("category", "Other") or "Other"
        expense_by_cat[cat] = expense_by_cat.get(cat, 0) + (e.get("amount", 0) or 0)

    available_years = list(range(datetime.now().year, 2023, -1))

    return render_template("agent/financials.html",
        user=user,
        year=year,
        available_years=available_years,
        commissions=commissions,
        expenses=expenses,
        mileage_logs=mileage_logs,
        goals=goals,
        ytd_gci=ytd_gci,
        ytd_projected=ytd_projected,
        ytd_expenses=ytd_expenses,
        ytd_miles=ytd_miles,
        mileage_deduction=mileage_deduction,
        net_income=net_income,
        monthly_gci_list=monthly_gci_list,
        expense_by_cat=expense_by_cat,
        irs_rate=irs_rate,
    )


@route("/agent/financials/commission/add", methods=["POST"])
def agent_financials_commission_add():
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return redirect(url_for("login", role="agent"))
    uid = user["id"]
    f = request.form
    sale_price = float(f.get("sale_price") or 0)
    comm_rate = float(f.get("commission_rate") or 3.0)
    split_pct = float(f.get("brokerage_split_pct") or 0)
    gross = round(sale_price * comm_rate / 100, 2)
    split_amt = round(gross * split_pct / 100, 2)
    net = round(gross - split_amt, 2)
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO agent_commissions
        (agent_user_id, property_address, client_name, close_date, transaction_side,
         sale_price, commission_rate, gross_commission, brokerage_split_pct,
         brokerage_split_amt, net_commission, status, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
    """, (uid,
          f.get("property_address",""),
          f.get("client_name",""),
          f.get("close_date",""),
          f.get("transaction_side","buyer"),
          sale_price, comm_rate, gross, split_pct, split_amt, net,
          f.get("status","projected"),
          f.get("notes","")))
    conn.commit()
    conn.close()
    flash("Commission added!", "success")
    year = (f.get("close_date") or "")[:4] or str(datetime.now().year)
    return redirect(url_for("agent_financials", year=year))


@route("/agent/financials/commission/<int:cid>/delete", methods=["POST"])
def agent_financials_commission_delete(cid):
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return redirect(url_for("login", role="agent"))
    conn = get_db_connection()
    conn.execute("DELETE FROM agent_commissions WHERE id=? AND agent_user_id=?", (cid, user["id"]))
    conn.commit()
    conn.close()
    flash("Commission removed.", "success")
    return redirect(url_for("agent_financials"))


@route("/agent/financials/commission/<int:cid>/mark-paid", methods=["POST"])
def agent_financials_commission_mark_paid(cid):
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return redirect(url_for("login", role="agent"))
    conn = get_db_connection()
    conn.execute("UPDATE agent_commissions SET status='paid' WHERE id=? AND agent_user_id=?", (cid, user["id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("agent_financials"))


@route("/agent/financials/expense/add", methods=["POST"])
def agent_financials_expense_add():
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return redirect(url_for("login", role="agent"))
    uid = user["id"]
    f = request.form
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO agent_expenses
        (agent_user_id, expense_date, category, description, amount, receipt_url, notes)
        VALUES (?,?,?,?,?,?,?)
    """, (uid, f.get("expense_date",""), f.get("category","Other"),
          f.get("description",""), float(f.get("amount") or 0),
          f.get("receipt_url",""), f.get("notes","")))
    conn.commit()
    conn.close()
    flash("Expense logged!", "success")
    year = (f.get("expense_date") or "")[:4] or str(datetime.now().year)
    return redirect(url_for("agent_financials", year=year))


@route("/agent/financials/expense/<int:eid>/delete", methods=["POST"])
def agent_financials_expense_delete(eid):
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return redirect(url_for("login", role="agent"))
    conn = get_db_connection()
    conn.execute("DELETE FROM agent_expenses WHERE id=? AND agent_user_id=?", (eid, user["id"]))
    conn.commit()
    conn.close()
    flash("Expense removed.", "success")
    return redirect(url_for("agent_financials"))


@route("/agent/financials/mileage/add", methods=["POST"])
def agent_financials_mileage_add():
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return redirect(url_for("login", role="agent"))
    uid = user["id"]
    f = request.form
    miles = float(f.get("miles") or 0)
    irs_rate = 0.70
    deduction = round(miles * irs_rate, 2)
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO agent_mileage
        (agent_user_id, trip_date, from_location, to_location, purpose, miles, irs_rate, deduction_amount)
        VALUES (?,?,?,?,?,?,?,?)
    """, (uid, f.get("trip_date",""), f.get("from_location",""),
          f.get("to_location",""), f.get("purpose",""),
          miles, irs_rate, deduction))
    conn.commit()
    conn.close()
    flash("Mileage logged!", "success")
    year = (f.get("trip_date") or "")[:4] or str(datetime.now().year)
    return redirect(url_for("agent_financials", year=year))


@route("/agent/financials/mileage/<int:mid>/delete", methods=["POST"])
def agent_financials_mileage_delete(mid):
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return redirect(url_for("login", role="agent"))
    conn = get_db_connection()
    conn.execute("DELETE FROM agent_mileage WHERE id=? AND agent_user_id=?", (mid, user["id"]))
    conn.commit()
    conn.close()
    flash("Mileage entry removed.", "success")
    return redirect(url_for("agent_financials"))


@route("/agent/financials/goal/save", methods=["POST"])
def agent_financials_goal_save():
    user = get_current_user()
    if not user or user.get("role") not in ("agent", "admin"):
        return redirect(url_for("login", role="agent"))
    uid = user["id"]
    f = request.form
    year = int(f.get("goal_year", datetime.now().year))
    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id FROM agent_financial_goals WHERE agent_user_id=? AND goal_year=?", (uid, year)
    ).fetchone()
    if existing:
        conn.execute("""
            UPDATE agent_financial_goals SET
            gross_commission_goal=?, transactions_goal=?, expenses_budget=?, net_income_goal=?, notes=?
            WHERE agent_user_id=? AND goal_year=?
        """, (float(f.get("gci_goal") or 0), int(f.get("transactions_goal") or 0),
              float(f.get("expenses_budget") or 0), float(f.get("net_income_goal") or 0),
              f.get("notes",""), uid, year))
    else:
        conn.execute("""
            INSERT INTO agent_financial_goals
            (agent_user_id, goal_year, gross_commission_goal, transactions_goal, expenses_budget, net_income_goal, notes)
            VALUES (?,?,?,?,?,?,?)
        """, (uid, year, float(f.get("gci_goal") or 0), int(f.get("transactions_goal") or 0),
              float(f.get("expenses_budget") or 0), float(f.get("net_income_goal") or 0),
              f.get("notes","")))
    conn.commit()
    conn.close()
    flash("Goals saved!", "success")
    return redirect(url_for("agent_financials", year=year))
