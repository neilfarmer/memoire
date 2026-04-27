"""Health log CRUD: combined exercise + nutrition + activity totals.

Daily-log shape:
  {
    user_id, log_date,
    exercises: [...],
    foods:     [{id, source, name, brand, calories, amount, unit,
                 meal_type_id, fitbit_log_id, logged_at, ...}],
    steps, distance_mi, active_minutes, calories_out,
    weight, weight_unit, weight_date,
    sleep: {minutes_asleep, efficiency, ...},
    notes, created_at, updated_at,
  }
"""

import os
import re
import uuid
from datetime import date as _date, timedelta
from decimal import Decimal, InvalidOperation

from boto3.dynamodb.conditions import Key

from db import get_table, query_by_user
from response import ok, no_content, error, not_found
from utils import now_iso, validate_date

TABLE_NAME = os.environ["TABLE_NAME"]

EXERCISE_TYPES = {"strength", "cardio", "mobility"}

# Source attribution. Health is a vendor-agnostic interface; any plugin
# (fitbit, apple_health, google_fit, ...) can feed entries by tagging their
# records with `source: "<plugin>"`. Manual UI entries default to "manual";
# the AI assistant uses "assistant". The set is open — new vendors plug in
# without code changes.
SOURCE_RE = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
DEFAULT_SOURCE = "manual"

MEAL_TYPE_IDS  = {1, 2, 3, 4, 5, 7}
NUMERIC_FOOD_FIELDS = (
    "calories",
    "protein",   "protein_g",
    "carbs",     "carbs_g",
    "fat",       "fat_g",
    "fiber",     "fiber_g",
    "sugar",     "sugar_g",
    "sodium",    "sodium_mg",
)
ACTIVITY_NUMERIC_FIELDS = (
    "steps", "active_minutes", "calories_out",
    "distance_mi", "weight",
)


def _table():
    return get_table(TABLE_NAME)


def _to_decimal(val):
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _exercise_totals(exercises: list) -> dict:
    """Compute rollup metrics across a day's exercises."""
    total_volume = Decimal("0")
    total_duration = Decimal("0")
    total_distance = Decimal("0")
    total_sets = 0
    for ex in exercises or []:
        dur = _to_decimal(ex.get("duration_min"))
        if dur is not None:
            total_duration += dur
        dist = _to_decimal(ex.get("distance_km"))
        if dist is not None:
            total_distance += dist
        sets_val = ex.get("sets")
        if not isinstance(sets_val, list):
            continue
        for s in sets_val:
            if not isinstance(s, dict):
                continue
            total_sets += 1
            reps = _to_decimal(s.get("reps"))
            weight = _to_decimal(s.get("weight"))
            if reps is not None and weight is not None:
                total_volume += reps * weight
    return {
        "total_volume":   total_volume,
        "total_duration": total_duration,
        "total_distance": total_distance,
        "total_sets":     total_sets,
    }


def _summary(item: dict) -> dict:
    exercises = item.get("exercises", [])
    foods     = item.get("foods", [])
    totals    = _exercise_totals(exercises)
    food_cal  = sum(int((f.get("calories") or 0)) for f in foods)
    return {
        "user_id":        item["user_id"],
        "log_date":       item["log_date"],
        "exercise_count": len(exercises),
        "food_count":     len(foods),
        "total_volume":   totals["total_volume"],
        "total_duration": totals["total_duration"],
        "total_distance": totals["total_distance"],
        "calories_in":    food_cal,
        "calories_out":   int(item.get("calories_out") or 0),
        "steps":          int(item.get("steps") or 0),
        "weight":         item.get("weight"),
        "sleep_minutes":  int((item.get("sleep") or {}).get("minutes_asleep") or 0),
        "notes":          item.get("notes", ""),
        "created_at":     item.get("created_at", ""),
        "updated_at":     item.get("updated_at", ""),
    }


def _normalize_food(f: dict) -> dict | None:
    """Validate a food entry. Returns sanitized dict or None if invalid."""
    name = (f.get("name") or "").strip()
    if not name:
        return None

    out: dict = {
        "id":   f.get("id") or str(uuid.uuid4()),
        "name": name,
    }

    source = (f.get("source") or DEFAULT_SOURCE).strip().lower()
    out["source"] = source if SOURCE_RE.match(source) else DEFAULT_SOURCE

    brand = (f.get("brand") or "").strip()
    if brand:
        out["brand"] = brand

    for field in NUMERIC_FOOD_FIELDS:
        if field in f:
            val = _to_decimal(f[field])
            if val is not None and val >= 0:
                out[field] = val

    amount = _to_decimal(f.get("amount"))
    if amount is not None and amount > 0:
        out["amount"] = amount

    unit = (f.get("unit") or "").strip()
    if unit:
        out["unit"] = unit

    try:
        meal_type_id = int(f.get("meal_type_id") or 0)
        if meal_type_id in MEAL_TYPE_IDS:
            out["meal_type_id"] = meal_type_id
    except (TypeError, ValueError):
        pass

    for k in ("fitbit_log_id", "logged_at"):
        v = f.get(k)
        if v not in (None, ""):
            out[k] = str(v)

    return out


def _normalize_activity_totals(body: dict) -> dict:
    """Pick + coerce just the activity scalar fields the caller wants to set."""
    out: dict = {}
    for field in ACTIVITY_NUMERIC_FIELDS:
        if field in body and body[field] not in (None, ""):
            val = _to_decimal(body[field])
            if val is not None and val >= 0:
                out[field] = val
    if "weight_unit" in body:
        wu = (body.get("weight_unit") or "").strip().lower()
        if wu in ("lb", "kg"):
            out["weight_unit"] = wu
    if "weight_date" in body:
        wd = (body.get("weight_date") or "").strip()
        if wd:
            out["weight_date"] = wd
    sleep = body.get("sleep")
    if isinstance(sleep, dict):
        clean = {}
        for k in ("duration_min", "minutes_asleep", "minutes_awake", "efficiency"):
            if k in sleep:
                v = _to_decimal(sleep[k])
                if v is not None and v >= 0:
                    clean[k] = v
        for k in ("start_time", "end_time", "date"):
            if sleep.get(k):
                clean[k] = str(sleep[k])
        if clean:
            out["sleep"] = clean
    return out


def _normalize_exercise(ex: dict) -> dict | None:
    """Validate + coerce one exercise entry. Returns sanitized dict or None if invalid."""
    name = (ex.get("name") or "").strip()
    if not name:
        return None

    out: dict = {
        "id":   ex.get("id") or str(uuid.uuid4()),
        "name": name,
    }

    ex_type = ex.get("type")
    if ex_type in EXERCISE_TYPES:
        out["type"] = ex_type

    dur = _to_decimal(ex.get("duration_min"))
    if dur is not None and dur >= 0:
        out["duration_min"] = dur

    dist = _to_decimal(ex.get("distance_km"))
    if dist is not None and dist >= 0:
        out["distance_km"] = dist

    intensity = _to_decimal(ex.get("intensity"))
    if intensity is not None and 0 <= intensity <= 10:
        out["intensity"] = intensity

    muscle_groups = ex.get("muscle_groups")
    if isinstance(muscle_groups, list):
        out["muscle_groups"] = [str(m).strip() for m in muscle_groups if str(m).strip()]

    sets = []
    for s in ex.get("sets") or []:
        reps = _to_decimal(s.get("reps"))
        weight = _to_decimal(s.get("weight"))
        if (reps is not None and reps < 0) or (weight is not None and weight < 0):
            continue
        clean = {}
        if reps   is not None: clean["reps"] = reps
        if weight is not None: clean["weight"] = weight
        sets.append(clean)
    out["sets"] = sets

    return out


def list_logs(user_id: str) -> dict:
    items = sorted(query_by_user(_table(), user_id), key=lambda x: x["log_date"], reverse=True)
    return ok([_summary(i) for i in items])


def get_log(user_id: str, log_date: str) -> dict:
    err = validate_date(log_date)
    if err:
        return error(err)

    table = _table()
    resp  = table.get_item(Key={"user_id": user_id, "log_date": log_date})
    item  = resp.get("Item")
    if not item:
        return not_found("Log")
    return ok(item)


def upsert_log(user_id: str, log_date: str, body: dict) -> dict:
    err = validate_date(log_date)
    if err:
        return error(err)

    table    = _table()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item") or {}

    exercises = [c for c in (_normalize_exercise(e) for e in (body.get("exercises") or [])) if c]
    foods     = [c for c in (_normalize_food(f)     for f in (body.get("foods")     or [])) if c]

    item = {
        **existing,
        "user_id":    user_id,
        "log_date":   log_date,
        "exercises":  exercises,
        "foods":      foods,
        "notes":      body.get("notes", existing.get("notes", "")),
        "created_at": existing.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    item.update(_normalize_activity_totals(body))
    table.put_item(Item=item)
    return ok(item)


def add_food(user_id: str, log_date: str, body: dict) -> dict:
    """Append a single food entry to the day's log. Creates the row if needed."""
    err = validate_date(log_date)
    if err:
        return error(err)

    food = _normalize_food(body or {})
    if food is None:
        return error("name is required")

    table    = _table()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item") or {}
    foods    = list(existing.get("foods") or [])
    foods.append(food)

    item = {
        **existing,
        "user_id":    user_id,
        "log_date":   log_date,
        "foods":      foods,
        "exercises":  list(existing.get("exercises") or []),
        "created_at": existing.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    table.put_item(Item=item)
    return ok({"food": food, "log": item})


def delete_food(user_id: str, log_date: str, food_id: str) -> dict:
    err = validate_date(log_date)
    if err:
        return error(err)
    if not food_id:
        return error("food_id required")

    table    = _table()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    if not existing:
        return not_found("Log")
    foods = list(existing.get("foods") or [])
    new_foods = [f for f in foods if f.get("id") != food_id]
    if len(new_foods) == len(foods):
        return not_found("Food")
    existing["foods"]      = new_foods
    existing["updated_at"] = now_iso()
    table.put_item(Item=existing)
    return no_content()


def set_activity_totals(user_id: str, log_date: str, body: dict) -> dict:
    """Upsert just the activity scalar fields (steps/sleep/weight/etc).

    Used by the Fitbit nightly push and any user-driven manual edit. Does not
    touch foods or exercises arrays.
    """
    err = validate_date(log_date)
    if err:
        return error(err)
    table    = _table()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item") or {}
    item = {
        **existing,
        "user_id":    user_id,
        "log_date":   log_date,
        "exercises":  list(existing.get("exercises") or []),
        "foods":      list(existing.get("foods") or []),
        "created_at": existing.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    item.update(_normalize_activity_totals(body))
    table.put_item(Item=item)
    return ok(item)


def merge_source_foods(user_id: str, log_date: str, source: str, foods: list) -> dict:
    """Replace foods tagged with the given source. Other sources untouched.

    Vendor-agnostic: any plugin (fitbit, apple_health, google_fit, ...) calls
    this with its own source identifier. Manual + other-vendor entries are
    preserved verbatim.
    """
    err = validate_date(log_date)
    if err:
        return error(err)
    src = (source or "").strip().lower()
    if not SOURCE_RE.match(src):
        return error("source must match [a-z][a-z0-9_]{0,31}")

    table    = _table()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item") or {}
    keep     = [f for f in (existing.get("foods") or []) if f.get("source") != src]
    new_src  = []
    for raw in foods or []:
        food = dict(raw)
        food["source"] = src
        clean = _normalize_food(food)
        if clean is not None:
            new_src.append(clean)

    item = {
        **existing,
        "user_id":    user_id,
        "log_date":   log_date,
        "foods":      keep + new_src,
        "exercises":  list(existing.get("exercises") or []),
        "created_at": existing.get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    table.put_item(Item=item)
    return ok(item)


# Backwards compatibility wrapper for callers using the old name. Removable
# once nothing references it.
def merge_fitbit_foods(user_id: str, log_date: str, fitbit_foods: list) -> dict:
    return merge_source_foods(user_id, log_date, "fitbit", fitbit_foods)


def delete_log(user_id: str, log_date: str) -> dict:
    err = validate_date(log_date)
    if err:
        return error(err)

    table    = _table()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    if not existing:
        return not_found("Log")
    table.delete_item(Key={"user_id": user_id, "log_date": log_date})
    return no_content()


# ── Aggregation ───────────────────────────────────────────────────────────────

def summary(user_id: str, query_params: dict) -> dict:
    """Weekly/monthly rollup across [from, to] inclusive. Defaults to last 30 days."""
    today = _date.today()
    date_from = (query_params or {}).get("from") or (today - timedelta(days=29)).isoformat()
    date_to   = (query_params or {}).get("to")   or today.isoformat()
    for d in (date_from, date_to):
        err = validate_date(d)
        if err:
            return error(f"Invalid date: {d}")

    items = [i for i in query_by_user(_table(), user_id)
             if date_from <= i.get("log_date", "") <= date_to]

    total_volume   = Decimal("0")
    total_duration = Decimal("0")
    total_distance = Decimal("0")
    workout_days   = 0
    exercise_count = 0
    type_counts: dict[str, int] = {}

    for item in items:
        ex_list = item.get("exercises") or []
        if not ex_list:
            continue
        workout_days += 1
        exercise_count += len(ex_list)
        t = _exercise_totals(ex_list)
        total_volume   += t["total_volume"]
        total_duration += t["total_duration"]
        total_distance += t["total_distance"]
        for ex in ex_list:
            if ex.get("type") in EXERCISE_TYPES:
                type_counts[ex["type"]] = type_counts.get(ex["type"], 0) + 1

    # Consecutive-day streak ending today (or the most recent logged day within range)
    logged_dates = {i["log_date"] for i in items if (i.get("exercises") or [])}
    streak = 0
    cursor = today
    while cursor.isoformat() in logged_dates:
        streak += 1
        cursor -= timedelta(days=1)

    return ok({
        "from":           date_from,
        "to":             date_to,
        "workout_days":   workout_days,
        "exercise_count": exercise_count,
        "total_volume":   total_volume,
        "total_duration": total_duration,
        "total_distance": total_distance,
        "type_counts":    type_counts,
        "streak_days":    streak,
    })


def get_history(user_id: str, query_params: dict) -> dict:
    """Return per-day rollup over the trailing N days for the trend charts.

    Excludes today by default unless include_today=1 (today is still mutable).
    """
    qp = query_params or {}
    try:
        days = int(qp.get("days") or 30)
    except (TypeError, ValueError):
        days = 30
    days = max(1, min(days, 365))
    include_today = (qp.get("include_today") or "").lower() in ("1", "true", "yes")

    today  = _date.today()
    cutoff = (today - timedelta(days=days)).isoformat()
    table  = _table()

    items: list[dict] = []
    params: dict = {
        "KeyConditionExpression":
            Key("user_id").eq(user_id) & Key("log_date").gte(cutoff),
        "ScanIndexForward": True,
    }
    while True:
        resp = table.query(**params)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    rows = []
    for item in items:
        if not include_today and item.get("log_date") == today.isoformat():
            continue
        foods = item.get("foods") or []
        cal_in = sum(int(f.get("calories") or 0) for f in foods)
        sleep = item.get("sleep") or {}
        rows.append({
            "log_date":         item.get("log_date"),
            "steps":            int(item.get("steps", 0) or 0),
            "calories_in":      cal_in,
            "calories_out":     int(item.get("calories_out", 0) or 0),
            "distance_mi":      float(item.get("distance_mi", 0) or 0),
            "active_minutes":   int(item.get("active_minutes", 0) or 0),
            "weight":           float(item.get("weight")) if item.get("weight") not in (None, "") else None,
            "sleep_minutes":    int(sleep.get("minutes_asleep") or 0),
            "sleep_efficiency": int(sleep.get("efficiency") or 0),
            "food_count":       len(foods),
            "exercise_count":   len(item.get("exercises") or []),
            "finalized":        bool(item.get("finalized", False)),
        })
    return ok({"days": days, "rows": rows})


def recent_exercises(user_id: str, query_params: dict) -> dict:
    """Distinct exercises from the most recent N days, optionally filtered by query.

    Each result includes the last-used date and the most recent configuration
    (sets, duration_min, distance_km, type, muscle_groups) so the caller can
    repeat a previous workout by copying the payload.
    """
    qp = query_params or {}
    try:
        days = max(1, min(int(qp.get("days", 90)), 365))
    except (TypeError, ValueError):
        days = 90
    try:
        limit = max(1, min(int(qp.get("limit", 20)), 100))
    except (TypeError, ValueError):
        limit = 20
    q = (qp.get("q") or "").strip().lower()

    cutoff = (_date.today() - timedelta(days=days)).isoformat()
    items  = sorted(
        (i for i in query_by_user(_table(), user_id) if i.get("log_date", "") >= cutoff),
        key=lambda x: x["log_date"],
        reverse=True,
    )

    seen: dict[str, dict] = {}
    for item in items:
        log_date = item["log_date"]
        for ex in item.get("exercises") or []:
            name = (ex.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if q and q not in key:
                continue
            if key in seen:
                seen[key]["count"] += 1
                continue
            seen[key] = {
                "name":          name,
                "last_date":     log_date,
                "count":         1,
                "type":          ex.get("type"),
                "sets":          ex.get("sets") or [],
                "duration_min":  ex.get("duration_min"),
                "distance_km":   ex.get("distance_km"),
                "muscle_groups": ex.get("muscle_groups") or [],
            }

    results = list(seen.values())[:limit]
    return ok(results)
