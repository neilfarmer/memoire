"""Unit tests for lambda/layer/python/db.py."""

import os
import pytest
import boto3
from moto import mock_aws

from conftest import REPO_ROOT, LAYER_DIR, USER, load_lambda, make_table

# Set env vars before module load
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

db = load_lambda.__func__ if hasattr(load_lambda, "__func__") else None


# We import db directly since it's a layer module, not a feature module
import sys
sys.path.insert(0, str(LAYER_DIR))
import db as db_mod


TABLE = "test-db-layer"


@pytest.fixture
def ddb_table():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        tbl = make_table(ddb, TABLE, "user_id", "item_id")
        yield tbl


class TestGetTable:
    def test_returns_table_object(self, ddb_table):
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            make_table(ddb, "get-table-test", "user_id", "item_id")
            tbl = db_mod.get_table("get-table-test")
            assert tbl is not None
            assert tbl.table_name == "get-table-test"


class TestQueryByUser:
    def test_returns_empty_for_unknown_user(self, ddb_table):
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            tbl = make_table(ddb, "qbu-empty", "user_id", "item_id")
            result = db_mod.query_by_user(tbl, "no-such-user")
            assert result == []

    def test_returns_items_for_user(self, ddb_table):
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            tbl = make_table(ddb, "qbu-items", "user_id", "item_id")
            tbl.put_item(Item={"user_id": USER, "item_id": "a", "val": "1"})
            tbl.put_item(Item={"user_id": USER, "item_id": "b", "val": "2"})
            tbl.put_item(Item={"user_id": "other", "item_id": "c", "val": "3"})
            result = db_mod.query_by_user(tbl, USER)
            assert len(result) == 2
            ids = {r["item_id"] for r in result}
            assert ids == {"a", "b"}

    def test_paginates_across_multiple_pages(self):
        """query_by_user must follow LastEvaluatedKey until exhausted."""
        from unittest.mock import MagicMock, patch

        page1 = {"Items": [{"user_id": USER, "item_id": "a"}], "LastEvaluatedKey": {"user_id": USER, "item_id": "a"}}
        page2 = {"Items": [{"user_id": USER, "item_id": "b"}]}

        mock_table = MagicMock()
        mock_table.query.side_effect = [page1, page2]

        result = db_mod.query_by_user(mock_table, USER)
        assert len(result) == 2
        assert mock_table.query.call_count == 2
        # Second call must include ExclusiveStartKey
        second_call_kwargs = mock_table.query.call_args_list[1][1]
        assert second_call_kwargs["ExclusiveStartKey"] == {"user_id": USER, "item_id": "a"}

    def test_does_not_return_other_users_data(self, ddb_table):
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            tbl = make_table(ddb, "qbu-isolation", "user_id", "item_id")
            tbl.put_item(Item={"user_id": "alice", "item_id": "1"})
            tbl.put_item(Item={"user_id": "bob", "item_id": "2"})
            assert db_mod.query_by_user(tbl, "alice") == [
                {"user_id": "alice", "item_id": "1"}
            ]


class TestGetItem:
    def test_returns_none_when_missing(self):
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            tbl = make_table(ddb, "gi-missing", "user_id", "item_id")
            result = db_mod.get_item(tbl, USER, "item_id", "nope")
            assert result is None

    def test_returns_item_when_present(self):
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            tbl = make_table(ddb, "gi-present", "user_id", "item_id")
            tbl.put_item(Item={"user_id": USER, "item_id": "x", "data": "hello"})
            result = db_mod.get_item(tbl, USER, "item_id", "x")
            assert result == {"user_id": USER, "item_id": "x", "data": "hello"}

    def test_does_not_return_wrong_user(self):
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            tbl = make_table(ddb, "gi-wronguser", "user_id", "item_id")
            tbl.put_item(Item={"user_id": "alice", "item_id": "x"})
            result = db_mod.get_item(tbl, "bob", "item_id", "x")
            assert result is None


class TestDeleteItem:
    def test_deletes_existing_item(self):
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            tbl = make_table(ddb, "di-delete", "user_id", "item_id")
            tbl.put_item(Item={"user_id": USER, "item_id": "del-me"})
            db_mod.delete_item(tbl, USER, "item_id", "del-me")
            assert db_mod.get_item(tbl, USER, "item_id", "del-me") is None

    def test_delete_nonexistent_is_silent(self):
        with mock_aws():
            ddb = boto3.resource("dynamodb", region_name="us-east-1")
            tbl = make_table(ddb, "di-noop", "user_id", "item_id")
            # Should not raise
            db_mod.delete_item(tbl, USER, "item_id", "ghost")
