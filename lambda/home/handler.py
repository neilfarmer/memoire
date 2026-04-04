import os
import sys
sys.path.insert(0, "/opt/python")

from response import not_found, forbidden
from costs import get_costs
from stats import get_stats

# Comma-separated list of Cognito sub claims allowed to call /admin/stats.
# Set ADMIN_USER_IDS in the Lambda environment at deploy time.
_ADMIN_IDS = {uid.strip() for uid in os.environ.get("ADMIN_USER_IDS", "").split(",") if uid.strip()}


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path   = event.get("rawPath", "")

    if method == "GET" and path == "/home/costs":
        return get_costs()

    if method == "GET" and path == "/admin/stats":
        user_id = (
            event.get("requestContext", {})
                 .get("authorizer", {})
                 .get("lambda", {})
                 .get("user_id", "")
        )
        if not _ADMIN_IDS or user_id not in _ADMIN_IDS:
            return forbidden()
        return get_stats()

    return not_found()
