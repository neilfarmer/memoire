"""Goals CRUD operations against DynamoDB."""

import os
import uuid
from datetime import datetime, timezone

import boto3
from response import ok, created, no_content, error, not_found
import db

_dynamodb_client = boto3.client("dynamodb")

TABLE_NAME = os.environ["TABLE_NAME"]
SORT_KEY = "goal_id"

VALID_STATUSES = {"active", "completed", "abandoned"}

MAX_TITLE_LEN       = 500
MAX_DESCRIPTION_LEN = 10_000


def _table():
    return db.get_table(TABLE_NAME)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_fields(body: dict) -> str | None:
    if "status" in body and body["status"] not in VALID_STATUSES:
        return f"status must be one of: {', '.join(sorted(VALID_STATUSES))}"
    return None


# ── List ──────────────────────────────────────────────────────────────────────

def list_goals(user_id: str) -> dict:
    goals = db.query_by_user(_table(), user_id)
    return ok(goals)


# ── Create ────────────────────────────────────────────────────────────────────

def create_goal(user_id: str, body: dict) -> dict:
    title = (body.get("title") or "").strip()
    if not title:
        return error("title is required")
    if len(title) > MAX_TITLE_LEN:
        return error(f"title exceeds maximum length of {MAX_TITLE_LEN}")

    description = body.get("description", "")
    if len(description) > MAX_DESCRIPTION_LEN:
        return error(f"description exceeds maximum length of {MAX_DESCRIPTION_LEN}")

    err = _validate_fields(body)
    if err:
        return error(err)

    now = _now()
    goal = {
        "user_id": user_id,
        "goal_id": str(uuid.uuid4()),
        "title": title,
        "description": description,
        "target_date": body.get("target_date"),
        "status": body.get("status", "active"),
        "created_at": now,
        "updated_at": now,
    }

    # Remove None values so DynamoDB doesn't reject them
    goal = {k: v for k, v in goal.items() if v is not None}

    _table().put_item(Item=goal)
    return created(goal)


# ── Get ───────────────────────────────────────────────────────────────────────

def get_goal(user_id: str, goal_id: str) -> dict:
    goal = db.get_item(_table(), user_id, SORT_KEY, goal_id)
    if not goal:
        return not_found("Goal")
    return ok(goal)


# ── Update ────────────────────────────────────────────────────────────────────

def update_goal(user_id: str, goal_id: str, body: dict) -> dict:
    updatable = {"title", "description", "target_date", "status"}
    fields = {k: v for k, v in body.items() if k in updatable}

    if not fields:
        return error("No valid fields provided for update")

    if "title" in fields:
        fields["title"] = fields["title"].strip()
        if not fields["title"]:
            return error("title cannot be empty")
        if len(fields["title"]) > MAX_TITLE_LEN:
            return error(f"title exceeds maximum length of {MAX_TITLE_LEN}")
    if "description" in fields and len(fields["description"]) > MAX_DESCRIPTION_LEN:
        return error(f"description exceeds maximum length of {MAX_DESCRIPTION_LEN}")

    err = _validate_fields(fields)
    if err:
        return error(err)

    fields["updated_at"] = _now()

    # Build a dynamic UpdateExpression
    set_parts = []
    names = {}
    values = {}

    for i, (key, val) in enumerate(fields.items()):
        placeholder_name = f"#f{i}"
        placeholder_val = f":v{i}"
        set_parts.append(f"{placeholder_name} = {placeholder_val}")
        names[placeholder_name] = key
        values[placeholder_val] = val

    try:
        result = _table().update_item(
            Key={"user_id": user_id, SORT_KEY: goal_id},
            UpdateExpression="SET " + ", ".join(set_parts),
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(goal_id)",
            ReturnValues="ALL_NEW",
        )
    except _dynamodb_client.exceptions.ConditionalCheckFailedException:
        return not_found("Goal")

    return ok(result["Attributes"])


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_goal(user_id: str, goal_id: str) -> dict:
    try:
        _table().delete_item(
            Key={"user_id": user_id, SORT_KEY: goal_id},
            ConditionExpression="attribute_exists(goal_id)",
        )
    except _dynamodb_client.exceptions.ConditionalCheckFailedException:
        return not_found("Goal")

    return no_content()
