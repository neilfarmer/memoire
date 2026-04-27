"""Read endpoints + sync trigger for Fitbit data."""

import json
import os
from datetime import date as _date

import boto3

import db
import oauth
from response import ok, error, not_found

DATA_TABLE       = os.environ["FITBIT_DATA_TABLE"]
SYNC_FUNCTION    = os.environ.get("FITBIT_SYNC_FUNCTION", "")

_lambda = boto3.client("lambda")


def _today_iso() -> str:
    return _date.today().isoformat()


def get_today(user_id: str) -> dict:
    log_date = _today_iso()
    item = db.get_table(DATA_TABLE).get_item(
        Key={"user_id": user_id, "log_date": log_date}
    ).get("Item")
    if not item:
        return ok({"log_date": log_date, "synced": False})
    item.pop("user_id", None)
    return ok(item)


def get_status(user_id: str) -> dict:
    tokens = oauth.get_tokens(user_id)
    return ok({
        "connected": bool(tokens),
        "fitbit_user_id": (tokens or {}).get("fitbit_user_id", ""),
        "connected_at":   (tokens or {}).get("connected_at", ""),
    })


def disconnect(user_id: str) -> dict:
    tokens = oauth.get_tokens(user_id)
    if not tokens:
        return not_found("Fitbit connection")
    oauth.delete_tokens(user_id)
    return ok({"disconnected": True})


def sync_now(user_id: str) -> dict:
    """Async-invoke the sync Lambda for a single user."""
    if not SYNC_FUNCTION:
        return error("Sync function not configured", status=503)
    if not oauth.get_tokens(user_id):
        return error("Fitbit not connected", status=400)

    _lambda.invoke(
        FunctionName=SYNC_FUNCTION,
        InvocationType="Event",
        Payload=json.dumps({"user_ids": [user_id]}).encode(),
    )
    return ok({"queued": True})
