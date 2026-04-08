"""Assistant Lambda router."""

from response import error, ok
import chat
import memory as mem
import analysis as ana


def route(route_key: str, user_id: str, body: dict, path_params: dict | None = None) -> dict:
    if path_params is None:
        path_params = {}
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
