"""Fitbit sync Lambda.

Triggered every 30 min by EventBridge, or on-demand via direct invoke.
For each connected user, refreshes tokens if needed, fetches today's
activity / nutrition / weight / sleep summary, and writes the result to
the fitbit_data table.

Direct-invoke payload:
  {"user_ids": ["<uid>", ...]}  — sync only these users (skips Fitbit toggle check).
"""

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import boto3

logger = logging.getLogger()
logger.setLevel(logging.INFO)

CLIENT_ID         = os.environ.get("FITBIT_CLIENT_ID", "")
CLIENT_SECRET     = os.environ.get("FITBIT_CLIENT_SECRET", "")
TOKENS_TABLE      = os.environ["FITBIT_TOKENS_TABLE"]
DATA_TABLE        = os.environ["FITBIT_DATA_TABLE"]
SETTINGS_TABLE    = os.environ["SETTINGS_TABLE"]

_dynamodb = boto3.resource("dynamodb")

API_BASE  = "https://api.fitbit.com"
TOKEN_URL = f"{API_BASE}/oauth2/token"

# Refresh access token if it expires within this many seconds.
REFRESH_LEEWAY_SECONDS = 300


def lambda_handler(event, context):
    payload  = event if isinstance(event, dict) else {}
    user_ids = payload.get("user_ids")

    if user_ids:
        targets = [uid for uid in user_ids if isinstance(uid, str) and uid]
        logger.info("Direct sync for %d user(s)", len(targets))
    else:
        targets = _users_with_fitbit_enabled()
        logger.info("Scheduled sync — %d enabled user(s)", len(targets))

    synced = 0
    for user_id in targets:
        try:
            if _sync_user(user_id):
                synced += 1
        except Exception as exc:
            logger.exception("Sync failed for user %s: %s", user_id, exc)

    return {"synced": synced, "total": len(targets)}


def _users_with_fitbit_enabled() -> list[str]:
    """Scan settings table for users whose fitbit.enabled flag is True."""
    table = _dynamodb.Table(SETTINGS_TABLE)
    users: list[str] = []
    resp = table.scan()
    while True:
        for item in resp.get("Items", []):
            fitbit = item.get("fitbit") or {}
            if isinstance(fitbit, dict) and fitbit.get("enabled"):
                uid = item.get("user_id")
                if uid:
                    users.append(uid)
        if "LastEvaluatedKey" not in resp:
            break
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
    return users


def _sync_user(user_id: str) -> bool:
    tokens_table = _dynamodb.Table(TOKENS_TABLE)
    item = tokens_table.get_item(Key={"user_id": user_id}).get("Item")
    if not item:
        logger.info("No Fitbit tokens for user %s — skipping", user_id)
        return False

    access_token = _ensure_fresh_access_token(item)
    if not access_token:
        return False

    log_date = _user_today(access_token)
    summary  = _fetch_summary(access_token, log_date)
    summary  = _to_dynamo_safe(summary)
    summary.update({
        "user_id":   user_id,
        "log_date":  log_date,
        "synced_at": int(time.time()),
    })
    _dynamodb.Table(DATA_TABLE).put_item(Item=summary)
    return True


def _user_today(access_token: str) -> str:
    """Return today's date in the user's Fitbit profile timezone (YYYY-MM-DD)."""
    profile = _fitbit_get(access_token, "/1/user/-/profile.json")
    tz_name = (((profile or {}).get("user") or {}).get("timezone")) or ""
    if tz_name:
        try:
            return datetime.now(ZoneInfo(tz_name)).date().isoformat()
        except ZoneInfoNotFoundError:
            pass
    return datetime.now(timezone.utc).date().isoformat()


def _to_dynamo_safe(value):
    """Recursively convert floats to Decimal so put_item accepts the payload."""
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, dict):
        return {k: _to_dynamo_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo_safe(v) for v in value]
    return value


def _ensure_fresh_access_token(item: dict) -> str | None:
    """Return a usable access token, refreshing it if it is close to expiry."""
    expires_at = int(item.get("expires_at", 0))
    if expires_at - int(time.time()) > REFRESH_LEEWAY_SECONDS:
        return item.get("access_token", "")

    refresh_token = item.get("refresh_token", "")
    user_id       = item.get("user_id", "")
    if not refresh_token:
        return None

    refreshed = _token_request({
        "client_id":     CLIENT_ID,
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
    })
    if refreshed is None:
        logger.warning("Token refresh failed for user %s", user_id)
        return None

    new_item = {
        **item,
        "access_token":  refreshed.get("access_token", ""),
        "refresh_token": refreshed.get("refresh_token", refresh_token),
        "expires_at":    int(time.time()) + int(refreshed.get("expires_in", 28800)),
        "scope":         refreshed.get("scope", item.get("scope", "")),
        "updated_at":    _now_iso(),
    }
    _dynamodb.Table(TOKENS_TABLE).put_item(Item=new_item)
    return new_item["access_token"]


def _fetch_summary(access_token: str, log_date: str) -> dict:
    """Aggregate the four data points the Fitbit page shows. Each call is best-effort.

    Sends Accept-Language: en_US so Fitbit returns imperial units (weight in
    pounds, distance in miles) — Memoire's audience is US-based.
    """
    out: dict = {}

    # log_date is already in the user's profile timezone, computed in _user_today.
    activity = _fitbit_get(access_token, f"/1/user/-/activities/date/{log_date}.json")
    if activity:
        summary = activity.get("summary") or {}
        out["steps"]        = int(summary.get("steps", 0) or 0)
        out["calories_out"] = int(summary.get("caloriesOut", 0) or 0)
        out["distance_mi"]  = _activity_distance(summary.get("distances") or [])
        out["active_minutes"] = int(
            (summary.get("veryActiveMinutes") or 0)
            + (summary.get("fairlyActiveMinutes") or 0)
        )
        logger.info(
            "Fitbit activity: steps=%s, calories_out=%s, distance_mi=%s",
            out.get("steps"), out.get("calories_out"), out.get("distance_mi"),
        )
    else:
        logger.warning("Fitbit activity endpoint returned no data")

    # Query food for both the user's local "today" and the next day. Fitbit's
    # mobile app sometimes files entries under the UTC date instead of the
    # user-timezone date, so we union both responses and dedupe by logId.
    items: dict[str, dict] = {}
    calories_in_total = 0
    water_total       = 0.0
    try:
        next_day = (datetime.fromisoformat(log_date).date() + timedelta(days=1)).isoformat()
    except ValueError:
        next_day = log_date

    for date_str in (log_date, next_day):
        food = _fitbit_get(access_token, f"/1/user/-/foods/log/date/{date_str}.json")
        if not food:
            continue
        food_summary = food.get("summary") or {}
        calories_in_total += int(food_summary.get("calories", 0) or 0)
        water_total       += float(food_summary.get("water", 0) or 0)
        for entry in food.get("foods") or []:
            log_id = str(entry.get("logId") or "")
            if log_id and log_id in items:
                continue
            logged = entry.get("loggedFood") or {}
            nutr   = entry.get("nutritionalValues") or {}
            unit   = logged.get("unit") or {}
            items[log_id or f"_{len(items)}"] = {
                "log_id":       log_id,
                "name":         logged.get("name") or "",
                "brand":        logged.get("brand") or "",
                "calories":     int(nutr.get("calories") or 0),
                "amount":       float(logged.get("amount") or 0),
                "unit":         unit.get("name") or "",
                "meal_type_id": int(logged.get("mealTypeId") or 0),
                "logged_at":    logged.get("logDate") or "",
            }

    if items or calories_in_total or water_total:
        out["calories_in"]   = calories_in_total
        out["food_water_oz"] = water_total
        out["foods"]         = list(items.values())

    # Weight: a single date often has no entry. Pull the last 30 days, take latest.
    weight = _fitbit_get(access_token, f"/1/user/-/body/log/weight/date/{log_date}/30d.json")
    if weight:
        entries = weight.get("weight") or []
        if entries:
            latest = max(entries, key=lambda e: (e.get("date", ""), e.get("time", "")))
            try:
                out["weight"] = float(latest.get("weight", 0) or 0)
                out["weight_unit"]  = "lb"
                out["weight_date"]  = latest.get("date", "")
            except (TypeError, ValueError):
                pass

    # Sleep: a session that ended this morning is often filed under today, but
    # if the API hasn't rolled over yet, fall back to yesterday.
    sleep_entry = _fetch_main_sleep(access_token, log_date)
    if sleep_entry:
        out["sleep"] = sleep_entry

    return out


def _fetch_main_sleep(access_token: str, log_date: str) -> dict | None:
    candidates = [log_date]
    try:
        prev = (datetime.fromisoformat(log_date).date() - timedelta(days=1)).isoformat()
        candidates.append(prev)
    except ValueError:
        pass

    for date_str in candidates:
        sleep = _fitbit_get(access_token, f"/1.2/user/-/sleep/date/{date_str}.json")
        if not sleep:
            continue
        sleeps = sleep.get("sleep") or []
        main   = next((s for s in sleeps if s.get("isMainSleep")), sleeps[0] if sleeps else None)
        if not main:
            continue
        return {
            "duration_min":     int((main.get("duration", 0) or 0) // 60000),
            "efficiency":       int(main.get("efficiency", 0) or 0),
            "minutes_asleep":   int(main.get("minutesAsleep", 0) or 0),
            "minutes_awake":    int(main.get("minutesAwake", 0) or 0),
            "start_time":       main.get("startTime", ""),
            "end_time":         main.get("endTime", ""),
            "date":             main.get("dateOfSleep", date_str),
        }
    return None


def _activity_distance(distances: list) -> float:
    for d in distances:
        if d.get("activity") == "total":
            try:
                return float(d.get("distance", 0) or 0)
            except (TypeError, ValueError):
                return 0.0
    return 0.0


def _fitbit_get(access_token: str, path: str) -> dict | None:
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        headers={
            "Authorization":   f"Bearer {access_token}",
            "Accept-Language": "en_US",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 — fixed Fitbit HTTPS endpoint
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode()[:300]
        except Exception:
            pass
        logger.warning("Fitbit GET %s failed: %s %s — %s", path, exc.code, exc.reason, body)
        return None
    except Exception as exc:
        logger.error("Fitbit GET %s error: %s", path, exc)
        return None


def _token_request(params: dict) -> dict | None:
    payload = urllib.parse.urlencode(params).encode()
    basic   = base64.b64encode(f"{CLIENT_ID}:{CLIENT_SECRET}".encode()).decode()
    req = urllib.request.Request(
        TOKEN_URL,
        data=payload,
        headers={
            "Authorization": f"Basic {basic}",
            "Content-Type":  "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 — fixed Fitbit HTTPS endpoint
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        logger.warning("Fitbit token refresh failed: %s %s", exc.code, exc.reason)
        return None
    except Exception as exc:
        logger.error("Fitbit token refresh error: %s", exc)
        return None


def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).isoformat()
