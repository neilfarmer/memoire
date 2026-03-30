"""Settings CRUD operations against DynamoDB."""

import os
from urllib.request import Request, urlopen

import db
from response import ok, error

TABLE_NAME = os.environ["TABLE_NAME"]

DEFAULTS = {
    "dark_mode":        False,
    "ntfy_url":         "",
    "autosave_seconds": 300,
    "timezone":         "",
}

ALLOWED_KEYS = set(DEFAULTS.keys())


def _table():
    return db.get_table(TABLE_NAME)


def get_settings(user_id: str) -> dict:
    item = _table().get_item(Key={"user_id": user_id}).get("Item")
    if not item:
        return ok(DEFAULTS)
    item.pop("user_id", None)
    return ok({**DEFAULTS, **item})


def update_settings(user_id: str, body: dict) -> dict:
    fields = {k: v for k, v in body.items() if k in ALLOWED_KEYS}

    if not fields:
        return ok(DEFAULTS)

    set_parts = []
    names     = {}
    values    = {}

    for i, (key, val) in enumerate(fields.items()):
        names[f"#f{i}"]  = key
        values[f":v{i}"] = val
        set_parts.append(f"#f{i} = :v{i}")

    result = _table().update_item(
        Key={"user_id": user_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )

    item = result["Attributes"]
    item.pop("user_id", None)
    return ok({**DEFAULTS, **item})


def test_notification(user_id: str, body: dict) -> dict:
    # Use URL from request body if provided, otherwise fall back to saved setting
    ntfy_url = (body.get("ntfy_url") or "").strip()
    if not ntfy_url:
        item = _table().get_item(Key={"user_id": user_id}).get("Item", {})
        ntfy_url = (item.get("ntfy_url") or "").strip()

    if not ntfy_url:
        return error("No ntfy URL configured")

    try:
        req = Request(
            ntfy_url,
            data=b"Your Memoire notifications are working.",
            headers={"Title": "Memoire test notification", "Priority": "3"},
            method="POST",
        )
        with urlopen(req, timeout=10):
            pass
    except Exception as e:
        return error(f"Could not reach ntfy endpoint: {e}")

    return ok({"sent": True})
