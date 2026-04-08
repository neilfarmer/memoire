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


MASTER_CONTEXT_KEY  = "__master_context__"
PROFILE_NAME_KEY    = "__profile_name__"
PROFILE_OCC_KEY     = "__profile_occupation__"
PROFILE_SUMMARY_KEY = "__profile_summary__"
AI_ANALYSIS_KEY     = "__ai_analysis__"
AI_ANALYSIS_AT_KEY  = "__ai_analysis_at__"


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


def load_profile(user_id: str) -> dict:
    """Return {name, occupation, summary} from profile keys."""
    table = db.get_table(MEMORY_TABLE)
    items = db.query_by_user(table, user_id)
    result  = {"name": "", "occupation": "", "summary": ""}
    key_map = {
        PROFILE_NAME_KEY:    "name",
        PROFILE_OCC_KEY:     "occupation",
        PROFILE_SUMMARY_KEY: "summary",
    }
    for item in items:
        field = key_map.get(item["memory_key"])
        if field:
            result[field] = item.get("value", "")
    return result


def save_profile(user_id: str, name: str | None = None, occupation: str | None = None, summary: str | None = None) -> None:
    """Save profile fields — only provided (non-None) fields are updated."""
    if name is not None:
        save_memory(user_id, PROFILE_NAME_KEY, name)
    if occupation is not None:
        save_memory(user_id, PROFILE_OCC_KEY, occupation)
    if summary is not None:
        save_memory(user_id, PROFILE_SUMMARY_KEY, summary)


def load_ai_analysis(user_id: str) -> dict:
    """Return {analysis, generated_at} for the stored AI profile analysis."""
    table = db.get_table(MEMORY_TABLE)
    items = db.query_by_user(table, user_id)
    analysis     = ""
    generated_at = ""
    for item in items:
        k = item["memory_key"]
        if k == AI_ANALYSIS_KEY:
            analysis = item.get("value", "")
        elif k == AI_ANALYSIS_AT_KEY:
            generated_at = item.get("value", "")
    return {"analysis": analysis, "generated_at": generated_at}


def save_ai_analysis(user_id: str, analysis: str) -> None:
    """Persist the AI profile analysis and its generation timestamp."""
    now = datetime.now(timezone.utc).isoformat()
    save_memory(user_id, AI_ANALYSIS_KEY, analysis)
    save_memory(user_id, AI_ANALYSIS_AT_KEY, now)


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
