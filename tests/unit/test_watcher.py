"""Unit tests for lambda/watcher/handler.py."""

import os
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

os.environ["TASKS_TABLE"]       = "test-tasks"
os.environ["SETTINGS_TABLE"]    = "test-settings"
os.environ["HABITS_TABLE"]      = "test-habits"
os.environ["HABIT_LOGS_TABLE"]  = "test-habit-logs"
os.environ["MEMORY_TABLE"]      = "test-memory-watcher"
os.environ["JOURNAL_TABLE"]     = "test-journal-watcher"
os.environ["GOALS_TABLE"]       = "test-goals-watcher"
os.environ["NOTES_TABLE"]       = "test-notes-watcher"

watcher = load_lambda("watcher", "handler.py")

TASKS_TABLE      = "test-tasks"
SETTINGS_TABLE   = "test-settings"
HABITS_TABLE     = "test-habits"
LOGS_TABLE       = "test-habit-logs"
MEMORY_TABLE     = "test-memory-watcher"
JOURNAL_TABLE    = "test-journal-watcher"
GOALS_TABLE      = "test-goals-watcher"
NOTES_TABLE      = "test-notes-watcher"


@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TASKS_TABLE,    "user_id", "task_id")
        make_table(ddb, SETTINGS_TABLE, "user_id")
        make_table(ddb, HABITS_TABLE,   "user_id", "habit_id")
        make_table(ddb, LOGS_TABLE,     "user_id", "log_id")
        yield ddb


@pytest.fixture
def inference_tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TASKS_TABLE,    "user_id", "task_id")
        make_table(ddb, SETTINGS_TABLE, "user_id")
        make_table(ddb, HABITS_TABLE,   "user_id", "habit_id")
        make_table(ddb, LOGS_TABLE,     "user_id", "log_id")
        make_table(ddb, MEMORY_TABLE,   "user_id", "memory_key")
        make_table(ddb, JOURNAL_TABLE,  "user_id", "journal_id")
        make_table(ddb, GOALS_TABLE,    "user_id", "goal_id")
        make_table(ddb, NOTES_TABLE,    "user_id", "note_id")
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


# ── _build_activity_context ───────────────────────────────────────────────────

class TestBuildActivityContext:
    def test_empty_returns_empty_string(self):
        result = watcher._build_activity_context([], [], [], [], [])
        assert result == ""

    def test_includes_tasks(self):
        tasks = [{"title": "Go for a run", "status": "todo", "description": "5k route"}]
        result = watcher._build_activity_context(tasks, [], [], [], [])
        assert "Go for a run" in result
        assert "5k route" in result

    def test_includes_habits(self):
        habits = [{"name": "Morning meditation", "description": "10 minutes"}]
        result = watcher._build_activity_context([], habits, [], [], [])
        assert "Morning meditation" in result

    def test_includes_journal(self):
        journal = [{"content": "Today I went hiking", "created_at": "2026-01-01"}]
        result = watcher._build_activity_context([], [], journal, [], [])
        assert "Today I went hiking" in result

    def test_includes_goals(self):
        goals = [{"title": "Run a marathon", "description": "by end of year"}]
        result = watcher._build_activity_context([], [], [], goals, [])
        assert "Run a marathon" in result

    def test_includes_notes(self):
        notes = [{"title": "Recipe ideas", "content": "pasta bolognese", "updated_at": "2026-01-01"}]
        result = watcher._build_activity_context([], [], [], [], notes)
        assert "Recipe ideas" in result


# ── _infer_facts_from_activity ────────────────────────────────────────────────

def _mock_bedrock_text(text: str):
    return {
        "output": {"message": {"content": [{"text": text}]}},
        "usage": {"inputTokens": 10, "outputTokens": 10},
    }


class TestInferFactsFromActivity:
    def test_returns_parsed_facts(self):
        with patch.object(watcher._bedrock, "converse", return_value=_mock_bedrock_text("interests: hiking\ncity: Toronto")):
            facts = watcher._infer_facts_from_activity({}, "some activity")
        assert facts == {"interests": "hiking", "city": "Toronto"}

    def test_none_response_returns_empty(self):
        with patch.object(watcher._bedrock, "converse", return_value=_mock_bedrock_text("NONE")):
            facts = watcher._infer_facts_from_activity({}, "create a task")
        assert facts == {}

    def test_bedrock_failure_returns_empty(self):
        with patch.object(watcher._bedrock, "converse", side_effect=Exception("timeout")):
            facts = watcher._infer_facts_from_activity({}, "some activity")
        assert facts == {}

    def test_skips_internal_keys(self):
        with patch.object(watcher._bedrock, "converse", return_value=_mock_bedrock_text("__secret__: bad\noccupation: developer")):
            facts = watcher._infer_facts_from_activity({}, "some activity")
        assert "__secret__" not in facts
        assert facts.get("occupation") == "developer"

    def test_malformed_lines_skipped(self):
        with patch.object(watcher._bedrock, "converse", return_value=_mock_bedrock_text("no colon here\noccupation: engineer")):
            facts = watcher._infer_facts_from_activity({}, "some activity")
        assert facts.get("occupation") == "engineer"
        assert len(facts) == 1


# ── _run_profile_inference ────────────────────────────────────────────────────

class TestRunProfileInference:
    def test_skips_user_with_inference_disabled(self, inference_tbls):
        inference_tbls.Table(SETTINGS_TABLE).put_item(Item={
            "user_id": USER, "profile_inference_hours": 0,
        })
        with patch.object(watcher._bedrock, "converse") as mock_converse:
            watcher._run_profile_inference(inference_tbls.Table(SETTINGS_TABLE), datetime.now(timezone.utc))
            mock_converse.assert_not_called()

    def test_skips_user_not_due(self, inference_tbls):
        recent_ts = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        inference_tbls.Table(SETTINGS_TABLE).put_item(Item={
            "user_id": USER, "profile_inference_hours": 24,
        })
        inference_tbls.Table(MEMORY_TABLE).put_item(Item={
            "user_id": USER, "memory_key": "__profile_inferred_at__", "value": recent_ts,
        })
        with patch.object(watcher._bedrock, "converse") as mock_converse:
            watcher._run_profile_inference(inference_tbls.Table(SETTINGS_TABLE), datetime.now(timezone.utc))
            mock_converse.assert_not_called()

    def test_runs_when_due(self, inference_tbls):
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
        inference_tbls.Table(SETTINGS_TABLE).put_item(Item={
            "user_id": USER, "profile_inference_hours": 24,
        })
        inference_tbls.Table(MEMORY_TABLE).put_item(Item={
            "user_id": USER, "memory_key": "__profile_inferred_at__", "value": old_ts,
        })
        inference_tbls.Table(TASKS_TABLE).put_item(Item={
            "user_id": USER, "task_id": "t1", "title": "Train for marathon", "status": "todo",
        })
        with patch.object(watcher._bedrock, "converse", return_value=_mock_bedrock_text("fitness_goal: marathon training")):
            watcher._run_profile_inference(inference_tbls.Table(SETTINGS_TABLE), datetime.now(timezone.utc))
        memory = inference_tbls.Table(MEMORY_TABLE)
        item = memory.get_item(Key={"user_id": USER, "memory_key": "fitness_goal"}).get("Item")
        assert item is not None
        assert item["value"] == "marathon training"

    def test_runs_first_time_no_timestamp(self, inference_tbls):
        inference_tbls.Table(SETTINGS_TABLE).put_item(Item={
            "user_id": USER, "profile_inference_hours": 24,
        })
        inference_tbls.Table(HABITS_TABLE).put_item(Item={
            "user_id": USER, "habit_id": "h1", "name": "Daily yoga",
        })
        with patch.object(watcher._bedrock, "converse", return_value=_mock_bedrock_text("workout_style: yoga")):
            watcher._run_profile_inference(inference_tbls.Table(SETTINGS_TABLE), datetime.now(timezone.utc))
        memory = inference_tbls.Table(MEMORY_TABLE)
        item = memory.get_item(Key={"user_id": USER, "memory_key": "workout_style"}).get("Item")
        assert item is not None
        # timestamp was also written
        ts_item = memory.get_item(Key={"user_id": USER, "memory_key": "__profile_inferred_at__"}).get("Item")
        assert ts_item is not None

    def test_updates_timestamp_even_with_no_activity(self, inference_tbls):
        inference_tbls.Table(SETTINGS_TABLE).put_item(Item={
            "user_id": USER, "profile_inference_hours": 24,
        })
        with patch.object(watcher._bedrock, "converse") as mock_converse:
            watcher._run_profile_inference(inference_tbls.Table(SETTINGS_TABLE), datetime.now(timezone.utc))
            mock_converse.assert_not_called()  # no activity data, skips Bedrock
        # timestamp still written
        memory = inference_tbls.Table(MEMORY_TABLE)
        ts_item = memory.get_item(Key={"user_id": USER, "memory_key": "__profile_inferred_at__"}).get("Item")
        assert ts_item is not None
