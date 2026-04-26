"""Unit tests for lambda/tasks/auto_schedule.py."""

import json
import os
from datetime import datetime, timezone
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table, make_links_table

os.environ["TABLE_NAME"]     = "test-tasks"
os.environ["SETTINGS_TABLE"] = "test-settings"

crud = load_lambda("tasks", "crud.py")
auto = load_lambda("tasks", "auto_schedule.py")

TASKS_TABLE    = "test-tasks"
SETTINGS_TABLE = "test-settings"

# A Tuesday, 09:00 EDT == 13:00 UTC
NOW_UTC = datetime(2026, 4, 28, 13, 0, 0, tzinfo=timezone.utc)


@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TASKS_TABLE,    "user_id", "task_id")
        make_table(ddb, SETTINGS_TABLE, "user_id")
        make_links_table(ddb)
        # Default user calendar settings — Mon-Fri 09:00-17:00 EDT, 30-min slots
        ddb.Table(SETTINGS_TABLE).put_item(Item={
            "user_id": USER,
            "calendar": {
                "timezone": "America/New_York",
                "working_hours_start": "09:00",
                "working_hours_end":   "17:00",
                "working_days": [1, 2, 3, 4, 5],
                "slot_minutes": 30,
                "horizon_days": 14,
                "reschedule_min_gap_days": 2,
                "max_reschedules": 3,
            },
        })
        yield ddb


def _frozen_now():
    return patch("auto_schedule.datetime", wraps=datetime,
                 **{"now.return_value": NOW_UTC})


# ── auto_schedule ─────────────────────────────────────────────────────────────

class TestAutoSchedule:
    def test_no_eligible_tasks(self, tbls):
        r = auto.auto_schedule(USER, {})
        body = json.loads(r["body"])
        assert body["scheduled"] == []

    def test_schedules_unscheduled_tasks(self, tbls):
        crud.create_task(USER, {"title": "A", "priority": "high"})
        crud.create_task(USER, {"title": "B", "priority": "low"})
        with patch("auto_schedule.datetime") as dt:
            dt.now.return_value = NOW_UTC
            dt.fromisoformat = datetime.fromisoformat
            r = auto.auto_schedule(USER, {})
        body = json.loads(r["body"])
        assert len(body["scheduled"]) == 2
        # High priority gets the earlier slot
        first = body["scheduled"][0]
        second = body["scheduled"][1]
        assert first["title"] == "A"
        assert first["scheduled_start"] < second["scheduled_start"]

    def test_skips_already_scheduled(self, tbls):
        crud.create_task(USER, {
            "title": "Already",
            "scheduled_start": "2026-04-28T14:00:00Z",
            "duration_minutes": 30,
        })
        with patch("auto_schedule.datetime") as dt:
            dt.now.return_value = NOW_UTC
            dt.fromisoformat = datetime.fromisoformat
            r = auto.auto_schedule(USER, {})
        body = json.loads(r["body"])
        assert body["scheduled"] == []

    def test_recurrence_template_excluded(self, tbls):
        crud.create_task(USER, {
            "title": "Standup",
            "recurrence_rule": {"freq": "daily", "interval": 1},
        })
        with patch("auto_schedule.datetime") as dt:
            dt.now.return_value = NOW_UTC
            dt.fromisoformat = datetime.fromisoformat
            r = auto.auto_schedule(USER, {})
        body = json.loads(r["body"])
        assert body["scheduled"] == []

    def test_specific_task_ids(self, tbls):
        a = json.loads(crud.create_task(USER, {"title": "A"})["body"])
        json.loads(crud.create_task(USER, {"title": "B"})["body"])
        with patch("auto_schedule.datetime") as dt:
            dt.now.return_value = NOW_UTC
            dt.fromisoformat = datetime.fromisoformat
            r = auto.auto_schedule(USER, {"task_ids": [a["task_id"]]})
        body = json.loads(r["body"])
        assert len(body["scheduled"]) == 1
        assert body["scheduled"][0]["task_id"] == a["task_id"]

    def test_overdue_tasks_still_scheduled(self, tbls):
        """Already-overdue tasks should be scheduled into the next free slot."""
        crud.create_task(USER, {"title": "Stale", "due_date": "2026-01-01"})
        with patch("auto_schedule.datetime") as dt:
            dt.now.return_value = NOW_UTC
            dt.fromisoformat = datetime.fromisoformat
            r = auto.auto_schedule(USER, {})
        body = json.loads(r["body"])
        assert len(body["scheduled"]) == 1
        assert body["scheduled"][0]["title"] == "Stale"
        assert body["skipped"] == []

    def test_skipped_when_slot_falls_after_future_due(self, tbls):
        """A not-yet-overdue task whose only free slot lands after its due date is skipped."""
        # Block the entire workday today + tomorrow so the only free slot is after the due date.
        for hour in range(13, 21):  # 09:00 - 17:00 EDT == 13:00 - 21:00 UTC
            crud.create_task(USER, {
                "title": f"Block-{hour}",
                "scheduled_start": f"2026-04-28T{hour:02d}:00:00Z",
                "duration_minutes": 60,
            })
            crud.create_task(USER, {
                "title": f"Block-{hour}-tmrw",
                "scheduled_start": f"2026-04-29T{hour:02d}:00:00Z",
                "duration_minutes": 60,
            })
        crud.create_task(USER, {"title": "DueTomorrow", "due_date": "2026-04-29"})
        with patch("auto_schedule.datetime") as dt:
            dt.now.return_value = NOW_UTC
            dt.fromisoformat = datetime.fromisoformat
            r = auto.auto_schedule(USER, {})
        body = json.loads(r["body"])
        skipped_titles = {s["reason"] for s in body["skipped"]}
        assert "past due date" in skipped_titles

    def test_avoids_overlap_with_existing_block(self, tbls):
        crud.create_task(USER, {
            "title": "Blocker",
            "scheduled_start": "2026-04-28T13:00:00Z",
            "duration_minutes": 60,
        })
        crud.create_task(USER, {"title": "New"})
        with patch("auto_schedule.datetime") as dt:
            dt.now.return_value = NOW_UTC
            dt.fromisoformat = datetime.fromisoformat
            r = auto.auto_schedule(USER, {})
        body = json.loads(r["body"])
        assert len(body["scheduled"]) == 1
        # Slot must be at or after 14:00 UTC (10:00 EDT)
        scheduled_dt = datetime.fromisoformat(body["scheduled"][0]["scheduled_start"])
        assert scheduled_dt >= datetime(2026, 4, 28, 14, 0, tzinfo=timezone.utc)

    def test_horizon_days_validation(self, tbls):
        r = auto.auto_schedule(USER, {"horizon_days": "lots"})
        assert r["statusCode"] == 400

    def test_respect_priority_false(self, tbls):
        json.loads(crud.create_task(USER, {"title": "A", "priority": "low"})["body"])
        json.loads(crud.create_task(USER, {"title": "B", "priority": "high"})["body"])
        with patch("auto_schedule.datetime") as dt:
            dt.now.return_value = NOW_UTC
            dt.fromisoformat = datetime.fromisoformat
            r = auto.auto_schedule(USER, {"respect_priority": False})
        body = json.loads(r["body"])
        # First created should come first when priority is ignored
        assert body["scheduled"][0]["title"] == "A"
