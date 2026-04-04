"""Unit tests for lambda/watcher/handler.py."""

import os
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

os.environ["TASKS_TABLE"]       = "test-tasks"
os.environ["SETTINGS_TABLE"]    = "test-settings"
os.environ["HABITS_TABLE"]      = "test-habits"
os.environ["HABIT_LOGS_TABLE"]  = "test-habit-logs"

watcher = load_lambda("watcher", "handler.py")

TASKS_TABLE      = "test-tasks"
SETTINGS_TABLE   = "test-settings"
HABITS_TABLE     = "test-habits"
LOGS_TABLE       = "test-habit-logs"


@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TASKS_TABLE,    "user_id", "task_id")
        make_table(ddb, SETTINGS_TABLE, "user_id")
        make_table(ddb, HABITS_TABLE,   "user_id", "habit_id")
        make_table(ddb, LOGS_TABLE,     "user_id", "log_id")
        yield ddb


# ── _users_with_ntfy ─────────────────────────────────────────────────────────

class TestUsersWithNtfy:
    def test_empty_returns_empty(self, tbls):
        settings = tbls.Table(SETTINGS_TABLE)
        assert watcher._users_with_ntfy(settings) == []

    def test_user_with_ntfy_returned(self, tbls):
        settings = tbls.Table(SETTINGS_TABLE)
        settings.put_item(Item={"user_id": USER, "ntfy_url": "https://ntfy.sh/test"})
        result = watcher._users_with_ntfy(settings)
        assert result == [(USER, "https://ntfy.sh/test")]

    def test_user_without_ntfy_excluded(self, tbls):
        settings = tbls.Table(SETTINGS_TABLE)
        settings.put_item(Item={"user_id": USER, "ntfy_url": ""})
        assert watcher._users_with_ntfy(settings) == []

    def test_user_without_ntfy_field_excluded(self, tbls):
        settings = tbls.Table(SETTINGS_TABLE)
        settings.put_item(Item={"user_id": USER})
        assert watcher._users_with_ntfy(settings) == []

    def test_multiple_users(self, tbls):
        settings = tbls.Table(SETTINGS_TABLE)
        settings.put_item(Item={"user_id": "u1", "ntfy_url": "https://ntfy.sh/u1"})
        settings.put_item(Item={"user_id": "u2", "ntfy_url": ""})
        settings.put_item(Item={"user_id": "u3", "ntfy_url": "https://ntfy.sh/u3"})
        result = watcher._users_with_ntfy(settings)
        user_ids = {uid for uid, _ in result}
        assert user_ids == {"u1", "u3"}


# ── _query_user ───────────────────────────────────────────────────────────────

class TestQueryUser:
    def test_empty_table(self, tbls):
        tasks = tbls.Table(TASKS_TABLE)
        assert watcher._query_user(tasks, USER) == []

    def test_returns_only_user_items(self, tbls):
        tasks = tbls.Table(TASKS_TABLE)
        tasks.put_item(Item={"user_id": USER,    "task_id": "t1", "title": "Mine"})
        tasks.put_item(Item={"user_id": "other", "task_id": "t2", "title": "Theirs"})
        result = watcher._query_user(tasks, USER)
        assert len(result) == 1
        assert result[0]["title"] == "Mine"


# ── lambda_handler: only processes users with ntfy_url ────────────────────────

class TestLambdaHandler:
    def test_skips_users_without_ntfy(self, tbls):
        # Add a task with notifications but no ntfy_url in settings
        tbls.Table(TASKS_TABLE).put_item(Item={
            "user_id": USER, "task_id": "t1",
            "title": "Test", "status": "todo",
            "notifications": {"on_due": True},
            "due_date": "2020-01-01",
        })

        with patch.object(watcher, "_process_task") as mock_process:
            watcher.lambda_handler({}, None)
            mock_process.assert_not_called()

    def test_processes_users_with_ntfy(self, tbls):
        ntfy_url = "https://ntfy.sh/test"
        tbls.Table(SETTINGS_TABLE).put_item(Item={"user_id": USER, "ntfy_url": ntfy_url})
        tbls.Table(TASKS_TABLE).put_item(Item={
            "user_id": USER, "task_id": "t1",
            "title": "Test", "status": "todo",
            "notifications": {"on_due": True},
            "due_date": "2020-01-01",
        })

        with patch.object(watcher, "_process_task") as mock_process, \
             patch.object(watcher, "_is_safe_ntfy_url", return_value=True):
            watcher.lambda_handler({}, None)
            mock_process.assert_called_once()
            _, _, called_url, _ = mock_process.call_args[0]
            assert called_url == ntfy_url
