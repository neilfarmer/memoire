"""Habits CRUD operations against DynamoDB."""

import os
import re
import uuid
from datetime import date, timedelta

import boto3
from boto3.dynamodb.conditions import Key

import db
from response import ok, created, no_content, error, not_found

HABITS_TABLE     = os.environ["HABITS_TABLE"]
HABIT_LOGS_TABLE = os.environ["HABIT_LOGS_TABLE"]

_dynamodb = boto3.resource("dynamodb")


def _habits():
    return db.get_table(HABITS_TABLE)


def _logs():
    return _dynamodb.Table(HABIT_LOGS_TABLE)


def _log_sk(habit_id: str, log_date: str) -> str:
    """Composite sort key: "{habit_id}#{log_date}"."""
    return f"{habit_id}#{log_date}"


def _window():
    """Return (today_str, thirty_days_ago_str)."""
    today = date.today()
    return today.isoformat(), (today - timedelta(days=29)).isoformat()


def _build_history(user_id: str, habit_id: str, today_str: str, thirty_ago_str: str) -> tuple[list, bool, int, int]:
    """Fetch logs and return (history, done_today, current_streak, best_streak)."""
    resp = _logs().query(
        KeyConditionExpression=
            Key("user_id").eq(user_id) &
            Key("log_id").between(
                _log_sk(habit_id, thirty_ago_str),
                _log_sk(habit_id, today_str),
            )
    )
    # Extract the date portion from the composite SK
    logged = {item["log_id"].split("#")[1] for item in resp.get("Items", [])}

    today  = date.fromisoformat(today_str)
    history = [
        {"date": (today - timedelta(days=i)).isoformat(),
         "done": (today - timedelta(days=i)).isoformat() in logged}
        for i in range(29, -1, -1)
    ]

    # Current streak — count back from today
    current = 0
    for entry in reversed(history):
        if entry["done"]:
            current += 1
        else:
            break

    # Best streak in window
    best, run = 0, 0
    for entry in history:
        run = run + 1 if entry["done"] else 0
        best = max(best, run)

    return history, today_str in logged, current, best


# ── List ──────────────────────────────────────────────────────────────────────

def list_habits(user_id: str) -> dict:
    habits  = db.query_by_user(_habits(), user_id)
    today_str, thirty_ago = _window()
    result  = []

    for habit in habits:
        history, done_today, current_streak, best_streak = _build_history(
            user_id, habit["habit_id"], today_str, thirty_ago
        )
        result.append({
            **habit,
            "history":        history,
            "done_today":     done_today,
            "current_streak": current_streak,
            "best_streak":    best_streak,
        })

    return ok(result)


# ── Create ────────────────────────────────────────────────────────────────────

def create_habit(user_id: str, body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        return error("name is required")

    notify_time = body.get("notify_time", "")
    if notify_time:
        err = _validate_time(notify_time)
        if err:
            return error(err)

    habit = {
        "user_id":     user_id,
        "habit_id":    str(uuid.uuid4()),
        "name":        name,
        "notify_time": notify_time,
        "created_at":  date.today().isoformat(),
    }
    habit = {k: v for k, v in habit.items() if v is not None and v != ""}

    _habits().put_item(Item=habit)
    return created({**habit, "history": [], "done_today": False,
                    "current_streak": 0, "best_streak": 0})


# ── Update ────────────────────────────────────────────────────────────────────

def update_habit(user_id: str, habit_id: str, body: dict) -> dict:
    habit = db.get_item(_habits(), user_id, "habit_id", habit_id)
    if not habit:
        return not_found("Habit")

    fields = {}
    if "name" in body:
        name = (body["name"] or "").strip()
        if not name:
            return error("name cannot be empty")
        fields["name"] = name

    if "notify_time" in body:
        nt = body["notify_time"] or ""
        if nt:
            err = _validate_time(nt)
            if err:
                return error(err)
        fields["notify_time"] = nt

    if not fields:
        return ok(habit)

    set_parts, names, values = [], {}, {}
    for i, (k, v) in enumerate(fields.items()):
        names[f"#f{i}"]  = k
        values[f":v{i}"] = v
        set_parts.append(f"#f{i} = :v{i}")

    result = _habits().update_item(
        Key={"user_id": user_id, "habit_id": habit_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return ok(result["Attributes"])


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_habit(user_id: str, habit_id: str) -> dict:
    habit = db.get_item(_habits(), user_id, "habit_id", habit_id)
    if not habit:
        return not_found("Habit")

    _habits().delete_item(Key={"user_id": user_id, "habit_id": habit_id})

    # Delete ALL logs for this habit — paginate to handle histories > 1,000 entries
    params: dict = {
        "KeyConditionExpression":
            Key("user_id").eq(user_id) &
            Key("log_id").begins_with(f"{habit_id}#")
    }
    with _logs().batch_writer() as batch:
        while True:
            resp = _logs().query(**params)
            for item in resp.get("Items", []):
                batch.delete_item(Key={"user_id": user_id, "log_id": item["log_id"]})
            if "LastEvaluatedKey" not in resp:
                break
            params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]

    return no_content()


# ── Toggle log ────────────────────────────────────────────────────────────────

def toggle_log(user_id: str, habit_id: str, body: dict) -> dict:
    habit = db.get_item(_habits(), user_id, "habit_id", habit_id)
    if not habit:
        return not_found("Habit")

    log_date = (body.get("date") or "").strip()
    if not log_date:
        log_date = date.today().isoformat()

    # Validate within 30-day window
    today = date.today()
    try:
        log_d = date.fromisoformat(log_date)
    except ValueError:
        return error("Invalid date format, expected YYYY-MM-DD")

    if log_d > today or log_d < today - timedelta(days=29):
        return error("Date must be within the last 30 days")

    log_key = {"user_id": user_id, "log_id": _log_sk(habit_id, log_date)}

    existing = _logs().get_item(Key=log_key).get("Item")

    if existing:
        _logs().delete_item(Key=log_key)
        return ok({"logged": False, "date": log_date})
    else:
        _logs().put_item(Item={**log_key, "habit_id": habit_id})
        return ok({"logged": True, "date": log_date})


# ── Helpers ───────────────────────────────────────────────────────────────────

def _validate_time(t: str) -> str | None:
    if not re.match(r"^\d{2}:\d{2}$", t):
        return "notify_time must be in HH:MM format (24h UTC)"
    h, m = int(t[:2]), int(t[3:])
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return "notify_time is not a valid time"
    return None
