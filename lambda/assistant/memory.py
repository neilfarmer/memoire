"""Conversation history and user memory storage in DynamoDB."""

import os
import time
import uuid
from datetime import datetime, timezone

import db

CONVERSATIONS_TABLE = os.environ["CONVERSATIONS_TABLE"]
MEMORY_TABLE        = os.environ["MEMORY_TABLE"]

MAX_HISTORY = 20
TTL_SECONDS = 30 * 24 * 3600  # 30 days


def load_history(user_id: str) -> list[dict]:
    """Return the last MAX_HISTORY messages as Bedrock converse message dicts."""
    table = db.get_table(CONVERSATIONS_TABLE)
    items = db.query_by_user(table, user_id)
    items.sort(key=lambda x: x["msg_id"])
    items = items[-MAX_HISTORY:]

    messages = []
    for item in items:
        role    = item["role"]
        content = item["content"]
        messages.append({"role": role, "content": [{"text": content}]})

    # Bedrock requires alternating user/assistant, starting with user.
    # Deduplicate consecutive same-role messages by merging content.
    merged: list[dict] = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"][0]["text"] += "\n" + msg["content"][0]["text"]
        else:
            merged.append(msg)

    # Must start with user role
    while merged and merged[0]["role"] != "user":
        merged.pop(0)

    return merged


def save_message(user_id: str, role: str, content: str) -> None:
    """Persist a single message to the conversations table."""
    table  = db.get_table(CONVERSATIONS_TABLE)
    now    = datetime.now(timezone.utc).isoformat()
    msg_id = f"{now}#{uuid.uuid4()}"
    table.put_item(Item={
        "user_id": user_id,
        "msg_id":  msg_id,
        "role":    role,
        "content": content,
        "ttl":     int(time.time()) + TTL_SECONDS,
    })


def load_memory(user_id: str) -> dict:
    """Return {key: value} dict of remembered facts for the user."""
    table = db.get_table(MEMORY_TABLE)
    items = db.query_by_user(table, user_id)
    return {item["memory_key"]: item["value"] for item in items}


def save_memory(user_id: str, key: str, value: str) -> None:
    """Upsert a memory fact."""
    table = db.get_table(MEMORY_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    table.put_item(Item={
        "user_id":    user_id,
        "memory_key": key,
        "value":      value,
        "updated_at": now,
    })
