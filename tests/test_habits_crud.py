#!/usr/bin/env python3
"""
Unit tests for lambda/habits/crud.py — verifies user-scoped DynamoDB queries
and streak/history logic introduced with habit_logs_v2.

No deployment or AWS credentials required.

Usage:
    python -m pytest tests/test_habits_crud.py -v
    make test-unit
"""

import importlib.util
import os
import sys
import unittest
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

# ── Environment + module stubs ────────────────────────────────────────────────

os.environ.setdefault("HABITS_TABLE",     "test-habits")
os.environ.setdefault("HABIT_LOGS_TABLE", "test-habit-logs-v2")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

_mock_boto3 = MagicMock()
_mock_db    = MagicMock()

_mock_response = MagicMock()
_mock_response.ok.side_effect        = lambda body: {"statusCode": 200, "body": body}
_mock_response.created.side_effect   = lambda body: {"statusCode": 201, "body": body}
_mock_response.no_content.return_value = {"statusCode": 204}
_mock_response.error.side_effect     = lambda msg: {"statusCode": 400, "body": msg}
_mock_response.not_found.side_effect = lambda _:   {"statusCode": 404}

_mock_conditions = MagicMock()
_mock_conditions.Key = MagicMock(side_effect=lambda name: MagicMock(
    eq=MagicMock(return_value=MagicMock(
        __and__=MagicMock(return_value=MagicMock())
    )),
    begins_with=MagicMock(return_value=MagicMock()),
    between=MagicMock(return_value=MagicMock()),
))

with patch.dict(sys.modules, {
    "boto3":                     _mock_boto3,
    "boto3.dynamodb":            MagicMock(),
    "boto3.dynamodb.conditions": _mock_conditions,
    "db":                        _mock_db,
    "response":                  _mock_response,
}):
    _spec = importlib.util.spec_from_file_location(
        "habits_crud",
        os.path.join(os.path.dirname(__file__), "..", "lambda", "habits", "crud.py"),
    )
    habits_crud = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(habits_crud)


# ── Helpers ───────────────────────────────────────────────────────────────────

USER_ID  = "user-abc-123"
HABIT_ID = "habit-xyz-456"
TODAY    = date.today()
TODAY_S  = TODAY.isoformat()


def _ok(r):     return r.get("statusCode") == 200
def _created(r): return r.get("statusCode") == 201
def _bad(r):    return r.get("statusCode") == 400
def _not_found(r): return r.get("statusCode") == 404


def _make_logs_table(logged_dates: list[str]) -> MagicMock:
    """Return a mock DynamoDB table whose query() returns items for the given dates."""
    table = MagicMock()
    items = [{"user_id": USER_ID, "log_id": f"{HABIT_ID}#{d}", "habit_id": HABIT_ID}
             for d in logged_dates]
    table.query.return_value = {"Items": items}
    return table


def _make_habits_table(habit: dict | None = None) -> MagicMock:
    table = MagicMock()
    _mock_db.get_item.return_value = habit
    return table


# ── _log_sk ───────────────────────────────────────────────────────────────────

class TestLogSk(unittest.TestCase):
    def test_format(self):
        sk = habits_crud._log_sk("h1", "2025-01-15")
        self.assertEqual(sk, "h1#2025-01-15")


# ── _build_history ────────────────────────────────────────────────────────────

class TestBuildHistory(unittest.TestCase):

    def setUp(self):
        self._orig_logs = habits_crud._logs
        self.thirty_ago = (TODAY - timedelta(days=29)).isoformat()

    def tearDown(self):
        habits_crud._logs = self._orig_logs

    def _run(self, logged_dates):
        mock_table = _make_logs_table(logged_dates)
        habits_crud._logs = lambda: mock_table
        return habits_crud._build_history(USER_ID, HABIT_ID, TODAY_S, self.thirty_ago)

    def test_no_logs_returns_empty_history(self):
        history, done_today, current, best = self._run([])
        self.assertEqual(len(history), 30)
        self.assertFalse(done_today)
        self.assertEqual(current, 0)
        self.assertEqual(best, 0)

    def test_done_today(self):
        _, done_today, _, _ = self._run([TODAY_S])
        self.assertTrue(done_today)

    def test_current_streak_consecutive_from_today(self):
        dates = [(TODAY - timedelta(days=i)).isoformat() for i in range(5)]
        _, _, current, _ = self._run(dates)
        self.assertEqual(current, 5)

    def test_current_streak_breaks_on_gap(self):
        # Done yesterday and today, gap before that
        dates = [TODAY_S, (TODAY - timedelta(days=1)).isoformat()]
        _, _, current, _ = self._run(dates)
        self.assertEqual(current, 2)

    def test_best_streak_in_window(self):
        # 3-day run starting 10 days ago
        dates = [(TODAY - timedelta(days=10 - i)).isoformat() for i in range(3)]
        _, _, _, best = self._run(dates)
        self.assertEqual(best, 3)

    def test_query_called_once_per_build_history(self):
        mock_table = _make_logs_table([])
        habits_crud._logs = lambda: mock_table
        habits_crud._build_history(USER_ID, HABIT_ID, TODAY_S, self.thirty_ago)
        mock_table.query.assert_called_once()

    def test_history_oldest_first(self):
        history, _, _, _ = self._run([])
        dates = [e["date"] for e in history]
        self.assertEqual(dates, sorted(dates))

    def test_history_includes_today(self):
        history, _, _, _ = self._run([])
        self.assertEqual(history[-1]["date"], TODAY_S)


# ── toggle_log ────────────────────────────────────────────────────────────────

class TestToggleLog(unittest.TestCase):

    def setUp(self):
        self._orig_logs   = habits_crud._logs
        self._orig_habits = habits_crud._habits
        _mock_db.get_item.return_value = {"habit_id": HABIT_ID, "user_id": USER_ID, "name": "test"}

    def tearDown(self):
        habits_crud._logs   = self._orig_logs
        habits_crud._habits = self._orig_habits

    def _setup_logs(self, existing_item=None):
        mock_table = MagicMock()
        mock_table.get_item.return_value = {"Item": existing_item} if existing_item else {}
        habits_crud._logs = lambda: mock_table
        return mock_table

    def test_toggle_on_writes_new_item(self):
        mock_logs = self._setup_logs(existing_item=None)
        result = habits_crud.toggle_log(USER_ID, HABIT_ID, {"date": TODAY_S})
        self.assertTrue(_ok(result))
        self.assertTrue(result["body"]["logged"])
        mock_logs.put_item.assert_called_once()
        written = mock_logs.put_item.call_args[1]["Item"]
        self.assertEqual(written["user_id"], USER_ID)
        self.assertEqual(written["log_id"], f"{HABIT_ID}#{TODAY_S}")

    def test_toggle_off_deletes_item(self):
        existing = {"user_id": USER_ID, "log_id": f"{HABIT_ID}#{TODAY_S}"}
        mock_logs = self._setup_logs(existing_item=existing)
        result = habits_crud.toggle_log(USER_ID, HABIT_ID, {"date": TODAY_S})
        self.assertTrue(_ok(result))
        self.assertFalse(result["body"]["logged"])
        mock_logs.delete_item.assert_called_once()

    def test_invalid_date_format_rejected(self):
        self._setup_logs()
        result = habits_crud.toggle_log(USER_ID, HABIT_ID, {"date": "not-a-date"})
        self.assertTrue(_bad(result))

    def test_future_date_rejected(self):
        self._setup_logs()
        future = (TODAY + timedelta(days=1)).isoformat()
        result = habits_crud.toggle_log(USER_ID, HABIT_ID, {"date": future})
        self.assertTrue(_bad(result))

    def test_date_older_than_30_days_rejected(self):
        self._setup_logs()
        old = (TODAY - timedelta(days=30)).isoformat()
        result = habits_crud.toggle_log(USER_ID, HABIT_ID, {"date": old})
        self.assertTrue(_bad(result))

    def test_missing_habit_returns_404(self):
        _mock_db.get_item.return_value = None
        self._setup_logs()
        result = habits_crud.toggle_log(USER_ID, "nonexistent", {"date": TODAY_S})
        self.assertTrue(_not_found(result))


# ── create_habit ──────────────────────────────────────────────────────────────

class TestCreateHabit(unittest.TestCase):

    def setUp(self):
        self._orig_habits = habits_crud._habits
        habits_crud._habits = lambda: MagicMock()

    def tearDown(self):
        habits_crud._habits = self._orig_habits

    def test_create_with_name(self):
        result = habits_crud.create_habit(USER_ID, {"name": "Exercise"})
        self.assertTrue(_created(result))
        self.assertEqual(result["body"]["name"], "Exercise")

    def test_empty_name_rejected(self):
        result = habits_crud.create_habit(USER_ID, {"name": "   "})
        self.assertTrue(_bad(result))

    def test_valid_notify_time_accepted(self):
        result = habits_crud.create_habit(USER_ID, {"name": "Run", "notify_time": "07:30"})
        self.assertTrue(_created(result))

    def test_invalid_notify_time_rejected(self):
        result = habits_crud.create_habit(USER_ID, {"name": "Run", "notify_time": "25:00"})
        self.assertTrue(_bad(result))


if __name__ == "__main__":
    unittest.main(verbosity=2)
