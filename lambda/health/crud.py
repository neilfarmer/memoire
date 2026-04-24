"""Health/exercise log CRUD operations against DynamoDB."""

import os
import uuid
from datetime import date as _date, timedelta
from decimal import Decimal, InvalidOperation

from db import get_table, query_by_user
from response import ok, no_content, error, not_found
from utils import now_iso, validate_date

TABLE_NAME = os.environ["TABLE_NAME"]

EXERCISE_TYPES = {"strength", "cardio", "mobility"}


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
        for s in ex.get("sets") or []:
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
    totals = _exercise_totals(exercises)
    return {
        "user_id":        item["user_id"],
        "log_date":       item["log_date"],
        "exercise_count": len(exercises),
        "total_volume":   totals["total_volume"],
        "total_duration": totals["total_duration"],
        "total_distance": totals["total_distance"],
        "notes":          item.get("notes", ""),
        "created_at":     item.get("created_at", ""),
        "updated_at":     item.get("updated_at", ""),
    }


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
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")

    exercises = []
    for raw in body.get("exercises", []):
        clean = _normalize_exercise(raw)
        if clean is not None:
            exercises.append(clean)

    item = {
        "user_id":    user_id,
        "log_date":   log_date,
        "exercises":  exercises,
        "notes":      body.get("notes", ""),
        "created_at": (existing or {}).get("created_at") or now_iso(),
        "updated_at": now_iso(),
    }
    table.put_item(Item=item)
    return ok(item)


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
