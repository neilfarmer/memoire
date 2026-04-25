"""Wiki-style `[[type:id]]` link parsing and persistence.

Shared helpers used by writer Lambdas (notes, journal, tasks) to keep the
`links` table in sync with the bodies of their entities. The `links` Lambda
owns the read endpoints.

Edge shape stored in DynamoDB:

    {
        "user_id":     "<user>",
        "link_key":    "<source_type>#<source_id>#<target_type>#<target_id>",
        "source_type": "note",
        "source_id":   "<uuid>",
        "target_type": "task",
        "target_id":   "<uuid>",
        "target_key":  "<target_type>#<target_id>",
        "created_at":  "<iso8601>"
    }

A reverse GSI (`reverse-index`) on (user_id, target_key) backs the backlinks
panel.
"""

import os
import re
from datetime import datetime, timezone

from boto3.dynamodb.conditions import Key

import db

LINKS_TABLE = os.environ.get("LINKS_TABLE", "")

# Restrict the recognised entity namespaces so a stray `[[foo:bar]]` does not
# pollute the graph. Keep in sync with the public type list in handler code.
LINK_TYPES = {
    "task", "note", "journal", "goal", "habit", "bookmark",
    "favorite", "feed", "diagram", "debt", "income", "expense",
    "health", "nutrition",
}

# Matches `[[type:id]]`. Ids accept alphanumerics plus `-`, `_`, and `:` to
# cover composite sort keys such as journal `YYYY-MM-DD`.
_LINK_RE = re.compile(r"\[\[([a-z_]+):([A-Za-z0-9:_\-]+)\]\]")


def parse_wiki_links(text: str | None) -> list[tuple[str, str]]:
    """Extract `(type, id)` pairs from *text*.

    Duplicates are removed while preserving first-seen order. Unknown
    types are dropped silently — the regex is intentionally lax so we never
    fail a save over a malformed link.
    """
    if not text:
        return []
    seen: set[tuple[str, str]] = set()
    out: list[tuple[str, str]] = []
    for m in _LINK_RE.finditer(text):
        t, i = m.group(1), m.group(2)
        if t not in LINK_TYPES:
            continue
        key = (t, i)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    return out


def _link_key(source_type: str, source_id: str,
              target_type: str, target_id: str) -> str:
    return f"{source_type}#{source_id}#{target_type}#{target_id}"


def _source_prefix(source_type: str, source_id: str) -> str:
    return f"{source_type}#{source_id}#"


def _table():
    return db.get_table(LINKS_TABLE)


def _query_outbound(user_id: str, source_type: str, source_id: str) -> list[dict]:
    items: list[dict] = []
    params = {
        "KeyConditionExpression":
            Key("user_id").eq(user_id)
            & Key("link_key").begins_with(_source_prefix(source_type, source_id)),
    }
    while True:
        resp = _table().query(**params)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items


def sync_links(user_id: str, source_type: str, source_id: str,
               texts: list[str | None] | None) -> None:
    """Reconcile the `links` table to match the wiki-links in *texts*.

    - Extracts `[[type:id]]` references across all provided text fragments
      (title + body, etc.).
    - Deletes rows that no longer appear.
    - Writes rows for new references with a fresh `created_at`.
    - Skips self-references `(source_type, source_id) == (target_type, target_id)`.
    - No-op when `LINKS_TABLE` is unset (e.g. legacy deploys).
    """
    if not LINKS_TABLE:
        return

    desired: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for t in (texts or []):
        for pair in parse_wiki_links(t):
            if pair in seen:
                continue
            # Drop self-references — they add noise and break some UIs.
            if pair == (source_type, source_id):
                continue
            seen.add(pair)
            desired.append(pair)

    desired_keys = {
        _link_key(source_type, source_id, tt, ti): (tt, ti)
        for tt, ti in desired
    }

    existing = _query_outbound(user_id, source_type, source_id)
    existing_keys = {item["link_key"] for item in existing}

    to_delete = existing_keys - desired_keys.keys()
    to_add    = desired_keys.keys() - existing_keys

    tbl = _table()
    with tbl.batch_writer() as batch:
        for link_key in to_delete:
            batch.delete_item(Key={"user_id": user_id, "link_key": link_key})
        now = datetime.now(timezone.utc).isoformat()
        for link_key in to_add:
            tt, ti = desired_keys[link_key]
            batch.put_item(Item={
                "user_id":     user_id,
                "link_key":    link_key,
                "source_type": source_type,
                "source_id":   source_id,
                "target_type": tt,
                "target_id":   ti,
                "target_key":  f"{tt}#{ti}",
                "created_at":  now,
            })


def delete_source_links(user_id: str, source_type: str, source_id: str) -> None:
    """Remove every outbound link originating from (source_type, source_id)."""
    if not LINKS_TABLE:
        return
    existing = _query_outbound(user_id, source_type, source_id)
    if not existing:
        return
    with _table().batch_writer() as batch:
        for item in existing:
            batch.delete_item(Key={"user_id": user_id, "link_key": item["link_key"]})


def query_outbound(user_id: str, source_type: str, source_id: str) -> list[dict]:
    """Return all outbound links from the given source entity."""
    if not LINKS_TABLE:
        return []
    return _query_outbound(user_id, source_type, source_id)


def query_inbound(user_id: str, target_type: str, target_id: str) -> list[dict]:
    """Return all inbound links pointing at the given target entity."""
    if not LINKS_TABLE:
        return []
    items: list[dict] = []
    params = {
        "IndexName": "reverse-index",
        "KeyConditionExpression":
            Key("user_id").eq(user_id)
            & Key("target_key").eq(f"{target_type}#{target_id}"),
    }
    while True:
        resp = _table().query(**params)
        items.extend(resp.get("Items", []))
        if "LastEvaluatedKey" not in resp:
            break
        params["ExclusiveStartKey"] = resp["LastEvaluatedKey"]
    return items
