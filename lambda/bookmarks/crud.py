"""Bookmarks CRUD with server-side metadata scraping."""

import ipaddress
import os
import re
import socket
import uuid
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timezone

from botocore.exceptions import ClientError

import db
from response import ok, created, no_content, error, not_found
from utils import build_update_expression

TABLE_NAME = os.environ["TABLE_NAME"]
SORT_KEY   = "bookmark_id"

FETCH_TIMEOUT   = 8
MAX_URL_LEN     = 2048
MAX_TITLE_LEN   = 500
MAX_NOTE_LEN    = 10_000
MAX_TAGS        = 20
MAX_TAG_LEN     = 100
MAX_BOOKMARKS   = 1000


def _table():
    return db.get_table(TABLE_NAME)


# ── Metadata scraping ─────────────────────────────────────────────────────────

def _abs_url(base: str, href: str) -> str:
    """Resolve href relative to base, accept only http(s)."""
    resolved = urllib.parse.urljoin(base, href)
    if resolved.startswith(("http://", "https://")):
        return resolved
    return ""


def _is_safe_url(url: str) -> bool:
    """Return False if the URL resolves to a private/link-local/loopback address."""
    try:
        hostname = urllib.parse.urlparse(url).hostname or ""
        addrs = socket.getaddrinfo(hostname, None)
        for _, _, _, _, sockaddr in addrs:
            ip = ipaddress.ip_address(sockaddr[0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return False
        return True
    except Exception:
        return False


def _scrape_metadata(url: str) -> dict:
    """Fetch *url* and extract favicon_url and thumbnail_url.

    Returns a dict with those two keys (values may be empty strings).
    Never raises — failures produce empty strings.
    """
    result = {"favicon_url": "", "thumbnail_url": ""}
    if not _is_safe_url(url):
        return result
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; Memoire/1.0)"},
        )
        with urllib.request.urlopen(req, timeout=FETCH_TIMEOUT) as resp:  # nosec B310
            final_url = resp.geturl()
            chunk = resp.read(131_072).decode("utf-8", errors="ignore")
    except Exception:
        return result

    # thumbnail — og:image first, then twitter:image
    for pat in (
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image',
    ):
        m = re.search(pat, chunk, re.IGNORECASE)
        if m:
            thumb = _abs_url(final_url, m.group(1).strip())
            if thumb:
                result["thumbnail_url"] = thumb
                break

    # favicon — <link rel="icon"> or <link rel="shortcut icon">
    for pat in (
        r'<link[^>]+rel=["\'](?:shortcut )?icon["\'][^>]+href=["\']([^"\']+)',
        r'<link[^>]+href=["\']([^"\']+)["\'][^>]+rel=["\'](?:shortcut )?icon',
    ):
        m = re.search(pat, chunk, re.IGNORECASE)
        if m:
            favicon = _abs_url(final_url, m.group(1).strip())
            if favicon:
                result["favicon_url"] = favicon
                break

    # fallback: /favicon.ico
    if not result["favicon_url"]:
        parsed = urllib.parse.urlparse(final_url)
        result["favicon_url"] = f"{parsed.scheme}://{parsed.netloc}/favicon.ico"

    return result


# ── Validation ────────────────────────────────────────────────────────────────

def _validate_tags(tags) -> tuple[list | None, str | None]:
    """Return (cleaned_list, error_msg). error_msg is None on success."""
    if tags is None:
        return [], None
    if not isinstance(tags, list):
        return None, "tags must be a list"
    if len(tags) > MAX_TAGS:
        return None, f"tags may contain at most {MAX_TAGS} entries"
    cleaned = []
    for t in tags:
        if not isinstance(t, str):
            return None, "each tag must be a string"
        t = t.strip()
        if not t:
            continue
        if len(t) > MAX_TAG_LEN:
            return None, f"tag exceeds maximum length of {MAX_TAG_LEN}"
        cleaned.append(t)
    return list(dict.fromkeys(cleaned)), None  # deduplicate, preserve order


# ── List ──────────────────────────────────────────────────────────────────────

def list_bookmarks(user_id: str, query_params: dict) -> dict:
    items = db.query_by_user(_table(), user_id)

    tag_filter   = (query_params.get("tag") or "").strip().lower()
    search_query = (query_params.get("q") or "").strip().lower()

    results = []
    for item in items:
        if tag_filter:
            tags_lower = [t.lower() for t in (item.get("tags") or [])]
            if tag_filter not in tags_lower:
                continue

        if search_query:
            haystack = " ".join([
                item.get("title", ""),
                item.get("url", ""),
                item.get("description", ""),
                item.get("note", ""),
            ]).lower()
            if search_query not in haystack:
                continue

        results.append(item)

    results.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return ok(results)


# ── Create ────────────────────────────────────────────────────────────────────

def create_bookmark(user_id: str, body: dict) -> dict:
    url = (body.get("url") or "")
    if not isinstance(url, str) or not url.strip():
        return error("url is required")
    url = url.strip()
    if not url.startswith(("http://", "https://")):
        return error("url must start with http:// or https://")
    if len(url) > MAX_URL_LEN:
        return error(f"url exceeds maximum length of {MAX_URL_LEN}")

    existing = db.query_by_user(_table(), user_id)
    if len(existing) >= MAX_BOOKMARKS:
        return error(f"Maximum of {MAX_BOOKMARKS} bookmarks allowed")

    tags, err = _validate_tags(body.get("tags"))
    if err:
        return error(err)

    raw_note = body.get("note") or ""
    if not isinstance(raw_note, str):
        return error("note must be a string")
    note = raw_note.strip()
    if len(note) > MAX_NOTE_LEN:
        return error(f"note exceeds maximum length of {MAX_NOTE_LEN}")

    raw_title = body.get("title") or ""
    if not isinstance(raw_title, str):
        return error("title must be a string")

    # Scrape favicon and thumbnail only; title/description are user-provided
    meta = _scrape_metadata(url)
    title         = raw_title.strip()[:MAX_TITLE_LEN]
    favicon_url   = meta["favicon_url"]
    thumbnail_url = meta["thumbnail_url"]

    now = datetime.now(timezone.utc).isoformat()
    item = {
        "user_id":       user_id,
        "bookmark_id":   str(uuid.uuid4()),
        "url":           url,
        "title":         title,
        "favicon_url":   favicon_url,
        "thumbnail_url": thumbnail_url,
        "tags":          tags,
        "note":          note,
        "favourited":    False,
        "created_at":    now,
        "updated_at":    now,
    }
    # Remove empty strings so DynamoDB is clean (keep booleans and lists)
    item = {k: v for k, v in item.items() if v != ""}

    _table().put_item(Item=item)
    return created(item)


# ── Get ───────────────────────────────────────────────────────────────────────

def get_bookmark(user_id: str, bookmark_id: str) -> dict:
    item = db.get_item(_table(), user_id, SORT_KEY, bookmark_id)
    if not item:
        return not_found("Bookmark")
    return ok(item)


# ── Update ────────────────────────────────────────────────────────────────────

def update_bookmark(user_id: str, bookmark_id: str, body: dict) -> dict:
    # If URL is changing, re-scrape metadata (unless caller provides title)
    new_url = (body.get("url") or "").strip()
    if new_url:
        if not new_url.startswith(("http://", "https://")):
            return error("url must start with http:// or https://")
        if len(new_url) > MAX_URL_LEN:
            return error(f"url exceeds maximum length of {MAX_URL_LEN}")
        meta = _scrape_metadata(new_url)
        body = {**body, "favicon_url": meta["favicon_url"], "thumbnail_url": meta["thumbnail_url"]}

    updatable = {"url", "title", "favicon_url", "thumbnail_url", "note", "favourited"}
    fields: dict = {}
    for k in updatable:
        if k in body:
            fields[k] = body[k]

    if "tags" in body:
        tags, err = _validate_tags(body["tags"])
        if err:
            return error(err)
        fields["tags"] = tags

    if "note" in fields:
        raw_note = fields["note"] or ""
        if not isinstance(raw_note, str):
            return error("note must be a string")
        note = raw_note.strip()
        if len(note) > MAX_NOTE_LEN:
            return error(f"note exceeds maximum length of {MAX_NOTE_LEN}")
        fields["note"] = note

    if "title" in fields:
        raw_title = fields["title"] or ""
        if not isinstance(raw_title, str):
            return error("title must be a string")
        fields["title"] = raw_title.strip()[:MAX_TITLE_LEN]

    if "favourited" in fields and not isinstance(fields["favourited"], bool):
        return error("favourited must be a boolean")

    if not fields:
        return error("No valid fields provided for update")

    fields["updated_at"] = datetime.now(timezone.utc).isoformat()

    update_expr, names, values = build_update_expression(fields)

    try:
        result = _table().update_item(
            Key={"user_id": user_id, SORT_KEY: bookmark_id},
            UpdateExpression=update_expr,
            ExpressionAttributeNames=names,
            ExpressionAttributeValues=values,
            ConditionExpression="attribute_exists(bookmark_id)",
            ReturnValues="ALL_NEW",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return not_found("Bookmark")
        raise

    return ok(result["Attributes"])


# ── Delete ────────────────────────────────────────────────────────────────────

def delete_bookmark(user_id: str, bookmark_id: str) -> dict:
    try:
        _table().delete_item(
            Key={"user_id": user_id, SORT_KEY: bookmark_id},
            ConditionExpression="attribute_exists(bookmark_id)",
        )
    except ClientError as e:
        if e.response["Error"]["Code"] == "ConditionalCheckFailedException":
            return not_found("Bookmark")
        raise

    return no_content()
