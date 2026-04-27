"""Read endpoints + sync trigger for Fitbit data."""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as _date

import boto3
from boto3.dynamodb.conditions import Key

import db
import oauth
from response import ok, error, not_found

DATA_TABLE       = os.environ["FITBIT_DATA_TABLE"]
SYNC_FUNCTION    = os.environ.get("FITBIT_SYNC_FUNCTION", "")

_lambda = boto3.client("lambda")
logger = logging.getLogger()

FITBIT_API_BASE = "https://api.fitbit.com"

MEAL_TYPE_IDS = {1, 2, 3, 4, 5, 7}  # Breakfast, Morning Snack, Lunch, Afternoon Snack, Dinner, Anytime


def _today_iso() -> str:
    return _date.today().isoformat()


def get_today(user_id: str) -> dict:
    """Return the most recent Fitbit data entry for the user.

    The sync Lambda stores entries keyed by the user's local date (derived
    from their Fitbit profile timezone), not UTC. The latest log_date is
    usually correct, but a stale row from a different day can outrank
    the freshest one lexicographically (e.g. 2026-04-27 zeros vs
    2026-04-26 today data when the user's TZ is behind UTC), so we pull
    the last few entries and pick the one with the highest synced_at.
    """
    resp = db.get_table(DATA_TABLE).query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,
        Limit=7,
    )
    items = resp.get("Items") or []
    if not items:
        return ok({"log_date": _today_iso(), "synced": False})
    item = max(items, key=lambda i: int(i.get("synced_at", 0) or 0))
    item.pop("user_id", None)
    return ok(item)


def get_status(user_id: str) -> dict:
    tokens = oauth.get_tokens(user_id)
    return ok({
        "connected": bool(tokens),
        "fitbit_user_id": (tokens or {}).get("fitbit_user_id", ""),
        "connected_at":   (tokens or {}).get("connected_at", ""),
    })


def disconnect(user_id: str) -> dict:
    tokens = oauth.get_tokens(user_id)
    if not tokens:
        return not_found("Fitbit connection")
    oauth.delete_tokens(user_id)
    return ok({"disconnected": True})


def log_food(user_id: str, body: dict) -> dict:
    """Quick-add a custom food entry directly to Fitbit's food log."""
    name = (body.get("name") or "").strip()
    if not name:
        return error("name is required")

    try:
        calories = int(body.get("calories") or 0)
    except (TypeError, ValueError):
        return error("calories must be an integer")
    if calories < 0 or calories > 10000:
        return error("calories must be between 0 and 10000")

    try:
        meal_type_id = int(body.get("meal_type_id") or 7)
    except (TypeError, ValueError):
        return error("meal_type_id must be an integer")
    if meal_type_id not in MEAL_TYPE_IDS:
        return error("meal_type_id must be one of 1,2,3,4,5,7")

    log_date = (body.get("log_date") or "").strip()
    if not log_date:
        log_date = _today_iso()

    tokens = oauth.get_tokens(user_id)
    if not tokens:
        return error("Fitbit not connected", status=400)

    access_token = oauth.refresh_if_needed(user_id, tokens)
    if not access_token:
        return error("Could not refresh Fitbit token", status=502)

    params = {
        "foodName":     name,
        "mealTypeId":   str(meal_type_id),
        "unitId":       "304",        # serving — Fitbit's generic unit
        "amount":       "1",
        "date":         log_date,
        "calories":     str(calories),
        "favorite":     "false",
    }
    payload = urllib.parse.urlencode(params).encode()
    req = urllib.request.Request(
        f"{FITBIT_API_BASE}/1/user/-/foods/log.json",
        data=payload,
        headers={
            "Authorization":   f"Bearer {access_token}",
            "Content-Type":    "application/x-www-form-urlencoded",
            "Accept-Language": "en_US",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310 — fixed Fitbit HTTPS endpoint
            data = json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = ""
        try:
            body_text = exc.read().decode()[:300]
        except Exception:
            pass
        logger.warning("Fitbit food log failed: %s %s — %s", exc.code, exc.reason, body_text)
        return error(f"Fitbit rejected the request ({exc.code})", status=502)
    except Exception as exc:
        logger.error("Fitbit food log error: %s", exc)
        return error("Could not reach Fitbit", status=502)

    # Run the sync synchronously so the next GET /fitbit/today reflects the
    # new entry. Fire-and-forget would beat the page's reload timer.
    if SYNC_FUNCTION:
        try:
            _lambda.invoke(
                FunctionName=SYNC_FUNCTION,
                InvocationType="RequestResponse",
                Payload=json.dumps({"user_ids": [user_id]}).encode(),
            )
        except Exception as exc:
            logger.warning("Synchronous sync invoke failed: %s", exc)

    return ok({
        "logged": True,
        "food":   data.get("foodLog") or data,
    })


def sync_now(user_id: str) -> dict:
    """Async-invoke the sync Lambda for a single user."""
    if not SYNC_FUNCTION:
        return error("Sync function not configured", status=503)
    if not oauth.get_tokens(user_id):
        return error("Fitbit not connected", status=400)

    _lambda.invoke(
        FunctionName=SYNC_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps({"user_ids": [user_id]}).encode(),
    )
    return ok({"queued": True})
