"""Note CRUD for the notes Lambda."""

import os
import uuid
from datetime import datetime, timezone

import db
from response import ok, created, no_content, error, not_found

NOTES_TABLE   = os.environ["NOTES_TABLE"]
FOLDERS_TABLE = os.environ["FOLDERS_TABLE"]
PREVIEW_LEN   = 200


def _table():
    return db.get_table(NOTES_TABLE)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_tags(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [t.strip() for t in raw if t.strip()]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


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

    now  = _now()
    note = {
        "user_id":    user_id,
        "note_id":    str(uuid.uuid4()),
        "folder_id":  folder_id,
        "title":      (body.get("title") or "").strip(),
        "body":       body.get("body", ""),
        "tags":       _parse_tags(body.get("tags")),
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
        fields["tags"] = _parse_tags(fields["tags"])
    if "title" in fields:
        fields["title"] = (fields["title"] or "").strip()
    if "folder_id" in fields:
        folder = db.get_item(db.get_table(FOLDERS_TABLE), user_id, "folder_id", fields["folder_id"])
        if not folder:
            return not_found("Folder")

    fields["updated_at"] = _now()

    set_parts, names, values = [], {}, {}
    for i, (k, v) in enumerate(fields.items()):
        names[f"#f{i}"]  = k
        values[f":v{i}"] = v
        set_parts.append(f"#f{i} = :v{i}")

    result = _table().update_item(
        Key={"user_id": user_id, "note_id": note_id},
        UpdateExpression="SET " + ", ".join(set_parts),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )
    return ok(result["Attributes"])


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_note(user_id: str, note_id: str) -> dict:
    note = db.get_item(_table(), user_id, "note_id", note_id)
    if not note:
        return not_found("Note")
    _table().delete_item(Key={"user_id": user_id, "note_id": note_id})
    return no_content()
