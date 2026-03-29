"""Nutrition log CRUD operations against DynamoDB."""

import os
import re
import uuid
from datetime import datetime, timezone

from db import get_table
from response import ok, no_content, error, not_found

TABLE_NAME = os.environ["TABLE_NAME"]


def _table():
    return get_table(TABLE_NAME)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_date(d: str):
    if not d or not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        raise ValueError(f"Invalid date format: {d}")


def _summary(item: dict) -> dict:
    meals = item.get("meals", [])
    total_cal = sum(m.get("calories") or 0 for m in meals)
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
    table = _table()
    resp  = table.query(
        KeyConditionExpression="user_id = :uid",
        ExpressionAttributeValues={":uid": user_id},
    )
    items = sorted(resp.get("Items", []), key=lambda x: x["log_date"], reverse=True)
    return ok([_summary(i) for i in items])


def get_log(user_id: str, log_date: str) -> dict:
    try:
        _validate_date(log_date)
    except ValueError as e:
        return error(str(e))

    table = _table()
    resp  = table.get_item(Key={"user_id": user_id, "log_date": log_date})
    item  = resp.get("Item")
    if not item:
        return not_found("Log")
    return ok(item)


def upsert_log(user_id: str, log_date: str, body: dict) -> dict:
    try:
        _validate_date(log_date)
    except ValueError as e:
        return error(str(e))

    table    = _table()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")

    meals = body.get("meals", [])
    for m in meals:
        if not m.get("id"):
            m["id"] = str(uuid.uuid4())

    item = {
        "user_id":    user_id,
        "log_date":   log_date,
        "meals":      meals,
        "notes":      body.get("notes", ""),
        "created_at": existing["created_at"] if existing else _now(),
        "updated_at": _now(),
    }
    table.put_item(Item=item)
    return ok(item)


def delete_log(user_id: str, log_date: str) -> dict:
    try:
        _validate_date(log_date)
    except ValueError as e:
        return error(str(e))

    table    = _table()
    existing = table.get_item(Key={"user_id": user_id, "log_date": log_date}).get("Item")
    if not existing:
        return not_found("Log")
    table.delete_item(Key={"user_id": user_id, "log_date": log_date})
    return no_content()
