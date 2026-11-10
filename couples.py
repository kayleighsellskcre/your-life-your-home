"""Spouses and partners in the agent CRM.

Each person is their own contact (their own email, phone and birthday), and the two are linked
through agent_contacts.partner_id. The partner copy shares the address and stage, and only gets
birthday emails, so a couple is never mailed the same thing twice.
"""
import re

from database import get_connection

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+\-']+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4}")
SEP_RE = re.compile(r"\s*(?:&|\+|/|\band\b)\s*", re.I)
SHARED = ("address", "city", "state", "zip_code", "stage", "property_address", "property_value",
          "equity_estimate", "lead_source", "tags")


def ensure_column():
    conn = get_connection()
    try:
        conn.execute("ALTER TABLE agent_contacts ADD COLUMN partner_id INTEGER")
        conn.commit()
    except Exception:
        pass
    finally:
        conn.close()


def split_names(name):
    """'Beard, Michael & Mindy' -> ('Michael Beard', 'Mindy Beard'); 'Pat and Sam Lee' -> ('Pat Lee', 'Sam Lee')."""
    name = (name or "").strip()
    last = ""
    if "," in name:
        last, name = [x.strip() for x in name.split(",", 1)]
    parts = [p.strip() for p in SEP_RE.split(name) if p.strip()]
    if len(parts) < 2:
        return name or last, ""
    first, second = parts[0], parts[1]
    if not last:
        words = second.split()
        if len(words) > 1 and len(first.split()) == 1:
            last = " ".join(words[1:])
            second = words[0]
    a = (first + " " + last).strip()
    b = (second + " " + last).strip() if len(second.split()) == 1 else second
    return a, b


def looks_like_couple(name, email, phone):
    return bool(len(EMAIL_RE.findall(email or "")) > 1 or len(PHONE_RE.findall(phone or "")) > 1
                or SEP_RE.search((name or "").replace(",", " ")) and len(SEP_RE.split((name or "").replace(",", " "))) > 1)


def _row(conn, agent_id, cid):
    r = conn.execute("SELECT * FROM agent_contacts WHERE id=? AND agent_user_id=?", (cid, agent_id)).fetchone()
    return dict(r) if r else None


def add_partner(agent_id, contact_id, name, email="", phone="", birthday=""):
    """Create a linked partner for contact_id. Returns the new contact id, or None."""
    name = (name or "").strip()
    if not name:
        return None
    conn = get_connection()
    try:
        me = _row(conn, agent_id, contact_id)
        if not me or me.get("partner_id"):
            return None
        cols = ["agent_user_id", "name", "email", "phone", "birthday", "best_contact", "partner_id",
                "auto_birthday", "auto_anniversary", "auto_seasonal", "auto_equity", "auto_holidays"] + list(SHARED)
        vals = [agent_id, name, (email or "").strip(), (phone or "").strip(), (birthday or "").strip(),
                (email or phone or "").strip(), contact_id, 1, 0, 0, 0, 0] + [me.get(c) for c in SHARED]
        cur = conn.execute("INSERT INTO agent_contacts (%s) VALUES (%s)" % (",".join(cols), ",".join("?" * len(cols))), vals)
        pid = cur.lastrowid
        conn.execute("UPDATE agent_contacts SET partner_id=? WHERE id=? AND agent_user_id=?", (pid, contact_id, agent_id))
        conn.commit()
        return pid
    finally:
        conn.close()


def split_couple(agent_id, contact_id, name, email, phone):
    """Turn one combined contact into two linked people. Returns (first_name, partner_id) or None."""
    n1, n2 = split_names(name)
    emails, phones = EMAIL_RE.findall(email or ""), PHONE_RE.findall(phone or "")
    if not n2:
        return None
    conn = get_connection()
    try:
        me = _row(conn, agent_id, contact_id)
    finally:
        conn.close()
    if not me or me.get("partner_id"):
        return None
    conn = get_connection()
    try:
        conn.execute("UPDATE agent_contacts SET name=?, email=?, phone=?, best_contact=? WHERE id=? AND agent_user_id=?",
                     (n1, emails[0] if emails else "", phones[0] if phones else "", (emails or phones or [""])[0], contact_id, agent_id))
        conn.commit()
    finally:
        conn.close()
    pid = add_partner(agent_id, contact_id, n2, emails[1] if len(emails) > 1 else "", phones[1] if len(phones) > 1 else "")
    return (n1, pid) if pid else None


def unlink(agent_id, contact_id):
    conn = get_connection()
    try:
        me = _row(conn, agent_id, contact_id)
        if not me:
            return
        conn.execute("UPDATE agent_contacts SET partner_id=NULL WHERE agent_user_id=? AND (id=? OR partner_id=?)",
                     (agent_id, contact_id, contact_id))
        conn.commit()
    finally:
        conn.close()


def forget(agent_id, contact_id):
    """Call before deleting a contact so their partner is left as a normal, unlinked contact."""
    conn = get_connection()
    try:
        conn.execute("UPDATE agent_contacts SET partner_id=NULL WHERE agent_user_id=? AND partner_id=?", (agent_id, contact_id))
        conn.commit()
    finally:
        conn.close()


BUSINESS = re.compile(r"\b(inc|llc|ltd|co|corp|company|realty|group|team|properties|trust|sons|bros|brothers|associates|partners|properties|homes|construction|roofing|plumbing|title|mortgage|bank|church)\b", re.I)


def find_combined(agent_id):
    """Contacts saved as a couple in one record, e.g. 'Beard, Michael & Mindy'. Business-looking names are skipped."""
    conn = get_connection()
    try:
        rows = conn.execute("SELECT id, name, email, phone FROM agent_contacts WHERE agent_user_id=? AND partner_id IS NULL AND name LIKE '%' ", (agent_id,)).fetchall()
    finally:
        conn.close()
    out = []
    for r in rows:
        name = r["name"] or ""
        if BUSINESS.search(name) or not SEP_RE.search(name.replace(",", " ")):
            continue
        n1, n2 = split_names(name)
        if n1 and n2:
            out.append({"id": r["id"], "name": name, "n1": n1, "n2": n2})
    return out


def split_many(agent_id, ids):
    """Split each chosen contact that is still a combined couple. Returns how many were split."""
    ok = {c["id"]: c for c in find_combined(agent_id)}
    done = 0
    for cid in ids:
        if cid not in ok:
            continue
        conn = get_connection()
        try:
            r = conn.execute("SELECT name, email, phone FROM agent_contacts WHERE id=? AND agent_user_id=?", (cid, agent_id)).fetchone()
        finally:
            conn.close()
        if r and split_couple(agent_id, cid, r["name"], r["email"], r["phone"]):
            done += 1
    return done
