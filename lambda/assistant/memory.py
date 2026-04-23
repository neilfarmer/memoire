"""Conversation history and user memory storage in DynamoDB.

Multiple chat threads per user are supported: each message row carries a
`conversation_id` attribute, and each thread has a metadata row with
`msg_id = "__meta__#<conversation_id>"` storing title, timestamps, and
message count. The TTL on message rows is configurable per user (0 means
keep forever).
"""

import os
import time
import uuid
from datetime import datetime, timezone

import db

CONVERSATIONS_TABLE = os.environ["CONVERSATIONS_TABLE"]
MEMORY_TABLE        = os.environ["MEMORY_TABLE"]

MAX_HISTORY        = 20
DEFAULT_TTL_DAYS   = 30
MAX_TITLE_LEN      = 200

META_PREFIX = "__meta__#"


def _meta_msg_id(conversation_id: str) -> str:
    return f"{META_PREFIX}{conversation_id}"


def _is_meta(item: dict) -> bool:
    return item.get("msg_id", "").startswith(META_PREFIX)


# ── Conversation metadata ─────────────────────────────────────────────────────

def create_conversation(user_id: str, title: str) -> dict:
    """Insert a new conversation metadata row. Return the metadata dict."""
    conv_id = str(uuid.uuid4())
    now     = datetime.now(timezone.utc).isoformat()
    title   = (title or "New chat").strip()[:MAX_TITLE_LEN] or "New chat"

    table = db.get_table(CONVERSATIONS_TABLE)
    meta  = {
        "user_id":         user_id,
        "msg_id":          _meta_msg_id(conv_id),
        "conversation_id": conv_id,
        "role":            "__meta__",
        "title":           title,
        "created_at":      now,
        "updated_at":      now,
        "message_count":   0,
    }
    table.put_item(Item=meta)
    return {
        "conversation_id": conv_id,
        "title":           title,
        "created_at":      now,
        "updated_at":      now,
        "message_count":   0,
    }


def list_conversations(user_id: str) -> list[dict]:
    table = db.get_table(CONVERSATIONS_TABLE)
    items = db.query_by_user(table, user_id)
    metas = [
        {
            "conversation_id": item.get("conversation_id", ""),
            "title":           item.get("title", "Untitled"),
            "created_at":      item.get("created_at", ""),
            "updated_at":      item.get("updated_at", ""),
            "message_count":   int(item.get("message_count", 0)),
        }
        for item in items
        if _is_meta(item) and item.get("conversation_id")
    ]
    metas.sort(key=lambda x: x["updated_at"], reverse=True)
    return metas


def get_conversation(user_id: str, conversation_id: str) -> dict | None:
    table = db.get_table(CONVERSATIONS_TABLE)
    item  = table.get_item(
        Key={"user_id": user_id, "msg_id": _meta_msg_id(conversation_id)}
    ).get("Item")
    if not item:
        return None
    return {
        "conversation_id": conversation_id,
        "title":           item.get("title", "Untitled"),
        "created_at":      item.get("created_at", ""),
        "updated_at":      item.get("updated_at", ""),
        "message_count":   int(item.get("message_count", 0)),
    }


def touch_conversation(
    user_id: str,
    conversation_id: str,
    title: str | None = None,
    bump_count: int = 0,
) -> None:
    """Update `updated_at` and optionally title/message_count on a thread."""
    now    = datetime.now(timezone.utc).isoformat()
    names  = {"#updated": "updated_at"}
    values = {":updated": now}
    sets   = ["#updated = :updated"]

    if title is not None:
        clean = title.strip()[:MAX_TITLE_LEN]
        if clean:
            names["#title"]  = "title"
            values[":title"] = clean
            sets.append("#title = :title")

    expr = "SET " + ", ".join(sets)
    if bump_count:
        names["#count"] = "message_count"
        values[":inc"]  = bump_count
        expr += " ADD #count :inc"

    table = db.get_table(CONVERSATIONS_TABLE)
    table.update_item(
        Key={"user_id": user_id, "msg_id": _meta_msg_id(conversation_id)},
        UpdateExpression=expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def rename_conversation(user_id: str, conversation_id: str, title: str) -> None:
    touch_conversation(user_id, conversation_id, title=title)


def delete_conversation(user_id: str, conversation_id: str) -> int:
    """Delete metadata and all messages for a single thread. Return row count."""
    table   = db.get_table(CONVERSATIONS_TABLE)
    items   = db.query_by_user(table, user_id)
    targets = [
        i for i in items
        if i.get("msg_id") == _meta_msg_id(conversation_id)
        or i.get("conversation_id") == conversation_id
    ]
    with table.batch_writer() as batch:
        for i in targets:
            batch.delete_item(Key={"user_id": user_id, "msg_id": i["msg_id"]})
    return len(targets)


# ── Messages ──────────────────────────────────────────────────────────────────

def load_history(user_id: str, conversation_id: str) -> list[dict]:
    """Return the last MAX_HISTORY messages for a thread as Bedrock converse dicts."""
    if not conversation_id:
        return []

    table = db.get_table(CONVERSATIONS_TABLE)
    items = db.query_by_user(table, user_id)
    msgs  = [
        i for i in items
        if not _is_meta(i) and i.get("conversation_id") == conversation_id
    ]
    msgs.sort(key=lambda x: x["msg_id"])
    msgs = msgs[-MAX_HISTORY:]

    messages = [
        {"role": m["role"], "content": [{"text": m["content"]}]}
        for m in msgs
    ]

    # Bedrock requires alternating user/assistant starting with user.
    merged: list[dict] = []
    for msg in messages:
        if merged and merged[-1]["role"] == msg["role"]:
            merged[-1]["content"][0]["text"] += "\n" + msg["content"][0]["text"]
        else:
            merged.append(msg)
    while merged and merged[0]["role"] != "user":
        merged.pop(0)
    return merged


def list_messages(user_id: str, conversation_id: str) -> list[dict]:
    """Return all messages for a thread as {role, content} dicts (UI rendering)."""
    if not conversation_id:
        return []
    table = db.get_table(CONVERSATIONS_TABLE)
    items = db.query_by_user(table, user_id)
    msgs  = [
        i for i in items
        if not _is_meta(i) and i.get("conversation_id") == conversation_id
    ]
    msgs.sort(key=lambda x: x["msg_id"])
    return [{"role": m["role"], "content": m["content"], "msg_id": m["msg_id"]} for m in msgs]


def save_message(
    user_id: str,
    conversation_id: str,
    role: str,
    content: str,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> None:
    """Persist a single message. ttl_days=0 disables TTL (kept forever)."""
    table  = db.get_table(CONVERSATIONS_TABLE)
    now    = datetime.now(timezone.utc).isoformat()
    msg_id = f"{now}#{uuid.uuid4()}"
    item   = {
        "user_id":         user_id,
        "msg_id":          msg_id,
        "conversation_id": conversation_id,
        "role":            role,
        "content":         content,
    }
    if ttl_days and ttl_days > 0:
        item["ttl"] = int(time.time()) + (ttl_days * 24 * 3600)
    table.put_item(Item=item)


def clear_history(user_id: str) -> None:
    """Delete every message and metadata row for the user (all threads)."""
    table = db.get_table(CONVERSATIONS_TABLE)
    items = db.query_by_user(table, user_id)
    with table.batch_writer() as batch:
        for item in items:
            batch.delete_item(Key={"user_id": user_id, "msg_id": item["msg_id"]})


# ── Memory (facts, profile, usage) ────────────────────────────────────────────

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
            continue
        else:
            facts[key] = item.get("value", "")
    return facts, master


def save_memory(user_id: str, key: str, value: str) -> None:
    table = db.get_table(MEMORY_TABLE)
    now   = datetime.now(timezone.utc).isoformat()
    table.put_item(Item={
        "user_id":    user_id,
        "memory_key": key,
        "value":      value,
        "updated_at": now,
    })


def save_master_context(user_id: str, context: str) -> None:
    save_memory(user_id, MASTER_CONTEXT_KEY, context)


def load_profile(user_id: str) -> dict:
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
    if name is not None:
        save_memory(user_id, PROFILE_NAME_KEY, name)
    if occupation is not None:
        save_memory(user_id, PROFILE_OCC_KEY, occupation)
    if summary is not None:
        save_memory(user_id, PROFILE_SUMMARY_KEY, summary)


def load_ai_analysis(user_id: str) -> dict:
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
    now = datetime.now(timezone.utc).isoformat()
    save_memory(user_id, AI_ANALYSIS_KEY, analysis)
    save_memory(user_id, AI_ANALYSIS_AT_KEY, now)


def delete_memory(user_id: str, key: str) -> None:
    table = db.get_table(MEMORY_TABLE)
    db.delete_item(table, user_id, "memory_key", key)


USAGE_KEY_PREFIX = "__usage__"


def update_model_usage(user_id: str, model_id: str, input_tokens: int, output_tokens: int) -> None:
    table = db.get_table(MEMORY_TABLE)
    key   = USAGE_KEY_PREFIX + model_id
    table.update_item(
        Key={"user_id": user_id, "memory_key": key},
        UpdateExpression="ADD invocations :one, input_tokens :inp, output_tokens :out",
        ExpressionAttributeValues={":one": 1, ":inp": input_tokens, ":out": output_tokens},
    )


def load_model_usage(user_id: str) -> list[dict]:
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
