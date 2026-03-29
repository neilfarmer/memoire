"""Watcher Lambda — runs hourly, sends ntfy notifications for tasks and habits."""

import logging
import os
from datetime import datetime, date, timezone, timedelta
from urllib.request import Request, urlopen

import boto3
from boto3.dynamodb.conditions import Attr, Key

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TASKS_TABLE      = os.environ["TASKS_TABLE"]
SETTINGS_TABLE   = os.environ["SETTINGS_TABLE"]
HABITS_TABLE     = os.environ["HABITS_TABLE"]
HABIT_LOGS_TABLE = os.environ["HABIT_LOGS_TABLE"]

_dynamodb = boto3.resource("dynamodb")

BEFORE_OFFSETS = {
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
}

RECURRING_INTERVALS = {
    "1h": timedelta(hours=1),
    "1d": timedelta(days=1),
    "1w": timedelta(weeks=1),
}

NTFY_PRIORITY = {"high": "5", "medium": "3", "low": "1"}


def lambda_handler(event, context):
    now            = datetime.now(timezone.utc)
    tasks_table    = _dynamodb.Table(TASKS_TABLE)
    settings_table = _dynamodb.Table(SETTINGS_TABLE)
    habits_table   = _dynamodb.Table(HABITS_TABLE)
    logs_table     = _dynamodb.Table(HABIT_LOGS_TABLE)

    settings_cache = {}

    # ── Tasks ─────────────────────────────────────────────────────────────────
    tasks = _scan(tasks_table, FilterExpression=Attr("status").ne("done"))
    logger.info("Checking %d active tasks", len(tasks))

    for task in tasks:
        if not task.get("notifications"):
            continue
        ntfy_url = _get_ntfy_url(settings_table, settings_cache, task["user_id"])
        if ntfy_url:
            _process_task(tasks_table, task, ntfy_url, now)

    # ── Habits ────────────────────────────────────────────────────────────────
    habits = _scan(habits_table, FilterExpression=Attr("notify_time").exists())
    logger.info("Checking %d habits with notify_time", len(habits))

    for habit in habits:
        notify_time = habit.get("notify_time", "")
        if not notify_time:
            continue
        try:
            notify_hour = int(notify_time.split(":")[0])
        except (ValueError, IndexError):
            continue
        if notify_hour != now.hour:
            continue

        today_str = now.date().isoformat()
        if habit.get("last_notified_date") == today_str:
            continue  # already sent today

        # Skip if already completed today
        log = logs_table.get_item(
            Key={"habit_id": habit["habit_id"], "log_date": today_str}
        ).get("Item")
        if log:
            continue

        ntfy_url = _get_ntfy_url(settings_table, settings_cache, habit["user_id"])
        if not ntfy_url:
            continue

        if _send_habit(ntfy_url, habit):
            habits_table.update_item(
                Key={"user_id": habit["user_id"], "habit_id": habit["habit_id"]},
                UpdateExpression="SET last_notified_date = :d",
                ExpressionAttributeValues={":d": today_str},
            )


# ── Shared helpers ────────────────────────────────────────────────────────────

def _scan(table, **kwargs):
    resp  = table.scan(**kwargs)
    items = resp.get("Items", [])
    while "LastEvaluatedKey" in resp:
        resp = table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        items.extend(resp.get("Items", []))
    return items


def _get_ntfy_url(settings_table, cache, user_id):
    if user_id not in cache:
        item = settings_table.get_item(Key={"user_id": user_id}).get("Item", {})
        cache[user_id] = item.get("ntfy_url", "")
    return cache[user_id]


def _ntfy_post(url, title, body, priority="3"):
    try:
        req = Request(
            url,
            data=body.encode(),
            headers={"Title": title, "Priority": priority},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:
            logger.info("Sent notification '%s' (status %s)", title, resp.status)
        return True
    except Exception as e:
        logger.error("Failed to send notification '%s': %s", title, e)
        return False


# ── Task processing ───────────────────────────────────────────────────────────

def _process_task(tasks_table, task, ntfy_url, now):
    notifications = task["notifications"]
    sent          = dict(task.get("notification_sent") or {})
    updates       = {}
    due_dt        = _parse_due(task.get("due_date"))

    if notifications.get("on_due") and due_dt:
        if now >= due_dt and "on_due" not in sent:
            if _send_task(ntfy_url, task, "Due now"):
                updates["on_due"] = now.isoformat()

    for key, offset in BEFORE_OFFSETS.items():
        sent_key = f"before_{key}"
        if key in (notifications.get("before_due") or []) and due_dt:
            if now >= (due_dt - offset) and sent_key not in sent:
                labels = {"1h": "Due in 1 hour", "1d": "Due tomorrow", "3d": "Due in 3 days"}
                if _send_task(ntfy_url, task, labels[key]):
                    updates[sent_key] = now.isoformat()

    recurring = notifications.get("recurring")
    if recurring and recurring in RECURRING_INTERVALS:
        interval    = RECURRING_INTERVALS[recurring]
        last_str    = sent.get("recurring")
        should_send = not last_str or now >= _parse_iso(last_str) + interval
        if should_send:
            if _send_task(ntfy_url, task, "Reminder"):
                updates["recurring"] = now.isoformat()

    if updates:
        tasks_table.update_item(
            Key={"user_id": task["user_id"], "task_id": task["task_id"]},
            UpdateExpression="SET notification_sent = :ns",
            ExpressionAttributeValues={":ns": {**sent, **updates}},
        )


def _send_task(ntfy_url, task, trigger_label):
    lines = [trigger_label]
    if task.get("description"):
        lines.append(task["description"])
    if task.get("due_date"):
        lines.append(f"Due: {task['due_date']}")
    if task.get("priority"):
        lines.append(f"Priority: {task['priority']}")
    priority = NTFY_PRIORITY.get(task.get("priority", "medium"), "3")
    return _ntfy_post(ntfy_url, task.get("title", "Task reminder"), "\n".join(lines), priority)


# ── Habit processing ──────────────────────────────────────────────────────────

def _send_habit(ntfy_url, habit):
    return _ntfy_post(ntfy_url, habit["name"], "Time to complete your habit.")


# ── Date helpers ──────────────────────────────────────────────────────────────

def _parse_due(due_date_str):
    if not due_date_str:
        return None
    d = date.fromisoformat(due_date_str)
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc)


def _parse_iso(ts):
    dt = datetime.fromisoformat(ts)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
