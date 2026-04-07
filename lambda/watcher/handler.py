"""Watcher Lambda — runs hourly, sends ntfy notifications for tasks and habits,
and runs periodic AI profile inference for all users."""

import ipaddress
import json
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
MEMORY_TABLE     = os.environ.get("MEMORY_TABLE", "")
JOURNAL_TABLE    = os.environ.get("JOURNAL_TABLE", "")
GOALS_TABLE      = os.environ.get("GOALS_TABLE", "")
NOTES_TABLE      = os.environ.get("NOTES_TABLE", "")
INFERENCE_MODEL_ID = os.environ.get("INFERENCE_MODEL_ID", "us.amazon.nova-lite-v1:0")

PROFILE_INFERRED_AT_KEY = "__profile_inferred_at__"

_dynamodb = boto3.resource("dynamodb")
_bedrock  = boto3.client("bedrock-runtime")

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

    # ── Profile inference (runs for all users, checks per-user interval) ───────
    if MEMORY_TABLE:
        try:
            _run_profile_inference(settings_table, now)
        except Exception as e:
            logger.error("Profile inference run failed: %s", e)

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


# ── Profile inference ─────────────────────────────────────────────────────────

def _run_profile_inference(settings_table, now: datetime) -> None:
    """Check each user's inference interval and run Bedrock fact extraction if due."""
    if not all([MEMORY_TABLE, JOURNAL_TABLE, GOALS_TABLE, NOTES_TABLE]):
        logger.warning("Profile inference skipped — one or more table env vars not set")
        return

    memory_table  = _dynamodb.Table(MEMORY_TABLE)
    journal_table = _dynamodb.Table(JOURNAL_TABLE)
    goals_table   = _dynamodb.Table(GOALS_TABLE)
    notes_table   = _dynamodb.Table(NOTES_TABLE)
    tasks_table_  = _dynamodb.Table(TASKS_TABLE)
    habits_table_ = _dynamodb.Table(HABITS_TABLE)

    all_settings = _all_user_settings(settings_table)
    logger.info("Profile inference: evaluating %d users", len(all_settings))

    for user_id, settings in all_settings:
        try:
            interval_hours = int(settings.get("profile_inference_hours", 24))
        except (ValueError, TypeError):
            interval_hours = 24

        if interval_hours == 0:
            continue  # inference disabled for this user

        # Check when inference last ran for this user
        last_at = _get_raw_memory(memory_table, user_id, PROFILE_INFERRED_AT_KEY)
        if last_at:
            try:
                last_dt = _parse_iso(last_at)
                if now < last_dt + timedelta(hours=interval_hours):
                    continue  # not due yet
            except Exception:
                pass  # bad timestamp — run anyway

        logger.info("Profile inference running for user %s", user_id)

        tasks   = _query_user(tasks_table_,  user_id)
        habits  = _query_user(habits_table_, user_id)
        journal = _query_user(journal_table, user_id)
        goals   = _query_user(goals_table,   user_id)
        notes   = _query_user(notes_table,   user_id)

        context = _build_activity_context(tasks, habits, journal, goals, notes)
        if not context.strip():
            logger.info("User %s has no activity data — skipping", user_id)
            _save_raw_memory(memory_table, user_id, PROFILE_INFERRED_AT_KEY, now.isoformat())
            continue

        existing_facts = _load_user_facts(memory_table, user_id)
        new_facts = _infer_facts_from_activity(existing_facts, context)

        for key, value in new_facts.items():
            _save_raw_memory(memory_table, user_id, key, value)

        _save_raw_memory(memory_table, user_id, PROFILE_INFERRED_AT_KEY, now.isoformat())
        logger.info("Profile inference done for user %s — %d fact(s) upserted", user_id, len(new_facts))


def _all_user_settings(settings_table) -> list[tuple[str, dict]]:
    """Return (user_id, settings_dict) for every user in the settings table."""
    users: list[tuple[str, dict]] = []
    resp = settings_table.scan()
    for item in resp.get("Items", []):
        uid = item.get("user_id")
        if uid:
            users.append((uid, item))
    while "LastEvaluatedKey" in resp:
        resp = settings_table.scan(ExclusiveStartKey=resp["LastEvaluatedKey"])
        for item in resp.get("Items", []):
            uid = item.get("user_id")
            if uid:
                users.append((uid, item))
    return users


def _load_user_facts(memory_table, user_id: str) -> dict:
    """Return the user's non-internal memory facts."""
    facts: dict = {}
    items = _query_user(memory_table, user_id)
    for item in items:
        key = item.get("memory_key", "")
        if key and not key.startswith("__"):
            facts[key] = item.get("value", "")
    return facts


def _get_raw_memory(memory_table, user_id: str, key: str) -> str:
    """Fetch a single memory item value (including internal __ keys)."""
    item = memory_table.get_item(Key={"user_id": user_id, "memory_key": key}).get("Item")
    return item.get("value", "") if item else ""


def _save_raw_memory(memory_table, user_id: str, key: str, value: str) -> None:
    """Upsert a single memory item."""
    from datetime import datetime, timezone as _tz
    now = datetime.now(_tz.utc).isoformat()
    memory_table.put_item(Item={
        "user_id":    user_id,
        "memory_key": key,
        "value":      value,
        "updated_at": now,
    })


def _build_activity_context(tasks, habits, journal, goals, notes) -> str:
    """Summarise user data into a text block for the Bedrock prompt."""
    lines: list[str] = []

    if tasks:
        lines.append("=== Tasks ===")
        for t in tasks[:30]:
            status = t.get("status", "")
            title  = t.get("title", "")
            desc   = t.get("description", "")
            lines.append(f"- [{status}] {title}" + (f": {desc}" if desc else ""))

    if habits:
        lines.append("=== Habits ===")
        for h in habits[:20]:
            lines.append(f"- {h.get('name', '')}" + (f": {h.get('description', '')}" if h.get("description") else ""))

    if journal:
        lines.append("=== Journal entries (recent) ===")
        sorted_journal = sorted(journal, key=lambda x: x.get("created_at", ""), reverse=True)
        for j in sorted_journal[:10]:
            content = j.get("content", "")[:300]
            if content:
                lines.append(f"- {content}")

    if goals:
        lines.append("=== Goals ===")
        for g in goals[:20]:
            lines.append(f"- {g.get('title', '')}" + (f": {g.get('description', '')}" if g.get("description") else ""))

    if notes:
        lines.append("=== Notes (recent) ===")
        sorted_notes = sorted(notes, key=lambda x: x.get("updated_at", ""), reverse=True)
        for n in sorted_notes[:10]:
            content = n.get("content", "")[:300]
            title   = n.get("title", "")
            if title or content:
                lines.append(f"- {title}: {content}" if title else f"- {content}")

    return "\n".join(lines)


def _infer_facts_from_activity(existing_facts: dict, activity_context: str) -> dict:
    """Call Bedrock to extract/update personal facts from the user's activity data."""
    existing_str = "\n".join(f"{k}: {v}" for k, v in existing_facts.items()) or "None"

    prompt = (
        "You are analyzing a user's personal productivity data to infer stable facts about them.\n\n"
        "Existing known facts:\n"
        f"{existing_str}\n\n"
        "User's recent activity:\n"
        f"{activity_context}\n\n"
        "From this activity data, identify NEW or UPDATED personal facts about this user. "
        "Focus on stable personal attributes: personality, lifestyle, occupation, specific interests/hobbies, "
        "recurring habits, long-term goals and aspirations, preferences, and values.\n\n"
        "Rules:\n"
        "- Infer themes and meaning — do NOT copy raw titles or task names verbatim.\n"
        "- Use SPECIFIC descriptive keys, not generic ones. BAD: 'goals', 'habits', 'interests'. "
        "GOOD: 'fitness_goal', 'morning_routine', 'creative_hobby'.\n"
        "- Values must be natural language phrases, not IDs or slugs. "
        "BAD: 'save_5000_emergency_fund'. GOOD: 'building an emergency fund'.\n"
        "- Only include facts clearly supported by patterns in the data — not one-off tasks or temporary items.\n"
        "- If a fact already exists and the data provides a richer or updated value, include it.\n"
        "- If there are no new or updated facts worth recording, output exactly: NONE\n\n"
        "Output one fact per line as 'key: value' using snake_case keys. Nothing else."
    )

    try:
        resp = _bedrock.converse(
            modelId=INFERENCE_MODEL_ID,
            messages=[{"role": "user", "content": [{"text": prompt}]}],
            inferenceConfig={"maxTokens": 512, "temperature": 0.1},
        )
        text = resp["output"]["message"]["content"][0]["text"].strip()
    except Exception as e:
        logger.error("Bedrock inference call failed: %s", e)
        return {}

    if text.upper() == "NONE" or not text:
        return {}

    facts: dict = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key   = key.strip().lower().replace(" ", "_")
        value = value.strip().replace("_", " ")
        if not key or not value:
            continue
        if key.startswith("__"):
            continue  # reject internal key attempts
        facts[key] = value

    return facts


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
