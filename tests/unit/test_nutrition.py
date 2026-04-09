"""Unit tests for lambda/nutrition/crud.py.

Same note as test_health.py: nutrition/crud.py uses a raw string
KeyConditionExpression (tracked in GitHub issue #16).
"""

import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

os.environ["TABLE_NAME"] = "test-nutrition"

crud = load_lambda("nutrition", "crud.py")

TABLE = "test-nutrition"


@pytest.fixture
def tbl():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TABLE, "user_id", "log_date")
        yield


# ── _summary ──────────────────────────────────────────────────────────────────

class TestSummary:
    def test_meal_count(self):
        item = {
            "user_id": USER, "log_date": "2024-01-01",
            "meals": [{"name": "Breakfast"}, {"name": "Lunch"}],
            "created_at": "t", "updated_at": "t",
        }
        s = crud._summary(item)
        assert s["meal_count"] == 2

    def test_total_cal(self):
        item = {
            "user_id": USER, "log_date": "2024-01-01",
            "meals": [{"calories": 500}, {"calories": 350}],
            "created_at": "t", "updated_at": "t",
        }
        assert crud._summary(item)["total_cal"] == 850

    def test_total_cal_handles_none_calories(self):
        item = {
            "user_id": USER, "log_date": "2024-01-01",
            "meals": [{"name": "Mystery meal"}],  # no calories key
            "created_at": "t", "updated_at": "t",
        }
        assert crud._summary(item)["total_cal"] == 0

    def test_empty_meals(self):
        item = {"user_id": USER, "log_date": "2024-01-01", "created_at": "t", "updated_at": "t"}
        s = crud._summary(item)
        assert s["meal_count"] == 0
        assert s["total_cal"] == 0


# ── list_logs ─────────────────────────────────────────────────────────────────

class TestListLogs:
    def test_empty(self, tbl):
        r = crud.list_logs(USER)
        assert r["statusCode"] == 200
        assert json.loads(r["body"]) == []

    def test_sorted_desc(self, tbl):
        crud.upsert_log(USER, "2024-01-01", {"meals": []})
        crud.upsert_log(USER, "2024-01-03", {"meals": []})
        crud.upsert_log(USER, "2024-01-02", {"meals": []})
        dates = [i["log_date"] for i in json.loads(crud.list_logs(USER)["body"])]
        assert dates == ["2024-01-03", "2024-01-02", "2024-01-01"]

    def test_returns_summaries(self, tbl):
        crud.upsert_log(USER, "2024-01-01", {"meals": [{"name": "Pasta", "calories": 600}]})
        items = json.loads(crud.list_logs(USER)["body"])
        assert "meals" not in items[0]
        assert items[0]["meal_count"] == 1
        assert items[0]["total_cal"] == 600


# ── get_log ───────────────────────────────────────────────────────────────────

class TestGetLog:
    def test_returns_log(self, tbl):
        crud.upsert_log(USER, "2024-03-10", {"meals": [{"name": "Salad"}]})
        r = crud.get_log(USER, "2024-03-10")
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["meals"][0]["name"] == "Salad"

    def test_not_found(self, tbl):
        assert crud.get_log(USER, "2024-03-10")["statusCode"] == 404

    def test_invalid_date(self, tbl):
        assert crud.get_log(USER, "10/03/2024")["statusCode"] == 400


# ── upsert_log ────────────────────────────────────────────────────────────────

class TestUpsertLog:
    def test_creates_log(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {"meals": []})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["log_date"] == "2024-05-01"

    def test_auto_assigns_meal_id(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {"meals": [{"name": "Tacos"}]})
        meal = json.loads(r["body"])["meals"][0]
        assert "id" in meal

    def test_preserves_existing_meal_id(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {"meals": [{"id": "kept", "name": "X"}]})
        assert json.loads(r["body"])["meals"][0]["id"] == "kept"

    def test_preserves_created_at(self, tbl):
        r1 = crud.upsert_log(USER, "2024-05-01", {"meals": []})
        ca = json.loads(r1["body"])["created_at"]
        r2 = crud.upsert_log(USER, "2024-05-01", {"meals": [], "notes": "x"})
        assert json.loads(r2["body"])["created_at"] == ca

    def test_invalid_date_returns_400(self, tbl):
        assert crud.upsert_log(USER, "2024/05/01", {})["statusCode"] == 400

    def test_preserves_created_at_on_legacy_record(self, tbl):
        # Records created before created_at was added have no such field;
        # upsert should not raise KeyError and should backfill created_at.
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.Table(TABLE).put_item(Item={
            "user_id": USER, "log_date": "2023-01-01",
            "meals": [], "notes": "",
            # deliberately omit created_at to simulate a legacy record
        })
        r = crud.upsert_log(USER, "2023-01-01", {"meals": [], "notes": "updated"})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["created_at"]  # backfilled, not empty

    def test_edit_ai_created_entry_succeeds(self, tbl):
        # Reproduces: AI creates entry with Decimal protein_g/carbs_g/fat_g →
        # frontend reads it (Decimal serialised to float) → edit sends floats back →
        # upsert used to 500 because DynamoDB rejects Python floats.
        from decimal import Decimal
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.Table(TABLE).put_item(Item={
            "user_id":    USER,
            "log_date":   "2024-06-01",
            "meals":      [{"id": "ai-1", "name": "Chicken", "calories": Decimal("350"),
                            "protein_g": Decimal("45.5"), "carbs_g": Decimal("10.2"), "fat_g": Decimal("8.0")}],
            "notes":      "",
            "created_at": "2024-06-01T12:00:00Z",
            "updated_at": "2024-06-01T12:00:00Z",
        })
        # Simulate frontend round-trip: Decimal → JSON float → Python float on edit
        r = crud.upsert_log(USER, "2024-06-01", {
            "meals": [{"id": "ai-1", "name": "Chicken", "calories": 350.0,
                       "protein_g": 45.5, "carbs_g": 10.2, "fat_g": 8.0}],
            "notes": "edited",
        })
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["notes"] == "edited"

    def test_macros_stored(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {
            "meals": [{"name": "Chicken", "calories": 300, "protein_g": 50,
                       "carbs_g": 10, "fat_g": 8}]
        })
        meal = json.loads(r["body"])["meals"][0]
        assert meal["protein_g"] == 50
        assert meal["carbs_g"] == 10
        assert meal["fat_g"] == 8


# ── delete_log ────────────────────────────────────────────────────────────────

class TestDeleteLog:
    def test_deletes_log(self, tbl):
        crud.upsert_log(USER, "2024-05-01", {"meals": []})
        r = crud.delete_log(USER, "2024-05-01")
        assert r["statusCode"] == 204
        assert crud.get_log(USER, "2024-05-01")["statusCode"] == 404

    def test_not_found(self, tbl):
        assert crud.delete_log(USER, "2024-05-01")["statusCode"] == 404

    def test_invalid_date(self, tbl):
        assert crud.delete_log(USER, "bad-date")["statusCode"] == 400
