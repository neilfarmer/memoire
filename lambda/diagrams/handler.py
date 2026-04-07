"""Diagrams Lambda entry point."""

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
                parsed = json.loads(event["body"])
                if not isinstance(parsed, dict):
                    from response import error
                    return error("Invalid JSON body")
                body = parsed
            except (json.JSONDecodeError, TypeError):
                from response import error
                return error("Invalid JSON body")

        path_params  = event.get("pathParameters") or {}
        query_params = event.get("queryStringParameters") or {}
        route_key    = event["routeKey"]

        # Path parameters take precedence over query string parameters
        return route(route_key, user_id, body, {**query_params, **path_params})
    except Exception:
        logger.exception("Unhandled exception in lambda_handler")
        from response import server_error
        return server_error()
