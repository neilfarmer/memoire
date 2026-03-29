"""Export Lambda — bundles all user data as a ZIP of human-readable files."""

import json
import logging

from exporter import build_export

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def lambda_handler(event: dict, context) -> dict:
    logger.info("Event: %s", json.dumps(event))

    claims  = event["requestContext"]["authorizer"]["jwt"]["claims"]
    user_id = claims["sub"]

    method = event.get("requestContext", {}).get("http", {}).get("method", "")
    path   = event.get("rawPath", "")

    if method == "GET" and path == "/export":
        return build_export(user_id)

    return {"statusCode": 404, "body": "Not found"}
