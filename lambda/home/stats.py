"""Admin stats: DynamoDB item counts, S3 storage, Lambda invocations."""

import os
import boto3
from datetime import datetime, timedelta, timezone
from response import ok, server_error

TABLES = {
    "tasks":     os.environ.get("TASKS_TABLE", ""),
    "journal":   os.environ.get("JOURNAL_TABLE", ""),
    "notes":     os.environ.get("NOTES_TABLE", ""),
    "folders":   os.environ.get("FOLDERS_TABLE", ""),
    "habits":    os.environ.get("HABITS_TABLE", ""),
    "health":    os.environ.get("HEALTH_TABLE", ""),
    "nutrition": os.environ.get("NUTRITION_TABLE", ""),
    "settings":  os.environ.get("SETTINGS_TABLE", ""),
}
FRONTEND_BUCKET  = os.environ.get("FRONTEND_BUCKET", "")
FUNCTION_PREFIX  = os.environ.get("FUNCTION_PREFIX", "")

_ddb = boto3.client("dynamodb")
_s3  = boto3.client("s3")
_cw  = boto3.client("cloudwatch")


def _dynamo_counts():
    counts = {}
    for name, table in TABLES.items():
        if not table:
            continue
        try:
            resp = _ddb.describe_table(TableName=table)
            counts[name] = resp["Table"].get("ItemCount", 0)
        except Exception:
            counts[name] = None
    return counts


def _s3_storage():
    if not FRONTEND_BUCKET:
        return {"objects": 0, "bytes": 0}
    total_objects = 0
    total_bytes   = 0
    paginator = _s3.get_paginator("list_objects_v2")
    for prefix in ("note-images/", "note-attachments/"):
        for page in paginator.paginate(Bucket=FRONTEND_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                total_objects += 1
                total_bytes   += obj.get("Size", 0)
    return {"objects": total_objects, "bytes": total_bytes}


def _lambda_invocations():
    if not FUNCTION_PREFIX:
        return []
    end   = datetime.now(tz=timezone.utc)
    start = end - timedelta(days=7)
    try:
        resp = _cw.get_metric_statistics(
            Namespace="AWS/Lambda",
            MetricName="Invocations",
            Dimensions=[],
            StartTime=start,
            EndTime=end,
            Period=86400,
            Statistics=["Sum"],
        )
        points = sorted(resp.get("Datapoints", []), key=lambda p: p["Timestamp"])
        return [{"date": p["Timestamp"].strftime("%Y-%m-%d"), "count": int(p["Sum"])} for p in points]
    except Exception:
        return []


def get_stats():
    try:
        return ok({
            "dynamo":  _dynamo_counts(),
            "s3":      _s3_storage(),
            "lambda":  _lambda_invocations(),
        })
    except Exception as e:
        return server_error(str(e))
