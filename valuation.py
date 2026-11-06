"""
Real home values.

Pulls an automated valuation (AVM) from RentCast (https://developers.rentcast.io) and stores it
on the homeowner's snapshot, so equity, the dashboards, and the agent/lender alerts use real data.

Turn it on by setting RENTCAST_API_KEY. Everything is cost-capped:
  RENTCAST_MONTHLY_CAP   max lookups per rolling 30 days   (default 45, inside the free plan's 50)
  VALUE_REFRESH_DAYS     min days between lookups per home (default 30)
  AVM_MAX_PER_RUN        max lookups per nightly run       (default 10)

A value pushed by Homebot (the webhook) is also real, so it is never overwritten within 45 days.
"""
import json
import os
import traceback
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from database import get_connection

API_URL = "https://api.rentcast.io/v1/avm/value"
SOURCE = "RentCast"


def provider_configured():
    return bool(os.environ.get("RENTCAST_API_KEY"))


def _int_env(name, default):
    try:
        return int(os.environ.get(name, default))
    except ValueError:
        return default


def _log(msg):
    print(f"[VALUES] {msg}")


def _http_get(url, headers, timeout=15):
    """Isolated so tests can replace it. Returns (status_code, parsed_json_or_None)."""
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, None
    except Exception as e:
        _log(f"request failed: {e}")
        return 0, None


def fetch_avm(address):
    """Ask RentCast for a value estimate. Returns {'price', 'low', 'high'} or {'error': code}."""
    key = os.environ.get("RENTCAST_API_KEY")
    if not key:
        return {"error": "no-key"}
    url = API_URL + "?" + urllib.parse.urlencode({"address": address})
    status, data = _http_get(url, {"X-Api-Key": key, "Accept": "application/json"})
    if status == 200 and data and data.get("price"):
        return {"price": float(data["price"]), "low": data.get("priceRangeLow"), "high": data.get("priceRangeHigh")}
    return {"error": status or "network"}


def _record_call(conn, property_id, status):
    conn.execute("INSERT INTO avm_calls (property_id, status) VALUES (?, ?)", (property_id, str(status)))
    conn.commit()


def refresh_property_value(user_id, property_id, min_days=None):
    """Refresh one home's value. Returns a status: 'ok', 'cooldown', 'cap', 'homebot', 'no-address',
    'no-key', 'not-found' or 'error'. Safe to call any time; it enforces the cost caps itself."""
    if not provider_configured():
        return "no-key"
    min_days = min_days if min_days is not None else _int_env("VALUE_REFRESH_DAYS", 30)
    cap = _int_env("RENTCAST_MONTHLY_CAP", 45)
    try:
        conn = get_connection()
        try:
            prop = conn.execute("SELECT id, address FROM properties WHERE id = ? AND user_id = ?", (property_id, user_id)).fetchone()
            if not prop or not (prop["address"] or "").strip():
                return "no-address"
            snap = conn.execute(
                "SELECT value_refresh_source, last_value_refresh FROM homeowner_snapshots WHERE user_id = ? AND property_id = ?",
                (user_id, property_id)).fetchone()
            if snap and snap["value_refresh_source"] == "Homebot" and snap["last_value_refresh"]:
                try:
                    if (datetime.now() - datetime.fromisoformat(snap["last_value_refresh"].replace("Z", ""))).days < 45:
                        return "homebot"
                except ValueError:
                    pass
            last = conn.execute(
                "SELECT created_at FROM avm_calls WHERE property_id = ? ORDER BY created_at DESC LIMIT 1", (property_id,)).fetchone()
            if last:
                age = conn.execute("SELECT julianday('now') - julianday(?)", (last["created_at"],)).fetchone()[0]
                if age is not None and age < min_days:
                    return "cooldown"
            used = conn.execute("SELECT COUNT(*) FROM avm_calls WHERE created_at >= datetime('now', '-30 days')").fetchone()[0]
            if used >= cap:
                _log(f"monthly cap reached ({used}/{cap}); skipping")
                return "cap"
            result = fetch_avm(prop["address"].strip())
            if "error" in result:
                code = result["error"]
                _record_call(conn, property_id, code)
                return "not-found" if code in (404, 400, 422) else "error"
            _record_call(conn, property_id, "ok")
        finally:
            conn.close()
        from database import upsert_homeowner_snapshot_for_property
        upsert_homeowner_snapshot_for_property(user_id=user_id, property_id=property_id, value_estimate=result["price"])
        conn = get_connection()
        try:
            conn.execute(
                """UPDATE homeowner_snapshots SET value_refresh_source = ?, last_value_refresh = ?, value_low = ?, value_high = ?
                   WHERE user_id = ? AND property_id = ?""",
                (SOURCE, datetime.now().isoformat(), result.get("low"), result.get("high"), user_id, property_id))
            conn.execute("UPDATE properties SET estimated_value = ? WHERE id = ?", (result["price"], property_id))
            conn.commit()
        finally:
            conn.close()
        _log(f"property {property_id}: ${result['price']:,.0f}")
        return "ok"
    except Exception:
        _log("refresh failed:\n" + traceback.format_exc())
        return "error"


def refresh_stale_values(max_calls=None):
    """Nightly job: refresh the homes whose values are oldest, within the caps."""
    if not provider_configured():
        return 0
    max_calls = max_calls if max_calls is not None else _int_env("AVM_MAX_PER_RUN", 10)
    done = 0
    try:
        conn = get_connection()
        try:
            rows = conn.execute(
                """SELECT p.id AS pid, p.user_id AS uid FROM properties p
                   LEFT JOIN homeowner_snapshots s ON s.user_id = p.user_id AND s.property_id = p.id
                   WHERE p.address IS NOT NULL AND TRIM(p.address) <> ''
                   ORDER BY COALESCE(s.last_value_refresh, '') ASC""").fetchall()
        finally:
            conn.close()
        for r in rows:
            if done >= max_calls:
                break
            status = refresh_property_value(r["uid"], r["pid"])
            if status == "cap":
                break
            if status in ("ok", "not-found", "error"):
                done += 1
    except Exception:
        _log("nightly refresh failed:\n" + traceback.format_exc())
    _log(f"nightly refresh: {done} lookups")
    return done


def describe_source(snapshot):
    """Plain-English line for the homeowner: where this number came from."""
    snap = snapshot or {}
    src = snap.get("value_refresh_source")
    when = (snap.get("last_value_refresh") or "")[:10]
    if src == SOURCE:
        rng = ""
        if snap.get("value_low") and snap.get("value_high"):
            rng = f" Likely range ${int(snap['value_low']):,} to ${int(snap['value_high']):,}."
        return f"Automated market estimate from RentCast, updated {when}.{rng}"
    if src == "Homebot":
        return f"Market estimate from Homebot, updated {when}."
    if snap.get("value_estimate"):
        return "This is the value you entered. Connect a live estimate to keep it current."
    return ""
