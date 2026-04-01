"""Unit tests for lambda/layer/python/response.py."""

import json
import os
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "lambda" / "layer" / "python"))

from response import ok, created, no_content, error, not_found, server_error, _json_default


class TestOk:
    def test_status_200(self):
        r = ok({"a": 1})
        assert r["statusCode"] == 200

    def test_body_serialised(self):
        r = ok({"key": "val"})
        assert json.loads(r["body"]) == {"key": "val"}

    def test_list_body(self):
        r = ok([1, 2, 3])
        assert json.loads(r["body"]) == [1, 2, 3]

    def test_content_type_header(self):
        r = ok({})
        assert r["headers"]["Content-Type"] == "application/json"

    def test_custom_status(self):
        r = ok({}, status=202)
        assert r["statusCode"] == 202

    def test_decimal_int_serialised_as_int(self):
        r = ok({"n": Decimal("42.0")})
        body = json.loads(r["body"])
        assert body["n"] == 42
        assert isinstance(body["n"], int)

    def test_decimal_float_serialised_as_float(self):
        r = ok({"n": Decimal("3.14")})
        body = json.loads(r["body"])
        assert abs(body["n"] - 3.14) < 1e-6

    def test_non_serialisable_falls_back_to_str(self):
        r = ok({"v": object.__new__(object)})
        body = json.loads(r["body"])
        assert isinstance(body["v"], str)


class TestCreated:
    def test_status_201(self):
        r = created({"id": "x"})
        assert r["statusCode"] == 201

    def test_body_serialised(self):
        r = created({"id": "x"})
        assert json.loads(r["body"])["id"] == "x"


class TestNoContent:
    def test_status_204(self):
        assert no_content()["statusCode"] == 204

    def test_empty_body(self):
        assert no_content()["body"] == ""


class TestError:
    def test_status_400_default(self):
        r = error("bad")
        assert r["statusCode"] == 400

    def test_custom_status(self):
        r = error("bad", status=422)
        assert r["statusCode"] == 422

    def test_error_key_in_body(self):
        r = error("something wrong")
        assert json.loads(r["body"])["error"] == "something wrong"


class TestNotFound:
    def test_status_404(self):
        assert not_found()["statusCode"] == 404

    def test_default_message(self):
        body = json.loads(not_found()["body"])
        assert "not found" in body["error"].lower()

    def test_custom_resource(self):
        body = json.loads(not_found("Task")["body"])
        assert "Task" in body["error"]


class TestServerError:
    def test_status_500(self):
        assert server_error()["statusCode"] == 500

    def test_default_message(self):
        body = json.loads(server_error()["body"])
        assert "error" in body

    def test_custom_message(self):
        body = json.loads(server_error("boom")["body"])
        assert body["error"] == "boom"
