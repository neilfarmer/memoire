"""Nutrition log CRUD operations against DynamoDB."""

import os
import uuid
from datetime import date as _date, timedelta
from decimal import Decimal, InvalidOperation

from db import get_table, query_by_user
from response import ok, no_content, error, not_found
from utils import now_iso, validate_date

TABLE_NAME = os.environ["TABLE_NAME"]

NUMERIC_MEAL_FIELDS = ("calories", "protein_g", "carbs_g", "fat_g")


def _table():
    return get_table(TABLE_NAME)


def _to_decimal(val):
    if val is None or val == "":
        return None
    try:
        return Decimal(str(val))
    except (InvalidOperation, ValueError):
        return None


def _normalize_meal(m: dict) -> dict | None:
    """Validate + coerce one meal. Returns sanitized dict or None if invalid."""
    name = (m.get("name") or "").strip()
    if not name:
        return None

    out: dict = {
        "id":   m.get("id") or str(uuid.uuid4()),
        "name": name,
    }
    for field in NUMERIC_MEAL_FIELDS:
        if field in m:
            val = _to_decimal(m[field])
            if val is not None and val >= 0:
                out[field] = val
    return out


def _summary(item: dict) -> dict:
    meals = item.get("meals", [])
    total_cal = sum((m.get("calories") or 0) for m in meals)
    return {
        "user_id":     item["user_id"],
        "log_date":    item["log_date"],
        "meal_count":  len(meals),
        "total_cal":   total_cal,
        "notes":       item.get("notes", ""),
        "created_at":  item.get("created_at", ""),
        "updated_at":  item.get("updated_at", ""),
    }


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

    meals = []
    for raw in body.get("meals", []):
        clean = _normalize_meal(raw)
        if clean is not None:
            meals.append(clean)

    item = {
        "user_id":    user_id,
        "log_date":   log_date,
        "meals":      meals,
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
    """Rollup macros over [from, to] inclusive. Defaults to last 30 days."""
    today = _date.today()
    date_from = (query_params or {}).get("from") or (today - timedelta(days=29)).isoformat()
    date_to   = (query_params or {}).get("to")   or today.isoformat()
    for d in (date_from, date_to):
        err = validate_date(d)
        if err:
            return error(f"Invalid date: {d}")

    items = [i for i in query_by_user(_table(), user_id)
             if date_from <= i.get("log_date", "") <= date_to]

    totals = {f: Decimal("0") for f in NUMERIC_MEAL_FIELDS}
    logged_days = 0
    meal_count  = 0

    for item in items:
        meals = item.get("meals") or []
        if not meals:
            continue
        logged_days += 1
        meal_count += len(meals)
        for m in meals:
            for f in NUMERIC_MEAL_FIELDS:
                val = _to_decimal(m.get(f))
                if val is not None:
                    totals[f] += val

    avg = {f: (totals[f] / logged_days) if logged_days else Decimal("0")
           for f in NUMERIC_MEAL_FIELDS}

    logged_dates = {i["log_date"] for i in items if (i.get("meals") or [])}
    streak = 0
    cursor = today
    while cursor.isoformat() in logged_dates:
        streak += 1
        cursor -= timedelta(days=1)

    return ok({
        "from":        date_from,
        "to":          date_to,
        "logged_days": logged_days,
        "meal_count":  meal_count,
        "totals":      totals,
        "avg_per_day": avg,
        "streak_days": streak,
    })


def recent_meals(user_id: str, query_params: dict) -> dict:
    """Distinct meals from the most recent N days, optionally filtered by query.

    Each result includes the last-used date and the most recent macro set so
    the caller can re-log the same meal by copying the payload.
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
        for m in item.get("meals") or []:
            name = (m.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if q and q not in key:
                continue
            if key in seen:
                seen[key]["count"] += 1
                continue
            entry = {"name": name, "last_date": log_date, "count": 1}
            for f in NUMERIC_MEAL_FIELDS:
                if m.get(f) is not None:
                    entry[f] = m[f]
            seen[key] = entry

    results = list(seen.values())[:limit]
    return ok(results)
