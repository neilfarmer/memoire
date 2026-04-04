"""Admin stats: DynamoDB item counts, S3 storage, Lambda invocations, Bedrock usage."""

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
FRONTEND_BUCKET       = os.environ.get("FRONTEND_BUCKET", "")
FUNCTION_PREFIX       = os.environ.get("FUNCTION_PREFIX", "")
ASSISTANT_FUNCTION    = os.environ.get("ASSISTANT_FUNCTION_NAME", "")
ASSISTANT_MODEL_ID    = os.environ.get("ASSISTANT_MODEL_ID", "amazon.nova-lite-v1:0")

# USD per 1K tokens
_BEDROCK_PRICING = {
    "amazon.nova-lite-v1:0":                        {"input": 0.00006, "output": 0.00024},
    "amazon.nova-pro-v1:0":                         {"input": 0.0008,  "output": 0.0032},
    "us.anthropic.claude-haiku-4-5-20251001-v1:0":  {"input": 0.0008,  "output": 0.004},
    "anthropic.claude-haiku-4-5-20251001-v1:0":     {"input": 0.0008,  "output": 0.004},
}

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


def _cw_sum(namespace, metric, dims, start, end, period=86400):
    """Return sum of a CloudWatch metric over the period, or None on error."""
    try:
        resp = _cw.get_metric_statistics(
            Namespace=namespace, MetricName=metric,
            Dimensions=dims, StartTime=start, EndTime=end,
            Period=period, Statistics=["Sum"],
        )
        return sum(p["Sum"] for p in resp.get("Datapoints", []))
    except Exception:
        return None


def _cw_avg(namespace, metric, dims, start, end, period=86400):
    """Return average of a CloudWatch metric, or None on error."""
    try:
        resp = _cw.get_metric_statistics(
            Namespace=namespace, MetricName=metric,
            Dimensions=dims, StartTime=start, EndTime=end,
            Period=period, Statistics=["Average"],
        )
        pts = resp.get("Datapoints", [])
        if not pts:
            return None
        return sum(p["Average"] for p in pts) / len(pts)
    except Exception:
        return None


def _cw_daily(namespace, metric, dims, start, end):
    """Return list of {date, value} daily datapoints, or []."""
    try:
        resp = _cw.get_metric_statistics(
            Namespace=namespace, MetricName=metric,
            Dimensions=dims, StartTime=start, EndTime=end,
            Period=86400, Statistics=["Sum"],
        )
        pts = sorted(resp.get("Datapoints", []), key=lambda p: p["Timestamp"])
        return [{"date": p["Timestamp"].strftime("%Y-%m-%d"), "value": int(p["Sum"])} for p in pts]
    except Exception:
        return []


def _bedrock_stats():
    end      = datetime.now(tz=timezone.utc)
    start_7d = end - timedelta(days=7)
    start_30d = end - timedelta(days=30)

    model_id  = ASSISTANT_MODEL_ID
    # Bedrock metrics use the base model ID, not cross-region inference profiles
    base_model = model_id.split("/")[-1].replace("us.", "").replace("eu.", "")
    bdims = [{"Name": "ModelId", "Value": base_model}]

    input_7d  = _cw_sum("AWS/Bedrock", "InputTokenCount",  bdims, start_7d,  end)
    output_7d = _cw_sum("AWS/Bedrock", "OutputTokenCount", bdims, start_7d,  end)
    input_30d = _cw_sum("AWS/Bedrock", "InputTokenCount",  bdims, start_30d, end)
    output_30d= _cw_sum("AWS/Bedrock", "OutputTokenCount", bdims, start_30d, end)
    latency   = _cw_avg("AWS/Bedrock", "InvocationLatency",bdims, start_7d,  end)
    errors_7d = _cw_sum("AWS/Bedrock", "InvocationClientErrors", bdims, start_7d, end)

    pricing = _BEDROCK_PRICING.get(model_id) or _BEDROCK_PRICING.get(base_model, {"input": 0, "output": 0})
    def est_cost(inp, out):
        if inp is None or out is None:
            return None
        return round((inp / 1000 * pricing["input"]) + (out / 1000 * pricing["output"]), 6)

    # Per-day token usage for sparkline
    daily_tokens = _cw_daily("AWS/Bedrock", "InputTokenCount", bdims, start_7d, end)

    # Assistant Lambda-specific metrics
    fn_inv_7d = fn_err_7d = fn_dur_avg = None
    if ASSISTANT_FUNCTION:
        fdims = [{"Name": "FunctionName", "Value": ASSISTANT_FUNCTION}]
        fn_inv_7d = _cw_sum("AWS/Lambda", "Invocations", fdims, start_7d, end)
        fn_err_7d = _cw_sum("AWS/Lambda", "Errors",      fdims, start_7d, end)
        fn_dur_avg = _cw_avg("AWS/Lambda", "Duration",   fdims, start_7d, end)

    error_rate = None
    if fn_inv_7d and fn_err_7d is not None and fn_inv_7d > 0:
        error_rate = round(fn_err_7d / fn_inv_7d * 100, 1)

    return {
        "model_id":           model_id,
        "input_tokens_7d":    int(input_7d)   if input_7d   is not None else None,
        "output_tokens_7d":   int(output_7d)  if output_7d  is not None else None,
        "input_tokens_30d":   int(input_30d)  if input_30d  is not None else None,
        "output_tokens_30d":  int(output_30d) if output_30d is not None else None,
        "estimated_cost_7d":  est_cost(input_7d, output_7d),
        "estimated_cost_30d": est_cost(input_30d, output_30d),
        "avg_latency_ms":     int(latency)    if latency     is not None else None,
        "errors_7d":          int(errors_7d)  if errors_7d   is not None else None,
        "invocations_7d":     int(fn_inv_7d)  if fn_inv_7d   is not None else None,
        "fn_errors_7d":       int(fn_err_7d)  if fn_err_7d   is not None else None,
        "error_rate_pct":     error_rate,
        "avg_duration_sec":   round(fn_dur_avg / 1000, 1) if fn_dur_avg else None,
        "daily_input_tokens": daily_tokens,
    }


def get_stats():
    try:
        return ok({
            "dynamo":  _dynamo_counts(),
            "s3":      _s3_storage(),
            "lambda":  _lambda_invocations(),
            "bedrock": _bedrock_stats(),
        })
    except Exception as e:
        return server_error(str(e))
