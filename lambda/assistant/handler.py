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

def _stream_handler(event: dict, context, response_stream) -> None:
    response_stream.set_response({
        "statusCode": 200,
        "headers": {
            "Content-Type":           "application/x-ndjson",
            "X-Content-Type-Options": "nosniff",
            "Cache-Control":          "no-cache, no-store",
        },
    })

    try:
        import token_auth
        user_id = token_auth.get_user_id(event)
        if not user_id:
            response_stream.write(
                json.dumps({"type": "error", "message": "Unauthorized"}).encode() + b"\n"
            )
            return

        body: dict = {}
        if event.get("body"):
            try:
                body = json.loads(event["body"])
            except (json.JSONDecodeError, TypeError):
                response_stream.write(
                    json.dumps({"type": "error", "message": "Invalid JSON body"}).encode() + b"\n"
                )
                return

        message = (body.get("message") or "").strip()
        if not message:
            response_stream.write(
                json.dumps({"type": "error", "message": "message is required"}).encode() + b"\n"
            )
            return

        import chat
        chat.chat_stream(
            user_id,
            message,
            emit=response_stream.write,
            model=body.get("model") or None,
            local_date=body.get("local_date") or None,
            no_history=bool(body.get("no_history")),
        )

    except Exception:
        logger.exception("Unhandled exception in streaming_lambda_handler")
        try:
            response_stream.write(
                json.dumps({"type": "error", "message": "Internal server error"}).encode() + b"\n"
            )
        except Exception:
            pass


try:
    from awslambdaric.bootstrap import wrap_streaming_handler
    streaming_lambda_handler = wrap_streaming_handler(_stream_handler)
except ImportError as _e:
    logger.warning("wrap_streaming_handler unavailable (%s); inspecting awslambdaric", _e)
    try:
        import awslambdaric.bootstrap as _bs
        logger.warning("awslambdaric.bootstrap attrs with 'stream': %s",
                       [a for a in dir(_bs) if "stream" in a.lower()])
    except Exception as _e2:
        logger.warning("Could not inspect awslambdaric.bootstrap: %s", _e2)
    streaming_lambda_handler = None  # type: ignore[assignment]
