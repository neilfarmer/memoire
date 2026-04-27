"""Unit tests for lambda/health/crud.py."""

import json
import os

import boto3
import pytest
from freezegun import freeze_time
from moto import mock_aws

from conftest import USER, load_lambda, make_table

os.environ["TABLE_NAME"] = "test-health"

crud = load_lambda("health", "crud.py")

import utils  # noqa: E402

TABLE = "test-health"


@pytest.fixture
def tbl():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TABLE, "user_id", "log_date")
        yield


# ── validate_date (now in shared utils) ──────────────────────────────────────

class TestValidateDate:
    def test_valid_date_returns_none(self):
        assert utils.validate_date("2024-01-15") is None

    def test_invalid_format_returns_error(self):
        assert utils.validate_date("15-01-2024") is not None

    def test_none_returns_error(self):
        assert utils.validate_date(None) is not None

    def test_empty_string_returns_error(self):
        assert utils.validate_date("") is not None


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


# ── Schema enrichment (type / distance / intensity / muscle_groups) ───────────

class TestExerciseSchema:
    def test_stores_type_and_extras(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {"exercises": [{
            "name": "Run", "type": "cardio", "duration_min": 30,
            "distance_km": 5.2, "intensity": 7, "muscle_groups": ["legs", "core"],
        }]})
        ex = json.loads(r["body"])["exercises"][0]
        assert ex["type"] == "cardio"
        assert ex["duration_min"] == 30
        assert float(ex["distance_km"]) == 5.2
        assert ex["intensity"] == 7
        assert ex["muscle_groups"] == ["legs", "core"]

    def test_rejects_unknown_type(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {"exercises": [{
            "name": "Bench", "type": "invalid",
        }]})
        ex = json.loads(r["body"])["exercises"][0]
        assert "type" not in ex

    def test_rejects_negative_sets(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {"exercises": [{
            "name": "Squat",
            "sets": [{"reps": 5, "weight": 225}, {"reps": -1, "weight": 225}],
        }]})
        ex = json.loads(r["body"])["exercises"][0]
        assert len(ex["sets"]) == 1

    def test_drops_empty_name_exercise(self, tbl):
        r = crud.upsert_log(USER, "2024-05-01", {"exercises": [
            {"name": ""},
            {"name": "  "},
            {"name": "Pushups"},
        ]})
        exs = json.loads(r["body"])["exercises"]
        assert len(exs) == 1
        assert exs[0]["name"] == "Pushups"

    def test_intensity_clamped_to_range(self, tbl):
        # intensity > 10 is dropped silently
        r = crud.upsert_log(USER, "2024-05-01", {"exercises": [{
            "name": "Heavy", "intensity": 12,
        }]})
        ex = json.loads(r["body"])["exercises"][0]
        assert "intensity" not in ex

    def test_created_at_backfills_on_legacy_record(self, tbl):
        # Record without created_at — must not KeyError
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.Table(TABLE).put_item(Item={
            "user_id": USER, "log_date": "2023-01-01",
            "exercises": [], "notes": "",
        })
        r = crud.upsert_log(USER, "2023-01-01", {"exercises": []})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["created_at"]


class TestSummaryEndpoint:
    @freeze_time("2024-05-20")
    def test_defaults_last_30_days(self, tbl):
        crud.upsert_log(USER, "2024-05-19", {"exercises": [{
            "name": "Squat", "sets": [{"reps": 5, "weight": 100}, {"reps": 5, "weight": 100}],
        }]})
        crud.upsert_log(USER, "2024-05-20", {"exercises": [{
            "name": "Run", "duration_min": 20, "distance_km": 3,
        }]})
        r = crud.summary(USER, {})
        body = json.loads(r["body"])
        assert body["workout_days"] == 2
        assert body["exercise_count"] == 2
        assert body["total_volume"] == 1000  # 5*100 + 5*100
        assert body["total_duration"] == 20
        assert body["total_distance"] == 3

    @freeze_time("2024-05-20")
    def test_streak_counts_consecutive_days_ending_today(self, tbl):
        for d in ("2024-05-18", "2024-05-19", "2024-05-20"):
            crud.upsert_log(USER, d, {"exercises": [{"name": "X", "sets": []}]})
        r = crud.summary(USER, {})
        body = json.loads(r["body"])
        assert body["streak_days"] == 3

    @freeze_time("2024-05-20")
    def test_streak_breaks_on_gap(self, tbl):
        crud.upsert_log(USER, "2024-05-18", {"exercises": [{"name": "X", "sets": []}]})
        # Gap at 2024-05-19, then today
        crud.upsert_log(USER, "2024-05-20", {"exercises": [{"name": "Y", "sets": []}]})
        r = crud.summary(USER, {})
        assert json.loads(r["body"])["streak_days"] == 1

    def test_respects_explicit_range(self, tbl):
        crud.upsert_log(USER, "2024-01-01", {"exercises": [{"name": "X", "sets": []}]})
        crud.upsert_log(USER, "2024-06-01", {"exercises": [{"name": "Y", "sets": []}]})
        r = crud.summary(USER, {"from": "2024-01-01", "to": "2024-01-31"})
        assert json.loads(r["body"])["workout_days"] == 1

    def test_invalid_from_returns_400(self, tbl):
        assert crud.summary(USER, {"from": "bad"})["statusCode"] == 400


class TestRecentExercises:
    @freeze_time("2024-05-20")
    def test_returns_distinct_by_name(self, tbl):
        crud.upsert_log(USER, "2024-05-18", {"exercises": [
            {"name": "Bench", "sets": [{"reps": 5, "weight": 135}]},
        ]})
        crud.upsert_log(USER, "2024-05-20", {"exercises": [
            {"name": "bench", "sets": [{"reps": 6, "weight": 140}]},
            {"name": "Squat", "sets": []},
        ]})
        r = crud.recent_exercises(USER, {})
        names = [x["name"] for x in json.loads(r["body"])]
        # Case-insensitive de-dupe; most recent ordering
        assert sorted(x.lower() for x in names) == ["bench", "squat"]

    @freeze_time("2024-05-20")
    def test_most_recent_config_wins(self, tbl):
        crud.upsert_log(USER, "2024-05-10", {"exercises": [
            {"name": "Bench", "sets": [{"reps": 5, "weight": 135}]},
        ]})
        crud.upsert_log(USER, "2024-05-18", {"exercises": [
            {"name": "Bench", "sets": [{"reps": 8, "weight": 155}]},
        ]})
        r = crud.recent_exercises(USER, {})
        rec = [x for x in json.loads(r["body"]) if x["name"].lower() == "bench"][0]
        assert rec["last_date"] == "2024-05-18"
        assert rec["count"] == 2
        assert rec["sets"][0]["weight"] == 155

    @freeze_time("2024-05-20")
    def test_filter_by_q(self, tbl):
        crud.upsert_log(USER, "2024-05-18", {"exercises": [
            {"name": "Bench Press"}, {"name": "Squat"},
        ]})
        r = crud.recent_exercises(USER, {"q": "bench"})
        names = [x["name"] for x in json.loads(r["body"])]
        assert names == ["Bench Press"]

    @freeze_time("2024-05-20")
    def test_respects_days_window(self, tbl):
        crud.upsert_log(USER, "2024-01-01", {"exercises": [{"name": "Ancient"}]})
        crud.upsert_log(USER, "2024-05-18", {"exercises": [{"name": "Recent"}]})
        r = crud.recent_exercises(USER, {"days": 30})
        names = [x["name"] for x in json.loads(r["body"])]
        assert names == ["Recent"]


# ── Foods / activity totals (unified health daily log) ───────────────────────

class TestFoods:
    def test_add_food_creates_row(self, tbl):
        r = crud.add_food(USER, "2024-05-20", {"name": "Apple", "calories": 95})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["food"]["name"]   == "Apple"
        assert body["food"]["source"] == "manual"
        assert body["food"]["calories"] == 95
        assert len(body["log"]["foods"]) == 1

    def test_add_food_appends_to_existing(self, tbl):
        crud.add_food(USER, "2024-05-20", {"name": "Apple", "calories": 95})
        crud.add_food(USER, "2024-05-20", {"name": "Banana", "calories": 105})
        r = crud.get_log(USER, "2024-05-20")
        body = json.loads(r["body"])
        names = [f["name"] for f in body["foods"]]
        assert names == ["Apple", "Banana"]

    def test_add_food_requires_name(self, tbl):
        r = crud.add_food(USER, "2024-05-20", {"calories": 100})
        assert r["statusCode"] == 400

    def test_add_food_invalid_date(self, tbl):
        r = crud.add_food(USER, "bad-date", {"name": "Apple"})
        assert r["statusCode"] == 400

    def test_delete_food_removes_entry(self, tbl):
        crud.add_food(USER, "2024-05-20", {"id": "f1", "name": "Apple"})
        crud.add_food(USER, "2024-05-20", {"id": "f2", "name": "Banana"})
        r = crud.delete_food(USER, "2024-05-20", "f1")
        assert r["statusCode"] == 204
        body = json.loads(crud.get_log(USER, "2024-05-20")["body"])
        assert [f["id"] for f in body["foods"]] == ["f2"]

    def test_delete_food_missing_returns_404(self, tbl):
        crud.add_food(USER, "2024-05-20", {"id": "f1", "name": "Apple"})
        r = crud.delete_food(USER, "2024-05-20", "missing-id")
        assert r["statusCode"] == 404

    def test_delete_food_no_log(self, tbl):
        r = crud.delete_food(USER, "2024-05-20", "f1")
        assert r["statusCode"] == 404


class TestActivityTotals:
    def test_set_steps_and_sleep(self, tbl):
        r = crud.set_activity_totals(USER, "2024-05-20", {
            "steps":          8000,
            "calories_out":   2500,
            "active_minutes": 45,
            "weight":         180.5,
            "weight_unit":    "lb",
            "weight_date":    "2024-05-19",
            "sleep": {"minutes_asleep": 480, "efficiency": 92},
        })
        assert r["statusCode"] == 200
        body = json.loads(crud.get_log(USER, "2024-05-20")["body"])
        assert int(body["steps"]) == 8000
        assert body["weight_unit"] == "lb"
        assert int(body["sleep"]["minutes_asleep"]) == 480
        assert int(body["sleep"]["efficiency"])     == 92

    def test_set_does_not_clobber_foods(self, tbl):
        crud.add_food(USER, "2024-05-20", {"name": "Apple"})
        crud.set_activity_totals(USER, "2024-05-20", {"steps": 1000})
        body = json.loads(crud.get_log(USER, "2024-05-20")["body"])
        assert int(body["steps"]) == 1000
        assert len(body["foods"]) == 1
        assert body["foods"][0]["name"] == "Apple"

    def test_invalid_date(self, tbl):
        r = crud.set_activity_totals(USER, "bad", {"steps": 100})
        assert r["statusCode"] == 400


class TestMergeSourceFoods:
    def test_replaces_only_matching_source(self, tbl):
        crud.add_food(USER, "2024-05-20", {"name": "Manual Apple", "source": "manual"})
        crud.add_food(USER, "2024-05-20", {"name": "Old Fitbit",   "source": "fitbit"})
        r = crud.merge_source_foods(USER, "2024-05-20", "fitbit", [
            {"name": "New Fitbit Food", "calories": 200, "fitbit_log_id": "abc"},
        ])
        assert r["statusCode"] == 200
        body = json.loads(crud.get_log(USER, "2024-05-20")["body"])
        names = sorted(f["name"] for f in body["foods"])
        assert names == ["Manual Apple", "New Fitbit Food"]
        for f in body["foods"]:
            if f["name"] == "New Fitbit Food":
                assert f["source"] == "fitbit"
                assert f["fitbit_log_id"] == "abc"

    def test_invalid_source_rejected(self, tbl):
        r = crud.merge_source_foods(USER, "2024-05-20", "BAD SOURCE", [])
        assert r["statusCode"] == 400

    def test_empty_list_clears_source(self, tbl):
        crud.add_food(USER, "2024-05-20", {"name": "Old Fitbit",  "source": "fitbit"})
        crud.add_food(USER, "2024-05-20", {"name": "Manual",      "source": "manual"})
        crud.merge_source_foods(USER, "2024-05-20", "fitbit", [])
        body = json.loads(crud.get_log(USER, "2024-05-20")["body"])
        assert [f["name"] for f in body["foods"]] == ["Manual"]


class TestNormalizeFood:
    def test_unknown_source_falls_back_to_manual(self):
        out = crud._normalize_food({"name": "Apple", "source": "MIXED CASE INVALID"})
        assert out["source"] == "manual"

    def test_carries_meal_type_id(self):
        out = crud._normalize_food({"name": "Eggs", "meal_type_id": 1})
        assert out["meal_type_id"] == 1

    def test_drops_invalid_meal_type(self):
        out = crud._normalize_food({"name": "Eggs", "meal_type_id": 99})
        assert "meal_type_id" not in out


class TestHistory:
    def test_empty(self, tbl):
        r = crud.get_history(USER, {})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["rows"] == []

    @freeze_time("2026-04-27")
    def test_returns_recent_rows_excluding_today(self, tbl):
        crud.set_activity_totals(USER, "2026-04-25", {"steps": 5000})
        crud.set_activity_totals(USER, "2026-04-26", {"steps": 7000})
        crud.set_activity_totals(USER, "2026-04-27", {"steps": 3000})  # today, excluded
        r = crud.get_history(USER, {"days": 30})
        body = json.loads(r["body"])
        dates = [row["log_date"] for row in body["rows"]]
        assert dates == ["2026-04-25", "2026-04-26"]

    @freeze_time("2026-04-27")
    def test_aggregates_food_calories(self, tbl):
        crud.add_food(USER, "2026-04-26", {"name": "Apple",  "calories": 95})
        crud.add_food(USER, "2026-04-26", {"name": "Banana", "calories": 105})
        r = crud.get_history(USER, {"days": 7})
        body = json.loads(r["body"])
        row = body["rows"][0]
        assert row["calories_in"] == 200
        assert row["food_count"]   == 2

    @freeze_time("2026-04-27")
    def test_include_today(self, tbl):
        crud.set_activity_totals(USER, "2026-04-27", {"steps": 100})
        r = crud.get_history(USER, {"days": 7, "include_today": "1"})
        body = json.loads(r["body"])
        assert len(body["rows"]) == 1
        assert body["rows"][0]["log_date"] == "2026-04-27"
