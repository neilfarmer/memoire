"""Unit tests for lambda/assistant/supervisor.py."""

import json
import os
from unittest.mock import patch

from conftest import load_lambda

os.environ.setdefault("AWS_REGION", "us-east-1")

sup = load_lambda("assistant", "supervisor.py")


class TestNeedsSupervision:
    def test_write_tool_triggers(self):
        assert sup.needs_supervision("Done.", ["log_meal"])

    def test_read_tool_does_not_trigger(self):
        assert not sup.needs_supervision("Here's your list.", ["list_tasks"])

    def test_completion_language_triggers(self):
        assert sup.needs_supervision("I've added those items to your nutrition log.", [])

    def test_logged_language_triggers(self):
        assert sup.needs_supervision("I logged them for you.", [])

    def test_plain_question_does_not_trigger(self):
        assert not sup.needs_supervision("What would you like to do next?", [])


class TestBuildCorrectionPrompt:
    def test_includes_missing_items(self):
        msg = sup.build_correction_prompt({
            "verdict": "incomplete",
            "reason": "two items missing",
            "missing": ["brats", "fries"],
        })
        assert "brats" in msg
        assert "fries" in msg
        assert "incomplete" in msg

    def test_handles_empty_missing(self):
        msg = sup.build_correction_prompt({
            "verdict": "hallucinated",
            "reason": "nothing was logged",
            "missing": [],
        })
        assert "hallucinated" in msg


class TestSupervise:
    def test_parses_ok_verdict(self):
        fake = {"output": {"message": {"content": [{"text": json.dumps({
            "verdict": "ok", "reason": "all logged", "missing": []
        })}]}}}
        with patch.object(sup, "_bedrock") as mock_client:
            mock_client.converse.return_value = fake
            v = sup.supervise("add cashews", "logged cashews", [{"name": "log_meal", "inputs": {}, "result": ""}], "2026-04-22")
        assert v["verdict"] == "ok"

    def test_parses_hallucinated_verdict(self):
        fake = {"output": {"message": {"content": [{"text": json.dumps({
            "verdict": "hallucinated", "reason": "no tools ran", "missing": ["cashews"]
        })}]}}}
        with patch.object(sup, "_bedrock") as mock_client:
            mock_client.converse.return_value = fake
            v = sup.supervise("add cashews", "I added cashews", [], "2026-04-22")
        assert v["verdict"] == "hallucinated"
        assert "cashews" in v["missing"]

    def test_degrades_on_bedrock_error(self):
        with patch.object(sup, "_bedrock") as mock_client:
            mock_client.converse.side_effect = RuntimeError("boom")
            v = sup.supervise("add cashews", "done", [], "2026-04-22")
        assert v["verdict"] == "ok"
        assert v["reason"] == "supervisor_error"

    def test_handles_non_json_output(self):
        fake = {"output": {"message": {"content": [{"text": "sorry I have no idea"}]}}}
        with patch.object(sup, "_bedrock") as mock_client:
            mock_client.converse.return_value = fake
            v = sup.supervise("x", "y", [], "2026-04-22")
        assert v["verdict"] == "ok"

    def test_invalid_verdict_coerced_to_ok(self):
        fake = {"output": {"message": {"content": [{"text": json.dumps({
            "verdict": "garbage", "reason": "?", "missing": []
        })}]}}}
        with patch.object(sup, "_bedrock") as mock_client:
            mock_client.converse.return_value = fake
            v = sup.supervise("x", "y", [], "2026-04-22")
        assert v["verdict"] == "ok"
