"""Unit tests for lambda/assistant — memory.py and tools.py."""

import json
import os
import sys
import time

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

# ── env vars before module load ───────────────────────────────────────────────
os.environ["CONVERSATIONS_TABLE"] = "test-conversations"
os.environ["MEMORY_TABLE"]        = "test-memory"
os.environ["TASKS_TABLE"]         = "test-tasks-asst"
os.environ["NOTES_TABLE"]         = "test-notes-asst"
os.environ["HABITS_TABLE"]        = "test-habits-asst"
os.environ["GOALS_TABLE"]         = "test-goals-asst"
os.environ["JOURNAL_TABLE"]       = "test-journal-asst"
os.environ["AWS_REGION"]          = "us-east-1"

memory = load_lambda("assistant", "memory.py")
tools  = load_lambda("assistant", "tools.py")


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, "test-conversations",   "user_id", "msg_id")
        make_table(ddb, "test-memory",          "user_id", "memory_key")
        make_table(ddb, "test-tasks-asst",      "user_id", "task_id")
        make_table(ddb, "test-notes-asst",      "user_id", "note_id")
        make_table(ddb, "test-habits-asst",     "user_id", "habit_id")
        make_table(ddb, "test-goals-asst",      "user_id", "goal_id")
        make_table(ddb, "test-journal-asst",    "user_id", "entry_date")
        yield


# ── memory: save and load ─────────────────────────────────────────────────────

class TestMemory:
    def test_save_and_load_memory(self, tbls):
        memory.save_memory(USER, "wake_time", "7am")
        memory.save_memory(USER, "goal", "run a 5k")
        result = memory.load_memory(USER)
        assert result["wake_time"] == "7am"
        assert result["goal"] == "run a 5k"

    def test_load_memory_empty(self, tbls):
        assert memory.load_memory(USER) == {}

    def test_save_and_load_history(self, tbls):
        memory.save_message(USER, "user", "Hello")
        memory.save_message(USER, "assistant", "Hi there!")
        history = memory.load_history(USER)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"][0]["text"] == "Hello"
        assert history[1]["role"] == "assistant"

    def test_load_history_empty(self, tbls):
        assert memory.load_history(USER) == []

    def test_history_starts_with_user(self, tbls):
        # Seed only an assistant message — should be stripped
        memory.save_message(USER, "assistant", "Orphan")
        history = memory.load_history(USER)
        assert history == []

    def test_history_max_messages(self, tbls):
        for i in range(25):
            memory.save_message(USER, "user" if i % 2 == 0 else "assistant", f"msg {i}")
        history = memory.load_history(USER)
        assert len(history) <= memory.MAX_HISTORY

    def test_upsert_memory(self, tbls):
        memory.save_memory(USER, "wake_time", "7am")
        memory.save_memory(USER, "wake_time", "6am")
        result = memory.load_memory(USER)
        assert result["wake_time"] == "6am"


# ── tools: create and list ────────────────────────────────────────────────────

class TestTools:
    def test_create_task(self, tbls):
        result = tools.handle_tool(USER, "create_task", {"title": "Buy groceries"})
        assert "Buy groceries" in result

    def test_create_task_with_priority(self, tbls):
        result = tools.handle_tool(USER, "create_task", {
            "title": "Urgent thing",
            "priority": "high",
            "due_date": "2026-04-10",
        })
        assert "Urgent thing" in result

    def test_list_tasks_empty(self, tbls):
        result = tools.handle_tool(USER, "list_tasks", {})
        assert "No tasks" in result

    def test_list_tasks_shows_created(self, tbls):
        tools.handle_tool(USER, "create_task", {"title": "Walk the dog"})
        result = tools.handle_tool(USER, "list_tasks", {})
        assert "Walk the dog" in result

    def test_list_tasks_filters_done(self, tbls):
        tools.handle_tool(USER, "create_task", {"title": "Done thing"})
        # list_tasks default filters to active (todo/in_progress)
        result = tools.handle_tool(USER, "list_tasks", {"status": "done"})
        assert "No tasks" in result  # nothing is done yet

    def test_create_note(self, tbls):
        result = tools.handle_tool(USER, "create_note", {
            "title": "Recipe idea",
            "body": "Pasta with tomato sauce",
        })
        assert "Recipe idea" in result

    def test_create_habit(self, tbls):
        result = tools.handle_tool(USER, "create_habit", {
            "name": "Morning run",
            "time_of_day": "morning",
        })
        assert "Morning run" in result

    def test_list_habits_empty(self, tbls):
        result = tools.handle_tool(USER, "list_habits", {})
        assert "No habits" in result

    def test_list_habits_shows_created(self, tbls):
        tools.handle_tool(USER, "create_habit", {"name": "Read"})
        result = tools.handle_tool(USER, "list_habits", {})
        assert "Read" in result

    def test_create_goal(self, tbls):
        result = tools.handle_tool(USER, "create_goal", {
            "title": "Learn piano",
            "target_date": "2026-12-31",
        })
        assert "Learn piano" in result

    def test_list_goals_empty(self, tbls):
        result = tools.handle_tool(USER, "list_goals", {})
        assert "No active goals" in result

    def test_list_goals_shows_active(self, tbls):
        tools.handle_tool(USER, "create_goal", {"title": "Run a 5k"})
        result = tools.handle_tool(USER, "list_goals", {})
        assert "Run a 5k" in result

    def test_create_journal_entry(self, tbls):
        result = tools.handle_tool(USER, "create_journal_entry", {
            "body": "Had a great day today",
            "mood": "great",
        })
        assert "journal entry" in result.lower()

    def test_create_journal_entry_upsert(self, tbls):
        tools.handle_tool(USER, "create_journal_entry", {"body": "First write"})
        result = tools.handle_tool(USER, "create_journal_entry", {"body": "Updated write"})
        assert "Updated" in result

    def test_remember_fact(self, tbls):
        result = tools.handle_tool(USER, "remember_fact", {
            "key": "timezone",
            "value": "America/New_York",
        })
        assert "timezone" in result

    def test_unknown_tool(self, tbls):
        result = tools.handle_tool(USER, "nonexistent_tool", {})
        assert "Unknown tool" in result
