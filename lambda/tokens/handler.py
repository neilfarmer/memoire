"""Tokens Lambda — Personal Access Token management.

Routes are protected by the Lambda authorizer.
PATs cannot be used to create or revoke other PATs — requests authenticated
via PAT are rejected here with 403.
"""

import json
import logging

from router import route

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context) -> dict:
    sanitized = {k: v for k, v in event.items() if k != "headers"}
    logger.info("Event: %s", json.dumps(sanitized))
    try:
        authorizer  = event["requestContext"]["authorizer"]["lambda"]
        user_id     = authorizer["user_id"]
        auth_method = authorizer.get("auth_method", "jwt")

        if auth_method == "pat":
            logger.warning("PAT-authenticated request rejected on /tokens (user_id=%s)", user_id)
            from response import error
            return error("PATs cannot be used to manage other PATs", status=403)

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
    except Exception:
        logger.exception("Unhandled exception in lambda_handler")
        from response import server_error
        return server_error()
