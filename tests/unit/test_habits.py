"""Unit tests for lambda/habits/crud.py."""

import json
import os
from datetime import date, timedelta

import boto3
import pytest
from freezegun import freeze_time
from moto import mock_aws

from conftest import USER, load_lambda, make_table

os.environ["HABITS_TABLE"] = "test-habits"
os.environ["HABIT_LOGS_TABLE"] = "test-habit-logs"

crud = load_lambda("habits", "crud.py")

HABITS_TABLE = "test-habits"
LOGS_TABLE = "test-habit-logs"
TODAY = "2024-06-15"
THIRTY_AGO = "2024-05-17"  # 29 days before 2024-06-15


@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, HABITS_TABLE, "user_id", "habit_id")
        make_table(ddb, LOGS_TABLE, "user_id", "log_id")
        yield ddb


# ── _validate_time ────────────────────────────────────────────────────────────

class TestValidateTime:
    def test_valid_times(self):
        assert crud._validate_time("00:00") is None
        assert crud._validate_time("09:30") is None
        assert crud._validate_time("23:59") is None

    def test_wrong_format(self):
        assert crud._validate_time("9:30") is not None
        assert crud._validate_time("0930") is not None
        assert crud._validate_time("09:60") is not None

    def test_invalid_hour(self):
        assert crud._validate_time("24:00") is not None

    def test_invalid_minute(self):
        assert crud._validate_time("12:60") is not None


# ── create_habit ──────────────────────────────────────────────────────────────

class TestCreateHabit:
    @freeze_time(TODAY)
    def test_requires_name(self, tbls):
        r = crud.create_habit(USER, {})
        assert r["statusCode"] == 400

    @freeze_time(TODAY)
    def test_blank_name_rejected(self, tbls):
        r = crud.create_habit(USER, {"name": "  "})
        assert r["statusCode"] == 400

    @freeze_time(TODAY)
    def test_creates_habit(self, tbls):
        r = crud.create_habit(USER, {"name": "Exercise"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["name"] == "Exercise"
        assert "habit_id" in body
        assert body["done_today"] is False
        assert body["current_streak"] == 0

    @freeze_time(TODAY)
    def test_valid_notify_time(self, tbls):
        r = crud.create_habit(USER, {"name": "Wake up", "notify_time": "07:00"})
        assert r["statusCode"] == 201
        assert json.loads(r["body"])["notify_time"] == "07:00"

    @freeze_time(TODAY)
    def test_invalid_notify_time_rejected(self, tbls):
        r = crud.create_habit(USER, {"name": "X", "notify_time": "25:00"})
        assert r["statusCode"] == 400

    @freeze_time(TODAY)
    def test_empty_notify_time_omitted(self, tbls):
        r = crud.create_habit(USER, {"name": "X", "notify_time": ""})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert "notify_time" not in body


# ── list_habits ───────────────────────────────────────────────────────────────

class TestListHabits:
    @freeze_time(TODAY)
    def test_empty(self, tbls):
        r = crud.list_habits(USER)
        assert r["statusCode"] == 200
        assert json.loads(r["body"]) == []

    @freeze_time(TODAY)
    def test_returns_habit_with_history(self, tbls):
        crud.create_habit(USER, {"name": "Read"})
        items = json.loads(crud.list_habits(USER)["body"])
        assert len(items) == 1
        assert "history" in items[0]
        assert len(items[0]["history"]) == 30

    @freeze_time(TODAY)
    def test_done_today_false_when_no_log(self, tbls):
        crud.create_habit(USER, {"name": "Run"})
        items = json.loads(crud.list_habits(USER)["body"])
        assert items[0]["done_today"] is False

    @freeze_time(TODAY)
    def test_done_today_true_after_toggle(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        crud.toggle_log(USER, habit_id, {"date": TODAY})
        items = json.loads(crud.list_habits(USER)["body"])
        assert items[0]["done_today"] is True

    @freeze_time(TODAY)
    def test_isolates_users(self, tbls):
        crud.create_habit(USER, {"name": "Mine"})
        crud.create_habit("other", {"name": "Theirs"})
        items = json.loads(crud.list_habits(USER)["body"])
        assert len(items) == 1


# ── update_habit ──────────────────────────────────────────────────────────────

class TestUpdateHabit:
    @freeze_time(TODAY)
    def test_updates_name(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Old"})["body"])["habit_id"]
        r = crud.update_habit(USER, habit_id, {"name": "New"})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["name"] == "New"

    @freeze_time(TODAY)
    def test_updates_notify_time(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "X"})["body"])["habit_id"]
        r = crud.update_habit(USER, habit_id, {"notify_time": "08:00"})
        assert r["statusCode"] == 200

    @freeze_time(TODAY)
    def test_empty_name_rejected(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "X"})["body"])["habit_id"]
        r = crud.update_habit(USER, habit_id, {"name": ""})
        assert r["statusCode"] == 400

    @freeze_time(TODAY)
    def test_nonexistent_habit_returns_404(self, tbls):
        r = crud.update_habit(USER, "ghost", {"name": "X"})
        assert r["statusCode"] == 404

    @freeze_time(TODAY)
    def test_no_fields_returns_ok(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "X"})["body"])["habit_id"]
        r = crud.update_habit(USER, habit_id, {})
        assert r["statusCode"] == 200


# ── delete_habit ──────────────────────────────────────────────────────────────

class TestDeleteHabit:
    @freeze_time(TODAY)
    def test_deletes_habit(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Bye"})["body"])["habit_id"]
        r = crud.delete_habit(USER, habit_id)
        assert r["statusCode"] == 204
        items = json.loads(crud.list_habits(USER)["body"])
        assert items == []

    @freeze_time(TODAY)
    def test_nonexistent_returns_404(self, tbls):
        assert crud.delete_habit(USER, "ghost")["statusCode"] == 404

    @freeze_time(TODAY)
    def test_cascade_deletes_logs(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        crud.toggle_log(USER, habit_id, {"date": TODAY})
        crud.delete_habit(USER, habit_id)
        # Log should be gone
        logs_tbl = boto3.resource("dynamodb", region_name="us-east-1").Table(LOGS_TABLE)
        resp = logs_tbl.get_item(Key={"user_id": USER, "log_id": f"{habit_id}#{TODAY}"})
        assert "Item" not in resp


# ── toggle_log ────────────────────────────────────────────────────────────────

class TestToggleLog:
    @freeze_time(TODAY)
    def test_creates_log(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        r = crud.toggle_log(USER, habit_id, {"date": TODAY})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["logged"] is True

    @freeze_time(TODAY)
    def test_deletes_log_on_second_toggle(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        crud.toggle_log(USER, habit_id, {"date": TODAY})
        r = crud.toggle_log(USER, habit_id, {"date": TODAY})
        assert json.loads(r["body"])["logged"] is False

    @freeze_time(TODAY)
    def test_defaults_to_today_when_no_date(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        r = crud.toggle_log(USER, habit_id, {})
        body = json.loads(r["body"])
        assert body["date"] == TODAY
        assert body["logged"] is True

    @freeze_time(TODAY)
    def test_date_outside_window_rejected(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        old_date = (date.fromisoformat(TODAY) - timedelta(days=31)).isoformat()
        r = crud.toggle_log(USER, habit_id, {"date": old_date})
        assert r["statusCode"] == 400

    @freeze_time(TODAY)
    def test_future_date_rejected(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        future = (date.fromisoformat(TODAY) + timedelta(days=1)).isoformat()
        r = crud.toggle_log(USER, habit_id, {"date": future})
        assert r["statusCode"] == 400

    @freeze_time(TODAY)
    def test_invalid_date_format_rejected(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        r = crud.toggle_log(USER, habit_id, {"date": "15-06-2024"})
        assert r["statusCode"] == 400

    @freeze_time(TODAY)
    def test_nonexistent_habit_returns_404(self, tbls):
        r = crud.toggle_log(USER, "ghost", {"date": TODAY})
        assert r["statusCode"] == 404


# ── _build_history streak logic ───────────────────────────────────────────────

class TestBuildHistory:
    @freeze_time(TODAY)
    def test_no_logs_zero_streaks(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        history, done_today, current, best = crud._build_history(USER, habit_id, TODAY, THIRTY_AGO)
        assert current == 0
        assert best == 0
        assert done_today is False

    @freeze_time(TODAY)
    def test_streak_counted_from_today(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        for i in range(3):
            d = (date.fromisoformat(TODAY) - timedelta(days=i)).isoformat()
            crud.toggle_log(USER, habit_id, {"date": d})
        _, _, current, best = crud._build_history(USER, habit_id, TODAY, THIRTY_AGO)
        assert current == 3
        assert best == 3

    @freeze_time(TODAY)
    def test_streak_broken_by_missed_day(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        # Done today and 2 days ago, but NOT yesterday.
        # current streak = 1 (only today, broken by yesterday's gap).
        # best streak = 1 (no two consecutive done days).
        crud.toggle_log(USER, habit_id, {"date": TODAY})
        two_ago = (date.fromisoformat(TODAY) - timedelta(days=2)).isoformat()
        crud.toggle_log(USER, habit_id, {"date": two_ago})
        _, _, current, best = crud._build_history(USER, habit_id, TODAY, THIRTY_AGO)
        assert current == 1
        assert best == 1

    @freeze_time(TODAY)
    def test_history_length_is_30(self, tbls):
        habit_id = json.loads(crud.create_habit(USER, {"name": "Run"})["body"])["habit_id"]
        history, _, _, _ = crud._build_history(USER, habit_id, TODAY, THIRTY_AGO)
        assert len(history) == 30
