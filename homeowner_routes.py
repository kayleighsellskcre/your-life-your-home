"""Homeowner pages (overview, home value and equity, documents, projects, support, next-home hub, settings).

Moved out of app.py. Loaded by install(), which runs these views in app.py's own namespace (see route_loader.py), so every
helper they use is looked up there, exactly as before. This file is not meant to be run or linted on its own. Route names
(endpoints) are unchanged, so url_for(...) keeps working.
"""
from typing import Optional

from route_loader import Registry

_registry = Registry()
route = _registry.route
install = _registry.install


@route("/homeowner/reno/planner/ajax-add", methods=["POST"])
def homeowner_reno_planner_ajax_add():
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401

    data = request.get_json() or {}
    name = data.get("project_name", "").strip()
    budget = data.get("project_budget")
    status = data.get("project_status", "Planning").strip()
    category = data.get("project_category", "Other").strip()  # Get category, default to "Other"
    board_name = data.get("board_name", "").strip()
    summary = data.get("project_summary", "").strip()

    if not name:
        return jsonify({"success": False, "error": "Project name required"}), 400

    # Convert budget to string (function expects string, not float)
    budget_str = str(budget) if budget else ""

    # Get notes from JSON data
    notes = data.get("project_notes", "").strip()
    
    # If a board_name is provided, save as a design board note as well
    board_save_error = None
    board_save_success = False
    board_note_id = None
    if board_name:
        note_title = name
        # Include budget and status in details - create a comprehensive note
        note_details_parts = []
        
        # Add summary if available
        if summary:
            note_details_parts.append(summary)
        elif notes:
            note_details_parts.append(notes)
        else:
            note_details_parts.append(f"Project: {name}")
        
        # Add budget information
        if budget:
            try:
                budget_float = float(budget) if budget else 0
                note_details_parts.append(f"\n\n Estimated Cost: ${budget_float:,.0f}")
            except (ValueError, TypeError):
                if budget_str:
                    note_details_parts.append(f"\n\n Estimated Cost: ${budget_str}")
        
        # Add status
        if status:
            note_details_parts.append(f"\n Status: {status}")
        
        # Add category if available
        if category and category != "Other":
            note_details_parts.append(f"\n Category: {category}")
        
        note_details = "\n".join(note_details_parts)
        
        try:
            # add_design_board_note will create the board if it doesn't exist
            note_id = add_design_board_note(
                user_id=user_id, 
                project_name=board_name, 
                title=note_title,
                details=note_details,
            photos=[],
                files=[],
                vision_statement=None,
                color_palette=None,
                board_template="collage",
                label_style="sans-serif",
                is_private=0,
                fixtures=[],
            )
            board_save_success = True
            board_note_id = note_id
            print(f"[COST ESTIMATE SAVE] Successfully saved to mood board '{board_name}' (note_id: {note_id})")
        except Exception as e:
            import traceback
            error_msg = str(e)
            print(f"[COST ESTIMATE SAVE ERROR] Could not save to board '{board_name}': {error_msg}")
            print(traceback.format_exc())
            board_save_error = error_msg

    # Always save to renovation planner, even if board save fails
    project_id = None
    try:
    # Fix: Add category parameter and correct argument order
    # Function signature: user_id, name, category, status, budget, notes
        project_id = add_homeowner_project(user_id, name, category, status, budget_str, notes)
    except Exception as e:
        import traceback
        error_msg = str(e)
        print(f"[COST ESTIMATE SAVE ERROR] Could not save to planner: {error_msg}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": f"Could not save project: {error_msg}"}), 500
    
    # Return success response with details
    response_data = {
        "success": True,
        "saved_to_planner": True,
        "saved_to_board": board_save_success,
        "project_id": project_id,
        "note_id": board_note_id if board_save_success else None
    }
    
    if board_save_success:
        response_data["message"] = f"Successfully saved to Renovation Planner and Mood Board '{board_name}'"
    elif board_save_error:
        response_data["warning"] = f"Project saved to Renovation Planner, but could not save to mood board '{board_name}': {board_save_error}"
    else:
        response_data["message"] = "Successfully saved to Renovation Planner"
    
    return jsonify(response_data)


@route("/homeowner")
@route("/homeowner/<int:homeowner_id>")
def homeowner_overview(homeowner_id: Optional[int] = None):
    """
    Overview dashboard (My Home Base).
    Shows agent/lender info if homeowner was referred.
    If homeowner_id is provided, it's an agent/lender viewing a homeowner's dashboard.
    """
    from database import get_homeowner_professionals, get_user_by_id
    
    _pending = session.get("pending_connect")
    if _pending and not homeowner_id and session.get("role") == "homeowner":
        session.pop("pending_connect", None)
        return redirect(url_for("connect_with_professional", token=_pending))

    # Determine which homeowner to show
    if homeowner_id:
        # Agent/lender viewing a specific homeowner
        user, error = require_homeowner_access(homeowner_id)
        if error:
            flash(error, "error")
            return redirect(url_for("agent_dashboard" if user and user.get("role") == "agent" else "lender_dashboard"))
        homeowner_user = get_user_by_id(homeowner_id)
        if not homeowner_user or homeowner_user["role"] != "homeowner":
            flash("We could not find that homeowner.", "error")
            return redirect(url_for("agent_dashboard" if user.get("role") == "agent" else "lender_dashboard"))
        homeowner_user = dict(homeowner_user)
        viewing_as_professional = True
        is_guest = False
    else:
        # Homeowner viewing their own dashboard (or guest)
        user = get_current_user()
        if not user:
            # Guest mode - allow viewing but not saving
            is_guest = True
            homeowner_user = None
            homeowner_id = None
            viewing_as_professional = False
        elif user.get("role") != "homeowner":
            flash("That page is made for homeowners.", "error")
            return redirect(url_for("agent_dashboard" if user.get("role") == "agent" else "lender_dashboard"))
        else:
            # Authenticated homeowner
            is_guest = False
            homeowner_user = user
            homeowner_id = user["id"]
            viewing_as_professional = False
    
    # CRITICAL: Explicitly load professionals for this homeowner
    professionals_list = []
    if homeowner_id:
        try:
            profs_raw = get_homeowner_professionals(homeowner_id)
            print(f"HOMEOWNER DASHBOARD: Loading professionals for homeowner {homeowner_id} - found {len(profs_raw)}")
            for prof in profs_raw:
                if hasattr(prof, 'keys'):
                    prof_dict = dict(prof)
                    if not prof_dict.get('professional_role'):
                        prof_dict['professional_role'] = prof_dict.get('professional_type') or 'agent'
                    if not prof_dict.get('professional_id'):
                        prof_dict['professional_id'] = prof_dict.get('user_id')
                    professionals_list.append(prof_dict)
                    print(f"HOMEOWNER DASHBOARD: Professional - {prof_dict.get('name')} ({prof_dict.get('professional_role')})")
                else:
                    professionals_list.append(prof)
            
            if not professionals_list:
                print(f"HOMEOWNER DASHBOARD WARNING: No professionals found for homeowner {homeowner_id}")
                # Fallback: check agent_id column
                if homeowner_user:
                    homeowner_dict = dict(homeowner_user) if hasattr(homeowner_user, 'keys') and not isinstance(homeowner_user, dict) else homeowner_user
                    agent_id = homeowner_dict.get("agent_id")
                    if agent_id:
                        print(f"HOMEOWNER DASHBOARD: Found agent_id {agent_id} in user record, loading...")
                        try:
                            from database import get_user_by_id, get_user_profile
                            agent_user = get_user_by_id(agent_id)
                            if agent_user:
                                agent_dict = dict(agent_user) if hasattr(agent_user, 'keys') and not isinstance(agent_user, dict) else agent_user
                                agent_profile = get_user_profile(agent_id)
                                prof_data = {
                                    'professional_id': agent_id,
                                    'professional_role': 'agent',
                                    'name': agent_dict.get('name'),
                                    'email': agent_dict.get('email'),
                                    'user_id': agent_id
                                }
                                if agent_profile:
                                    profile_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') and not isinstance(agent_profile, dict) else agent_profile
                                    prof_data.update({
                                        'professional_photo': profile_dict.get('professional_photo'),
                                        'brokerage_logo': profile_dict.get('brokerage_logo'),
                                        'brokerage_name': profile_dict.get('brokerage_name'),
                                        'phone': profile_dict.get('phone'),
                                        'team_name': profile_dict.get('team_name'),
                                        'website_url': profile_dict.get('website_url'),
                                        'bio': profile_dict.get('bio'),
                                    })
                                professionals_list.append(prof_data)
                                print(f"HOMEOWNER DASHBOARD: Added agent from agent_id column - {prof_data.get('name')}")
                        except Exception as fallback_error:
                            print(f"HOMEOWNER DASHBOARD: Fallback failed - {str(fallback_error)}")
        except Exception as prof_error:
            import traceback
            print(f"HOMEOWNER DASHBOARD ERROR loading professionals: {traceback.format_exc()}")
    
    # Get snapshot (only for authenticated homeowners) - use property-specific for consistency with equity overview
    snapshot = None
    if homeowner_user:
        from database import get_primary_property, get_homeowner_snapshot_for_property
        primary_property = get_primary_property(homeowner_id)
        if primary_property:
            property_id = primary_property.get('id')
            snapshot = get_homeowner_snapshot_for_property(homeowner_id, property_id)
            # Calculate equity if we have value and loan balance (same formula as equity overview)
            if snapshot and snapshot.get('value_estimate') and snapshot.get('loan_balance'):
                snapshot['equity_estimate'] = snapshot.get('value_estimate') - snapshot.get('loan_balance')
        if not snapshot:
            # Fallback to user-level snapshot
            snapshot = get_homeowner_snapshot_or_default(homeowner_user)
    else:
        # Guest mode - create empty snapshot
        snapshot = {
            "value_estimate": None,
            "equity_estimate": None,
            "loan_rate": None,
            "loan_payment": None,
            "loan_balance": None,
        }
    
    # Use the professionals_list we loaded earlier, or fallback to empty list
    professionals = professionals_list if professionals_list else []

    # Attach referral URLs so the homeowner can share their agent/lender's link
    try:
        from database import get_referral_links_for_agent, get_referral_links_for_lender, create_referral_link as _create_ref_ho
        for prof in professionals:
            prof_role = prof.get("professional_role") or prof.get("professional_type", "agent")
            prof_id = prof.get("professional_id") or prof.get("user_id")
            if not prof_id:
                continue
            try:
                if prof_role == "agent":
                    links = get_referral_links_for_agent(prof_id)
                    if not links:
                        _create_ref_ho(agent_id=prof_id)
                        links = get_referral_links_for_agent(prof_id)
                else:
                    links = get_referral_links_for_lender(prof_id)
                    if not links:
                        _create_ref_ho(lender_id=prof_id)
                        links = get_referral_links_for_lender(prof_id)
                if links:
                    prof["referral_url"] = url_for("referral_landing", referral_code=links[0]["token"], _external=True)
            except Exception:
                pass
    except Exception:
        pass

    # Final verification before rendering
    if homeowner_id and not professionals:
        print(f"HOMEOWNER DASHBOARD FINAL WARNING: No professionals found for homeowner {homeowner_id} - dashboard will show empty team section")

    # Load the homeowner's active transaction (linked by homeowner account or client email)
    active_transaction = None
    if homeowner_id and homeowner_user:
        try:
            hw_email = (homeowner_user.get("email") or "").lower().strip()
            conn_tx = get_db_connection()
            tx_row = conn_tx.execute(
                """SELECT *, current_stage AS stage, target_close_date AS close_date FROM transactions
                   WHERE (homeowner_user_id = ? OR (? <> '' AND lower(client_email) = ?))
                     AND status = 'active' AND current_stage NOT IN ('closed','cancelled')
                   ORDER BY created_at DESC LIMIT 1""",
                (homeowner_id, hw_email, hw_email)
            ).fetchone()
            conn_tx.close()
            if tx_row:
                active_transaction = dict(tx_row)
        except Exception as tx_err:
            print(f"[Overview] Could not load homeowner transaction: {tx_err}")

    recent_items = []
    try:
        import automation
        recent_items = automation.homeowner_activity(homeowner_id or session.get("user_id"), limit=5)
        for _a in recent_items:
            _a["link_url"] = url_for(_a["endpoint"])
    except Exception as _e:
        print(f"[Overview] activity feed skipped: {_e}")

    extras = None
    if homeowner_id and homeowner_user and not viewing_as_professional:
        try:
            extras = _homeowner_home.overview_extras(homeowner_id)
        except Exception as _e:
            print(f"[Overview] extras skipped: {_e}")

    return render_template(
        "homeowner/overview.html",
        brand_name=FRONT_BRAND_NAME,
        extras=extras,
        recent_items=recent_items,
        snapshot=snapshot,
        cloud_cma_url=CLOUD_CMA_URL,
        professionals=professionals,
        homeowner=homeowner_user,
        viewing_as_professional=viewing_as_professional,
        current_user=user,
        is_guest=is_guest,
        active_transaction=active_transaction,
    )


@route("/homeowner/recent-activity")
def homeowner_recent_activity():
    import automation
    activities = automation.homeowner_activity(
        session.get("user_id"),
        q=request.args.get("q"), type_=request.args.get("type"), range_=request.args.get("range"),
        from_date=request.args.get("from_date"), to_date=request.args.get("to_date"),
    )
    for a in activities:
        a["link_url"] = url_for(a["endpoint"])
    return render_template(
        "homeowner/recent_activity.html",
        brand_name=FRONT_BRAND_NAME,
        activities=activities,
        activity_types=automation.ACTIVITY_TYPES,
    )


@route("/homeowner/saved-notes", methods=["GET", "POST"])
def homeowner_saved_notes():
    """
    Manage premium mood boards for homeowners with advanced features like
    color palettes, vision statements, templates, and drag-and-drop uploads.
    """
    user = get_current_user()
    if not user:
        flash("Please sign in to create boards.", "warning")
        return redirect(url_for("login"))
    
    user_id = user.get("id")
    if not user_id:
        flash("Please sign in again to continue.", "error")
        return redirect(url_for("login"))
    
    print(f"[SAVED NOTES] user_id: {user_id}")
    raw_boards = get_design_boards_for_user(user_id)
    print(
        f"[DEBUG][SAVED NOTES] get_design_boards_for_user({user_id}) returned: {raw_boards}"
    )

    design_dir = BASE_DIR / "static" / "uploads" / "design_boards"
    design_dir.mkdir(parents=True, exist_ok=True)

    if request.method == "POST":
        action = request.form.get("action") or "create_board"
        print(f"[BOARD POST] Action: {action}")

        # ---------- CREATE BOARD ----------
        if action == "create_board":
            board_name = (request.form.get("board_name") or "").strip()
            vision_statement = (request.form.get("vision_statement") or "").strip()
            board_title = (request.form.get("board_title") or "").strip()
            board_notes = (request.form.get("board_notes") or "").strip()
            board_links = (request.form.get("board_links") or "").strip()

            if not board_name:
                flash("Please give your board a name.", "error")
                return redirect(url_for("homeowner_saved_notes"))

            # Photos
            saved_photos = []
            files = request.files.getlist("board_photos")
            for f in files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                unique_name = f"{uuid4().hex}_{safe_name}"
                save_path = design_dir / unique_name
                try:
                    f.save(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    saved_photos.append(rel_path)
                except Exception:
                    flash("We could not save file. Please try again in a moment.", "error")

            # Fixtures
            saved_fixtures = []
            fixture_files = request.files.getlist("board_fixtures")
            for f in fixture_files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                base_name = Path(safe_name).stem
                unique_name = f"{uuid4().hex}_fixture_{base_name}.png"
                save_path = design_dir / unique_name
                try:
                    f.save(save_path)
                    remove_white_background(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    saved_fixtures.append(rel_path)
                except Exception:
                    flash("We could not save fixture. Please try again in a moment.", "error")

            colors = request.form.getlist("colors[]")
            color_palette = [c for c in colors if c]
            
            # Get estimated_budget and project_status
            estimated_budget = (request.form.get("estimated_budget") or "").strip()
            project_status = (request.form.get("project_status") or "").strip()
            
            # Build details with budget and status if provided
            details_parts = []
            if board_notes:
                details_parts.append(board_notes)
            if estimated_budget:
                details_parts.append(f"\n\nEstimated Budget: ${estimated_budget}")
            if project_status:
                details_parts.append(f"Status: {project_status}")
            if board_links:
                details_parts.append(f"\n\nLinks:\n{board_links}")
            
            combined_details = "\n".join(details_parts) if details_parts else None

            # Validate required fields before attempting to save
            if not board_name or not board_name.strip():
                flash("Please give your board a name.", "error")
                return redirect(url_for("homeowner_saved_notes"))
            
            print(f"[BOARD CREATE] Attempting to create board:")
            print(f"  - user_id: {user_id}")
            print(f"  - board_name: {board_name}")
            print(f"  - title: {board_title}")
            print(f"  - details length: {len(combined_details) if combined_details else 0}")
            print(f"  - photos count: {len(saved_photos)}")
            print(f"  - fixtures count: {len(saved_fixtures)}")
            print(f"  - color_palette: {color_palette}")
            
            try:
                # Ensure we have valid data
                if not user_id:
                    raise ValueError("User ID is missing. Please log in again.")
                if not board_name or not board_name.strip():
                    raise ValueError("Board name is required.")
                
                print(f"[BOARD CREATE] Calling add_design_board_note with:")
                print(f"  user_id={user_id} (type: {type(user_id)})")
                print(f"  project_name='{board_name}'")
                print(f"  title='{board_title}'")
                print(f"  details='{combined_details[:100] if combined_details else None}...'")
                print(f"  photos={len(saved_photos)} items")
                print(f"  fixtures={len(saved_fixtures)} items")
                print(f"  color_palette={color_palette}")
                
                board_id = add_design_board_note(
                    user_id=user_id,
                    project_name=board_name.strip(),
                    title=board_title.strip() if board_title and board_title.strip() else None,
                    tags=None,
                    details=combined_details if combined_details and combined_details.strip() else None,
                    links=None,
                    photos=saved_photos if saved_photos else [],
                    files=[],
                    vision_statement=vision_statement.strip() if vision_statement and vision_statement.strip() else None,
                    color_palette=color_palette if color_palette else [],
                    board_template="collage",
                    label_style="sans-serif",
                    is_private=0,
                    fixtures=saved_fixtures if saved_fixtures else [],
                )
                
                if not board_id:
                    raise ValueError("Board was created but no ID was returned from database.")
                
                print(f"[BOARD CREATE SUCCESS] Board '{board_name}' created with ID {board_id}")
                
                # Verify the board was actually created by querying the database
                from database import list_homeowner_notes
                all_notes = list_homeowner_notes(user_id)
                matching_notes = [n for n in all_notes if n.get('project_name') == board_name or (hasattr(n, 'project_name') and n.project_name == board_name)]
                print(f"[BOARD CREATE VERIFY] Found {len(matching_notes)} notes with project_name='{board_name}'")
                
                verify_boards = get_design_boards_for_user(user_id)
                print(f"[BOARD CREATE VERIFY] All boards for user: {list(verify_boards.keys())}")
                
                if board_name not in verify_boards:
                    print(f"[BOARD CREATE WARNING] Board '{board_name}' not found in get_design_boards_for_user result!")
                    print(f"[BOARD CREATE WARNING] This might be a query issue, but the board should still exist.")
                
                # Force a small delay to ensure database commit is complete
                import time
                time.sleep(0.1)
                
                # Re-query boards to ensure they're fresh
                fresh_boards = get_design_boards_for_user(user_id)
                print(f"[BOARD CREATE] Fresh boards query after creation: {list(fresh_boards.keys())}")
                
                flash(" Beautiful board created!", "success")
                return redirect(url_for("homeowner_saved_notes", view=board_name))
            except ValueError as ve:
                print(f"[BOARD CREATE VALIDATION ERROR] {str(ve)}")
                flash("Something in that form needs another look. Please check it and try again.", "error")
                return redirect(url_for("homeowner_saved_notes"))
            except Exception as e:
                import traceback
                error_trace = traceback.format_exc()
                print(f"[BOARD CREATE ERROR] Failed to create board '{board_name}': {str(e)}")
                print(f"[BOARD CREATE ERROR] Error type: {type(e).__name__}")
                print(error_trace)
                flash("We could not create the board. Please try again in a moment.", "error")
                return redirect(url_for("homeowner_saved_notes"))

        # ---------- EDIT BOARD ----------
        if action == "edit_board":
            board_name = (request.form.get("board_name") or "").strip()
            if not board_name:
                flash("Please give your board a name.", "error")
                return redirect(url_for("homeowner_saved_notes"))

            # Remove photos
            remove_photos_list = request.form.getlist("remove_photos")
            if remove_photos_list:
                try:
                    remove_photos_from_board(user_id, board_name, remove_photos_list)
                    for p in remove_photos_list:
                        try:
                            ppath = BASE_DIR / "static" / p
                            if ppath.exists():
                                ppath.unlink()
                        except Exception:
                            pass
                except Exception:
                    flash("We could not remove some of those photos. Please try again.", "error")

            # Remove fixtures
            remove_fixtures_list = request.form.getlist("remove_fixtures")
            if remove_fixtures_list:
                try:
                    remove_fixtures_from_board(
                        user_id, board_name, remove_fixtures_list
                    )
                    for f in remove_fixtures_list:
                        try:
                            fpath = BASE_DIR / "static" / f
                            if fpath.exists():
                                fpath.unlink()
                        except Exception as file_error:
                            print(f"[FIXTURE REMOVAL] Could not delete file {f}: {file_error}")
                    flash("Fixtures removed!", "success")
                except Exception as e:
                    import traceback
                    print(f"[FIXTURE REMOVAL ERROR] Failed to remove fixtures: {str(e)}")
                    print(traceback.format_exc())
                    flash("We could not remove some fixtures. Please try again in a moment.", "error")

            # New photos
            new_photos = []
            files = request.files.getlist("new_photos")
            for f in files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                unique_name = f"{uuid4().hex}_{safe_name}"
                save_path = (
                    BASE_DIR / "static" / "uploads" / "design_boards" / unique_name
                )
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    f.save(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    new_photos.append(rel_path)
                except Exception:
                    flash("We could not save file. Please try again in a moment.", "error")

            # New fixtures
            new_fixtures = []
            fixture_files = request.files.getlist("new_fixtures")
            for f in fixture_files:
                if not f or not getattr(f, "filename", None):
                    continue
                safe_name = secure_filename(f.filename)
                base_name = Path(safe_name).stem
                unique_name = f"{uuid4().hex}_fixture_{base_name}.png"
                save_path = (
                    BASE_DIR / "static" / "uploads" / "design_boards" / unique_name
                )
                try:
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    f.save(save_path)
                    remove_white_background(save_path)
                    rel_path = str(
                        Path("uploads") / "design_boards" / unique_name
                    ).replace("\\", "/")
                    new_fixtures.append(rel_path)
                except Exception:
                    flash("We could not save fixture. Please try again in a moment.", "error")

            edit_title = (request.form.get("edit_title") or "").strip()
            edit_notes = (request.form.get("edit_notes") or "").strip()

            # New colors
            new_colors = request.form.getlist("new_colors[]")
            if new_colors:
                color_palette = [c for c in new_colors if c]
                try:
                    update_board_colors(user_id, board_name, color_palette)
                except Exception:
                    pass

            if new_photos or new_fixtures or edit_title or edit_notes:
                try:
                    # Get existing photos and fixtures to merge with new ones
                    existing_details_list = get_design_board_details(user_id, board_name)
                    existing_photos = []
                    existing_fixtures = []
                    
                    if existing_details_list and len(existing_details_list) > 0:
                        # Get all photos and fixtures from all notes in this board
                        for detail in existing_details_list:
                            detail_dict = dict(detail) if hasattr(detail, 'keys') else detail
                            
                            # Get existing photos
                            existing_photos_json = detail_dict.get("photos") if isinstance(detail_dict, dict) else detail_dict.get("photos", None)
                            if existing_photos_json:
                                try:
                                    parsed_photos = json.loads(existing_photos_json) if isinstance(existing_photos_json, str) else existing_photos_json
                                    if isinstance(parsed_photos, list):
                                        existing_photos.extend(parsed_photos)
                                except Exception:
                                    pass
                            
                            # Get existing fixtures
                            existing_fixtures_json = detail_dict.get("fixtures") if isinstance(detail_dict, dict) else detail_dict.get("fixtures", None)
                            if existing_fixtures_json:
                                try:
                                    parsed_fixtures = json.loads(existing_fixtures_json) if isinstance(existing_fixtures_json, str) else existing_fixtures_json
                                    if isinstance(parsed_fixtures, list):
                                        existing_fixtures.extend(parsed_fixtures)
                                except Exception:
                                    pass
                    
                    # Merge existing with new (remove duplicates)
                    all_photos = list(dict.fromkeys(existing_photos + new_photos))  # Preserves order, removes duplicates
                    all_fixtures = list(dict.fromkeys(existing_fixtures + new_fixtures))
                    
                    # Add new note with merged photos and fixtures
                    add_design_board_note(
                        user_id=user_id,
                        project_name=board_name,
                        title=edit_title,
                        details=edit_notes,
                        photos=all_photos,
                        files=[],
                        fixtures=all_fixtures,
                    )
                    flash("Board updated!", "success")
                    # Redirect to board detail page if we're coming from there
                    if request.referrer and '/design-boards/' in request.referrer:
                        return redirect(url_for('homeowner_design_board_view', board_name=board_name))
                    return redirect(url_for("homeowner_saved_notes", view=board_name))
                except Exception as e:
                    import traceback
                    print(f"[BOARD EDIT ERROR] Failed to update board: {str(e)}")
                    print(traceback.format_exc())
                    flash("We could not update board. Please try again in a moment.", "error")
                    # Redirect to board detail page if we're coming from there
                    if request.referrer and '/design-boards/' in request.referrer:
                        return redirect(url_for('homeowner_design_board_view', board_name=board_name))

            return redirect(url_for("homeowner_saved_notes", view=board_name))

        # ---------- DELETE BOARD ----------
        if action == "delete_board":
            board_name = (request.form.get("board_name") or "").strip()
            print(f"[BOARD DELETE] Attempting to delete board: '{board_name}' for user {user_id}")
            if not board_name:
                flash("Please tell us which board to delete.", "error")
                return redirect(url_for("homeowner_saved_notes"))
            
            try:
                # Get board details to delete associated files
                details_list = get_design_board_details(user_id, board_name)
                if details_list and len(details_list) > 0:
                    details = details_list[0]  # Get first detail record
                    
                    # Convert sqlite3.Row to dict (sqlite3.Row doesn't have .get() method)
                    details_dict = dict(details)
                    
                    # Delete photos
                    photos = details_dict.get("photos")
                    if photos:
                        try:
                            photos_list = json.loads(photos) if isinstance(photos, str) else photos
                            if isinstance(photos_list, list):
                                for photo in photos_list:
                                    try:
                                        file_path = BASE_DIR / "static" / photo
                                        if file_path.exists():
                                            file_path.unlink()
                                            print(f"[BOARD DELETE] Deleted photo: {photo}")
                                    except Exception as e:
                                        print(f"[BOARD DELETE] Error deleting photo {photo}: {e}")
                        except Exception as e:
                            print(f"[BOARD DELETE] Error parsing photos: {e}")
                    
                    # Delete fixtures
                    fixtures = details_dict.get("fixtures")
                    if fixtures:
                        try:
                            fixtures_list = json.loads(fixtures) if isinstance(fixtures, str) else fixtures
                            if isinstance(fixtures_list, list):
                                for fixture in fixtures_list:
                                    try:
                                        file_path = BASE_DIR / "static" / fixture
                                        if file_path.exists():
                                            file_path.unlink()
                                            print(f"[BOARD DELETE] Deleted fixture: {fixture}")
                                    except Exception as e:
                                        print(f"[BOARD DELETE] Error deleting fixture {fixture}: {e}")
                        except Exception as e:
                            print(f"[BOARD DELETE] Error parsing fixtures: {e}")
                
                # Delete from database
                    delete_design_board(user_id, board_name)
                print(f"[BOARD DELETE] Successfully deleted board '{board_name}' from database")
                flash("Board deleted.", "success")
            except Exception as e:
                import traceback
                print(f"[BOARD DELETE ERROR] Failed to delete board '{board_name}': {str(e)}")
                print(traceback.format_exc())
                flash("We could not delete that board. Please try again in a moment.", "error")

            return redirect(url_for("homeowner_saved_notes"))

    # ---------- GET: LIST & VIEW BOARDS ----------
    raw_boards_dict = get_design_boards_for_user(user_id) or {}
    # Convert dict to list of board names for template iteration
    boards = list(raw_boards_dict.keys()) if raw_boards_dict else []
    _dbg(f"[DEBUG][SAVED NOTES] Raw boards dict: {raw_boards_dict}")
    _dbg(f"[DEBUG][SAVED NOTES] Boards list: {boards}")
    
    board_details = {}
    for board_name in boards:
        try:
            details = get_design_board_details(user_id, board_name)
            if details:
                # Convert Row objects to dicts if needed
                if isinstance(details, list) and len(details) > 0:
                    first_detail = details[0]
                    if hasattr(first_detail, 'keys'):
                        board_details[board_name] = {
                            "project_name": board_name,
                            "photos": json.loads(first_detail.get('photos', '[]') or '[]') if first_detail.get('photos') else [],
                            "notes": [first_detail.get('details', '')] if first_detail.get('details') else [],
                            "files": json.loads(first_detail.get('files', '[]') or '[]') if first_detail.get('files') else [],
                            "color_palette": json.loads(first_detail.get('color_palette', '[]') or '[]') if first_detail.get('color_palette') else [],
                            "vision_statement": first_detail.get('vision_statement', ''),
                            "title": first_detail.get('title', ''),
                        }
                    else:
                        board_details[board_name] = {
                            "project_name": board_name,
                "photos": [],
                "notes": [],
                "files": [],
            }
                else:
                    board_details[board_name] = {
                        "project_name": board_name,
                        "photos": [],
                        "notes": [],
                        "files": [],
                    }
            else:
                board_details[board_name] = {
                    "project_name": board_name,
                    "photos": [],
                    "notes": [],
                    "files": [],
                }
        except Exception as e:
            _dbg(f"[DEBUG][SAVED NOTES] Error getting details for board '{board_name}': {e}")
            import traceback
            print(traceback.format_exc())
            board_details[board_name] = {
                "project_name": board_name,
                "photos": [],
                "notes": [],
                "files": [],
            }

    selected_board = request.args.get("view")
    selected_details = board_details.get(selected_board) if selected_board else None

    return render_template(
        "homeowner/saved_notes.html",
        brand_name=FRONT_BRAND_NAME,
        boards=boards,
        board_details=board_details,
        selected_board=selected_board,
        selected_details=selected_details,
    )


@route("/homeowner/design-boards/<path:board_name>", methods=["GET"])
def homeowner_design_board_view(board_name):
    """Display a dedicated detail page for a single design board."""
    user_id = get_current_user_id()
    details_list = get_design_board_details(user_id, board_name)

    if not details_list:
        flash("That board could not be found.", "error")
        return redirect(url_for("homeowner_saved_notes"))

    # Aggregate all photos, fixtures, and other data from all notes in this board
    all_photos = []
    all_fixtures = []
    all_files = []
    color_palette = []
    vision_statement = None
    title = None
    details_text = []
    
    for detail in details_list:
        detail_dict = dict(detail) if hasattr(detail, 'keys') else detail
        
        # Collect photos from all notes
        photos_json = detail_dict.get('photos') or '[]'
        if photos_json:
            try:
                photos = json.loads(photos_json) if isinstance(photos_json, str) else photos_json
                if isinstance(photos, list):
                    all_photos.extend(photos)
            except Exception:
                pass
        
        # Collect fixtures from all notes
        fixtures_json = detail_dict.get('fixtures') or '[]'
        if fixtures_json:
            try:
                fixtures = json.loads(fixtures_json) if isinstance(fixtures_json, str) else fixtures_json
                if isinstance(fixtures, list):
                    all_fixtures.extend(fixtures)
            except Exception:
                pass
        
        # Collect files
        files_json = detail_dict.get('files') or '[]'
        if files_json:
            try:
                files = json.loads(files_json) if isinstance(files_json, str) else files_json
                if isinstance(files, list):
                    all_files.extend(files)
            except Exception:
                pass
        
        # Get color palette (from most recent note)
        color_palette_json = detail_dict.get('color_palette') or '[]'
        if color_palette_json and not color_palette:
            try:
                color_palette = json.loads(color_palette_json) if isinstance(color_palette_json, str) else color_palette_json
            except Exception:
                pass
        
        # Get vision statement (from most recent note)
        if not vision_statement and detail_dict.get('vision_statement'):
            vision_statement = detail_dict.get('vision_statement')
        
        # Get title (from most recent note)
        if not title and detail_dict.get('title'):
            title = detail_dict.get('title')
        
        # Collect details text (only unique, non-empty details)
        if detail_dict.get('details'):
            detail_text = detail_dict.get('details').strip()
            if detail_text and detail_text not in details_text:
                details_text.append(detail_text)
    
    # Remove duplicates while preserving order
    all_photos = list(dict.fromkeys(all_photos))
    all_fixtures = list(dict.fromkeys(all_fixtures))
    all_files = list(dict.fromkeys(all_files))
    
    # Combine all unique details with newlines for readability
    combined_details = '\n\n'.join(details_text) if details_text else None
    
    # Create aggregated details dict for template
    aggregated_details = {
        'photos': all_photos,
        'fixtures': all_fixtures,
        'files': all_files,
        'color_palette': color_palette if isinstance(color_palette, list) else [],
        'vision_statement': vision_statement,
        'title': title,
        'details': combined_details,
    }
    
    # Prepare individual notes with IDs for edit/delete functionality
    notes_list = []
    for detail in details_list:
        detail_dict = dict(detail) if hasattr(detail, 'keys') else detail
        note_data = {
            'id': detail_dict.get('id'),
            'title': detail_dict.get('title'),
            'details': detail_dict.get('details'),
            'created_at': detail_dict.get('created_at'),
        }
        if note_data['id'] and (note_data['title'] or note_data['details']):
            notes_list.append(note_data)

    return render_template(
        "homeowner/board_detail.html",
        selected_board=board_name,
        selected_details=aggregated_details,
        notes_list=notes_list,
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/design-boards/<path:board_name>/download")
def homeowner_design_board_download(board_name):
    """Render a print-optimized view of a single board."""
    user_id = get_current_user_id()
    details_list = get_design_board_details(user_id, board_name)
    if not details_list:
        flash("That board could not be found.", "error")
        return redirect(url_for("homeowner_saved_notes"))

    # Aggregate all photos, fixtures, and other data from all notes in this board
    # (same logic as homeowner_design_board_view)
    all_photos = []
    all_fixtures = []
    all_files = []
    color_palette = []
    vision_statement = None
    title = None
    details_text = []
    
    for detail in details_list:
        detail_dict = dict(detail) if hasattr(detail, 'keys') else detail
        
        # Collect photos from all notes
        photos_json = detail_dict.get('photos') or '[]'
        if photos_json:
            try:
                photos = json.loads(photos_json) if isinstance(photos_json, str) else photos_json
                if isinstance(photos, list):
                    all_photos.extend(photos)
            except Exception:
                pass
        
        # Collect fixtures from all notes
        fixtures_json = detail_dict.get('fixtures') or '[]'
        if fixtures_json:
            try:
                fixtures = json.loads(fixtures_json) if isinstance(fixtures_json, str) else fixtures_json
                if isinstance(fixtures, list):
                    all_fixtures.extend(fixtures)
            except Exception:
                pass
        
        # Collect files
        files_json = detail_dict.get('files') or '[]'
        if files_json:
            try:
                files = json.loads(files_json) if isinstance(files_json, str) else files_json
                if isinstance(files, list):
                    all_files.extend(files)
            except Exception:
                pass
        
        # Get color palette (from most recent note)
        color_palette_json = detail_dict.get('color_palette') or '[]'
        if color_palette_json and not color_palette:
            try:
                color_palette = json.loads(color_palette_json) if isinstance(color_palette_json, str) else color_palette_json
            except Exception:
                pass
        
        # Get vision statement (from most recent note)
        if not vision_statement and detail_dict.get('vision_statement'):
            vision_statement = detail_dict.get('vision_statement')
        
        # Get title (from most recent note)
        if not title and detail_dict.get('title'):
            title = detail_dict.get('title')
        
        # Collect details text (only unique, non-empty details)
        if detail_dict.get('details'):
            detail_text = detail_dict.get('details').strip()
            if detail_text and detail_text not in details_text:
                details_text.append(detail_text)
    
    # Remove duplicates while preserving order
    all_photos = list(dict.fromkeys(all_photos))
    all_fixtures = list(dict.fromkeys(all_fixtures))
    all_files = list(dict.fromkeys(all_files))
    
    # Combine all unique details with newlines for readability
    combined_details = '\n\n'.join(details_text) if details_text else None
    
    # Create aggregated details dict for template
    aggregated_details = {
        'photos': all_photos,
        'fixtures': all_fixtures,
        'files': all_files,
        'color_palette': color_palette if isinstance(color_palette, list) else [],
        'vision_statement': vision_statement,
        'title': title,
        'details': combined_details,
        'notes': details_list,  # Include raw notes for the template
    }

    html = render_template(
        "homeowner/board_print.html",
        selected_board=board_name,
        selected_details=aggregated_details,
        brand_name=FRONT_BRAND_NAME,
    )

    try:
        from weasyprint import HTML

        pdf = HTML(string=html, base_url=str(BASE_DIR / "static")).write_pdf()
        safe_filename = board_name.replace("/", "_")
        return Response(
            pdf,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_filename}.pdf"'
            },
        )
    except ImportError:
        # WeasyPrint not installed - return HTML as fallback
        return html
    except Exception as e:
        # PDF generation failed - log error and return HTML
        import traceback
        print(f"[PDF DOWNLOAD ERROR] Failed to generate PDF: {str(e)}")
        print(traceback.format_exc())
        return html


@route("/homeowner/design-boards/<path:board_name>/duplicate", methods=["POST"])
def homeowner_design_board_duplicate(board_name):
    """Duplicate an existing board with a new name."""
    user_id = get_current_user_id()
    new_name = request.form.get("new_name", f"{board_name} (Copy)").strip()

    if not new_name:
        flash("Please give the new board a name.", "error")
        return redirect(url_for("homeowner_design_board_view", board_name=board_name))

    try:
        duplicate_design_board(user_id, board_name, new_name)
        flash(f" Board duplicated as '{new_name}'!", "success")
        return redirect(url_for("homeowner_design_board_view", board_name=new_name))
    except Exception:
        flash("We could not duplicate that board. Please try again.", "error")
        return redirect(url_for("homeowner_design_board_view", board_name=board_name))


@route("/homeowner/design-boards/<path:board_name>/privacy", methods=["POST"])
def homeowner_design_board_privacy(board_name):
    """Toggle privacy settings for a board."""
    user_id = get_current_user_id()
    is_private = int(request.form.get("is_private", 0))

    shareable_link = None
    if not is_private:
        shareable_link = secrets.token_urlsafe(16)

    try:
        update_board_privacy(user_id, board_name, is_private, shareable_link)
        status = "private" if is_private else "shareable"
        flash(f"Board is now {status}.", "success")
    except Exception:
        flash("We could not update the privacy setting. Please try again.", "error")

    return redirect(url_for("homeowner_design_board_view", board_name=board_name))


@route("/homeowner/design-boards/<path:board_name>/template", methods=["POST"])
def homeowner_design_board_template(board_name):
    """Change the board template style."""
    user_id = get_current_user_id()
    template = request.form.get("template", "collage")

    if template not in ["collage", "grid", "editorial"]:
        template = "collage"

    try:
        update_board_template(user_id, board_name, template)
        flash(f"Board template changed to {template}.", "success")
    except Exception:
        flash("We could not update the template. Please try again.", "error")

    return redirect(url_for("homeowner_design_board_view", board_name=board_name))


@route("/homeowner/crop-photo", methods=["POST"])
def homeowner_crop_photo():
    """Crop a photo and replace the original."""
    try:
        user_id = get_current_user_id()
        board_name = request.form.get("board_name")
        original_path = request.form.get("original_path")
        cropped_file = request.files.get("cropped_image")

        if not all([board_name, original_path, cropped_file]):
            return jsonify({"success": False, "error": "Missing data"})

        # Verify user owns this board and photo exists
        details_list = get_design_board_details(user_id, board_name)
        if not details_list:
            return jsonify({"success": False, "error": "Board not found"})
        
        # Check if photo exists in any note in the board
        photo_found = False
        for detail in details_list:
            detail_dict = dict(detail) if hasattr(detail, 'keys') else detail
            photos_json = detail_dict.get('photos') or '[]'
            try:
                photos = json.loads(photos_json) if isinstance(photos_json, str) else photos_json
                if isinstance(photos, list) and original_path in photos:
                    photo_found = True
                    break
            except Exception:
                pass
        
        if not photo_found:
            return jsonify({"success": False, "error": "Photo not found in board"})

        # Save cropped image over original
        file_path = BASE_DIR / "static" / original_path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        cropped_file.save(file_path)

        return jsonify({"success": True})
    except Exception as e:
        import traceback
        print(f"Crop error: {e}")
        print(traceback.format_exc())
        return jsonify({"success": False, "error": str(e)})


@route("/homeowner/home-timeline", methods=["GET", "POST"])
def homeowner_home_timeline():
    user_id = get_current_user_id()

    if request.method == "POST":
        title = request.form.get("title")
        category = request.form.get("category")
        event_date = request.form.get("event_date")
        cost = request.form.get("cost")
        notes = request.form.get("notes")
        files = request.files.getlist("files")

        saved_files = []
        for f in files:
            if f.filename:
                filename = secure_filename(f.filename)
                filepath = UPLOAD_TIMELINE / filename
                f.save(filepath)
                saved_files.append(filename)

        add_timeline_event(user_id, event_date, title, category, cost, notes, saved_files)
        return redirect(url_for("homeowner_home_timeline"))

    events = list_timeline_events(user_id)
    return render_template(
        "homeowner/home_timeline.html",
        brand_name=FRONT_BRAND_NAME,
        events=events,
    )


@route("/homeowner/home-timeline/delete/<int:event_id>")
def homeowner_timeline_delete(event_id):
    delete_timeline_event(event_id, get_current_user_id())
    return redirect(url_for("homeowner_home_timeline"))


@route("/homeowner/home-timeline/print")
def homeowner_timeline_print():
    events = list_timeline_events(get_current_user_id())
    return render_template(
        "homeowner/home_timeline_print.html",
        brand_name=FRONT_BRAND_NAME,
        events=events,
    )


@route("/homeowner/documents/<int:doc_id>/view")
def homeowner_document_view(doc_id):
    user_id = get_current_user_id()
    row = get_homeowner_document_for_user(doc_id, user_id)
    if not row:
        flash("That document could not be found.", "error")
        return redirect(url_for("homeowner_upload_documents"))

    # If file is in R2, redirect to R2 URL
    if row.get("r2_key"):
        try:
            file_url = get_file_url_from_r2(row["r2_key"])
            return redirect(file_url)
        except Exception as e:
            flash("We could not retrieve file. Please try again in a moment.", "error")
            return redirect(url_for("homeowner_upload_documents"))

    # Fallback to local file
    return send_from_directory(
        HOMEOWNER_DOCS_DIR, row["file_name"], as_attachment=False
    )


@route("/homeowner/documents/<int:doc_id>/replace", methods=["GET", "POST"])
def homeowner_document_replace(doc_id):
    user_id = get_current_user_id()
    row = get_homeowner_document_for_user(doc_id, user_id)
    if not row:
        flash("That document could not be found.", "error")
        return redirect(url_for("homeowner_upload_documents"))

    if request.method == "POST":
        file = request.files.get("file")
        if not file or file.filename == "":
            flash("Please choose a file to upload.", "error")
            return redirect(request.url)

        safe_name = secure_filename(file.filename)
        save_path = HOMEOWNER_DOCS_DIR / safe_name
        HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        file.save(save_path)

        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE homeowner_documents
            SET file_name = ?, uploaded_at = ?
            WHERE id = ? AND user_id = ?
            """,
            (
                safe_name,
                datetime.utcnow().isoformat(sep=" ", timespec="seconds"),
                doc_id,
                user_id,
            ),
        )
        conn.commit()
        conn.close()

        flash("Document updated.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    return render_template(
        "homeowner/document_replace.html",
        document=row,
    )


@route("/homeowner/upload-documents", methods=["GET", "POST"])
def homeowner_upload_documents():
    user_id = get_current_user_id()
    docs = list_homeowner_documents(user_id)
    events = list_timeline_events(user_id)

    # DELETE FILE
    if request.method == "POST" and request.form.get("delete_id"):
        delete_id = request.form["delete_id"]
        delete_homeowner_document(delete_id)
        flash("Document removed.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    # REATTACH / REUPLOAD
    if (
        request.method == "POST"
        and request.form.get("reattach_id")
        and request.files.get("file")
    ):
        doc_id = request.form["reattach_id"]
        new_file = request.files["file"]
        save_name = secure_filename(new_file.filename)
        HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        new_file.save(HOMEOWNER_DOCS_DIR / save_name)
        update_homeowner_document_file(doc_id, save_name)
        flash("File updated.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    # NORMAL UPLOAD
    if request.method == "POST" and request.files.get("file"):
        file = request.files["file"]
        category = request.form.get("category", "Other")
        title = request.form.get("title", "").strip() or file.filename

        if not file or file.filename == "":
            flash("Please choose a file to upload.", "error")
            return redirect(url_for("homeowner_upload_documents"))

        filename = secure_filename(file.filename)

        # If using R2, upload there; else save locally
        if is_r2_enabled() and R2_CLIENT:
            r2_key = f"homeowner_docs/{user_id}/{uuid4().hex}_{filename}"
            upload_file_to_r2(file, r2_key)
            stored_name = filename  # For DB reference, still keep original name
        else:
            HOMEOWNER_DOCS_DIR.mkdir(parents=True, exist_ok=True)
            save_path = HOMEOWNER_DOCS_DIR / filename
            file.save(save_path)
            r2_key = None
            stored_name = filename

        add_homeowner_document(
            user_id=user_id,
            name=title,
            category=category,
            file_path=stored_name,
            r2_key=r2_key,
        )
        flash("Document uploaded.", "success")
        return redirect(url_for("homeowner_upload_documents"))

    return render_template(
        "homeowner/upload_documents.html",
        brand_name=FRONT_BRAND_NAME,
        documents=docs,
        events=events,
    )


@route("/homeowner/value/equity-overview", methods=["GET", "POST"])
def homeowner_value_equity_overview():
    """Homebot-powered equity page - shows Homebot widget if agent/lender has configured it."""
    from database import get_homeowner_professionals, get_user_profile, get_user_by_id
    
    user = get_current_user()
    if not user:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for("login"))
    
    if user.get("role") != "homeowner":
        flash("That page is made for homeowners.", "error")
        return redirect(url_for("agent_dashboard" if user.get("role") == "agent" else "lender_dashboard"))
    
    homeowner_id = user["id"]
    
    # Handle POST requests for updating loan details
    if request.method == "POST":
        print(f"\n{'='*60}")
        print(f"[LOAN UPDATE] POST request received for user {homeowner_id}")
        print(f"[LOAN UPDATE] Form data keys: {list(request.form.keys())}")
        for key, value in request.form.items():
            print(f"  {key}: {value}")
        print(f"{'='*60}\n")
        from database import get_primary_property, upsert_homeowner_snapshot_for_property
        
        # Get property ID
        primary_property = get_primary_property(homeowner_id)
        if not primary_property:
            flash("Please add your home first, then we can add your loan details.", "error")
            return redirect(url_for("homeowner_value_equity_overview"))
        
        property_id = primary_property.get('id')
        
        # Parse form data - only update fields that are actually provided (not empty)
        def safe_float(val):
            if not val or val == "":
                return None
            try:
                return float(str(val).replace(",", "").replace("$", ""))
            except (ValueError, TypeError):
                return None
        
        # Get form values - only update fields that have actual values (not empty)
        # Empty form fields should preserve existing data
        def get_form_value(field_name):
            val = request.form.get(field_name, "").strip()
            return val if val else None
        
        form_value_estimate = get_form_value("value_estimate")
        form_loan_balance = get_form_value("loan_balance")
        form_loan_rate = get_form_value("loan_rate")
        form_loan_payment = get_form_value("loan_payment")
        form_loan_term_years = get_form_value("loan_term_years")
        form_loan_start_date = get_form_value("loan_start_date")
        form_property_tax = get_form_value("property_tax_monthly")
        form_insurance = get_form_value("homeowners_insurance_monthly")
        form_pmi = get_form_value("pmi_monthly")
        
        # Convert to appropriate types, but only if value was provided
        # If None, the function will preserve existing data
        value_estimate = safe_float(form_value_estimate) if form_value_estimate else None
        loan_balance = safe_float(form_loan_balance) if form_loan_balance else None
        loan_rate = safe_float(form_loan_rate) if form_loan_rate else None
        loan_payment = safe_float(form_loan_payment) if form_loan_payment else None
        loan_term_years = safe_float(form_loan_term_years) if form_loan_term_years else None
        loan_start_date = form_loan_start_date if form_loan_start_date else None
        property_tax_monthly = safe_float(form_property_tax) if form_property_tax else None
        homeowners_insurance_monthly = safe_float(form_insurance) if form_insurance else None
        pmi_monthly = safe_float(form_pmi) if form_pmi else None
        
        # Update snapshot - function will preserve existing data for None values
        try:
            print(f"[LOAN UPDATE] Updating snapshot for user {homeowner_id}, property {property_id}")
            
            upsert_homeowner_snapshot_for_property(
                user_id=homeowner_id,
                property_id=property_id,
                value_estimate=value_estimate,
                loan_balance=loan_balance,
                loan_rate=loan_rate,
                loan_payment=loan_payment,
                loan_term_years=loan_term_years,
                loan_start_date=loan_start_date,
                property_tax_monthly=property_tax_monthly,
                homeowners_insurance_monthly=homeowners_insurance_monthly,
                pmi_monthly=pmi_monthly,
            )
            
            print(f"[LOAN UPDATE] Successfully updated snapshot")
            flash("Loan details updated! Your equity numbers have been recalculated.", "success")
            return redirect(url_for("homeowner_value_equity_overview"))
        except Exception as e:
            import traceback
            error_trace = traceback.format_exc()
            print(f"[LOAN UPDATE] ERROR: {str(e)}")
            print(error_trace)
            flash("We could not update your loan details. Please try again in a moment.", "error")
            # Continue to render the form so user can see the error
    
    # Get homeowner's professionals (agents and lenders)
    professionals = get_homeowner_professionals(homeowner_id)
    
    # Get market rates from lender (precedence) or agent, with defaults
    market_rates = {
        'va_rate_30yr': 6.1,
        'fha_rate_30yr': 6.1,
        'conventional_rate_30yr': 6.1
    }
    lender_profile = None
    agent_profile = None
    
    # Find lender first (lender takes precedence)
    for prof in professionals:
        prof_dict = dict(prof) if hasattr(prof, 'keys') else prof
        prof_id = prof_dict.get('professional_id') or prof_dict.get('user_id')
        prof_role = prof_dict.get('professional_role') or prof_dict.get('professional_type')
        if prof_id and prof_role == 'lender':
            lender_profile = get_user_profile(prof_id)
            if lender_profile:
                lender_dict = dict(lender_profile) if hasattr(lender_profile, 'keys') else lender_profile
                if lender_dict.get('va_rate_30yr'):
                    market_rates['va_rate_30yr'] = float(lender_dict.get('va_rate_30yr'))
                if lender_dict.get('fha_rate_30yr'):
                    market_rates['fha_rate_30yr'] = float(lender_dict.get('fha_rate_30yr'))
                if lender_dict.get('conventional_rate_30yr'):
                    market_rates['conventional_rate_30yr'] = float(lender_dict.get('conventional_rate_30yr'))
                break
    
    # If no lender rates, check agent
    if not lender_profile or (market_rates['va_rate_30yr'] == 6.1 and market_rates['fha_rate_30yr'] == 6.1 and market_rates['conventional_rate_30yr'] == 6.1):
        for prof in professionals:
            prof_dict = dict(prof) if hasattr(prof, 'keys') else prof
            prof_id = prof_dict.get('professional_id') or prof_dict.get('user_id')
            prof_role = prof_dict.get('professional_role') or prof_dict.get('professional_type')
            if prof_id and prof_role == 'agent':
                agent_profile = get_user_profile(prof_id)
                if agent_profile:
                    agent_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') else agent_profile
                    # Only use agent rates if lender rates weren't set
                    if not lender_profile:
                        if agent_dict.get('va_rate_30yr'):
                            market_rates['va_rate_30yr'] = float(agent_dict.get('va_rate_30yr'))
                        if agent_dict.get('fha_rate_30yr'):
                            market_rates['fha_rate_30yr'] = float(agent_dict.get('fha_rate_30yr'))
                        if agent_dict.get('conventional_rate_30yr'):
                            market_rates['conventional_rate_30yr'] = float(agent_dict.get('conventional_rate_30yr'))
                    break
    
    # Find the first professional (agent preferred, then lender) with a Homebot widget ID
    homebot_widget_id = None
    professional_info = None
    
    # Prefer agent over lender
    for prof in professionals:
        prof_dict = dict(prof) if hasattr(prof, 'keys') else prof
        prof_id = prof_dict.get('professional_id') or prof_dict.get('user_id')
        if prof_id:
            profile = get_user_profile(prof_id)
            if profile:
                profile_dict = dict(profile) if hasattr(profile, 'keys') else profile
                widget_id = profile_dict.get('homebot_widget_id')
                if widget_id:
                    # Clean the widget ID - remove any whitespace
                    widget_id = str(widget_id).strip()
                    # If widget_id contains HTML/embed code, extract just the ID
                    if '<' in widget_id or 'Homebot(' in widget_id:
                        # Try to extract the ID from embed code
                        import re
                        id_match = re.search(r"['\"]([a-f0-9]{40,})['\"]", widget_id)
                        if id_match:
                            widget_id = id_match.group(1)
                            print(f"[HOMEBOT] Extracted widget ID from embed code: {widget_id[:20]}...")
                    if widget_id:
                        homebot_widget_id = widget_id
                    professional_info = {
                        'name': prof_dict.get('name') or profile_dict.get('name'),
                        'email': prof_dict.get('email'),
                        'role': prof_dict.get('professional_role') or 'agent',
                        'brokerage_name': profile_dict.get('brokerage_name'),
                        'team_name': profile_dict.get('team_name'),
                        'professional_photo': profile_dict.get('professional_photo'),
                    }
                    # Prefer agent, so if we found an agent, break
                    if prof_dict.get('professional_role') == 'agent' or prof_dict.get('professional_type') == 'agent':
                        break
    
    # Fallback: check agent_id/lender_id columns if no professionals found
    if not homebot_widget_id:
        homeowner_user = get_user_by_id(homeowner_id)
        if homeowner_user:
            homeowner_dict = dict(homeowner_user) if hasattr(homeowner_user, 'keys') else homeowner_user
            # Try agent first
            agent_id = homeowner_dict.get("agent_id")
            if agent_id:
                agent_profile = get_user_profile(agent_id)
                if agent_profile:
                    profile_dict = dict(agent_profile) if hasattr(agent_profile, 'keys') else agent_profile
                    widget_id = profile_dict.get('homebot_widget_id')
                    if widget_id:
                        # Clean the widget ID - remove any whitespace
                        widget_id = str(widget_id).strip()
                        # If widget_id contains HTML/embed code, extract just the ID
                        if '<' in widget_id or 'Homebot(' in widget_id:
                            # Try to extract the ID from embed code
                            import re
                            id_match = re.search(r"['\"]([a-f0-9]{40,})['\"]", widget_id)
                            if id_match:
                                widget_id = id_match.group(1)
                                print(f"[HOMEBOT] Extracted widget ID from embed code: {widget_id[:20]}...")
                        if widget_id:
                            homebot_widget_id = widget_id
                        agent_user = get_user_by_id(agent_id)
                        if agent_user:
                            agent_dict = dict(agent_user) if hasattr(agent_user, 'keys') else agent_user
                            professional_info = {
                                'name': agent_dict.get('name'),
                                'email': agent_dict.get('email'),
                                'role': 'agent',
                                'brokerage_name': profile_dict.get('brokerage_name'),
                                'team_name': profile_dict.get('team_name'),
                                'professional_photo': profile_dict.get('professional_photo'),
                            }
            # Try lender if no agent
            if not homebot_widget_id:
                lender_id = homeowner_dict.get("lender_id")
                if lender_id:
                    lender_profile = get_user_profile(lender_id)
                    if lender_profile:
                        profile_dict = dict(lender_profile) if hasattr(lender_profile, 'keys') else lender_profile
                        widget_id = profile_dict.get('homebot_widget_id')
                        if widget_id:
                            # Clean the widget ID - remove any whitespace
                            widget_id = str(widget_id).strip()
                            # If widget_id contains HTML/embed code, extract just the ID
                            if '<' in widget_id or 'Homebot(' in widget_id:
                                # Try to extract the ID from embed code
                                import re
                                id_match = re.search(r"['\"]([a-f0-9]{40,})['\"]", widget_id)
                                if id_match:
                                    widget_id = id_match.group(1)
                                    print(f"[HOMEBOT] Extracted widget ID from embed code: {widget_id[:20]}...")
                            if widget_id:
                                homebot_widget_id = widget_id
                            lender_user = get_user_by_id(lender_id)
                            if lender_user:
                                lender_dict = dict(lender_user) if hasattr(lender_user, 'keys') else lender_user
                                professional_info = {
                                    'name': lender_dict.get('name'),
                                    'email': lender_dict.get('email'),
                                    'role': 'lender',
                                    'brokerage_name': profile_dict.get('brokerage_name'),
                                    'team_name': profile_dict.get('team_name'),
                                    'professional_photo': profile_dict.get('professional_photo'),
                                }

    # Get homeowner's email and property address to pass to Homebot widget
    homeowner_data = {}
    homeowner_user = get_user_by_id(homeowner_id)
    if homeowner_user:
        homeowner_dict = dict(homeowner_user) if hasattr(homeowner_user, 'keys') else homeowner_user
        homeowner_email = homeowner_dict.get('email')
        if homeowner_email:
            homeowner_data['email'] = homeowner_email
        
        # Get primary property address, or first property if no primary
        from database import get_primary_property, get_user_properties
        primary_property = get_primary_property(homeowner_id)
        if primary_property and primary_property.get('address'):
            homeowner_data['address'] = primary_property.get('address')
        else:
            # Fallback to first property if no primary
            all_properties = get_user_properties(homeowner_id)
            if all_properties and len(all_properties) > 0 and all_properties[0].get('address'):
                homeowner_data['address'] = all_properties[0].get('address')
    
    # Get all properties and current property
    from database import get_primary_property, get_homeowner_snapshot_for_property, get_snapshot_history, get_user_properties, get_property_by_id
    all_properties = get_user_properties(homeowner_id)
    primary_property = get_primary_property(homeowner_id)
    
    # If no properties exist, create a default one
    if not all_properties or len(all_properties) == 0:
        if not primary_property:
            # Create default property
            default_address = homeowner_data.get('address', 'My Home') if homeowner_data else 'My Home'
            property_id = add_property(homeowner_id, default_address, None, "primary")
            primary_property = get_property_by_id(property_id)
            all_properties = get_user_properties(homeowner_id)
    
    # Get current property - ensure it's a dict
    current_property = None
    if primary_property:
        current_property = dict(primary_property) if hasattr(primary_property, 'keys') and not isinstance(primary_property, dict) else primary_property
    elif all_properties and len(all_properties) > 0:
        first_prop = all_properties[0]
        current_property = dict(first_prop) if hasattr(first_prop, 'keys') and not isinstance(first_prop, dict) else first_prop
    
    # Get current property ID safely
    current_property_id = None
    if current_property:
        if isinstance(current_property, dict):
            current_property_id = current_property.get('id')
        elif hasattr(current_property, 'get'):
            current_property_id = current_property.get('id')
        elif hasattr(current_property, 'id'):
            current_property_id = current_property.id
    
    # Get homeowner snapshot data (synced from Homebot webhook)
    snapshot_data = None
    snapshot_history = []
    if current_property_id:
        try:
            snapshot_data = get_homeowner_snapshot_for_property(homeowner_id, current_property_id)
            # Convert to dict if it's a Row object
            if snapshot_data and hasattr(snapshot_data, 'keys') and not isinstance(snapshot_data, dict):
                snapshot_data = dict(snapshot_data)
            # Calculate equity if we have value and loan balance
            if snapshot_data and snapshot_data.get('value_estimate') and snapshot_data.get('loan_balance'):
                snapshot_data['equity_estimate'] = snapshot_data.get('value_estimate') - snapshot_data.get('loan_balance')
            # Get historical snapshots
            try:
                snapshot_history = get_snapshot_history(homeowner_id, current_property_id, limit=24)
            except Exception as e:
                print(f"[HOMEBOT] Error getting snapshot history: {e}")
                snapshot_history = []
        except Exception as e:
            print(f"[HOMEBOT] Error getting snapshot data: {e}")
            import traceback
            print(traceback.format_exc())
            snapshot_data = None
            snapshot_history = []

    # Debug logging
    print(f"[HOMEBOT] Widget ID found: {homebot_widget_id is not None}")
    if homebot_widget_id:
        print(f"[HOMEBOT] Widget ID value: {homebot_widget_id[:20]}... (length: {len(homebot_widget_id)})")
    print(f"[HOMEBOT] Professional Info: {professional_info}")
    print(f"[HOMEBOT] Homeowner Data: {homeowner_data}")
    print(f"[HOMEBOT] Snapshot Data: {snapshot_data}")
    print(f"[HOMEBOT] Properties: {len(all_properties) if all_properties else 0} total, current: {current_property_id}")
    
    # Ensure all variables are properly formatted for template
    # Convert all properties to dicts
    properties_list = []
    for prop in (all_properties or []):
        if hasattr(prop, 'keys') and not isinstance(prop, dict):
            properties_list.append(dict(prop))
        elif isinstance(prop, dict):
            properties_list.append(prop)
        else:
            properties_list.append(prop)
    
    # Ensure current_property is a dict
    if current_property and hasattr(current_property, 'keys') and not isinstance(current_property, dict):
        current_property = dict(current_property)
    elif not current_property:
        current_property = {}
    
    # Ensure snapshot_data is a dict
    if snapshot_data and hasattr(snapshot_data, 'keys') and not isinstance(snapshot_data, dict):
        snapshot_data = dict(snapshot_data)
    
    # Render Homebot-powered equity page
    try:
        response = make_response(render_template(
            "homeowner/value_equity_homebot.html",
            brand_name=FRONT_BRAND_NAME,
            homebot_widget_id=homebot_widget_id,
            professional_info=professional_info,
            homeowner_data=homeowner_data or {},
            market_rates=market_rates,
            snapshot=snapshot_data,
            value_source_note=__import__("valuation").describe_source(snapshot_data),
            value_change=_value_change_last_year(snapshot_history, snapshot_data),
            value_refresh_available=__import__("valuation").provider_configured(),
            snapshot_history=snapshot_history or [],
            properties=properties_list,
            current_property=current_property or {},
            current_property_id=current_property_id,
        ))
    except Exception as e:
        import traceback
        error_trace = traceback.format_exc()
        print(f"[HOMEBOT] ERROR rendering template: {str(e)}")
        print(error_trace)
        flash("We could not load your equity page. Please try again in a moment.", "error")
        return redirect(url_for("homeowner_overview"))
    
    # Set CSP headers to allow Homebot iframe (only if widget is present)
    # VERY permissive CSP to ensure Homebot widget works fully (address autocomplete, form submission, etc.)
    if homebot_widget_id:
        response.headers['Content-Security-Policy'] = (
            "default-src 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com https://*.googleapis.com https://*.gstatic.com https://static.cloudflareinsights.com; "
            "script-src 'self' 'unsafe-inline' 'unsafe-eval' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com https://*.googleapis.com https://*.gstatic.com https://maps.googleapis.com https://static.cloudflareinsights.com; "
            "frame-src 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com https://*.googleapis.com https://*.gstatic.com data: blob:; "
            "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://*.homebotapp.com https://*.googleapis.com; "
            "font-src 'self' https://fonts.gstatic.com https://*.homebotapp.com data:; "
            "img-src 'self' data: https: blob:; "
            "connect-src 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.cloudflare.com https://*.amazonaws.com https://*.googleapis.com https://*.gstatic.com https://static.cloudflareinsights.com https://mikasa.homebotapp.com wss: ws:; "
            "form-action 'self' https://embed.homebotapp.com https://*.homebotapp.com https://*.googleapis.com; "
            "frame-ancestors 'self'; "
            "worker-src 'self' blob: https://*.homebotapp.com; "
            "manifest-src 'self' https://*.homebotapp.com;"
        )
    
    return response


@route("/homeowner/add-property", methods=["POST"])
def homeowner_add_property():
    """Add a new property for the homeowner."""
    user = get_current_user()
    if not user:
        flash("Please sign in to add a property.", "warning")
        return redirect(url_for("login"))

    address = request.form.get("property_address", "").strip()
    if not address:
        flash("Please add the home's address.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))

    estimated_value = None
    value_str = request.form.get("estimated_value", "").strip()
    if value_str:
        try:
            estimated_value = float(value_str.replace(",", ""))
        except Exception:
            pass

    property_type = request.form.get("property_type", "primary").strip()

    property_id = add_property(user["id"], address, estimated_value, property_type)
    set_primary_property(user["id"], property_id)
    try:
        import valuation
        if valuation.provider_configured():
            _bg(valuation.refresh_property_value, user["id"], property_id)
    except Exception as _e:
        print(f"[VALUES] add-property lookup skipped: {_e}")

    flash(f"Property '{address}' added!", "success")
    return redirect(
        url_for("homeowner_value_equity_overview", property_id=property_id)
    )


@route("/homeowner/value/refresh", methods=["POST"])
def homeowner_value_refresh():
    import valuation
    uid = session.get("user_id")
    pid = request.form.get("property_id", type=int)
    if not pid:
        from database import get_user_properties
        props = [dict(p) for p in (get_user_properties(uid) or [])]
        pid = next((p["id"] for p in props if p.get("is_primary")), props[0]["id"] if props else None)
    msgs = {
        "ok": ("Your home value was updated from live market data.", "success"),
        "cooldown": ("Your value was refreshed recently. Estimates update about once a week at most.", "info"),
        "cap": ("Live updates are paused for now. Please try again later.", "info"),
        "homebot": ("Your value is already kept current by Homebot.", "info"),
        "no-address": ("Add your full street address first so we can look up your home.", "error"),
        "no-key": ("Live home values are not switched on yet.", "info"),
        "not-found": ("We couldn't find that address. Use the full format: street, city, state, ZIP.", "error"),
        "error": ("We couldn't reach the value service. Please try again soon.", "error"),
    }
    status = valuation.refresh_property_value(uid, pid, min_days=7) if pid else "no-address"
    text, cat = msgs.get(status, msgs["error"])
    flash(text, cat)
    return redirect(url_for("homeowner_value_equity_overview"))


@route("/homeowner/switch-property", methods=["POST"])
def homeowner_switch_property():
    """Switch to a different property."""
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))

    property_id = request.form.get("property_id")
    if not property_id:
        flash("Please choose a home first.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))

    try:
        property_id = int(property_id)
    except Exception:
        flash("We could not find that home.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))

    prop = get_property_by_id(property_id)
    if not prop or prop["user_id"] != user["id"]:
        flash("We could not find that home.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))

    set_primary_property(user["id"], property_id)

    flash(f"Switched to {prop['address']}", "success")
    return redirect(
        url_for("homeowner_value_equity_overview", property_id=property_id)
    )


@route("/homeowner/update-property-address", methods=["POST"])
def homeowner_update_property_address():
    """Update the address of a property."""
    user = get_current_user()
    if not user:
        flash("Please sign in to continue.", "warning")
        return redirect(url_for("login"))
    
    property_id = request.form.get("property_id")
    new_address = request.form.get("address", "").strip()
    
    if not property_id or not new_address:
        flash("Property ID and address are required.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    try:
        property_id = int(property_id)
    except Exception:
        flash("We could not find that home.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    # Verify property belongs to user
    prop = get_property_by_id(property_id)
    if not prop or prop["user_id"] != user["id"]:
        flash("We could not find that home.", "error")
        return redirect(url_for("homeowner_value_equity_overview"))
    
    # Update address
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE properties SET address = ? WHERE id = ? AND user_id = ?",
        (new_address, property_id, user["id"])
    )
    conn.commit()
    conn.close()
    
    flash(f"Address updated to {new_address}", "success")
    return redirect(url_for("homeowner_value_equity_overview"))


@route("/homeowner/reno/planner", methods=["GET", "POST"])
def homeowner_reno_planner():
    user = get_current_user()
    user_id = user["id"] if user else None

    if request.method == "POST" and user_id:
        name = request.form.get("project_name", "").strip()
        budget_raw = (
            request.form.get("project_budget", "").replace(",", "").strip()
        )
        status = request.form.get("project_status", "Planning").strip()
        category = request.form.get("project_category", "Other").strip()  # Get category, default to "Other"
        notes = request.form.get("project_notes", "").strip()

        # Convert budget to string (function expects string, not float)
        budget_str = budget_raw if budget_raw else ""

        if name:
            # Fix: Add category parameter and correct argument order
            # Function signature: user_id, name, category, status, budget, notes
            add_homeowner_project(user_id, name, category, status, budget_str, notes)
            flash("Project saved.", "success")

    projects = list_homeowner_projects(user_id) if user_id else []

    return render_template(
        "homeowner/reno_planner.html",
        brand_name=FRONT_BRAND_NAME,
        projects=projects,
    )


@route("/homeowner/reno/planner/projects/json", methods=["GET"])
def homeowner_reno_planner_projects_json():
    """Return saved projects as JSON for AJAX loading."""
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    
    projects = list_homeowner_projects(user_id) if user_id else []
    # Convert to dict format for JSON
    projects_list = []
    for project in projects:
        project_dict = dict(project) if hasattr(project, 'keys') else project
        projects_list.append({
            "id": project_dict.get("id"),
            "name": project_dict.get("name"),
            "category": project_dict.get("category"),
            "status": project_dict.get("status"),
            "budget": project_dict.get("budget"),
            "notes": project_dict.get("notes"),
            "created_at": project_dict.get("created_at"),
        })
    
    return jsonify({"success": True, "projects": projects_list})


@route("/homeowner/reno/planner/project/<int:project_id>/edit", methods=["GET", "POST"])
def homeowner_reno_planner_edit_project(project_id):
    """Edit a renovation project."""
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        flash("Please sign in to edit projects.", "error")
        return redirect(url_for("login", role="homeowner"))
    
    project = get_homeowner_project(project_id, user_id)
    if not project:
        flash("We could not find that project.", "error")
        return redirect(url_for("homeowner_reno_planner"))
    
    if request.method == "POST":
        name = request.form.get("project_name", "").strip()
        budget_raw = request.form.get("project_budget", "").replace(",", "").strip()
        status = request.form.get("project_status", "Planning").strip()
        category = request.form.get("project_category", "Other").strip()
        notes = request.form.get("project_notes", "").strip()
        
        budget_str = budget_raw if budget_raw else ""
        
        if name:
            update_homeowner_project(
                project_id=project_id,
                user_id=user_id,
                name=name,
                category=category,
                status=status,
                budget=budget_str,
                notes=notes,
            )
            flash("Project updated.", "success")
            return redirect(url_for("homeowner_reno_planner"))
        else:
            flash("Please give your project a name.", "error")
    
    project_dict = dict(project) if hasattr(project, 'keys') else project
    return render_template(
        "homeowner/reno_planner_edit.html",
        project=project_dict,
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/reno/planner/project/<int:project_id>/delete", methods=["POST"])
def homeowner_reno_planner_delete_project(project_id):
    """Delete a renovation project."""
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    
    project = get_homeowner_project(project_id, user_id)
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404
    
    try:
        delete_homeowner_project(project_id, user_id)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@route("/homeowner/design-boards/note/<int:note_id>/edit", methods=["GET", "POST"])
def homeowner_edit_note(note_id):
    """Edit a note on a mood board."""
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        flash("Please sign in to edit notes.", "error")
        return redirect(url_for("login", role="homeowner"))
    
    note = get_homeowner_note_by_id(note_id, user_id)
    if not note:
        flash("We could not find that note.", "error")
        return redirect(url_for("homeowner_saved_notes"))
    
    note_dict = dict(note) if hasattr(note, 'keys') else note
    board_name = note_dict.get("project_name")
    
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        details = request.form.get("details", "").strip()
        tags = request.form.get("tags", "").strip()
        
        update_homeowner_note(
            note_id=note_id,
            user_id=user_id,
            title=title if title else None,
            details=details if details else None,
            tags=tags if tags else None,
        )
        flash("Note updated.", "success")
        return redirect(url_for("homeowner_design_board_view", board_name=board_name))
    
    return render_template(
        "homeowner/edit_note.html",
        note=note_dict,
        board_name=board_name,
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/design-boards/note/<int:note_id>/delete", methods=["POST"])
def homeowner_delete_note(note_id):
    """Delete a note from a mood board."""
    user = get_current_user()
    user_id = user["id"] if user else None
    if not user_id:
        return jsonify({"success": False, "error": "Not logged in"}), 401
    
    note = get_homeowner_note_by_id(note_id, user_id)
    if not note:
        return jsonify({"success": False, "error": "Note not found"}), 404
    
    note_dict = dict(note) if hasattr(note, 'keys') else note
    board_name = note_dict.get("project_name")
    
    try:
        delete_homeowner_note(note_id, user_id)
        return jsonify({"success": True, "board_name": board_name})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@route("/homeowner/reno/material-cost", methods=["GET"])
def homeowner_reno_material_cost():
    """Material & Cost Estimator - linked to mood boards."""
    from database import get_design_boards_for_user
    user = get_current_user()
    user_id = user["id"] if user else None
    
    # Get list of mood board names for the dropdown
    board_names = []
    if user_id:
        boards = get_design_boards_for_user(user_id) or []
        board_names = [b for b in boards if b]  # Filter out None values
    
    return render_template(
        "homeowner/reno_material_cost.html",
        brand_name=FRONT_BRAND_NAME,
        board_names=board_names,
    )


@route("/homeowner/reno/roi-guide", methods=["GET"])
def homeowner_reno_roi_guide():
    """Renovation ROI guide."""
    return render_template(
        "homeowner/reno_roi_guide.html",
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/next/plan-my-move", methods=["GET", "POST"])
def homeowner_next_plan_move():
    """Plan my move - next home planning questionnaire."""
    import json
    user = get_current_user()
    if request.method == "POST":
        # Collect all questionnaire data
        questionnaire_data = {
            # Personal Information
            "legal_name": request.form.get("legal_name", "").strip(),
            "email": request.form.get("email", "").strip(),
            "phone": request.form.get("phone", "").strip(),
            "birthday": request.form.get("birthday", "").strip(),
            # Home Purchase Basics
            "preapproved": request.form.get("preapproved", "").strip(),
            "timeline": request.form.get("timeline", "").strip(),
            "budget": request.form.get("budget", "").strip(),
            "beds_baths": request.form.get("beds_baths", "").strip(),
            "must_haves": request.form.get("must_haves", "").strip(),
            "areas": request.form.get("areas", "").strip(),
            # Property Preferences
            "floor_plan": request.form.get("floor_plan", "").strip(),
            "important_items": request.form.get("important_items", "").strip(),
            "garage_specifics": request.form.get("garage_specifics", "").strip(),
            "requirements": request.form.get("requirements", "").strip(),
            "home_type": request.form.get("home_type", "").strip(),
            "construction_type": request.form.get("construction_type", "").strip(),
            "condition": request.form.get("condition", "").strip(),
            "lot_size": request.form.get("lot_size", "").strip(),
            "architectural_style": request.form.get("architectural_style", "").strip(),
            # Location & Lifestyle
            "school_districts": request.form.get("school_districts", "").strip(),
            "transportation": request.form.get("transportation", "").strip(),
            "contact_method": request.form.get("contact_method", "").strip(),
            # Additional Information
            "dealbreakers": request.form.get("dealbreakers", "").strip(),
            "feeling": request.form.get("feeling", "").strip(),
            "other_info": request.form.get("other_info", "").strip(),
        }
        
        # Map to database fields (existing structure)
        timeline = questionnaire_data.get("timeline", "")
        budget_range = questionnaire_data.get("budget", "")
        location_preferences = questionnaire_data.get("areas", "")
        property_type_preferences = f"{questionnaire_data.get('home_type', '')} | {questionnaire_data.get('construction_type', '')} | {questionnaire_data.get('condition', '')}".strip(" |")
        must_haves = questionnaire_data.get("must_haves", "")
        nice_to_haves = f"{questionnaire_data.get('important_items', '')} | {questionnaire_data.get('architectural_style', '')}".strip(" |")
        concerns = questionnaire_data.get("dealbreakers", "")
        # Store all detailed data in notes as JSON
        notes = json.dumps(questionnaire_data, indent=2)
        
        if user:
            upsert_next_move_plan(
                user["id"],
                timeline=timeline,
                budget_range=budget_range,
                location_preferences=location_preferences,
                property_type_preferences=property_type_preferences,
                must_haves=must_haves,
                nice_to_haves=nice_to_haves,
                concerns=concerns,
                notes=notes,
            )
            flash("Your home buyer questionnaire has been saved!", "success")

    plan = get_next_move_plan(user["id"]) if user else None
    # Parse JSON notes if present
    if plan and hasattr(plan, 'notes') and plan.notes:
        try:
            plan_dict = dict(plan) if hasattr(plan, 'keys') else plan
            parsed_notes = json.loads(plan_dict.get('notes', '{}'))
            # Merge parsed data back into plan for template access
            if isinstance(plan_dict, dict):
                plan_dict.update(parsed_notes)
                plan = type('obj', (object,), plan_dict)
        except Exception:
            pass
    
    return render_template(
        "homeowner/next_plan_move.html",
        brand_name=FRONT_BRAND_NAME,
        plan=plan,
    )


@route("/homeowner/next/buy-sell-guidance", methods=["GET"])
def homeowner_next_buy_sell_guidance():
    """Buy and sell guidance."""
    return render_template(
        "homeowner/next_buy_sell_guidance.html",
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/next/loan-paths", methods=["GET"])
def homeowner_next_loan_paths():
    """Loan paths guidance."""
    return render_template(
        "homeowner/next_loan_paths.html",
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/next/affordability", methods=["GET"])
def homeowner_next_affordability():
    """Affordability calculator."""
    return render_template(
        "homeowner/next_affordability.html",
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/care/maintenance-guide", methods=["GET"])
def homeowner_care_maintenance_guide():
    """Home maintenance guide."""
    return render_template(
        "homeowner/care_maintenance_guide.html",
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/care/seasonal-checklists", methods=["GET"])
def homeowner_care_seasonal_checklists():
    """Seasonal maintenance checklists."""
    return render_template(
        "homeowner/care_seasonal_checklists.html",
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/care/home-protection", methods=["GET"])
def homeowner_care_home_protection():
    """Home protection guide."""
    return render_template(
        "homeowner/care_home_protection.html",
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/care/warranty-log", methods=["GET", "POST"])
def homeowner_care_warranty_log():
    """Warranty log - add, view, and delete warranty items."""
    from database import add_warranty_log_item, list_warranty_log_items, delete_warranty_log_item
    from datetime import datetime
    
    user = get_current_user()
    if not user:
        flash("Please sign in to access this page.", "warning")
        return redirect(url_for("login"))
    
    if user.get("role") != "homeowner":
        flash("That page is made for homeowners.", "error")
        return redirect(url_for("agent_dashboard" if user.get("role") == "agent" else "lender_dashboard"))
    
    homeowner_id = user["id"]
    
    # Handle POST requests
    if request.method == "POST":
        # Handle delete
        if request.form.get("delete_id"):
            item_id = int(request.form.get("delete_id"))
            if delete_warranty_log_item(item_id, homeowner_id):
                flash("Warranty item deleted.", "success")
            else:
                flash("We could not delete that warranty item. Please try again in a moment.", "error")
            return redirect(url_for("homeowner_care_warranty_log"))
        
        # Handle add new item
        item_name = request.form.get("item_name", "").strip()
        category = request.form.get("category", "").strip()
        
        if not item_name or not category:
            flash("Please add an item name and a category.", "error")
            return redirect(url_for("homeowner_care_warranty_log"))
        
        purchase_date = request.form.get("purchase_date") or None
        warranty_start = request.form.get("warranty_start") or None
        warranty_expiry = request.form.get("warranty_expiry") or None
        warranty_provider = request.form.get("warranty_provider", "").strip() or None
        warranty_number = request.form.get("warranty_number", "").strip() or None
        notes = request.form.get("notes", "").strip() or None
        
        try:
            add_warranty_log_item(
                user_id=homeowner_id,
                item_name=item_name,
                category=category,
                purchase_date=purchase_date,
                warranty_start=warranty_start,
                warranty_expiry=warranty_expiry,
                warranty_provider=warranty_provider,
                warranty_number=warranty_number,
                notes=notes
            )
            flash("Warranty item added!", "success")
        except Exception as e:
            print(f"[WARRANTY LOG] Error adding item: {e}")
            import traceback
            traceback.print_exc()
            flash("We could not add that warranty item. Please try again in a moment.", "error")
        
        return redirect(url_for("homeowner_care_warranty_log"))
    
    # GET request - display items
    warranty_items = list_warranty_log_items(homeowner_id)
    
    return render_template(
        "homeowner/care_warranty_log.html",
        brand_name=FRONT_BRAND_NAME,
        warranty_items=warranty_items,
        now=datetime.now()
    )


@route("/homeowner/care/energy-savings", methods=["GET"])
def homeowner_care_energy_savings():
    """Energy savings guide."""
    return render_template(
        "homeowner/care_energy_savings.html",
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/support/ask-question", methods=["GET", "POST"])
def homeowner_support_ask_question():
    """Ask a question. GET redirects to unified Get Help page; POST saves question."""
    user = get_current_user()
    if request.method == "POST":
        topic = request.form.get("topic", "").strip() or None
        question = request.form.get("question", "").strip()
        redirect_to = request.form.get("_redirect_to") or url_for("homeowner_support_get_help") + "?tab=ask&sent=1"
        if question and user:
            add_homeowner_question(user["id"], topic or "General", question)
            try:
                import automation
                _bg(automation.route_homeowner_question, user["id"], topic or "General", question, send_reminder_email, _site_url())
            except Exception as _auto_err:
                print(f"[AUTOMATION] question hook failed: {_auto_err}")
            flash("Question submitted! Your agent has been notified and will reply to you directly.", "success")
            return redirect(redirect_to)
        elif not question:
            flash("What would you like to ask? Type your question and we will pass it along.", "error")
        return redirect(url_for("homeowner_support_get_help") + "?tab=ask")
    # GET: redirect to unified page
    return redirect(url_for("homeowner_support_get_help") + "?tab=ask")


@route("/homeowner/support/chat-human", methods=["GET"])
def homeowner_support_chat_human():
    """Redirects to unified Get Help page, Contact tab."""
    return redirect(url_for("homeowner_support_get_help") + "?tab=contact")


@route("/homeowner/support/schedule-chat", methods=["GET"])
def homeowner_support_schedule_chat():
    """Redirects to unified Get Help page, Schedule tab."""
    return redirect(url_for("homeowner_support_get_help") + "?tab=schedule")


@route("/homeowner/support/resources", methods=["GET"])
def homeowner_support_resources():
    """Redirects to unified Get Help page, Resources tab."""
    return redirect(url_for("homeowner_support_get_help") + "?tab=resources")


@route("/homeowner/support/get-help", methods=["GET"])
@route("/homeowner/support", methods=["GET"])
def homeowner_support_get_help():
    """Unified Get Help page, replaces the 5 separate support sub-pages."""
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))
    professionals = []
    try:
        from database import get_homeowner_professionals as _ghp
        professionals = [dict(p) for p in _ghp(user["id"])]
    except Exception:
        pass
    question_submitted = request.args.get("sent") == "1"
    return render_template(
        "homeowner/support_get_help.html",
        professionals=professionals,
        question_submitted=question_submitted,
        brand_name=FRONT_BRAND_NAME,
    )


@route("/homeowner/next", methods=["GET"])
@route("/homeowner/next/", methods=["GET"])
def homeowner_next_home_hub():
    """Hub landing page for the Next Home section."""
    user = get_current_user()
    if not user:
        return redirect(url_for("login"))
    professionals = []
    try:
        from database import get_homeowner_professionals as _ghp
        professionals = [dict(p) for p in _ghp(user["id"])]
    except Exception:
        pass
    return render_template(
        "homeowner/next_home_hub.html",
        professionals=professionals,
        brand_name=FRONT_BRAND_NAME,
    )
