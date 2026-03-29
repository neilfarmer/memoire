"""Journal CRUD operations against DynamoDB."""

import os
import re
from datetime import datetime, timezone

import db
from response import ok, no_content, error, not_found

TABLE_NAME = os.environ["TABLE_NAME"]

VALID_MOODS  = {"great", "good", "okay", "bad", "terrible"}
PREVIEW_LEN  = 200


def _table():
    return db.get_table(TABLE_NAME)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _validate_date(d: str) -> str | None:
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return "date must be YYYY-MM-DD"
    return None


def _parse_tags(raw) -> list[str]:
    if not raw:
        return []
    if isinstance(raw, list):
        return [t.strip() for t in raw if t.strip()]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


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
    err = _validate_date(entry_date)
    if err:
        return error(err)

    item = db.get_item(_table(), user_id, "entry_date", entry_date)
    if not item:
        return not_found("Entry")
    return ok(item)


# ── Upsert ────────────────────────────────────────────────────────────────────

def upsert_entry(user_id: str, entry_date: str, body: dict) -> dict:
    err = _validate_date(entry_date)
    if err:
        return error(err)

    mood = body.get("mood", "")
    if mood and mood not in VALID_MOODS:
        return error(f"mood must be one of: {', '.join(sorted(VALID_MOODS))}")

    tags = _parse_tags(body.get("tags"))

    # Check if entry already exists to preserve created_at
    existing = db.get_item(_table(), user_id, "entry_date", entry_date)
    now      = _now()

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
    return ok(item)


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_entry(user_id: str, entry_date: str) -> dict:
    err = _validate_date(entry_date)
    if err:
        return error(err)

    item = db.get_item(_table(), user_id, "entry_date", entry_date)
    if not item:
        return not_found("Entry")

    _table().delete_item(Key={"user_id": user_id, "entry_date": entry_date})
    return no_content()
