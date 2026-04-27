"""Read endpoints + sync trigger for Fitbit data."""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as _date, timedelta

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
    """Log a food entry to Fitbit.

    Two modes:
      - Database food: pass food_id (and optionally unit_id, amount). Fitbit
        derives calories from its own database for that food + unit + amount.
      - Custom food: pass name + calories. Stored as a one-off entry.
    """
    food_id_raw = body.get("food_id")
    food_id = str(food_id_raw).strip() if food_id_raw not in (None, "") else ""

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

    params: dict
    if food_id:
        try:
            unit_id = int(body.get("unit_id") or 304)
        except (TypeError, ValueError):
            return error("unit_id must be an integer")
        try:
            amount = float(body.get("amount") or 1)
        except (TypeError, ValueError):
            return error("amount must be a number")
        if amount <= 0:
            return error("amount must be greater than 0")

        params = {
            "foodId":     food_id,
            "mealTypeId": str(meal_type_id),
            "unitId":     str(unit_id),
            "amount":     f"{amount:g}",
            "date":       log_date,
        }
    else:
        name = (body.get("name") or "").strip()
        if not name:
            return error("name or food_id is required")
        try:
            calories = int(body.get("calories") or 0)
        except (TypeError, ValueError):
            return error("calories must be an integer")
        if calories < 0 or calories > 10000:
            return error("calories must be between 0 and 10000")

        params = {
            "foodName":   name,
            "mealTypeId": str(meal_type_id),
            "unitId":     "304",        # generic serving
            "amount":     "1",
            "date":       log_date,
            "calories":   str(calories),
            "favorite":   "false",
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

    # Fire-and-forget the sync so we don't risk an API Gateway 29s timeout.
    # The frontend optimistically appends the newly-logged food to its local
    # state from the response below — Fitbit's authoritative copy lands a
    # few seconds later via the next GET /fitbit/today.
    if SYNC_FUNCTION:
        try:
            _lambda.invoke(
                FunctionName=SYNC_FUNCTION,
                InvocationType="Event",
                Payload=json.dumps({"user_ids": [user_id]}).encode(),
            )
        except Exception as exc:
            logger.warning("Async sync invoke failed: %s", exc)

    return ok({
        "logged": True,
        "food":   data.get("foodLog") or {},
    })


def get_history(user_id: str, query_params: dict) -> dict:
    """Return per-day Fitbit data for the trailing N days (default 30, max 365).

    Excludes today by default unless include_today=1, since today is still
    mutable. Used by the dashboard's history charts.
    """
    qp = query_params or {}
    try:
        days = int(qp.get("days") or 30)
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 365))
    include_today = (qp.get("include_today") or "").lower() in ("1", "true", "yes")

    today = _date.today()
    cutoff = (today - timedelta(days=days)).isoformat()

    resp = db.get_table(DATA_TABLE).query(
        KeyConditionExpression=(
            Key("user_id").eq(user_id) & Key("log_date").gte(cutoff)
        ),
        ScanIndexForward=True,
    )
    rows = []
    for item in resp.get("Items") or []:
        if not include_today and item.get("log_date") == today.isoformat():
            continue
        item.pop("user_id", None)
        rows.append({
            "log_date":       item.get("log_date"),
            "steps":          int(item.get("steps", 0) or 0),
            "calories_in":    int(item.get("calories_in", 0) or 0),
            "calories_out":   int(item.get("calories_out", 0) or 0),
            "distance_mi":    float(item.get("distance_mi", 0) or 0),
            "active_minutes": int(item.get("active_minutes", 0) or 0),
            "weight":         float(item.get("weight")) if item.get("weight") not in (None, "") else None,
            "sleep_minutes":  int(((item.get("sleep") or {}).get("minutes_asleep")) or 0),
            "sleep_efficiency": int(((item.get("sleep") or {}).get("efficiency")) or 0),
            "finalized":      bool(item.get("finalized", False)),
        })
    return ok({"days": days, "rows": rows})


def search_foods(user_id: str, query_params: dict) -> dict:
    """Search Fitbit's public food database by query string.

    Returns a list of foods with their default serving size + calories so the
    frontend can present an autocomplete dropdown the user can pick from.
    """
    qp = query_params or {}
    q = (qp.get("q") or "").strip()
    if len(q) < 2:
        return ok({"foods": []})

    tokens = oauth.get_tokens(user_id)
    if not tokens:
        return error("Fitbit not connected", status=400)
    access_token = oauth.refresh_if_needed(user_id, tokens)
    if not access_token:
        return error("Could not refresh Fitbit token", status=502)

    path = f"/1/foods/search.json?{urllib.parse.urlencode({'query': q})}"
    req = urllib.request.Request(
        f"{FITBIT_API_BASE}{path}",
        headers={
            "Authorization":   f"Bearer {access_token}",
            "Accept-Language": "en_US",
        },
        method="GET",
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
        logger.warning("Fitbit food search failed: %s %s — %s", exc.code, exc.reason, body_text)
        return error(f"Fitbit rejected the request ({exc.code})", status=502)
    except Exception as exc:
        logger.error("Fitbit food search error: %s", exc)
        return error("Could not reach Fitbit", status=502)

    foods = []
    for item in (data.get("foods") or [])[:25]:
        unit = item.get("defaultUnit") or {}
        foods.append({
            "food_id":     str(item.get("foodId") or ""),
            "name":        item.get("name") or "",
            "brand":       item.get("brand") or "",
            "calories":    int(item.get("calories") or 0),
            "amount":      float(item.get("defaultServingSize") or 1),
            "unit_id":     int(unit.get("id") or 304),
            "unit":        unit.get("name") or "",
            "access_level": item.get("accessLevel") or "",
        })
    return ok({"foods": foods, "query": q})


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
