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


MASTER_CONTEXT_KEY = "__master_context__"


def load_memory(user_id: str) -> tuple[dict, str]:
    """Return ({key: value} facts dict, master_context string) for the user."""
    table = db.get_table(MEMORY_TABLE)
    items = db.query_by_user(table, user_id)
    facts  = {}
    master = ""
    for item in items:
        key = item["memory_key"]
        if key == MASTER_CONTEXT_KEY:
            master = item.get("value", "")
        elif key.startswith("__"):
            continue  # skip internal keys (usage counters, etc.)
        else:
            facts[key] = item.get("value", "")
    return facts, master


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


def save_master_context(user_id: str, context: str) -> None:
    """Persist the master context paragraph."""
    save_memory(user_id, MASTER_CONTEXT_KEY, context)


def delete_memory(user_id: str, key: str) -> None:
    """Delete a single memory fact by key."""
    table = db.get_table(MEMORY_TABLE)
    db.delete_item(table, user_id, "memory_key", key)


USAGE_KEY_PREFIX = "__usage__"


def update_model_usage(user_id: str, model_id: str, input_tokens: int, output_tokens: int) -> None:
    """Atomically increment per-model token counters and invocation count."""
    table = db.get_table(MEMORY_TABLE)
    key   = USAGE_KEY_PREFIX + model_id
    table.update_item(
        Key={"user_id": user_id, "memory_key": key},
        UpdateExpression="ADD invocations :one, input_tokens :inp, output_tokens :out",
        ExpressionAttributeValues={":one": 1, ":inp": input_tokens, ":out": output_tokens},
    )


def load_model_usage(user_id: str) -> list[dict]:
    """Return per-model usage records."""
    table = db.get_table(MEMORY_TABLE)
    items = db.query_by_user(table, user_id)
    return [
        {
            "model_id":     item["memory_key"][len(USAGE_KEY_PREFIX):],
            "invocations":  int(item.get("invocations", 0)),
            "input_tokens": int(item.get("input_tokens", 0)),
            "output_tokens":int(item.get("output_tokens", 0)),
        }
        for item in items
        if item["memory_key"].startswith(USAGE_KEY_PREFIX)
    ]


def clear_history(user_id: str) -> None:
    """Delete all conversation history for the user."""
    table = db.get_table(CONVERSATIONS_TABLE)
    items = db.query_by_user(table, user_id)
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"user_id": user_id, "msg_id": item["msg_id"]})
