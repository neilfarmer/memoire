"""Unit tests for lambda/assistant/chat.py — _clean_reply, _system_prompt, _extract_facts."""

import json
import os
from unittest.mock import patch

import boto3
import pytest
from moto import mock_aws

from conftest import load_lambda, USER, make_table

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


# ── _extract_facts ─────────────────────────────────────────────────────────────

memory = load_lambda("assistant", "memory.py")

@pytest.fixture
def mem_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, "test-memory", "user_id", "memory_key")
        yield


def _mock_bedrock_text(text: str):
    """Return a mock converse response with the given text."""
    return {
        "output": {"message": {"content": [{"text": text}]}},
        "usage": {"inputTokens": 10, "outputTokens": 10},
    }


class TestExtractFacts:
    def test_extracts_new_fact(self, mem_table):
        with patch.object(chat._bedrock, "converse", return_value=_mock_bedrock_text("interests: building gaming PCs")):
            chat._extract_facts(USER, {}, "I love building gaming PCs", "Got it!", chat.MODEL_ID)
        facts, _ = memory.load_memory(USER)
        assert facts.get("interests") == "building gaming PCs"

    def test_extracts_multiple_facts(self, mem_table):
        output = "interests: hiking\nfavorite_food: tacos"
        with patch.object(chat._bedrock, "converse", return_value=_mock_bedrock_text(output)):
            chat._extract_facts(USER, {}, "I hike and love tacos", "Great!", chat.MODEL_ID)
        facts, _ = memory.load_memory(USER)
        assert facts.get("interests") == "hiking"
        assert facts.get("favorite_food") == "tacos"

    def test_none_response_saves_nothing(self, mem_table):
        with patch.object(chat._bedrock, "converse", return_value=_mock_bedrock_text("NONE")):
            chat._extract_facts(USER, {}, "create a task for me", "Done!", chat.MODEL_ID)
        facts, _ = memory.load_memory(USER)
        assert facts == {}

    def test_skips_internal_keys(self, mem_table):
        output = "__secret__: bad\noccupation: engineer"
        with patch.object(chat._bedrock, "converse", return_value=_mock_bedrock_text(output)):
            chat._extract_facts(USER, {}, "hi", "hi", chat.MODEL_ID)
        facts, _ = memory.load_memory(USER)
        assert "__secret__" not in facts
        assert facts.get("occupation") == "engineer"

    def test_overwrites_existing_fact(self, mem_table):
        memory.save_memory(USER, "interests", "gaming")
        output = "interests: gaming, building PCs"
        with patch.object(chat._bedrock, "converse", return_value=_mock_bedrock_text(output)):
            chat._extract_facts(USER, {"interests": "gaming"}, "I also build PCs", "Cool!", chat.MODEL_ID)
        facts, _ = memory.load_memory(USER)
        assert facts.get("interests") == "gaming, building PCs"

    def test_bedrock_failure_does_not_raise(self, mem_table):
        with patch.object(chat._bedrock, "converse", side_effect=Exception("timeout")):
            chat._extract_facts(USER, {}, "hi", "hi", chat.MODEL_ID)  # should not raise

    def test_malformed_lines_skipped(self, mem_table):
        output = "no colon here\noccupation: developer"
        with patch.object(chat._bedrock, "converse", return_value=_mock_bedrock_text(output)):
            chat._extract_facts(USER, {}, "hi", "hi", chat.MODEL_ID)
        facts, _ = memory.load_memory(USER)
        assert facts.get("occupation") == "developer"
