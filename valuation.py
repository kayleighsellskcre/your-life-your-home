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


def api_key():
    """The RentCast key, cleaned of the things that often get pasted along with it: spaces, line breaks,
    quote marks, or a leading 'X-Api-Key:' / 'Bearer '."""
    key = (os.environ.get("RENTCAST_API_KEY") or "").strip().strip("\"'").strip()
    for prefix in ("x-api-key:", "bearer "):
        if key.lower().startswith(prefix):
            key = key[len(prefix):].strip()
    return key


def provider_configured():
    return bool(api_key())


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
    key = api_key()
    if not key:
        return {"error": "no-key"}
    url = API_URL + "?" + urllib.parse.urlencode({"address": address})
    status, data = _http_get(url, {"X-Api-Key": key, "Accept": "application/json"})
    if status == 200 and data and data.get("price"):
        return {"price": float(data["price"]), "low": data.get("priceRangeLow"), "high": data.get("priceRangeHigh")}
    detail = ""
    if isinstance(data, dict):
        detail = str(data.get("message") or data.get("error") or "")[:200]
    return {"error": status or "network", "detail": detail}


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
                "SELECT created_at FROM avm_calls WHERE property_id = ? AND status IN ('ok', '404', '400', '422') "
                "ORDER BY created_at DESC LIMIT 1", (property_id,)).fetchone()  # a rejected key or a dropped connection never blocks a retry
            if last:
                age = conn.execute("SELECT julianday('now') - julianday(?)", (last["created_at"],)).fetchone()[0]
                if age is not None and age < min_days:
                    return "cooldown"
            used = conn.execute("SELECT COUNT(*) FROM avm_calls WHERE created_at >= datetime('now', '-30 days') AND status NOT IN ('401', '403', 'network', 'test-401', 'test-403', 'test-network', '0')").fetchone()[0]
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


ERROR_HELP = {
    "no-key": "No RentCast key is set. Add RENTCAST_API_KEY in your Railway variables.",
    401: "RentCast did not accept the key. Check RENTCAST_API_KEY in Railway for typos or extra spaces, and that the key is active in your RentCast account.",
    403: "Your RentCast key is not tied to an active plan yet. Open app.rentcast.io/app/api, pick a plan (there is a free starter level), then run the test again.",
    404: "RentCast could not find a value for that address. Check the street, city, state and ZIP.",
    400: "RentCast did not understand that address. Use the full form: street, city, state ZIP.",
    422: "RentCast did not understand that address. Use the full form: street, city, state ZIP.",
    429: "RentCast says you are over your plan's limit or sending too fast. Check your usage in your RentCast account.",
    "network": "The site could not reach RentCast. Try again in a minute.",
}


def describe_error(code):
    if code in ERROR_HELP:
        return ERROR_HELP[code]
    try:
        if int(code) >= 500:
            return "RentCast had a problem on its side. Try again later."
    except (TypeError, ValueError):
        pass
    return f"RentCast returned an unexpected answer ({code})."


SHORT_LABEL = {"401": "Key rejected", "403": "Key rejected", "404": "Address not found", "400": "Address not understood",
               "422": "Address not understood", "429": "Over the limit", "0": "No connection", "network": "No connection",
               "no-key": "No key", "cooldown": "Skipped (too soon)", "cap": "Skipped (limit)", "homebot": "Skipped (Homebot value)"}


def _recent_row(r):
    """Turn a stored lookup into a short label plus, for problems, a one-line explanation."""
    status = str(r.get("status") or "")
    code = status.replace("test-", "")
    r["is_test"] = status.startswith("test-")
    r["ok"] = code == "ok"
    r["label"] = "worked" if r["ok"] else SHORT_LABEL.get(code, "Problem")
    if r["ok"]:
        r["why"] = ""
    else:
        try:
            r["why"] = describe_error(int(code))
        except ValueError:
            r["why"] = describe_error(code)
    return r


def settings_summary():
    """The numbers the admin page shows, so nobody has to dig through logs."""
    cap = _int_env("RENTCAST_MONTHLY_CAP", 45)
    out = dict(configured=provider_configured(), cap=cap, refresh_days=_int_env("VALUE_REFRESH_DAYS", 30),
               per_run=_int_env("AVM_MAX_PER_RUN", 10), used=0, homes=0, refreshed=0, recent=[], by_status={})
    try:
        conn = get_connection()
        try:
            out["used"] = conn.execute("SELECT COUNT(*) FROM avm_calls WHERE created_at >= datetime('now', '-30 days') AND status NOT IN ('401', '403', 'network', 'test-401', 'test-403', 'test-network', '0')").fetchone()[0]
            out["homes"] = conn.execute("SELECT COUNT(*) FROM properties WHERE address IS NOT NULL AND TRIM(address) <> ''").fetchone()[0]
            out["refreshed"] = conn.execute("SELECT COUNT(*) FROM homeowner_snapshots WHERE value_refresh_source = ?", (SOURCE,)).fetchone()[0]
            for r in conn.execute("SELECT status, COUNT(*) n FROM avm_calls WHERE created_at >= datetime('now', '-30 days') GROUP BY status").fetchall():
                out["by_status"][r["status"]] = r["n"]
            out["recent"] = [_recent_row(dict(r)) for r in conn.execute(
                """SELECT c.created_at, c.status, p.address FROM avm_calls c LEFT JOIN properties p ON p.id = c.property_id
                   ORDER BY c.id DESC LIMIT 10""").fetchall()]
        finally:
            conn.close()
    except Exception:
        _log("summary failed:\n" + traceback.format_exc())
    out["remaining"] = max(0, cap - out["used"])
    return out


def test_address(address):
    """One real lookup for any address, to prove the connection works. Counts toward the monthly cap."""
    address = (address or "").strip()
    if not provider_configured():
        return dict(ok=False, message=describe_error("no-key"))
    if len(address) < 8:
        return dict(ok=False, message="Type a full address: street, city, state ZIP.")
    cap = _int_env("RENTCAST_MONTHLY_CAP", 45)
    conn = get_connection()
    try:
        used = conn.execute("SELECT COUNT(*) FROM avm_calls WHERE created_at >= datetime('now', '-30 days') AND status NOT IN ('401', '403', 'network', 'test-401', 'test-403', 'test-network', '0')").fetchone()[0]
        if used >= cap:
            return dict(ok=False, message=f"Your monthly limit of {cap} lookups is used up. Raise RENTCAST_MONTHLY_CAP after upgrading your plan.")
        result = fetch_avm(address)
        _record_call(conn, None, "test-ok" if "error" not in result else f"test-{result['error']}")
    finally:
        conn.close()
    if "error" in result:
        msg = describe_error(result["error"])
        code = result["error"]
        extra = f" (RentCast answered {code}" + (f": {result.get('detail')}" if result.get("detail") else "") + ")"
        return dict(ok=False, message=msg + extra)
    return dict(ok=True, price=result["price"], low=result.get("low"), high=result.get("high"),
                message="Connected. RentCast returned a value for that address.")
