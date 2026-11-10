"""Site admin pages (dashboard, home values, users).

Moved out of app.py. Loaded by install(), which runs these views in app.py's own namespace (see route_loader.py), so every
helper they use is looked up there, exactly as before. This file is not meant to be run or linted on its own. Route names
(endpoints) are unchanged, so url_for(...) keeps working.
"""
from route_loader import Registry

_registry = Registry()
route = _registry.route
install = _registry.install


@route("/admin/promo-codes")
def admin_promo_codes():
    """Admin view of all promo codes and usage."""
    if not _admin_session_user():
        flash("That area is just for site administrators.", "error")
        return redirect(url_for("login", role="agent"))
    from database import list_promo_codes
    codes = list_promo_codes()
    return render_template("admin/promo_codes.html", codes=codes)


@route("/admin")
@route("/admin/dashboard")
def admin_dashboard():
    """Admin dashboard - Owner control panel"""
    from rbac import has_role
    from audit import get_audit_logs
    
    user = _admin_session_user()
    if not user:
        flash("That area is just for site administrators.", "error")
        return redirect(url_for('login', role='agent'))
    
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get stats
    cur.execute("SELECT COUNT(*) as count FROM users")
    total_users = cur.fetchone()['count']
    
    cur.execute("SELECT COUNT(*) as count FROM properties")
    total_properties = cur.fetchone()['count']
    
    try:
        cur.execute("SELECT COUNT(*) as count FROM video_projects")
        total_videos = cur.fetchone()['count']
    except Exception:
        total_videos = 0  # video studio was removed; table may not exist
    
    cur.execute("""
        SELECT COUNT(*) as count FROM users 
        WHERE DATE(last_login) = DATE('now')
    """)
    active_today = cur.fetchone()['count']
    
    # Get recent users
    cur.execute("""
        SELECT id, name, email, role, subscription_tier, created_at, email_verified
        FROM users
        ORDER BY created_at DESC
        LIMIT 10
    """)
    recent_users = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    
    # Get recent activity from audit logs
    recent_activity = []
    try:
        logs = get_audit_logs(limit=10)
        for log in logs:
            # Get user name
            conn = get_connection()
            cur = conn.cursor()
            if log['user_id']:
                cur.execute("SELECT name FROM users WHERE id = ?", (log['user_id'],))
                user_row = cur.fetchone()
                log['user_name'] = user_row['name'] if user_row else 'Unknown'
            else:
                log['user_name'] = 'System'
            conn.close()
            recent_activity.append(log)
    except Exception:
        pass
    
    stats = {
        'total_users': total_users,
        'total_properties': total_properties,
        'total_videos': total_videos,
        'active_today': active_today
    }
    
    return render_template(
        'admin/dashboard.html',
        stats=stats,
        recent_users=recent_users,
        recent_activity=recent_activity
    )


@route("/admin/home-values", methods=["GET", "POST"])
def admin_home_values():
    """Owner-only status page for the RentCast connection: settings, usage, recent lookups, and a test lookup."""
    import valuation
    user = _admin_session_user()
    if not user:
        flash("That area is just for site administrators.", "error")
        return redirect(url_for("login", role="agent"))
    test = None
    address = ""
    if request.method == "POST":
        address = request.form.get("address", "").strip()
        test = valuation.test_address(address)
    return render_template("admin/home_values.html", s=valuation.settings_summary(), test=test, address=address,
                           describe=valuation.describe_error)


@route("/admin/home-values/refresh-now", methods=["POST"])
def admin_home_values_refresh_now():
    """Run the nightly value refresh right now (still inside the caps), so new homes do not wait until 2 AM."""
    import valuation
    user = _admin_session_user()
    if not user:
        flash("That area is just for site administrators.", "error")
        return redirect(url_for("login", role="agent"))
    if not valuation.provider_configured():
        flash(valuation.describe_error("no-key"), "error")
    else:
        done = valuation.refresh_stale_values()
        flash(f"Checked {done} home{'s' if done != 1 else ''} with RentCast. See the list below for what came back.", "success")
    return redirect(url_for("admin_home_values"))


@route("/admin/home-values/clear-failed", methods=["POST"])
def admin_home_values_clear_failed():
    """Remove lookups that did not work (rejected key, address not found, no connection) from the history."""
    user = _admin_session_user()
    if not user:
        flash("That area is just for site administrators.", "error")
        return redirect(url_for("login", role="agent"))
    conn = get_connection()
    try:
        n = conn.execute("DELETE FROM avm_calls WHERE status NOT IN ('ok', 'test-ok')").rowcount
        conn.commit()
    finally:
        conn.close()
    flash(f"Cleared {n} lookup{'s' if n != 1 else ''} that did not work. Lookups that worked were kept.", "success")
    return redirect(url_for("admin_home_values"))


@route("/admin/impersonate/<int:user_id>", methods=["POST"])
def admin_impersonate_user(user_id):
    """Start impersonating a user (View As feature)"""
    from rbac import has_permission
    from impersonation import start_impersonation
    
    admin = _admin_session_user()
    if not admin:
        return redirect(url_for('login'))
    
    # Check permission
    if not has_permission(admin['id'], 'users.impersonate'):
        flash("That option is just for site administrators.", "error")
        return redirect(url_for('admin_dashboard'))
    
    # Get target user
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    target_user = cur.fetchone()
    conn.close()
    
    if not target_user:
        flash("We could not find that person.", "error")
        return redirect(url_for('admin_dashboard'))
    
    target_user = dict(target_user)
    
    # Start impersonation
    reason = request.form.get('reason', 'Support assistance')
    session_id, _ = start_impersonation(admin['id'], user_id, reason)
    
    # Store impersonation data in session
    session['impersonation'] = {
        'session_id': session_id,
        'admin_id': admin['id'],
        'admin_name': admin['name'],
        'original_user': admin
    }
    
    # Switch to target user
    session['user'] = target_user
    
    flash(f"Support Mode: Now viewing as {target_user['name']}", "warning")
    
    # Redirect to appropriate dashboard based on target user's role
    if target_user['role'] == 'homeowner':
        return redirect(url_for('homeowner_overview'))
    elif target_user['role'] == 'agent':
        return redirect(url_for('agent_dashboard'))
    elif target_user['role'] == 'lender':
        return redirect(url_for('lender_dashboard'))
    else:
        return redirect(url_for('index'))


@route("/admin/end-impersonation", methods=["POST"])
def admin_end_impersonation():
    """End impersonation session"""
    from impersonation import end_impersonation
    
    if 'impersonation' not in session:
        return redirect(url_for('index'))
    if not _admin_session_user():
        abort(403)
    
    imp = session['impersonation']
    
    # End the impersonation session
    end_impersonation(imp['session_id'], imp['admin_id'])
    
    # Restore admin session
    orig = imp.get('original_user') or {}
    session['user_id'] = int(orig.get('user_id') or imp['admin_id'])
    session['name'] = orig.get('name') or 'Admin'
    session['role'] = orig.get('role') or 'agent'
    del session['impersonation']
    
    flash("Exited Support Mode - Back to Admin View", "success")
    return redirect(url_for('admin_dashboard'))


@route("/admin/users")
def admin_users_list():
    """List all users with management options"""
    from rbac import has_permission
    
    user = _admin_session_user()
    if not user or not has_permission(user['id'], 'users.view'):
        flash("That page is not available to your account.", "error")
        return redirect(url_for('index'))
    
    conn = get_connection()
    cur = conn.cursor()
    
    # Get all users
    cur.execute("""
        SELECT id, name, email, phone, role, subscription_tier, 
               created_at, last_login, email_verified
        FROM users
        ORDER BY created_at DESC
    """)
    users = [dict(row) for row in cur.fetchall()]
    
    conn.close()
    
    return render_template('admin/users.html', users=users)


@route("/admin/backup/download")
def admin_backup_download():
    """Admins can download a fresh snapshot of the database."""
    user = _admin_session_user()
    if not user:
        flash("That page is not available to your account.", "error")
        return redirect(url_for("index"))
    path = backup_database()
    return send_file(path, as_attachment=True, download_name=path.name)


@route("/admin/audit-logs")
def admin_audit_logs():
    """View audit logs"""
    from rbac import has_permission
    from audit import get_audit_logs
    
    user = _admin_session_user()
    if not user or not has_permission(user['id'], 'security.view_audit'):
        flash("That page is not available to your account.", "error")
        return redirect(url_for('index'))
    
    # Get filters from query params
    action_filter = request.args.get('action')
    user_filter = request.args.get('user_id', type=int)
    limit = request.args.get('limit', 100, type=int)
    
    # Get logs
    logs = get_audit_logs(
        user_id=user_filter,
        action=action_filter,
        limit=limit
    )
    
    # Enrich with user names
    conn = get_connection()
    cur = conn.cursor()
    
    for log in logs:
        if log['user_id']:
            cur.execute("SELECT name FROM users WHERE id = ?", (log['user_id'],))
            user_row = cur.fetchone()
            log['user_name'] = user_row['name'] if user_row else 'Unknown'
        else:
            log['user_name'] = 'System'
    
    conn.close()
    
    return render_template('admin/audit_logs.html', logs=logs)
