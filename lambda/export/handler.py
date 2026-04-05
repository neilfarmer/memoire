"""Export Lambda — bundles all user data as a ZIP of human-readable files."""

import json
import logging

from exporter import build_export

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context) -> dict:
    from auth import sanitize_event
    logger.info("Event: %s", json.dumps(sanitize_event(event)))
    try:
        from auth import get_user_id
        user_id = get_user_id(event)

        method = event.get("requestContext", {}).get("http", {}).get("method", "")
        path   = event.get("rawPath", "")

        if method == "GET" and path == "/export":
            return build_export(user_id)

        return {"statusCode": 404, "body": "Not found"}
    except Exception:
        logger.exception("Unhandled exception in lambda_handler")
        from response import server_error
        return server_error()
