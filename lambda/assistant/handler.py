"""Assistant Lambda entry point.

Two handlers are exported:
- lambda_handler          — standard API Gateway proxy handler (all routes).
- streaming_lambda_handler — Lambda Function URL handler with RESPONSE_STREAM
                             invoke mode; streams chat tokens as NDJSON.
"""

import json
import logging

from router import route

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context) -> dict:
    from auth import sanitize_event
    logger.info("Event: %s", json.dumps(sanitize_event(event)))
    try:
        from auth import get_user_id
        user_id = get_user_id(event)

        body = {}
        if event.get("body"):
            try:
                body = json.loads(event["body"])
            except (json.JSONDecodeError, TypeError):
                from response import error
                return error("Invalid JSON body")

        route_key    = event["routeKey"]
        return route(route_key, user_id, body)
    except Exception:
        logger.exception("Unhandled exception in lambda_handler")
        from response import server_error
        return server_error()


# ── Streaming handler (Lambda Function URL, InvokeMode: RESPONSE_STREAM) ──────
#
# Clients receive NDJSON lines:
#   {"type":"status","text":"<tool_name>"}  — tool invocation in progress
#   {"type":"token","text":"<chunk>"}       — streamed text token
#   {"type":"done","tools_used":[...],"reply":"<full_clean_reply>"}
#   {"type":"error","message":"..."}        — on failure
#
# Auth is handled in-function (no API Gateway authorizer) via token_auth.py,
# which supports the same Cognito JWTs and PATs as the authorizer Lambda.

def streaming_lambda_handler(event: dict, context) -> dict:
    """Lambda Function URL handler (BUFFERED invoke mode).

    Auth is handled in-function (no API Gateway authorizer context).
    Calls Bedrock, collects the full NDJSON output, and returns it in one
    response.  Clients receive the same NDJSON format as the streaming path;
    the full response just arrives in one payload rather than token-by-token.
    """
    try:
        import token_auth
        hdrs = event.get("headers") or {}
        logger.info("Auth headers: auth=%s cookie_keys=%s",
                    bool(hdrs.get("authorization") or hdrs.get("Authorization")),
                    [k for k in hdrs if "cookie" in k.lower()])
        user_id = token_auth.get_user_id(event)
        if not user_id:
            logger.warning("Auth failed; headers present: %s", sorted(hdrs.keys()))
            return {
                "statusCode": 401,
                "headers": {"Content-Type": "application/x-ndjson"},
                "body": json.dumps({"type": "error", "message": "Unauthorized"}) + "\n",
            }

        body: dict = {}
        if event.get("body"):
            try:
                body = json.loads(event["body"])
            except (json.JSONDecodeError, TypeError):
                return {
                    "statusCode": 400,
                    "headers": {"Content-Type": "application/x-ndjson"},
                    "body": json.dumps({"type": "error", "message": "Invalid JSON body"}) + "\n",
                }

        message = (body.get("message") or "").strip()
        if not message:
            return {
                "statusCode": 400,
                "headers": {"Content-Type": "application/x-ndjson"},
                "body": json.dumps({"type": "error", "message": "message is required"}) + "\n",
            }

        buf: list[bytes] = []

        import chat
        chat.chat_stream(
            user_id,
            message,
            emit=buf.append,
            model=body.get("model") or None,
            local_date=body.get("local_date") or None,
            no_history=bool(body.get("no_history")),
        )

        return {
            "statusCode": 200,
            "headers": {
                "Content-Type":           "application/x-ndjson",
                "X-Content-Type-Options": "nosniff",
                "Cache-Control":          "no-cache, no-store",
            },
            "body": b"".join(buf).decode("utf-8", errors="replace"),
        }

    except Exception:
        logger.exception("Unhandled exception in streaming_lambda_handler")
        return {
            "statusCode": 500,
            "headers": {"Content-Type": "application/x-ndjson"},
            "body": json.dumps({"type": "error", "message": "Internal server error"}) + "\n",
        }
