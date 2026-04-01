"""Unit tests for lambda/health/crud.py.

Note: health/crud.py uses a raw string KeyConditionExpression
  ``KeyConditionExpression="user_id = :uid"``
instead of the Key() helper used everywhere else.  Moto supports this form, so
the tests exercise the real code path.  The inconsistency is tracked in
GitHub issue #16.
"""

import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

os.environ["TABLE_NAME"] = "test-health"

crud = load_lambda("health", "crud.py")

TABLE = "test-health"


@pytest.fixture
def tbl():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TABLE, "user_id", "log_date")
        yield


# ── _validate_date ────────────────────────────────────────────────────────────

class TestValidateDate:
    def test_valid_date_does_not_raise(self):
        crud._validate_date("2024-01-15")  # should not raise

    def test_invalid_format_raises(self):
        import pytest as _pytest
        with _pytest.raises(ValueError):
            crud._validate_date("15-01-2024")

    def test_none_raises(self):
        import pytest as _pytest
        with _pytest.raises(ValueError):
            crud._validate_date(None)

    def test_empty_string_raises(self):
        import pytest as _pytest
        with _pytest.raises(ValueError):
            crud._validate_date("")


# ── _summary ──────────────────────────────────────────────────────────────────

class TestSummary:
    def test_exercise_count(self):
        item = {
            "user_id": USER, "log_date": "2024-01-01",
            "exercises": [{"name": "push-up"}, {"name": "squat"}],
            "created_at": "t", "updated_at": "t",
        }
        s = crud._summary(item)
        assert s["exercise_count"] == 2

    def test_empty_exercises(self):
        item = {"user_id": USER, "log_date": "2024-01-01", "created_at": "t", "updated_at": "t"}
        s = crud._summary(item)
        assert s["exercise_count"] == 0

    def test_notes_included(self):
        item = {"user_id": USER, "log_date": "2024-01-01", "notes": "felt good",
                "created_at": "t", "updated_at": "t"}
        assert crud._summary(item)["notes"] == "felt good"


# ── list_logs ─────────────────────────────────────────────────────────────────

class TestListLogs:
    def test_empty(self, tbl):
        r = crud.list_logs(USER)
        assert r["statusCode"] == 200
        assert json.loads(r["body"]) == []

    def test_returns_summaries_sorted_desc(self, tbl):
        crud.upsert_log(USER, "2024-01-01", {"exercises": []})
        crud.upsert_log(USER, "2024-01-03", {"exercises": []})
        crud.upsert_log(USER, "2024-01-02", {"exercises": []})
        items = json.loads(crud.list_logs(USER)["body"])
        dates = [i["log_date"] for i in items]
        assert dates == ["2024-01-03", "2024-01-02", "2024-01-01"]

    def test_returns_summaries_not_full_records(self, tbl):
        crud.upsert_log(USER, "2024-01-01", {"exercises": [{"name": "run"}]})
        items = json.loads(crud.list_logs(USER)["body"])
        assert "exercises" not in items[0]
        assert "exercise_count" in items[0]


# ── get_log ───────────────────────────────────────────────────────────────────

class TestGetLog:
    def test_returns_log(self, tbl):
        crud.upsert_log(USER, "2024-03-10", {"exercises": [{"name": "push-up", "sets": []}]})
        r = crud.get_log(USER, "2024-03-10")
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["exercises"][0]["name"] == "push-up"

    def test_not_found(self, tbl):
        assert crud.get_log(USER, "2024-03-10")["statusCode"] == 404

    def test_invalid_date_returns_400(self, tbl):
        assert crud.get_log(USER, "10-03-2024")["statusCode"] == 400


# ── upsert_log ────────────────────────────────────────────────────────────────

class TestUpsertLog:
    def test_creates_log(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {"exercises": []})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["log_date"] == "2024-05-01"
        assert "created_at" in body

    def test_auto_assigns_exercise_id(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {
            "exercises": [{"name": "squat", "sets": []}]
        })
        ex = json.loads(r["body"])["exercises"][0]
        assert "id" in ex

    def test_preserves_existing_exercise_id(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {
            "exercises": [{"id": "my-id", "name": "squat"}]
        })
        assert json.loads(r["body"])["exercises"][0]["id"] == "my-id"

    def test_preserves_created_at_on_update(self, tbl):
        r1 = crud.upsert_log(USER, "2024-05-01", {"exercises": []})
        created_at = json.loads(r1["body"])["created_at"]
        r2 = crud.upsert_log(USER, "2024-05-01", {"exercises": [], "notes": "updated"})
        assert json.loads(r2["body"])["created_at"] == created_at

    def test_invalid_date_returns_400(self, tbl):
        assert crud.upsert_log(USER, "2024/05/01", {})["statusCode"] == 400

    def test_notes_stored(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {"exercises": [], "notes": "leg day"})
        assert json.loads(r["body"])["notes"] == "leg day"


# ── delete_log ────────────────────────────────────────────────────────────────

class TestDeleteLog:
    def test_deletes_log(self, tbl):
        crud.upsert_log(USER, "2024-05-01", {"exercises": []})
        r = crud.delete_log(USER, "2024-05-01")
        assert r["statusCode"] == 204
        assert crud.get_log(USER, "2024-05-01")["statusCode"] == 404

    def test_not_found_returns_404(self, tbl):
        assert crud.delete_log(USER, "2024-05-01")["statusCode"] == 404

    def test_invalid_date_returns_400(self, tbl):
        assert crud.delete_log(USER, "bad")["statusCode"] == 400
