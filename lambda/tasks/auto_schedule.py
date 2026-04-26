"""Auto-schedule unscheduled tasks into free working-hour slots.

Greedy first-fit. Sorts targets by (priority desc, due_date asc, created_at asc)
and walks the user's working-hour slots until each fits. Skips tasks that
already have a scheduled_start unless `respect_existing` is False.
"""

import os
from datetime import datetime, timezone
from typing import Iterable

import db
import scheduler
from response import ok, error

TASKS_TABLE    = os.environ["TABLE_NAME"]
SETTINGS_TABLE = os.environ.get("SETTINGS_TABLE", "")

PRIORITY_RANK = {"high": 0, "medium": 1, "low": 2}


def _table():
    return db.get_table(TASKS_TABLE)


def _settings_for(user_id: str) -> dict:
    if not SETTINGS_TABLE:
        return {}
    item = db.get_table(SETTINGS_TABLE).get_item(Key={"user_id": user_id}).get("Item") or {}
    return item


def _candidate_tasks(tasks: list[dict], requested_ids: Iterable[str] | None) -> list[dict]:
    if requested_ids:
        wanted = set(requested_ids)
        return [t for t in tasks if t.get("task_id") in wanted]
    return [t for t in tasks
            if t.get("status") in ("todo", "in_progress")
            and not t.get("scheduled_start")
            and not t.get("recurrence_rule")]


def _due_horizon(task: dict) -> float | None:
    """Return the latest UTC timestamp this task should fit before, or None."""
    due = task.get("due_date")
    if not due:
        return None
    try:
        return datetime.fromisoformat(due + "T23:59:59+00:00").timestamp()
    except ValueError:
        return None


def auto_schedule(user_id: str, body: dict) -> dict:
    body = body or {}
    requested_ids = body.get("task_ids")
    try:
        horizon_days = int(body.get("horizon_days") or 0)
    except (TypeError, ValueError):
        return error("horizon_days must be an integer")
    respect_priority = body.get("respect_priority", True)

    settings_item = _settings_for(user_id)
    cal = scheduler._coerce_calendar(settings_item)
    if horizon_days > 0:
        cal["horizon_days"] = min(horizon_days, 60)

    tz = scheduler._zone(cal["timezone"])
    now = datetime.now(timezone.utc)

    tasks_table = _table()
    all_tasks = db.query_by_user(tasks_table, user_id)

    targets = _candidate_tasks(all_tasks, requested_ids)
    if not targets:
        return ok({"scheduled": [], "skipped": [], "message": "No eligible tasks to schedule"})

    if respect_priority:
        targets.sort(key=lambda t: (
            PRIORITY_RANK.get(t.get("priority", "medium"), 1),
            t.get("due_date") or "9999-12-31",
            t.get("created_at") or "",
        ))
    else:
        targets.sort(key=lambda t: t.get("created_at") or "")

    busy = scheduler._busy_intervals(all_tasks)
    scheduled = []
    skipped = []

    for task in targets:
        try:
            duration = int(task.get("duration_minutes") or cal["slot_minutes"])
        except (TypeError, ValueError):
            duration = cal["slot_minutes"]

        cutoff = _due_horizon(task)
        slot = scheduler._find_free_slot(now, duration, cal, tz, busy, exclude_id=task.get("task_id"))
        if not slot:
            skipped.append({"task_id": task["task_id"], "reason": "no free slot"})
            continue
        if cutoff is not None and slot.timestamp() + duration * 60 > cutoff:
            skipped.append({"task_id": task["task_id"], "reason": "past due date"})
            continue

        tasks_table.update_item(
            Key={"user_id": user_id, "task_id": task["task_id"]},
            UpdateExpression="SET scheduled_start = :s, duration_minutes = :d, updated_at = :u",
            ExpressionAttributeValues={
                ":s": slot.isoformat(),
                ":d": duration,
                ":u": now.isoformat(),
            },
        )
        busy.append((slot.timestamp(), slot.timestamp() + duration * 60, task["task_id"]))
        scheduled.append({
            "task_id":          task["task_id"],
            "title":            task.get("title", ""),
            "scheduled_start":  slot.isoformat(),
            "duration_minutes": duration,
        })

    return ok({"scheduled": scheduled, "skipped": skipped})
