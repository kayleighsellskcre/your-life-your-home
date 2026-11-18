"""Lender follow-ups: the borrowers a lender planned to reach, with Done and Snooze.

Same idea as the agent Follow-ups page. A borrower shows up when their next-action date is today or earlier, or when they
were never contacted and have no date yet (open loans only). Done logs how it went and sets the next step; Snooze moves the
date forward and keeps the note.
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

bp = Blueprint("lender_followups", __name__)
_H = {}
SNOOZES = {"1": ("Tomorrow", 1), "3": ("In 3 days", 3), "7": ("Next week", 7)}
# key: (label, what we log, new status or None, days until the next check-in or None, note for that check-in)
OUTCOMES = {
    "talked": ("We talked, all good", "We talked and it went well.", None, None, ""),
    "message": ("I left a message", "Left a message.", None, 3, "Try again"),
    "rates": ("I will send them numbers", "Promised to send numbers.", None, 2, "Send numbers"),
    "later": ("Check in again in 2 weeks", "Agreed to talk again in a couple of weeks.", None, 14, "Friendly check in"),
    "ready": ("They are ready to apply", "Ready to move forward.", "preapproval", None, ""),
    "notnow": ("Not the right time yet", "Not the right time yet. Keeping in touch gently.", None, 60, "Gentle check in"),
}
_SKIP = ("lost", "hold", "past", "inactive")


def _db():
    from database import get_connection
    return get_connection()


def _lender():
    u = _H["get_current_user"]()
    return u if u and u.get("role") == "lender" else None


def due_for(lender_id):
    """Overdue and due-today borrowers first (oldest first), then open borrowers never contacted who have no date."""
    from planner import ago
    today = date.today().isoformat()
    conn = _db()
    try:
        rows = conn.execute(
            """SELECT id, name, phone, email, status, last_touch, COALESCE(next_action_date,'') AS due, COALESCE(next_action_note,'') AS note
               FROM lender_borrowers
               WHERE lender_user_id = ? AND TRIM(COALESCE(name, '')) != '' AND LOWER(COALESCE(status, '')) NOT IN ('lost', 'hold', 'past', 'inactive')
                 AND ((COALESCE(next_action_date, '') != '' AND next_action_date <= ?)
                      OR (COALESCE(next_action_date, '') = '' AND COALESCE(last_touch, '') = '' AND LOWER(COALESCE(status, '')) != 'closed'))
               ORDER BY CASE WHEN COALESCE(next_action_date,'') = '' THEN 1 ELSE 0 END, next_action_date, name COLLATE NOCASE
               LIMIT 300""", (lender_id, today)).fetchall()
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
            r["status_label"] = "Due today" if late <= 0 else ("1 day late" if late == 1 else f"{late} days late")
            r["late"] = late > 0
        else:
            r["status_label"], r["late"] = "Never contacted", False
        out.append(r)
    return out


@bp.route("/lender/followups")
def followups_page():
    u = _lender()
    if not u:
        return redirect(url_for("login", role="lender"))
    conn = _db()
    try:
        people = conn.execute("SELECT COUNT(*) FROM lender_borrowers WHERE lender_user_id = ?", (u["id"],)).fetchone()[0]
    finally:
        conn.close()
    return render_template("lender/followups.html", rows=due_for(u["id"]), snoozes=SNOOZES, outcomes=OUTCOMES, has_people=bool(people))


@bp.route("/lender/followups/<int:borrower_id>/<action>", methods=["POST"])
def followup_act(borrower_id, action):
    u = _lender()
    if not u:
        return redirect(url_for("login", role="lender"))
    conn = _db()
    try:
        row = conn.execute("SELECT id, name FROM lender_borrowers WHERE id = ? AND lender_user_id = ?", (borrower_id, u["id"])).fetchone()
        if not row:
            flash("We could not find that borrower.", "error")
            return redirect(url_for("lender_followups.followups_page"))
        today = date.today()
        if action == "done":
            conn.execute("UPDATE lender_borrowers SET next_action_date = '', next_action_note = '', last_touch = ? WHERE id = ?", (today.isoformat(), borrower_id))
            flash(f"Done. {row['name']} is marked as followed up today.", "success")
        elif action == "outcome":
            label, what, status, days, note = OUTCOMES.get(request.form.get("result", ""), OUTCOMES["talked"])
            nxt = (today + timedelta(days=days)).isoformat() if days else ""
            conn.execute("UPDATE lender_borrowers SET next_action_date = ?, next_action_note = ?, last_touch = ? WHERE id = ?", (nxt, note, today.isoformat(), borrower_id))
            if status:
                conn.execute("UPDATE lender_borrowers SET status = ? WHERE id = ? AND lender_user_id = ?", (status, borrower_id, u["id"]))
            conn.commit()  # release the lock before the history entry is written
            try:
                from database import add_crm_interaction
                add_crm_interaction(borrower_id, "lender_borrower", u["id"], "call", label, what, "phone")
            except Exception:
                pass
            flash(f"Saved. {row['name']}: {label.lower()}." + (f" I will remind you on {nxt}." if nxt else ""), "success")
        elif action == "snooze":
            n = SNOOZES.get(request.form.get("days", "1"), SNOOZES["1"])[1]
            new = (today + timedelta(days=n)).isoformat()
            conn.execute("UPDATE lender_borrowers SET next_action_date = ? WHERE id = ?", (new, borrower_id))
            flash(f"Snoozed. {row['name']} will come back on {new}.", "success")
        else:
            flash("That action is not available.", "error")
            return redirect(url_for("lender_followups.followups_page"))
        conn.commit()
    finally:
        conn.close()
    return redirect(url_for("lender_followups.followups_page"))


def init_app(app, get_current_user):
    _H.update(get_current_user=get_current_user)
    app.register_blueprint(bp)
