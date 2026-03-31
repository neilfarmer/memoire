#!/usr/bin/env python3
"""
Unit tests for lambda/auth/handler.py.

Tests all three endpoints (callback, refresh, logout) with mocked Cognito
responses. No deployment or network access required.

Usage:
    python -m pytest tests/test_auth_handler.py -v
    # or
    python tests/test_auth_handler.py
"""

import base64
import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

# Point at the Lambda source without installing it as a package
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "lambda", "auth"))

os.environ.setdefault("AUTH_DOMAIN", "https://example.auth.us-east-1.amazoncognito.com")
os.environ.setdefault("COGNITO_CLIENT_ID", "test-client-id")

import handler  # noqa: E402  (imported after env vars are set)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_jwt(payload: dict) -> str:
    """Build a minimal (unsigned) JWT-shaped string for testing."""
    header  = base64.urlsafe_b64encode(b'{"alg":"RS256"}').rstrip(b"=").decode()
    body    = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{header}.{body}.fakesig"


def _event(path: str, body: dict = None, cookies: list = None) -> dict:
    return {
        "requestContext": {"http": {"method": "POST", "path": path}},
        "body": json.dumps(body) if body else None,
        "cookies": cookies or [],
    }


def _mock_cognito_ok(id_token: str, refresh_token: str = "rt_test"):
    """Return a context manager that makes urlopen return a successful token response."""
    resp_body = json.dumps({"id_token": id_token, "refresh_token": refresh_token}).encode()
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = resp_body
    return patch("urllib.request.urlopen", return_value=mock_resp)


def _mock_cognito_fail(http_code: int = 400):
    """Return a context manager that makes urlopen raise an HTTPError."""
    import urllib.error
    exc = urllib.error.HTTPError(url="", code=http_code, msg="Bad Request", hdrs=None, fp=None)
    return patch("urllib.request.urlopen", side_effect=exc)


SAMPLE_JWT = _make_jwt({"email": "user@example.com", "sub": "sub-123", "exp": 9999999999})


# ── /auth/callback tests ──────────────────────────────────────────────────────

class TestCallback(unittest.TestCase):

    def test_missing_code_returns_400(self):
        r = handler.lambda_handler(_event("/auth/callback", {"redirect_uri": "https://x.com/", "code_verifier": "v"}), None)
        self.assertEqual(r["statusCode"], 400)
        self.assertIn("required", json.loads(r["body"])["error"])

    def test_missing_redirect_uri_returns_400(self):
        r = handler.lambda_handler(_event("/auth/callback", {"code": "c", "code_verifier": "v"}), None)
        self.assertEqual(r["statusCode"], 400)

    def test_missing_code_verifier_returns_400(self):
        r = handler.lambda_handler(_event("/auth/callback", {"code": "c", "redirect_uri": "https://x.com/"}), None)
        self.assertEqual(r["statusCode"], 400)

    def test_invalid_json_body_returns_400(self):
        event = _event("/auth/callback")
        event["body"] = "not-json"
        r = handler.lambda_handler(event, None)
        self.assertEqual(r["statusCode"], 400)

    def test_cognito_failure_returns_400(self):
        with _mock_cognito_fail():
            r = handler.lambda_handler(_event("/auth/callback", {
                "code": "authcode", "redirect_uri": "https://x.com/", "code_verifier": "verifier",
            }), None)
        self.assertEqual(r["statusCode"], 400)
        self.assertIn("failed", json.loads(r["body"])["error"])

    def test_success_sets_httponly_cookies(self):
        with _mock_cognito_ok(SAMPLE_JWT):
            r = handler.lambda_handler(_event("/auth/callback", {
                "code": "authcode", "redirect_uri": "https://x.com/", "code_verifier": "verifier",
            }), None)

        self.assertEqual(r["statusCode"], 200)

        cookies = r.get("cookies", [])
        access_cookie  = next((c for c in cookies if c.startswith("memoire_token=")), None)
        refresh_cookie = next((c for c in cookies if c.startswith("memoire_refresh=")), None)

        self.assertIsNotNone(access_cookie,  "memoire_token cookie missing")
        self.assertIsNotNone(refresh_cookie, "memoire_refresh cookie missing")
        self.assertIn("HttpOnly",  access_cookie)
        self.assertIn("Secure",    access_cookie)
        self.assertIn("SameSite=None", access_cookie)
        self.assertIn("HttpOnly",  refresh_cookie)

    def test_success_returns_user_info(self):
        with _mock_cognito_ok(SAMPLE_JWT):
            r = handler.lambda_handler(_event("/auth/callback", {
                "code": "authcode", "redirect_uri": "https://x.com/", "code_verifier": "verifier",
            }), None)

        body = json.loads(r["body"])
        self.assertEqual(body["email"], "user@example.com")
        self.assertEqual(body["sub"],   "sub-123")
        self.assertEqual(body["exp"],   9999999999)

    def test_no_id_token_in_cognito_response_returns_400(self):
        resp_body = json.dumps({"refresh_token": "rt"}).encode()
        mock_resp = MagicMock()
        mock_resp.__enter__ = lambda s: s
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.read.return_value = resp_body
        with patch("urllib.request.urlopen", return_value=mock_resp):
            r = handler.lambda_handler(_event("/auth/callback", {
                "code": "c", "redirect_uri": "https://x.com/", "code_verifier": "v",
            }), None)
        self.assertEqual(r["statusCode"], 400)


# ── /auth/refresh tests ───────────────────────────────────────────────────────

class TestRefresh(unittest.TestCase):

    def test_no_refresh_cookie_returns_401(self):
        r = handler.lambda_handler(_event("/auth/refresh"), None)
        self.assertEqual(r["statusCode"], 401)

    def test_cognito_failure_returns_401(self):
        event = _event("/auth/refresh", cookies=["memoire_refresh=rt_old"])
        with _mock_cognito_fail():
            r = handler.lambda_handler(event, None)
        self.assertEqual(r["statusCode"], 401)

    def test_success_updates_access_cookie(self):
        new_jwt = _make_jwt({"email": "user@example.com", "sub": "sub-123", "exp": 9999999998})
        event = _event("/auth/refresh", cookies=["memoire_refresh=rt_good"])
        with _mock_cognito_ok(new_jwt):
            r = handler.lambda_handler(event, None)

        self.assertEqual(r["statusCode"], 200)
        cookies = r.get("cookies", [])
        access_cookie = next((c for c in cookies if c.startswith("memoire_token=")), None)
        self.assertIsNotNone(access_cookie)
        self.assertIn("HttpOnly", access_cookie)
        # Refresh token should NOT be rotated (Cognito doesn't return one on refresh)
        refresh_cookie = next((c for c in cookies if c.startswith("memoire_refresh=")), None)
        self.assertIsNone(refresh_cookie, "Refresh cookie should not be set on token refresh")

    def test_success_returns_user_info(self):
        new_jwt = _make_jwt({"email": "user@example.com", "sub": "sub-123", "exp": 9999999998})
        event = _event("/auth/refresh", cookies=["memoire_refresh=rt_good"])
        with _mock_cognito_ok(new_jwt):
            r = handler.lambda_handler(event, None)

        body = json.loads(r["body"])
        self.assertIn("email", body)
        self.assertIn("sub", body)


# ── /auth/logout tests ────────────────────────────────────────────────────────

class TestLogout(unittest.TestCase):

    def test_logout_returns_200(self):
        r = handler.lambda_handler(_event("/auth/logout"), None)
        self.assertEqual(r["statusCode"], 200)

    def test_logout_clears_access_cookie(self):
        r = handler.lambda_handler(_event("/auth/logout"), None)
        cookies = r.get("cookies", [])
        access_cookie = next((c for c in cookies if c.startswith("memoire_token=")), None)
        self.assertIsNotNone(access_cookie)
        self.assertIn("Max-Age=0", access_cookie)

    def test_logout_clears_refresh_cookie(self):
        r = handler.lambda_handler(_event("/auth/logout"), None)
        cookies = r.get("cookies", [])
        refresh_cookie = next((c for c in cookies if c.startswith("memoire_refresh=")), None)
        self.assertIsNotNone(refresh_cookie)
        self.assertIn("Max-Age=0", refresh_cookie)

    def test_logout_cookies_are_httponly(self):
        r = handler.lambda_handler(_event("/auth/logout"), None)
        for cookie in r.get("cookies", []):
            self.assertIn("HttpOnly", cookie, f"Cookie missing HttpOnly: {cookie}")


# ── Unknown route tests ───────────────────────────────────────────────────────

class TestRouting(unittest.TestCase):

    def test_unknown_path_returns_404(self):
        r = handler.lambda_handler(_event("/auth/unknown"), None)
        self.assertEqual(r["statusCode"], 404)


# ── _extract_user_info unit tests ─────────────────────────────────────────────

class TestExtractUserInfo(unittest.TestCase):

    def test_extracts_email_sub_exp(self):
        jwt = _make_jwt({"email": "a@b.com", "sub": "u1", "exp": 12345})
        info = handler._extract_user_info(jwt)
        self.assertEqual(info["email"], "a@b.com")
        self.assertEqual(info["sub"],   "u1")
        self.assertEqual(info["exp"],   12345)

    def test_falls_back_to_cognito_username(self):
        jwt = _make_jwt({"cognito:username": "alice", "sub": "u2", "exp": 0})
        info = handler._extract_user_info(jwt)
        self.assertEqual(info["email"], "alice")

    def test_malformed_jwt_returns_empty(self):
        info = handler._extract_user_info("not.a.jwt")
        self.assertEqual(info, {"email": "", "sub": "", "exp": 0})


# ── _get_cookie unit tests ────────────────────────────────────────────────────

class TestGetCookie(unittest.TestCase):

    def test_finds_named_cookie(self):
        event = {"cookies": ["memoire_token=abc123; Path=/"]}
        self.assertEqual(handler._get_cookie(event, "memoire_token"), "abc123")

    def test_returns_none_when_absent(self):
        event = {"cookies": ["other=val"]}
        self.assertIsNone(handler._get_cookie(event, "memoire_token"))

    def test_returns_none_with_no_cookies(self):
        event = {"cookies": []}
        self.assertIsNone(handler._get_cookie(event, "memoire_token"))

    def test_handles_multiple_cookies(self):
        event = {"cookies": ["a=1; b=2", "memoire_token=tok; HttpOnly"]}
        self.assertEqual(handler._get_cookie(event, "memoire_token"), "tok")


if __name__ == "__main__":
    unittest.main(verbosity=2)
