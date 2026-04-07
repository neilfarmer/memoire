"""Favorites CRUD."""

import os
import uuid
from datetime import datetime, timezone

import db
from response import ok, created, no_content, error, not_found

FAVORITES_TABLE = os.environ["FAVORITES_TABLE"]

MAX_FAVORITES = 500
MAX_TAGS      = 20
MAX_TAG_LEN   = 50


def _table():
    return db.get_table(FAVORITES_TABLE)


def list_favorites(user_id: str) -> dict:
    items = db.query_by_user(_table(), user_id)
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return ok(items)


def add_favorite(user_id: str, body: dict) -> dict:
    url = (body.get("url") or "").strip()
    if not url:
        return error("url is required")

    existing = db.query_by_user(_table(), user_id)
    if len(existing) >= MAX_FAVORITES:
        return error(f"Maximum of {MAX_FAVORITES} favorites allowed")
    if any(f["url"] == url for f in existing):
        return error("Already favorited")

    tags = [str(t).strip()[:MAX_TAG_LEN] for t in (body.get("tags") or []) if str(t).strip()]
    tags = list(dict.fromkeys(tags))[:MAX_TAGS]  # deduplicate, cap

    favorite_id = str(uuid.uuid4())
    item = {
        "user_id":     user_id,
        "favorite_id": favorite_id,
        "url":         url,
        "title":       (body.get("title") or "").strip()[:500],
        "feed_title":  (body.get("feed_title") or "").strip()[:200],
        "image":       (body.get("image") or "").strip()[:2000],
        "description": (body.get("description") or "").strip()[:500],
        "published":   (body.get("published") or "").strip(),
        "tags":        tags,
        "created_at":  datetime.now(timezone.utc).isoformat(),
    }
    _table().put_item(Item=item)
    return created(item)


def remove_favorite(user_id: str, favorite_id: str) -> dict:
    existing = db.get_item(_table(), user_id, "favorite_id", favorite_id)
    if not existing:
        return not_found("Favorite")
    db.delete_item(_table(), user_id, "favorite_id", favorite_id)
    return no_content()


def update_tags(user_id: str, favorite_id: str, body: dict) -> dict:
    existing = db.get_item(_table(), user_id, "favorite_id", favorite_id)
    if not existing:
        return not_found("Favorite")

    tags = [str(t).strip()[:MAX_TAG_LEN] for t in (body.get("tags") or []) if str(t).strip()]
    tags = list(dict.fromkeys(tags))[:MAX_TAGS]

    _table().update_item(
        Key={"user_id": user_id, "favorite_id": favorite_id},
        UpdateExpression="SET tags = :t",
        ExpressionAttributeValues={":t": tags},
    )
    existing["tags"] = tags
    return ok(existing)
