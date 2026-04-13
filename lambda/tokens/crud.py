"""Personal Access Token CRUD operations."""

import hashlib
import os
import secrets
import uuid
from datetime import datetime, timezone, timedelta

import boto3
from boto3.dynamodb.conditions import Key

from response import created, no_content, not_found, ok, error

DEFAULT_PAT_EXPIRY_DAYS = 90
MAX_PAT_EXPIRY_DAYS = 365

TABLE_NAME = os.environ["TABLE_NAME"]
SORT_KEY   = "token_id"

_dynamodb = boto3.resource("dynamodb")


def _table():
    return _dynamodb.Table(TABLE_NAME)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _generate_pat() -> str:
    """Generate a new personal access token with the pat_ prefix."""
    return "pat_" + secrets.token_urlsafe(32)


def list_tokens(user_id: str) -> dict:
    result = _table().query(
        KeyConditionExpression=Key("user_id").eq(user_id)
    )
    items = result.get("Items", [])
    # Never expose token_hash to the client
    safe = [{k: v for k, v in item.items() if k != "token_hash"} for item in items]
    return ok(safe)


def create_token(user_id: str, body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        return error("name is required")
    if len(name) > 100:
        return error("name must be 100 characters or fewer")

    # Expiry: default 90 days, max 365 days, 0 means no expiry
    expiry_days = body.get("expiry_days", DEFAULT_PAT_EXPIRY_DAYS)
    try:
        expiry_days = int(expiry_days)
    except (ValueError, TypeError):
        expiry_days = DEFAULT_PAT_EXPIRY_DAYS
    if expiry_days < 0:
        return error("expiry_days must be 0 (no expiry) or a positive number")
    if expiry_days > MAX_PAT_EXPIRY_DAYS:
        return error(f"expiry_days must be {MAX_PAT_EXPIRY_DAYS} or fewer")

    plaintext  = _generate_pat()
    token_hash = hashlib.sha256(plaintext.encode()).hexdigest()
    token_id   = str(uuid.uuid4())
    now        = _now()

    item = {
        "user_id":    user_id,
        "token_id":   token_id,
        "token_hash": token_hash,
        "name":       name,
        "created_at": now,
    }

    if expiry_days > 0:
        expires_at = (datetime.now(timezone.utc) + timedelta(days=expiry_days)).isoformat()
        item["expires_at"] = expires_at

    _table().put_item(Item=item)

    # Return the plaintext token exactly once — it is never stored
    response_item = {k: v for k, v in item.items() if k != "token_hash"}
    response_item["token"] = plaintext
    return created(response_item)


def delete_token(user_id: str, token_id: str) -> dict:
    table  = _table()
    result = table.get_item(Key={"user_id": user_id, "token_id": token_id})
    if not result.get("Item"):
        return not_found("Token")
    table.delete_item(Key={"user_id": user_id, "token_id": token_id})
    return no_content()
