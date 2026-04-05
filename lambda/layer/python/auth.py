"""Extract the authenticated user_id from an API Gateway v2 event.

Supports two authorizer contexts:
- JWT authorizer (Cognito built-in):   event["requestContext"]["authorizer"]["jwt"]["claims"]["sub"]
- Lambda authorizer (PAT or JWT):      event["requestContext"]["authorizer"]["lambda"]["user_id"]
"""


def get_user_id(event: dict) -> str:
    auth = event["requestContext"]["authorizer"]
    if "lambda" in auth:
        return auth["lambda"]["user_id"]
    return auth["jwt"]["claims"]["sub"]


_REDACTED_KEYS = {"headers", "cookies"}


def sanitize_event(event: dict) -> dict:
    """Return event with sensitive keys removed for safe logging.

    Strips headers (contains Authorization/cookie) and cookies (top-level
    array in API Gateway HTTP API events) to prevent credentials from
    appearing in CloudWatch Logs.
    """
    return {k: v for k, v in event.items() if k not in _REDACTED_KEYS}
