"""Unit tests for lambda/settings/crud.py."""

import json
import os
from unittest.mock import patch, MagicMock

import boto3
import pytest
from moto import mock_aws

from conftest import USER, load_lambda

os.environ["TABLE_NAME"] = "test-settings"

crud = load_lambda("settings", "crud.py")

TABLE = "test-settings"


@pytest.fixture
def tbl():
    with mock_aws():
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        # Settings table has only a partition key (no sort key)
        ddb.create_table(
            TableName=TABLE,
            KeySchema=[{"AttributeName": "user_id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "user_id", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield


# ── get_settings ──────────────────────────────────────────────────────────────

class TestGetSettings:
    def test_returns_defaults_for_new_user(self, tbl):
        r = crud.get_settings(USER)
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert body["dark_mode"] is False
        assert body["ntfy_url"] == ""
        assert body["autosave_seconds"] == 300
        assert body["timezone"] == ""

    def test_returns_merged_defaults_after_partial_update(self, tbl):
        crud.update_settings(USER, {"dark_mode": True})
        r = crud.get_settings(USER)
        body = json.loads(r["body"])
        assert body["dark_mode"] is True
        assert body["autosave_seconds"] == 300  # still default

    def test_user_id_not_in_response(self, tbl):
        body = json.loads(crud.get_settings(USER)["body"])
        assert "user_id" not in body


# ── update_settings ───────────────────────────────────────────────────────────

class TestUpdateSettings:
    def test_updates_dark_mode(self, tbl):
        crud.update_settings(USER, {"dark_mode": True})
        body = json.loads(crud.get_settings(USER)["body"])
        assert body["dark_mode"] is True

    def test_updates_ntfy_url(self, tbl):
        with patch.object(crud.socket, "gethostbyname", return_value="1.2.3.4"):
            crud.update_settings(USER, {"ntfy_url": "https://ntfy.sh/my-topic"})
        body = json.loads(crud.get_settings(USER)["body"])
        assert body["ntfy_url"] == "https://ntfy.sh/my-topic"

    def test_updates_autosave_seconds(self, tbl):
        crud.update_settings(USER, {"autosave_seconds": 60})
        body = json.loads(crud.get_settings(USER)["body"])
        assert body["autosave_seconds"] == 60

    def test_unknown_keys_filtered_out(self, tbl):
        # Should not raise, just ignore unknown keys
        r = crud.update_settings(USER, {"hacker_field": "bad", "dark_mode": True})
        assert r["statusCode"] == 200
        body = json.loads(r["body"])
        assert "hacker_field" not in body

    def test_display_name_persists(self, tbl):
        crud.update_settings(USER, {"display_name": "Alice"})
        body = json.loads(crud.get_settings(USER)["body"])
        assert body["display_name"] == "Alice"

    def test_display_name_in_defaults(self, tbl):
        body = json.loads(crud.get_settings(USER)["body"])
        assert "display_name" in body
        assert body["display_name"] == ""

    def test_empty_body_returns_defaults(self, tbl):
        r = crud.update_settings(USER, {})
        assert r["statusCode"] == 200

    def test_chat_retention_default(self, tbl):
        body = json.loads(crud.get_settings(USER)["body"])
        assert body["chat_retention_days"] == 30

    def test_chat_retention_update(self, tbl):
        crud.update_settings(USER, {"chat_retention_days": 90})
        body = json.loads(crud.get_settings(USER)["body"])
        assert body["chat_retention_days"] == 90

    def test_chat_retention_zero_allowed(self, tbl):
        r = crud.update_settings(USER, {"chat_retention_days": 0})
        assert r["statusCode"] == 200

    def test_chat_retention_negative_rejected(self, tbl):
        r = crud.update_settings(USER, {"chat_retention_days": -1})
        assert r["statusCode"] == 400

    def test_chat_retention_too_large_rejected(self, tbl):
        r = crud.update_settings(USER, {"chat_retention_days": 99999})
        assert r["statusCode"] == 400

    def test_chat_retention_non_integer_rejected(self, tbl):
        r = crud.update_settings(USER, {"chat_retention_days": "forever"})
        assert r["statusCode"] == 400

    def test_user_id_not_in_response(self, tbl):
        crud.update_settings(USER, {"dark_mode": False})
        body = json.loads(crud.get_settings(USER)["body"])
        assert "user_id" not in body


# ── test_notification ─────────────────────────────────────────────────────────

class TestTestNotification:
    def test_no_url_configured_returns_400(self, tbl):
        r = crud.test_notification(USER, {})
        assert r["statusCode"] == 400
        assert "No ntfy URL" in json.loads(r["body"])["error"]

    def test_uses_url_from_body(self, tbl):
        with patch.object(crud.socket, "gethostbyname", return_value="1.2.3.4"), \
             patch.object(crud, "urlopen", return_value=MagicMock()):
            r = crud.test_notification(USER, {"ntfy_url": "https://ntfy.sh/test"})
        assert r["statusCode"] == 200

    def test_uses_saved_url_when_none_in_body(self, tbl):
        with patch.object(crud.socket, "gethostbyname", return_value="1.2.3.4"):
            crud.update_settings(USER, {"ntfy_url": "https://ntfy.sh/saved"})
        with patch.object(crud.socket, "gethostbyname", return_value="1.2.3.4"), \
             patch.object(crud, "urlopen", return_value=MagicMock()):
            r = crud.test_notification(USER, {})
        assert r["statusCode"] == 200

    def test_network_error_returns_400(self, tbl):
        with patch.object(crud.socket, "gethostbyname", return_value="1.2.3.4"), \
             patch.object(crud, "urlopen", side_effect=Exception("connection refused")):
            r = crud.test_notification(USER, {"ntfy_url": "https://ntfy.sh/test"})
        assert r["statusCode"] == 400
        assert "Could not reach" in json.loads(r["body"])["error"]

    def test_http_url_rejected(self, tbl):
        r = crud.test_notification(USER, {"ntfy_url": "http://ntfy.sh/test"})
        assert r["statusCode"] == 400
        assert "HTTPS" in json.loads(r["body"])["error"]

    def test_metadata_endpoint_blocked(self, tbl):
        with patch.object(crud.socket, "gethostbyname", return_value="169.254.169.254"):
            r = crud.test_notification(USER, {"ntfy_url": "https://169.254.169.254/latest/meta-data/"})
        assert r["statusCode"] == 400
        assert "private" in json.loads(r["body"])["error"].lower()

    def test_private_ip_blocked(self, tbl):
        with patch.object(crud.socket, "gethostbyname", return_value="192.168.1.1"):
            r = crud.test_notification(USER, {"ntfy_url": "https://internal.example.com/topic"})
        assert r["statusCode"] == 400

    def test_update_with_ssrf_url_rejected(self, tbl):
        with patch.object(crud.socket, "gethostbyname", return_value="10.0.0.1"):
            r = crud.update_settings(USER, {"ntfy_url": "https://internal.corp/ntfy"})
        assert r["statusCode"] == 400
