"""Smart calendar logic for the watcher Lambda.

Two passes per hourly run, executed for every user that has a settings record:

1. _materialize_recurrences: turn parent tasks with `recurrence_rule` into
   concrete child tasks inside the user's horizon window. Children are normal
   scheduled tasks linked back via `recurrence_parent_id`.
2. _process_missed_blocks: any non-done task whose scheduled block is fully in
   the past gets bumped at least `reschedule_min_gap_days` days into the
   future, into the next free slot inside working hours. Bump is capped by
   `max_reschedules`; over the cap the task is flagged as blocked.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timedelta, timezone
from typing import Iterable

logger = logging.getLogger(__name__)


CALENDAR_DEFAULTS = {
    "timezone":                 "America/New_York",
    "working_hours_start":      "09:00",
    "working_hours_end":        "17:00",
    "working_days":             [1, 2, 3, 4, 5],
    "slot_minutes":             30,
    "horizon_days":             14,
    "reschedule_min_gap_days":  2,
    "max_reschedules":          3,
    "default_duration_minutes": 60,
}


def _zone(tz_name: str):
    """Return a tzinfo for *tz_name*. Falls back to UTC if zoneinfo lookup fails."""
    try:
        from zoneinfo import ZoneInfo
        return ZoneInfo(tz_name)
    except Exception:
        return timezone.utc


def _coerce_calendar(settings_item: dict) -> dict:
    cal = settings_item.get("calendar") or {}
    if not isinstance(cal, dict):
        cal = {}
    merged = {**CALENDAR_DEFAULTS, **cal}
    # Cast int-like values that may come back from DDB as Decimal
    for k in ("slot_minutes", "horizon_days", "reschedule_min_gap_days",
              "max_reschedules", "default_duration_minutes"):
        merged[k] = int(merged[k])
    if isinstance(merged.get("working_days"), Iterable):
        merged["working_days"] = sorted({int(d) for d in merged["working_days"]})
    return merged


def _parse_iso(value: str) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _hhmm(value: str) -> time:
    h, m = value.split(":")
    return time(int(h), int(m))


def _busy_intervals(tasks: list[dict]) -> list[tuple[float, float, str]]:
    """Return [(start_ts, end_ts, task_id)] for non-done scheduled tasks."""
    out: list[tuple[float, float, str]] = []
    for t in tasks:
        if t.get("status") == "done":
            continue
        start = _parse_iso(t.get("scheduled_start") or "")
        if not start:
            continue
        try:
            dur = int(t.get("duration_minutes") or 30)
        except (TypeError, ValueError):
            continue
        out.append((start.timestamp(), start.timestamp() + dur * 60, t.get("task_id", "")))
    return out


def _slot_is_free(start: datetime, duration_min: int,
                  busy: list[tuple[float, float, str]],
                  exclude_id: str | None = None) -> bool:
    s = start.timestamp()
    e = s + duration_min * 60
    for bs, be, bid in busy:
        if exclude_id and bid == exclude_id:
            continue
        if bs < e and be > s:
            return False
    return True


def _walk_slots(from_dt: datetime, cal: dict, tz, max_horizon_days: int):
    """Yield candidate slot starts (UTC datetimes), aligned to slot_minutes,
    inside the user's working hours/days, going forward from *from_dt*."""
    slot = cal["slot_minutes"]
    work_start = _hhmm(cal["working_hours_start"])
    work_end   = _hhmm(cal["working_hours_end"])
    work_days  = set(cal["working_days"])

    # Work in user-local time, return UTC.
    cur = from_dt.astimezone(tz)
    # Round up to next slot boundary
    minute = (cur.minute // slot) * slot
    cur = cur.replace(minute=minute, second=0, microsecond=0)
    if cur < from_dt.astimezone(tz):
        cur = cur + timedelta(minutes=slot)

    end_horizon = (from_dt + timedelta(days=max_horizon_days)).astimezone(tz)

    while cur < end_horizon:
        if cur.isoweekday() not in work_days:
            cur = (cur + timedelta(days=1)).replace(
                hour=work_start.hour, minute=work_start.minute, second=0, microsecond=0
            )
            continue
        if cur.time() < work_start:
            cur = cur.replace(hour=work_start.hour, minute=work_start.minute)
            continue
        if cur.time() >= work_end:
            cur = (cur + timedelta(days=1)).replace(
                hour=work_start.hour, minute=work_start.minute, second=0, microsecond=0
            )
            continue
        yield cur.astimezone(timezone.utc)
        cur = cur + timedelta(minutes=slot)


def _find_free_slot(from_dt: datetime, duration_min: int, cal: dict, tz,
                    busy: list[tuple[float, float, str]],
                    exclude_id: str | None = None) -> datetime | None:
    """Return the first free working-hours slot of *duration_min* on/after *from_dt*."""
    for slot_start in _walk_slots(from_dt, cal, tz, cal["horizon_days"]):
        # Block must end inside working hours of the same day
        local = slot_start.astimezone(tz)
        end_local = (local + timedelta(minutes=duration_min)).time()
        if end_local > _hhmm(cal["working_hours_end"]) and end_local != time(0, 0):
            continue
        if _slot_is_free(slot_start, duration_min, busy, exclude_id=exclude_id):
            return slot_start
    return None


# ── Recurrence materialization ────────────────────────────────────────────────

def _recurrence_dates(parent_start_local: datetime, rule: dict, today_local: date,
                      horizon_days: int, cal: dict) -> list[datetime]:
    """Return the list of local-tz datetimes a recurring parent should produce
    inside [today, today+horizon_days]. Honours `until` and skips weekends for
    the `weekdays` freq. Children inherit the parent's local time-of-day."""
    freq = rule.get("freq")
    interval = max(1, int(rule.get("interval", 1)))
    until_str = rule.get("until")
    until = date.fromisoformat(until_str) if until_str else None
    by_weekday = set(rule.get("by_weekday") or [])
    work_days = set(cal["working_days"])

    horizon_end = today_local + timedelta(days=horizon_days)
    out: list[datetime] = []

    cur_date = max(parent_start_local.date(), today_local)
    # Anchor stride for daily/weekly to the parent's start date so interval works.
    parent_date = parent_start_local.date()

    while cur_date <= horizon_end:
        if until and cur_date > until:
            break

        accept = False
        if freq == "daily":
            delta = (cur_date - parent_date).days
            accept = delta >= 0 and delta % interval == 0
        elif freq == "weekly":
            delta_weeks = (cur_date - parent_date).days // 7
            week_aligned = (cur_date - parent_date).days % 7 == 0 if not by_weekday else True
            in_set = cur_date.isoweekday() in by_weekday if by_weekday else week_aligned
            accept = (delta_weeks >= 0 and (delta_weeks % interval == 0)) and in_set
        elif freq == "weekdays":
            accept = cur_date.isoweekday() in work_days

        if accept:
            local_dt = datetime.combine(cur_date, parent_start_local.time(),
                                        tzinfo=parent_start_local.tzinfo)
            out.append(local_dt)
        cur_date += timedelta(days=1)
    return out


def materialize_recurrences(tasks_table, user_id: str, tasks: list[dict],
                            cal: dict, now: datetime) -> int:
    """Create concrete child tasks for any recurring parents that are missing
    instances inside the horizon. Returns number of new children created."""
    tz = _zone(cal["timezone"])
    today_local = now.astimezone(tz).date()

    # Map parent_id -> set of existing child instance dates (local)
    children_by_parent: dict[str, set[date]] = {}
    for t in tasks:
        pid = t.get("recurrence_parent_id")
        if not pid:
            continue
        sched = _parse_iso(t.get("scheduled_start") or "")
        if not sched:
            continue
        children_by_parent.setdefault(pid, set()).add(sched.astimezone(tz).date())

    busy = _busy_intervals(tasks)
    created = 0

    for parent in tasks:
        rule = parent.get("recurrence_rule")
        if not rule or parent.get("recurrence_parent_id"):
            continue  # only top-level templates produce children
        parent_start = _parse_iso(parent.get("scheduled_start") or "")
        if not parent_start:
            continue
        try:
            duration = int(parent.get("duration_minutes") or cal["slot_minutes"])
        except (TypeError, ValueError):
            duration = cal["slot_minutes"]

        parent_local = parent_start.astimezone(tz)
        existing = children_by_parent.get(parent["task_id"], set())

        for local_dt in _recurrence_dates(parent_local, rule, today_local,
                                          cal["horizon_days"], cal):
            if local_dt.date() in existing:
                continue
            if local_dt < now.astimezone(tz):
                continue  # don't fill in past slots
            utc_start = local_dt.astimezone(timezone.utc)
            if not _slot_is_free(utc_start, duration, busy):
                continue
            child_id = str(uuid.uuid4())
            child = {
                "user_id":              user_id,
                "task_id":              child_id,
                "title":                parent.get("title", ""),
                "description":          parent.get("description", ""),
                "status":               "todo",
                "priority":             parent.get("priority", "medium"),
                "scheduled_start":      utc_start.isoformat(),
                "duration_minutes":     duration,
                "recurrence_parent_id": parent["task_id"],
                "created_at":           now.isoformat(),
                "updated_at":           now.isoformat(),
            }
            if parent.get("folder_id"):
                child["folder_id"] = parent["folder_id"]
            tasks_table.put_item(Item=child)
            busy.append((utc_start.timestamp(), utc_start.timestamp() + duration * 60, child_id))
            existing.add(local_dt.date())
            created += 1

    return created


# ── Missed-block reschedule ───────────────────────────────────────────────────

def _send_missed_notification(ntfy_post, ntfy_url: str | None, task: dict,
                              new_start: datetime, blocked: bool) -> None:
    if not ntfy_url:
        return
    title = task.get("title", "Task")
    if blocked:
        subj = f"Action needed: {title}"
        body = f"Task has been bumped {task.get('reschedule_count', 0)} times and is now blocked."
        ntfy_post(ntfy_url, subj, body, priority="5")
    else:
        subj = f"Rescheduled: {title}"
        body = f"Moved to {new_start.isoformat()} after a missed slot."
        ntfy_post(ntfy_url, subj, body, priority="3")


def process_missed_blocks(tasks_table, user_id: str, tasks: list[dict], cal: dict,
                          now: datetime, ntfy_post=None, ntfy_url: str | None = None) -> int:
    """Bump or block tasks whose scheduled block is fully in the past."""
    tz = _zone(cal["timezone"])
    busy = _busy_intervals(tasks)
    bumped = 0
    min_gap = cal["reschedule_min_gap_days"]
    cap = cal["max_reschedules"]

    for task in tasks:
        if task.get("status") == "done":
            continue
        sched = _parse_iso(task.get("scheduled_start") or "")
        if not sched:
            continue
        try:
            duration = int(task.get("duration_minutes") or cal["slot_minutes"])
        except (TypeError, ValueError):
            duration = cal["slot_minutes"]

        block_end = sched + timedelta(minutes=duration)
        if block_end > now:
            continue  # still upcoming or in progress
        if task.get("last_missed_at") == sched.isoformat():
            continue  # already handled this miss
        if task.get("blocked_reason") == "max_reschedules":
            continue  # already blocked; don't keep notifying

        count = int(task.get("reschedule_count") or 0)
        if count >= cap:
            tasks_table.update_item(
                Key={"user_id": user_id, "task_id": task["task_id"]},
                UpdateExpression=(
                    "SET blocked_reason = :br, last_missed_at = :lm, updated_at = :u"
                ),
                ExpressionAttributeValues={
                    ":br": "max_reschedules",
                    ":lm": sched.isoformat(),
                    ":u":  now.isoformat(),
                },
            )
            if ntfy_post:
                _send_missed_notification(ntfy_post, ntfy_url, task, sched, blocked=True)
            continue

        # Find the next free slot at least `min_gap` days out (user-local midnight).
        local_today = now.astimezone(tz).date()
        from_local = datetime.combine(
            local_today + timedelta(days=min_gap), time(0, 0), tzinfo=tz
        )
        from_dt = from_local.astimezone(timezone.utc)
        next_start = _find_free_slot(from_dt, duration, cal, tz, busy,
                                     exclude_id=task.get("task_id"))
        if not next_start:
            logger.info("No free slot found in horizon for task %s", task.get("task_id"))
            continue

        tasks_table.update_item(
            Key={"user_id": user_id, "task_id": task["task_id"]},
            UpdateExpression=(
                "SET scheduled_start = :s, last_missed_at = :lm, "
                "reschedule_count = :rc, updated_at = :u"
            ),
            ExpressionAttributeValues={
                ":s":  next_start.isoformat(),
                ":lm": sched.isoformat(),
                ":rc": count + 1,
                ":u":  now.isoformat(),
            },
        )
        # Update busy list so subsequent tasks don't collide with the new slot
        busy = [b for b in busy if b[2] != task.get("task_id")]
        busy.append((next_start.timestamp(),
                     next_start.timestamp() + duration * 60,
                     task.get("task_id", "")))
        bumped += 1
        if ntfy_post:
            _send_missed_notification(ntfy_post, ntfy_url, task, next_start, blocked=False)

    return bumped


def run_calendar_pass(tasks_table, user_id: str, settings_item: dict,
                      now: datetime, ntfy_post=None, ntfy_url: str | None = None,
                      query_user=None) -> tuple[int, int]:
    """Top-level entry: returns (created, bumped) counts."""
    if query_user is None:
        return (0, 0)
    cal = _coerce_calendar(settings_item or {})
    tasks = query_user(tasks_table, user_id)
    bumped = process_missed_blocks(tasks_table, user_id, tasks, cal, now,
                                   ntfy_post=ntfy_post, ntfy_url=ntfy_url)
    # Re-fetch after bumps so child materialization sees current state
    tasks = query_user(tasks_table, user_id)
    created = materialize_recurrences(tasks_table, user_id, tasks, cal, now)
    return (created, bumped)
