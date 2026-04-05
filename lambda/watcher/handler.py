"""Watcher Lambda — runs hourly, sends ntfy notifications for tasks and habits."""

import ipaddress
import logging
import os
import socket
from datetime import datetime, date, timezone, timedelta
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import boto3
from boto3.dynamodb.conditions import Attr

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


def _is_safe_ntfy_url(url: str) -> bool:
    """Return True only if the URL is HTTPS and resolves to a public IP."""
    try:
        parsed = urlparse(url)
        if parsed.scheme != "https" or not parsed.hostname:
            return False
        ip = socket.gethostbyname(parsed.hostname)
        addr = ipaddress.ip_address(ip)
        return not (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved)
    except Exception:
        return False


def lambda_handler(event, context):
    now            = datetime.now(timezone.utc)
    tasks_table    = _dynamodb.Table(TASKS_TABLE)
    settings_table = _dynamodb.Table(SETTINGS_TABLE)
    habits_table   = _dynamodb.Table(HABITS_TABLE)
    logs_table     = _dynamodb.Table(HABIT_LOGS_TABLE)

    # Scan only the settings table (one row per user) to find users who have
    # ntfy_url configured.  Then query tasks/habits per user by PK instead of
    # scanning the full tasks and habits tables every hour.
    users = _users_with_ntfy(settings_table)
    logger.info("Found %d users with ntfy_url configured", len(users))

    today_str = now.date().isoformat()

    for user_id, ntfy_url in users:
        # ── Tasks ─────────────────────────────────────────────────────────────
        user_tasks = _query_user(tasks_table, user_id)
        active_tasks = [t for t in user_tasks if t.get("status") != "done" and t.get("notifications")]
        logger.info("User %s: checking %d active tasks with notifications", user_id, len(active_tasks))
        for task in active_tasks:
            _process_task(tasks_table, task, ntfy_url, now)

        # ── Habits ────────────────────────────────────────────────────────────
        user_habits = _query_user(habits_table, user_id)
        for habit in user_habits:
            notify_time = habit.get("notify_time", "")
            if not notify_time:
                continue
            try:
                notify_hour = int(notify_time.split(":")[0])
            except (ValueError, IndexError):
                continue
            if notify_hour != now.hour:
                continue

            if habit.get("last_notified_date") == today_str:
                continue  # already sent today

            # Skip if already completed today
            log = logs_table.get_item(
                Key={"user_id": user_id, "log_id": f"{habit['habit_id']}#{today_str}"}
            ).get("Item")
            if log:
                continue

            if _send_habit(ntfy_url, habit):
                habits_table.update_item(
                    Key={"user_id": user_id, "habit_id": habit["habit_id"]},
                    UpdateExpression="SET last_notified_date = :d",
                    ExpressionAttributeValues={":d": today_str},
                )


# ── Shared helpers ────────────────────────────────────────────────────────────

def _users_with_ntfy(settings_table) -> list[tuple[str, str]]:
    """Return (user_id, ntfy_url) for every user with a non-empty ntfy_url."""
    users: list[tuple[str, str]] = []
    kwargs = {"FilterExpression": Attr("ntfy_url").exists() & Attr("ntfy_url").ne("")}
    resp = settings_table.scan(**kwargs)
    for item in resp.get("Items", []):
        users.append((item["user_id"], item["ntfy_url"]))
    while "LastEvaluatedKey" in resp:
        resp = settings_table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"], **kwargs)
        for item in resp.get("Items", []):
            users.append((item["user_id"], item["ntfy_url"]))
    return users


def _query_user(table, user_id: str) -> list[dict]:
    """Fetch all items for a user via PK query (avoids full-table scan)."""
    from boto3.dynamodb.conditions import Key as DKey
    items: list[dict] = []
    params: dict = {"KeyConditionExpression": DKey("user_id").eq(user_id)}
    while True:
        resp = table.query(**params)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def _ntfy_post(url, title, body, priority="3"):
    if not _is_safe_ntfy_url(url):
        logger.warning("Skipping ntfy notification — URL failed safety check: %s", url)
        return False
    try:
        req = Request(
            url,
            data=body.encode(),
            headers={"Title": title, "Priority": priority},
            method="POST",
        )
        with urlopen(req, timeout=10) as resp:  # nosec B310 — ntfy_url validated as https + non-private on write
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
