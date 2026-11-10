"""Follow-ups: the CRM contacts an agent planned to reach, with Done and Snooze.

It lists exactly the people the dashboard's Follow-ups number counts: next-action date today or earlier, plus people never
contacted who have no date. Done records the follow-up as today; Snooze moves the date forward and keeps the note.
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

bp = Blueprint("followups", __name__)
_H = {}
SNOOZES = {"1": ("Tomorrow", 1), "3": ("In 3 days", 3), "7": ("Next week", 7)}
# How did it go? key: (label, what we log, new stage or None, days until the next check-in or None, note for that check-in)
OUTCOMES = {
    "talked": ("We talked, all good", "We talked and it went well.", None, None, ""),
    "message": ("I left a message", "Left a message.", None, 3, "Try again"),
    "listings": ("I will send them listings", "Promised to send listings.", None, 2, "Send listings"),
    "later": ("Check in again in 2 weeks", "Agreed to talk again in a couple of weeks.", None, 14, "Friendly check in"),
    "ready": ("They are ready to work together", "Ready to work together.", "active", None, ""),
    "notnow": ("Not the right time yet", "Not the right time yet. Keeping in touch gently.", "nurture", 60, "Gentle check in"),
}


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
            """SELECT id, name, phone, email, stage, last_touch, COALESCE(next_action_date,'') AS due, COALESCE(next_action_note,'') AS note,
                      partner_id, (SELECT p.name FROM agent_contacts p WHERE p.id = agent_contacts.partner_id) AS partner_name
               FROM agent_contacts
               WHERE agent_user_id = ? AND LOWER(COALESCE(stage, '')) NOT IN ('closed', 'hold', 'past')
                 AND ((COALESCE(next_action_date, '') != '' AND next_action_date <= ?)
                      OR (COALESCE(next_action_date, '') = '' AND COALESCE(last_touch, '') = ''))
               ORDER BY CASE WHEN COALESCE(next_action_date,'') = '' THEN 1 ELSE 0 END, next_action_date, name COLLATE NOCASE
               LIMIT 300""", (agent_id, today)).fetchall()
    finally:
        conn.close()
    out = []
    due_ids = {r["id"] for r in rows}
    for r in rows:
        r = dict(r)
        if r["partner_id"] in due_ids and r["partner_id"] < r["id"]:
            continue  # a couple is one reminder, not two
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
    return render_template("agent/followups.html", rows=due_for(u["id"]), snoozes=SNOOZES, outcomes=OUTCOMES)


@bp.route("/agent/followups/<int:contact_id>/<action>", methods=["POST"])
def followup_act(contact_id, action):
    u = _agent()
    if not u:
        return redirect(url_for("login", role="agent"))
    conn = _db()
    try:
        row = conn.execute("SELECT id, name, partner_id, COALESCE(next_action_date,'') AS due FROM agent_contacts WHERE id = ? AND agent_user_id = ?",
                           (contact_id, u["id"])).fetchone()
        if not row:
            flash("We could not find that contact.", "error")
            return redirect(url_for("followups.followups_page"))
        today = date.today()
        group = [contact_id] + ([row["partner_id"]] if row["partner_id"] else [])
        if action == "done":
            for cid in group:
                conn.execute("UPDATE agent_contacts SET next_action_date = '', next_action_note = '', last_touch = ? WHERE id = ?",
                             (today.isoformat(), cid))
            flash(f"Done. {row['name']} is marked as followed up today.", "success")
        elif action == "outcome":
            label, what, stage, days, note = OUTCOMES.get(request.form.get("result", ""), OUTCOMES["talked"])
            nxt = (today + timedelta(days=days)).isoformat() if days else ""
            for cid in group:
                conn.execute("UPDATE agent_contacts SET next_action_date = ?, next_action_note = ?, last_touch = ? WHERE id = ?",
                             (nxt, note, today.isoformat(), cid))
            if stage:
                conn.execute("UPDATE agent_contacts SET stage = ? WHERE agent_user_id = ? AND (id = ? OR id = (SELECT partner_id FROM agent_contacts WHERE id = ?))",
                             (stage, u["id"], contact_id, contact_id))
            conn.commit()  # release the lock before the history entry is written
            try:
                from database import add_crm_interaction
                add_crm_interaction(contact_id, "agent_contact", u["id"], "call", label, what, "phone")
            except Exception:
                pass
            flash(f"Saved. {row['name']}: {label.lower()}." + (f" I will remind you on {nxt}." if nxt else ""), "success")
        elif action == "snooze":
            n = SNOOZES.get(request.form.get("days", "1"), SNOOZES["1"])[1]
            new = (today + timedelta(days=n)).isoformat()
            for cid in group:
                conn.execute("UPDATE agent_contacts SET next_action_date = ? WHERE id = ?", (new, cid))
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
