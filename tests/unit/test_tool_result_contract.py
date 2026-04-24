"""Unit tests for tools.verify_tool_result and its integration with chat._invoke_tool."""

import os
from unittest.mock import patch

from conftest import USER, load_lambda

# ── env vars before module load ───────────────────────────────────────────────
os.environ.setdefault("CONVERSATIONS_TABLE", "test-conversations")
os.environ.setdefault("MEMORY_TABLE",        "test-memory")
os.environ.setdefault("TASKS_TABLE",         "test-tasks-asst")
os.environ.setdefault("NOTES_TABLE",         "test-notes-asst")
os.environ.setdefault("NOTE_FOLDERS_TABLE",  "test-note-folders-asst")
os.environ.setdefault("HABITS_TABLE",        "test-habits-asst")
os.environ.setdefault("GOALS_TABLE",         "test-goals-asst")
os.environ.setdefault("JOURNAL_TABLE",       "test-journal-asst")
os.environ.setdefault("NUTRITION_TABLE",     "test-nutrition-asst")
os.environ.setdefault("HEALTH_TABLE",        "test-health-asst")
os.environ.setdefault("AWS_REGION",          "us-east-1")

tools = load_lambda("assistant", "tools.py")
chat  = load_lambda("assistant", "chat.py")


class TestVerifyToolResult:
    def test_read_only_tool_has_no_contract(self):
        assert tools.verify_tool_result("list_tasks", "no tag here") is None

    def test_unknown_tool_has_no_contract(self):
        assert tools.verify_tool_result("not_a_tool", "anything") is None

    def test_create_task_with_pal_link_passes(self):
        result = "Created task: Walk dog [pal-link:task:abc-123:Open task →]"
        assert tools.verify_tool_result("create_task", result) is None

    def test_create_task_without_pal_link_fails(self):
        err = tools.verify_tool_result("create_task", "Created task: Walk dog")
        assert err is not None
        assert "create_task" in err
        assert "did not return an id tag" in err

    def test_create_note_requires_note_pal_link(self):
        # task pal-link is not a note pal-link
        wrong = "Created note [pal-link:task:abc:Open task →]"
        err = tools.verify_tool_result("create_note", wrong)
        assert err is not None

    def test_create_journal_entry_accepts_journal_tag(self):
        ok = "Created journal entry for 2026-04-24 [pal-link:journal:2026-04-24:Open entry →]"
        assert tools.verify_tool_result("create_journal_entry", ok) is None

    def test_create_bookmark_requires_id_tag(self):
        assert tools.verify_tool_result("create_bookmark", "Saved [id:b-1]") is None
        err = tools.verify_tool_result("create_bookmark", "Saved bookmark")
        assert err is not None

    def test_add_favorite_requires_id_tag(self):
        assert tools.verify_tool_result("add_favorite", "Favorited task [id:f-1]") is None
        assert tools.verify_tool_result("add_favorite", "Favorited task") is not None

    def test_empty_result_flagged(self):
        assert tools.verify_tool_result("create_task", "") is not None

    def test_none_result_flagged(self):
        assert tools.verify_tool_result("create_task", None) is not None


class TestInvokeToolIntegration:
    def test_contract_violation_marks_tool_failed(self):
        tool_log = []
        # Patch handle_tool to return a string that does NOT match create_task's contract.
        with patch.object(chat, "handle_tool", return_value="Created task: Walk dog"):
            result = chat._invoke_tool(
                USER, "create_task", {"title": "Walk dog"},
                local_date="2026-04-24",
                model_id=chat.MODEL_ID,
                tool_log=tool_log,
            )
        assert "Tool error" in result
        assert len(tool_log) == 1
        assert tool_log[0]["success"] is False
        assert tool_log[0]["name"] == "create_task"

    def test_contract_satisfied_marks_tool_success(self):
        tool_log = []
        ok = "Created task: Walk dog [pal-link:task:abc-123:Open task →]"
        with patch.object(chat, "handle_tool", return_value=ok):
            result = chat._invoke_tool(
                USER, "create_task", {"title": "Walk dog"},
                local_date="2026-04-24",
                model_id=chat.MODEL_ID,
                tool_log=tool_log,
            )
        assert result == ok
        assert tool_log[0]["success"] is True

    def test_read_tool_bypasses_contract(self):
        tool_log = []
        with patch.object(chat, "handle_tool", return_value="- Task A [id:t-1]"):
            result = chat._invoke_tool(
                USER, "list_tasks", {},
                local_date="2026-04-24",
                model_id=chat.MODEL_ID,
                tool_log=tool_log,
            )
        assert "Tool error" not in result
        assert tool_log[0]["success"] is True

    def test_handler_exception_marks_failed(self):
        tool_log = []
        with patch.object(chat, "handle_tool", side_effect=RuntimeError("db down")):
            result = chat._invoke_tool(
                USER, "create_task", {"title": "x"},
                local_date="2026-04-24",
                model_id=chat.MODEL_ID,
                tool_log=tool_log,
            )
        assert "Tool error" in result
        assert tool_log[0]["success"] is False
