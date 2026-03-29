import sys
sys.path.insert(0, "/opt/python")

from response import not_found
from costs import get_costs
from stats import get_stats


def lambda_handler(event, context):
    method = event.get("requestContext", {}).get("http", {}).get("method", "GET")
    path   = event.get("rawPath", "")

    if method == "GET" and path == "/home/costs":
        return get_costs()

    if method == "GET" and path == "/admin/stats":
        return get_stats()

    return not_found()
