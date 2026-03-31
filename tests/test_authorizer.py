#!/usr/bin/env python3
"""
Unit tests for lambda/authorizer/handler.py — specifically the new
_extract_token() function that reads from Cookie or Authorization header.

No deployment or network access required.

Usage:
    python -m pytest tests/test_authorizer.py -v
    # or
    python tests/test_authorizer.py
"""

import importlib.util
import os
import sys
import unittest
from unittest.mock import MagicMock, patch

os.environ.setdefault("TOKENS_TABLE",    "test-tokens-table")
os.environ.setdefault("JWKS_URI",        "https://cognito-idp.us-east-1.amazonaws.com/pool/.well-known/jwks.json")
os.environ.setdefault("JWT_ISSUER",      "https://cognito-idp.us-east-1.amazonaws.com/pool")
os.environ.setdefault("JWT_AUDIENCE",    "test-client-id")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

# The authorizer imports boto3 and boto3.dynamodb.conditions at module level
# and creates a DynamoDB resource. Mock both so the tests need no AWS credentials.
_mock_boto3 = MagicMock()
_mock_conditions = MagicMock()
with patch.dict(sys.modules, {"boto3": _mock_boto3, "boto3.dynamodb": _mock_boto3.dynamodb, "boto3.dynamodb.conditions": _mock_conditions}):
    _auth_handler_path = os.path.join(os.path.dirname(__file__), "..", "lambda", "authorizer", "handler.py")
    _spec = importlib.util.spec_from_file_location("authorizer_handler", _auth_handler_path)
    handler = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(handler)


class TestExtractToken(unittest.TestCase):
    """_extract_token should prefer Authorization header, fall back to Cookie."""

    # ── Authorization header ──────────────────────────────────────────────────

    def test_bare_token_in_authorization(self):
        event = {"headers": {"authorization": "eyJhbGciOiJSUzI1NiJ9.payload.sig"}}
        self.assertEqual(handler._extract_token(event), "eyJhbGciOiJSUzI1NiJ9.payload.sig")

    def test_bearer_prefix_stripped(self):
        event = {"headers": {"authorization": "Bearer eyJtoken"}}
        self.assertEqual(handler._extract_token(event), "eyJtoken")

    def test_bearer_prefix_case_insensitive(self):
        event = {"headers": {"authorization": "BEARER eyJtoken"}}
        self.assertEqual(handler._extract_token(event), "eyJtoken")

    def test_pat_token_in_authorization(self):
        event = {"headers": {"authorization": "pat_abc123"}}
        self.assertEqual(handler._extract_token(event), "pat_abc123")

    def test_authorization_takes_priority_over_cookie(self):
        event = {"headers": {
            "authorization": "pat_from_header",
            "cookie": "memoire_token=jwt_from_cookie",
        }}
        self.assertEqual(handler._extract_token(event), "pat_from_header")

    # ── Cookie header ─────────────────────────────────────────────────────────

    def test_token_from_cookie(self):
        event = {"headers": {"cookie": "memoire_token=eyJjb29raWU"}}
        self.assertEqual(handler._extract_token(event), "eyJjb29raWU")

    def test_token_from_cookie_among_others(self):
        event = {"headers": {"cookie": "theme=dark; memoire_token=eyJtoken; other=val"}}
        self.assertEqual(handler._extract_token(event), "eyJtoken")

    def test_cookie_header_capitalized(self):
        event = {"headers": {"Cookie": "memoire_token=eyJcap"}}
        self.assertEqual(handler._extract_token(event), "eyJcap")

    def test_no_memoire_token_cookie_returns_empty(self):
        event = {"headers": {"cookie": "theme=dark; session=abc"}}
        self.assertEqual(handler._extract_token(event), "")

    # ── Missing / empty ───────────────────────────────────────────────────────

    def test_no_headers_returns_empty(self):
        self.assertEqual(handler._extract_token({}), "")

    def test_empty_authorization_falls_through_to_cookie(self):
        event = {"headers": {
            "authorization": "",
            "cookie": "memoire_token=fallback",
        }}
        self.assertEqual(handler._extract_token(event), "fallback")

    def test_bearer_only_no_token_falls_through_to_cookie(self):
        event = {"headers": {
            "authorization": "Bearer ",
            "cookie": "memoire_token=fallback",
        }}
        self.assertEqual(handler._extract_token(event), "fallback")

    def test_no_token_anywhere_returns_empty(self):
        event = {"headers": {"cookie": "theme=dark"}}
        self.assertEqual(handler._extract_token(event), "")


if __name__ == "__main__":
    unittest.main(verbosity=2)
