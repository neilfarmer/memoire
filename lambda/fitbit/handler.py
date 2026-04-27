"""Fitbit Lambda entry point.

Handles OAuth2 connect/callback/disconnect plus the read endpoint
for today's cached Fitbit data.
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
            from response import error
            try:
                body = json.loads(event["body"])
            except (json.JSONDecodeError, TypeError):
                return error("Invalid JSON body")
            if not isinstance(body, dict):
                return error("Request body must be a JSON object")

        path_params  = event.get("pathParameters") or {}
        query_params = event.get("queryStringParameters") or {}
        route_key    = event["routeKey"]

        return route(route_key, user_id, body, path_params, query_params)
    except Exception:
        logger.exception("Unhandled exception in lambda_handler")
        from response import server_error
        return server_error()
