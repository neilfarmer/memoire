"""Admin events + CloudWatch logs view.

- get_events(): recent assistant_events rows (tool calls, supervisor verdicts,
  chat completions) across all users, ordered by timestamp desc.
- get_logs(): recent ERROR/WARN lines from the assistant + watcher Lambda log
  groups via CloudWatch Logs Insights.
"""

import os
import time

import boto3
from boto3.dynamodb.conditions import Key

from response import ok, server_error

EVENTS_TABLE    = os.environ.get("EVENTS_TABLE", "")
FUNCTION_PREFIX = os.environ.get("FUNCTION_PREFIX", "")

_ddb  = boto3.resource("dynamodb")
_logs = boto3.client("logs")

_SHARD_KEY = "all"


def _decimal_to_primitive(v):
    try:
        if hasattr(v, "as_tuple"):
            return float(v) if v % 1 else int(v)
    except Exception:
        pass
    return v


def _sanitize(item: dict) -> dict:
    out = {}
    for k, v in item.items():
        if k in ("ttl", "shard"):
            continue
        if isinstance(v, list):
            out[k] = [_decimal_to_primitive(x) if not isinstance(x, dict) else x for x in v]
        else:
            out[k] = _decimal_to_primitive(v)
    return out


def get_events(limit: int = 100, event_type: str | None = None):
    if not EVENTS_TABLE:
        return ok({"events": [], "count": 0})
    try:
        table = _ddb.Table(EVENTS_TABLE)
        kwargs = {
            "IndexName":              "scope-ts-index",
            "KeyConditionExpression": Key("shard").eq(_SHARD_KEY),
            "ScanIndexForward":       False,
            "Limit":                  min(max(limit, 1), 500),
        }
        if event_type:
            kwargs["FilterExpression"] = Key("event_type").eq(event_type)
        resp = table.query(**kwargs)
        items = [_sanitize(i) for i in resp.get("Items", [])]
        return ok({"events": items, "count": len(items)})
    except Exception as e:
        return server_error(f"events query failed: {e}")


def _run_insights_query(log_groups: list[str], query: str, minutes: int) -> list[dict]:
    end   = int(time.time())
    start = end - minutes * 60
    try:
        q = _logs.start_query(
            logGroupNames=log_groups,
            startTime=start,
            endTime=end,
            queryString=query,
            limit=200,
        )
        query_id = q["queryId"]
        deadline = time.time() + 8
        while time.time() < deadline:
            r = _logs.get_query_results(queryId=query_id)
            status = r.get("status")
            if status in ("Complete", "Failed", "Cancelled", "Timeout"):
                break
            time.sleep(0.4)
        else:
            try:
                _logs.stop_query(queryId=query_id)
            except Exception:
                pass
            return []
        results = []
        for row in r.get("results", []):
            rec = {cell["field"]: cell["value"] for cell in row if cell.get("field") != "@ptr"}
            results.append(rec)
        return results
    except Exception:
        return []


def get_logs(minutes: int = 60):
    if not FUNCTION_PREFIX:
        return ok({"logs": [], "count": 0})

    groups = [
        f"/aws/lambda/{FUNCTION_PREFIX}-assistant",
        f"/aws/lambda/{FUNCTION_PREFIX}-watcher",
        f"/aws/lambda/{FUNCTION_PREFIX}-authorizer",
    ]

    query = (
        "fields @timestamp, @message, @logStream | "
        "filter @message like /ERROR|WARN|Exception|Traceback|FAIL/ | "
        "sort @timestamp desc | "
        "limit 100"
    )

    rows = _run_insights_query(groups, query, minutes=max(minutes, 5))
    return ok({"logs": rows, "count": len(rows), "minutes": minutes})
