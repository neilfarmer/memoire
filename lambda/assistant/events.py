"""Assistant event recording for admin dashboard.

Writes structured events (tool calls, supervisor verdicts, chat completions)
to the assistant_events DynamoDB table. All writes are non-blocking — failures
are logged but never raised, so event telemetry cannot break a user chat turn.
"""

import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3

logger = logging.getLogger(__name__)

EVENTS_TABLE = os.environ.get("EVENTS_TABLE", "")
TTL_DAYS     = 30

_SHARD_KEY = "all"


def _table():
    if not EVENTS_TABLE:
        return None
    # Lazy resource so moto (and tests) can intercept correctly at call time.
    return boto3.resource("dynamodb").Table(EVENTS_TABLE)


def _trim(value, limit: int = 2000) -> str:
    try:
        s = value if isinstance(value, str) else json.dumps(value, default=str)
    except Exception:
        s = str(value)
    if len(s) > limit:
        return s[:limit] + "…[truncated]"
    return s


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def record(user_id: str, event_type: str, payload: dict) -> None:
    """Write a single event. Silent on failure."""
    table = _table()
    if table is None or not user_id:
        return
    try:
        ts       = _now_iso()
        event_id = f"{ts}#{uuid.uuid4().hex[:8]}"
        ttl      = int(time.time()) + TTL_DAYS * 86400
        item = {
            "user_id":    user_id,
            "event_id":   event_id,
            "shard":      _SHARD_KEY,
            "ts":         ts,
            "event_type": event_type,
            "ttl":        ttl,
        }
        for k, v in payload.items():
            if v is None:
                continue
            if isinstance(v, (dict, list)):
                item[k] = _trim(v)
            elif isinstance(v, str):
                item[k] = _trim(v)
            elif isinstance(v, float):
                item[k] = Decimal(str(v))
            else:
                item[k] = v
        table.put_item(Item=item)
    except Exception:
        logger.warning("Failed to record assistant event", exc_info=True)


def record_tool_call(user_id: str, tool_name: str, inputs: dict, result: str,
                     success: bool, duration_ms: int, model_id: str) -> None:
    record(user_id, "tool_call", {
        "tool_name":   tool_name,
        "inputs":      inputs,
        "result":      result,
        "success":     success,
        "duration_ms": duration_ms,
        "model_id":    model_id,
    })


def record_supervisor(user_id: str, verdict: str, reason: str, retry_count: int,
                      tools_used: list, model_id: str) -> None:
    record(user_id, "supervisor_verdict", {
        "verdict":     verdict,
        "reason":      reason,
        "retry_count": retry_count,
        "tools_used":  tools_used,
        "model_id":    model_id,
    })


def record_chat_complete(user_id: str, tools_used: list, tokens_in: int,
                         tokens_out: int, duration_ms: int, model_id: str,
                         error: str | None = None) -> None:
    record(user_id, "chat_complete", {
        "tools_used":  tools_used,
        "tokens_in":   tokens_in,
        "tokens_out":  tokens_out,
        "duration_ms": duration_ms,
        "model_id":    model_id,
        "error":       error,
    })
