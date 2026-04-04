"""Assistant Lambda router."""

from response import error
import chat


def route(route_key: str, user_id: str, body: dict) -> dict:
    if route_key == "POST /assistant/chat":
        message = (body.get("message") or "").strip()
        if not message:
            return error("message is required")
        return chat.chat(user_id, message)

    return error("Not found", status=404)
