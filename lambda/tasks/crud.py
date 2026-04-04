"""Tasks CRUD operations against DynamoDB."""

import os
import uuid

import boto3
from response import ok, created, no_content, error, not_found
import db
from utils import now_iso, build_update_expression

_dynamodb_client = boto3.client("dynamodb")

TABLE_NAME = os.environ["TABLE_NAME"]
SORT_KEY = "task_id"

VALID_STATUSES    = {"todo", "in_progress", "done"}
VALID_PRIORITIES  = {"low", "medium", "high"}
VALID_BEFORE_DUE  = {"1h", "1d", "3d"}
VALID_RECURRING   = {"1h", "1d", "1w"}

MAX_TITLE_LEN       = 500
MAX_DESCRIPTION_LEN = 10_000


def _table():
    return db.get_table(TABLE_NAME)


def _validate_fields(body: dict) -> str | None:
    """Return an error message if any provided fields are invalid, else None."""
    if "status" in body and body["status"] not in VALID_STATUSES:
        return f"status must be one of: {', '.join(sorted(VALID_STATUSES))}"
    if "priority" in body and body["priority"] not in VALID_PRIORITIES:
        return f"priority must be one of: {', '.join(sorted(VALID_PRIORITIES))}"
    if "notifications" in body and body["notifications"] is not None:
        n = body["notifications"]
        if not isinstance(n, dict):
            return "notifications must be an object"
        before = n.get("before_due") or []
        if not isinstance(before, list) or not all(v in VALID_BEFORE_DUE for v in before):
            return f"notifications.before_due values must be from: {', '.join(sorted(VALID_BEFORE_DUE))}"
        recurring = n.get("recurring")
        if recurring and recurring not in VALID_RECURRING:
            return f"notifications.recurring must be one of: {', '.join(sorted(VALID_RECURRING))}"
    return None


# ── List ──────────────────────────────────────────────────────────────────────

def list_tasks(user_id: str) -> dict:
    tasks = db.query_by_user(_table(), user_id)
    return ok(tasks)


# ── Create ────────────────────────────────────────────────────────────────────

def create_task(user_id: str, body: dict) -> dict:
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

    now = now_iso()
    task = {
        "user_id": user_id,
        "task_id": str(uuid.uuid4()),
        "title": title,
        "description": description,
        "status": body.get("status", "todo"),
        "priority": body.get("priority", "medium"),
        "due_date": body.get("due_date"),
        "notifications": body.get("notifications"),
        "folder_id": body.get("folder_id"),
        "created_at": now,
        "updated_at": now,
    }

    # Remove None values so DynamoDB doesn't reject them
    task = {k: v for k, v in task.items() if v is not None}

    _table().put_item(Item=task)
    return created(task)


# ── Get ───────────────────────────────────────────────────────────────────────

def get_task(user_id: str, task_id: str) -> dict:
    task = db.get_item(_table(), user_id, SORT_KEY, task_id)
    if not task:
        return not_found("Task")
    return ok(task)


# ── Update ────────────────────────────────────────────────────────────────────

def update_task(user_id: str, task_id: str, body: dict) -> dict:
    updatable = {"title", "description", "status", "priority", "due_date", "notifications", "folder_id"}
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

    fields["updated_at"] = now_iso()
    if "notifications" in fields:
        fields["notification_sent"] = {}

    update_expr, names, values = build_update_expression(fields)

    try:
        result = _table().update_item(
            Key={"user_id": user_id, SORT_KEY: task_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(task_id)",
            ReturnValues="ALL_NEW",
        )
    except _dynamodb_client.exceptions.ConditionalCheckFailedException:
        return not_found("Task")

    return ok(result["Attributes"])


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_task(user_id: str, task_id: str) -> dict:
    try:
        _table().delete_item(
            Key={"user_id": user_id, SORT_KEY: task_id},
            ConditionExpression="attribute_exists(task_id)",
        )
    except _dynamodb_client.exceptions.ConditionalCheckFailedException:
        return not_found("Task")

    return no_content()
