"""Unit tests for lambda/goals/crud.py."""

import json
import os

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda, make_table

os.environ["TABLE_NAME"] = "test-goals"

crud = load_lambda("goals", "crud.py")

TABLE = "test-goals"


@pytest.fixture
def tbl():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TABLE, "user_id", "goal_id")
        yield


# ── list_goals ────────────────────────────────────────────────────────────────

class TestListGoals:
    def test_empty(self, tbl):
        r = crud.list_goals(USER)
        assert r["statusCode"] == 200
        assert json.loads(r["body"]) == []

    def test_returns_own_goals_only(self, tbl):
        crud.create_goal(USER, {"title": "Mine"})
        crud.create_goal("other", {"title": "Theirs"})
        items = json.loads(crud.list_goals(USER)["body"])
        assert len(items) == 1


# ── create_goal ───────────────────────────────────────────────────────────────

class TestCreateGoal:
    def test_requires_title(self, tbl):
        r = crud.create_goal(USER, {})
        assert r["statusCode"] == 400

    def test_blank_title_rejected(self, tbl):
        r = crud.create_goal(USER, {"title": "   "})
        assert r["statusCode"] == 400

    def test_creates_with_defaults(self, tbl):
        r = crud.create_goal(USER, {"title": "Learn piano"})
        assert r["statusCode"] == 201
        body = json.loads(r["body"])
        assert body["status"] == "active"
        assert body["title"] == "Learn piano"
        assert "goal_id" in body
        assert "created_at" in body

    def test_creates_with_explicit_status(self, tbl):
        r = crud.create_goal(USER, {"title": "Old goal", "status": "completed"})
        assert json.loads(r["body"])["status"] == "completed"

    def test_invalid_status_rejected(self, tbl):
        r = crud.create_goal(USER, {"title": "Bad", "status": "paused"})
        assert r["statusCode"] == 400

    def test_valid_statuses(self, tbl):
        for s in ("active", "completed", "abandoned"):
            r = crud.create_goal(USER, {"title": f"Goal {s}", "status": s})
            assert r["statusCode"] == 201

    def test_target_date_stored(self, tbl):
        r = crud.create_goal(USER, {"title": "Deadline", "target_date": "2025-12-31"})
        assert json.loads(r["body"])["target_date"] == "2025-12-31"

    def test_none_values_not_stored(self, tbl):
        r = crud.create_goal(USER, {"title": "No date"})
        body = json.loads(r["body"])
        assert "target_date" not in body

    def test_title_too_long_rejected(self, tbl):
        r = crud.create_goal(USER, {"title": "x" * 501})
        assert r["statusCode"] == 400

    def test_description_too_long_rejected(self, tbl):
        r = crud.create_goal(USER, {"title": "OK", "description": "x" * 10_001})
        assert r["statusCode"] == 400


# ── get_goal ──────────────────────────────────────────────────────────────────

class TestGetGoal:
    def test_returns_goal(self, tbl):
        goal_id = json.loads(crud.create_goal(USER, {"title": "Find me"})["body"])["goal_id"]
        r = crud.get_goal(USER, goal_id)
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["title"] == "Find me"

    def test_not_found(self, tbl):
        assert crud.get_goal(USER, "ghost")["statusCode"] == 404

    def test_cannot_get_other_users_goal(self, tbl):
        goal_id = json.loads(crud.create_goal("alice", {"title": "Alice"})["body"])["goal_id"]
        assert crud.get_goal("bob", goal_id)["statusCode"] == 404


# ── update_goal ───────────────────────────────────────────────────────────────

class TestUpdateGoal:
    def test_updates_title(self, tbl):
        goal_id = json.loads(crud.create_goal(USER, {"title": "Old"})["body"])["goal_id"]
        r = crud.update_goal(USER, goal_id, {"title": "New"})
        assert r["statusCode"] == 200
        assert json.loads(r["body"])["title"] == "New"

    def test_updates_status(self, tbl):
        goal_id = json.loads(crud.create_goal(USER, {"title": "G"})["body"])["goal_id"]
        r = crud.update_goal(USER, goal_id, {"status": "completed"})
        assert json.loads(r["body"])["status"] == "completed"

    def test_no_valid_fields_returns_400(self, tbl):
        goal_id = json.loads(crud.create_goal(USER, {"title": "G"})["body"])["goal_id"]
        r = crud.update_goal(USER, goal_id, {"unknown": "x"})
        assert r["statusCode"] == 400

    def test_empty_title_rejected(self, tbl):
        goal_id = json.loads(crud.create_goal(USER, {"title": "G"})["body"])["goal_id"]
        r = crud.update_goal(USER, goal_id, {"title": ""})
        assert r["statusCode"] == 400

    def test_invalid_status_rejected(self, tbl):
        goal_id = json.loads(crud.create_goal(USER, {"title": "G"})["body"])["goal_id"]
        r = crud.update_goal(USER, goal_id, {"status": "paused"})
        assert r["statusCode"] == 400

    def test_update_nonexistent_returns_404(self, tbl):
        r = crud.update_goal(USER, "ghost", {"title": "X"})
        assert r["statusCode"] == 404


# ── delete_goal ───────────────────────────────────────────────────────────────

class TestDeleteGoal:
    def test_deletes_goal(self, tbl):
        goal_id = json.loads(crud.create_goal(USER, {"title": "Done"})["body"])["goal_id"]
        r = crud.delete_goal(USER, goal_id)
        assert r["statusCode"] == 204
        assert crud.get_goal(USER, goal_id)["statusCode"] == 404

    def test_delete_nonexistent_returns_404(self, tbl):
        assert crud.delete_goal(USER, "ghost")["statusCode"] == 404
