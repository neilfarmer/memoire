"""Note CRUD for the notes Lambda."""

import os
import re
import uuid

import boto3
import db
from response import ok, created, no_content, error, not_found
from utils import now_iso, parse_tags, build_update_expression

NOTES_TABLE     = os.environ["NOTES_TABLE"]
FOLDERS_TABLE   = os.environ["FOLDERS_TABLE"]
FRONTEND_BUCKET = os.environ["FRONTEND_BUCKET"]

_s3 = boto3.client("s3")
PREVIEW_LEN   = 200

MAX_TITLE_LEN = 500
MAX_BODY_LEN  = 100_000


def _table():
    return db.get_table(NOTES_TABLE)


def _summary(note: dict) -> dict:
    body    = note.get("body", "")
    preview = body[:PREVIEW_LEN] + ("..." if len(body) > PREVIEW_LEN else "")
    return {k: v for k, v in note.items() if k != "body"} | {"preview": preview}


# ── List all notes (summaries) ────────────────────────────────────────────────

def list_notes(user_id: str) -> dict:
    notes = db.query_by_user(_table(), user_id)
    notes.sort(key=lambda n: n.get("updated_at", ""), reverse=True)
    return ok([_summary(n) for n in notes])


# ── Search ────────────────────────────────────────────────────────────────────

def search_notes(user_id: str, q: str) -> dict:
    notes   = db.query_by_user(_table(), user_id)
    q_lower = q.lower()

    def matches(n):
        return (
            q_lower in n.get("title", "").lower()
            or q_lower in n.get("body", "").lower()
            or any(q_lower in t.lower() for t in (n.get("tags") or []))
        )

    results = sorted(
        [_summary(n) for n in notes if matches(n)],
        key=lambda n: n.get("updated_at", ""),
        reverse=True,
    )
    return ok(results)


# ── Get ───────────────────────────────────────────────────────────────────────

def get_note(user_id: str, note_id: str) -> dict:
    note = db.get_item(_table(), user_id, "note_id", note_id)
    if not note:
        return not_found("Note")
    return ok(note)


# ── Create ────────────────────────────────────────────────────────────────────

def create_note(user_id: str, body: dict) -> dict:
    folder_id = body.get("folder_id")
    if not folder_id:
        return error("folder_id is required")

    folder = db.get_item(db.get_table(FOLDERS_TABLE), user_id, "folder_id", folder_id)
    if not folder:
        return not_found("Folder")

    title = (body.get("title") or "").strip()
    if len(title) > MAX_TITLE_LEN:
        return error(f"title exceeds maximum length of {MAX_TITLE_LEN}")
    note_body = body.get("body", "")
    if len(note_body) > MAX_BODY_LEN:
        return error(f"body exceeds maximum length of {MAX_BODY_LEN}")

    now  = now_iso()
    note = {
        "user_id":    user_id,
        "note_id":    str(uuid.uuid4()),
        "folder_id":  folder_id,
        "title":      title,
        "body":       note_body,
        "tags":       parse_tags(body.get("tags")),
        "created_at": now,
        "updated_at": now,
    }
    _table().put_item(Item=note)
    return created(note)


# ── Update ────────────────────────────────────────────────────────────────────

def update_note(user_id: str, note_id: str, body: dict) -> dict:
    note = db.get_item(_table(), user_id, "note_id", note_id)
    if not note:
        return not_found("Note")

    updatable = {"title", "body", "tags", "folder_id"}
    fields    = {k: v for k, v in body.items() if k in updatable}

    if "tags" in fields:
        fields["tags"] = parse_tags(fields["tags"])
    if "title" in fields:
        fields["title"] = (fields["title"] or "").strip()
        if len(fields["title"]) > MAX_TITLE_LEN:
            return error(f"title exceeds maximum length of {MAX_TITLE_LEN}")
    if "body" in fields and len(fields["body"]) > MAX_BODY_LEN:
        return error(f"body exceeds maximum length of {MAX_BODY_LEN}")
    if "folder_id" in fields:
        folder = db.get_item(db.get_table(FOLDERS_TABLE), user_id, "folder_id", fields["folder_id"])
        if not folder:
            return not_found("Folder")

    fields["updated_at"] = now_iso()

    update_expr, names, values = build_update_expression(fields)

    result = _table().update_item(
        Key={"user_id": user_id, "note_id": note_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return ok(result["Attributes"])


# ── Delete ────────────────────────────────────────────────────────────────────

def _delete_note_s3_assets(user_id: str, note: dict) -> None:
    """Delete all S3 objects associated with a note: attachment prefix + inline images."""
    note_id = note["note_id"]
    keys: list[str] = []

    # Attachments stored under note-attachments/{user_id}/{note_id}/
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=FRONTEND_BUCKET, Prefix=f"note-attachments/{user_id}/{note_id}/"):
        keys.extend(obj["Key"] for obj in page.get("Contents", []))

    # Inline images embedded in the note body as S3 key paths
    body = note.get("body", "")
    keys.extend(re.findall(rf"note-images/{re.escape(user_id)}/[^\s\)\"\'\]]+", body))

    # Batch delete in chunks of 1,000 (S3 delete_objects limit)
    for i in range(0, len(keys), 1000):
        chunk = [{"Key": k} for k in keys[i : i + 1000]]
        if chunk:
            _s3.delete_objects(Bucket=FRONTEND_BUCKET, Delete={"Objects": chunk})


def delete_note(user_id: str, note_id: str) -> dict:
    note = db.get_item(_table(), user_id, "note_id", note_id)
    if not note:
        return not_found("Note")
    _delete_note_s3_assets(user_id, note)
    _table().delete_item(Key={"user_id": user_id, "note_id": note_id})
    return no_content()
