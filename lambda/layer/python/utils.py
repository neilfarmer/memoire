"""Shared utility functions for Lambda CRUD modules."""

import re
from datetime import datetime, timezone


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def validate_date(d: str) -> str | None:
    """Return an error string if *d* is not a valid YYYY-MM-DD date, else None."""
    if not d or not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return "date must be YYYY-MM-DD"
    return None


def parse_tags(raw) -> list[str]:
    """Normalise a tag value that may be a list, a comma-separated string, or None."""
    if not raw:
        return []
    if isinstance(raw, list):
        return [t.strip() for t in raw if t.strip()]
    return [t.strip() for t in str(raw).split(",") if t.strip()]


def build_update_expression(fields: dict) -> tuple[str, dict, dict]:
    """
    Build a DynamoDB SET UpdateExpression from a flat dict of field→value pairs.

    Returns (UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues).
    """
    set_parts: list[str] = []
    names: dict = {}
    values: dict = {}

    for i, (key, val) in enumerate(fields.items()):
        names[f"#f{i}"]  = key
        values[f":v{i}"] = val
        set_parts.append(f"#f{i} = :v{i}")

    return "SET " + ", ".join(set_parts), names, values
