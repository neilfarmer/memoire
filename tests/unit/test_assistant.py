"""Unit tests for lambda/assistant — memory.py, tools.py, and chat.py."""

import json
import os
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

# ── env vars must be set before module load ───────────────────────────────────
os.environ["CONVERSATIONS_TABLE"] = "test-conversations"
os.environ["MEMORY_TABLE"]        = "test-memory"
os.environ["TASKS_TABLE"]         = "test-tasks-asst"
os.environ["NOTES_TABLE"]         = "test-notes-asst"
os.environ["NOTE_FOLDERS_TABLE"]  = "test-note-folders-asst"
os.environ["HABITS_TABLE"]        = "test-habits-asst"
os.environ["GOALS_TABLE"]         = "test-goals-asst"
os.environ["JOURNAL_TABLE"]       = "test-journal-asst"
os.environ["NUTRITION_TABLE"]     = "test-nutrition-asst"
os.environ["HEALTH_TABLE"]        = "test-health-asst"
os.environ["AWS_REGION"]          = "us-east-1"
os.environ["TOKENS_TABLE"]        = "test-tokens"
os.environ["JWKS_URI"]            = "https://cognito.example.com/.well-known/jwks.json"
os.environ["JWT_ISSUER"]          = "https://cognito.example.com"
os.environ["JWT_AUDIENCE"]        = "test-client-id"

memory     = load_lambda("assistant", "memory.py")
tools      = load_lambda("assistant", "tools.py")
chat       = load_lambda("assistant", "chat.py")
token_auth = load_lambda("assistant", "token_auth.py")
# auth must be pre-registered so handler.py's `from auth import ...` resolves
from conftest import LAYER_DIR, _register as _reg
if "auth" not in __import__("sys").modules:
    _reg(LAYER_DIR / "auth.py", "auth")
handler    = load_lambda("assistant", "handler.py")


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def tbls():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, "test-conversations",     "user_id", "msg_id")
        make_table(ddb, "test-memory",            "user_id", "memory_key")
        make_table(ddb, "test-tasks-asst",        "user_id", "task_id")
        make_table(ddb, "test-notes-asst",        "user_id", "note_id")
        make_table(ddb, "test-note-folders-asst", "user_id", "folder_id")
        make_table(ddb, "test-habits-asst",       "user_id", "habit_id")
        make_table(ddb, "test-goals-asst",        "user_id", "goal_id")
        make_table(ddb, "test-journal-asst",      "user_id", "entry_date")
        make_table(ddb, "test-nutrition-asst",    "user_id", "log_date")
        make_table(ddb, "test-health-asst",       "user_id", "log_date")
        # Tokens table with token-hash GSI (used by token_auth PAT lookup)
        ddb.create_table(
            TableName="test-tokens",
            KeySchema=[
                {"AttributeName": "user_id",  "KeyType": "HASH"},
                {"AttributeName": "token_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id",    "AttributeType": "S"},
                {"AttributeName": "token_id",   "AttributeType": "S"},
                {"AttributeName": "token_hash", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "token-hash-index",
                "KeySchema": [{"AttributeName": "token_hash", "KeyType": "HASH"}],
                "Projection": {"ProjectionType": "KEYS_ONLY"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


# ── memory: facts ─────────────────────────────────────────────────────────────

class TestMemoryFacts:
    def test_save_and_load_facts(self, tbls):
        memory.save_memory(USER, "wake_time", "7am")
        memory.save_memory(USER, "goal", "run a 5k")
        facts, master = memory.load_memory(USER)
        assert facts["wake_time"] == "7am"
        assert facts["goal"] == "run a 5k"

    def test_load_memory_empty(self, tbls):
        facts, master = memory.load_memory(USER)
        assert facts == {}
        assert master == ""

    def test_upsert_fact(self, tbls):
        memory.save_memory(USER, "wake_time", "7am")
        memory.save_memory(USER, "wake_time", "6am")
        facts, _ = memory.load_memory(USER)
        assert facts["wake_time"] == "6am"

    def test_internal_keys_excluded_from_facts(self, tbls):
        # Usage keys start with __ and must not appear in facts
        memory.update_model_usage(USER, "us.amazon.nova-lite-v1:0", 100, 50)
        facts, _ = memory.load_memory(USER)
        assert not any(k.startswith("__") for k in facts)

    def test_master_context_excluded_from_facts(self, tbls):
        memory.save_master_context(USER, "Neil is a software engineer.")
        facts, master = memory.load_memory(USER)
        assert "__master_context__" not in facts
        assert master == "Neil is a software engineer."

    def test_save_master_context(self, tbls):
        memory.save_master_context(USER, "Loves cycling and coffee.")
        _, master = memory.load_memory(USER)
        assert master == "Loves cycling and coffee."

    def test_overwrite_master_context(self, tbls):
        memory.save_master_context(USER, "First version.")
        memory.save_master_context(USER, "Second version.")
        _, master = memory.load_memory(USER)
        assert master == "Second version."


# ── memory: history ───────────────────────────────────────────────────────────

class TestMemoryHistory:
    def test_save_and_load(self, tbls):
        memory.save_message(USER, "user", "Hello")
        memory.save_message(USER, "assistant", "Hi there!")
        history = memory.load_history(USER)
        assert len(history) == 2
        assert history[0]["role"] == "user"
        assert history[0]["content"][0]["text"] == "Hello"
        assert history[1]["role"] == "assistant"

    def test_empty(self, tbls):
        assert memory.load_history(USER) == []

    def test_must_start_with_user(self, tbls):
        # Orphaned assistant message at front should be stripped
        memory.save_message(USER, "assistant", "Orphan")
        assert memory.load_history(USER) == []

    def test_max_messages_capped(self, tbls):
        for i in range(25):
            memory.save_message(USER, "user" if i % 2 == 0 else "assistant", f"msg {i}")
        history = memory.load_history(USER)
        assert len(history) <= memory.MAX_HISTORY

    def test_consecutive_same_role_merged(self, tbls):
        memory.save_message(USER, "user", "First")
        memory.save_message(USER, "user", "Second")
        memory.save_message(USER, "assistant", "Reply")
        history = memory.load_history(USER)
        # Two user messages should merge into one
        assert history[0]["role"] == "user"
        assert "First" in history[0]["content"][0]["text"]
        assert "Second" in history[0]["content"][0]["text"]

    def test_clear_history(self, tbls):
        memory.save_message(USER, "user", "Hello")
        memory.save_message(USER, "assistant", "Hi")
        memory.clear_history(USER)
        assert memory.load_history(USER) == []


# ── memory: model usage ───────────────────────────────────────────────────────

class TestMemoryUsage:
    def test_update_and_load(self, tbls):
        memory.update_model_usage(USER, "nova-lite", 100, 50)
        usage = memory.load_model_usage(USER)
        assert len(usage) == 1
        assert usage[0]["model_id"] == "nova-lite"
        assert usage[0]["invocations"] == 1
        assert usage[0]["input_tokens"] == 100
        assert usage[0]["output_tokens"] == 50

    def test_increments_on_second_call(self, tbls):
        memory.update_model_usage(USER, "nova-lite", 100, 50)
        memory.update_model_usage(USER, "nova-lite", 200, 80)
        usage = memory.load_model_usage(USER)
        assert usage[0]["invocations"] == 2
        assert usage[0]["input_tokens"] == 300
        assert usage[0]["output_tokens"] == 130

    def test_multiple_models_tracked_separately(self, tbls):
        memory.update_model_usage(USER, "nova-lite", 100, 50)
        memory.update_model_usage(USER, "nova-pro",  500, 200)
        usage = {u["model_id"]: u for u in memory.load_model_usage(USER)}
        assert usage["nova-lite"]["invocations"] == 1
        assert usage["nova-pro"]["invocations"] == 1

    def test_empty_returns_empty_list(self, tbls):
        assert memory.load_model_usage(USER) == []


# ── tools: tasks ──────────────────────────────────────────────────────────────

class TestToolsTasks:
    def test_create_task(self, tbls):
        result = tools.handle_tool(USER, "create_task", {"title": "Buy groceries"})
        assert "Buy groceries" in result

    def test_create_task_with_priority_and_due(self, tbls):
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

    def test_list_tasks_includes_id(self, tbls):
        tools.handle_tool(USER, "create_task", {"title": "Check IDs"})
        result = tools.handle_tool(USER, "list_tasks", {})
        assert "[id:" in result

    def test_list_tasks_filters_done_status(self, tbls):
        result = tools.handle_tool(USER, "list_tasks", {"status": "done"})
        assert "No tasks" in result

    def test_complete_task(self, tbls):
        tools.handle_tool(USER, "create_task", {"title": "Finish report"})
        listing = tools.handle_tool(USER, "list_tasks", {})
        task_id = listing.split("[id:")[1].split("]")[0]
        result = tools.handle_tool(USER, "complete_task", {"task_id": task_id})
        assert "done" in result.lower()

    def test_complete_task_not_found(self, tbls):
        result = tools.handle_tool(USER, "complete_task", {"task_id": "nonexistent"})
        assert "not found" in result.lower()

    def test_delete_task(self, tbls):
        tools.handle_tool(USER, "create_task", {"title": "Delete me"})
        listing = tools.handle_tool(USER, "list_tasks", {})
        task_id = listing.split("[id:")[1].split("]")[0]
        result = tools.handle_tool(USER, "delete_task", {"task_id": task_id})
        assert "Deleted" in result
        assert "Delete me" in result

    def test_delete_task_not_found(self, tbls):
        result = tools.handle_tool(USER, "delete_task", {"task_id": "ghost"})
        assert "not found" in result.lower()

    def test_complete_then_list_done(self, tbls):
        tools.handle_tool(USER, "create_task", {"title": "Will be done"})
        listing = tools.handle_tool(USER, "list_tasks", {})
        task_id = listing.split("[id:")[1].split("]")[0]
        tools.handle_tool(USER, "complete_task", {"task_id": task_id})
        done = tools.handle_tool(USER, "list_tasks", {"status": "done"})
        assert "Will be done" in done


# ── tools: notes ──────────────────────────────────────────────────────────────

class TestToolsNotes:
    def test_create_note(self, tbls):
        result = tools.handle_tool(USER, "create_note", {
            "title": "Recipe idea",
            "body": "Pasta with tomato sauce",
        })
        assert "Recipe idea" in result

    def test_create_note_in_folder(self, tbls):
        result = tools.handle_tool(USER, "create_note", {
            "title": "Meeting notes",
            "folder_name": "Work",
        })
        assert "Meeting notes" in result
        assert "Work" in result

    def test_create_note_creates_folder_if_needed(self, tbls):
        tools.handle_tool(USER, "create_note", {"title": "Note", "folder_name": "NewFolder"})
        folders = tools.handle_tool(USER, "list_note_folders", {})
        assert "NewFolder" in folders

    def test_list_notes_empty(self, tbls):
        result = tools.handle_tool(USER, "list_notes", {})
        assert "No notes" in result

    def test_list_notes_shows_created(self, tbls):
        tools.handle_tool(USER, "create_note", {"title": "My note"})
        result = tools.handle_tool(USER, "list_notes", {})
        assert "My note" in result

    def test_list_notes_filter_by_folder(self, tbls):
        tools.handle_tool(USER, "create_note", {"title": "Work note", "folder_name": "Work"})
        tools.handle_tool(USER, "create_note", {"title": "Personal note", "folder_name": "Personal"})
        work = tools.handle_tool(USER, "list_notes", {"folder_name": "Work"})
        assert "Work note" in work
        assert "Personal note" not in work

    def test_list_notes_filter_unknown_folder(self, tbls):
        result = tools.handle_tool(USER, "list_notes", {"folder_name": "DoesNotExist"})
        assert "No folder" in result or "not found" in result.lower()

    def test_delete_note(self, tbls):
        tools.handle_tool(USER, "create_note", {"title": "Delete me"})
        listing = tools.handle_tool(USER, "list_notes", {})
        note_id = listing.split("[")[1].split("]")[0]
        result = tools.handle_tool(USER, "delete_note", {"note_id": note_id})
        assert "Deleted" in result

    def test_delete_note_not_found(self, tbls):
        result = tools.handle_tool(USER, "delete_note", {"note_id": "ghost"})
        assert "not found" in result.lower()

    def test_create_note_folder(self, tbls):
        result = tools.handle_tool(USER, "create_note_folder", {"name": "Archive"})
        assert "Archive" in result

    def test_create_note_folder_duplicate(self, tbls):
        tools.handle_tool(USER, "create_note_folder", {"name": "Archive"})
        result = tools.handle_tool(USER, "create_note_folder", {"name": "Archive"})
        assert "already exists" in result.lower()

    def test_list_note_folders_empty(self, tbls):
        result = tools.handle_tool(USER, "list_note_folders", {})
        assert "No note folders" in result

    def test_list_note_folders_shows_created(self, tbls):
        tools.handle_tool(USER, "create_note_folder", {"name": "Projects"})
        result = tools.handle_tool(USER, "list_note_folders", {})
        assert "Projects" in result


# ── tools: habits ─────────────────────────────────────────────────────────────

class TestToolsHabits:
    def test_create_habit(self, tbls):
        result = tools.handle_tool(USER, "create_habit", {"name": "Morning run", "time_of_day": "morning"})
        assert "Morning run" in result

    def test_list_habits_empty(self, tbls):
        result = tools.handle_tool(USER, "list_habits", {})
        assert "No habits" in result

    def test_list_habits_shows_created(self, tbls):
        tools.handle_tool(USER, "create_habit", {"name": "Read"})
        result = tools.handle_tool(USER, "list_habits", {})
        assert "Read" in result

    def test_toggle_habit_completes(self, tbls):
        tools.handle_tool(USER, "create_habit", {"name": "Meditate"})
        tools.handle_tool(USER, "list_habits", {})
        # Extract habit_id via list_tasks pattern doesn't work for habits
        # Use the db directly — toggle by finding the habit through create→list→parse
        # Habits list doesn't expose IDs; test toggle via handle_tool with known ID
        # We need to get the habit_id — create one and fetch from db
        import boto3
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-habits-asst")
        items = table.query(
            KeyConditionExpression="user_id = :u",
            ExpressionAttributeValues={":u": USER},
        )["Items"]
        habit_id = items[0]["habit_id"]
        result = tools.handle_tool(USER, "toggle_habit", {"habit_id": habit_id, "_today": "2026-01-01"})
        assert "completed" in result.lower()

    def test_toggle_habit_toggles_off(self, tbls):
        tools.handle_tool(USER, "create_habit", {"name": "Yoga"})
        import boto3
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-habits-asst")
        items = table.query(
            KeyConditionExpression="user_id = :u",
            ExpressionAttributeValues={":u": USER},
        )["Items"]
        habit_id = items[0]["habit_id"]
        tools.handle_tool(USER, "toggle_habit", {"habit_id": habit_id, "_today": "2026-01-01"})
        result = tools.handle_tool(USER, "toggle_habit", {"habit_id": habit_id, "_today": "2026-01-01"})
        assert "un-completed" in result.lower()

    def test_toggle_habit_not_found(self, tbls):
        result = tools.handle_tool(USER, "toggle_habit", {"habit_id": "ghost"})
        assert "not found" in result.lower()

    def test_delete_habit(self, tbls):
        tools.handle_tool(USER, "create_habit", {"name": "Delete me"})
        import boto3
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-habits-asst")
        items = table.query(
            KeyConditionExpression="user_id = :u",
            ExpressionAttributeValues={":u": USER},
        )["Items"]
        habit_id = items[0]["habit_id"]
        result = tools.handle_tool(USER, "delete_habit", {"habit_id": habit_id})
        assert "Deleted" in result

    def test_delete_habit_not_found(self, tbls):
        result = tools.handle_tool(USER, "delete_habit", {"habit_id": "ghost"})
        assert "not found" in result.lower()


# ── tools: goals ──────────────────────────────────────────────────────────────

class TestToolsGoals:
    def test_create_goal(self, tbls):
        result = tools.handle_tool(USER, "create_goal", {"title": "Learn piano", "target_date": "2026-12-31"})
        assert "Learn piano" in result

    def test_list_goals_empty(self, tbls):
        result = tools.handle_tool(USER, "list_goals", {})
        assert "No active goals" in result

    def test_list_goals_shows_active(self, tbls):
        tools.handle_tool(USER, "create_goal", {"title": "Run a 5k"})
        result = tools.handle_tool(USER, "list_goals", {})
        assert "Run a 5k" in result

    def _get_goal_id(self):
        import boto3
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-goals-asst")
        items = table.query(
            KeyConditionExpression="user_id = :u",
            ExpressionAttributeValues={":u": USER},
        )["Items"]
        return items[0]["goal_id"]

    def test_update_goal_progress(self, tbls):
        tools.handle_tool(USER, "create_goal", {"title": "Write a book"})
        goal_id = self._get_goal_id()
        result = tools.handle_tool(USER, "update_goal_progress", {"goal_id": goal_id, "progress": 50})
        assert "50%" in result

    def test_update_goal_status(self, tbls):
        tools.handle_tool(USER, "create_goal", {"title": "Ship it"})
        goal_id = self._get_goal_id()
        result = tools.handle_tool(USER, "update_goal_progress", {"goal_id": goal_id, "status": "completed"})
        assert "completed" in result.lower()

    def test_update_goal_not_found(self, tbls):
        result = tools.handle_tool(USER, "update_goal_progress", {"goal_id": "ghost", "progress": 10})
        assert "not found" in result.lower()

    def test_delete_goal(self, tbls):
        tools.handle_tool(USER, "create_goal", {"title": "Delete me"})
        goal_id = self._get_goal_id()
        result = tools.handle_tool(USER, "delete_goal", {"goal_id": goal_id})
        assert "Deleted" in result

    def test_delete_goal_not_found(self, tbls):
        result = tools.handle_tool(USER, "delete_goal", {"goal_id": "ghost"})
        assert "not found" in result.lower()

    def test_completed_goal_excluded_from_active_list(self, tbls):
        tools.handle_tool(USER, "create_goal", {"title": "Old goal"})
        goal_id = self._get_goal_id()
        tools.handle_tool(USER, "update_goal_progress", {"goal_id": goal_id, "status": "completed"})
        result = tools.handle_tool(USER, "list_goals", {})
        assert "No active goals" in result


# ── tools: journal ────────────────────────────────────────────────────────────

class TestToolsJournal:
    def test_create_entry(self, tbls):
        result = tools.handle_tool(USER, "create_journal_entry", {
            "body": "Had a great day today",
            "mood": "great",
            "_today": "2026-01-01",
        })
        assert "journal entry" in result.lower()

    def test_upsert_entry(self, tbls):
        tools.handle_tool(USER, "create_journal_entry", {"body": "First write", "_today": "2026-01-01"})
        result = tools.handle_tool(USER, "create_journal_entry", {"body": "Updated write", "_today": "2026-01-01"})
        assert "Updated" in result

    def test_entry_includes_pal_link(self, tbls):
        result = tools.handle_tool(USER, "create_journal_entry", {
            "body": "Felt good",
        }, local_date="2026-01-15")
        assert "[pal-link:journal:2026-01-15:" in result


# ── tools: nutrition ──────────────────────────────────────────────────────────

class TestToolsNutrition:
    def test_log_meal(self, tbls):
        result = tools.handle_tool(USER, "log_meal", {
            "name": "Oatmeal",
            "calories": 300,
            "protein_g": 10,
            "_today": "2026-01-01",
        })
        assert "Oatmeal" in result
        assert "300 cal" in result

    def test_log_meal_accumulates(self, tbls):
        tools.handle_tool(USER, "log_meal", {"name": "Breakfast", "calories": 400, "_today": "2026-01-01"})
        result = tools.handle_tool(USER, "log_meal", {"name": "Lunch", "calories": 600, "_today": "2026-01-01"})
        assert "2 item(s)" in result

    def test_get_nutrition_log_empty(self, tbls):
        result = tools.handle_tool(USER, "get_nutrition_log", {"_today": "2026-01-01"})
        assert "No nutrition log" in result

    def test_get_nutrition_log_shows_meals(self, tbls):
        tools.handle_tool(USER, "log_meal", {"name": "Pizza", "calories": 800, "_today": "2026-01-01"})
        result = tools.handle_tool(USER, "get_nutrition_log", {"_today": "2026-01-01"})
        assert "Pizza" in result
        assert "800 cal" in result

    def test_get_nutrition_log_totals(self, tbls):
        tools.handle_tool(USER, "log_meal", {"name": "A", "calories": 300, "protein_g": 10, "_today": "2026-01-02"})
        tools.handle_tool(USER, "log_meal", {"name": "B", "calories": 500, "protein_g": 20, "_today": "2026-01-02"})
        result = tools.handle_tool(USER, "get_nutrition_log", {"_today": "2026-01-02"})
        assert "800 cal" in result


# ── tools: exercise ───────────────────────────────────────────────────────────

class TestToolsExercise:
    def test_log_exercise_cardio(self, tbls):
        result = tools.handle_tool(USER, "log_exercise", {
            "name": "Morning run",
            "duration_min": 30,
            "_today": "2026-01-01",
        })
        assert "Morning run" in result
        assert "30 min" in result

    def test_log_exercise_strength(self, tbls):
        result = tools.handle_tool(USER, "log_exercise", {
            "name": "Bench Press",
            "sets": [{"reps": 10, "weight": 135}, {"reps": 8, "weight": 145}],
            "_today": "2026-01-01",
        })
        assert "Bench Press" in result
        assert "2 set(s)" in result

    def test_log_exercise_accumulates(self, tbls):
        tools.handle_tool(USER, "log_exercise", {"name": "Run", "_today": "2026-01-01"})
        result = tools.handle_tool(USER, "log_exercise", {"name": "Squat", "_today": "2026-01-01"})
        assert "2 exercise(s)" in result

    def test_get_exercise_log_empty(self, tbls):
        result = tools.handle_tool(USER, "get_exercise_log", {"_today": "2026-01-01"})
        assert "No exercise log" in result

    def test_get_exercise_log_shows_exercises(self, tbls):
        tools.handle_tool(USER, "log_exercise", {"name": "Deadlift", "duration_min": 45, "_today": "2026-01-01"})
        result = tools.handle_tool(USER, "get_exercise_log", {"_today": "2026-01-01"})
        assert "Deadlift" in result
        assert "45 min" in result


# ── tools: nutrition lookup ───────────────────────────────────────────────────

class TestToolsLookupNutrition:
    def test_empty_food_name(self, tbls):
        result = tools.handle_tool(USER, "lookup_nutrition", {"food_name": ""})
        assert "No food name" in result

    def test_usda_failure_returns_graceful_fallback(self, tbls, monkeypatch):
        # Simulate USDA API being unreachable
        def _fail(*args, **kwargs):
            raise OSError("Network unreachable")
        monkeypatch.setattr(tools, "_usda_search", _fail)
        result = tools.handle_tool(USER, "lookup_nutrition", {"food_name": "banana"})
        assert "unavailable" in result.lower() or "general knowledge" in result.lower()

    def test_pick_usda_result_sanity_check(self, tbls):
        # Calorie density > 900 kcal/100g should be rejected (e.g. pure oil edge case)
        foods = [
            {"foodNutrients": [
                {"nutrientName": "Energy", "value": 950, "unitName": "KCAL"},
                {"nutrientName": "Protein", "value": 0, "unitName": "G"},
            ]},
            {"foodNutrients": [
                {"nutrientName": "Energy", "value": 500, "unitName": "KCAL"},
                {"nutrientName": "Protein", "value": 5, "unitName": "G"},
            ], "description": "Good food"},
        ]
        chosen, nutrients = tools._pick_usda_result(foods)
        assert chosen is not None
        assert nutrients["Energy"] == 500

    def test_pick_usda_result_kj_ignored(self, tbls):
        # kJ entries should NOT be selected as the calorie value
        foods = [{"foodNutrients": [
            {"nutrientName": "Energy", "value": 1800, "unitName": "kJ"},
            {"nutrientName": "Energy", "value": 430, "unitName": "KCAL"},
        ], "description": "Test food"}]
        chosen, nutrients = tools._pick_usda_result(foods)
        assert nutrients.get("Energy") == 430

    def test_pick_usda_result_empty_list(self, tbls):
        chosen, nutrients = tools._pick_usda_result([])
        assert chosen is None
        assert nutrients == {}

    def test_usda_no_results_returns_fallback(self, tbls, monkeypatch):
        monkeypatch.setattr(tools, "_usda_search", lambda *a, **k: [])
        result = tools.handle_tool(USER, "lookup_nutrition", {"food_name": "xyz123abc"})
        assert "No reliable" in result or "general knowledge" in result.lower()


# ── tools: remember_fact ─────────────────────────────────────────────────────

class TestToolsRememberFact:
    def test_remember_fact(self, tbls):
        result = tools.handle_tool(USER, "remember_fact", {"key": "timezone", "value": "America/New_York"})
        assert "timezone" in result

    def test_remembered_fact_persists(self, tbls):
        tools.handle_tool(USER, "remember_fact", {"key": "city", "value": "Toronto"})
        facts, _ = memory.load_memory(USER)
        assert facts["city"] == "Toronto"


# ── tools: unknown tool ───────────────────────────────────────────────────────

class TestToolsUnknown:
    def test_unknown_tool_returns_error(self, tbls):
        result = tools.handle_tool(USER, "nonexistent_tool", {})
        assert "Unknown tool" in result


# ── chat: chat_stream ─────────────────────────────────────────────────────────

def _make_stream_events(text_chunks, stop_reason="end_turn", input_tokens=10, output_tokens=5):
    """Build the list of converse_stream events for a simple text response."""
    events = [
        {"contentBlockStart": {"contentBlockIndex": 0, "start": {}}},
    ]
    for chunk in text_chunks:
        events.append({"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": chunk}}})
    events += [
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": stop_reason}},
        {"metadata": {"usage": {"inputTokens": input_tokens, "outputTokens": output_tokens}}},
    ]
    return events


def _make_tool_use_events(tool_use_id, tool_name, tool_input_dict):
    """Build converse_stream events for a single tool-use block."""
    input_str = json.dumps(tool_input_dict)
    return [
        {"contentBlockStart": {"contentBlockIndex": 0, "start": {"toolUse": {"toolUseId": tool_use_id, "name": tool_name}}}},
        {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": input_str}}}},
        {"contentBlockStop": {"contentBlockIndex": 0}},
        {"messageStop": {"stopReason": "tool_use"}},
        {"metadata": {"usage": {"inputTokens": 20, "outputTokens": 10}}},
    ]


class TestChatStream:
    def test_simple_text_response(self, tbls):
        """chat_stream emits token events and a done event for a plain text reply."""
        mock_resp = {"stream": iter(_make_stream_events(["Hello ", "world"]))}

        with patch.object(chat._bedrock, "converse_stream", return_value=mock_resp):
            chunks = []
            chat.chat_stream(USER, "hi", emit=lambda b: chunks.append(json.loads(b.rstrip(b"\n"))))

        tokens   = [c for c in chunks if c["type"] == "token"]
        done_evt = next(c for c in chunks if c["type"] == "done")

        assert "".join(t["text"] for t in tokens) == "Hello world"
        assert done_evt["reply"] == "Hello world"
        assert done_evt["tools_used"] == []

    def test_reply_saved_to_history(self, tbls):
        """chat_stream persists the exchange to conversation history."""
        mock_resp = {"stream": iter(_make_stream_events(["Done"]))}

        with patch.object(chat._bedrock, "converse_stream", return_value=mock_resp):
            chat.chat_stream(USER, "save this", emit=lambda b: None)

        history = memory.load_history(USER)
        assert any(m["role"] == "user"      and "save this" in m["content"][0]["text"] for m in history)
        assert any(m["role"] == "assistant" and "Done"       in m["content"][0]["text"] for m in history)

    def test_tool_use_then_text(self, tbls):
        """chat_stream handles a tool-use loop followed by a final text response."""
        tool_events  = _make_tool_use_events("tu-1", "list_tasks", {})
        final_events = _make_stream_events(["Here are your tasks"])

        call_count = [0]
        def fake_converse_stream(**kwargs):
            call_count[0] += 1
            return {"stream": iter(tool_events if call_count[0] == 1 else final_events)}

        with patch.object(chat._bedrock, "converse_stream", side_effect=fake_converse_stream):
            chunks = []
            chat.chat_stream(USER, "list tasks", emit=lambda b: chunks.append(json.loads(b.rstrip(b"\n"))))

        statuses = [c for c in chunks if c["type"] == "status"]
        done_evt = next(c for c in chunks if c["type"] == "done")

        assert any(s["text"] == "list_tasks" for s in statuses)
        assert "list_tasks" in done_evt["tools_used"]
        assert "Here are your tasks" in done_evt["reply"]

    def test_thinking_tags_stripped_from_reply(self, tbls):
        """_clean_reply removes <thinking> blocks from the done event reply."""
        raw = "<thinking>internal</thinking><response>Clean answer</response>"
        mock_resp = {"stream": iter(_make_stream_events([raw]))}

        with patch.object(chat._bedrock, "converse_stream", return_value=mock_resp):
            chunks = []
            chat.chat_stream(USER, "q", emit=lambda b: chunks.append(json.loads(b.rstrip(b"\n"))))

        done_evt = next(c for c in chunks if c["type"] == "done")
        assert done_evt["reply"] == "Clean answer"

    def test_usage_recorded(self, tbls):
        """Token usage from the stream metadata is persisted to memory."""
        mock_resp = {"stream": iter(_make_stream_events(["ok"], input_tokens=7, output_tokens=3))}

        with patch.object(chat._bedrock, "converse_stream", return_value=mock_resp):
            chat.chat_stream(USER, "usage test", emit=lambda b: None)

        usage = memory.load_model_usage(USER)
        model_entry = next((u for u in usage if u["model_id"] == chat.MODEL_ID), None)
        assert model_entry is not None
        assert model_entry["input_tokens"] == 7
        assert model_entry["output_tokens"] == 3

    def test_error_event_on_bedrock_failure(self, tbls):
        """chat_stream emits an error event when Bedrock raises."""
        with patch.object(chat._bedrock, "converse_stream", side_effect=RuntimeError("boom")):
            chunks = []
            chat.chat_stream(USER, "fail", emit=lambda b: chunks.append(json.loads(b.rstrip(b"\n"))))

        assert any(c["type"] == "error" for c in chunks)


# ── token_auth ────────────────────────────────────────────────────────────────

class TestTokenAuthExtract:
    def test_bearer_header(self):
        event = {"headers": {"authorization": "Bearer mytoken"}}
        assert token_auth.extract_token(event) == "mytoken"

    def test_authorization_no_bearer_prefix(self):
        event = {"headers": {"Authorization": "rawtoken"}}
        assert token_auth.extract_token(event) == "rawtoken"

    def test_cookie_fallback(self):
        event = {"headers": {"cookie": "other=x; memoire_token=cookietok; z=1"}}
        assert token_auth.extract_token(event) == "cookietok"

    def test_header_takes_priority_over_cookie(self):
        event = {"headers": {"authorization": "Bearer hdrtoken", "cookie": "memoire_token=cookietok"}}
        assert token_auth.extract_token(event) == "hdrtoken"

    def test_empty_event_returns_empty(self):
        assert token_auth.extract_token({}) == ""

    def test_no_matching_cookie_returns_empty(self):
        event = {"headers": {"cookie": "other=value"}}
        assert token_auth.extract_token(event) == ""


class TestTokenAuthGetUserId:
    def test_no_token_returns_none(self, tbls):
        assert token_auth.get_user_id({}) is None

    def test_malformed_jwt_returns_none(self, tbls):
        # Not three dot-separated parts → rejected immediately
        event = {"headers": {"authorization": "notajwt"}}
        assert token_auth.get_user_id(event) is None

    def test_pat_not_in_db_returns_none(self, tbls):
        event = {"headers": {"authorization": "pat_unknowntoken"}}
        assert token_auth.get_user_id(event) is None

    def test_expired_jwt_returns_none(self, tbls):
        # Craft a JWT with a valid structure but expired exp claim.
        # The signature will be wrong, but exp is checked first.
        import base64
        header  = base64.urlsafe_b64encode(b'{"alg":"RS256","kid":"k1"}').rstrip(b"=").decode()
        payload = base64.urlsafe_b64encode(b'{"sub":"u1","exp":1,"iss":"https://cognito.example.com","aud":"test-client-id"}').rstrip(b"=").decode()
        token   = f"{header}.{payload}.fakesig"
        event   = {"headers": {"authorization": f"Bearer {token}"}}
        assert token_auth.get_user_id(event) is None

    def test_wrong_issuer_returns_none(self, tbls):
        import base64
        import time
        header  = base64.urlsafe_b64encode(b'{"alg":"RS256","kid":"k1"}').rstrip(b"=").decode()
        payload_bytes = json.dumps({"sub": "u1", "exp": int(time.time()) + 3600, "iss": "https://wrong.example.com", "aud": "test-client-id"}).encode()
        payload = base64.urlsafe_b64encode(payload_bytes).rstrip(b"=").decode()
        token   = f"{header}.{payload}.fakesig"
        event   = {"headers": {"authorization": f"Bearer {token}"}}
        assert token_auth.get_user_id(event) is None


# ── streaming handler ───���─────────────────────────────────────────────────────

class TestStreamHandler:
    """Tests for _stream_handler called directly (no awslambdaric wrapper needed)."""

    def _collect(self, stream_mock):
        chunks = []
        for call in stream_mock.write.call_args_list:
            line = call.args[0].rstrip(b"\n")
            if line:
                chunks.append(json.loads(line))
        return chunks

    def test_unauthorized_when_no_token(self, tbls):
        from unittest.mock import MagicMock
        stream = MagicMock()
        handler._stream_handler({"headers": {}}, None, stream)
        chunks = self._collect(stream)
        assert chunks[0] == {"type": "error", "message": "Unauthorized"}

    def test_invalid_json_body_returns_error(self, tbls, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(token_auth, "get_user_id", lambda e: USER)
        stream = MagicMock()
        handler._stream_handler({"headers": {}, "body": "not-json"}, None, stream)
        chunks = self._collect(stream)
        assert chunks[0]["type"] == "error"
        assert "JSON" in chunks[0]["message"]

    def test_missing_message_returns_error(self, tbls, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(token_auth, "get_user_id", lambda e: USER)
        stream = MagicMock()
        handler._stream_handler({"headers": {}, "body": "{}"}, None, stream)
        chunks = self._collect(stream)
        assert chunks[0]["type"] == "error"
        assert "message" in chunks[0]["message"].lower()

    def test_delegates_to_chat_stream(self, tbls, monkeypatch):
        from unittest.mock import MagicMock
        monkeypatch.setattr(token_auth, "get_user_id", lambda e: USER)
        called_with = {}

        def fake_chat_stream(user_id, message, emit, model=None, local_date=None):
            called_with["user_id"] = user_id
            called_with["message"] = message
            emit(json.dumps({"type": "done", "tools_used": [], "reply": "hi"}).encode() + b"\n")

        monkeypatch.setattr(chat, "chat_stream", fake_chat_stream)
        stream = MagicMock()
        body   = json.dumps({"message": "hello world"})
        handler._stream_handler({"headers": {}, "body": body}, None, stream)

        assert called_with["user_id"] == USER
        assert called_with["message"] == "hello world"

    def test_exception_in_chat_stream_emits_error(self, tbls, monkeypatch):
        """Unhandled exception inside chat_stream writes an error event."""
        from unittest.mock import MagicMock
        monkeypatch.setattr(token_auth, "get_user_id", lambda e: USER)
        monkeypatch.setattr(chat, "chat_stream", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("kaboom")))
        stream = MagicMock()
        handler._stream_handler({"headers": {}, "body": json.dumps({"message": "hi"})}, None, stream)
        chunks = self._collect(stream)
        assert any(c["type"] == "error" for c in chunks)


# ── handler.lambda_handler ────────────────────────────────────────────────────

class TestLambdaHandler:
    def _event(self, route_key="POST /assistant/chat", body=None):
        return {
            "requestContext": {"authorizer": {"lambda": {"user_id": USER}}},
            "routeKey": route_key,
            "headers": {},
            "body": json.dumps(body) if body is not None else None,
        }

    def test_routes_chat_request(self, tbls, monkeypatch):
        monkeypatch.setattr(handler, "route", lambda rk, uid, b: {"statusCode": 200, "body": json.dumps({"reply": "ok", "tools_used": []})})
        result = handler.lambda_handler(self._event(body={"message": "hi"}), None)
        assert result["statusCode"] == 200

    def test_invalid_json_body_returns_400(self, tbls):
        event = self._event()
        event["body"] = "not-json"
        result = handler.lambda_handler(event, None)
        assert result["statusCode"] == 400

    def test_exception_returns_500(self, tbls, monkeypatch):
        monkeypatch.setattr(handler, "route", lambda *a: (_ for _ in ()).throw(RuntimeError("oops")))
        result = handler.lambda_handler(self._event(body={"message": "hi"}), None)
        assert result["statusCode"] == 500


# ── token_auth: JWKS fetch and RSA paths ─────────────────────────────────────

class TestTokenAuthJWKSAndRSA:
    def _make_jwt(self, kid="test-kid", extra_payload=None):
        import base64
        import time
        header  = base64.urlsafe_b64encode(json.dumps({"alg": "RS256", "kid": kid}).encode()).rstrip(b"=").decode()
        payload = {"sub": "u-test", "exp": int(time.time()) + 3600, "iss": "https://cognito.example.com", "aud": "test-client-id"}
        if extra_payload:
            payload.update(extra_payload)
        payload_b64 = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        # 256 zero bytes = valid base64url signature of the right length for 2048-bit RSA
        sig = base64.urlsafe_b64encode(b"\x00" * 256).rstrip(b"=").decode()
        return f"{header}.{payload_b64}.{sig}"

    def _urlopen_mock(self, jwks: dict):
        from unittest.mock import MagicMock
        mock_resp = MagicMock()
        mock_resp.read.return_value = json.dumps(jwks).encode()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        return mock_resp

    def _fake_jwks(self, kid="test-kid"):
        import base64
        # 2048-bit fake modulus (not a real key — signature check will fail, but all code runs)
        n_bytes = (2 ** 2047).to_bytes(256, "big")
        e_bytes = (65537).to_bytes(3, "big")
        return {"keys": [{"kid": kid, "n": base64.urlsafe_b64encode(n_bytes).rstrip(b"=").decode(),
                                       "e": base64.urlsafe_b64encode(e_bytes).rstrip(b"=").decode()}]}

    def test_jwks_fetched_on_cache_miss(self, tbls):
        token_auth._jwks_cache    = None  # force cache miss
        token_auth._jwks_cache_at = 0.0
        jwks = self._fake_jwks()
        with patch("urllib.request.urlopen", return_value=self._urlopen_mock(jwks)):
            result = token_auth._verify_jwt(self._make_jwt())
        # Signature verification fails (fake key), so result is None — but JWKS was fetched
        assert result is None
        assert token_auth._jwks_cache == jwks

    def test_jwks_cache_hit_skips_fetch(self, tbls):
        token_auth._jwks_cache    = self._fake_jwks()
        token_auth._jwks_cache_at = 9_999_999_999.0  # far future
        with patch("urllib.request.urlopen", side_effect=AssertionError("should not fetch")):
            token_auth._verify_jwt(self._make_jwt())  # uses cache, no network call

    def test_no_matching_kid_returns_none(self, tbls):
        token_auth._jwks_cache    = None
        token_auth._jwks_cache_at = 0.0
        jwks = self._fake_jwks(kid="other-kid")
        with patch("urllib.request.urlopen", return_value=self._urlopen_mock(jwks)):
            result = token_auth._verify_jwt(self._make_jwt(kid="test-kid"))
        assert result is None

    def test_rsa_wrong_signature_length_returns_false(self):
        # Signature length != modulus length → immediate False (lines 55-57)
        result = token_auth._verify_rsa_pkcs1v15_sha256(b"msg", b"\x00" * 10, n=2**2047, e=65537)
        assert result is False

    def test_rsa_correct_length_bad_sig_returns_false(self):
        # Correct length but wrong signature value → runs full verification (lines 55-69)
        sig = b"\x00" * 256  # 256 bytes = 2048-bit modulus, but sig = 0
        result = token_auth._verify_rsa_pkcs1v15_sha256(b"msg", sig, n=2**2047, e=65537)
        assert result is False

    def test_get_user_id_exception_returns_none(self, tbls, monkeypatch):
        # _verify_jwt raises → exception handler in get_user_id returns None (lines 158-160)
        monkeypatch.setattr(token_auth, "_verify_jwt", lambda t: (_ for _ in ()).throw(RuntimeError("boom")))
        event = {"headers": {"authorization": "Bearer valid.looking.jwt"}}
        assert token_auth.get_user_id(event) is None


# ── token_auth: PAT success path ──────────────────────────────────────────────

class TestTokenAuthPATSuccess:
    def test_valid_pat_returns_user_id(self, tbls):
        import hashlib
        pat   = "pat_testtoken123"
        h     = hashlib.sha256(pat.encode()).hexdigest()
        # Insert the PAT hash into the tokens table
        import boto3
        ddb   = boto3.resource("dynamodb", region_name="us-east-1")
        table = ddb.Table("test-tokens")
        table.put_item(Item={"user_id": USER, "token_id": "tok-1", "token_hash": h})

        result = token_auth._verify_pat(pat)
        assert result == USER


# ── chat_stream: edge-case coverage ──────────────────────────────────────────

class TestChatStreamEdgeCases:
    def test_text_delta_without_prior_block_start(self, tbls):
        """A contentBlockDelta with text but no prior contentBlockStart is handled (line 221)."""
        events = [
            # No contentBlockStart — delta arrives cold
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"text": "Hello"}}},
            {"contentBlockStop":  {"contentBlockIndex": 0}},
            {"messageStop":       {"stopReason": "end_turn"}},
            {"metadata":          {"usage": {"inputTokens": 1, "outputTokens": 1}}},
        ]
        mock_resp = {"stream": iter(events)}
        with patch.object(chat._bedrock, "converse_stream", return_value=mock_resp):
            chunks = []
            chat.chat_stream(USER, "hi", emit=lambda b: chunks.append(json.loads(b.rstrip(b"\n"))))
        tokens = [c for c in chunks if c["type"] == "token"]
        assert any("Hello" in t["text"] for t in tokens)

    def test_invalid_tool_json_does_not_crash(self, tbls):
        """Invalid JSON in a tool input block is handled gracefully (lines 235-236)."""
        tool_events = [
            {"contentBlockStart": {"contentBlockIndex": 0, "start": {"toolUse": {"toolUseId": "tu-bad", "name": "list_tasks"}}}},
            {"contentBlockDelta": {"contentBlockIndex": 0, "delta": {"toolUse": {"input": "{{invalid json"}}}},
            {"contentBlockStop":  {"contentBlockIndex": 0}},
            {"messageStop":       {"stopReason": "tool_use"}},
            {"metadata":          {"usage": {"inputTokens": 5, "outputTokens": 2}}},
        ]
        final_events = _make_stream_events(["Done"])
        call_count = [0]
        def fake_stream(**kwargs):
            call_count[0] += 1
            return {"stream": iter(tool_events if call_count[0] == 1 else final_events)}

        with patch.object(chat._bedrock, "converse_stream", side_effect=fake_stream):
            chunks = []
            chat.chat_stream(USER, "list tasks", emit=lambda b: chunks.append(json.loads(b.rstrip(b"\n"))))
        assert any(c["type"] == "done" for c in chunks)
