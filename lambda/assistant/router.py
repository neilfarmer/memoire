"""Assistant Lambda router."""

from response import error, ok
import chat
import memory as mem


def route(route_key: str, user_id: str, body: dict) -> dict:
    if route_key == "POST /assistant/chat":
        message = (body.get("message") or "").strip()
        if not message:
            return error("message is required")
        model      = body.get("model") or None
        local_date = body.get("local_date") or None
        no_history = bool(body.get("no_history"))
        return chat.chat(user_id, message, model=model, local_date=local_date, no_history=no_history)

    if route_key == "GET /assistant/history":
        history = mem.load_history(user_id)
        from chat import _clean_reply
        messages = [
            {
                "role": msg["role"],
                "content": _clean_reply(msg["content"][0]["text"]) if msg["role"] == "assistant" else msg["content"][0]["text"],
            }
            for msg in history
        ]
        return ok(messages)

    if route_key == "DELETE /assistant/history":
        mem.clear_history(user_id)
        return ok({"cleared": True})

    if route_key == "GET /assistant/usage":
        return ok(mem.load_model_usage(user_id))

    return error("Not found", status=404)
