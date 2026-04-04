"""Folder CRUD for the tasks Lambda."""

import os
import uuid

import db
from response import ok, created, no_content, error, not_found
from utils import now_iso

FOLDERS_TABLE = os.environ["FOLDERS_TABLE"]
TASKS_TABLE   = os.environ["TABLE_NAME"]


def _table():
    return db.get_table(FOLDERS_TABLE)


def list_folders(user_id: str) -> dict:
    items = db.query_by_user(_table(), user_id)
    if not items:
        inbox = _create_inbox(user_id)
        items = [inbox]
    return ok(items)


def _create_inbox(user_id: str) -> dict:
    folder = {
        "user_id":    user_id,
        "folder_id":  str(uuid.uuid4()),
        "name":       "Inbox",
        "created_at": now_iso(),
    }
    _table().put_item(Item=folder)
    return folder


def create_folder(user_id: str, body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        return error("name is required")

    folder = {
        "user_id":    user_id,
        "folder_id":  str(uuid.uuid4()),
        "name":       name,
        "created_at": now_iso(),
    }
    _table().put_item(Item=folder)
    return created(folder)


def update_folder(user_id: str, folder_id: str, body: dict) -> dict:
    folder = db.get_item(_table(), user_id, "folder_id", folder_id)
    if not folder:
        return not_found("Folder")

    name = (body.get("name") or "").strip()
    if not name:
        return error("name is required")

    result = _table().update_item(
        Key={"user_id": user_id, "folder_id": folder_id},
        UpdateExpression="SET #n = :n",
        ExpressionAttributeNames={"#n": "name"},
        ExpressionAttributeValues={":n": name},
        ReturnValues="ALL_NEW",
    )
    return ok(result["Attributes"])


def delete_folder(user_id: str, folder_id: str) -> dict:
    folder = db.get_item(_table(), user_id, "folder_id", folder_id)
    if not folder:
        return not_found("Folder")

    # Delete all tasks in this folder
    tasks_table     = db.get_table(TASKS_TABLE)
    all_tasks       = db.query_by_user(tasks_table, user_id)
    tasks_to_delete = [t for t in all_tasks if t.get("folder_id") == folder_id]

    with tasks_table.batch_writer() as batch:
        for task in tasks_to_delete:
            batch.delete_item(Key={"user_id": user_id, "task_id": task["task_id"]})

    _table().delete_item(Key={"user_id": user_id, "folder_id": folder_id})
    return no_content()
