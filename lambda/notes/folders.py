"""Folder CRUD for the notes Lambda."""

import os
import uuid
from datetime import datetime, timezone

import db
import note_crud
from response import ok, created, no_content, error, not_found

FOLDERS_TABLE = os.environ["FOLDERS_TABLE"]
NOTES_TABLE   = os.environ["NOTES_TABLE"]


def _table():
    return db.get_table(FOLDERS_TABLE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ── List (auto-creates Inbox on first use) ────────────────────────────────────

def list_folders(user_id: str) -> dict:
    items = db.query_by_user(_table(), user_id)
    if not items:
        inbox = _create_inbox(user_id)
        items = [inbox]
    return ok(items)


def _create_inbox(user_id: str) -> dict:
    now    = _now()
    folder = {
        "user_id":    user_id,
        "folder_id":  str(uuid.uuid4()),
        "name":       "Inbox",
        "parent_id":  None,
        "created_at": now,
    }
    _table().put_item(Item={k: v for k, v in folder.items() if v is not None})
    return folder


# ── Create ────────────────────────────────────────────────────────────────────

def create_folder(user_id: str, body: dict) -> dict:
    name = (body.get("name") or "").strip()
    if not name:
        return error("name is required")

    parent_id = body.get("parent_id")
    if parent_id:
        parent = db.get_item(_table(), user_id, "folder_id", parent_id)
        if not parent:
            return not_found("Parent folder")

    folder = {
        "user_id":    user_id,
        "folder_id":  str(uuid.uuid4()),
        "name":       name,
        "parent_id":  parent_id,
        "created_at": _now(),
    }
    _table().put_item(Item={k: v for k, v in folder.items() if v is not None})
    return created(folder)


# ── Update (rename) ───────────────────────────────────────────────────────────

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


# ── Delete (recursive) ────────────────────────────────────────────────────────

def delete_folder(user_id: str, folder_id: str) -> dict:
    folder = db.get_item(_table(), user_id, "folder_id", folder_id)
    if not folder:
        return not_found("Folder")

    all_folders = db.query_by_user(_table(), user_id)
    ids_to_delete = _subtree_ids(all_folders, folder_id)

    # Delete all notes in every folder in the subtree
    all_notes = db.query_by_user(db.get_table(NOTES_TABLE), user_id)
    notes_to_delete = [n for n in all_notes if n.get("folder_id") in ids_to_delete]

    notes_table = db.get_table(NOTES_TABLE)
    with notes_table.batch_writer() as batch:
        for note in notes_to_delete:
            batch.delete_item(Key={"user_id": user_id, "note_id": note["note_id"]})

    with _table().batch_writer() as batch:
        for fid in ids_to_delete:
            batch.delete_item(Key={"user_id": user_id, "folder_id": fid})

    return no_content()


def _subtree_ids(all_folders: list, root_id: str) -> set:
    ids = {root_id}
    for f in all_folders:
        if f.get("parent_id") == root_id:
            ids |= _subtree_ids(all_folders, f["folder_id"])
    return ids
