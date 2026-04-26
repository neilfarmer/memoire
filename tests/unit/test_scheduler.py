"""Unit tests for lambda/watcher/scheduler.py — calendar pass logic."""

import os
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

# Watcher env vars must be set before its module is imported. Force-assign the
# same values test_watcher.py uses so the watcher's module-level constants
# match no matter which test file loads it first (test files share env state).
os.environ["TASKS_TABLE"]       = "test-tasks"
os.environ["SETTINGS_TABLE"]    = "test-settings"
os.environ["HABITS_TABLE"]      = "test-habits"
os.environ["HABIT_LOGS_TABLE"]  = "test-habit-logs"
os.environ["MEMORY_TABLE"]      = "test-memory-watcher"
os.environ["JOURNAL_TABLE"]     = "test-journal-watcher"
os.environ["GOALS_TABLE"]       = "test-goals-watcher"
os.environ["NOTES_TABLE"]       = "test-notes-watcher"

watcher = load_lambda("watcher", "handler.py")
import scheduler  # noqa: E402  pre-registered by conftest.load_lambda

TASKS_TABLE = "test-tasks"


@pytest.fixture
def tasks_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TASKS_TABLE, "user_id", "task_id")
        yield ddb.Table(TASKS_TABLE)


# A Tuesday, 09:00 EDT == 13:00 UTC. April 28, 2026 is a Tuesday.
NOW_UTC = datetime(2026, 4, 28, 13, 0, 0, tzinfo=timezone.utc)


def _cal(**overrides):
    base = dict(scheduler.CALENDAR_DEFAULTS)
    base.update(overrides)
    return base


def _put(table, **fields):
    item = {"user_id": USER, "task_id": fields.pop("task_id", "t-x"), "status": "todo"}
    item.update(fields)
    table.put_item(Item=item)
    return item["task_id"]


# ── _find_free_slot ───────────────────────────────────────────────────────────

class TestFindFreeSlot:
    def test_returns_first_slot_inside_working_hours(self):
        cal = _cal()
        tz = scheduler._zone(cal["timezone"])
        # Pick a from_dt that's already within working hours.
        from_dt = datetime(2026, 4, 28, 13, 0, tzinfo=timezone.utc)  # 09:00 EDT
        slot = scheduler._find_free_slot(from_dt, 30, cal, tz, busy=[])
        assert slot is not None
        local = slot.astimezone(tz)
        assert local.hour == 9 and local.minute == 0

    def test_skips_busy_slot(self):
        cal = _cal()
        tz = scheduler._zone(cal["timezone"])
        from_dt = datetime(2026, 4, 28, 13, 0, tzinfo=timezone.utc)
        # Block the 09:00-09:30 slot
        busy = [(from_dt.timestamp(), from_dt.timestamp() + 30 * 60, "busy-1")]
        slot = scheduler._find_free_slot(from_dt, 30, cal, tz, busy)
        local = slot.astimezone(tz)
        assert local.hour == 9 and local.minute == 30

    def test_jumps_to_next_working_day(self):
        cal = _cal(working_days=[3])  # Wednesday only
        tz = scheduler._zone(cal["timezone"])
        # NOW_UTC is Tuesday 09:00 EDT
        slot = scheduler._find_free_slot(NOW_UTC, 30, cal, tz, busy=[])
        local = slot.astimezone(tz)
        assert local.isoweekday() == 3
        assert local.hour == 9 and local.minute == 0

    def test_returns_none_when_horizon_exhausted(self):
        cal = _cal(horizon_days=1, working_days=[6])  # only Saturday, but horizon=1d
        tz = scheduler._zone(cal["timezone"])
        slot = scheduler._find_free_slot(NOW_UTC, 30, cal, tz, busy=[])
        assert slot is None


# ── _recurrence_dates ─────────────────────────────────────────────────────────

class TestRecurrenceDates:
    def test_daily_every_day(self):
        cal = _cal()
        tz = scheduler._zone(cal["timezone"])
        parent_local = datetime(2026, 4, 28, 9, 0, tzinfo=tz)
        today_local = parent_local.date()
        dates = scheduler._recurrence_dates(parent_local, {"freq": "daily", "interval": 1},
                                            today_local, 5, cal)
        assert len(dates) == 6  # today + 5 horizon days inclusive

    def test_daily_interval_2(self):
        cal = _cal()
        tz = scheduler._zone(cal["timezone"])
        parent_local = datetime(2026, 4, 28, 9, 0, tzinfo=tz)
        dates = scheduler._recurrence_dates(parent_local, {"freq": "daily", "interval": 2},
                                            parent_local.date(), 6, cal)
        # 4/28, 4/30, 5/2, 5/4 — 4 instances
        assert len(dates) == 4

    def test_weekly_by_weekday(self):
        cal = _cal()
        tz = scheduler._zone(cal["timezone"])
        parent_local = datetime(2026, 4, 27, 9, 0, tzinfo=tz)  # Mon 4/27
        dates = scheduler._recurrence_dates(
            parent_local, {"freq": "weekly", "interval": 1, "by_weekday": [1, 3]},
            parent_local.date(), 14, cal,
        )
        weekdays = {d.isoweekday() for d in dates}
        assert weekdays.issubset({1, 3})

    def test_weekdays_skips_weekend(self):
        cal = _cal()
        tz = scheduler._zone(cal["timezone"])
        parent_local = datetime(2026, 4, 24, 9, 0, tzinfo=tz)  # Fri 4/24
        dates = scheduler._recurrence_dates(parent_local, {"freq": "weekdays"},
                                            parent_local.date(), 7, cal)
        for d in dates:
            assert d.isoweekday() in (1, 2, 3, 4, 5)

    def test_until_caps(self):
        cal = _cal()
        tz = scheduler._zone(cal["timezone"])
        parent_local = datetime(2026, 4, 28, 9, 0, tzinfo=tz)
        dates = scheduler._recurrence_dates(
            parent_local, {"freq": "daily", "interval": 1, "until": "2026-04-30"},
            parent_local.date(), 30, cal,
        )
        assert len(dates) == 3  # 4/28, 4/29, 4/30


# ── materialize_recurrences ───────────────────────────────────────────────────

class TestMaterializeRecurrences:
    def test_creates_children_for_daily_template(self, tasks_table):
        _put(tasks_table, task_id="parent",
             title="Standup",
             scheduled_start="2026-04-28T13:00:00+00:00",
             duration_minutes=30,
             recurrence_rule={"freq": "daily", "interval": 1})
        tasks = list(tasks_table.scan()["Items"])
        n = scheduler.materialize_recurrences(tasks_table, USER, tasks, _cal(horizon_days=3), NOW_UTC)
        assert n >= 2  # at least a few future days created
        items = tasks_table.scan()["Items"]
        children = [i for i in items if i.get("recurrence_parent_id") == "parent"]
        assert len(children) == n

    def test_does_not_duplicate_existing_children(self, tasks_table):
        _put(tasks_table, task_id="parent",
             title="Standup",
             scheduled_start="2026-04-28T13:00:00+00:00",
             duration_minutes=30,
             recurrence_rule={"freq": "daily", "interval": 1})
        # Pre-existing child for 4/29
        _put(tasks_table, task_id="kid-1",
             title="Standup",
             scheduled_start="2026-04-29T13:00:00+00:00",
             duration_minutes=30,
             recurrence_parent_id="parent")
        tasks = list(tasks_table.scan()["Items"])
        scheduler.materialize_recurrences(tasks_table, USER, tasks, _cal(horizon_days=3), NOW_UTC)
        items = tasks_table.scan()["Items"]
        starts = [i.get("scheduled_start") for i in items
                  if i.get("recurrence_parent_id") == "parent"]
        # Only one entry per date
        assert len(starts) == len(set(starts))

    def test_skips_when_slot_busy(self, tasks_table):
        _put(tasks_table, task_id="parent",
             title="Standup",
             scheduled_start="2026-04-28T13:00:00+00:00",
             duration_minutes=30,
             recurrence_rule={"freq": "daily", "interval": 1})
        # Block 4/29 13:00 with another task
        _put(tasks_table, task_id="other",
             title="Conflict",
             scheduled_start="2026-04-29T13:00:00+00:00",
             duration_minutes=30)
        tasks = list(tasks_table.scan()["Items"])
        scheduler.materialize_recurrences(tasks_table, USER, tasks, _cal(horizon_days=2), NOW_UTC)
        items = tasks_table.scan()["Items"]
        children_starts = [i["scheduled_start"] for i in items
                           if i.get("recurrence_parent_id") == "parent"]
        assert "2026-04-29T13:00:00+00:00" not in children_starts


# ── process_missed_blocks ─────────────────────────────────────────────────────

class TestProcessMissedBlocks:
    def test_bumps_missed_task_at_least_min_gap_days(self, tasks_table):
        # Yesterday (Mon) 09:00 EDT == 13:00 UTC on 2026-04-27
        _put(tasks_table, task_id="t1",
             title="Missed",
             scheduled_start="2026-04-27T13:00:00+00:00",
             duration_minutes=30)
        tasks = list(tasks_table.scan()["Items"])
        n = scheduler.process_missed_blocks(tasks_table, USER, tasks,
                                            _cal(reschedule_min_gap_days=2), NOW_UTC)
        assert n == 1
        item = tasks_table.get_item(Key={"user_id": USER, "task_id": "t1"})["Item"]
        assert int(item["reschedule_count"]) == 1
        new_start = datetime.fromisoformat(item["scheduled_start"])
        assert (new_start - NOW_UTC) >= timedelta(days=2)

    def test_dedup_via_last_missed_at(self, tasks_table):
        _put(tasks_table, task_id="t1",
             title="Already",
             scheduled_start="2026-04-27T13:00:00+00:00",
             duration_minutes=30,
             last_missed_at="2026-04-27T13:00:00+00:00")
        tasks = list(tasks_table.scan()["Items"])
        n = scheduler.process_missed_blocks(tasks_table, USER, tasks, _cal(), NOW_UTC)
        assert n == 0

    def test_done_tasks_skipped(self, tasks_table):
        _put(tasks_table, task_id="t1",
             title="Done",
             status="done",
             scheduled_start="2026-04-27T13:00:00+00:00",
             duration_minutes=30)
        tasks = list(tasks_table.scan()["Items"])
        n = scheduler.process_missed_blocks(tasks_table, USER, tasks, _cal(), NOW_UTC)
        assert n == 0

    def test_upcoming_tasks_skipped(self, tasks_table):
        _put(tasks_table, task_id="t1",
             title="Future",
             scheduled_start="2026-05-01T13:00:00+00:00",
             duration_minutes=30)
        tasks = list(tasks_table.scan()["Items"])
        n = scheduler.process_missed_blocks(tasks_table, USER, tasks, _cal(), NOW_UTC)
        assert n == 0

    def test_caps_at_max_reschedules(self, tasks_table):
        _put(tasks_table, task_id="t1",
             title="Stale",
             scheduled_start="2026-04-27T13:00:00+00:00",
             duration_minutes=30,
             reschedule_count=3)
        ntfy = MagicMock(return_value=True)
        tasks = list(tasks_table.scan()["Items"])
        scheduler.process_missed_blocks(tasks_table, USER, tasks,
                                        _cal(max_reschedules=3),
                                        NOW_UTC, ntfy_post=ntfy, ntfy_url="https://ntfy.sh/u")
        item = tasks_table.get_item(Key={"user_id": USER, "task_id": "t1"})["Item"]
        assert item.get("blocked_reason") == "max_reschedules"
        # High priority blocked notification was sent
        assert ntfy.called
        args, kwargs = ntfy.call_args
        # _ntfy_post(url, title, body, priority=...)
        assert kwargs.get("priority") == "5" or (len(args) >= 4 and args[3] == "5")

    def test_blocked_task_not_re_notified(self, tasks_table):
        _put(tasks_table, task_id="t1",
             title="Already blocked",
             scheduled_start="2026-04-27T13:00:00+00:00",
             duration_minutes=30,
             blocked_reason="max_reschedules",
             reschedule_count=3)
        ntfy = MagicMock()
        tasks = list(tasks_table.scan()["Items"])
        scheduler.process_missed_blocks(tasks_table, USER, tasks, _cal(max_reschedules=3),
                                        NOW_UTC, ntfy_post=ntfy, ntfy_url="https://ntfy.sh/u")
        ntfy.assert_not_called()

    def test_ntfy_called_for_normal_bump(self, tasks_table):
        _put(tasks_table, task_id="t1",
             title="Slipped",
             scheduled_start="2026-04-27T13:00:00+00:00",
             duration_minutes=30)
        ntfy = MagicMock(return_value=True)
        tasks = list(tasks_table.scan()["Items"])
        scheduler.process_missed_blocks(tasks_table, USER, tasks, _cal(),
                                        NOW_UTC, ntfy_post=ntfy, ntfy_url="https://ntfy.sh/u")
        assert ntfy.called


# ── run_calendar_pass ─────────────────────────────────────────────────────────

class TestRunCalendarPass:
    def test_runs_both_passes(self, tasks_table):
        _put(tasks_table, task_id="parent",
             title="Daily",
             scheduled_start="2026-04-28T13:00:00+00:00",
             duration_minutes=30,
             recurrence_rule={"freq": "daily", "interval": 1})
        _put(tasks_table, task_id="missed",
             title="Missed",
             scheduled_start="2026-04-27T13:00:00+00:00",
             duration_minutes=30)
        settings = {"calendar": {"timezone": "America/New_York", "horizon_days": 3,
                                  "reschedule_min_gap_days": 2, "max_reschedules": 3}}
        created, bumped = scheduler.run_calendar_pass(
            tasks_table, USER, settings, NOW_UTC,
            query_user=watcher._query_user,
        )
        assert bumped == 1
        assert created >= 1
