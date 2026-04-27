"""Settings CRUD operations against DynamoDB."""

import ipaddress
import os
import re
import socket
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import db
from response import ok, error
from utils import build_update_expression

TABLE_NAME = os.environ["TABLE_NAME"]

CALENDAR_DEFAULTS = {
    "timezone":                 "America/New_York",
    "working_hours_start":      "09:00",
    "working_hours_end":        "17:00",
    "working_days":             [1, 2, 3, 4, 5],
    "slot_minutes":             30,
    "horizon_days":             14,
    "reschedule_min_gap_days":  2,
    "max_reschedules":          3,
    "default_duration_minutes": 60,
}

FITBIT_DEFAULTS = {
    "enabled": False,
}

DEFAULTS = {
    "dark_mode":                    False,
    "ntfy_url":                     "",
    "autosave_seconds":             300,
    "timezone":                     "",
    "display_name":                 "",
    "pal_name":                     "",
    "profile_inference_hours":      24,
    "home_finances_widget":         False,
    "chat_retention_days":          30,
    "supervisor_enabled":           True,
    "browser_notifications_enabled": False,
    "calendar":                     CALENDAR_DEFAULTS,
    "fitbit":                       FITBIT_DEFAULTS,
}

ALLOWED_KEYS = set(DEFAULTS.keys())
CHAT_RETENTION_MAX_DAYS = 3650

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _table():
    return db.get_table(TABLE_NAME)


def _validate_ntfy_url(url: str) -> str | None:
    """Return an error string if the URL is unsafe, or None if it's acceptable."""
    try:
        parsed = urlparse(url)
    except Exception:
        return "ntfy_url is not a valid URL"

    if parsed.scheme != "https":
        return "ntfy_url must use HTTPS"

    hostname = parsed.hostname
    if not hostname:
        return "ntfy_url has no hostname"

    try:
        ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        return f"ntfy_url hostname could not be resolved: {hostname}"

    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return "ntfy_url resolved to an invalid IP address"

    if addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved:
        return "ntfy_url must not point to a private or reserved address"

    return None


def _validate_calendar(cal: dict) -> tuple[str | None, dict | None]:
    """Validate a calendar settings sub-object. Returns (error, normalized) tuple."""
    if not isinstance(cal, dict):
        return "calendar must be an object", None

    out = dict(CALENDAR_DEFAULTS)
    out.update({k: v for k, v in cal.items() if k in CALENDAR_DEFAULTS})

    if not isinstance(out["timezone"], str) or not out["timezone"]:
        return "calendar.timezone must be a non-empty string", None

    for key in ("working_hours_start", "working_hours_end"):
        if not isinstance(out[key], str) or not _HHMM_RE.match(out[key]):
            return f"calendar.{key} must be HH:MM (24-hour)", None
    if out["working_hours_start"] >= out["working_hours_end"]:
        return "calendar.working_hours_start must be before working_hours_end", None

    days = out["working_days"]
    if not isinstance(days, list) or not days or not all(isinstance(d, int) and 1 <= d <= 7 for d in days):
        return "calendar.working_days must be a non-empty list of 1..7", None
    out["working_days"] = sorted(set(days))

    for key, lo, hi in (
        ("slot_minutes", 5, 240),
        ("horizon_days", 1, 60),
        ("reschedule_min_gap_days", 0, 30),
        ("max_reschedules", 0, 50),
        ("default_duration_minutes", 5, 480),
    ):
        try:
            v = int(out[key])
        except (TypeError, ValueError):
            return f"calendar.{key} must be an integer", None
        if v < lo or v > hi:
            return f"calendar.{key} must be between {lo} and {hi}", None
        out[key] = v

    if out["default_duration_minutes"] % out["slot_minutes"] != 0:
        return "calendar.default_duration_minutes must be a multiple of slot_minutes", None

    return None, out


def _merge_calendar(item: dict) -> dict:
    """Merge stored calendar partial onto defaults so reads always see all keys."""
    cal = item.get("calendar") or {}
    if not isinstance(cal, dict):
        cal = {}
    item["calendar"] = {**CALENDAR_DEFAULTS, **cal}

    fitbit = item.get("fitbit") or {}
    if not isinstance(fitbit, dict):
        fitbit = {}
    item["fitbit"] = {**FITBIT_DEFAULTS, **fitbit}
    return item


def _validate_fitbit(val: dict) -> tuple[str | None, dict | None]:
    if not isinstance(val, dict):
        return "fitbit must be an object", None
    out = dict(FITBIT_DEFAULTS)
    if "enabled" in val:
        out["enabled"] = bool(val["enabled"])
    return None, out


def get_settings(user_id: str) -> dict:
    item = _table().get_item(Key={"user_id": user_id}).get("Item")
    if not item:
        return ok(DEFAULTS)
    item.pop("user_id", None)
    return ok(_merge_calendar({**DEFAULTS, **item}))


def update_settings(user_id: str, body: dict) -> dict:
    fields = {k: v for k, v in body.items() if k in ALLOWED_KEYS}

    if not fields:
        return ok(DEFAULTS)

    if "ntfy_url" in fields and fields["ntfy_url"]:
        err = _validate_ntfy_url(fields["ntfy_url"])
        if err:
            return error(err)

    if "chat_retention_days" in fields:
        try:
            days = int(fields["chat_retention_days"])
        except (TypeError, ValueError):
            return error("chat_retention_days must be an integer")
        if days < 0 or days > CHAT_RETENTION_MAX_DAYS:
            return error(f"chat_retention_days must be between 0 and {CHAT_RETENTION_MAX_DAYS}")
        fields["chat_retention_days"] = days

    if "calendar" in fields:
        err, normalized = _validate_calendar(fields["calendar"])
        if err:
            return error(err)
        fields["calendar"] = normalized

    if "fitbit" in fields:
        err, normalized = _validate_fitbit(fields["fitbit"])
        if err:
            return error(err)
        fields["fitbit"] = normalized

    update_expr, names, values = build_update_expression(fields)

    result = _table().update_item(
        Key={"user_id": user_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
        ReturnValues="ALL_NEW",
    )

    item = result["Attributes"]
    item.pop("user_id", None)
    return ok(_merge_calendar({**DEFAULTS, **item}))


def test_notification(user_id: str, body: dict) -> dict:
    # Use URL from request body if provided, otherwise fall back to saved setting
    ntfy_url = (body.get("ntfy_url") or "").strip()
    if not ntfy_url:
        item = _table().get_item(Key={"user_id": user_id}).get("Item", {})
        ntfy_url = (item.get("ntfy_url") or "").strip()

    if not ntfy_url:
        return error("No ntfy URL configured")

    err = _validate_ntfy_url(ntfy_url)
    if err:
        return error(err)

    try:
        req = Request(
            ntfy_url,
            data=b"Your Memoire notifications are working.",
            headers={"Title": "Memoire test notification", "Priority": "3"},
            method="POST",
        )
        with urlopen(req, timeout=10):  # nosec B310 — URL validated as https + non-private by _validate_ntfy_url
            pass
    except Exception as e:
        return error(f"Could not reach ntfy endpoint: {e}")

    return ok({"sent": True})
