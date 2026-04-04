"""Health/exercise log CRUD operations against DynamoDB."""

import os
import uuid

from db import get_table, query_by_user
from response import ok, no_content, error, not_found
from utils import now_iso, validate_date

TABLE_NAME = os.environ["TABLE_NAME"]


def _table():
    return get_table(TABLE_NAME)


def _summary(item: dict) -> dict:
    return {
        "user_id":        item["user_id"],
        "log_date":       item["log_date"],
        "exercise_count": len(item.get("exercises", [])),
        "notes":          item.get("notes", ""),
        "created_at":     item.get("created_at", ""),
        "updated_at":     item.get("updated_at", ""),
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

    exercises = body.get("exercises", [])
    for ex in exercises:
        if not ex.get("id"):
            ex["id"] = str(uuid.uuid4())

    item = {
        "user_id":    user_id,
        "log_date":   log_date,
        "exercises":  exercises,
        "notes":      body.get("notes", ""),
        "created_at": existing["created_at"] if existing else now_iso(),
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
