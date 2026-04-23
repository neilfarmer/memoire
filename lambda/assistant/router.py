"""Assistant Lambda router."""

import os

import boto3

from response import error, ok, not_found
import chat
import memory as mem
import analysis as ana


SETTINGS_TABLE = os.environ.get("SETTINGS_TABLE")


def _load_chat_retention_days(user_id: str) -> int:
    """Read `chat_retention_days` from the user's settings. Fall back to default."""
    if not SETTINGS_TABLE:
        return mem.DEFAULT_TTL_DAYS
    try:
        ddb  = boto3.resource("dynamodb")
        item = ddb.Table(SETTINGS_TABLE).get_item(Key={"user_id": user_id}).get("Item")
    except Exception:
        return mem.DEFAULT_TTL_DAYS
    if not item or "chat_retention_days" not in item:
        return mem.DEFAULT_TTL_DAYS
    try:
        return max(0, int(item["chat_retention_days"]))
    except (TypeError, ValueError):
        return mem.DEFAULT_TTL_DAYS


def _derive_title(message: str) -> str:
    clean = (message or "").strip().replace("\n", " ")
    if len(clean) > 60:
        clean = clean[:57].rstrip() + "..."
    return clean or "New chat"


def route(route_key: str, user_id: str, body: dict, path_params: dict | None = None) -> dict:
    if path_params is None:
        path_params = {}

    if route_key == "POST /assistant/chat":
        message = (body.get("message") or "").strip()
        if not message:
            return error("message is required")
        model           = body.get("model") or None
        local_date      = body.get("local_date") or None
        no_history      = bool(body.get("no_history"))
        conversation_id = (body.get("conversation_id") or "").strip() or None

        ttl_days = _load_chat_retention_days(user_id)

        if not no_history:
            if conversation_id:
                if mem.get_conversation(user_id, conversation_id) is None:
                    return error("conversation_id not found", status=404)
            else:
                meta = mem.create_conversation(user_id, _derive_title(message))
                conversation_id = meta["conversation_id"]

        return chat.chat(
            user_id,
            message,
            model=model,
            local_date=local_date,
            no_history=no_history,
            conversation_id=conversation_id,
            ttl_days=ttl_days,
        )

    if route_key == "GET /assistant/conversations":
        return ok(mem.list_conversations(user_id))

    if route_key == "POST /assistant/conversations":
        title = (body.get("title") or "").strip() or "New chat"
        meta  = mem.create_conversation(user_id, title)
        return ok(meta)

    if route_key == "GET /assistant/conversations/{id}":
        conv_id = path_params.get("id", "").strip()
        if not conv_id:
            return error("Missing conversation id")
        meta = mem.get_conversation(user_id, conv_id)
        if not meta:
            return not_found("Conversation")
        from chat import _clean_reply
        raw = mem.list_messages(user_id, conv_id)
        messages = [
            {
                "role": m["role"],
                "content": _clean_reply(m["content"]) if m["role"] == "assistant" else m["content"],
                "msg_id": m["msg_id"],
            }
            for m in raw
        ]
        return ok({**meta, "messages": messages})

    if route_key == "PATCH /assistant/conversations/{id}":
        conv_id = path_params.get("id", "").strip()
        if not conv_id:
            return error("Missing conversation id")
        if mem.get_conversation(user_id, conv_id) is None:
            return not_found("Conversation")
        title = (body.get("title") or "").strip()
        if not title:
            return error("title is required")
        mem.rename_conversation(user_id, conv_id, title)
        return ok({"updated": True})

    if route_key == "DELETE /assistant/conversations/{id}":
        conv_id = path_params.get("id", "").strip()
        if not conv_id:
            return error("Missing conversation id")
        deleted = mem.delete_conversation(user_id, conv_id)
        if deleted == 0:
            return not_found("Conversation")
        return ok({"deleted": True})

    if route_key == "GET /assistant/history":
        # Legacy: return the most recent thread's messages (or empty).
        conversations = mem.list_conversations(user_id)
        if not conversations:
            return ok([])
        latest = conversations[0]
        from chat import _clean_reply
        raw = mem.list_messages(user_id, latest["conversation_id"])
        messages = [
            {
                "role": m["role"],
                "content": _clean_reply(m["content"]) if m["role"] == "assistant" else m["content"],
            }
            for m in raw
        ]
        return ok(messages)

    if route_key == "DELETE /assistant/history":
        mem.clear_history(user_id)
        return ok({"cleared": True})

    if route_key == "GET /assistant/usage":
        return ok(mem.load_model_usage(user_id))

    if route_key == "GET /assistant/memory":
        facts, master = mem.load_memory(user_id)
        profile       = mem.load_profile(user_id)
        ai_analysis   = mem.load_ai_analysis(user_id)
        return ok({"master_context": master, "facts": facts, "profile": profile, "ai_analysis": ai_analysis})

    if route_key == "PUT /assistant/memory":
        context = (body.get("master_context") or "").strip()
        mem.save_master_context(user_id, context)
        return ok({"updated": True})

    if route_key == "PUT /assistant/memory/facts/{key}":
        key   = path_params.get("key", "").strip()
        value = (body.get("value") or "").strip()
        if not key or key.startswith("__"):
            return error("Invalid key")
        if not value:
            return error("value is required")
        mem.save_memory(user_id, key, value)
        return ok({"updated": True})

    if route_key == "DELETE /assistant/memory/{key}":
        key = path_params.get("key", "").strip()
        if not key or key.startswith("__"):
            return error("Invalid key")
        mem.delete_memory(user_id, key)
        return ok({"deleted": True})

    if route_key == "GET /assistant/profile":
        return ok(mem.load_profile(user_id))

    if route_key == "PUT /assistant/profile":
        name       = body.get("name")
        occupation = body.get("occupation")
        summary    = body.get("summary")
        if name is None and occupation is None and summary is None:
            return error("At least one field required")
        mem.save_profile(user_id, name=name, occupation=occupation, summary=summary)
        return ok({"updated": True})

    if route_key == "POST /assistant/profile/analyze":
        result = ana.generate_analysis(user_id)
        return ok(result)

    return error("Not found", status=404)
