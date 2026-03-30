"""Tokens Lambda — Personal Access Token management.

Routes are protected by the Cognito JWT authorizer only.
PATs cannot be used to create or revoke other PATs.
"""

import json
import logging

from router import route

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context) -> dict:
    logger.info("Event: %s", json.dumps(event))

    # These routes only accept the JWT authorizer, so jwt.claims is always present.
    claims  = event["requestContext"]["authorizer"]["jwt"]["claims"]
    user_id = claims["sub"]

    body = {}
    if event.get("body"):
        try:
            body = json.loads(event["body"])
        except (json.JSONDecodeError, TypeError):
            from response import error
            return error("Invalid JSON body")

    path_params = event.get("pathParameters") or {}
    route_key   = event["routeKey"]

    return route(route_key, user_id, body, path_params)
