"""Assistant Lambda entry point — standard API Gateway proxy handler."""

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
