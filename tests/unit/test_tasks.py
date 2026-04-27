"""Unit tests for lambda/tasks/crud.py."""

import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table, make_links_table

# ── env vars before module load ───────────────────────────────────────────────
os.environ["TABLE_NAME"] = "test-tasks"

crud = load_lambda("tasks", "crud.py")

TASKS_TABLE = "test-tasks"


@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TASKS_TABLE, "user_id", "task_id")
        make_links_table(ddb)
        yield


# ── _validate_fields ──────────────────────────────────────────────────────────

class TestValidateFields:
    def test_valid_status(self):
        for s in ("todo", "in_progress", "done"):
            assert crud._validate_fields({"status": s}) is None

    def test_invalid_status(self):
        err = crud._validate_fields({"status": "DONE"})
        assert err is not None
        assert "status" in err

    def test_valid_priority(self):
        for p in ("low", "medium", "high"):
            assert crud._validate_fields({"priority": p}) is None

    def test_invalid_priority(self):
        err = crud._validate_fields({"priority": "urgent"})
        assert err is not None

    def test_notifications_must_be_dict(self):
        err = crud._validate_fields({"notifications": "now"})
        assert err is not None

    def test_valid_before_due(self):
        err = crud._validate_fields({"notifications": {"before_due": ["1h", "1d"]}})
        assert err is None

    def test_invalid_before_due_value(self):
        err = crud._validate_fields({"notifications": {"before_due": ["2h"]}})
        assert err is not None

    def test_valid_recurring(self):
        for v in ("1h", "1d", "1w"):
            assert crud._validate_fields({"notifications": {"recurring": v}}) is None

    def test_invalid_recurring(self):
        err = crud._validate_fields({"notifications": {"recurring": "2w"}})
        assert err is not None

    def test_empty_body_valid(self):
        assert crud._validate_fields({}) is None

    def test_scheduled_start_must_be_iso(self):
        err = crud._validate_fields({"scheduled_start": "tomorrow"})
        assert err is not None
        assert "scheduled_start" in err

    def test_scheduled_start_must_align_to_slot(self):
        # 09:07 is not a 15-minute multiple, so it's rejected.
        err = crud._validate_fields({"scheduled_start": "2026-04-26T09:07:00Z"})
        assert err is not None and "15-minute slot" in err

    def test_scheduled_start_15_minute_slots_ok(self):
        # Now that the validator aligns to DURATION_GRAIN_MIN (15) instead of
        # SLOT_MINUTES (30), :15 and :45 are also valid starts.
        for ts in ("2026-04-26T09:15:00Z", "2026-04-26T09:45:00Z"):
            assert crud._validate_fields({"scheduled_start": ts}) is None

    def test_scheduled_start_z_suffix_ok(self):
        assert crud._validate_fields({"scheduled_start": "2026-04-26T09:30:00Z"}) is None

    def test_scheduled_start_offset_ok(self):
        assert crud._validate_fields({"scheduled_start": "2026-04-26T09:30:00+00:00"}) is None

    def test_duration_must_be_multiple_of_15(self):
        err = crud._validate_fields({"duration_minutes": 20})
        assert err is not None

    def test_duration_must_be_positive(self):
        err = crud._validate_fields({"duration_minutes": 0})
        assert err is not None

    def test_duration_max_8h(self):
        err = crud._validate_fields({"duration_minutes": 600})
        assert err is not None

    def test_duration_valid(self):
        for mins in (15, 30, 45, 60, 120, 180, 240):
            assert crud._validate_fields({"duration_minutes": mins}) is None

    def test_recurrence_freq_validated(self):
        err = crud._validate_fields({"recurrence_rule": {"freq": "monthly"}})
        assert err is not None
        assert crud._validate_fields({"recurrence_rule": {"freq": "weekly"}}) is None

    def test_recurrence_by_weekday_range(self):
        err = crud._validate_fields(
            {"recurrence_rule": {"freq": "weekly", "by_weekday": [0]}}
        )
        assert err is not None
        ok = crud._validate_fields(
            {"recurrence_rule": {"freq": "weekly", "by_weekday": [1, 5]}}
        )
        assert ok is None

    def test_recurrence_until_format(self):
        err = crud._validate_fields(
            {"recurrence_rule": {"freq": "daily", "until": "2026/12/31"}}
        )
        assert err is not None


# ── list_tasks ────────────────────────────────────────────────────────────────

class TestListTasks:
    def test_empty(self, tbls):
        r = crud.list_tasks(USER)
        assert r["statusCode"] == 200
        assert json.loads(r["body"]) == []

    def test_returns_own_tasks_only(self, tbls):
        crud.create_task(USER, {"title": "Mine"})
        crud.create_task("other", {"title": "Theirs"})
        items = json.loads(crud.list_tasks(USER)["body"])
        assert len(items) == 1
        assert items[0]["title"] == "Mine"


# ── create_task ───────────────────────────────────────────────────────────────

class TestCreateTask:
    def test_requires_title(self, tbls):
        r = crud.create_task(USER, {})
        assert r["statusCode"] == 400

    def test_blank_title_rejected(self, tbls):
        r = crud.create_task(USER, {"title": "   "})
        assert r["statusCode"] == 400

    def test_creates_with_defaults(self, tbls):
        r = crud.create_task(USER, {"title": "Do something"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["status"] == "todo"
        assert body["priority"] == "medium"
        assert "task_id" in body
        assert "created_at" in body

    def test_creates_with_explicit_fields(self, tbls):
        r = crud.create_task(USER, {
            "title": "Important",
            "status": "in_progress",
            "priority": "high",
            "description": "Details here",
        })
        body = json.loads(r["body"])
        assert body["status"] == "in_progress"
        assert body["priority"] == "high"
        assert body["description"] == "Details here"

    def test_invalid_status_rejected(self, tbls):
        r = crud.create_task(USER, {"title": "Bad", "status": "pending"})
        assert r["statusCode"] == 400

    def test_invalid_priority_rejected(self, tbls):
        r = crud.create_task(USER, {"title": "Bad", "priority": "critical"})
        assert r["statusCode"] == 400

    def test_title_stripped(self, tbls):
        r = crud.create_task(USER, {"title": "  Spaced  "})
        assert json.loads(r["body"])["title"] == "Spaced"

    def test_none_values_not_stored(self, tbls):
        r = crud.create_task(USER, {"title": "No due date"})
        body = json.loads(r["body"])
        assert "due_date" not in body
        assert "notifications" not in body

    def test_title_too_long_rejected(self, tbls):
        r = crud.create_task(USER, {"title": "x" * 501})
        assert r["statusCode"] == 400

    def test_description_too_long_rejected(self, tbls):
        r = crud.create_task(USER, {"title": "OK", "description": "x" * 10_001})
        assert r["statusCode"] == 400


# ── scheduling: overlap + calendar ────────────────────────────────────────────

class TestScheduling:
    def test_create_with_schedule(self, tbls):
        r = crud.create_task(USER, {
            "title": "Standup",
            "scheduled_start": "2026-04-27T13:00:00Z",
            "duration_minutes": 30,
        })
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["scheduled_start"].startswith("2026-04-27T13:00:00")
        assert body["duration_minutes"] == 30

    def test_overlap_rejected(self, tbls):
        crud.create_task(USER, {
            "title": "First",
            "scheduled_start": "2026-04-27T13:00:00Z",
            "duration_minutes": 60,
        })
        r = crud.create_task(USER, {
            "title": "Overlap",
            "scheduled_start": "2026-04-27T13:30:00Z",
            "duration_minutes": 30,
        })
        assert r["statusCode"] == 409

    def test_back_to_back_allowed(self, tbls):
        crud.create_task(USER, {
            "title": "First",
            "scheduled_start": "2026-04-27T13:00:00Z",
            "duration_minutes": 30,
        })
        r = crud.create_task(USER, {
            "title": "Next",
            "scheduled_start": "2026-04-27T13:30:00Z",
            "duration_minutes": 30,
        })
        assert r["statusCode"] == 201

    def test_done_tasks_dont_block(self, tbls):
        first = json.loads(crud.create_task(USER, {
            "title": "Old",
            "scheduled_start": "2026-04-27T13:00:00Z",
            "duration_minutes": 60,
        })["body"])
        crud.update_task(USER, first["task_id"], {"status": "done"})
        r = crud.create_task(USER, {
            "title": "Reuse",
            "scheduled_start": "2026-04-27T13:30:00Z",
            "duration_minutes": 30,
        })
        assert r["statusCode"] == 201

    def test_update_scheduled_start_with_overlap(self, tbls):
        a = json.loads(crud.create_task(USER, {
            "title": "A",
            "scheduled_start": "2026-04-27T13:00:00Z",
            "duration_minutes": 60,
        })["body"])
        json.loads(crud.create_task(USER, {
            "title": "B",
            "scheduled_start": "2026-04-27T15:00:00Z",
            "duration_minutes": 30,
        })["body"])
        r = crud.update_task(USER, a["task_id"], {
            "scheduled_start": "2026-04-27T14:30:00Z",
        })
        assert r["statusCode"] == 409

    def test_update_self_does_not_count_as_overlap(self, tbls):
        a = json.loads(crud.create_task(USER, {
            "title": "A",
            "scheduled_start": "2026-04-27T13:00:00Z",
            "duration_minutes": 60,
        })["body"])
        r = crud.update_task(USER, a["task_id"], {"duration_minutes": 90})
        assert r["statusCode"] == 200

    def test_list_calendar_returns_only_in_range(self, tbls):
        crud.create_task(USER, {
            "title": "in",
            "scheduled_start": "2026-04-27T09:00:00Z",
            "duration_minutes": 30,
        })
        crud.create_task(USER, {
            "title": "out",
            "scheduled_start": "2026-05-15T09:00:00Z",
            "duration_minutes": 30,
        })
        crud.create_task(USER, {"title": "no schedule"})
        r = crud.list_calendar(USER, {"from": "2026-04-26", "to": "2026-04-30"})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        titles = [t["title"] for t in body]
        assert titles == ["in"]

    def test_list_calendar_requires_params(self, tbls):
        r = crud.list_calendar(USER, {})
        assert r["statusCode"] == 400


# ── get_task ──────────────────────────────────────────────────────────────────

class TestGetTask:
    def test_returns_task(self, tbls):
        r = crud.create_task(USER, {"title": "Find me"})
        task_id = json.loads(r["body"])["task_id"]
        got = crud.get_task(USER, task_id)
        assert got["statusCode"] == 200
        assert json.loads(got["body"])["title"] == "Find me"

    def test_not_found(self, tbls):
        r = crud.get_task(USER, "does-not-exist")
        assert r["statusCode"] == 404

    def test_cannot_get_other_users_task(self, tbls):
        r = crud.create_task("alice", {"title": "Alice task"})
        task_id = json.loads(r["body"])["task_id"]
        r2 = crud.get_task("bob", task_id)
        assert r2["statusCode"] == 404


# ── update_task ───────────────────────────────────────────────────────────────

class TestUpdateTask:
    def test_updates_fields(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "Old"})["body"])["task_id"]
        r = crud.update_task(USER, task_id, {"title": "New", "status": "done"})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["title"] == "New"
        assert body["status"] == "done"

    def test_no_valid_fields_returns_400(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "T"})["body"])["task_id"]
        r = crud.update_task(USER, task_id, {"unknown_field": "x"})
        assert r["statusCode"] == 400

    def test_empty_title_rejected(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "T"})["body"])["task_id"]
        r = crud.update_task(USER, task_id, {"title": ""})
        assert r["statusCode"] == 400

    def test_update_nonexistent_task(self, tbls):
        r = crud.update_task(USER, "ghost-id", {"title": "X"})
        assert r["statusCode"] == 404

    def test_invalid_status_in_update(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "T"})["body"])["task_id"]
        r = crud.update_task(USER, task_id, {"status": "DONE"})
        assert r["statusCode"] == 400

    def test_updating_notifications_resets_sent_tracker(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "T"})["body"])["task_id"]
        r = crud.update_task(USER, task_id, {"notifications": {"before_due": ["1d"]}})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body.get("notification_sent") == {}


# ── delete_task ───────────────────────────────────────────────────────────────

class TestDeleteTask:
    def test_deletes_task(self, tbls):
        task_id = json.loads(crud.create_task(USER, {"title": "Bye"})["body"])["task_id"]
        r = crud.delete_task(USER, task_id)
        assert r["statusCode"] == 204
        assert crud.get_task(USER, task_id)["statusCode"] == 404

    def test_delete_nonexistent_returns_404(self, tbls):
        r = crud.delete_task(USER, "ghost")
        assert r["statusCode"] == 404


# ── tags ──────────────────────────────────────────────────────────────────────

class TestTags:
    def test_create_with_tags(self, tbls):
        r = crud.create_task(USER, {"title": "T", "tags": ["work", "urgent"]})
        body = json.loads(r["body"])
        assert body["tags"] == ["work", "urgent"]

    def test_create_default_empty_tags(self, tbls):
        r = crud.create_task(USER, {"title": "T"})
        body = json.loads(r["body"])
        assert body["tags"] == []

    def test_tags_dedup_case_insensitive(self, tbls):
        r = crud.create_task(USER, {"title": "T", "tags": ["Work", "work", "  WORK  "]})
        body = json.loads(r["body"])
        assert body["tags"] == ["Work"]

    def test_tags_accept_csv_string(self, tbls):
        r = crud.create_task(USER, {"title": "T", "tags": "a, b, c"})
        body = json.loads(r["body"])
        assert body["tags"] == ["a", "b", "c"]

    def test_tag_length_limit(self, tbls):
        r = crud.create_task(USER, {"title": "T", "tags": ["x" * 51]})
        assert r["statusCode"] == 400

    def test_too_many_tags(self, tbls):
        r = crud.create_task(USER, {"title": "T", "tags": [f"t{i}" for i in range(21)]})
        assert r["statusCode"] == 400

    def test_update_replaces_tags(self, tbls):
        created = json.loads(crud.create_task(USER, {"title": "T", "tags": ["a"]})["body"])
        r = crud.update_task(USER, created["task_id"], {"tags": ["b", "c"]})
        body = json.loads(r["body"])
        assert body["tags"] == ["b", "c"]
