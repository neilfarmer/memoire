import os
import sys
sys.path.insert(0, "/opt/python")

from response import not_found, forbidden
from costs import get_costs
from stats import get_stats
from admin_events import get_events, get_logs

# Comma-separated list of Cognito sub claims allowed to call /admin/stats.
# Set ADMIN_USER_IDS in the Lambda environment at deploy time.
_ADMIN_IDS = {uid.strip() for uid in os.environ.get("ADMIN_USER_IDS", "").split(",") if uid.strip()}


def _admin_user_id(event):
    return (
        event.get("requestContext", {})
             .get("authorizer", {})
             .get("lambda", {})
             .get("user_id", "")
    )


def _is_admin(event) -> bool:
    return bool(_ADMIN_IDS) and _admin_user_id(event) in _ADMIN_IDS


def _int_qs(event, key: str, default: int) -> int:
    try:
        return int(event.get("queryStringParameters", {}).get(key, default))
    except (TypeError, ValueError):
        return default


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path   = event.get("rawPath", "")

    if method == "GET" and path == "/home/costs":
        return get_costs()

    if method == "GET" and path == "/admin/stats":
        if not _is_admin(event):
            return forbidden()
        return get_stats()

    if method == "GET" and path == "/admin/events":
        if not _is_admin(event):
            return forbidden()
        limit = _int_qs(event, "limit", 100)
        event_type = (event.get("queryStringParameters") or {}).get("event_type")
        return get_events(limit=limit, event_type=event_type)

    if method == "GET" and path == "/admin/logs":
        if not _is_admin(event):
            return forbidden()
        minutes = _int_qs(event, "minutes", 60)
        return get_logs(minutes=minutes)

    return not_found()
