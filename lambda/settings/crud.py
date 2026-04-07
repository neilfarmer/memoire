"""Settings CRUD operations against DynamoDB."""

import ipaddress
import os
import socket
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import db
from response import ok, error
from utils import build_update_expression

TABLE_NAME = os.environ["TABLE_NAME"]

DEFAULTS = {
    "dark_mode":               False,
    "ntfy_url":                "",
    "autosave_seconds":        300,
    "timezone":                "",
    "display_name":            "",
    "pal_name":                "",
    "profile_inference_hours": 24,
}

ALLOWED_KEYS = set(DEFAULTS.keys())


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


def get_settings(user_id: str) -> dict:
    item = _table().get_item(Key={"user_id": user_id}).get("Item")
    if not item:
        return ok(DEFAULTS)
    item.pop("user_id", None)
    return ok({**DEFAULTS, **item})


def update_settings(user_id: str, body: dict) -> dict:
    fields = {k: v for k, v in body.items() if k in ALLOWED_KEYS}

    if not fields:
        return ok(DEFAULTS)

    if "ntfy_url" in fields and fields["ntfy_url"]:
        err = _validate_ntfy_url(fields["ntfy_url"])
        if err:
            return error(err)

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
    return ok({**DEFAULTS, **item})


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
