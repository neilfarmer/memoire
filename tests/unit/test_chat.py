"""Unit tests for lambda/assistant/chat.py — _clean_reply and _system_prompt."""

import os
import sys

import pytest

from conftest import load_lambda

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

chat = load_lambda("assistant", "chat.py")


# ── _clean_reply ──────────────────────────────────────────────────────────────

class TestCleanReply:
    def test_plain_text_unchanged(self):
        assert chat._clean_reply("Hello!") == "Hello!"

    def test_strips_thinking_block(self):
        text = "<thinking>internal reasoning</thinking>The actual reply."
        assert chat._clean_reply(text) == "The actual reply."

    def test_strips_multiline_thinking_block(self):
        text = "<thinking>\nLine one\nLine two\n</thinking>Done."
        assert chat._clean_reply(text) == "Done."

    def test_strips_multiple_thinking_blocks(self):
        text = "<thinking>first</thinking>Middle<thinking>second</thinking>End"
        result = chat._clean_reply(text)
        assert "first" not in result
        assert "second" not in result
        assert "Middle" in result
        assert "End" in result

    def test_unwraps_response_tag(self):
        text = "<response>This is the reply.</response>"
        assert chat._clean_reply(text) == "This is the reply."

    def test_unwraps_response_tag_with_surrounding_whitespace(self):
        text = "  <response>  content  </response>  "
        assert chat._clean_reply(text) == "content"

    def test_thinking_then_response(self):
        text = "<thinking>reasoning</thinking><response>Final answer.</response>"
        assert chat._clean_reply(text) == "Final answer."

    def test_empty_string(self):
        assert chat._clean_reply("") == ""

    def test_whitespace_only(self):
        assert chat._clean_reply("   \n  ") == ""

    def test_thinking_only_leaves_empty(self):
        # If model only outputs a thinking block with no text, result is empty
        text = "<thinking>Just thinking, no reply.</thinking>"
        assert chat._clean_reply(text) == ""

    def test_no_xml_tags(self):
        text = "Here is a list:\n- item 1\n- item 2"
        assert chat._clean_reply(text) == text


# ── _system_prompt ────────────────────────────────────────────────────────────

class TestSystemPrompt:
    def test_returns_list_with_text_key(self):
        result = chat._system_prompt({}, "", local_date="2026-01-15")
        assert isinstance(result, list)
        assert len(result) == 1
        assert "text" in result[0]

    def test_injects_date(self):
        result = chat._system_prompt({}, "", local_date="2026-06-15")
        text = result[0]["text"]
        assert "June" in text or "2026" in text

    def test_injects_facts(self):
        facts = {"wake_time": "7am", "city": "Toronto"}
        result = chat._system_prompt(facts, "", local_date="2026-01-01")
        text = result[0]["text"]
        assert "wake_time" in text
        assert "7am" in text
        assert "Toronto" in text

    def test_empty_facts_shows_placeholder(self):
        result = chat._system_prompt({}, "", local_date="2026-01-01")
        text = result[0]["text"]
        assert "Nothing remembered yet" in text

    def test_master_context_appended(self):
        result = chat._system_prompt({}, "Neil is a software engineer.", local_date="2026-01-01")
        text = result[0]["text"]
        assert "Neil is a software engineer." in text

    def test_empty_master_context_not_appended(self):
        result = chat._system_prompt({}, "", local_date="2026-01-01")
        text = result[0]["text"]
        # "big picture" section should only appear when master context is non-empty
        assert "big picture" not in text

    def test_invalid_date_falls_back_gracefully(self):
        # Should not raise — falls back to date.today()
        result = chat._system_prompt({}, "", local_date="not-a-date")
        assert isinstance(result, list)
        assert "text" in result[0]

    def test_no_local_date_uses_today(self):
        result = chat._system_prompt({}, "", local_date=None)
        assert isinstance(result, list)
        assert "text" in result[0]
