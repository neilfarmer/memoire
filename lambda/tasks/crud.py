"""Tasks CRUD operations against DynamoDB."""

import os
import re
import uuid
from datetime import datetime, timezone

import boto3
from response import ok, created, no_content, error, not_found
import db
import links_util
from utils import now_iso, build_update_expression

_dynamodb_client = boto3.client("dynamodb")

TABLE_NAME = os.environ["TABLE_NAME"]
SORT_KEY = "task_id"

VALID_STATUSES    = {"todo", "in_progress", "done"}
VALID_PRIORITIES  = {"low", "medium", "high"}
VALID_BEFORE_DUE  = {"1h", "1d", "3d"}
VALID_RECURRING   = {"1h", "1d", "1w"}

VALID_RECURRENCE_FREQ = {"daily", "weekly", "weekdays"}

MAX_TITLE_LEN       = 500
MAX_DESCRIPTION_LEN = 10_000
MAX_TAG_LEN         = 50
MAX_TAGS_PER_TASK   = 20

SLOT_MINUTES        = 30
MAX_DURATION_MIN    = 8 * 60

_ISO_WEEKDAY_RANGE  = range(1, 8)


def _table():
    return db.get_table(TABLE_NAME)


def _parse_scheduled_start(value: str) -> datetime | None:
    """Parse an ISO-8601 datetime; return tz-aware UTC datetime or None on failure."""
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _validate_scheduling(body: dict) -> str | None:
    """Validate scheduled_start, duration_minutes, and recurrence_rule together."""
    if "scheduled_start" in body and body["scheduled_start"] is not None:
        dt = _parse_scheduled_start(body["scheduled_start"])
        if dt is None:
            return "scheduled_start must be an ISO 8601 datetime"
        if dt.minute % SLOT_MINUTES != 0 or dt.second != 0 or dt.microsecond != 0:
            return f"scheduled_start must align to a {SLOT_MINUTES}-minute slot"

    if "duration_minutes" in body and body["duration_minutes"] is not None:
        try:
            dur = int(body["duration_minutes"])
        except (TypeError, ValueError):
            return "duration_minutes must be an integer"
        if dur <= 0 or dur % SLOT_MINUTES != 0 or dur > MAX_DURATION_MIN:
            return (
                f"duration_minutes must be a positive multiple of {SLOT_MINUTES} "
                f"and at most {MAX_DURATION_MIN}"
            )

    if "recurrence_rule" in body and body["recurrence_rule"] is not None:
        rr = body["recurrence_rule"]
        if not isinstance(rr, dict):
            return "recurrence_rule must be an object"
        freq = rr.get("freq")
        if freq not in VALID_RECURRENCE_FREQ:
            return f"recurrence_rule.freq must be one of: {', '.join(sorted(VALID_RECURRENCE_FREQ))}"
        interval = rr.get("interval", 1)
        try:
            interval_int = int(interval)
        except (TypeError, ValueError):
            return "recurrence_rule.interval must be an integer"
        if interval_int < 1 or interval_int > 365:
            return "recurrence_rule.interval must be between 1 and 365"
        by_weekday = rr.get("by_weekday")
        if by_weekday is not None:
            if not isinstance(by_weekday, list) or not all(
                isinstance(d, int) and d in _ISO_WEEKDAY_RANGE for d in by_weekday
            ):
                return "recurrence_rule.by_weekday must be a list of ISO weekday integers (1=Mon..7=Sun)"
        until = rr.get("until")
        if until is not None and (not isinstance(until, str) or not re.match(r"^\d{4}-\d{2}-\d{2}$", until)):
            return "recurrence_rule.until must be YYYY-MM-DD"
    return None


def _normalize_tags(raw) -> list[str] | None:
    """Return a sanitized tag list, or None if input is missing.

    Accepts a list of strings or a comma-separated string. Strips whitespace,
    drops empties, deduplicates while preserving order.
    """
    if raw is None:
        return None
    if isinstance(raw, str):
        raw = [t for t in raw.split(",")]
    if not isinstance(raw, list):
        return []
    seen = set()
    out: list[str] = []
    for tag in raw:
        if not isinstance(tag, str):
            continue
        norm = tag.strip()
        if not norm or norm.lower() in seen:
            continue
        seen.add(norm.lower())
        out.append(norm)
    return out


def _validate_fields(body: dict) -> str | None:
    """Return an error message if any provided fields are invalid, else None."""
    if "status" in body and body["status"] not in VALID_STATUSES:
        return f"status must be one of: {', '.join(sorted(VALID_STATUSES))}"
    if "priority" in body and body["priority"] not in VALID_PRIORITIES:
        return f"priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}"
    if "notifications" in body and body["notifications"] is not None:
        n = body["notifications"]
        if not isinstance(n, dict):
            return "notifications must be an object"
        before = n.get("before_due") or []
        if not isinstance(before, list) or not all(v in VALID_BEFORE_DUE for v in before):
            return f"notifications.before_due values must be from: {', '.join(sorted(VALID_BEFORE_DUE))}"
        recurring = n.get("recurring")
        if recurring and recurring not in VALID_RECURRING:
            return f"notifications.recurring must be one of: {', '.join(sorted(VALID_RECURRING))}"
    if "tags" in body and body["tags"] is not None:
        tags = _normalize_tags(body["tags"])
        if len(tags) > MAX_TAGS_PER_TASK:
            return f"tags must contain no more than {MAX_TAGS_PER_TASK} entries"
        if any(len(t) > MAX_TAG_LEN for t in tags):
            return f"each tag must be at most {MAX_TAG_LEN} characters"
        body["tags"] = tags
    return _validate_scheduling(body)


def _check_overlap(user_id: str, start: datetime, duration: int, exclude_id: str | None) -> bool:
    """Return True if an existing scheduled task overlaps [start, start+duration)."""
    end = start.timestamp() + duration * 60
    for t in db.query_by_user(_table(), user_id):
        if exclude_id and t.get("task_id") == exclude_id:
            continue
        if t.get("status") == "done":
            continue
        other_start = _parse_scheduled_start(t.get("scheduled_start") or "")
        if not other_start:
            continue
        try:
            other_dur = int(t.get("duration_minutes") or SLOT_MINUTES)
        except (TypeError, ValueError):
            continue
        other_end = other_start.timestamp() + other_dur * 60
        if other_start.timestamp() < end and other_end > start.timestamp():
            return True
    return False


# ── List ──────────────────────────────────────────────────────────────────────

def list_tasks(user_id: str) -> dict:
    tasks = db.query_by_user(_table(), user_id)
    return ok(tasks)


def list_calendar(user_id: str, query_params: dict) -> dict:
    """Return only scheduled tasks whose start falls in [from, to] (ISO dates)."""
    frm = (query_params or {}).get("from")
    to  = (query_params or {}).get("to")
    if not frm or not to:
        return error("from and to query parameters are required (YYYY-MM-DD)")
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", frm) or not re.match(r"^\d{4}-\d{2}-\d{2}$", to):
        return error("from/to must be YYYY-MM-DD")

    start_ts = datetime.fromisoformat(frm + "T00:00:00+00:00").timestamp()
    end_ts   = datetime.fromisoformat(to  + "T23:59:59+00:00").timestamp()

    items = []
    for t in db.query_by_user(_table(), user_id):
        sch = _parse_scheduled_start(t.get("scheduled_start") or "")
        if not sch:
            continue
        if start_ts <= sch.timestamp() <= end_ts:
            items.append(t)
    return ok(items)


# ── Create ────────────────────────────────────────────────────────────────────

def create_task(user_id: str, body: dict) -> dict:
    title = (body.get("title") or "").strip()
    if not title:
        return error("title is required")
    if len(title) > MAX_TITLE_LEN:
        return error(f"title exceeds maximum length of {MAX_TITLE_LEN}")

    description = body.get("description", "")
    if len(description) > MAX_DESCRIPTION_LEN:
        return error(f"description exceeds maximum length of {MAX_DESCRIPTION_LEN}")

    err = _validate_fields(body)
    if err:
        return error(err)

    sched = _parse_scheduled_start(body.get("scheduled_start") or "")
    duration = int(body.get("duration_minutes") or SLOT_MINUTES) if sched else None
    if sched and _check_overlap(user_id, sched, duration, exclude_id=None):
        return error("scheduled_start overlaps an existing block", status=409)

    now = now_iso()
    tags = _normalize_tags(body.get("tags")) if body.get("tags") is not None else []
    task = {
        "user_id": user_id,
        "task_id": str(uuid.uuid4()),
        "title": title,
        "description": description,
        "status": body.get("status", "todo"),
        "priority": body.get("priority", "medium"),
        "due_date": body.get("due_date"),
        "notifications": body.get("notifications"),
        "tags": tags,
        "scheduled_start": sched.isoformat() if sched else None,
        "duration_minutes": duration,
        "recurrence_rule": body.get("recurrence_rule"),
        "recurrence_parent_id": body.get("recurrence_parent_id"),
        "created_at": now,
        "updated_at": now,
    }

    # Remove None values so DynamoDB doesn't reject them
    task = {k: v for k, v in task.items() if v is not None}

    _table().put_item(Item=task)
    links_util.sync_links(user_id, "task", task["task_id"], [title, description])
    return created(task)


# ── Get ───────────────────────────────────────────────────────────────────────

def get_task(user_id: str, task_id: str) -> dict:
    task = db.get_item(_table(), user_id, SORT_KEY, task_id)
    if not task:
        return not_found("Task")
    return ok(task)


# ── Update ────────────────────────────────────────────────────────────────────

def update_task(user_id: str, task_id: str, body: dict) -> dict:
    updatable = {
        "title", "description", "status", "priority", "due_date", "notifications",
        "tags", "scheduled_start", "duration_minutes",
        "recurrence_rule", "recurrence_parent_id",
    }
    fields = {k: v for k, v in body.items() if k in updatable}

    if not fields:
        return error("No valid fields provided for update")

    if "title" in fields:
        fields["title"] = fields["title"].strip()
        if not fields["title"]:
            return error("title cannot be empty")
        if len(fields["title"]) > MAX_TITLE_LEN:
            return error(f"title exceeds maximum length of {MAX_TITLE_LEN}")
    if "description" in fields and len(fields["description"]) > MAX_DESCRIPTION_LEN:
        return error(f"description exceeds maximum length of {MAX_DESCRIPTION_LEN}")

    err = _validate_fields(fields)
    if err:
        return error(err)

    if "scheduled_start" in fields and fields["scheduled_start"] is not None:
        sched = _parse_scheduled_start(fields["scheduled_start"])
        existing = db.get_item(_table(), user_id, SORT_KEY, task_id) or {}
        duration = fields.get("duration_minutes")
        if duration is None:
            duration = int(existing.get("duration_minutes") or SLOT_MINUTES)
        else:
            duration = int(duration)
        if sched and _check_overlap(user_id, sched, duration, exclude_id=task_id):
            return error("scheduled_start overlaps an existing block", status=409)
        fields["scheduled_start"] = sched.isoformat()

    fields["updated_at"] = now_iso()
    if "notifications" in fields:
        fields["notification_sent"] = {}

    update_expr, names, values = build_update_expression(fields)

    try:
        result = _table().update_item(
            Key={"user_id": user_id, SORT_KEY: task_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(task_id)",
            ReturnValues="ALL_NEW",
        )
    except _dynamodb_client.exceptions.ConditionalCheckFailedException:
        return not_found("Task")

    updated = result["Attributes"]
    links_util.sync_links(
        user_id, "task", task_id,
        [updated.get("title", ""), updated.get("description", "")],
    )
    return ok(updated)


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_task(user_id: str, task_id: str) -> dict:
    try:
        _table().delete_item(
            Key={"user_id": user_id, SORT_KEY: task_id},
            ConditionExpression="attribute_exists(task_id)",
        )
    except _dynamodb_client.exceptions.ConditionalCheckFailedException:
        return not_found("Task")

    links_util.delete_source_links(user_id, "task", task_id)
    return no_content()
