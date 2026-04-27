"""Unit tests for the Fitbit lambda + sync handler."""

import json
import os
import time
from unittest.mock import patch

import boto3
import pytest
from freezegun import freeze_time
from moto import mock_aws

from conftest import USER, load_lambda, make_table

os.environ["FITBIT_TOKENS_TABLE"]   = "test-fitbit-tokens"
os.environ["FITBIT_DATA_TABLE"]     = "test-fitbit-data"
os.environ["SETTINGS_TABLE"]        = "test-fitbit-settings"
os.environ["FITBIT_SYNC_FUNCTION"]  = "test-fitbit-sync"
os.environ["FITBIT_CLIENT_ID"]      = "test-client-id"
os.environ["FITBIT_CLIENT_SECRET"]  = "test-client-secret"

oauth = load_lambda("fitbit", "oauth.py")
crud  = load_lambda("fitbit", "crud.py")
router = load_lambda("fitbit", "router.py")
sync_handler = load_lambda("fitbit_sync", "handler.py")

# Tests must reference the names captured at module-import time. Other test
# modules (e.g. test_watcher) overwrite SETTINGS_TABLE in os.environ during
# their own imports, so re-reading the env at fixture time would create a
# table the production code never scans.
TOKENS_TABLE_NAME   = sync_handler.TOKENS_TABLE
DATA_TABLE_NAME     = sync_handler.DATA_TABLE
SETTINGS_TABLE_NAME = sync_handler.SETTINGS_TABLE


@pytest.fixture
def tables():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        make_table(ddb, TOKENS_TABLE_NAME,   "user_id")
        make_table(ddb, DATA_TABLE_NAME,     "user_id", "log_date")
        make_table(ddb, SETTINGS_TABLE_NAME, "user_id")
        yield ddb


# ── PKCE ──────────────────────────────────────────────────────────────────────

class TestPkce:
    def test_pair_lengths(self):
        verifier, challenge = oauth._pkce_pair()
        assert 43 <= len(verifier) <= 128
        assert 43 <= len(challenge) <= 128
        assert verifier != challenge

    def test_unique_per_call(self):
        a, _ = oauth._pkce_pair()
        b, _ = oauth._pkce_pair()
        assert a != b


# ── oauth.start ───────────────────────────────────────────────────────────────

class TestStart:
    def test_missing_redirect_uri(self):
        r = oauth.start(USER, {})
        assert r["statusCode"] == 400

    def test_returns_authorize_url_and_verifier(self):
        r = oauth.start(USER, {"redirect_uri": "https://example.com/cb"})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["authorize_url"].startswith("https://www.fitbit.com/oauth2/authorize?")
        assert "code_challenge" in body["authorize_url"]
        assert "redirect_uri=https%3A%2F%2Fexample.com%2Fcb" in body["authorize_url"]
        assert body["code_verifier"]
        assert body["state"]

    def test_returns_503_when_unconfigured(self):
        with patch.object(oauth, "CLIENT_ID", ""):
            r = oauth.start(USER, {"redirect_uri": "https://example.com/cb"})
        assert r["statusCode"] == 503


# ── oauth.callback ────────────────────────────────────────────────────────────

class TestCallback:
    def test_missing_fields(self, tables):
        r = oauth.callback(USER, {})
        assert r["statusCode"] == 400

    def test_persists_tokens_on_success(self, tables):
        fake_resp = {
            "access_token":  "AT",
            "refresh_token": "RT",
            "expires_in":    3600,
            "scope":         "activity sleep",
            "user_id":       "FB-USER",
        }
        with patch.object(oauth, "_token_request", return_value=fake_resp):
            r = oauth.callback(USER, {
                "code":          "abc",
                "redirect_uri":  "https://example.com/cb",
                "code_verifier": "v",
            })
        assert r["statusCode"] == 200

        item = tables.Table(TOKENS_TABLE_NAME).get_item(
            Key={"user_id": USER}
        ).get("Item")
        assert item["access_token"]  == "AT"
        assert item["refresh_token"] == "RT"
        assert item["fitbit_user_id"] == "FB-USER"
        assert item["expires_at"] > int(time.time())

    def test_returns_400_on_token_failure(self, tables):
        with patch.object(oauth, "_token_request", return_value=None):
            r = oauth.callback(USER, {
                "code":          "abc",
                "redirect_uri":  "https://example.com/cb",
                "code_verifier": "v",
            })
        assert r["statusCode"] == 400


# ── crud.get_today / get_status / disconnect / sync_now ───────────────────────

class TestCrud:
    def test_get_today_no_data(self, tables):
        with freeze_time("2026-04-26"):
            r = crud.get_today(USER)
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["synced"] is False
        assert body["log_date"] == "2026-04-26"

    def test_get_today_returns_latest_entry(self, tables):
        tables.Table(DATA_TABLE_NAME).put_item(Item={
            "user_id":   USER,
            "log_date":  "2026-04-25",
            "steps":     1000,
            "synced_at": 100,
        })
        tables.Table(DATA_TABLE_NAME).put_item(Item={
            "user_id":   USER,
            "log_date":  "2026-04-26",
            "steps":     5000,
            "synced_at": 200,
        })
        with freeze_time("2026-04-27"):
            r = crud.get_today(USER)
        body = json.loads(r["body"])
        assert body["log_date"] == "2026-04-26"
        assert body["steps"] == 5000
        assert "user_id" not in body

    def test_get_today_picks_most_recent_synced_at(self, tables):
        # A stale row with a higher log_date but older synced_at should not
        # win over the freshly-synced row from the prior day.
        tables.Table(DATA_TABLE_NAME).put_item(Item={
            "user_id":   USER,
            "log_date":  "2026-04-27",
            "steps":     0,
            "synced_at": 100,
        })
        tables.Table(DATA_TABLE_NAME).put_item(Item={
            "user_id":   USER,
            "log_date":  "2026-04-26",
            "steps":     8868,
            "synced_at": 500,
        })
        r = crud.get_today(USER)
        body = json.loads(r["body"])
        assert body["log_date"] == "2026-04-26"
        assert body["steps"] == 8868

    def test_get_status_disconnected(self, tables):
        r = crud.get_status(USER)
        body = json.loads(r["body"])
        assert body["connected"] is False

    def test_get_status_connected(self, tables):
        tables.Table(TOKENS_TABLE_NAME).put_item(Item={
            "user_id":        USER,
            "access_token":   "AT",
            "fitbit_user_id": "FB-USER",
        })
        r = crud.get_status(USER)
        body = json.loads(r["body"])
        assert body["connected"] is True
        assert body["fitbit_user_id"] == "FB-USER"

    def test_disconnect_when_not_connected(self, tables):
        r = crud.disconnect(USER)
        assert r["statusCode"] == 404

    def test_disconnect_removes_tokens(self, tables):
        tables.Table(TOKENS_TABLE_NAME).put_item(Item={
            "user_id":      USER,
            "access_token": "AT",
        })
        r = crud.disconnect(USER)
        assert r["statusCode"] == 200
        item = tables.Table(TOKENS_TABLE_NAME).get_item(
            Key={"user_id": USER}
        ).get("Item")
        assert item is None

    def test_sync_now_requires_connection(self, tables):
        r = crud.sync_now(USER)
        assert r["statusCode"] == 400

    def test_sync_now_invokes_lambda(self, tables):
        tables.Table(TOKENS_TABLE_NAME).put_item(Item={
            "user_id":      USER,
            "access_token": "AT",
        })
        with patch.object(crud, "_lambda") as mock_lambda:
            r = crud.sync_now(USER)
        assert r["statusCode"] == 200
        mock_lambda.invoke.assert_called_once()
        call_kwargs = mock_lambda.invoke.call_args.kwargs
        assert call_kwargs["InvocationType"] == "Event"
        assert json.loads(call_kwargs["Payload"]) == {"user_ids": [USER]}


class TestLogFood:
    def _connect(self, tables):
        tables.Table(TOKENS_TABLE_NAME).put_item(Item={
            "user_id":       USER,
            "access_token":  "AT",
            "refresh_token": "RT",
            "expires_at":    int(time.time()) + 3600,
        })

    def test_requires_name(self, tables):
        self._connect(tables)
        r = crud.log_food(USER, {"calories": 100})
        assert r["statusCode"] == 400

    def test_requires_connection(self, tables):
        r = crud.log_food(USER, {"name": "Apple", "calories": 95})
        assert r["statusCode"] == 400

    def test_invalid_meal_type(self, tables):
        self._connect(tables)
        r = crud.log_food(USER, {"name": "Apple", "calories": 95, "meal_type_id": 99})
        assert r["statusCode"] == 400

    def test_invalid_calories(self, tables):
        self._connect(tables)
        r = crud.log_food(USER, {"name": "Apple", "calories": -5})
        assert r["statusCode"] == 400

    def test_posts_to_fitbit(self, tables):
        self._connect(tables)
        captured = {}

        class FakeResp:
            def __enter__(self): return self
            def __exit__(self, *a): pass
            def read(self): return b'{"foodLog": {"logId": 123}}'

        def fake_urlopen(req, timeout=10):
            captured["url"]    = req.full_url
            captured["data"]   = req.data
            captured["method"] = req.get_method()
            return FakeResp()

        with patch.object(crud.urllib.request, "urlopen", side_effect=fake_urlopen):
            with patch.object(crud, "_lambda"):  # sync_now invoke
                r = crud.log_food(USER, {"name": "Greek yogurt", "calories": 120, "meal_type_id": 1})

        assert r["statusCode"] == 200
        assert captured["url"].endswith("/foods/log.json")
        assert captured["method"] == "POST"
        assert b"foodName=Greek+yogurt" in captured["data"]
        assert b"calories=120"          in captured["data"]
        assert b"mealTypeId=1"          in captured["data"]


# ── router ────────────────────────────────────────────────────────────────────

class TestRouter:
    def test_unknown_route(self):
        r = router.route("GET /fitbit/unknown", USER, {}, {}, {})
        assert r["statusCode"] == 404

    def test_today_route_dispatches(self, tables):
        with freeze_time("2026-04-26"):
            r = router.route("GET /fitbit/today", USER, {}, {}, {})
        assert r["statusCode"] == 200


# ── sync handler ──────────────────────────────────────────────────────────────

class TestSync:
    def _seed_settings(self, tables, enabled=True):
        tables.Table(SETTINGS_TABLE_NAME).put_item(Item={
            "user_id": USER,
            "fitbit":  {"enabled": enabled},
        })

    def _seed_tokens(self, tables, expires_in=3600):
        tables.Table(TOKENS_TABLE_NAME).put_item(Item={
            "user_id":       USER,
            "access_token":  "AT",
            "refresh_token": "RT",
            "expires_at":    int(time.time()) + expires_in,
            "scope":         "activity sleep",
        })

    def test_finds_enabled_users(self, tables):
        self._seed_settings(tables, enabled=True)
        users = sync_handler._users_with_fitbit_enabled()
        assert users == [USER]

    def test_skips_disabled_users(self, tables):
        self._seed_settings(tables, enabled=False)
        assert sync_handler._users_with_fitbit_enabled() == []

    def test_sync_user_writes_data(self, tables):
        self._seed_tokens(tables)
        fake_summary = {
            "steps":          7500,
            "calories_out":   2200,
            "distance_km":    5.5,
            "active_minutes": 60,
            "calories_in":    1800,
            "weight":         80.5,
            "weight_unit":    "kg",
            "sleep": {
                "duration_min":   480,
                "efficiency":     90,
                "minutes_asleep": 450,
                "minutes_awake":  30,
                "start_time":     "2026-04-26T00:00:00",
                "end_time":       "2026-04-26T08:00:00",
            },
        }
        with patch.object(sync_handler, "_fetch_summary", return_value=fake_summary):
            with freeze_time("2026-04-26"):
                ok = sync_handler._sync_user(USER)
        assert ok is True

        item = tables.Table(DATA_TABLE_NAME).get_item(
            Key={"user_id": USER, "log_date": "2026-04-26"}
        ).get("Item")
        assert item["steps"] == 7500
        assert item["sleep"]["minutes_asleep"] == 450

    def test_sync_user_without_tokens(self, tables):
        assert sync_handler._sync_user(USER) is False

    def test_refresh_when_expired(self, tables):
        self._seed_tokens(tables, expires_in=-100)
        refreshed = {
            "access_token":  "NEW_AT",
            "refresh_token": "NEW_RT",
            "expires_in":    3600,
            "scope":         "activity sleep",
        }
        with patch.object(sync_handler, "_token_request", return_value=refreshed):
            item = tables.Table(TOKENS_TABLE_NAME).get_item(
                Key={"user_id": USER}
            )["Item"]
            token = sync_handler._ensure_fresh_access_token(item)
        assert token == "NEW_AT"

        stored = tables.Table(TOKENS_TABLE_NAME).get_item(
            Key={"user_id": USER}
        )["Item"]
        assert stored["access_token"]  == "NEW_AT"
        assert stored["refresh_token"] == "NEW_RT"

    def test_refresh_failure_returns_none(self, tables):
        self._seed_tokens(tables, expires_in=-100)
        with patch.object(sync_handler, "_token_request", return_value=None):
            item = tables.Table(TOKENS_TABLE_NAME).get_item(
                Key={"user_id": USER}
            )["Item"]
            token = sync_handler._ensure_fresh_access_token(item)
        assert token is None

    def test_lambda_handler_uses_user_ids_from_event(self, tables):
        self._seed_tokens(tables)
        # Disable settings scan path by giving a direct user_ids payload.
        with patch.object(sync_handler, "_fetch_summary", return_value={"steps": 100}):
            with freeze_time("2026-04-26"):
                result = sync_handler.lambda_handler({"user_ids": [USER]}, None)
        assert result == {"synced": 1, "total": 1}

    def test_activity_distance_helper(self):
        distances = [
            {"activity": "tracker", "distance": 1.0},
            {"activity": "total",   "distance": 4.2},
            {"activity": "loggedActivities", "distance": 0.5},
        ]
        assert sync_handler._activity_distance(distances) == 4.2

    def test_activity_distance_handles_missing(self):
        assert sync_handler._activity_distance([]) == 0.0
