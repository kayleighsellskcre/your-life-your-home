"""Follow-ups: the CRM contacts an agent planned to reach, with Done and Snooze.

It lists exactly the people the dashboard's Follow-ups number counts: next-action date today or earlier, plus people never
contacted who have no date. Done records the follow-up as today; Snooze moves the date forward and keeps the note.
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

bp = Blueprint("followups", __name__)
_H = {}
SNOOZES = {"1": ("Tomorrow", 1), "3": ("In 3 days", 3), "7": ("Next week", 7)}


def _db():
    from database import get_connection
    return get_connection()


def _agent():
    u = _H["get_current_user"]()
    return u if u and u.get("role") == "agent" else None


def due_for(agent_id):
    """Overdue and due-today follow-ups first (oldest first), then people never contacted who have no date."""
    from planner import ago
    today = date.today().isoformat()
    conn = _db()
    try:
        rows = conn.execute(
            """SELECT id, name, phone, email, stage, last_touch, COALESCE(next_action_date,'') AS due, COALESCE(next_action_note,'') AS note
               FROM agent_contacts
               WHERE agent_user_id = ? AND LOWER(COALESCE(stage, '')) NOT IN ('closed', 'hold', 'past')
                 AND ((COALESCE(next_action_date, '') != '' AND next_action_date <= ?)
                      OR (COALESCE(next_action_date, '') = '' AND COALESCE(last_touch, '') = ''))
               ORDER BY CASE WHEN COALESCE(next_action_date,'') = '' THEN 1 ELSE 0 END, next_action_date, name COLLATE NOCASE
               LIMIT 300""", (agent_id, today)).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        r = dict(r)
        label, days = ago(r["last_touch"])
        r["last"], r["days"] = label, days
        if r["due"]:
            try:
                late = (date.today() - datetime.strptime(r["due"][:10], "%Y-%m-%d").date()).days
            except ValueError:
                late = 0
            r["status"] = "Due today" if late <= 0 else ("1 day late" if late == 1 else f"{late} days late")
            r["late"] = late > 0
        else:
            r["status"], r["late"] = "Never contacted", False
        out.append(r)
    return out


@bp.route("/agent/followups")
def followups_page():
    u = _agent()
    if not u:
        return redirect(url_for("login", role="agent"))
    return render_template("agent/followups.html", rows=due_for(u["id"]), snoozes=SNOOZES)


@bp.route("/agent/followups/<int:contact_id>/<action>", methods=["POST"])
def followup_act(contact_id, action):
    u = _agent()
    if not u:
        return redirect(url_for("login", role="agent"))
    conn = _db()
    try:
        row = conn.execute("SELECT id, name, COALESCE(next_action_date,'') AS due FROM agent_contacts WHERE id = ? AND agent_user_id = ?",
                           (contact_id, u["id"])).fetchone()
        if not row:
            flash("We could not find that contact.", "error")
            return redirect(url_for("followups.followups_page"))
        today = date.today()
        if action == "done":
            conn.execute("UPDATE agent_contacts SET next_action_date = '', next_action_note = '', last_touch = ? WHERE id = ?",
                         (today.isoformat(), contact_id))
            flash(f"Done. {row['name']} is marked as followed up today.", "success")
        elif action == "snooze":
            n = SNOOZES.get(request.form.get("days", "1"), SNOOZES["1"])[1]
            new = (today + timedelta(days=n)).isoformat()
            conn.execute("UPDATE agent_contacts SET next_action_date = ? WHERE id = ?", (new, contact_id))
            flash(f"Snoozed. {row['name']} will come back on {new}.", "success")
        else:
            flash("That action is not available.", "error")
            return redirect(url_for("followups.followups_page"))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("followups.followups_page"))


def init_app(app, get_current_user):
    _H.update(get_current_user=get_current_user)
    app.register_blueprint(bp)
