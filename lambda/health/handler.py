"""Health Lambda entry point."""

import json
import logging

from router import route

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context) -> dict:
    logger.info("Event: %s", json.dumps(event))

    claims  = event["requestContext"]["authorizer"]["jwt"]["claims"]
    user_id = claims["sub"]

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except (json.JSONDecodeError, TypeError):
            from response import error
            return error("Invalid JSON body")

    path_params  = event.get("pathParameters") or {}
    query_params = event.get("queryStringParameters") or {}
    route_key    = event["routeKey"]

    return route(route_key, user_id, body, path_params, query_params)
