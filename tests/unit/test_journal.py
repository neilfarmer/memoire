"""Unit tests for lambda/journal/crud.py."""

import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

# ── env vars must be set before module load ───────────────────────────────────
os.environ["TABLE_NAME"] = "test-journal"

crud = load_lambda("journal", "crud.py")

import utils  # noqa: E402 — loaded via conftest after env vars set

TABLE = "test-journal"


@pytest.fixture
def tbl():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TABLE, "user_id", "entry_date")
        yield


# ── _parse_tags ───────────────────────────────────────────────────────────────

class TestParseTags:
    def test_none_returns_empty(self):
        assert utils.parse_tags(None) == []

    def test_empty_string_returns_empty(self):
        assert utils.parse_tags("") == []

    def test_list_input(self):
        assert utils.parse_tags(["a", "b", " c "]) == ["a", "b", "c"]

    def test_list_strips_blanks(self):
        assert utils.parse_tags(["  ", "x"]) == ["x"]

    def test_comma_string(self):
        assert utils.parse_tags("foo, bar, baz") == ["foo", "bar", "baz"]

    def test_comma_string_strips_whitespace(self):
        assert utils.parse_tags("  hello , world ") == ["hello", "world"]


# ── _summary ──────────────────────────────────────────────────────────────────

class TestSummary:
    def test_strips_body_field(self):
        s = crud._summary({"user_id": USER, "entry_date": "2024-01-01", "body": "x"})
        assert "body" not in s

    def test_adds_preview(self):
        s = crud._summary({"body": "hello"})
        assert s["preview"] == "hello"

    def test_preview_truncated_at_200(self):
        long_body = "x" * 300
        s = crud._summary({"body": long_body})
        assert s["preview"].endswith("...")
        assert len(s["preview"]) == 203  # 200 + "..."

    def test_short_body_no_ellipsis(self):
        s = crud._summary({"body": "short"})
        assert not s["preview"].endswith("...")


# ── list_entries ──────────────────────────────────────────────────────────────

class TestListEntries:
    def test_empty_list(self, tbl):
        r = crud.list_entries(USER)
        assert r["statusCode"] == 200
        assert json.loads(r["body"]) == []

    def test_returns_summaries_sorted_desc(self, tbl):
        crud.upsert_entry(USER, "2024-01-01", {"body": "first"})
        crud.upsert_entry(USER, "2024-01-03", {"body": "third"})
        crud.upsert_entry(USER, "2024-01-02", {"body": "second"})
        items = json.loads(crud.list_entries(USER)["body"])
        dates = [i["entry_date"] for i in items]
        assert dates == ["2024-01-03", "2024-01-02", "2024-01-01"]

    def test_isolates_users(self, tbl):
        crud.upsert_entry(USER, "2024-01-01", {"body": "mine"})
        crud.upsert_entry("other-user", "2024-01-01", {"body": "theirs"})
        items = json.loads(crud.list_entries(USER)["body"])
        assert len(items) == 1


# ── search_entries ────────────────────────────────────────────────────────────

class TestSearchEntries:
    def test_matches_title(self, tbl):
        crud.upsert_entry(USER, "2024-01-01", {"title": "Project Alpha", "body": ""})
        crud.upsert_entry(USER, "2024-01-02", {"title": "Grocery list", "body": ""})
        results = json.loads(crud.search_entries(USER, "alpha")["body"])
        assert len(results) == 1
        assert results[0]["entry_date"] == "2024-01-01"

    def test_matches_body(self, tbl):
        crud.upsert_entry(USER, "2024-01-01", {"body": "Had a great workout"})
        results = json.loads(crud.search_entries(USER, "workout")["body"])
        assert len(results) == 1

    def test_matches_tags(self, tbl):
        crud.upsert_entry(USER, "2024-01-01", {"body": "", "tags": ["fitness", "health"]})
        results = json.loads(crud.search_entries(USER, "fitness")["body"])
        assert len(results) == 1

    def test_case_insensitive(self, tbl):
        crud.upsert_entry(USER, "2024-01-01", {"title": "UPPER CASE", "body": ""})
        results = json.loads(crud.search_entries(USER, "upper case")["body"])
        assert len(results) == 1

    def test_no_match_returns_empty(self, tbl):
        crud.upsert_entry(USER, "2024-01-01", {"title": "Unrelated", "body": ""})
        results = json.loads(crud.search_entries(USER, "xyz_not_found")["body"])
        assert results == []


# ── get_entry ─────────────────────────────────────────────────────────────────

class TestGetEntry:
    def test_returns_entry(self, tbl):
        crud.upsert_entry(USER, "2024-06-15", {"body": "hello"})
        r = crud.get_entry(USER, "2024-06-15")
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["body"] == "hello"

    def test_not_found(self, tbl):
        r = crud.get_entry(USER, "2024-01-01")
        assert r["statusCode"] == 404

    def test_invalid_date_format(self, tbl):
        r = crud.get_entry(USER, "01-01-2024")
        assert r["statusCode"] == 400

    def test_invalid_date_letters(self, tbl):
        r = crud.get_entry(USER, "not-a-date")
        assert r["statusCode"] == 400


# ── upsert_entry ──────────────────────────────────────────────────────────────

class TestUpsertEntry:
    def test_creates_new_entry(self, tbl):
        r = crud.upsert_entry(USER, "2024-03-10", {"body": "Day one"})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["body"] == "Day one"
        assert body["user_id"] == USER
        assert "created_at" in body

    def test_updates_existing_entry(self, tbl):
        crud.upsert_entry(USER, "2024-03-10", {"body": "original"})
        r = crud.upsert_entry(USER, "2024-03-10", {"body": "updated"})
        assert json.loads(r["body"])["body"] == "updated"

    def test_preserves_created_at_on_update(self, tbl):
        r1 = crud.upsert_entry(USER, "2024-03-10", {"body": "first"})
        created_at = json.loads(r1["body"])["created_at"]
        r2 = crud.upsert_entry(USER, "2024-03-10", {"body": "second"})
        assert json.loads(r2["body"])["created_at"] == created_at

    def test_invalid_date_returns_400(self, tbl):
        r = crud.upsert_entry(USER, "2024/03/10", {"body": ""})
        assert r["statusCode"] == 400

    def test_invalid_mood_returns_400(self, tbl):
        r = crud.upsert_entry(USER, "2024-03-10", {"mood": "ecstatic"})
        assert r["statusCode"] == 400

    def test_valid_mood_accepted(self, tbl):
        for mood in ("great", "good", "okay", "bad", "terrible"):
            r = crud.upsert_entry(USER, "2024-03-10", {"mood": mood})
            assert r["statusCode"] == 200

    def test_tags_parsed_from_list(self, tbl):
        r = crud.upsert_entry(USER, "2024-03-10", {"body": "", "tags": ["a", "b"]})
        assert json.loads(r["body"])["tags"] == ["a", "b"]

    def test_tags_parsed_from_string(self, tbl):
        r = crud.upsert_entry(USER, "2024-03-10", {"body": "", "tags": "x, y"})
        assert json.loads(r["body"])["tags"] == ["x", "y"]


# ── delete_entry ──────────────────────────────────────────────────────────────

class TestDeleteEntry:
    def test_deletes_entry(self, tbl):
        crud.upsert_entry(USER, "2024-05-01", {"body": "bye"})
        r = crud.delete_entry(USER, "2024-05-01")
        assert r["statusCode"] == 204
        assert crud.get_entry(USER, "2024-05-01")["statusCode"] == 404

    def test_delete_nonexistent_returns_404(self, tbl):
        r = crud.delete_entry(USER, "2024-05-01")
        assert r["statusCode"] == 404

    def test_invalid_date_returns_400(self, tbl):
        r = crud.delete_entry(USER, "bad-date")
        assert r["statusCode"] == 400
