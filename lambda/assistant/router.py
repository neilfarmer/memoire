"""Assistant Lambda router."""

from response import error, ok
import chat
import memory as mem


def route(route_key: str, user_id: str, body: dict) -> dict:
    if route_key == "POST /assistant/chat":
        message = (body.get("message") or "").strip()
        if not message:
            return error("message is required")
        return chat.chat(user_id, message)

    if route_key == "GET /assistant/history":
        history = mem.load_history(user_id)
        # Return as a flat list of {role, content} for the frontend
        messages = [
            {"role": msg["role"], "content": msg["content"][0]["text"]}
            for msg in history
        ]
        return ok(messages)

    return error("Not found", status=404)
