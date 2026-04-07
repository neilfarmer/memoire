"""Diagrams CRUD — DynamoDB-backed Excalidraw diagram storage."""

import json
import os
import uuid
from datetime import datetime, timezone

import db
from response import ok, created, no_content, error, not_found

DIAGRAMS_TABLE = os.environ["DIAGRAMS_TABLE"]

MAX_DIAGRAMS    = 100
MAX_TITLE_CHARS = 200


def _table():
    return db.get_table(DIAGRAMS_TABLE)


def list_diagrams(user_id: str) -> dict:
    items = db.query_by_user(_table(), user_id)
    # Return metadata only — omit elements/app_state to keep list payloads small
    summaries = [
        {
            "diagram_id": item["diagram_id"],
            "title":      item.get("title", "Untitled"),
            "created_at": item.get("created_at", ""),
            "updated_at": item.get("updated_at", ""),
        }
        for item in items
    ]
    summaries.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return ok(summaries)


def create_diagram(user_id: str, body: dict) -> dict:
    title = (body.get("title") or "Untitled").strip()[:MAX_TITLE_CHARS]

    existing = db.query_by_user(_table(), user_id)
    if len(existing) >= MAX_DIAGRAMS:
        return error(f"Maximum of {MAX_DIAGRAMS} diagrams allowed")

    now = datetime.now(timezone.utc).isoformat()
    diagram_id = str(uuid.uuid4())
    item = {
        "user_id":    user_id,
        "diagram_id": diagram_id,
        "title":      title,
        "elements":   json.dumps(body.get("elements") or []),
        "app_state":  json.dumps(body.get("app_state") or {}),
        "created_at": now,
        "updated_at": now,
    }
    _table().put_item(Item=item)
    return created({
        "diagram_id": diagram_id,
        "title":      title,
        "elements":   body.get("elements") or [],
        "app_state":  body.get("app_state") or {},
        "created_at": now,
        "updated_at": now,
    })


def update_diagram(user_id: str, diagram_id: str, body: dict) -> dict:
    existing = db.get_item(_table(), user_id, "diagram_id", diagram_id)
    if not existing:
        return not_found("Diagram")

    now = datetime.now(timezone.utc).isoformat()
    title    = (body.get("title") or existing.get("title") or "Untitled").strip()[:MAX_TITLE_CHARS]
    elements = body.get("elements")
    app_state = body.get("app_state")

    item = {
        "user_id":    user_id,
        "diagram_id": diagram_id,
        "title":      title,
        "elements":   json.dumps(elements if elements is not None else json.loads(existing.get("elements", "[]"))),
        "app_state":  json.dumps(app_state if app_state is not None else json.loads(existing.get("app_state", "{}"))),
        "created_at": existing.get("created_at", now),
        "updated_at": now,
    }
    _table().put_item(Item=item)
    return ok({
        "diagram_id": diagram_id,
        "title":      title,
        "elements":   elements if elements is not None else json.loads(existing.get("elements", "[]")),
        "app_state":  app_state if app_state is not None else json.loads(existing.get("app_state", "{}")),
        "created_at": item["created_at"],
        "updated_at": now,
    })


def delete_diagram(user_id: str, diagram_id: str) -> dict:
    existing = db.get_item(_table(), user_id, "diagram_id", diagram_id)
    if not existing:
        return not_found("Diagram")
    db.delete_item(_table(), user_id, "diagram_id", diagram_id)
    return no_content()


def get_diagram(user_id: str, diagram_id: str) -> dict:
    """Return a single diagram including full elements/app_state."""
    item = db.get_item(_table(), user_id, "diagram_id", diagram_id)
    if not item:
        return not_found("Diagram")
    return ok({
        "diagram_id": item["diagram_id"],
        "title":      item.get("title", "Untitled"),
        "elements":   json.loads(item.get("elements", "[]")),
        "app_state":  json.loads(item.get("app_state", "{}")),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
    })
