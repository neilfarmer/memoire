"""Unit tests for lambda/assistant/events.py."""

import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda

os.environ["EVENTS_TABLE"] = "test-assistant-events"

evt = load_lambda("assistant", "events.py")


@pytest.fixture
def tbl():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="test-assistant-events",
            KeySchema=[
                {"AttributeName": "user_id",  "KeyType": "HASH"},
                {"AttributeName": "event_id", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "user_id",  "AttributeType": "S"},
                {"AttributeName": "event_id", "AttributeType": "S"},
                {"AttributeName": "shard",    "AttributeType": "S"},
                {"AttributeName": "ts",       "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[{
                "IndexName": "scope-ts-index",
                "KeySchema": [
                    {"AttributeName": "shard", "KeyType": "HASH"},
                    {"AttributeName": "ts",    "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "ALL"},
            }],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


class TestRecord:
    def test_tool_call_persists(self, tbl):
        evt.record_tool_call(USER, "log_meal", {"name": "x"}, "Logged", True, 42, "nova-pro")
        items = boto3.resource("dynamodb", region_name="us-east-1").Table("test-assistant-events").scan()["Items"]
        assert len(items) == 1
        assert items[0]["tool_name"] == "log_meal"
        assert items[0]["success"] is True
        assert items[0]["event_type"] == "tool_call"

    def test_supervisor_verdict_persists(self, tbl):
        evt.record_supervisor(USER, "incomplete", "missing brats", 0, ["log_meal"], "nova-pro")
        items = boto3.resource("dynamodb", region_name="us-east-1").Table("test-assistant-events").scan()["Items"]
        assert items[0]["verdict"] == "incomplete"

    def test_chat_complete_persists(self, tbl):
        evt.record_chat_complete(USER, ["log_meal"], 200, 50, 1200, "nova-pro")
        items = boto3.resource("dynamodb", region_name="us-east-1").Table("test-assistant-events").scan()["Items"]
        assert items[0]["tokens_in"] == 200

    def test_large_payload_trimmed(self, tbl):
        big = "x" * 5000
        evt.record_tool_call(USER, "log_meal", {"name": big}, big, True, 10, "nova-pro")
        items = boto3.resource("dynamodb", region_name="us-east-1").Table("test-assistant-events").scan()["Items"]
        assert len(items[0]["result"]) < 5000

    def test_silent_when_table_env_missing(self, monkeypatch):
        monkeypatch.setattr(evt, "EVENTS_TABLE", "")
        # Should not raise even without real table
        evt.record_tool_call(USER, "log_meal", {}, "ok", True, 1, "m")

    def test_silent_on_put_failure(self, monkeypatch):
        # EVENTS_TABLE is set but table does not exist — record() should swallow errors
        monkeypatch.setattr(evt, "EVENTS_TABLE", "does-not-exist")
        evt.record_tool_call(USER, "log_meal", {}, "ok", True, 1, "m")
