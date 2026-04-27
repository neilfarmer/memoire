"""Read endpoints + sync trigger for Fitbit data."""

import json
import os
from datetime import date as _date

import boto3
from boto3.dynamodb.conditions import Key

import db
import oauth
from response import ok, error, not_found

DATA_TABLE       = os.environ["FITBIT_DATA_TABLE"]
SYNC_FUNCTION    = os.environ.get("FITBIT_SYNC_FUNCTION", "")

_lambda = boto3.client("lambda")


def _today_iso() -> str:
    return _date.today().isoformat()


def get_today(user_id: str) -> dict:
    """Return the most recent Fitbit data entry for the user.

    The sync Lambda stores entries keyed by the user's local date (derived
    from their Fitbit profile timezone), not UTC. The latest log_date is
    usually correct, but a stale row from a different day can outrank
    the freshest one lexicographically (e.g. 2026-04-27 zeros vs
    2026-04-26 today data when the user's TZ is behind UTC), so we pull
    the last few entries and pick the one with the highest synced_at.
    """
    resp = db.get_table(DATA_TABLE).query(
        KeyConditionExpression=Key("user_id").eq(user_id),
        ScanIndexForward=False,
        Limit=7,
    )
    items = resp.get("Items") or []
    if not items:
        return ok({"log_date": _today_iso(), "synced": False})
    item = max(items, key=lambda i: int(i.get("synced_at", 0) or 0))
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
