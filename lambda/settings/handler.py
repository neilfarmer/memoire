"""Settings Lambda entry point."""

import json
import logging

from router import route

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context) -> dict:
    logger.info("Event: %s", json.dumps(event))

    from auth import get_user_id
    user_id = get_user_id(event)

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except (json.JSONDecodeError, TypeError):
            from response import error
            return error("Invalid JSON body")

    route_key = event["routeKey"]

    return route(route_key, user_id, body)
