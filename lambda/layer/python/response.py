"""HTTP response helpers shared across all feature Lambdas."""

import json
from decimal import Decimal


def _json_default(obj):
    if isinstance(obj, Decimal):
        f = float(obj)
        return int(f) if f.is_integer() else f
    return str(obj)


def ok(body: dict | list, status: int = 200) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps(body, default=_json_default),
    }


def created(body: dict) -> dict:
    return ok(body, status=201)


def no_content() -> dict:
    return {"statusCode": 204, "body": ""}


def error(message: str, status: int = 400) -> dict:
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"error": message}),
    }


def not_found(resource: str = "Resource") -> dict:
    return error(f"{resource} not found", status=404)


def forbidden(message: str = "Forbidden") -> dict:
    return error(message, status=403)


def server_error(message: str = "Internal server error") -> dict:
    return error(message, status=500)
