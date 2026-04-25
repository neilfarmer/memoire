"""Journal CRUD operations against DynamoDB."""

import os

import db
import links_util
from response import ok, no_content, error, not_found
from utils import now_iso, validate_date, parse_tags

TABLE_NAME = os.environ["TABLE_NAME"]

VALID_MOODS  = {"great", "good", "okay", "bad", "terrible"}
PREVIEW_LEN  = 200


def _table():
    return db.get_table(TABLE_NAME)


def _summary(item: dict) -> dict:
    """Strip body down to a preview for list/search responses."""
    body    = item.get("body", "")
    preview = body[:PREVIEW_LEN] + ("..." if len(body) > PREVIEW_LEN else "")
    return {k: v for k, v in item.items() if k != "body"} | {"preview": preview}


# ── List ──────────────────────────────────────────────────────────────────────

def list_entries(user_id: str) -> dict:
    entries = db.query_by_user(_table(), user_id)
    entries.sort(key=lambda e: e["entry_date"], reverse=True)
    return ok([_summary(e) for e in entries])


# ── Search ────────────────────────────────────────────────────────────────────

def search_entries(user_id: str, q: str) -> dict:
    entries = db.query_by_user(_table(), user_id)
    q_lower = q.lower()

    def matches(e):
        return (
            q_lower in e.get("title", "").lower()
            or q_lower in e.get("body", "").lower()
            or any(q_lower in t.lower() for t in (e.get("tags") or []))
        )

    results = sorted(
        [_summary(e) for e in entries if matches(e)],
        key=lambda e: e["entry_date"],
        reverse=True,
    )
    return ok(results)


# ── Get ───────────────────────────────────────────────────────────────────────

def get_entry(user_id: str, entry_date: str) -> dict:
    err = validate_date(entry_date)
    if err:
        return error(err)

    item = db.get_item(_table(), user_id, "entry_date", entry_date)
    if not item:
        return not_found("Entry")
    return ok(item)


# ── Upsert ────────────────────────────────────────────────────────────────────

def upsert_entry(user_id: str, entry_date: str, body: dict) -> dict:
    err = validate_date(entry_date)
    if err:
        return error(err)

    mood = body.get("mood", "")
    if mood and mood not in VALID_MOODS:
        return error(f"mood must be one of: {', '.join(sorted(VALID_MOODS))}")

    tags = parse_tags(body.get("tags"))

    # Check if entry already exists to preserve created_at
    existing = db.get_item(_table(), user_id, "entry_date", entry_date)
    now      = now_iso()

    item = {
        "user_id":    user_id,
        "entry_date": entry_date,
        "title":      (body.get("title") or "").strip(),
        "body":       body.get("body", ""),
        "mood":       mood,
        "tags":       tags,
        "created_at": existing["created_at"] if existing else now,
        "updated_at": now,
    }
    item = {k: v for k, v in item.items() if v is not None and v != "" or k in ("body", "tags", "mood", "title")}

    _table().put_item(Item=item)
    links_util.sync_links(
        user_id, "journal", entry_date,
        [item.get("title", ""), item.get("body", "")],
    )
    return ok(item)


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_entry(user_id: str, entry_date: str) -> dict:
    err = validate_date(entry_date)
    if err:
        return error(err)

    item = db.get_item(_table(), user_id, "entry_date", entry_date)
    if not item:
        return not_found("Entry")

    _table().delete_item(Key={"user_id": user_id, "entry_date": entry_date})
    links_util.delete_source_links(user_id, "journal", entry_date)
    return no_content()
