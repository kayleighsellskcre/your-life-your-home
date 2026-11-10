"""Lender pages (dashboard, CRM, loans, marketing, referrals, financials, settings, billing).

These views used to sit in app.py. They are loaded by install(), which runs them in app.py's own namespace, so every
helper they use (get_current_user, render_template, send_reminder_email, ...) is looked up there, exactly as before.
That is also why this file is not meant to be run or linted on its own. Route names (endpoints) are unchanged, so every
url_for('lender_...') in the templates keeps working.
"""
from route_loader import Registry

_registry = Registry()
route = _registry.route
install = _registry.install


@route("/lender", methods=["GET"])
def lender_dashboard():
    """Lender dashboard view."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "lender":
            return redirect(url_for("login", role="lender"))

        try:
            metrics = get_lender_dashboard_metrics(user["id"])
        except Exception as e:
            import traceback
            print(f"Error getting lender metrics: {traceback.format_exc()}")
            metrics = {
                "new_applications": 0,
                "loans_in_process": 0,
                "nurture_contacts": 0,
            }
        
        # Convert Row objects to dicts if needed
        try:
            loans_raw = list_lender_loans(user["id"])
            loans = []
            for loan in loans_raw:
                if hasattr(loan, 'keys'):
                    loans.append(dict(loan))
                else:
                    loans.append(loan)
        except Exception as e:
            import traceback
            print(f"Error getting lender loans: {traceback.format_exc()}")
            loans = []
        
        try:
            borrowers_raw = list_lender_borrowers(user["id"])
            borrowers = []
            for borrower in borrowers_raw:
                if hasattr(borrower, 'keys'):
                    borrowers.append(dict(borrower))
                else:
                    borrowers.append(borrower)
        except Exception as e:
            import traceback
            print(f"Error getting lender borrowers: {traceback.format_exc()}")
            borrowers = []

        import automation
        return render_template(
            "lender/dashboard.html",
            brand_name=FRONT_BRAND_NAME,
            user=user,
            metrics=metrics,
            loans=loans,
            borrowers=borrowers,
            shared_deals=automation.lender_shared_deals(user["id"]),
            today_digest=automation.build_digest(user["id"], "lender"),
        )
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"ERROR in lender_dashboard: {error_trace}")
        flash("We could not load your dashboard. Please try again in a moment.", "error")
        return redirect(url_for("login", role="lender"))


@route("/lender/seasonal-checklists")
def lender_seasonal_checklists():
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    previews = [_get_checklist_data(s, "lender") for s in SEASONS]
    return render_template("shared/seasonal_checklists.html",
                           brand_name=FRONT_BRAND_NAME, user=user,
                           role="lender", previews=previews,
                           back_url=url_for("lender_power_suite"))


@route("/lender/seasonal-checklists/<season>")
def lender_checklist_print(season):
    if season not in SEASONS:
        return redirect(url_for("lender_seasonal_checklists"))
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    from database import get_user_profile
    profile = get_user_profile(user["id"]) or {}
    data = _get_checklist_data(season, "lender")
    is_kayleigh = user.get("email", "").lower() == "kayleighsellskcre@gmail.com"
    return render_template("shared/checklist_print.html",
                           checklist=data, user=user, profile=profile,
                           is_kayleigh=is_kayleigh,
                           back_url=url_for("lender_seasonal_checklists"))


@route("/lender/subscription")
def lender_subscription():
    """Lender subscription management page."""
    if "user_id" not in session or session.get("role") != "lender":
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
        "lender/subscription.html",
        user=user_dict,
        profile=profile,
        current_tier=current_tier,
        tiers=SUBSCRIPTION_TIERS,
        stripe_configured=stripe_configured,
    )


@route("/lender/subscription/checkout/<tier>", methods=["POST"])
def lender_subscription_checkout(tier):
    """Start Stripe checkout for lender subscription."""
    if "user_id" not in session or session.get("role") != "lender":
        return redirect(url_for("login"))
    if tier not in ("professional", "elite"):
        flash("We could not find that plan. Please choose one from the list.", "error")
        return redirect(url_for("lender_subscription"))

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
        role="lender",
        success_url=f"{base_url}/lender/subscription/success",
        cancel_url=f"{base_url}/lender/subscription",
    )

    if error:
        flash("We could not start checkout. Please try again in a moment.", "error")
        return redirect(url_for("lender_subscription"))

    return redirect(checkout_url)


@route("/lender/subscription/success")
def lender_subscription_success():
    """Subscription success landing page for lenders."""
    if "user_id" not in session or session.get("role") != "lender":
        return redirect(url_for("login"))
    user = get_user_by_id(session["user_id"])
    user_dict = dict(user) if hasattr(user, "keys") and not isinstance(user, dict) else user
    return render_template("shared/subscription_success.html", user=user_dict, role="lender",
                           dashboard_url=url_for("lender_dashboard"))


@route("/lender/subscription/portal", methods=["POST"])
def lender_subscription_portal():
    """Redirect lender to Stripe customer portal to manage billing."""
    if "user_id" not in session or session.get("role") != "lender":
        return redirect(url_for("login"))
    user = get_user_by_id(session["user_id"])
    user_dict = dict(user) if hasattr(user, "keys") and not isinstance(user, dict) else user

    stripe_customer_id = user_dict.get("stripe_customer_id")
    if not stripe_customer_id:
        flash("No active subscription found. Please subscribe first.", "error")
        return redirect(url_for("lender_subscription"))

    base_url = request.host_url.rstrip("/")
    portal_url, error = create_customer_portal_session(
        stripe_customer_id,
        return_url=f"{base_url}/lender/subscription"
    )

    if error:
        flash("We could not open billing portal. Please try again in a moment.", "error")
        return redirect(url_for("lender_subscription"))

    return redirect(portal_url)


@route("/lender/crm", methods=["GET", "POST"])
def lender_crm():
    """Lender CRM - comprehensive borrower management with automated emails."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    if request.method == "POST":
        action = request.form.get("action", "add")
        
        if action == "add":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip()
            phone = request.form.get("phone", "").strip()
            status = request.form.get("status", "prospect").strip()
            loan_type = request.form.get("loan_type", "").strip()
            target_payment = request.form.get("target_payment", "").strip()
            birthday = request.form.get("birthday", "").strip()
            home_anniversary = request.form.get("home_anniversary", "").strip()
            address = request.form.get("address", "").strip()
            notes = request.form.get("notes", "").strip()
            tags = request.form.get("tags", "").strip()
            property_address = request.form.get("property_address", "").strip()
            loan_amount = request.form.get("loan_amount", "").strip()
            loan_rate = request.form.get("loan_rate", "").strip()
            
            try:
                loan_amt = float(loan_amount) if loan_amount else None
                rate = float(loan_rate) if loan_rate else None
                borrower_id = add_lender_borrower(
                    user["id"], name, status, loan_type, target_payment, "",
                    email, phone, birthday, home_anniversary, address, notes, tags,
                    property_address, loan_amt, rate
                )
                
                # If email provided, try to link to existing homeowner account
                if email:
                    from database import get_user_by_email, create_client_relationship, get_or_create_referral_code
                    homeowner = get_user_by_email(email)
                    from database import get_active_professional_id as _gap
                    if homeowner and homeowner.get("role") == "homeowner" and _gap(homeowner["id"], "lender") not in (None, user["id"]):
                        flash("Borrower added. That email already has a homeowner account connected to another lender, so "
                              "send them your invite link and they can choose to connect with you.", "success")
                    elif homeowner and homeowner.get("role") == "homeowner":
                        # Create relationship
                        referral_code = get_or_create_referral_code(user["id"], "lender")
                        create_client_relationship(
                            homeowner_id=homeowner["id"],
                            professional_id=user["id"],
                            professional_role="lender",
                            referral_code=referral_code
                        )
                        flash(f"Borrower added and linked to homeowner account ({email})!", "success")
                    else:
                        flash("Borrower added!", "success")
                else:
                    flash("Borrower added!", "success")
            except Exception as e:
                flash("We could not add that borrower. Please try again in a moment.", "error")
        
        elif action == "update":
            borrower_id = request.form.get("borrower_id")
            if borrower_id:
                updates = {}
                for field in ['name', 'email', 'phone', 'status', 'loan_type', 
                            'target_payment', 'birthday', 'home_anniversary', 
                            'address', 'notes', 'tags', 'property_address',
                            'loan_amount', 'loan_rate', 'auto_birthday', 
                            'auto_anniversary', 'auto_seasonal', 'auto_equity',
                            'auto_holidays', 'equity_frequency', 'loan_stage', 'close_date']:
                    val = request.form.get(field, "").strip()
                    if val or field in ['auto_birthday', 'auto_anniversary', 
                                       'auto_seasonal', 'auto_equity', 'auto_holidays']:
                        if field in ['auto_birthday', 'auto_anniversary', 
                                    'auto_seasonal', 'auto_equity', 'auto_holidays']:
                            updates[field] = 1 if request.form.get(field) else 0
                        elif field in ['loan_amount', 'loan_rate']:
                            try:
                                updates[field] = float(val) if val else None
                            except Exception:
                                pass
                        else:
                            updates[field] = val if val else None
                
                try:
                    _before = get_lender_borrower(int(borrower_id), user["id"]) or {}
                    update_lender_borrower(int(borrower_id), user["id"], **updates)
                    if updates.get("status") and updates.get("status") != _before.get("status"):
                        import automation
                        _bg(automation.notify_borrower_status, user["id"],
                            updates.get("name") or _before.get("name"),
                            updates.get("email") or _before.get("email"),
                            updates["status"], send_reminder_email, _site_url())
                    flash("Borrower updated!", "success")
                except Exception as e:
                    flash("We could not update that borrower. Please try again in a moment.", "error")
        
        elif action == "add_interaction":
            borrower_id = request.form.get("borrower_id")
            interaction_type = request.form.get("interaction_type", "").strip()
            subject = request.form.get("subject", "").strip()
            notes = request.form.get("notes", "").strip()
            channel = request.form.get("channel", "email").strip()
            
            if borrower_id and interaction_type:
                try:
                    add_crm_interaction(
                        int(borrower_id), "lender_borrower", user["id"],
                        interaction_type, subject, notes, channel
                    )
                    flash("Interaction logged!", "success")
                except Exception as e:
                    flash("We could not log that note. Please try again in a moment.", "error")
        
        elif action == "add_task":
            borrower_id = request.form.get("borrower_id")
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            due_date = request.form.get("due_date", "").strip()
            priority = request.form.get("priority", "medium").strip()
            reminder_date = request.form.get("reminder_date", "").strip() or None
            
            if borrower_id and title:
                try:
                    add_crm_task(
                        int(borrower_id), "lender_borrower", user["id"],
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
        
        elif action == "add_deal":
            borrower_id = request.form.get("borrower_id")
            deal_name = request.form.get("deal_name", "").strip()
            deal_type = request.form.get("deal_type", "other").strip()
            property_address = request.form.get("property_address", "").strip()
            deal_value = request.form.get("deal_value", "").strip()
            commission_rate = request.form.get("commission_rate", "").strip()
            stage = request.form.get("stage", "prospect").strip()
            probability = request.form.get("probability", "0").strip()
            expected_close_date = request.form.get("expected_close_date", "").strip()
            notes = request.form.get("notes", "").strip()
            
            if borrower_id and deal_name:
                try:
                    deal_val = float(deal_value) if deal_value else None
                    comm_rate = float(commission_rate) if commission_rate else None
                    prob = int(probability) if probability else 0
                    add_crm_deal(
                        int(borrower_id), "lender_borrower", user["id"],
                        deal_name, deal_type, property_address, deal_val, comm_rate,
                        stage, prob, expected_close_date or None, notes
                    )
                    flash("Deal added!", "success")
                except Exception as e:
                    flash("We could not add that deal. Please try again in a moment.", "error")
        
        elif action == "bulk_action":
            borrower_ids = request.form.getlist("borrower_ids")
            bulk_action_type = request.form.get("bulk_action_type", "").strip()
            
            if borrower_ids and bulk_action_type:
                try:
                    for borrower_id in borrower_ids:
                        if bulk_action_type == "add_tag":
                            tag = request.form.get("bulk_tag", "").strip()
                            borrower = get_lender_borrower(int(borrower_id), user["id"])
                            if borrower:
                                existing_tags = (borrower.get("tags") or "").split(",")
                                existing_tags = [t.strip() for t in existing_tags if t.strip()]
                                if tag and tag not in existing_tags:
                                    existing_tags.append(tag)
                                    update_lender_borrower(int(borrower_id), user["id"], tags=", ".join(existing_tags))
                        elif bulk_action_type == "change_status":
                            status = request.form.get("bulk_status", "").strip()
                            if status:
                                update_lender_borrower(int(borrower_id), user["id"], status=status)
                    flash(f"Bulk action completed for {len(borrower_ids)} borrower(s)!", "success")
                except Exception as e:
                    flash("We could not complete that bulk action. Please try again in a moment.", "error")
        
        elif action == "update_followup_days":
            follow_up_days = request.form.get("follow_up_days", "30").strip()
            try:
                days = int(follow_up_days)
                if 1 <= days <= 365:
                    conn = get_connection()
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE users SET follow_up_days = ? WHERE id = ?",
                        (days, user["id"])
                    )
                    conn.commit()
                    conn.close()
                    flash(f"Follow-up reminder set to {days} days!", "success")
                else:
                    flash("Please enter a number between 1 and 365.", "error")
            except ValueError:
                flash("Invalid number. Please enter a number between 1 and 365.", "error")

    status_filter = request.args.get("status")
    borrowers_all = list_lender_borrowers(user["id"], status_filter)
    search_query = (request.args.get("q") or "").strip()
    if search_query:
        _q = search_query.lower()
        borrowers_all = [b for b in borrowers_all if _q in " ".join(str(b[k] or "") for k in ("name", "email", "phone") if k in b.keys()).lower()]
    # Fifty borrowers per page: the page stays fast and small however many borrowers there are.
    PER_PAGE = 50
    filtered_total = len(borrowers_all)
    pages = max(1, -(-filtered_total // PER_PAGE))
    try:
        page = int(request.args.get("page", 1))
    except (TypeError, ValueError):
        page = 1
    page = max(1, min(page, pages))
    borrowers = borrowers_all[(page - 1) * PER_PAGE: page * PER_PAGE]

    # Enrich only this page with history/tasks/deals (four batched queries, not three per borrower)
    from database import crm_page_bundle
    _bundle = crm_page_bundle(user["id"], [b["id"] for b in borrowers], "lender_borrower")
    borrowers_list = []
    for borrower in borrowers:
        try:
            borrower_dict = dict(borrower)
            _bid = borrower_dict['id']
            _ints = _bundle["interactions"].get(_bid, [])
            borrower_dict['interaction_count'] = len(_ints)
            borrower_dict['recent_interactions'] = _ints[:3]
            _tasks = _bundle["tasks"].get(_bid, [])
            borrower_dict['pending_tasks'] = _tasks
            borrower_dict['task_count'] = len(_tasks)
            _deals = _bundle["deals"].get(_bid, [])
            borrower_dict['deals'] = _deals
            borrower_dict['deal_count'] = len(_deals)
            borrower_dict['total_pipeline_value'] = sum([d.get('deal_value') or 0 for d in _deals])
            borrowers_list.append(borrower_dict)
        except Exception:
            continue

    # Calculate stats
    all_tasks = list_crm_tasks(user["id"], status="pending")
    all_deals = list_crm_deals(user["id"])
    
    # Get follow-up threshold from user settings
    from database import get_user_by_id
    user_details = get_user_by_id(user["id"])
    follow_up_days = user_details.get('follow_up_days', 30) if user_details else 30
    
    # Get borrowers needing follow-up
    try:
        from database import get_connection
        conn = get_connection()
        cur = conn.cursor()
        from datetime import timedelta
        cutoff_date = datetime.now() - timedelta(days=follow_up_days)
        cutoff_iso = cutoff_date.isoformat()
        
        cur.execute("""
            SELECT DISTINCT lb.id
            FROM lender_borrowers lb
            LEFT JOIN crm_interactions ci ON ci.contact_id = lb.id 
                AND ci.contact_type = 'lender_borrower' 
                AND ci.professional_user_id = lb.lender_user_id
            WHERE lb.lender_user_id = ?
            AND (
                COALESCE(
                    (SELECT MAX(ci2.interaction_date) 
                     FROM crm_interactions ci2 
                     WHERE ci2.contact_id = lb.id 
                     AND ci2.contact_type = 'lender_borrower' 
                     AND ci2.professional_user_id = lb.lender_user_id),
                    lb.last_touch,
                    lb.created_at
                ) < ? OR
                COALESCE(
                    (SELECT MAX(ci3.interaction_date) 
                     FROM crm_interactions ci3 
                     WHERE ci3.contact_id = lb.id 
                     AND ci3.contact_type = 'lender_borrower' 
                     AND ci3.professional_user_id = lb.lender_user_id),
                    lb.last_touch
                ) IS NULL
            )
        """, (user["id"], cutoff_iso))
        needs_followup_count = len(cur.fetchall())
        conn.close()
    except Exception as e:
        print(f"Error getting borrowers needing followup: {e}")
        needs_followup_count = 0
    
    _all_rows = [dict(b) for b in list_lender_borrowers(user["id"], None)]
    stats = {
        'total': len(_all_rows),
        'prospect': len([b for b in _all_rows if b.get('status') == 'prospect']),
        'preapproval': len([b for b in _all_rows if b.get('status') == 'preapproval']),
        'in_process': len([b for b in _all_rows if b.get('status') == 'in_process']),
        'closed': len([b for b in _all_rows if b.get('status') == 'closed']),
        'pending_tasks': len(all_tasks),
        'total_deals': len(all_deals),
        'pipeline_value': sum([d.get('deal_value') or 0 for d in all_deals]),
        'expected_commission': sum([d.get('expected_commission') or 0 for d in all_deals]),
        'needs_followup': needs_followup_count,
        'follow_up_days': follow_up_days,
        'with_automation': len([b for b in _all_rows if any([
            b.get('auto_birthday'), b.get('auto_anniversary'),
            b.get('auto_seasonal'), b.get('auto_equity'), b.get('auto_holidays')
        ])]),
    }
    
    # Get all unique tags
    all_tags = set()
    for borrower in _all_rows:
        tags = borrower.get('tags', '') or ''
        if tags:
            all_tags.update([t.strip() for t in tags.split(',') if t.strip()])
    all_tags = sorted(list(all_tags))
    
    # Get upcoming tasks
    try:
        upcoming_tasks = [dict(t) for t in all_tasks[:10]]
    except Exception:
        upcoming_tasks = []
    
    return render_template(
        "lender/crm.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        borrowers=borrowers_list,
        status_filter=status_filter,
        search_query=search_query,
        page=page, pages=pages, filtered_total=filtered_total,
        stats=stats,
        all_tags=all_tags,
        upcoming_tasks=upcoming_tasks,
    )


@route("/lender/crm/address-labels")
def lender_address_labels():
    """Print address labels for lender CRM borrowers (30 per page, 3x10 grid)."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    borrowers = list_lender_borrowers(user["id"], status_filter=None)
    labels = []
    for b in borrowers:
        name = (b.get("name") or "").strip()
        addr = (b.get("address") or b.get("property_address") or "").strip()
        if name and addr:
            labels.append({"name": name, "address": addr})
        elif name:
            labels.append({"name": name, "address": "(No address on file)"})
    if not labels:
        labels = [{"name": "", "address": ""}] * 30
    return render_template(
        "shared/address_labels.html",
        labels=labels,
        back_url=url_for("lender_crm"),
        back_label="Back to CRM",
        role="lender",
    )


@route("/lender/crm/import", methods=["GET", "POST"])
def lender_crm_import():
    """Lender CRM bulk import from Excel/CSV."""
    try:
        user = get_current_user()
        if not user or user.get("role") != "lender":
            return redirect(url_for("login", role="lender"))
    except Exception as e:
        return f"Error: {e}", 500

    if request.method == "POST":
        action = request.form.get("action")
        
        if action == "upload":
            # Handle file upload
            if 'file' not in request.files:
                flash("Please choose a file to upload.", "error")
                return redirect(url_for("lender_crm_import"))
            
            file = request.files['file']
            if file.filename == '':
                flash("Please choose a file to upload.", "error")
                return redirect(url_for("lender_crm_import"))
            
            # Check file extension
            filename = file.filename.lower()
            if not (filename.endswith('.xlsx') or filename.endswith('.xls') or filename.endswith('.csv')):
                flash("Please upload an Excel (.xlsx, .xls) or CSV file and we will take it from there.", "error")
                return redirect(url_for("lender_crm_import"))
            
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
                    "lender/crm_import_preview.html",
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
                return redirect(url_for("lender_crm_import"))
        
        elif action == "import":
            # Actually import the data
            import_data_json = session.get('crm_import_data')
            if not import_data_json:
                flash("We lost track of that import. Please upload your file again.", "error")
                return redirect(url_for("lender_crm_import"))
            
            try:
                data = json.loads(import_data_json)
                
                # Get column mappings from form
                mappings = {
                    'name': request.form.get('map_name', '').strip(),
                    'last_name': request.form.get('map_last_name', '').strip(),
                    'email': request.form.get('map_email', '').strip(),
                    'phone': request.form.get('map_phone', '').strip(),
                    'status': request.form.get('map_status', '').strip(),
                    'loan_type': request.form.get('map_loan_type', '').strip(),
                    'target_payment': request.form.get('map_target_payment', '').strip(),
                    'birthday': request.form.get('map_birthday', '').strip(),
                    'home_anniversary': request.form.get('map_anniversary', '').strip(),
                    'address': request.form.get('map_address', '').strip(),
                    'property_address': request.form.get('map_property_address', '').strip(),
                    'loan_amount': request.form.get('map_loan_amount', '').strip(),
                    'loan_rate': request.form.get('map_loan_rate', '').strip(),
                    'notes': request.form.get('map_notes', '').strip(),
                    'tags': request.form.get('map_tags', '').strip(),
                }
                
                # Default status if not mapped
                default_status = request.form.get('default_status', 'prospect').strip()
                
                # Import settings
                skip_duplicates = request.form.get('skip_duplicates') == 'on'
                duplicate_check = request.form.get('duplicate_check', 'email').strip()
                
                imported = 0
                skipped = 0
                errors = []
                
                def safe_get(val):
                    if val is None:
                        return ''
                    s = str(val).strip()
                    if s.lower() in ('nan', 'none', 'null', ''):
                        return ''
                    return s

                for idx, row in enumerate(data):
                    try:
                        # Map columns to fields
                        first_part = safe_get(row.get(mappings['name'], '')) if mappings['name'] else ''
                        last_part = safe_get(row.get(mappings['last_name'], '')) if mappings.get('last_name') else ''
                        name = f"{first_part} {last_part}".strip() if (first_part or last_part) else ''
                        email = safe_get(row.get(mappings['email'], '')) if mappings['email'] else ''
                        phone = str(row.get(mappings['phone'], '')).strip() if mappings['phone'] else ''
                        status = str(row.get(mappings['status'], default_status)).strip() if mappings['status'] else default_status
                        loan_type = str(row.get(mappings['loan_type'], '')).strip() if mappings['loan_type'] else ''
                        target_payment = str(row.get(mappings['target_payment'], '')).strip() if mappings['target_payment'] else ''
                        birthday = str(row.get(mappings['birthday'], '')).strip() if mappings['birthday'] else ''
                        home_anniversary = str(row.get(mappings['home_anniversary'], '')).strip() if mappings['home_anniversary'] else ''
                        address = str(row.get(mappings['address'], '')).strip() if mappings['address'] else ''
                        property_address = str(row.get(mappings['property_address'], '')).strip() if mappings['property_address'] else ''
                        notes = str(row.get(mappings['notes'], '')).strip() if mappings['notes'] else ''
                        tags = str(row.get(mappings['tags'], '')).strip() if mappings['tags'] else ''
                        
                        # Parse numeric values
                        try:
                            loan_amount = float(row.get(mappings['loan_amount'], 0)) if mappings['loan_amount'] and str(row.get(mappings['loan_amount'], '')).strip() else None
                        except Exception:
                            loan_amount = None
                        
                        try:
                            loan_rate = float(row.get(mappings['loan_rate'], 0)) if mappings['loan_rate'] and str(row.get(mappings['loan_rate'], '')).strip() else None
                        except Exception:
                            loan_rate = None
                        
                        if not name:
                            errors.append(f"Row {idx + 1}: Missing name")
                            continue
                        
                        # Check for duplicates if enabled
                        if skip_duplicates:
                            existing_borrowers = list_lender_borrowers(user["id"])
                            is_duplicate = False
                            for existing in existing_borrowers:
                                if duplicate_check == 'email' and email:
                                    if existing.get('email') and existing['email'].lower() == email.lower():
                                        is_duplicate = True
                                        break
                                elif duplicate_check == 'phone' and phone:
                                    if existing.get('phone') and existing['phone'] == phone:
                                        is_duplicate = True
                                        break
                                elif duplicate_check == 'name' and name:
                                    if existing.get('name') and existing['name'].lower() == name.lower():
                                        is_duplicate = True
                                        break
                            
                            if is_duplicate:
                                skipped += 1
                                continue
                        
                        # Add borrower
                        add_lender_borrower(
                            user["id"], name, status, loan_type, target_payment, "",
                            email, phone, birthday, home_anniversary, address, notes, tags,
                            property_address, loan_amount, loan_rate
                        )
                        imported += 1
                    except Exception as e:
                        errors.append(f"Row {idx + 1}: {str(e)}")
                
                # Clear session
                session.pop('crm_import_data', None)
                session.pop('crm_import_columns', None)
                
                flash(f"All done! We imported {imported} borrowers. {skipped} were skipped and {len(errors)} had trouble.", "success")
                if errors:
                    flash(f"Errors: {', '.join(errors[:5])}{'...' if len(errors) > 5 else ''}", "error")
                
                return redirect(url_for("lender_crm"))
            except Exception as e:
                import traceback
                flash("We ran into trouble with that import. Please check your file and try again.", "error")
                print(f"Import error: {traceback.format_exc()}")
                return redirect(url_for("lender_crm_import"))
    
    # GET request - show upload form
    return render_template(
        "lender/crm_import.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@route("/lender/loans", methods=["GET", "POST"])
def lender_loans():
    """Lender loans management."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    if request.method == "POST":
        borrower_name = request.form.get("borrower_name", "").strip()
        borrower_email = request.form.get("borrower_email", "").strip()
        loan_type = request.form.get("loan_type", "").strip() or "Conventional"
        status = request.form.get("status", "preapproval").strip()

        if borrower_name:
            try:
                add_lender_loan(
                    user["id"], borrower_name, status, loan_type,
                    request.form.get("target_payment", "").strip(),
                    request.form.get("stage", "preapproval_started").strip(),
                    request.form.get("close_date", "").strip(),
                    borrower_email,
                )
                import automation
                _bg(automation.on_loan_created, user["id"], borrower_name, borrower_email, send_reminder_email, _site_url())
                flash("Loan saved." + (" Your borrower has been invited to their portal." if borrower_email else ""), "success")
            except Exception as e:
                print(f"[LOANS] save failed: {e}")
                flash("We could not save that loan. Please try again.", "error")
        else:
            flash("Please enter the borrower's name.", "error")

    loans = list_lender_loans(user["id"])
    return render_template(
        "lender/loans.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        loans=loans,
    )


@route("/lender/booking")
def lender_booking():
    """Calendar and booking integration for lenders."""
    if "user_id" not in session or session.get("role") != "lender":
        return redirect(url_for("login"))
    user = get_user_by_id(session["user_id"])
    if not user:
        return redirect(url_for("login"))
    from database import get_user_profile
    profile = get_user_profile(user["id"])
    return render_template("lender/booking.html", user=user, profile=dict(profile) if profile else {})


@route("/lender/marketing", methods=["GET"])
def lender_marketing():
    """Lender marketing tools."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/marketing.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@route("/lender/marketing-hub")
def lender_marketing_hub_global():
    """Global Marketing Hub for Lenders - Create marketing without a specific loan."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    
    # Get all borrowers for selection
    from database import list_lender_borrowers
    borrowers = list_lender_borrowers(user["id"])
    
    # Get lender profile for branding
    from database import get_user_profile
    lender_profile = None
    try:
        lender_profile = get_user_profile(user["id"])
        if lender_profile and hasattr(lender_profile, 'keys'):
            lender_profile = dict(lender_profile)
    except Exception as e:
        print(f"Error getting lender profile: {e}")
    
    return render_template(
        "lender/marketing_hub_global.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        borrowers=borrowers,
        lender_profile=lender_profile,
    )


@route("/lender/borrowers/<int:borrower_id>/marketing-hub")
def lender_marketing_hub(borrower_id):
    """Marketing Hub for a specific borrower/loan."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    from database import get_lender_borrower
    borrower = get_lender_borrower(borrower_id, user["id"])
    if not borrower:
        flash("We could not find that borrower.", "error")
        return redirect(url_for("lender_crm"))
    
    # Get lender profile for branding
    from database import get_user_profile
    lender_profile = None
    try:
        lender_profile = get_user_profile(user["id"])
        if lender_profile and hasattr(lender_profile, 'keys'):
            lender_profile = dict(lender_profile)
    except Exception as e:
        print(f"Error getting lender profile: {e}")
    
    return render_template(
        "lender/marketing_hub.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        borrower_id=borrower_id,
        borrower=borrower,
        lender_profile=lender_profile,
    )


@route("/lender/borrowers/<int:borrower_id>/marketing-hub/create")
def lender_marketing_create(borrower_id):
    """Create a marketing asset for lender."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    from database import get_lender_borrower
    borrower = get_lender_borrower(borrower_id, user["id"])
    if not borrower:
        flash("We could not find that borrower.", "error")
        return redirect(url_for("lender_crm"))
    
    # Get category and asset type from query params
    category = request.args.get('category', 'pre-approval')
    asset_type = request.args.get('type', 'flyer')
    
    # Get lender profile for branding
    from database import get_user_profile
    lender_profile = None
    try:
        lender_profile = get_user_profile(user["id"])
        if lender_profile and hasattr(lender_profile, 'keys'):
            lender_profile = dict(lender_profile)
    except Exception as e:
        print(f"Error getting lender profile: {e}")
    
    return render_template(
        "lender/marketing_create.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        borrower_id=borrower_id,
        borrower=borrower,
        lender_profile=lender_profile,
        category=category,
        asset_type=asset_type,
    )


@route("/lender/borrowers/<int:borrower_id>/marketing-hub/generate", methods=["POST"])
def lender_marketing_generate(borrower_id):
    """Generate the final marketing asset HTML for printing."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    from database import get_lender_borrower
    borrower = get_lender_borrower(borrower_id, user["id"])
    if not borrower:
        flash("We could not find that borrower.", "error")
        return redirect(url_for("lender_crm"))
    
    try:
        # Get form data
        category = request.form.get('category', '')
        asset_type = request.form.get('asset_type', '')
        headline = request.form.get('headline', '')
        subtext = request.form.get('subtext', '')
        loan_amount = request.form.get('loan_amount', '')
        borrower_name = request.form.get('borrower_name', '')
        custom_text = request.form.get('custom_text', '')
        color_scheme = request.form.get('color_scheme', 'classic')
        layout_style = request.form.get('layout_style', 'classic')
        include_photo = request.form.get('include_photo') == 'on'
        include_logo = request.form.get('include_logo') == 'on'
        include_nmls = request.form.get('include_nmls') == 'on'
        
        # Handle property photo uploads
        property_photos = []
        if 'property_photos' in request.files:
            files = request.files.getlist('property_photos')
            for file in files[:3]:  # Limit to 3 photos
                if file and file.filename:
                    try:
                        # Read file and convert to base64
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
        
        # Get lender profile for branding
        from database import get_user_profile
        lender_profile = None
        try:
            lender_profile = get_user_profile(user["id"])
            if lender_profile and hasattr(lender_profile, 'keys'):
                lender_profile = dict(lender_profile)
        except Exception as e:
            print(f"Error getting lender profile: {e}")
        
        # Render the marketing asset template
        html_content = render_template(
            f"lender/marketing_templates/{category}_{asset_type}.html",
            borrower=borrower,
            lender_profile=lender_profile,
            user=user,
            headline=headline,
            subtext=subtext,
            loan_amount=loan_amount,
            borrower_name=borrower_name,
            custom_text=custom_text,
            color_scheme=color_scheme,
            layout_style=layout_style,
            property_photos=property_photos,
            include_photo=include_photo,
            include_logo=include_logo,
            include_nmls=include_nmls,
        )
        
        # Return HTML with print button for browser-based PDF generation
        return html_content
            
    except Exception as e:
        import traceback
        print(f"Error generating marketing asset: {traceback.format_exc()}")
        flash("We could not create that. Please try again in a moment.", "error")
        return redirect(url_for('lender_marketing_hub', borrower_id=borrower_id))


@route("/lender/marketing/refine-text", methods=["POST"])
def lender_marketing_refine_text():
    """Refine lender marketing text using AI to sound professional but natural."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
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
        
        prompt = f"""You are a mortgage lending marketing expert. Refine this {field} to be:
- Professional and trustworthy
- Natural and human-sounding (NOT robotic or overly formal)
- Warm and celebratory (for celebrations) or informative (for educational content)
- Concise and clear
- Appropriate for financial services marketing

Original {field}: {text}

Return ONLY the refined text, nothing else. Keep it roughly the same length."""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a mortgage lending marketing copywriter who creates warm, professional copy."},
                {"role": "user", "content": prompt}
            ],
            max_tokens=200,
            temperature=0.7
        )
        
        from ai_platform import humanize as _humanize
        refined_text = _humanize(response.choices[0].message.content.strip())
        refined_text = refined_text.strip('"').strip("'")
        
        return jsonify({
            "success": True,
            "refined_text": refined_text
        })
        
    except Exception as e:
        import traceback
        print(f"Error refining lender marketing text: {traceback.format_exc()}")
        return jsonify({"success": False, "error": "Failed to refine text"}), 500


@route("/lender/messages", methods=["GET"])
def lender_messages():
    """Lender messages."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/messages.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@route("/lender/roles", methods=["GET"])
def lender_roles():
    """Lender roles and partners."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/roles.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@route("/lender/power-suite", methods=["GET"])
def lender_power_suite():
    """Lender power suite."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    return render_template(
        "lender/power_suite.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
    )


@route("/lender/clients")
def lender_clients():
    """Lender client portal, list of all linked homeowner clients with live data."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    
    from database import get_lender_clients
    clients = get_lender_clients(user["id"])
    
    return render_template("lender/clients.html", clients=clients)


@route("/lender/clients/<int:homeowner_id>")
def lender_client_detail(homeowner_id):
    """Lender view of a specific homeowner client's full portal data."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    
    from database import (
        can_access_homeowner, get_user_by_id, get_homeowner_full_profile,
        get_homeowner_recent_activity, get_homeowner_professionals
    )
    
    if not can_access_homeowner(user["id"], "lender", homeowner_id):
        flash("That client is not connected to your account.", "error")
        return redirect(url_for("lender_clients"))
    
    homeowner = get_user_by_id(homeowner_id)
    if not homeowner or homeowner.get("role") != "homeowner":
        flash("We could not find that client.", "error")
        return redirect(url_for("lender_clients"))
    
    profile = get_homeowner_full_profile(homeowner_id)
    recent_activity = get_homeowner_recent_activity(homeowner_id, limit=15)
    professionals = get_homeowner_professionals(homeowner_id)
    
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
    snapshot_history = [dict(r) for r in _conn.execute(
        "SELECT snapshot_date, value_estimate, equity_estimate, loan_balance, loan_rate FROM homeowner_snapshot_history WHERE user_id = ? ORDER BY snapshot_date DESC LIMIT 12",
        (homeowner_id,)
    ).fetchall()]
    # Load any transactions where this lender is attached
    transactions = [dict(r) for r in _conn.execute(
        """SELECT t.id, t.property_address, t.client_name, t.current_stage, 
                  t.purchase_price, t.target_close_date, t.status,
                  u.name as agent_name
           FROM transactions t
           LEFT JOIN users u ON u.id = t.agent_id
           WHERE t.lender_user_id = ? OR t.homeowner_user_id = ?
           ORDER BY t.created_at DESC LIMIT 10""",
        (user["id"], homeowner_id)
    ).fetchall()]
    _conn.close()
    
    from database import list_lender_borrowers
    crm_borrower = None
    for b in list_lender_borrowers(user["id"]):
        if b.get("user_id") == homeowner_id or (b.get("email") and homeowner and b.get("email").lower() == dict(homeowner).get("email", "").lower()):
            crm_borrower = b
            break
    
    return render_template(
        "lender/client_detail.html",
        homeowner=dict(homeowner),
        profile=profile,
        recent_activity=recent_activity,
        professionals=professionals,
        docs=docs,
        projects=projects,
        snapshot_history=snapshot_history,
        transactions=transactions,
        crm_borrower=crm_borrower,
    )


@route("/lender/referrals", methods=["GET", "POST"])
def lender_referrals():
    """Lender referral link management."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    try:
        from database import (
            get_referral_links_for_lender,
            create_referral_link,
            get_referral_stats,
            get_accessible_homeowners
        )
        
        # Handle POST - create new referral link
        if request.method == "POST":
            try:
                token = create_referral_link(lender_id=user["id"])
                flash("New referral link created!", "success")
                return redirect(url_for("lender_referrals"))
            except Exception as e:
                flash("We could not create that referral link. Please try again in a moment.", "error")
        
        # Get all referral links for this lender
        referral_links = get_referral_links_for_lender(user["id"])
        
        # If no links exist, create one automatically
        if not referral_links:
            try:
                token = create_referral_link(lender_id=user["id"])
                referral_links = get_referral_links_for_lender(user["id"])
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
            "lender/referrals.html",
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
        print(f"Error in lender_referrals: {error_trace}")
        flash("We could not load your referral page. Please try again in a moment.", "error")
        return redirect(url_for("lender_dashboard"))


@route("/lender/settings/profile", methods=["GET", "POST"])
def lender_settings_profile():
    """Lender settings and profile."""
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))

    from database import get_user_profile, create_or_update_user_profile

    # Handle POST - update profile
    if request.method == "POST":
        try:
            # Handle file uploads using consolidated helper
            professional_photo = handle_profile_file_upload("professional_photo", folder="profiles", role_prefix="LENDER ")
            brokerage_logo = handle_profile_file_upload("brokerage_logo", folder="profiles", role_prefix="LENDER ")
            
            # Preserve existing photos/logos if not uploading new ones
            professional_photo, brokerage_logo = preserve_existing_profile_media(
                user["id"], professional_photo, brokerage_logo
            )
            
            # Get form data
            print(f"LENDER PROFILE: About to save profile with photo={professional_photo}, logo={brokerage_logo}")
            profile_id = create_or_update_user_profile(
                user_id=user["id"],
                role="lender",
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
                application_url=request.form.get("application_url", "").strip() or None,
                bio=request.form.get("bio", "").strip() or None,
                specialties=request.form.get("specialties", "").strip() or None,
                years_experience=int(request.form.get("years_experience")) if request.form.get("years_experience") else None,
                languages=request.form.get("languages", "").strip() or None,
                service_areas=request.form.get("service_areas", "").strip() or None,
                nmls_number=request.form.get("nmls_number", "").strip() or None,
                license_number=request.form.get("license_number", "").strip() or None,
                company_address=request.form.get("company_address", "").strip() or None,
                company_city=request.form.get("company_city", "").strip() or None,
                company_state=request.form.get("company_state", "").strip() or None,
                company_zip=request.form.get("company_zip", "").strip() or None,
                homebot_widget_id=request.form.get("homebot_widget_id", "").strip() or None,
                va_rate_30yr=float(request.form.get("va_rate_30yr")) if request.form.get("va_rate_30yr") else None,
                fha_rate_30yr=float(request.form.get("fha_rate_30yr")) if request.form.get("fha_rate_30yr") else None,
                conventional_rate_30yr=float(request.form.get("conventional_rate_30yr")) if request.form.get("conventional_rate_30yr") else None,
            )
            flash("Profile updated!", "success")
            return redirect(url_for("lender_settings_profile"))
        except Exception as e:
            import traceback
            print(f"Error updating profile: {traceback.format_exc()}")
            flash("We could not update your profile. Please try again in a moment.", "error")
    
    # GET - load profile
    profile = get_user_profile(user["id"])
    profile_dict = dict(profile) if profile and hasattr(profile, 'keys') else (profile if profile else {})

    # Referral link
    from database import get_referral_links_for_lender, create_referral_link as _create_ref_l
    try:
        ref_links = get_referral_links_for_lender(user["id"])
        if not ref_links:
            _create_ref_l(lender_id=user["id"])
            ref_links = get_referral_links_for_lender(user["id"])
        referral_url = url_for("referral_landing", referral_code=ref_links[0]["token"], _external=True) if ref_links else None
    except Exception:
        referral_url = None

    return render_template(
        "lender/settings_profile.html",
        brand_name=FRONT_BRAND_NAME,
        user=user,
        profile=profile_dict,
        referral_url=referral_url,
    )


@route("/lender/financials", methods=["GET"])
def lender_financials():
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    uid = user["id"]

    year = request.args.get("year", str(datetime.now().year))
    try:
        year = int(year)
    except Exception:
        year = datetime.now().year

    try:
        conn = get_db_connection()

        # Revenue (closed loans)
        revenues = [dict(r) for r in conn.execute(
            "SELECT * FROM lender_loan_revenue WHERE lender_user_id=? AND close_date LIKE ? ORDER BY close_date DESC",
            (uid, f"{year}%")
        ).fetchall()]

        # Expenses
        expenses = [dict(r) for r in conn.execute(
            "SELECT * FROM lender_expenses WHERE lender_user_id=? AND expense_date LIKE ? ORDER BY expense_date DESC",
            (uid, f"{year}%")
        ).fetchall()]

        # Goals
        goals = [dict(r) for r in conn.execute(
            "SELECT * FROM lender_financial_goals WHERE lender_user_id=? AND goal_year=?",
            (uid, year)
        ).fetchall()]

        conn.close()
    except Exception as db_err:
        app.logger.error(f"lender_financials DB error: {db_err}")
        revenues, expenses, goals = [], [], []

    ytd_revenue = sum(r.get("origination_fee_amt", 0) or 0 for r in revenues if r.get("status") == "funded")
    ytd_projected = sum(r.get("origination_fee_amt", 0) or 0 for r in revenues if r.get("status") == "projected")
    ytd_expenses = sum(e.get("amount", 0) or 0 for e in expenses)
    ytd_loan_volume = sum(r.get("loan_amount", 0) or 0 for r in revenues if r.get("status") == "funded")
    net_income = ytd_revenue - ytd_expenses

    monthly_revenue = {}
    for r in revenues:
        if r.get("status") == "funded" and r.get("close_date"):
            try:
                mo = int(r["close_date"].split("-")[1])
                monthly_revenue[mo] = monthly_revenue.get(mo, 0) + (r.get("origination_fee_amt", 0) or 0)
            except Exception:
                pass
    monthly_revenue_list = [monthly_revenue.get(m, 0) for m in range(1, 13)]

    expense_by_cat = {}
    for e in expenses:
        cat = e.get("category", "Other") or "Other"
        expense_by_cat[cat] = expense_by_cat.get(cat, 0) + (e.get("amount", 0) or 0)

    available_years = list(range(datetime.now().year, 2023, -1))

    return render_template("lender/financials.html",
        user=user,
        year=year,
        available_years=available_years,
        revenues=revenues,
        expenses=expenses,
        goals=goals,
        ytd_revenue=ytd_revenue,
        ytd_projected=ytd_projected,
        ytd_expenses=ytd_expenses,
        ytd_loan_volume=ytd_loan_volume,
        net_income=net_income,
        monthly_revenue_list=monthly_revenue_list,
        expense_by_cat=expense_by_cat,
    )


@route("/lender/financials/revenue/add", methods=["POST"])
def lender_financials_revenue_add():
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    uid = user["id"]
    f = request.form
    loan_amount = float(f.get("loan_amount") or 0)
    orig_pct = float(f.get("origination_pct") or 1.0)
    orig_fee_amt = float(f.get("origination_fee") or round(loan_amount * orig_pct / 100, 2))
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO lender_loan_revenue
        (lender_user_id, borrower_name, property_address, loan_type, loan_amount,
         origination_fee_pct, origination_fee_amt, total_revenue, close_date, status, notes)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """, (uid, f.get("borrower_name",""), f.get("property_address",""),
          f.get("loan_type","purchase"), loan_amount, orig_pct, orig_fee_amt, orig_fee_amt,
          f.get("close_date",""), f.get("status","projected"), f.get("notes","")))
    conn.commit()
    conn.close()
    flash("Loan revenue added!", "success")
    year = (f.get("close_date") or "")[:4] or str(datetime.now().year)
    return redirect(url_for("lender_financials", year=year))


@route("/lender/financials/revenue/<int:rid>/delete", methods=["POST"])
def lender_financials_revenue_delete(rid):
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    conn = get_db_connection()
    conn.execute("DELETE FROM lender_loan_revenue WHERE id=? AND lender_user_id=?", (rid, user["id"]))
    conn.commit()
    conn.close()
    flash("Revenue entry removed.", "success")
    return redirect(url_for("lender_financials"))


@route("/lender/financials/revenue/<int:rid>/mark-funded", methods=["POST"])
def lender_financials_revenue_mark_funded(rid):
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    conn = get_db_connection()
    conn.execute("UPDATE lender_loan_revenue SET status='funded' WHERE id=? AND lender_user_id=?", (rid, user["id"]))
    conn.commit()
    conn.close()
    return redirect(url_for("lender_financials"))


@route("/lender/financials/expense/add", methods=["POST"])
def lender_financials_expense_add():
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    uid = user["id"]
    f = request.form
    conn = get_db_connection()
    conn.execute("""
        INSERT INTO lender_expenses
        (lender_user_id, expense_date, category, description, amount, receipt_url, notes)
        VALUES (?,?,?,?,?,?,?)
    """, (uid, f.get("expense_date",""), f.get("category","Other"),
          f.get("description",""), float(f.get("amount") or 0),
          f.get("receipt_url",""), f.get("notes","")))
    conn.commit()
    conn.close()
    flash("Expense logged!", "success")
    year = (f.get("expense_date") or "")[:4] or str(datetime.now().year)
    return redirect(url_for("lender_financials", year=year))


@route("/lender/financials/expense/<int:eid>/delete", methods=["POST"])
def lender_financials_expense_delete(eid):
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    conn = get_db_connection()
    conn.execute("DELETE FROM lender_expenses WHERE id=? AND lender_user_id=?", (eid, user["id"]))
    conn.commit()
    conn.close()
    flash("Expense removed.", "success")
    return redirect(url_for("lender_financials"))


@route("/lender/financials/goal/save", methods=["POST"])
def lender_financials_goal_save():
    user = get_current_user()
    if not user or user.get("role") != "lender":
        return redirect(url_for("login", role="lender"))
    uid = user["id"]
    f = request.form
    year = int(f.get("goal_year", datetime.now().year))
    conn = get_db_connection()
    existing = conn.execute(
        "SELECT id FROM lender_financial_goals WHERE lender_user_id=? AND goal_year=?", (uid, year)
    ).fetchone()
    if existing:
        conn.execute("""
            UPDATE lender_financial_goals SET
            revenue_goal=?, loan_count_goal=?, loan_volume_goal=?,
            expenses_budget=?, net_income_goal=?, notes=?
            WHERE lender_user_id=? AND goal_year=?
        """, (float(f.get("revenue_goal") or 0), int(f.get("loan_count_goal") or 0),
              float(f.get("loan_volume_goal") or 0), float(f.get("expenses_budget") or 0),
              float(f.get("net_income_goal") or 0), f.get("notes",""), uid, year))
    else:
        conn.execute("""
            INSERT INTO lender_financial_goals
            (lender_user_id, goal_year, revenue_goal, loan_count_goal, loan_volume_goal,
             expenses_budget, net_income_goal, notes)
            VALUES (?,?,?,?,?,?,?,?)
        """, (uid, year, float(f.get("revenue_goal") or 0), int(f.get("loan_count_goal") or 0),
              float(f.get("loan_volume_goal") or 0), float(f.get("expenses_budget") or 0),
              float(f.get("net_income_goal") or 0), f.get("notes","")))
    conn.commit()
    conn.close()
    flash("Goals saved!", "success")
    return redirect(url_for("lender_financials", year=year))
